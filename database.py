import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = 'imperio_data.db'

def conectar():
    return sqlite3.connect(DB_NAME)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    
    # 1. Tabla Clientes
    c.execute('''CREATE TABLE IF NOT EXISTS clientes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, notas TEXT)''')
    
    # 2. Tabla Cotizaciones (Relacionada con cliente por nombre o ID)
    c.execute('''CREATE TABLE IF NOT EXISTS cotizaciones 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, 
                  trabajo TEXT, monto REAL, estado TEXT)''')
    
    # 3. Tabla Inventario
    c.execute('''CREATE TABLE IF NOT EXISTS inventario 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, cantidad REAL, 
                  unidad TEXT, precio_usd REAL)''')
    
    # 4. Tabla Ventas (Finalizadas)
    c.execute('''CREATE TABLE IF NOT EXISTS ventas 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, 
                  monto_total REAL, metodo_pago TEXT)''')

    # 5. Tabla Usuarios (Seguridad)
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                 (username TEXT PRIMARY KEY, password TEXT, rol TEXT)''')
    
    # Insertar admin por defecto si no existe
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', '1234', 'superadmin')")
    
    conn.commit()
    conn.close()

# --- FUNCIONES CRUD CLIENTES ---
def add_cliente(nombre, whatsapp, notas):
    conn = conectar()
    conn.execute("INSERT INTO clientes (nombre, whatsapp, notas) VALUES (?,?,?)", (nombre, whatsapp, notas))
    conn.commit()
    conn.close()

def get_clientes():
    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM clientes", conn)
    conn.close()
    return df

# --- FUNCIONES CRUD COTIZACIONES ---
def add_cotizacion(cliente, trabajo, monto):
    conn = conectar()
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto, estado) VALUES (?,?,?,?,?)",
                 (fecha, cliente, trabajo, monto, 'Pendiente'))
    conn.commit()
    conn.close()

def get_cotizaciones():
    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY id DESC", conn)
    conn.close()
    return df

# --- FUNCIONES CRUD INVENTARIO ---
def update_inventario(item, cantidad, unidad, precio):
    conn = conectar()
    # Si existe lo actualiza, si no lo crea
    c = conn.cursor()
    c.execute("SELECT id FROM inventario WHERE item = ?", (item,))
    if c.fetchone():
        c.execute("UPDATE inventario SET cantidad = ?, precio_usd = ? WHERE item = ?", (cantidad, precio, item))
    else:
        c.execute("INSERT INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?,?,?,?)", (item, cantidad, unidad, precio))
    conn.commit()
    conn.close()

def get_inventario():
    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM inventario", conn)
    conn.close()
    return df

# --- AUTENTICACIÓN ---
def login_user(user, pw):
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT rol FROM usuarios WHERE username = ? AND password = ?", (user, pw))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None
