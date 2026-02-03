import sqlite3
import pandas as pd

# Esta función crea el archivo de la base de datos y las tablas nuevas
def inicializar_sistema():
    conn = sqlite3.connect('imperio_data.db')
    c = conn.cursor()
    
    # Tabla para las Cotizaciones (Lo que pidió GPT)
    c.execute('''CREATE TABLE IF NOT EXISTS cotizaciones 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  fecha TEXT, cliente TEXT, trabajo TEXT, 
                  monto REAL, estado TEXT)''')
    
    # Tabla para los Niveles de Tinta (Para lo que me mandas luego)
    c.execute('''CREATE TABLE IF NOT EXISTS niveles_inyectores 
                 (impresora TEXT, color TEXT, nivel REAL, fecha_test TEXT)''')
    
    conn.commit()
    conn.close()

# Función para guardar una cotización rápida
def guardar_cotizacion(cliente, trabajo, monto):
    conn = sqlite3.connect('imperio_data.db')
    c = conn.cursor()
    fecha = pd.Timestamp.now().strftime('%Y-%m-%d')
    c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto, estado) VALUES (?,?,?,?,?)",
              (fecha, cliente, trabajo, monto, 'Pendiente'))
    conn.commit()
    conn.close()
