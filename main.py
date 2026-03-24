import secrets
from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from contextlib import asynccontextmanager
import sqlite3
import re
import csv
import io
from fastapi import Response # Agrega 'Response' a tus importaciones de fastapi
from openpyxl import Workbook
from pydantic import BaseModel
from typing import Optional

DB_FILE = "ventas_locro.db"

# --- NUEVO: Configuración de Seguridad ---
security = HTTPBasic()

def verificar_credenciales(credentials: HTTPBasicCredentials = Depends(security)):
    # Aquí defines tu usuario y contraseña. Usa secrets para mayor seguridad interna.
    usuario_correcto = secrets.compare_digest(credentials.username, "admin")
    password_correcto = secrets.compare_digest(credentials.password, "siemprelistos")
    
    if not (usuario_correcto and password_correcto):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
# -----------------------------------------

# 1. Configuración de la Base de Datos
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Tabla de ventas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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

        # Nueva Tabla: Vendedores Permitidos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vendedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE
            )
        ''')

        # Insertar vendedor inicial por defecto si la tabla está vacía para que el sistema funcione
        cursor.execute("SELECT COUNT(*) FROM vendedores")
        if cursor.fetchone()[0] == 0:
            # Como ejemplo, insertamos 'jules' (o 'admin', o un nombre genérico)
            cursor.execute("INSERT INTO vendedores (nombre) VALUES ('jules')")

        conn.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# 2. Funciones Auxiliares
def calcular_precio(cantidad: int) -> int:
    return (cantidad // 2) * 18000 + (cantidad % 2) * 10000

def limpiar_telefono(telefono: str) -> str:
    # Eliminar cualquier prefijo de país si está presente
    if telefono.startswith("+54"):
        telefono = telefono[3:]
    elif telefono.startswith("54") and len(telefono) > 10:
        telefono = telefono[2:]

    num = re.sub(r'\D', '', telefono)

    # Remover 9 (para celulares en el exterior/nacional si se incluyó el +549)
    if num.startswith('9') and len(num) == 11:
        num = num[1:]

    # Remover el 0 inicial (prefijo interurbano)
    if num.startswith('0'):
        num = num[1:]

    # Remover el 15 (prefijo de celular antiguo)
    if '15' in num and len(num) >= 12: # Ej. 11 15 xxxx xxxx
        num = num.replace('15', '', 1)
    elif num.startswith('15') and len(num) == 10: # Esto no es válido usualmente (15xxxxxxxx)
        pass # Podría ser un error, pero el regex lo filtrará más adelante si no son 10.

    # Un paso general extra para remover '15' si quedó exactamente después de la característica
    if len(num) == 12 and num[2:4] == '15':
        num = num[:2] + num[4:]
    elif len(num) == 13 and num[3:5] == '15':
        num = num[:3] + num[5:]
    elif len(num) == 14 and num[4:6] == '15':
        num = num[:4] + num[6:]

    return num

# --- NUEVO: Modelos Pydantic para APIs CRUD ---
class VendedorCreate(BaseModel):
    nombre: str

class VentaUpdate(BaseModel):
    nombre: str
    apellido: str
    telefono: str
    mail: Optional[str] = None
    entrega: str
    direccion: Optional[str] = None
    cantidad: int
    pago: str

# 3. Rutas
@app.get("/venta/{vendedor}", response_class=HTMLResponse)
async def formulario_venta(request: Request, vendedor: str):
    vendedor_limpio = vendedor.strip().lower()

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM vendedores WHERE nombre = ?", (vendedor_limpio,))
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
    
    # Validaciones de nombre y apellido
    if not re.match(r"^[A-Za-zÁ-Úá-úñÑ\s]{2,}$", nombre_limpio):
        raise HTTPException(status_code=400, detail="El nombre debe contener al menos 2 letras y sin números ni caracteres especiales.")
    if not re.match(r"^[A-Za-zÁ-Úá-úñÑ\s]{2,}$", apellido_limpio):
        raise HTTPException(status_code=400, detail="El apellido debe contener al menos 2 letras y sin números ni caracteres especiales.")

    # Validaciones de mail
    mail_limpio = None
    if mail and mail.strip():
        mail_limpio = mail.strip()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", mail_limpio):
             raise HTTPException(status_code=400, detail="El correo electrónico no tiene un formato válido.")

    # Validaciones de teléfono
    telefono_limpio = limpiar_telefono(telefono)
    if len(telefono_limpio) != 10:
        raise HTTPException(status_code=400, detail="El teléfono debe tener exactamente 10 números válidos (sin contar el 0, ni el 15, ni el +549).")
    
    # Validaciones de entrega y dirección
    if entrega not in ["retiro", "delivery"]:
        raise HTTPException(status_code=400, detail="Opción de entrega inválida.")

    if entrega == "delivery":
        if not direccion or len(direccion.strip()) < 5:
            raise HTTPException(status_code=400, detail="Debes ingresar una dirección válida para el delivery (mínimo 5 caracteres).")
        direccion = direccion.strip()
    else:
        direccion = None # Si retira, no nos importa la dirección

    # Validaciones de pago
    if pago not in ["pagado", "al_recibir"]:
        raise HTTPException(status_code=400, detail="Opción de pago inválida.")

    # Validaciones de cantidad
    if cantidad < 1:
         raise HTTPException(status_code=400, detail="La cantidad debe ser al menos 1.")

    vendedor_limpio = vendedor.strip().lower()

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Validación de Vendedor en base de datos
        cursor.execute("SELECT nombre FROM vendedores WHERE nombre = ?", (vendedor_limpio,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="Vendedor no válido.")

        total_a_pagar = calcular_precio(cantidad)

        cursor.execute('''
            INSERT INTO ventas (vendedor, nombre, apellido, telefono, mail, entrega, direccion, cantidad, total, pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (vendedor_limpio, nombre_limpio, apellido_limpio, telefono_limpio, mail_limpio, entrega, direccion, cantidad, total_a_pagar, pago))
        conn.commit()

    return {
        "mensaje": "¡Venta registrada con éxito!",
        "vendedor": vendedor,
        "comprador": f"{nombre_limpio} {apellido_limpio}",
        "porciones": cantidad,
        "total_a_cobrar": f"${total_a_pagar}"
    }

# --- NUEVA RUTA PROTEGIDA ---
# Nota el "Depends(verificar_credenciales)"
@app.get("/admin_scout", response_class=HTMLResponse)
async def panel_admin(request: Request, usuario: str = Depends(verificar_credenciales)):
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM ventas ORDER BY fecha DESC")
        ventas = cursor.fetchall()
        
        cursor.execute("SELECT * FROM vendedores ORDER BY nombre ASC")
        vendedores = cursor.fetchall()

        # Ojo: si no hay ventas todavía, sum() tiraría error si no le pasamos un valor por defecto, 
        # pero en Python los generadores vacíos devuelven 0, así que estamos bien.
        total_porciones = sum(venta["cantidad"] for venta in ventas)
        total_plata_general = sum(venta["total"] for venta in ventas)
        total_recaudado_real = sum(venta["total"] for venta in ventas if venta["pago"] == "pagado")
        plata_a_cobrar = total_plata_general - total_recaudado_real

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "ventas": ventas,
            "vendedores": vendedores,
            "total_porciones": total_porciones,
            "total_plata_general": total_plata_general,
            "total_recaudado_real": total_recaudado_real,
            "plata_a_cobrar": plata_a_cobrar
        }
    )

# --- NUEVAS RUTAS CRUD (Protegidas) ---

@app.post("/api/vendedores", status_code=status.HTTP_201_CREATED)
async def crear_vendedor(vendedor: VendedorCreate, usuario: str = Depends(verificar_credenciales)):
    nombre_limpio = vendedor.nombre.strip().lower()
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre del vendedor no puede estar vacío.")

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO vendedores (nombre) VALUES (?)", (nombre_limpio,))
            conn.commit()
            return {"mensaje": "Vendedor creado exitosamente.", "id": cursor.lastrowid, "nombre": nombre_limpio}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="El vendedor ya existe.")

@app.delete("/api/vendedores/{vendedor_id}")
async def eliminar_vendedor(vendedor_id: int, usuario: str = Depends(verificar_credenciales)):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vendedores WHERE id = ?", (vendedor_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Vendedor no encontrado.")
        return {"mensaje": "Vendedor eliminado exitosamente."}

@app.delete("/api/ventas/{venta_id}")
async def eliminar_venta(venta_id: int, usuario: str = Depends(verificar_credenciales)):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ventas WHERE id = ?", (venta_id,))
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

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE ventas
            SET nombre = ?, apellido = ?, telefono = ?, mail = ?, entrega = ?, direccion = ?, cantidad = ?, total = ?, pago = ?
            WHERE id = ?
        ''', (nombre_limpio, apellido_limpio, telefono_limpio, venta.mail, venta.entrega, venta.direccion, venta.cantidad, total_a_pagar, venta.pago, venta_id))
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Venta no encontrada.")

    return {"mensaje": "Venta actualizada exitosamente."}

@app.get("/descargar_csv")
async def descargar_csv(usuario: str = Depends(verificar_credenciales)):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Traemos todas las ventas
        cursor.execute("SELECT * FROM ventas ORDER BY fecha DESC")
        ventas = cursor.fetchall()
        
        # Obtenemos los nombres de las columnas para el encabezado del Excel
        nombres_columnas = [description[0] for description in cursor.description]

    # Creamos un archivo de texto en la memoria RAM
    output = io.StringIO()
    # Usamos punto y coma (;) porque el Excel configurado en Argentina 
    # suele separar las columnas así por defecto.
    writer = csv.writer(output, delimiter=';') 

    # Escribimos la primera fila con los títulos
    writer.writerow(nombres_columnas)
    
    # Escribimos todas las filas de ventas
    for venta in ventas:
        writer.writerow(venta)

    # Preparamos la respuesta para que el navegador entienda que es una descarga
    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="ventas_locro_scout.csv"'
    
    return response

@app.get("/descargar_excel")
async def descargar_excel(usuario: str = Depends(verificar_credenciales)):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Traemos todas las ventas
        cursor.execute("SELECT * FROM ventas ORDER BY fecha DESC")
        ventas = cursor.fetchall()
        
        # Obtenemos los nombres de las columnas
        nombres_columnas = [description[0] for description in cursor.description]

    # Creamos un libro de Excel en memoria
    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas Locro"

    # Agregamos la fila de los encabezados
    ws.append(nombres_columnas)

    # Agregamos todas las filas de ventas
    for venta in ventas:
        ws.append(venta)

    # Guardamos el Excel en un archivo binario en memoria (BytesIO)
    output = io.BytesIO()
    wb.save(output)

    # Preparamos la respuesta indicando que es un archivo .xlsx
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response = Response(content=output.getvalue(), media_type=media_type)
    response.headers["Content-Disposition"] = 'attachment; filename="ventas_locro_scout.xlsx"'
    
    return response