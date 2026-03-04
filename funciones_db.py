import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.getenv('IMPERIO_DB_PATH', 'data/imperio.db')


def now_iso():
    return datetime.utcnow().isoformat(timespec='seconds')


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def registrar_auditoria(conn, usuario, accion, valor_anterior='', valor_nuevo=''):
    conn.execute(
        '''
        INSERT INTO auditoria(fecha, usuario, accion, valor_anterior, valor_nuevo)
        VALUES (?,?,?,?,?)
        ''',
        (now_iso(), usuario, accion, str(valor_anterior), str(valor_nuevo)),
    )


def get_config(parametro, default=''):
    with get_conn() as conn:
        row = conn.execute('SELECT valor FROM configuracion WHERE parametro=?', (parametro,)).fetchone()
        return row['valor'] if row else default


def init_db():
    with get_conn() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS configuracion (
                parametro TEXT PRIMARY KEY,
                valor TEXT
            );

            CREATE TABLE IF NOT EXISTS inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT NOT NULL,
                categoria TEXT,
                variante TEXT,
                unidad TEXT DEFAULT 'unidad',
                cantidad REAL DEFAULT 0,
                minimo REAL DEFAULT 0,
                precio_usd REAL DEFAULT 0,
                perfil_color TEXT DEFAULT 'normal',
                imprimible_cmyk INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                ultima_actualizacion TEXT
            );

            CREATE TABLE IF NOT EXISTS inventario_movs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                item_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                cantidad REAL NOT NULL,
                motivo TEXT,
                referencia TEXT,
                usuario TEXT,
                FOREIGN KEY (item_id) REFERENCES inventario(id)
            );

            CREATE TABLE IF NOT EXISTS kardex (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                item_id INTEGER NOT NULL,
                entrada REAL DEFAULT 0,
                salida REAL DEFAULT 0,
                saldo REAL DEFAULT 0,
                costo_unitario REAL DEFAULT 0,
                referencia TEXT,
                FOREIGN KEY (item_id) REFERENCES inventario(id)
            );

            CREATE TABLE IF NOT EXISTS activos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipo TEXT NOT NULL,
                modelo TEXT,
                tipo TEXT,
                vida_total REAL DEFAULT 0,
                uso_actual REAL DEFAULT 0,
                vida_restante REAL DEFAULT 0,
                desgaste REAL DEFAULT 0,
                vida_cabezal REAL DEFAULT 100,
                seleccionada INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS diagnosticos_impresora (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                activo_id INTEGER NOT NULL,
                hoja_diagnostico TEXT,
                foto_tanques TEXT,
                niveles_json TEXT,
                observacion TEXT,
                FOREIGN KEY (activo_id) REFERENCES activos(id)
            );

            CREATE TABLE IF NOT EXISTS recetas_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proceso TEXT NOT NULL,
                producto TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                consumo_unitario REAL NOT NULL DEFAULT 0,
                unidad TEXT,
                activo_id INTEGER,
                dureza_factor REAL DEFAULT 1,
                area_factor REAL DEFAULT 1,
                activo INTEGER DEFAULT 1,
                FOREIGN KEY (item_id) REFERENCES inventario(id),
                FOREIGN KEY (activo_id) REFERENCES activos(id)
            );

            CREATE TABLE IF NOT EXISTS ordenes_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                proceso TEXT,
                producto TEXT,
                cantidad REAL,
                estado TEXT DEFAULT 'COMPLETADA',
                usuario TEXT,
                activo_id INTEGER,
                FOREIGN KEY (activo_id) REFERENCES activos(id)
            );

            CREATE TABLE IF NOT EXISTS tiempos_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER NOT NULL,
                inicio TEXT,
                fin TEXT,
                minutos_reales REAL,
                operador TEXT,
                FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id)
            );

            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                cliente TEXT,
                detalle TEXT,
                monto_total REAL DEFAULT 0,
                activo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                descripcion TEXT,
                monto REAL DEFAULT 0,
                activo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                usuario TEXT,
                accion TEXT,
                valor_anterior TEXT,
                valor_nuevo TEXT
            );
            '''
        )

        defaults = {
            'stock_no_negativo': '1',
            'factor_borrador': '0.8',
            'factor_normal': '1.0',
            'factor_alta': '1.2',
            'factor_papel_fotografico': '1.2',
            'factor_papel_bond': '1.0',
            'factor_papel_adhesivo': '1.1',
        }
        for k, v in defaults.items():
            conn.execute('INSERT OR IGNORE INTO configuracion(parametro, valor) VALUES (?,?)', (k, v))
