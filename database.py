def migrar_base_datos():
    conn = conectar()
    cursor = conn.cursor()
    try:
        # Intentamos agregar la columna cliente_id a cotizaciones
        cursor.execute("ALTER TABLE cotizaciones ADD COLUMN cliente_id INTEGER")
        # Intentamos agregar la tabla de movimientos si no existe
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventario_movs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    tipo TEXT,
                    cantidad REAL,
                    motivo TEXT,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
    except:
        # Si ya existe, no hará nada y no dará error
        pass
    finally:
        conn.close()

# Llama a la migración después de inicializar
inicializar_sistema()
migrar_base_datos()
