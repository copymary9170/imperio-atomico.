import sqlite3
import pandas as pd

def conectar():
    return sqlite3.connect('imperio_data.db')

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    # Tabla para las Cotizaciones
    c.execute('''CREATE TABLE IF NOT EXISTS cotizaciones 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  fecha TEXT, cliente TEXT, trabajo TEXT, 
                  monto REAL, estado TEXT)''')
    
    # Tabla para los Niveles de Tinta (Lista para la tarde)
    c.execute('''CREATE TABLE IF NOT EXISTS niveles_tinta 
                 (impresora TEXT, color TEXT, nivel REAL, fecha_test TEXT)''')
    conn.commit()
    conn.close()

def guardar_cotizacion(cliente, trabajo, monto):
    conn = conectar()
    c = conn.cursor()
    fecha = pd.Timestamp.now().strftime('%Y-%m-%d')
    c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto, estado) VALUES (?,?,?,?,?)",
              (fecha, cliente, trabajo, monto, 'Pendiente'))
    conn.commit()
    conn.close()

def obtener_cotizaciones():
    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY id DESC", conn)
    conn.close()
    return df
