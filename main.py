import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from contextlib import asynccontextmanager
import re
import io
from openpyxl import Workbook
from pydantic import BaseModel
from typing import Optional
from fastapi.staticfiles import StaticFiles

# --- Configuración de Base de Datos PostgreSQL ---
# En tu computadora puedes probar seteando esta variable, 
# en Render la configuras en la pestaña "Environment".
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://usuario:password@localhost:5432/locro_db")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- Configuración de Seguridad ---
security = HTTPBasic()

def verificar_credenciales(credentials: HTTPBasicCredentials = Depends(security)):
    usuario_correcto = secrets.compare_digest(credentials.username, "admin")
    password_correcto = secrets.compare_digest(credentials.password, "siemprelistos")
    
    if not (usuario_correcto and password_correcto):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- Inicialización de Base de Datos ---
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # Tabla de ventas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ventas (
                    id SERIAL PRIMARY KEY,
                    vendedor TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    apellido TEXT NOT NULL,
                    telefono TEXT NOT NULL,
                    mail TEXT,
                    entrega TEXT NOT NULL,
                    direccion TEXT,
                    cantidad INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    pago TEXT NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Tabla de Vendedores Permitidos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vendedores (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE,
                    rama TEXT NOT NULL
                )
            ''')

            # Insertar vendedor inicial por defecto si la tabla está vacía
            cursor.execute("SELECT COUNT(*) FROM vendedores")
            if cursor.fetchone()[0] == 0:
                # Usamos ON CONFLICT DO NOTHING por seguridad si hay concurrencia inicial
                cursor.execute("INSERT INTO vendedores (nombre, rama) VALUES ('Ignacio_Otranto', 'Rovers') ON CONFLICT DO NOTHING")

            # Tabla de Entregas de dinero
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS entregas_dinero (
                    id SERIAL PRIMARY KEY,
                    vendedor TEXT NOT NULL,
                    monto INTEGER NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

# --- Modelos Pydantic ---
class EntregaCreate(BaseModel):
    vendedor: str
    monto: int

class VendedorCreate(BaseModel):
    nombre: str
    rama: str

class VentaUpdate(BaseModel):
    nombre: str
    apellido: str
    telefono: str
    mail: Optional[str] = None
    entrega: str
    direccion: Optional[str] = None
    cantidad: int
    pago: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Funciones Auxiliares ---
def calcular_precio(cantidad: int) -> int:
    return (cantidad // 2) * 18000 + (cantidad % 2) * 10000

def limpiar_telefono(telefono: str) -> str:
    if telefono.startswith("+54"):
        telefono = telefono[3:]
    elif telefono.startswith("54") and len(telefono) > 10:
        telefono = telefono[2:]

    num = re.sub(r'\D', '', telefono)

    if num.startswith('9') and len(num) == 11:
        num = num[1:]
    if num.startswith('0'):
        num = num[1:]

    if '15' in num and len(num) >= 12:
        num = num.replace('15', '', 1)
    
    if len(num) == 12 and num[2:4] == '15':
        num = num[:2] + num[4:]
    elif len(num) == 13 and num[3:5] == '15':
        num = num[:3] + num[5:]
    elif len(num) == 14 and num[4:6] == '15':
        num = num[:4] + num[6:]

    return num

# --- Rutas ---

@app.get("/venta/{vendedor}", response_class=HTMLResponse)
async def formulario_venta(request: Request, vendedor: str):
    vendedor_limpio = vendedor.strip().lower()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nombre FROM vendedores WHERE nombre = %s", (vendedor_limpio,))
            if not cursor.fetchone():
                return HTMLResponse(content="<h1>Error 404: Vendedor no encontrado</h1><p>Verifica que el link sea correcto.</p>", status_code=404)

    return templates.TemplateResponse(
        request=request, 
        name="formulario.html", 
        context={"vendedor": vendedor_limpio}
    )

@app.post("/procesar_venta")
async def procesar_venta(
    vendedor: str = Form(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    telefono: str = Form(...),
    entrega: str = Form(...),
    direccion: str = Form(None),
    cantidad: int = Form(...),
    pago: str = Form(...),
    mail: str = Form(None)
):
    nombre_limpio = nombre.strip().title()
    apellido_limpio = apellido.strip().title()
    
    if not re.match(r"^[A-Za-zÁ-Úá-úñÑ\s]{2,}$", nombre_limpio):
        raise HTTPException(status_code=400, detail="El nombre debe contener al menos 2 letras y sin números ni caracteres especiales.")
    if not re.match(r"^[A-Za-zÁ-Úá-úñÑ\s]{2,}$", apellido_limpio):
        raise HTTPException(status_code=400, detail="El apellido debe contener al menos 2 letras y sin números ni caracteres especiales.")

    mail_limpio = None
    if mail and mail.strip():
        mail_limpio = mail.strip()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", mail_limpio):
             raise HTTPException(status_code=400, detail="El correo electrónico no tiene un formato válido.")

    telefono_limpio = limpiar_telefono(telefono)
    if len(telefono_limpio) != 10:
        raise HTTPException(status_code=400, detail="El teléfono debe tener exactamente 10 números válidos (sin contar el 0, ni el 15, ni el +549).")
    
    if entrega not in ["retiro", "delivery"]:
        raise HTTPException(status_code=400, detail="Opción de entrega inválida.")

    if entrega == "delivery":
        if not direccion or len(direccion.strip()) < 5:
            raise HTTPException(status_code=400, detail="Debes ingresar una dirección válida para el delivery (mínimo 5 caracteres).")
        direccion = direccion.strip()
    else:
        direccion = None 

    if pago not in ["pagado", "al_recibir"]:
        raise HTTPException(status_code=400, detail="Opción de pago inválida.")

    if cantidad < 1:
         raise HTTPException(status_code=400, detail="La cantidad debe ser al menos 1.")

    vendedor_limpio = vendedor.strip().lower()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nombre FROM vendedores WHERE nombre = %s", (vendedor_limpio,))
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail="Vendedor no válido.")

            total_a_pagar = calcular_precio(cantidad)

            cursor.execute('''
                INSERT INTO ventas (vendedor, nombre, apellido, telefono, mail, entrega, direccion, cantidad, total, pago)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (vendedor_limpio, nombre_limpio, apellido_limpio, telefono_limpio, mail_limpio, entrega, direccion, cantidad, total_a_pagar, pago))
            conn.commit()

    return {
        "mensaje": "¡Venta registrada con éxito!",
        "vendedor": vendedor,
        "comprador": f"{nombre_limpio} {apellido_limpio}",
        "porciones": cantidad,
        "total_a_cobrar": f"${total_a_pagar}"
    }

@app.get("/admin_scout", response_class=HTMLResponse)
async def panel_admin(request: Request, usuario: str = Depends(verificar_credenciales)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT ventas.*, COALESCE(vendedores.rama, 'Sin Rama') as rama 
                FROM ventas 
                LEFT JOIN vendedores ON ventas.vendedor = vendedores.nombre 
                ORDER BY ventas.fecha DESC
            ''')
            ventas = cursor.fetchall()
            
            cursor.execute('''
                SELECT v.id, v.nombre, COALESCE(v.rama, 'Sin Rama') as rama,
                       COALESCE((SELECT SUM(monto) FROM entregas_dinero WHERE vendedor = v.nombre), 0) as dinero_entregado
                FROM vendedores v
                ORDER BY v.nombre ASC
            ''')
            vendedores = cursor.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "ventas": ventas,
            "vendedores": vendedores
        }
    )

@app.post("/api/entregas", status_code=status.HTTP_201_CREATED)
async def registrar_entrega(entrega: EntregaCreate, usuario: str = Depends(verificar_credenciales)):
    if entrega.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT SUM(total) FROM ventas WHERE vendedor = %s AND pago = 'pagado'", (entrega.vendedor,))
            total_recaudado = cursor.fetchone()[0] or 0

            cursor.execute("SELECT SUM(monto) FROM entregas_dinero WHERE vendedor = %s", (entrega.vendedor,))
            ya_entregado = cursor.fetchone()[0] or 0

            disponible = total_recaudado - ya_entregado

            if entrega.monto > disponible:
                raise HTTPException(status_code=400, detail=f"El vendedor solo tiene ${disponible} disponibles para entregar (Recaudó ${total_recaudado} y ya entregó ${ya_entregado}).")

            cursor.execute("INSERT INTO entregas_dinero (vendedor, monto) VALUES (%s, %s)", (entrega.vendedor, entrega.monto))
            conn.commit()
        
    return {"mensaje": f"Se registraron ${entrega.monto} correctamente."}

@app.post("/api/vendedores", status_code=status.HTTP_201_CREATED)
async def crear_vendedor(vendedor: VendedorCreate, usuario: str = Depends(verificar_credenciales)):
    nombre_limpio = vendedor.nombre.strip().lower()
    
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre del vendedor no puede estar vacío.")
    
    ramas_permitidas = ["Manada", "Unidad", "Caminantes", "Rovers", "Educadores/acompañantes"]
    if vendedor.rama not in ramas_permitidas:
        raise HTTPException(status_code=400, detail="Rama seleccionada no válida.")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # PostgreSQL requiere RETURNING para obtener el ID recién insertado
                cursor.execute("INSERT INTO vendedores (nombre, rama) VALUES (%s, %s) RETURNING id", (nombre_limpio, vendedor.rama))
                nuevo_id = cursor.fetchone()[0]
                conn.commit()
                return {
                    "mensaje": "Vendedor creado exitosamente.", 
                    "id": nuevo_id, 
                    "nombre": nombre_limpio,
                    "rama": vendedor.rama
                }
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="El vendedor ya existe.")

@app.delete("/api/vendedores/{vendedor_id}")
async def eliminar_vendedor(vendedor_id: int, usuario: str = Depends(verificar_credenciales)):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM vendedores WHERE id = %s", (vendedor_id,))
            conn.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Vendedor no encontrado.")
    return {"mensaje": "Vendedor eliminado exitosamente."}

@app.delete("/api/ventas/{venta_id}")
async def eliminar_venta(venta_id: int, usuario: str = Depends(verificar_credenciales)):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM ventas WHERE id = %s", (venta_id,))
            conn.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Venta no encontrada.")
    return {"mensaje": "Venta eliminada exitosamente."}

@app.put("/api/ventas/{venta_id}")
async def editar_venta(venta_id: int, venta: VentaUpdate, usuario: str = Depends(verificar_credenciales)):
    nombre_limpio = venta.nombre.strip().title()
    apellido_limpio = venta.apellido.strip().title()
    telefono_limpio = limpiar_telefono(venta.telefono)

    if len(telefono_limpio) != 10:
        raise HTTPException(status_code=400, detail="El teléfono debe tener 10 números.")

    if venta.entrega == "delivery" and not venta.direccion:
        raise HTTPException(status_code=400, detail="Debes ingresar una dirección para el delivery.")

    if venta.cantidad < 1:
        raise HTTPException(status_code=400, detail="La cantidad debe ser al menos 1.")

    total_a_pagar = calcular_precio(venta.cantidad)

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE ventas
                SET nombre = %s, apellido = %s, telefono = %s, mail = %s, entrega = %s, direccion = %s, cantidad = %s, total = %s, pago = %s
                WHERE id = %s
            ''', (nombre_limpio, apellido_limpio, telefono_limpio, venta.mail, venta.entrega, venta.direccion, venta.cantidad, total_a_pagar, venta.pago, venta_id))
            conn.commit()

            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Venta no encontrada.")

    return {"mensaje": "Venta actualizada exitosamente."}

@app.get("/descargar_excel")
async def descargar_excel(rama: Optional[str] = None, vendedor: Optional[str] = None, usuario: str = Depends(verificar_credenciales)):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            query = '''
                SELECT ventas.vendedor, COALESCE(vendedores.rama, 'Sin Rama') as rama, 
                       ventas.nombre, ventas.apellido, ventas.telefono, ventas.mail, 
                       ventas.entrega, ventas.direccion, ventas.cantidad, ventas.total, 
                       ventas.pago, ventas.fecha
                FROM ventas
                LEFT JOIN vendedores ON ventas.vendedor = vendedores.nombre
                WHERE 1=1
            '''
            parametros = []

            if vendedor:
                query += " AND ventas.vendedor = %s"
                parametros.append(vendedor)
            if rama:
                if rama == "Sin Rama":
                    query += " AND vendedores.rama IS NULL"
                else:
                    query += " AND vendedores.rama = %s"
                    parametros.append(rama)
            
            query += " ORDER BY ventas.fecha DESC"
            
            # Convertimos la lista de parámetros en una tupla, que es lo que espera psycopg2
            cursor.execute(query, tuple(parametros))
            ventas = cursor.fetchall()
            
            nombres_columnas = ["Vendedor", "Rama", "Nombre del Comprador", "Apellido", "Teléfono", "Mail", "Entrega", "Dirección", "Cantidad", "Total", "Pago", "Fecha"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas Locro"

    ws.append(nombres_columnas)

    for venta in ventas:
        ws.append(venta)

    output = io.BytesIO()
    wb.save(output)

    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response = Response(content=output.getvalue(), media_type=media_type)
    response.headers["Content-Disposition"] = 'attachment; filename="ventas_locro_scout.xlsx"'
    
    return response