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
    num = re.sub(r'\D', '', telefono)
    if num.startswith('0'): num = num[1:]
    if num.startswith('15') and len(num) == 12: num = num[2:]
    return num

# 3. Rutas
@app.get("/venta/{vendedor}", response_class=HTMLResponse)
async def formulario_venta(request: Request, vendedor: str):
    return templates.TemplateResponse(
        request=request, 
        name="formulario.html", 
        context={"vendedor": vendedor}
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
    telefono_limpio = limpiar_telefono(telefono)
    
    if len(telefono_limpio) != 10:
        raise HTTPException(status_code=400, detail="El teléfono debe tener 10 números válidos (sin contar el 0 ni el 15).")
    
    if entrega == "delivery" and not direccion:
        raise HTTPException(status_code=400, detail="Debes ingresar una dirección para el delivery.")
        
    if cantidad < 1:
         raise HTTPException(status_code=400, detail="La cantidad debe ser al menos 1.")

    total_a_pagar = calcular_precio(cantidad)

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ventas (vendedor, nombre, apellido, telefono, mail, entrega, direccion, cantidad, total, pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (vendedor, nombre_limpio, apellido_limpio, telefono_limpio, mail, entrega, direccion, cantidad, total_a_pagar, pago))
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
            "total_porciones": total_porciones,
            "total_plata_general": total_plata_general,
            "total_recaudado_real": total_recaudado_real,
            "plata_a_cobrar": plata_a_cobrar
        }
    )

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