from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import sqlite3
import re

DB_FILE = "ventas_locro.db"

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

# Ciclo de vida de la app: Crea la tabla al arrancar el servidor
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
    # Validaciones
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

    # Guardar en SQLite
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ventas (vendedor, nombre, apellido, telefono, mail, entrega, direccion, cantidad, total, pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (vendedor, nombre_limpio, apellido_limpio, telefono_limpio, mail, entrega, direccion, cantidad, total_a_pagar, pago))
        conn.commit()

    # Mensaje de éxito simple (puedes cambiarlo por un HTML de éxito luego)
    return {
        "mensaje": "¡Venta registrada con éxito!",
        "vendedor": vendedor,
        "comprador": f"{nombre_limpio} {apellido_limpio}",
        "porciones": cantidad,
        "total_a_cobrar": f"${total_a_pagar}"
    }

# Agrega esto al final de tu main.py

@app.get("/admin_scout", response_class=HTMLResponse)
async def panel_admin(request: Request):
    with sqlite3.connect(DB_FILE) as conn:
        # Esto hace que SQLite devuelva las filas como diccionarios, 
        # ideal para leerlos fácil en el HTML
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # Traemos todas las ventas, ordenadas por la más reciente
        cursor.execute("SELECT * FROM ventas ORDER BY fecha DESC")
        ventas = cursor.fetchall()
        
        # Calculamos algunos totales rápidos en Python
        total_porciones = sum(venta["cantidad"] for venta in ventas)
        total_plata_general = sum(venta["total"] for venta in ventas)
        # Sumamos solo la plata de los que marcaron "pagado"
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