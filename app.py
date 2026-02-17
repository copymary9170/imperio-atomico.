import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import io
import plotly.express as px
from PIL import Image
from datetime import datetime, date, timedelta
import time
import os
import hashlib
import hmac
import secrets

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide", page_icon="⚛️")

# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():

    ruta = "data/imperio.db"

    conn = sqlite3.connect(
        ruta,
        check_same_thread=False
    )

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def hash_password(password: str, salt: str | None = None) -> str:
    """Genera hash PBKDF2 para almacenar contraseñas sin texto plano."""
    salt = salt or secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, digest = password_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        test_digest = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            int(iterations)
        ).hex()
        return hmac.compare_digest(test_digest, digest)
    except (ValueError, TypeError):
        return False


def obtener_password_admin_inicial() -> str:
    """Obtiene contraseña inicial desde entorno para evitar hardcode total en el código."""
    return os.getenv('IMPERIO_ADMIN_PASSWORD', 'atomica2026')

# --- 3. INICIALIZACIÓN DEL SISTEMA ---
# ===========================================================
# 3. INICIALIZACIÓN DEL SISTEMA — IMPERIO ATÓMICO ERP PRO
# ===========================================================

def inicializar_sistema():

    with conectar() as conn:

        c = conn.cursor()

        # ===================================================
        # CONFIGURACIÓN GENERAL
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            parametro TEXT PRIMARY KEY,
            valor REAL
        )
        """)

        # ===================================================
        # PROVEEDORES
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            telefono TEXT,
            rif TEXT,
            contacto TEXT,
            observaciones TEXT,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ===================================================
        # HISTORIAL DE COMPRAS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS historial_compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            proveedor_id INTEGER,
            cantidad REAL,
            unidad TEXT,
            costo_total_usd REAL,
            costo_unit_usd REAL,
            impuestos REAL,
            delivery REAL,
            tasa_usada REAL,
            moneda_pago TEXT,
            usuario TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ===================================================
        # INVENTARIO
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT UNIQUE,
            cantidad REAL,
            unidad TEXT,
            precio_usd REAL,
            minimo REAL DEFAULT 5.0,
            activo INTEGER DEFAULT 1,
            ultima_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # COLUMNAS EXTRA INVENTARIO

        try:
            c.execute("ALTER TABLE inventario ADD COLUMN imprimible_cmyk INTEGER DEFAULT 0")
        except:
            pass

        try:
            c.execute("ALTER TABLE inventario ADD COLUMN area_por_pliego_cm2 REAL")
        except:
            pass

        # ===================================================
        # TASAS DE CAMBIO
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS tasas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tasa_bcv REAL,
            tasa_binance REAL,
            fecha TEXT
        )
        """)

        # ===================================================
        # COSTOS OPERATIVOS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS costos_operativos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            monto_mensual REAL
        )
        """)

        # ===================================================
        # CLIENTES
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            whatsapp TEXT
        )
        """)

        # ===================================================
        # USUARIOS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            password TEXT,
            password_hash TEXT,
            rol TEXT,
            nombre TEXT
        )
        """)

        # ===================================================
        # MOVIMIENTOS INVENTARIO
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS inventario_movs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            tipo TEXT,
            cantidad REAL,
            motivo TEXT,
            usuario TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ===================================================
        # COMPRAS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor TEXT,
            total REAL,
            usuario TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS compras_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER,
            item TEXT,
            cantidad REAL,
            costo REAL
        )
        """)

        # ===================================================
        # VENTAS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            cliente TEXT,
            detalle TEXT,
            monto_total REAL,
            costo_total REAL,
            utilidad REAL,
            margen REAL,
            metodo TEXT,
            usuario TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ventas_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            item TEXT,
            cantidad REAL,
            costo REAL,
            precio REAL
        )
        """)

        # ===================================================
        # GASTOS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT,
            monto REAL,
            categoria TEXT,
            metodo TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ===================================================
        # ACTIVOS
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            costo REAL,
            vida_util_meses INTEGER,
            fecha_compra TEXT
        )
        """)

        # ===================================================
        # COTIZACIONES
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            total REAL,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS cotizacion_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER,
            item TEXT,
            cantidad REAL,
            precio REAL
        )
        """)

        # ===================================================
        # CMYK LOG
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS cmyk_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo TEXT,
            area REAL,
            costo REAL,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ===================================================
        # CIERRE DE CAJA
        # ===================================================

        c.execute("""
        CREATE TABLE IF NOT EXISTS cierre_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            ventas REAL,
            gastos REAL,
            utilidad REAL,
            usuario TEXT
        )
        """)

        # ===================================================
        # CREAR ADMIN
        # ===================================================

        try:

            admin_password = obtener_password_admin_inicial()

            c.execute("""
            INSERT OR IGNORE INTO usuarios
            VALUES (?, ?, ?, ?, ?)
            """, (
                "jefa",
                "",
                hash_password(admin_password),
                "Admin",
                "Dueña del Imperio"
            ))

        except:
            pass

        conn.commit()
# ===========================================================
# 💰 FUNCIÓN FINANCIERA EMPRESARIAL
# ===========================================================
def calcular_costo_operativo_por_dia():

    with conectar() as conn:

        df = pd.read_sql(
            "SELECT monto_mensual FROM costos_operativos",
            conn
        )

    if df.empty:
        return 0

    total_mensual = df["monto_mensual"].sum()

    return total_mensual / 30

# --- 4. CARGA DE DATOS ---
def cargar_datos():

    with conectar() as conn:

        try:

            # INVENTARIO
            existe = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='inventario'
            """).fetchone()

            if existe:
                columnas = {
                    row[1] for row in
                    conn.execute(
                        "PRAGMA table_info(inventario)"
                    ).fetchall()
                }

                query = "SELECT * FROM inventario"

                if 'activo' in columnas:
                    query += " WHERE COALESCE(activo,1)=1"

                st.session_state.df_inv = pd.read_sql(query, conn)

            else:
                st.session_state.df_inv = pd.DataFrame()


            # CLIENTES

            existe_cli = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='clientes'
            """).fetchone()

            if existe_cli:

                st.session_state.df_cli = pd.read_sql(
                    "SELECT * FROM clientes",
                    conn
                )

            else:

                st.session_state.df_cli = pd.DataFrame()


        except Exception as e:

            st.warning(f"Error cargando datos: {e}")

# Alias de compatibilidad para módulos que lo usan
def cargar_datos_seguros():
    cargar_datos()

# --- 5. LOGICA DE ACCESO ---

# 🔥 SIEMPRE inicializar primero
inicializar_sistema()

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

def login():
    st.title("⚛️ Acceso al Imperio Atómico")
    with st.container(border=True):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar", use_container_width=True):
            with conectar() as conn:
                res = conn.execute(
                    "SELECT username, rol, nombre, password, password_hash FROM usuarios WHERE username=?",
                    (u,)
                ).fetchone()

            acceso_ok = False
            if res:
                username, rol, nombre, password_plain, password_hash = res
                if verify_password(p, password_hash):
                    acceso_ok = True
                elif password_plain and hmac.compare_digest(password_plain, p):
                    acceso_ok = True
                    with conectar() as conn:
                        conn.execute(
                            "UPDATE usuarios SET password_hash=?, password='' WHERE username=?",
                            (hash_password(p), username)
                        )
                        conn.commit()

            if acceso_ok:
                st.session_state.autenticado = True
                st.session_state.rol = rol
                st.session_state.usuario_nombre = nombre
                cargar_datos()
                st.rerun()
            else:
                st.error("Acceso denegado")

if not st.session_state.autenticado:
    login()
    st.stop()

# --- 6. SIDEBAR Y VARIABLES ---
cargar_datos()
t_bcv = st.session_state.get('tasa_bcv', 1.0)
t_bin = st.session_state.get('tasa_binance', 1.0)
ROL = st.session_state.get('rol', "Produccion")

with st.sidebar:
    st.header(f"👋 {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 Bin: {t_bin}")

    menu = st.radio(
        "Secciones:",
        [
            "📊 Dashboard",
            "🛒 Venta Directa",
            "📦 Inventario",
            "👥 Clientes",
            "🎨 Análisis CMYK",
            "🏗️ Activos",
            "🛠️ Otros Procesos",
            "💰 Ventas",
            "📉 Gastos",
            "🏁 Cierre de Caja",
            "📊 Auditoría y Métricas",
            "📝 Cotizaciones",
            "⚙️ Configuración"
        ]
    )

    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

        
# ===========================================================
# 📊 DASHBOARD GENERAL
# ===========================================================
if menu == "📊 Dashboard":

    st.title("📊 Dashboard Ejecutivo")
    st.caption("Resumen general financiero y operativo")

    # =============================
    # CARGA DE DATOS
    # =============================

    with conectar() as conn:

        df_ventas = pd.read_sql(
            "SELECT fecha, monto_total, utilidad FROM ventas",
            conn
        )

        df_gastos = pd.read_sql(
            "SELECT fecha, monto FROM gastos",
            conn
        )

        df_inv_dash = pd.read_sql(
            "SELECT cantidad, precio_usd, minimo FROM inventario",
            conn
        )

        total_clientes = conn.execute(
            "SELECT COUNT(*) FROM clientes"
        ).fetchone()[0]

        utilidad = conn.execute(
            "SELECT COALESCE(SUM(utilidad),0) FROM ventas"
        ).fetchone()[0]


    # =============================
    # CALCULOS
    # =============================

    ventas_total = df_ventas["monto_total"].sum() if not df_ventas.empty else 0
    gastos_total = df_gastos["monto"].sum() if not df_gastos.empty else 0

    capital_inv = 0
    stock_bajo = 0

    if not df_inv_dash.empty:

        capital_inv = (
            df_inv_dash["cantidad"]
            * df_inv_dash["precio_usd"]
        ).sum()

        stock_bajo = (
            df_inv_dash["cantidad"]
            <= df_inv_dash["minimo"]
        ).sum()


    # =============================
    # METRICAS PRINCIPALES
    # =============================

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("💰 Ventas", f"${ventas_total:,.2f}")

    c2.metric("📉 Gastos", f"${gastos_total:,.2f}")

    c3.metric("💎 Utilidad Real", f"${utilidad:,.2f}")

    c4.metric("👥 Clientes", total_clientes)

    c5.metric("🚨 Stock Bajo", stock_bajo)


    st.divider()


    # =============================
    # CAPITAL INVENTARIO
    # =============================

    st.metric(
        "📦 Capital en Inventario",
        f"${capital_inv:,.2f}"
    )


    # =============================
    # GRAFICO VENTAS
    # =============================

    if not df_ventas.empty:

        df_ventas["fecha"] = pd.to_datetime(df_ventas["fecha"])

        resumen = df_ventas.groupby(
            df_ventas["fecha"].dt.date
        )["monto_total"].sum()

        st.line_chart(resumen)


    # =============================
    # GRAFICO GASTOS
    # =============================

    if not df_gastos.empty:

        df_gastos["fecha"] = pd.to_datetime(df_gastos["fecha"])

        resumen = df_gastos.groupby(
            df_gastos["fecha"].dt.date
        )["monto"].sum()

        st.bar_chart(resumen)

# ===========================================================
# 📦 MÓDULO DE INVENTARIO – ESTRUCTURA CORREGIDA
# ===========================================================
elif menu == "📦 Inventario":

    st.title("📦 Centro de Control de Suministros")

    # --- SINCRONIZACIÓN CON SESIÓN ---
    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    t_ref = st.session_state.get('tasa_bcv', 36.5)
    t_bin = st.session_state.get('tasa_binance', 38.0)
    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    # =======================================================
    # 1️⃣ DASHBOARD EJECUTIVO
    # =======================================================
    if not df_inv.empty:

        with st.container(border=True):

            c1, c2, c3, c4 = st.columns(4)

            capital_total = (df_inv["cantidad"] * df_inv["precio_usd"]).sum()
            items_criticos = df_inv[df_inv["cantidad"] <= df_inv["minimo"]]
            total_items = len(df_inv)

            salud = ((total_items - len(items_criticos)) / total_items) * 100 if total_items > 0 else 0

            c1.metric("💰 Capital en Inventario", f"${capital_total:,.2f}")
            c2.metric("📦 Total Ítems", total_items)
            c3.metric("🚨 Stock Bajo", len(items_criticos), delta="Revisar" if len(items_criticos) > 0 else "OK", delta_color="inverse")
            c4.metric("🧠 Salud del Almacén", f"{salud:.0f}%")

    # =======================================================
    # 2️⃣ TABS
    # =======================================================
    tabs = st.tabs([
        "📋 Existencias",
        "📥 Registrar Compra",
        "📊 Historial Compras",
        "👤 Proveedores",
        "🔧 Ajustes"
    ])

    # =======================================================
    # 📋 TAB 1 — EXISTENCIAS
    # =======================================================
    with tabs[0]:

        if df_inv.empty:
            st.info("Inventario vacío.")
        else:
            col1, col2, col3 = st.columns([2, 1, 1])
            filtro = col1.text_input("🔍 Buscar insumo")
            moneda_vista = col2.selectbox("Moneda", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], key="inv_moneda_vista")
            solo_bajo = col3.checkbox("🚨 Solo stock bajo")

            tasa_vista = 1.0
            simbolo = "$"

            if "BCV" in moneda_vista:
                tasa_vista = t_ref
                simbolo = "Bs"
            elif "Binance" in moneda_vista:
                tasa_vista = t_bin
                simbolo = "Bs"

            df_v = df_inv.copy()

            if filtro:
                df_v = df_v[df_v["item"].str.contains(filtro, case=False)]

            if solo_bajo:
                df_v = df_v[df_v["cantidad"] <= df_v["minimo"]]

            df_v["Costo Unitario"] = df_v["precio_usd"] * tasa_vista
            df_v["Valor Total"] = df_v["cantidad"] * df_v["Costo Unitario"]


            def resaltar_critico(row):
                if row["cantidad"] <= row["minimo"]:
                    return ['background-color: rgba(255,0,0,0.15)'] * len(row)
                return [''] * len(row)
          
            st.dataframe(
               df_v.style.apply(resaltar_critico, axis=1),
                column_config={
                    "item": "Insumo",
                    "cantidad": "Stock",
                    "unidad": "Unidad",
                    "Costo Unitario": st.column_config.NumberColumn(
                        f"Costo ({simbolo})", format="%.4f"
                    ),
                    "Valor Total": st.column_config.NumberColumn(
                        f"Valor Total ({simbolo})", format="%.2f"
                    ),
                    "minimo": "Mínimo",
                    "imprimible_cmyk": st.column_config.CheckboxColumn("CMYK", help="Disponible para impresión en Análisis CMYK"),
                    "area_por_pliego_cm2": st.column_config.NumberColumn("cm²/pliego", format="%.2f"),
                    "precio_usd": None,
                    "id": None,
                    "activo": None,
                    "ultima_actualizacion": None
                },
                use_container_width=True,
                hide_index=True
            )

        st.divider()
        st.subheader("🛠 Gestión de Insumo Existente")

        if not df_inv.empty:

            insumo_sel = st.selectbox("Seleccionar Insumo", df_inv["item"].tolist())
            fila_sel = df_inv[df_inv["item"] == insumo_sel].iloc[0]
            colA, colB, colC = st.columns(3)
            nuevo_min = colA.number_input("Nuevo Stock Mínimo", min_value=0.0, value=float(fila_sel.get('minimo', 0)))
            flag_cmyk = colB.checkbox("Visible en CMYK", value=bool(fila_sel.get('imprimible_cmyk', 0)))

            if colA.button("Actualizar Mínimo"):
                with conectar() as conn:
                    conn.execute(
                        "UPDATE inventario SET minimo=?, imprimible_cmyk=? WHERE item=?",
                        (nuevo_min, 1 if flag_cmyk else 0, insumo_sel)
                    )
                    conn.commit()
                cargar_datos()
                st.success("Stock mínimo actualizado.")
                st.rerun()

            # Conversión para inventarios viejos cargados como cm2
            if str(fila_sel.get('unidad', '')).lower() == 'cm2':
                st.warning("Este insumo aún está en cm². Conviene convertirlo a pliegos para control real de stock.")
                ref_default = float(fila_sel.get('area_por_pliego_cm2') or fila_sel.get('cantidad', 1) or 1)
                cm2_por_hoja = colC.number_input("cm² por pliego", min_value=1.0, value=ref_default)
                if colC.button("🔄 Convertir stock cm2 → pliegos"):
                    pliegos = float(fila_sel.get('cantidad', 0)) / float(cm2_por_hoja)
                    with conectar() as conn:
                        conn.execute(
                            "UPDATE inventario SET cantidad=?, unidad='pliegos', area_por_pliego_cm2=?, activo=1 WHERE item=?",
                            (pliegos, cm2_por_hoja, insumo_sel)
                        )
                        conn.commit()
                    st.success(f"Convertido a {pliegos:.3f} pliegos.")
                    cargar_datos()
                    st.rerun()
            if colB.button("🗑 Eliminar Insumo"):
                with conectar() as conn:
                    existe_historial = conn.execute(
                        "SELECT COUNT(*) FROM historial_compras WHERE item=?",
                        (insumo_sel,)
                    ).fetchone()[0]
                    if existe_historial > 0:
                        conn.execute(
                            "UPDATE inventario SET activo=0, cantidad=0 WHERE item=?",
                            (insumo_sel,)
                        )
                        conn.commit()
                        st.success("Insumo archivado (tiene historial y no se elimina físicamente).")
                        cargar_datos()
                        st.rerun()
                    else:
                        st.session_state.confirmar_borrado = True

            if st.session_state.get("confirmar_borrado", False):
                st.warning(f"⚠ Confirmar eliminación de '{insumo_sel}'")
                colC, colD = st.columns(2)

                if colC.button("✅ Confirmar"):
                    with conectar() as conn:
                        conn.execute(
                            "DELETE FROM inventario WHERE item=?",
                            (insumo_sel,)
                        )
                        conn.commit()
                    st.session_state.confirmar_borrado = False
                    cargar_datos()
                    st.success("Insumo eliminado.")
                    st.rerun()

                if colD.button("❌ Cancelar"):
                    st.session_state.confirmar_borrado = False

    # =======================================================
    # 📥 TAB 2 — REGISTRAR COMPRA
    # =======================================================
    with tabs[1]:

        st.subheader("📥 Registrar Nueva Compra")

        with conectar() as conn:
            try:
                proveedores_existentes = pd.read_sql(
                    "SELECT nombre FROM proveedores ORDER BY nombre ASC",
                    conn
                )["nombre"].dropna().astype(str).tolist()
            except (sqlite3.DatabaseError, pd.errors.DatabaseError):
                proveedores_existentes = []

        col_base1, col_base2 = st.columns(2)
        nombre_c = col_base1.text_input("Nombre del Insumo")
        proveedor_sel = col_base2.selectbox(
            "Proveedor",
            ["(Sin proveedor)", "➕ Nuevo proveedor"] + proveedores_existentes,
            key="inv_proveedor_compra"
        )

        proveedor = ""
        if proveedor_sel == "➕ Nuevo proveedor":
            proveedor = st.text_input("Nombre del nuevo proveedor", key="inv_proveedor_nuevo")
        elif proveedor_sel != "(Sin proveedor)":
            proveedor = proveedor_sel

        minimo_stock = st.number_input("Stock mínimo", min_value=0.0)
        imprimible_cmyk = st.checkbox(
            "✅ Se puede imprimir (mostrar en módulo CMYK)",
            value=False,
            help="Marca solo los insumos que sí participan en impresión (tintas, acetato imprimible, papeles de impresión)."
        )

        # ------------------------------
        # TIPO DE UNIDAD
        # ------------------------------
        tipo_unidad = st.selectbox(
            "Tipo de Unidad",
            ["Unidad", "Área (cm²)", "Líquido (ml)", "Peso (gr)"]
        )

        stock_real = 0
        unidad_final = "Unidad"
        area_por_pliego_val = None

        if tipo_unidad == "Área (cm²)":
            c1, c2, c3 = st.columns(3)
            ancho = c1.number_input("Ancho (cm)", min_value=0.1)
            alto = c2.number_input("Alto (cm)", min_value=0.1)
            cantidad_envases = c3.number_input("Cantidad de Pliegos", min_value=0.001)

            # Inventario se controla por unidades físicas (hojas/pliegos),
            # no por área total acumulada. El área queda como referencia técnica.
            area_por_pliego = ancho * alto
            area_total_ref = area_por_pliego * cantidad_envases
            stock_real = cantidad_envases
            unidad_final = "pliegos"
            area_por_pliego_val = area_por_pliego

            st.caption(
                f"Referencia técnica: {area_por_pliego:,.2f} cm² por pliego | "
                f"Área total cargada: {area_total_ref:,.2f} cm²"
            )

        elif tipo_unidad == "Líquido (ml)":
            c1, c2 = st.columns(2)
            ml_por_envase = c1.number_input("ml por Envase", min_value=1.0)
            cantidad_envases = c2.number_input("Cantidad de Envases", min_value=0.001)
            stock_real = ml_por_envase * cantidad_envases
            unidad_final = "ml"

        elif tipo_unidad == "Peso (gr)":
            c1, c2 = st.columns(2)
            gr_por_envase = c1.number_input("gramos por Envase", min_value=1.0)
            cantidad_envases = c2.number_input("Cantidad de Envases", min_value=0.001)
            stock_real = gr_por_envase * cantidad_envases
            unidad_final = "gr"

        else:
            cantidad_envases = st.number_input("Cantidad Comprada", min_value=0.001)
            stock_real = cantidad_envases
            unidad_final = "Unidad"

        # ------------------------------
        # DATOS FINANCIEROS
        # ------------------------------
        col4, col5 = st.columns(2)
        monto_factura = col4.number_input("Monto Factura", min_value=0.0)
        moneda_pago = col5.selectbox(
            "Moneda",
            ["USD $", "Bs (BCV)", "Bs (Binance)"],
            key="inv_moneda_pago"
        )

        col6, col7, col8 = st.columns(3)
        iva_activo = col6.checkbox(f"IVA (+{st.session_state.get('iva_perc',16)}%)")
        igtf_activo = col7.checkbox(f"IGTF (+{st.session_state.get('igtf_perc',3)}%)")
        banco_activo = col8.checkbox(f"Banco (+{st.session_state.get('banco_perc',0.5)}%)")

        st.caption(f"Sugerencia de impuesto total para compras: {st.session_state.get('inv_impuesto_default', 16.0):.2f}%")

        delivery = st.number_input("Gastos Logística / Delivery ($)", value=float(st.session_state.get("inv_delivery_default", 0.0)))

        # ------------------------------
        # BOTÓN GUARDAR
        # ------------------------------
        if st.button("💾 Guardar Compra", use_container_width=True):

            if not nombre_c:
                st.error("Debe indicar nombre del insumo.")
                st.stop()

            if stock_real <= 0:
                st.error("Cantidad inválida.")
                st.stop()

            if "BCV" in moneda_pago:
                tasa_usada = t_ref
            elif "Binance" in moneda_pago:
                tasa_usada = t_bin

            else:
                tasa_usada = 1.0

            porc_impuestos = 0
            if iva_activo:
                porc_impuestos += st.session_state.get("iva_perc", 16)
            if igtf_activo:
                porc_impuestos += st.session_state.get("igtf_perc", 3)
            if banco_activo:
                porc_impuestos += st.session_state.get("banco_perc", 0.5)

            costo_total_usd = ((monto_factura / tasa_usada) * (1 + (porc_impuestos / 100))) + delivery
            costo_unitario = costo_total_usd / stock_real

            with conectar() as conn:
                cur = conn.cursor()


                proveedor_id = None
                if proveedor:
                    cur.execute("SELECT id FROM proveedores WHERE nombre=?", (proveedor,))
                    prov = cur.fetchone()
                    if not prov:
                        cur.execute("INSERT INTO proveedores (nombre) VALUES (?)", (proveedor,))
                        proveedor_id = cur.lastrowid
                    else:
                        proveedor_id = prov[0]

                old = cur.execute(
                    "SELECT cantidad, precio_usd FROM inventario WHERE item=?",
                    (nombre_c,)
                ).fetchone()

                if old:
                    nueva_cant = old[0] + stock_real
                    precio_ponderado = (
                        (old[0] * old[1] + stock_real * costo_unitario)
                        / nueva_cant
                    )
                else:
                    nueva_cant = stock_real
                    precio_ponderado = costo_unitario

                if old:
                    cur.execute(
                        """
                        UPDATE inventario
                        SET cantidad=?, unidad=?, precio_usd=?, minimo=?, imprimible_cmyk=?, area_por_pliego_cm2=?, activo=1, ultima_actualizacion=CURRENT_TIMESTAMP
                        WHERE item=?
                        """,
                        (nueva_cant, unidad_final, precio_ponderado, minimo_stock, 1 if imprimible_cmyk else 0, area_por_pliego_val, nombre_c)
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO inventario
                        (item, cantidad, unidad, precio_usd, minimo, imprimible_cmyk, area_por_pliego_cm2, activo, ultima_actualizacion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (nombre_c, nueva_cant, unidad_final, precio_ponderado, minimo_stock, 1 if imprimible_cmyk else 0, area_por_pliego_val, 1)
                    )

                cur.execute("""
                    INSERT INTO historial_compras
                    (item, proveedor_id, cantidad, unidad, costo_total_usd, costo_unit_usd, impuestos, delivery, tasa_usada, moneda_pago, usuario)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    nombre_c,
                    proveedor_id,
                    stock_real,
                    unidad_final,
                    costo_total_usd,
                    costo_unitario,
                    porc_impuestos,
                    delivery,
                    tasa_usada,
                    moneda_pago,
                    usuario_actual
                ))

                item_id_row = cur.execute(
                    "SELECT id FROM inventario WHERE item = ?",
                    (nombre_c,)
                ).fetchone()

                if item_id_row:
                    cur.execute("""
                        INSERT INTO inventario_movs
                        (item_id, tipo, cantidad, motivo, usuario)
                        VALUES (?,?,?,?,?)
                    """, (
                        item_id_row[0],
                        "ENTRADA",
                        stock_real,
                        "Compra registrada",
                        usuario_actual
                    ))

                conn.commit()

            cargar_datos()
            st.success("Compra registrada correctamente.")
            st.rerun()


    # =======================================================
    # 📊 TAB 3 — HISTORIAL DE COMPRAS
    # =======================================================
    with tabs[2]:

        st.subheader("📊 Historial Profesional de Compras")

        with conectar() as conn:
            df_hist = pd.read_sql("""
                SELECT 
                    h.id as compra_id,
                    h.fecha,
                    h.item,
                    h.cantidad,
                    h.unidad,
                    h.costo_total_usd,
                    h.costo_unit_usd,
                    h.impuestos,
                    h.delivery,
                    h.moneda_pago,
                    p.nombre as proveedor
                FROM historial_compras h
                LEFT JOIN proveedores p ON h.proveedor_id = p.id
                ORDER BY h.fecha DESC
            """, conn)

        if df_hist.empty:
            st.info("No hay compras registradas.")
        else:

            col1, col2 = st.columns(2)

            filtro_item = col1.text_input("🔍 Filtrar por Insumo")
            filtro_proveedor = col2.text_input("👤 Filtrar por Proveedor")

            df_v = df_hist.copy()

            if filtro_item:
                df_v = df_v[df_v["item"].str.contains(filtro_item, case=False)]

            if filtro_proveedor:
                df_v = df_v[df_v["proveedor"].fillna("").str.contains(filtro_proveedor, case=False)]

            total_compras = df_v["costo_total_usd"].sum()

            st.metric("💰 Total Comprado (USD)", f"${total_compras:,.2f}")

            st.dataframe(
                df_v,
                column_config={
                    "compra_id": None,
                    "fecha": "Fecha",
                    "item": "Insumo",
                    "cantidad": "Cantidad",
                    "unidad": "Unidad",
                    "costo_total_usd": st.column_config.NumberColumn("Costo Total ($)", format="%.2f"),
                    "costo_unit_usd": st.column_config.NumberColumn("Costo Unit ($)", format="%.4f"),
                    "impuestos": "Impuestos %",
                    "delivery": "Delivery $",
                    "moneda_pago": "Moneda",
                    "proveedor": "Proveedor"
                },
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("🧹 Corregir historial de compras")
            opciones_compra = {
                f"#{int(r.compra_id)} | {r.fecha} | {r.item} | {r.cantidad} {r.unidad} | ${r.costo_total_usd:.2f}": int(r.compra_id)
                for r in df_hist.itertuples(index=False)
            }
            compra_sel_label = st.selectbox("Selecciona la compra a corregir", list(opciones_compra.keys()))
            compra_sel_id = opciones_compra[compra_sel_label]
            compra_row = df_hist[df_hist["compra_id"] == compra_sel_id].iloc[0]
            st.caption("Si eliminas la compra, el sistema descuenta esa cantidad del inventario del insumo asociado.")

            if st.button("🗑 Eliminar compra seleccionada", type="secondary"):
                with conectar() as conn:
                    cur = conn.cursor()
                    actual_row = cur.execute(
                        "SELECT id, cantidad FROM inventario WHERE item=?",
                        (str(compra_row["item"]),)
                    ).fetchone()

                    if actual_row:
                        item_id, cantidad_actual = actual_row
                        nueva_cant = max(0.0, float(cantidad_actual or 0) - float(compra_row["cantidad"]))
                        cur.execute(
                            "UPDATE inventario SET cantidad=?, ultima_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
                            (nueva_cant, int(item_id))
                        )
                        cur.execute(
                            """
                            INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario)
                            VALUES (?, 'SALIDA', ?, 'Corrección: eliminación de compra', ?)
                            """,
                            (int(item_id), float(compra_row["cantidad"]), usuario_actual)
                        )

                    cur.execute("DELETE FROM historial_compras WHERE id=?", (int(compra_sel_id),))
                    conn.commit()

                st.success("Compra eliminada y stock ajustado correctamente.")
                cargar_datos()
                st.rerun()

            st.divider()
            st.subheader("🧽 Limpiar historial por insumo")
            df_hist_aux = df_hist.copy()
            df_hist_aux["item_norm"] = df_hist_aux["item"].fillna("").str.strip().str.lower()
            items_disponibles = sorted([i for i in df_hist_aux["item_norm"].unique().tolist() if i])

            if items_disponibles:
                item_norm_sel = st.selectbox("Insumo a limpiar del historial", items_disponibles, key="hist_item_norm")
                filas_item = df_hist_aux[df_hist_aux["item_norm"] == item_norm_sel]
                st.caption(f"Se eliminarán {len(filas_item)} compras del historial para ese insumo.")

                confirmar_limpieza = st.checkbox("Confirmo que deseo borrar ese historial por error de carga", key="hist_confirma_limpieza")
                if st.button("🗑 Borrar historial del insumo seleccionado", type="secondary", disabled=not confirmar_limpieza):
                    with conectar() as conn:
                        cur = conn.cursor()

                        for _, row in filas_item.iterrows():
                            actual_row = cur.execute(
                                "SELECT id, cantidad FROM inventario WHERE lower(trim(item))=?",
                                (str(row["item_norm"]),)
                            ).fetchone()

                            if actual_row:
                                item_id, cantidad_actual = actual_row
                                nueva_cant = max(0.0, float(cantidad_actual or 0) - float(row["cantidad"]))
                                cur.execute(
                                    "UPDATE inventario SET cantidad=?, ultima_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
                                    (nueva_cant, int(item_id))
                                )
                                cur.execute(
                                    """
                                    INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario)
                                    VALUES (?, 'SALIDA', ?, 'Corrección masiva: limpieza historial por insumo', ?)
                                    """,
                                    (int(item_id), float(row["cantidad"]), usuario_actual)
                                )

                        ids_borrar = [int(x) for x in filas_item["compra_id"].tolist()]
                        cur.executemany("DELETE FROM historial_compras WHERE id=?", [(i,) for i in ids_borrar])
                        conn.commit()

                    st.success(f"Se borró el historial de '{item_norm_sel}' y se ajustó el stock donde correspondía.")
                    cargar_datos()
                    st.rerun()

    # =======================================================
    # 👤 TAB 4 — PROVEEDORES
    # =======================================================
    with tabs[3]:

        st.subheader("👤 Directorio de Proveedores")

        with conectar() as conn:
            try:
                columnas_proveedores = {
                    row[1] for row in conn.execute("PRAGMA table_info(proveedores)").fetchall()
                }
                if not columnas_proveedores:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS proveedores (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nombre TEXT UNIQUE,
                            telefono TEXT,
                            rif TEXT,
                            contacto TEXT,
                            observaciones TEXT,
                            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    conn.commit()
                    columnas_proveedores = {
                        row[1] for row in conn.execute("PRAGMA table_info(proveedores)").fetchall()
                    }

                def sel_col(nombre_columna):
                    return nombre_columna if nombre_columna in columnas_proveedores else f"NULL AS {nombre_columna}"

                query_proveedores = f"""
                    SELECT
                        {sel_col('id')},
                        {sel_col('nombre')},
                        {sel_col('telefono')},
                        {sel_col('rif')},
                        {sel_col('contacto')},
                        {sel_col('observaciones')},
                        {sel_col('fecha_creacion')}
                    FROM proveedores
                    ORDER BY nombre ASC
                """
                df_prov = pd.read_sql(query_proveedores, conn)
            except (sqlite3.DatabaseError, pd.errors.DatabaseError) as e:
                st.error(f"No se pudo cargar la tabla de proveedores: {e}")
                df_prov = pd.DataFrame(columns=[
                    'id', 'nombre', 'telefono', 'rif', 'contacto', 'observaciones', 'fecha_creacion'
                ])

        if df_prov.empty:
            st.info("No hay proveedores registrados todavía.")
        else:
            filtro_proveedor = st.text_input("🔍 Buscar proveedor")
            df_prov_view = df_prov.copy()

            if filtro_proveedor:
                mask_nombre = df_prov_view["nombre"].fillna("").str.contains(filtro_proveedor, case=False)
                mask_contacto = df_prov_view["contacto"].fillna("").str.contains(filtro_proveedor, case=False)
                mask_rif = df_prov_view["rif"].fillna("").str.contains(filtro_proveedor, case=False)
                df_prov_view = df_prov_view[mask_nombre | mask_contacto | mask_rif]

            st.dataframe(
                df_prov_view,
                column_config={
                    "id": None,
                    "nombre": "Proveedor",
                    "telefono": "Teléfono",
                    "rif": "RIF",
                    "contacto": "Contacto",
                    "observaciones": "Observaciones",
                    "fecha_creacion": "Creado"
                },
                use_container_width=True,
                hide_index=True
            )

        st.divider()
        st.subheader("➕ Registrar / Editar proveedor")

        nombre_edit = st.selectbox(
            "Proveedor a editar",
            ["Nuevo proveedor"] + (df_prov["nombre"].tolist() if not df_prov.empty else []),
            key="inv_proveedor_selector"
        )

        prov_actual = None
        if nombre_edit != "Nuevo proveedor" and not df_prov.empty:
            prov_actual = df_prov[df_prov["nombre"] == nombre_edit].iloc[0]

        with st.form("form_proveedor"):
            c1, c2 = st.columns(2)
            nombre_prov = c1.text_input("Nombre", value="" if prov_actual is None else str(prov_actual["nombre"] or ""))
            telefono_prov = c2.text_input("Teléfono", value="" if prov_actual is None else str(prov_actual["telefono"] or ""))
            c3, c4 = st.columns(2)
            rif_prov = c3.text_input("RIF", value="" if prov_actual is None else str(prov_actual["rif"] or ""))
            contacto_prov = c4.text_input("Persona de contacto", value="" if prov_actual is None else str(prov_actual["contacto"] or ""))
            observaciones_prov = st.text_area("Observaciones", value="" if prov_actual is None else str(prov_actual["observaciones"] or ""))

            guardar_proveedor = st.form_submit_button("💾 Guardar proveedor", use_container_width=True)

        if guardar_proveedor:
            if not nombre_prov.strip():
                st.error("El nombre del proveedor es obligatorio.")
            else:
                try:
                    with conectar() as conn:
                        if prov_actual is None:
                            conn.execute(
                                """
                                INSERT INTO proveedores (nombre, telefono, rif, contacto, observaciones)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (nombre_prov.strip(), telefono_prov.strip(), rif_prov.strip(), contacto_prov.strip(), observaciones_prov.strip())
                            )
                        else:
                            conn.execute(
                                """
                                UPDATE proveedores
                                SET nombre=?, telefono=?, rif=?, contacto=?, observaciones=?
                                WHERE id=?
                                """,
                                (
                                    nombre_prov.strip(),
                                    telefono_prov.strip(),
                                    rif_prov.strip(),
                                    contacto_prov.strip(),
                                    observaciones_prov.strip(),
                                    int(prov_actual["id"])
                                )
                            )
                        conn.commit()
                    st.success("Proveedor guardado correctamente.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ya existe un proveedor con ese nombre.")

        if prov_actual is not None:
            if st.button("🗑 Eliminar proveedor seleccionado", type="secondary"):
                with conectar() as conn:
                    compras = conn.execute(
                        "SELECT COUNT(*) FROM historial_compras WHERE proveedor_id=?",
                        (int(prov_actual["id"]),)
                    ).fetchone()[0]

                    if compras > 0:
                        st.error("No se puede eliminar: el proveedor tiene compras asociadas.")
                    else:
                        conn.execute("DELETE FROM proveedores WHERE id=?", (int(prov_actual["id"]),))
                        conn.commit()
                        st.success("Proveedor eliminado.")
                        st.rerun()

    # =======================================================
    # 🔧 TAB 5 — AJUSTES
    # =======================================================
    with tabs[4]:

        st.subheader("🔧 Ajustes del módulo de inventario")
        st.caption("Estos parámetros precargan valores al registrar compras y ayudan al control de inventario.")

        with conectar() as conn:
            cfg_inv = pd.read_sql(
                """
                SELECT parametro, valor
                FROM configuracion
                WHERE parametro IN ('inv_alerta_dias', 'inv_impuesto_default', 'inv_delivery_default')
                """,
                conn
            )

        cfg_map = {row["parametro"]: float(row["valor"]) for _, row in cfg_inv.iterrows()}

        with st.form("form_ajustes_inventario"):
            alerta_dias = st.number_input(
                "Días para alerta de reposición",
                min_value=1,
                max_value=120,
                value=int(cfg_map.get("inv_alerta_dias", 14)),
                help="Referencia para revisar proveedores y planificar compras preventivas."
            )
            impuesto_default = st.number_input(
                "Impuesto por defecto en compras (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(cfg_map.get("inv_impuesto_default", 16.0)),
                format="%.2f"
            )
            delivery_default = st.number_input(
                "Delivery por defecto por compra ($)",
                min_value=0.0,
                value=float(cfg_map.get("inv_delivery_default", 0.0)),
                format="%.2f"
            )

            guardar_ajustes = st.form_submit_button("💾 Guardar ajustes", use_container_width=True)

        if guardar_ajustes:
            with conectar() as conn:
                ajustes = [
                    ("inv_alerta_dias", float(alerta_dias)),
                    ("inv_impuesto_default", float(impuesto_default)),
                    ("inv_delivery_default", float(delivery_default))
                ]
                for parametro, valor in ajustes:
                    conn.execute(
                        "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES (?, ?)",
                        (parametro, valor)
                    )
                conn.commit()

            st.session_state["inv_alerta_dias"] = float(alerta_dias)
            st.session_state["inv_impuesto_default"] = float(impuesto_default)
            st.session_state["inv_delivery_default"] = float(delivery_default)
            st.success("Ajustes de inventario actualizados.")

        c1, c2, c3 = st.columns(3)
        c1.metric("⏱️ Alerta reposición", f"{int(cfg_map.get('inv_alerta_dias', 14))} días")
        c2.metric("🛡️ Impuesto sugerido", f"{cfg_map.get('inv_impuesto_default', 16.0):.2f}%")
        c3.metric("🚚 Delivery sugerido", f"${cfg_map.get('inv_delivery_default', 0.0):.2f}")

 # ===========================================================
# ⚙️ CONFIGURACIÓN GENERAL DEL SISTEMA
# ===========================================================
elif menu == "⚙️ Configuración":

    st.title("⚙️ Configuración del Sistema")

    st.subheader("🏢 Costos Operativos")

    with conectar() as conn:
        df_costos = pd.read_sql("SELECT * FROM costos_operativos", conn)

    st.dataframe(df_costos)

    with st.form("form_costos_operativos_config"):
        nombre = st.text_input("Nombre")
        monto = st.number_input("Monto")

        if st.form_submit_button("Guardar"):
            with conectar() as conn:
                conn.execute(
                    "INSERT INTO costos_operativos (nombre, monto_mensual) VALUES (?,?)",
                    (nombre, monto)
                )
                conn.commit()

            st.rerun()
            
    st.caption("Parámetros generales, tasas y costos operativos")

    # ===========================================================
    # 💱 TASAS DE CAMBIO
    # ===========================================================

    st.subheader("💱 Tasas de Cambio")

    with conectar() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tasa_bcv REAL,
                tasa_binance REAL,
                fecha TEXT
            )
        """)

        conn.commit()

        df_tasas = pd.read_sql(
            "SELECT * FROM tasas ORDER BY id DESC LIMIT 1",
            conn
        )

    tasa_bcv_actual = float(df_tasas["tasa_bcv"].iloc[0]) if not df_tasas.empty else 0.0
    tasa_binance_actual = float(df_tasas["tasa_binance"].iloc[0]) if not df_tasas.empty else 0.0


    with st.form(key="form_tasas"):

        col1, col2 = st.columns(2)

        tasa_bcv = col1.number_input(
            "Tasa BCV",
            value=tasa_bcv_actual,
            format="%.4f"
        )

        tasa_binance = col2.number_input(
            "Tasa Binance",
            value=tasa_binance_actual,
            format="%.4f"
        )

        guardar_tasa = st.form_submit_button(
            "💾 Guardar tasas",
            use_container_width=True
        )

    if guardar_tasa:

        with conectar() as conn:

            conn.execute(
                """
                INSERT INTO tasas
                (tasa_bcv, tasa_binance, fecha)
                VALUES (?, ?, datetime('now'))
                """,
                (tasa_bcv, tasa_binance)
            )

            conn.commit()

        st.success("Tasas actualizadas correctamente")
        st.rerun()


    st.divider()


   
  

    # ===========================================================
    # 📊 RESUMEN COSTOS
    # ===========================================================

    if not df_costos.empty:

        total = df_costos["monto_mensual"].sum()

        costo_diario = total / 30

        col1, col2 = st.columns(2)

        col1.metric(
            "Total mensual",
            f"${total:,.2f}"
        )

        col2.metric(
            "Costo operativo diario",
            f"${costo_diario:,.2f}"
        )

    else:

        st.info("No hay costos operativos registrados")


    st.divider()


    # ===========================================================
    # 🧹 OPCIONES DEL SISTEMA
    # ===========================================================

    st.subheader("🧹 Sistema")

    if st.button(
        "🔄 Reinicializar Sistema (NO borra datos)",
        use_container_width=True
    ):

        inicializar_sistema()

        st.success("Sistema verificado correctamente")
        st.rerun()
# ===========================================================
# 10. ANALIZADOR CMYK PROFESIONAL (VERSIÓN MEJORADA 2.0)
# ===========================================================
if menu == "🎨 Análisis CMYK":

    st.title("🎨 Analizador Profesional de Cobertura CMYK")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:

            # Usamos el inventario como fuente de tintas
            df_tintas_db = pd.read_sql_query(
                "SELECT * FROM inventario", conn
            )
            if 'imprimible_cmyk' in df_tintas_db.columns:
                df_impresion_db = df_tintas_db[df_tintas_db['imprimible_cmyk'].fillna(0) == 1].copy()
            else:
                df_impresion_db = df_tintas_db.copy()
            try:
                df_activos_cmyk = pd.read_sql_query(
                    "SELECT equipo, categoria, unidad FROM activos", conn
                )
            except Exception:
                df_activos_cmyk = pd.DataFrame(columns=['equipo', 'categoria', 'unidad'])

            # Tabla histórica
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial_cmyk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    impresora TEXT,
                    paginas INTEGER,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            df_hist_cmyk = pd.read_sql(
                "SELECT fecha, impresora, paginas, costo FROM historial_cmyk ORDER BY fecha DESC LIMIT 100",
                conn
            )

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # --- LISTA DE IMPRESORAS DISPONIBLES ---
    impresoras_disponibles = []

    # 1) Prioridad: Activos en Maquinaria categoría Tinta (como indicaste)
    if 'df_activos_cmyk' in locals() and not df_activos_cmyk.empty:
        act = df_activos_cmyk.copy()
        mask_maquinaria = act['unidad'].fillna('').str.contains('Maquinaria', case=False, na=False)
        # Acepta tanto categoría Tinta como Impresión/Impresora para compatibilidad
        mask_categoria_imp = act['categoria'].fillna('').str.contains('Tinta|Impres', case=False, na=False)
        mask_equipo_imp = act['equipo'].fillna('').str.contains('Impres', case=False, na=False)
        posibles_activos = act[mask_maquinaria & (mask_categoria_imp | mask_equipo_imp)]['equipo'].dropna().astype(str).tolist()
        for eq in posibles_activos:
            nombre_limpio = eq
            if '] ' in nombre_limpio:
                nombre_limpio = nombre_limpio.split('] ', 1)[1]
            if nombre_limpio not in impresoras_disponibles:
                impresoras_disponibles.append(nombre_limpio)

    # 2) Fallback: equipos con palabra impresora en inventario
    if not df_impresion_db.empty:
        posibles = df_impresion_db[
            df_impresion_db['item'].str.contains("impresora", case=False, na=False)
        ]['item'].tolist()

        for p in posibles:
            if p not in impresoras_disponibles:
                impresoras_disponibles.append(p)

    # 3) Último fallback por defecto
    if not impresoras_disponibles:
        impresoras_disponibles = ["Impresora Principal", "Impresora Secundaria"]

    # --- VALIDACIÓN ---
    if not impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en el sistema.")
        st.stop()

    # --- SELECCIÓN DE IMPRESORA Y ARCHIVOS ---
    c_printer, c_file = st.columns([1, 2])

    with c_printer:

        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)

        impresora_aliases = [impresora_sel.lower().strip()]
        if ' ' in impresora_aliases[0]:
            impresora_aliases.extend([x for x in impresora_aliases[0].split(' ') if len(x) > 2])

        usar_stock_por_impresora = st.checkbox(
            "Usar tintas del inventario solo de esta impresora",
            value=True,
            help="Actívalo si registras tintas separadas por impresora en inventario."
        )
        auto_negro_inteligente = st.checkbox(
            "Conteo automático inteligente de negro (sombras y mezclas)",
            value=True,
            help="Detecta zonas oscuras y mezclas ricas para sumar consumo real de tinta negra (K)."
        )

        # Mantener separador decimal estilo Python (.) para evitar SyntaxError por locales con coma.
        step_desgaste = 0.005
        step_base_ml = 0.01

        costo_desgaste = st.number_input(
            "Costo desgaste por página ($)",
            min_value=0.0,
            value=0.02,
            step=step_desgaste,
            format="%.3f"
        )
        ml_base_pagina = st.number_input(
            "Consumo base por página a cobertura 100% (ml)",
            min_value=0.01,
            value=0.15,
            step=step_base_ml,
            format="%.3f"
        )

        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)

        if not df_impresion_db.empty:
            mask = df_impresion_db['item'].str.contains("tinta", case=False, na=False)
            tintas = df_impresion_db[mask]

            if usar_stock_por_impresora and not tintas.empty:
                tintas_imp = tintas[tintas['item'].fillna('').str.contains('|'.join(impresora_aliases), case=False, na=False)]
                if not tintas_imp.empty:
                    tintas = tintas_imp
                else:
                    st.info("No se encontraron tintas asociadas a esta impresora; se usará promedio global de tintas.")

            if not tintas.empty:
                precio_tinta_ml = tintas['precio_usd'].mean()
                st.success(f"💧 Precio de tinta detectado: ${precio_tinta_ml:.4f}/ml")

        st.subheader("⚙️ Ajustes de Calibración")

        factor = st.slider(
            "Factor General de Consumo",
            1.0, 3.0, 1.5, 0.1,
            help="Ajuste global según rendimiento real de la impresora"
        )

        factor_k = 0.8
        refuerzo_negro = 0.06
        if auto_negro_inteligente:
            st.success("🧠 Modo automático de negro activo: se detectan sombras y mezclas con negro en cada página.")
        else:
            factor_k = st.slider(
                "Factor Especial para Negro (K)",
                0.5, 1.2, 0.8, 0.05,
                help="Modo manual: ajusta consumo base del negro."
            )
            refuerzo_negro = st.slider(
                "Refuerzo de Negro en Mezclas Oscuras",
                0.0, 0.2, 0.06, 0.01,
                help="Modo manual: simula uso extra de K en sombras."
            )

    with c_file:
        archivos_multiples = st.file_uploader(
            "Carga tus diseños",
            type=['pdf', 'png', 'jpg', 'jpeg'],
            accept_multiple_files=True
        )

    if not archivos_multiples and 'cmyk_analisis_cache' in st.session_state:
        st.session_state.pop('cmyk_analisis_cache', None)

    # --- PROCESAMIENTO ---
    if archivos_multiples:

        try:
            import fitz  # PyMuPDF (opcional para PDF)
        except ModuleNotFoundError:
            fitz = None

        resultados = []
        totales_lote_cmyk = {'C': 0.0, 'M': 0.0, 'Y': 0.0, 'K': 0.0}
        total_pags = 0

        with st.spinner('🚀 Analizando cobertura real...'):

            for arc in archivos_multiples:

                try:
                    paginas_items = []
                    bytes_data = arc.read()

                    if arc.name.lower().endswith('.pdf'):

                        if fitz is None:
                            st.error(
                                f"No se puede analizar '{arc.name}' porque falta PyMuPDF (fitz). "
                                "Carga imágenes (PNG/JPG) o instala la dependencia para PDF."
                            )
                            continue

                        doc = fitz.open(stream=bytes_data, filetype="pdf")

                        for i in range(len(doc)):
                            page = doc.load_page(i)

                            pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)

                            img = Image.frombytes(
                                "CMYK",
                                [pix.width, pix.height],
                                pix.samples
                            )

                            paginas_items.append((f"{arc.name} (P{i+1})", img))

                        doc.close()

                    else:
                        img = Image.open(io.BytesIO(bytes_data)).convert('CMYK')
                        paginas_items.append((arc.name, img))

                    for nombre, img_obj in paginas_items:

                        total_pags += 1
                        arr = np.array(img_obj)

                        c_chan = arr[:, :, 0] / 255.0
                        m_chan = arr[:, :, 1] / 255.0
                        y_chan = arr[:, :, 2] / 255.0
                        k_chan = arr[:, :, 3] / 255.0

                        c_media = float(np.mean(c_chan))
                        m_media = float(np.mean(m_chan))
                        y_media = float(np.mean(y_chan))
                        k_media = float(np.mean(k_chan))

                        ml_c = c_media * ml_base_pagina * factor
                        ml_m = m_media * ml_base_pagina * factor
                        ml_y = y_media * ml_base_pagina * factor

                        ml_k_base = k_media * ml_base_pagina * factor * factor_k
                        k_extra_ml = 0.0

                        if auto_negro_inteligente:
                            cobertura_cmy = (c_chan + m_chan + y_chan) / 3.0
                            neutral_mask = (
                                (np.abs(c_chan - m_chan) < 0.08)
                                & (np.abs(m_chan - y_chan) < 0.08)
                            )
                            shadow_mask = (k_chan > 0.45) | (cobertura_cmy > 0.60)
                            rich_black_mask = shadow_mask & (cobertura_cmy > 0.35)

                            ratio_extra = (
                                float(np.mean(shadow_mask)) * 0.12
                                + float(np.mean(neutral_mask)) * 0.10
                                + float(np.mean(rich_black_mask)) * 0.18
                            )
                            k_extra_ml = ml_base_pagina * factor * ratio_extra
                        else:
                            promedio_color = (c_media + m_media + y_media) / 3
                            if promedio_color > 0.55:
                                k_extra_ml = promedio_color * refuerzo_negro * factor

                        ml_k = ml_k_base + k_extra_ml
                        consumo_total_f = ml_c + ml_m + ml_y + ml_k

                        costo_f = (consumo_total_f * precio_tinta_ml) + costo_desgaste

                        totales_lote_cmyk['C'] += ml_c
                        totales_lote_cmyk['M'] += ml_m
                        totales_lote_cmyk['Y'] += ml_y
                        totales_lote_cmyk['K'] += ml_k

                        resultados.append({
                            "Archivo": nombre,
                            "C (ml)": round(ml_c, 4),
                            "M (ml)": round(ml_m, 4),
                            "Y (ml)": round(ml_y, 4),
                            "K (ml)": round(ml_k, 4),
                            "K extra auto (ml)": round(k_extra_ml, 4),
                            "Total ml": round(consumo_total_f, 4),
                            "Costo $": round(costo_f, 4)
                        })

                except Exception as e:
                    st.error(f"Error analizando {arc.name}: {e}")

        # --- RESULTADOS ---
        if resultados:

            st.subheader("📋 Desglose por Archivo")
            st.dataframe(pd.DataFrame(resultados), use_container_width=True)

            st.subheader("🧪 Consumo Total de Tintas")

            col_c, col_m, col_y, col_k = st.columns(4)

            col_c.metric("Cian", f"{totales_lote_cmyk['C']:.3f} ml")
            col_m.metric("Magenta", f"{totales_lote_cmyk['M']:.3f} ml")
            col_y.metric("Amarillo", f"{totales_lote_cmyk['Y']:.3f} ml")
            col_k.metric("Negro", f"{totales_lote_cmyk['K']:.3f} ml")

            st.divider()

            total_usd_lote = sum(r['Costo $'] for r in resultados)

            costo_promedio_pagina = (total_usd_lote / total_pags) if total_pags > 0 else 0
            st.metric(
                "💰 Costo Total Estimado de Producción",
                f"$ {total_usd_lote:.2f}",
                delta=f"$ {costo_promedio_pagina:.4f} por pág"
            )

            df_totales = pd.DataFrame([
                {"Color": "C", "ml": totales_lote_cmyk['C']},
                {"Color": "M", "ml": totales_lote_cmyk['M']},
                {"Color": "Y", "ml": totales_lote_cmyk['Y']},
                {"Color": "K", "ml": totales_lote_cmyk['K']}
            ])
            fig_cmyk = px.pie(df_totales, names='Color', values='ml', title='Distribución de consumo CMYK')
            st.plotly_chart(fig_cmyk, use_container_width=True)

            df_resultados = pd.DataFrame(resultados)
            st.download_button(
                "📥 Descargar desglose CMYK (CSV)",
                data=df_resultados.to_csv(index=False).encode('utf-8'),
                file_name="analisis_cmyk.csv",
                mime="text/csv"
            )

            # --- COSTEO AUTOMÁTICO POR PAPEL Y CALIDAD ---
            st.subheader("🧾 Simulación automática por Papel y Calidad")
            # Papeles desde inventario (precio_usd) con fallback por defecto
            perfiles_papel = {}
            try:
                papeles_inv = df_impresion_db[
                    df_impresion_db['item'].fillna('').str.contains(
                        'papel|bond|fotograf|cartulina|adhesivo|opalina|sulfato',
                        case=False,
                        na=False
                    )
                ][['item', 'precio_usd']].dropna(subset=['precio_usd'])

                for _, row_p in papeles_inv.iterrows():
                    nombre_p = str(row_p['item']).strip()
                    precio_p = float(row_p['precio_usd'])
                    if precio_p > 0:
                        perfiles_papel[nombre_p] = precio_p
            except Exception:
                perfiles_papel = {}

            if not perfiles_papel:
                perfiles_papel = {
                    "Bond 75g": 0.03,
                    "Bond 90g": 0.05,
                    "Fotográfico Brillante": 0.22,
                    "Fotográfico Mate": 0.20,
                    "Cartulina": 0.12,
                    "Adhesivo": 0.16
                }
                st.info("No se detectaron papeles en inventario; se usan costos base por defecto.")
            else:
                st.success("📄 Costos de papeles detectados automáticamente desde inventario.")
            perfiles_calidad = {
                "Borrador": {"ink_mult": 0.82, "wear_mult": 0.90},
                "Normal": {"ink_mult": 1.00, "wear_mult": 1.00},
                "Alta": {"ink_mult": 1.18, "wear_mult": 1.10},
                "Foto": {"ink_mult": 1.32, "wear_mult": 1.15}
            }

            total_ml_lote = float(sum(totales_lote_cmyk.values()))
            costo_tinta_base = total_ml_lote * float(precio_tinta_ml)
            costo_desgaste_base = float(costo_desgaste) * float(total_pags)

            simulaciones = []
            for papel, costo_hoja in perfiles_papel.items():
                for calidad, cfg_q in perfiles_calidad.items():
                    costo_tinta_q = costo_tinta_base * cfg_q['ink_mult']
                    costo_desgaste_q = costo_desgaste_base * cfg_q['wear_mult']
                    costo_papel_q = float(total_pags) * costo_hoja
                    total_q = costo_tinta_q + costo_desgaste_q + costo_papel_q
                    simulaciones.append({
                        "Papel": papel,
                        "Calidad": calidad,
                        "Páginas": total_pags,
                        "Tinta ($)": round(costo_tinta_q, 2),
                        "Desgaste ($)": round(costo_desgaste_q, 2),
                        "Papel ($)": round(costo_papel_q, 2),
                        "Total ($)": round(total_q, 2),
                        "Costo por pág ($)": round(total_q / total_pags, 4) if total_pags else 0
                    })

            df_sim = pd.DataFrame(simulaciones).sort_values('Total ($)')
            st.dataframe(df_sim, use_container_width=True, hide_index=True)
            fig_sim = px.bar(df_sim.head(12), x='Papel', y='Total ($)', color='Calidad', barmode='group', title='Comparativo de costos (top 12 más económicos)')
            st.plotly_chart(fig_sim, use_container_width=True)

            mejor = df_sim.iloc[0]
            st.success(
                f"Mejor costo automático: {mejor['Papel']} | {mejor['Calidad']} → ${mejor['Total ($)']:.2f} "
                f"(${mejor['Costo por pág ($)']:.4f}/pág)"
            )

            st.session_state['cmyk_analisis_cache'] = {
                'resultados': resultados,
                'simulaciones': simulaciones,
                'impresora': impresora_sel,
                'paginas': total_pags
            }

            # --- VERIFICAR INVENTARIO ---
            if not df_impresion_db.empty:

                st.subheader("📦 Verificación de Inventario")

                alertas = []

                stock_base = df_impresion_db[df_impresion_db['item'].str.contains('tinta', case=False, na=False)].copy()
                if usar_stock_por_impresora:
                    stock_imp = stock_base[stock_base['item'].fillna('').str.contains('|'.join(impresora_aliases), case=False, na=False)]
                    if not stock_imp.empty:
                        stock_base = stock_imp

                alias_colores = {
                    'C': ['cian', 'cyan'],
                    'M': ['magenta'],
                    'Y': ['amarillo', 'yellow'],
                    # K = Negro. Incluye variantes reales de inventario: negro/negra/black/k
                    'K': ['negro', 'negra', 'black', ' k ']
                }

                for color, ml in totales_lote_cmyk.items():
                    aliases = alias_colores.get(color, [])
                    stock = stock_base[(" " + stock_base['item'].fillna('').str.lower() + " " ).str.contains('|'.join(aliases), case=False, na=False)] if aliases else pd.DataFrame()

                    if not stock.empty:
                        disponible = stock['cantidad'].sum()

                        if disponible < ml:
                            alertas.append(
                                f"⚠️ Falta tinta {color}: necesitas {ml:.2f} ml y hay {disponible:.2f} ml"
                            )
                    else:
                        alertas.append(f"⚠️ No se encontró tinta {color} asociada en inventario para validar stock.")

                if alertas:
                    for a in alertas:
                        st.error(a)
                else:
                    st.success("✅ Hay suficiente tinta para producir")


                       # --- ENVÍO A COTIZACIÓN ---
            if st.button("📝 ENVIAR A COTIZACIÓN", use_container_width=True):

                # Guardamos información completa para el cotizador
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Impresión {impresora_sel} ({total_pags} pgs)",
                    'costo_base': float(df_sim.iloc[0]['Total ($)']) if not df_sim.empty else float(total_usd_lote),
                    'unidades': total_pags,

                    # Desglose de consumo real
                    'consumos': totales_lote_cmyk,

                    # Información técnica adicional
                    'impresora': impresora_sel,
                    'factor_consumo': factor,
                    'factor_negro': factor_k,
                    'refuerzo_negro': refuerzo_negro,
                    'precio_tinta_ml': precio_tinta_ml,
                    'costo_desgaste': costo_desgaste,

                    # Historial detallado por archivo
                    'detalle_archivos': resultados
                }

                try:
                    with conectar() as conn:
                        conn.execute("""
                            INSERT INTO historial_cmyk
                            (impresora, paginas, costo)
                            VALUES (?,?,?)
                        """, (impresora_sel, total_pags, total_usd_lote))
                        conn.commit()
                except Exception as e:
                    st.warning(f"No se pudo guardar en historial: {e}")

                st.success("✅ Datos enviados correctamente al módulo de Cotizaciones")
                st.toast("Listo para cotizar", icon="📨")

                st.rerun()


    st.divider()
    st.subheader("🕘 Historial reciente CMYK")
    if df_hist_cmyk.empty:
        st.info("Aún no hay análisis guardados en el historial.")
    else:
        df_hist_view = df_hist_cmyk.copy()
        df_hist_view['fecha'] = pd.to_datetime(df_hist_view['fecha'], errors='coerce')
        st.dataframe(df_hist_view, use_container_width=True, hide_index=True)

        hist_ordenado = df_hist_view.dropna(subset=['fecha']).copy()
        if not hist_ordenado.empty:
            hist_ordenado['dia'] = hist_ordenado['fecha'].dt.date.astype(str)
            hist_dia = hist_ordenado.groupby('dia', as_index=False)['costo'].sum()
            fig_hist = px.line(hist_dia, x='dia', y='costo', markers=True, title='Costo CMYK por día (historial)')
            fig_hist.update_layout(xaxis_title='Día', yaxis_title='Costo ($)')
            st.plotly_chart(fig_hist, use_container_width=True)


# --- 9. MÓDULO PROFESIONAL DE ACTIVOS ---
elif menu == "🏗️ Activos":

    if ROL != "Admin":
        st.error("🚫 Acceso Denegado. Solo Administración puede gestionar activos.")
        st.stop()

    st.title("🏗️ Gestión Integral de Activos")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:
            df = pd.read_sql_query("SELECT * FROM activos", conn)

            # Crear tabla de historial si no existe
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activos_historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activo TEXT,
                    accion TEXT,
                    detalle TEXT,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")
        st.stop()

    # --- REGISTRO DE NUEVO ACTIVO ---
    with st.expander("➕ Registrar Nuevo Activo"):

        with st.form("form_activos_pro"):

            c1, c2 = st.columns(2)

            nombre_eq = c1.text_input("Nombre del Activo")
            tipo_seccion = c2.selectbox("Tipo de Activo", [
                "Maquinaria (Equipos Grandes)",
                "Herramienta Manual (Uso diario)",
                "Repuesto Crítico (Stock de seguridad)"
            ])

            col_m1, col_m2, col_m3 = st.columns(3)

            monto_inv = col_m1.number_input("Inversión ($)", min_value=0.0)
            vida_util = col_m2.number_input("Vida Útil (Usos)", min_value=1, value=1000)

            categoria_especifica = col_m3.selectbox(
                "Categoría",
                ["Corte", "Impresión", "Tinta", "Calor", "Mobiliario", "Mantenimiento"]
            )

            if st.form_submit_button("🚀 Guardar Activo"):

                if not nombre_eq:
                    st.error("Debe indicar un nombre.")
                    st.stop()

                if monto_inv <= 0:
                    st.error("La inversión debe ser mayor a cero.")
                    st.stop()

                desgaste_u = monto_inv / vida_util

                try:
                    with conectar() as conn:
                        conn.execute("""
                            INSERT INTO activos 
                            (equipo, categoria, inversion, unidad, desgaste) 
                            VALUES (?,?,?,?,?)
                        """, (
                            f"[{tipo_seccion[:3].upper()}] {nombre_eq}",
                            categoria_especifica,
                            monto_inv,
                            tipo_seccion,
                            desgaste_u
                        ))

                        conn.execute("""
                            INSERT INTO activos_historial 
                            (activo, accion, detalle, costo)
                            VALUES (?,?,?,?)
                        """, (nombre_eq, "CREACIÓN", "Registro inicial", monto_inv))

                        conn.commit()

                    st.success("✅ Activo registrado correctamente.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al registrar: {e}")

    st.divider()

    # --- EDICIÓN DE ACTIVOS ---
    with st.expander("✏️ Editar Activo Existente"):

        if df.empty:
            st.info("No hay activos para editar.")
        else:
            activo_sel = st.selectbox("Seleccionar activo:", df['equipo'].tolist())

            datos = df[df['equipo'] == activo_sel].iloc[0]

            with st.form("editar_activo"):

                c1, c2, c3 = st.columns(3)

                nueva_inv = c1.number_input("Inversión ($)", value=float(datos['inversion']))
                nueva_vida = c2.number_input("Vida útil", value=1000)
                nueva_cat = c3.selectbox(
                    "Categoría",
                    ["Corte", "Impresión", "Tinta", "Calor", "Mobiliario", "Mantenimiento"],
                    index=0
                )

                if st.form_submit_button("💾 Guardar Cambios"):

                    nuevo_desgaste = nueva_inv / nueva_vida

                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE activos
                                SET inversion = ?, categoria = ?, desgaste = ?
                                WHERE id = ?
                            """, (nueva_inv, nueva_cat, nuevo_desgaste, int(datos['id'])))

                            conn.execute("""
                                INSERT INTO activos_historial 
                                (activo, accion, detalle, costo)
                                VALUES (?,?,?,?)
                            """, (activo_sel, "EDICIÓN", "Actualización de valores", nueva_inv))

                            conn.commit()

                        st.success("Activo actualizado.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error al actualizar: {e}")

    st.divider()

    # --- VISUALIZACIÓN POR SECCIONES ---
    t1, t2, t3, t4, t5 = st.tabs([
        "📟 Maquinaria",
        "🛠️ Herramientas",
        "🔄 Repuestos",
        "📊 Resumen Global",
        "📜 Historial"
    ])

    if not df.empty:

        with t1:
            st.subheader("Equipos y Maquinaria")
            df_maq = df[df['unidad'].str.contains("Maquinaria")]
            st.dataframe(df_maq, use_container_width=True, hide_index=True)

        with t2:
            st.subheader("Herramientas Manuales")
            df_her = df[df['unidad'].str.contains("Herramienta")]
            st.dataframe(df_her, use_container_width=True, hide_index=True)

        with t3:
            st.subheader("Repuestos Críticos")
            df_rep = df[df['unidad'].str.contains("Repuesto")]
            st.dataframe(df_rep, use_container_width=True, hide_index=True)

        with t4:
            c_inv, c_des, c_prom = st.columns(3)

            c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
            c_des.metric("Activos Registrados", len(df))

            promedio = df['desgaste'].mean() if not df.empty else 0
            c_prom.metric("Desgaste Promedio por Uso", f"$ {promedio:.4f}")

            fig = px.bar(
                df,
                x='equipo',
                y='inversion',
                color='categoria',
                title="Distribución de Inversión por Activo"
            )
            st.plotly_chart(fig, use_container_width=True)

        with t5:
            st.subheader("Historial de Movimientos de Activos")

            try:
                with conectar() as conn:
                    df_hist = pd.read_sql_query(
                        "SELECT activo, accion, detalle, costo, fecha FROM activos_historial ORDER BY fecha DESC",
                        conn
                    )

                if not df_hist.empty:
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay movimientos registrados aún.")

            except Exception as e:
                st.error(f"Error cargando historial: {e}")

    else:
        st.info("No hay activos registrados todavía.")


# ===========================================================
# 11. MÓDULO PROFESIONAL DE OTROS PROCESOS
# ===========================================================
elif menu == "🛠️ Otros Procesos":

    st.title("🛠️ Calculadora de Procesos Especiales")
    st.info("Cálculo de costos de procesos que no usan tinta: corte, laminado, planchado, etc.")

    # --- CARGA SEGURA DE EQUIPOS ---
    try:
        with conectar() as conn:
            df_act_db = pd.read_sql_query(
                "SELECT equipo, categoria, unidad, desgaste FROM activos", conn
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial_procesos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equipo TEXT,
                    cantidad REAL,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    except Exception as e:
        st.error(f"Error cargando activos: {e}")
        st.stop()

    # Filtrar solo equipos que NO gastan tinta
    otros_equipos = df_act_db[
        df_act_db['categoria'] != "Impresora (Gasta Tinta)"
    ].to_dict('records')

    if not otros_equipos:
        st.warning("⚠️ No hay equipos registrados para procesos especiales.")
        st.stop()

    nombres_eq = [e['equipo'] for e in otros_equipos]

    if "lista_procesos" not in st.session_state:
        st.session_state.lista_procesos = []

    with st.container(border=True):

        c1, c2 = st.columns(2)

        eq_sel = c1.selectbox("Selecciona el Proceso/Equipo:", nombres_eq)

        datos_eq = next(e for e in otros_equipos if e['equipo'] == eq_sel)

        cantidad = c2.number_input(
            f"Cantidad de {datos_eq['unidad']}:",
            min_value=1.0,
            value=1.0
        )

        # Conversión segura del desgaste
        costo_unitario = float(datos_eq.get('desgaste', 0.0))
        costo_total = costo_unitario * cantidad

        st.divider()

        r1, r2 = st.columns(2)
        r1.metric("Costo Unitario", f"$ {costo_unitario:.4f}")
        r2.metric("Costo Total", f"$ {costo_total:.2f}")

        if st.button("➕ Agregar Proceso"):
            st.session_state.lista_procesos.append({
                "equipo": eq_sel,
                "cantidad": cantidad,
                "costo": costo_total
            })
            st.toast("Proceso añadido")

    # --- RESUMEN DE PROCESOS EN SESIÓN ---
    if st.session_state.lista_procesos:

        st.subheader("📋 Procesos Acumulados")

        df_proc = pd.DataFrame(st.session_state.lista_procesos)
        st.dataframe(df_proc, use_container_width=True, hide_index=True)

        total = df_proc["costo"].sum()
        st.metric("Total Procesos", f"$ {total:.2f}")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📝 Enviar a Cotización", use_container_width=True):

                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': " + ".join(df_proc["equipo"].tolist()),
                    'costo_base': float(total),
                    'unidades': 1,
                    'es_proceso_extra': True
                }

                st.success("Enviado a cotización")
                st.session_state.lista_procesos = []
                st.rerun()

        with col2:
            if st.button("🧹 Limpiar", use_container_width=True):
                st.session_state.lista_procesos = []
                st.rerun()

    # --- HISTORIAL ---
    with st.expander("📜 Historial de Procesos"):

        try:
            with conectar() as conn:
                df_hist = pd.read_sql_query(
                    "SELECT * FROM historial_procesos ORDER BY fecha DESC",
                    conn
                )

            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("Sin registros aún.")

        except Exception as e:
            st.info("Historial no disponible.")


# ===========================================================
# 12. MÓDULO PROFESIONAL DE VENTAS (VERSIÓN 2.0)
# ===========================================================
elif menu == "💰 Ventas":

    st.title("💰 Gestión Profesional de Ventas")

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar Venta",
        "📜 Historial",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE VENTA
    # -----------------------------------
    with tab1:

        df_cli = st.session_state.get("df_cli", pd.DataFrame())

        if df_cli.empty:
            st.warning("⚠️ Registra clientes primero.")
            st.stop()

        with st.form("venta_manual", clear_on_submit=True):

            st.subheader("Datos de la Venta")

            opciones_cli = {
                row['nombre']: row['id']
                for _, row in df_cli.iterrows()
            }

            col1, col2 = st.columns(2)

            cliente_nombre = col1.selectbox(
                "Cliente:",
                list(opciones_cli.keys())
            )

            detalle_v = col2.text_input(
                "Detalle de lo vendido:"
            )

            col3, col4, col5 = st.columns(3)

            monto_venta = col3.number_input(
                "Monto ($):",
                min_value=0.01,
                format="%.2f"
            )

            metodo_pago = col4.selectbox(
                "Método:",
                ["Efectivo ($)", "Pago Móvil (BCV)", "Zelle", "Binance (USDT)", "Transferencia (Bs)", "Pendiente"]
            )

            tasa_uso = t_bcv if "BCV" in metodo_pago else (
                t_bin if "Binance" in metodo_pago else 1.0
            )

            monto_bs = monto_venta * tasa_uso

            col5.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            submit_venta = st.form_submit_button("🚀 Registrar Venta")

        if submit_venta:

            if not detalle_v.strip():
                st.error("Debes indicar el detalle de la venta.")
                st.stop()

            consumos = {}

            exito, msg = registrar_venta_global(
                id_cliente=opciones_cli[cliente_nombre],
                nombre_cliente=cliente_nombre,
                detalle=detalle_v.strip(),
                monto_usd=float(monto_venta),
                metodo=metodo_pago,
                consumos=consumos,
                usuario=st.session_state.get("usuario_nombre", "Sistema")
            )

            if exito:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    # -----------------------------------
    # HISTORIAL
    # -----------------------------------
    with tab2:

        st.subheader("Historial de Ventas")

        try:
            with conectar() as conn:
                df_historial = pd.read_sql_query("""
                    SELECT 
                        v.id,
                        v.fecha,
                        v.cliente,
                        v.detalle,
                        v.monto_total as total,
                        v.metodo,
                        e.tasa,
                        e.monto_bs
                    FROM ventas v
                    LEFT JOIN ventas_extra e ON v.id = e.venta_id
                    ORDER BY v.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_historial.empty:
            st.info("No hay ventas aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", date.today() - timedelta(days=30))
        hasta = c2.date_input("Hasta", date.today())

        df_historial['fecha'] = pd.to_datetime(df_historial['fecha'], errors='coerce')

        df_fil = df_historial[
            (df_historial['fecha'].dt.date >= desde) &
            (df_historial['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por cliente o detalle:")

        if busc:
            df_fil = df_fil[
                df_fil['cliente'].str.contains(busc, case=False, na=False) |
                df_fil['detalle'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del periodo", f"$ {df_fil['total'].sum():.2f}")

        # --- GESTIÓN DE PENDIENTES ---
        st.subheader("Gestión de Cuentas Pendientes")

        pendientes = df_fil[df_fil['metodo'] == "Pendiente"]

        for _, row in pendientes.iterrows():

            with st.container(border=True):

                st.write(f"**{row['cliente']}** – ${row['total']:.2f}")

                if st.button(f"Marcar como pagada #{row['id']}"):

                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE ventas
                                SET metodo = 'Pagado'
                                WHERE id = ?
                            """, (int(row['id']),))
                            conn.commit()

                        st.success("Actualizado")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fil.to_excel(writer, index=False, sheet_name='Ventas')

        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "historial_ventas.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    with tab3:

        st.subheader("Resumen Comercial")

        try:
            with conectar() as conn:
                df_v = pd.read_sql("SELECT * FROM ventas", conn)
        except:
            st.info("Sin datos")
            st.stop()

        if df_v.empty:
            st.info("No hay ventas registradas.")
            st.stop()

        total = df_v['monto_total'].sum()

        c1, c2, c3 = st.columns(3)

        c1.metric("Ventas Totales", f"$ {total:.2f}")

        pendientes = df_v[
            df_v['metodo'].str.contains("Pendiente", case=False, na=False)
        ]['monto_total'].sum()

        c2.metric("Por Cobrar", f"$ {pendientes:.2f}")

        top = df_v.groupby('cliente')['monto_total'].sum().reset_index()

        mejor = top.sort_values("monto_total", ascending=False).head(1)

        if not mejor.empty:
            c3.metric("Mejor Cliente", mejor.iloc[0]['cliente'])

        st.subheader("Ventas por Cliente")
        st.bar_chart(top.set_index("cliente"))


# ===========================================================
# 12. MÓDULO PROFESIONAL DE GASTOS (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "📉 Gastos":

    st.title("📉 Control Integral de Gastos")
    st.info("Registro, análisis y control de egresos del negocio")

    # Solo administración puede registrar gastos
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede gestionar gastos.")
        st.stop()

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar Gasto",
        "📜 Historial",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE GASTOS
    # -----------------------------------
    with tab1:

        with st.form("form_gastos_pro", clear_on_submit=True):

            col_d, col_c = st.columns([2, 1])

            desc = col_d.text_input(
                "Descripción del Gasto",
                placeholder="Ej: Pago de luz, resma de papel, repuesto..."
            ).strip()

            categoria = col_c.selectbox("Categoría:", [
                "Materia Prima",
                "Mantenimiento de Equipos",
                "Servicios (Luz/Internet)",
                "Publicidad",
                "Sueldos/Retiros",
                "Logística",
                "Otros"
            ])

            c1, c2, c3 = st.columns(3)

            monto_gasto = c1.number_input(
                "Monto en Dólares ($):",
                min_value=0.01,
                format="%.2f"
            )

            metodo_pago = c2.selectbox("Método de Pago:", [
                "Efectivo ($)",
                "Pago Móvil (BCV)",
                "Zelle",
                "Binance (USDT)",
                "Transferencia (Bs)"
            ])

            tasa_ref = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (
                t_bin if "Binance" in metodo_pago else 1.0
            )

            monto_bs = monto_gasto * tasa_ref

            c3.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            st.divider()

            if st.form_submit_button("📉 REGISTRAR EGRESO"):

                if not desc:
                    st.error("⚠️ La descripción es obligatoria.")
                    st.stop()

                try:
                    with conectar() as conn:

                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS gastos_extra (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                gasto_id INTEGER,
                                tasa REAL,
                                monto_bs REAL,
                                usuario TEXT
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO gastos 
                            (descripcion, monto, categoria, metodo) 
                            VALUES (?, ?, ?, ?)
                        """, (desc, float(monto_gasto), categoria, metodo_pago))

                        gasto_id = cur.lastrowid

                        cur.execute("""
                            INSERT INTO gastos_extra
                            (gasto_id, tasa, monto_bs, usuario)
                            VALUES (?, ?, ?, ?)
                        """, (
                            gasto_id,
                            float(tasa_ref),
                            float(monto_bs),
                            st.session_state.get("usuario_nombre", "Sistema")
                        ))

                        conn.commit()

                    st.success("📉 Gasto registrado correctamente.")
                    st.balloons()
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Error al guardar el gasto: {e}")

    # -----------------------------------
    # HISTORIAL DE GASTOS
    # -----------------------------------
    with tab2:

        st.subheader("📋 Historial de Gastos")

        try:
            with conectar() as conn:
                df_g = pd.read_sql_query("""
                    SELECT 
                        g.id,
                        g.fecha,
                        g.descripcion,
                        g.categoria,
                        g.monto,
                        g.metodo,
                        e.tasa,
                        e.monto_bs,
                        e.usuario
                    FROM gastos g
                    LEFT JOIN gastos_extra e ON g.id = e.gasto_id
                    ORDER BY g.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_g.empty:
            st.info("No hay gastos registrados aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", date.today() - timedelta(days=30))
        hasta = c2.date_input("Hasta", date.today())

        df_g['fecha'] = pd.to_datetime(df_g['fecha'], errors='coerce')

        df_fil = df_g[
            (df_g['fecha'].dt.date >= desde) &
            (df_g['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por descripción:")

        if busc:
            df_fil = df_fil[
                df_fil['descripcion'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del Periodo", f"$ {df_fil['monto'].sum():.2f}")

        # --- EDICIÓN Y ELIMINACIÓN ---
        st.subheader("Gestión de Gastos")

        gasto_sel = st.selectbox(
            "Seleccionar gasto para editar/eliminar:",
            df_fil['descripcion'].tolist()
        )

        datos = df_fil[df_fil['descripcion'] == gasto_sel].iloc[0]

        with st.expander("✏️ Editar Gasto"):

            nuevo_monto = st.number_input(
                "Monto $",
                value=float(datos['monto']),
                format="%.2f"
            )

            if st.button("💾 Guardar Cambios"):

                try:
                    with conectar() as conn:
                        conn.execute("""
                            UPDATE gastos
                            SET monto = ?
                            WHERE id = ?
                        """, (float(nuevo_monto), int(datos['id'])))
                        conn.commit()

                    st.success("Actualizado correctamente")
                    st.rerun()

                except Exception as e:
                    st.error(str(e))

        with st.expander("🗑️ Eliminar Gasto"):

            confirmar = st.checkbox("Confirmo que deseo eliminar este gasto")

            if st.button("Eliminar definitivamente"):

                if not confirmar:
                    st.warning("Debes confirmar para eliminar")
                else:
                    try:
                        with conectar() as conn:
                            conn.execute(
                                "DELETE FROM gastos WHERE id = ?",
                                (int(datos['id']),)
                            )
                            conn.commit()

                        st.warning("Gasto eliminado")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fil.to_excel(writer, index=False, sheet_name='Gastos')

        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "historial_gastos.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    with tab3:

        st.subheader("📊 Resumen de Egresos")

        try:
            with conectar() as conn:
                df = pd.read_sql("SELECT * FROM gastos", conn)
        except:
            st.info("Sin datos")
            st.stop()

        if df.empty:
            st.info("No hay gastos para analizar.")
            st.stop()

        total = df['monto'].sum()

        c1, c2 = st.columns(2)

        c1.metric("Total Gastado", f"$ {total:.2f}")

        por_cat = df.groupby('categoria')['monto'].sum()

        categoria_top = por_cat.idxmax() if not por_cat.empty else "N/A"

        c2.metric("Categoría Principal", categoria_top)

        st.subheader("Gastos por Categoría")
        st.bar_chart(por_cat)


# ===========================================================
# 13. MÓDULO PROFESIONAL DE CIERRE DE CAJA (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "🏁 Cierre de Caja":

    st.title("🏁 Cierre de Caja y Arqueo Diario")

    # --- SEGURIDAD ---
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede realizar cierres.")
        st.stop()

    # Selección de fecha
    fecha_cierre = st.date_input("Seleccionar fecha:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    try:
        with conectar() as conn:

            # Asegurar tabla de cierres
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cierres_caja (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT UNIQUE,
                    ingresos REAL,
                    egresos REAL,
                    neto REAL,
                    usuario TEXT,
                    creado DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            df_v = pd.read_sql(
                "SELECT * FROM ventas WHERE date(fecha) = ?",
                conn,
                params=(fecha_str,)
            )

            df_g = pd.read_sql(
                "SELECT * FROM gastos WHERE date(fecha) = ?",
                conn,
                params=(fecha_str,)
            )

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # Asegurar que existan columnas esperadas
    if not df_v.empty and 'metodo' not in df_v.columns:
        df_v['metodo'] = ""

    # --- SEPARAR COBRADO Y PENDIENTE ---
    if not df_v.empty:
        cobradas = df_v[~df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
        pendientes = df_v[df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
    else:
        cobradas = pd.DataFrame(columns=df_v.columns)
        pendientes = pd.DataFrame(columns=df_v.columns)

    t_ventas_cobradas = float(cobradas['monto_total'].sum()) if not cobradas.empty else 0.0
    t_pendientes = float(pendientes['monto_total'].sum()) if not pendientes.empty else 0.0
    t_gastos = float(df_g['monto'].sum()) if not df_g.empty else 0.0

    balance_dia = t_ventas_cobradas - t_gastos

    # --- MÉTRICAS PRINCIPALES ---
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Ingresos Cobrados", f"$ {t_ventas_cobradas:,.2f}")
    c2.metric("Cuentas Pendientes", f"$ {t_pendientes:,.2f}")
    c3.metric("Egresos del Día", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c4.metric("Neto en Caja", f"$ {balance_dia:,.2f}")

    st.divider()

    # --- DESGLOSE POR MÉTODO ---
    col_v, col_g = st.columns(2)

    with col_v:
        st.subheader("💰 Ingresos por Método")

        if not cobradas.empty:
            resumen_v = cobradas.groupby('metodo')['monto_total'].sum()
            for metodo, monto in resumen_v.items():
                st.write(f"✅ **{metodo}:** ${float(monto):,.2f}")
        else:
            st.info("No hubo ingresos cobrados.")

    with col_g:
        st.subheader("💸 Egresos por Método")

        if not df_g.empty:
            resumen_g = df_g.groupby('metodo')['monto'].sum()
            for metodo, monto in resumen_g.items():
                st.write(f"❌ **{metodo}:** ${float(monto):,.2f}")
        else:
            st.info("No hubo gastos.")

    st.divider()

    # --- DETALLES ---
    with st.expander("📝 Ver detalle completo"):

        st.write("### Ventas Cobradas")
        if not cobradas.empty:
            st.dataframe(cobradas, use_container_width=True, hide_index=True)
        else:
            st.info("Sin ventas cobradas")

        st.write("### Ventas Pendientes")
        if not pendientes.empty:
            st.dataframe(pendientes, use_container_width=True, hide_index=True)
        else:
            st.info("Sin ventas pendientes")

        st.write("### Gastos")
        if not df_g.empty:
            st.dataframe(df_g, use_container_width=True, hide_index=True)
        else:
            st.info("Sin gastos registrados")

    # --- GUARDAR CIERRE ---
    if st.button("💾 Guardar Cierre del Día"):

        try:
            with conectar() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cierres_caja
                    (fecha, ingresos, egresos, neto, usuario)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    fecha_str,
                    float(t_ventas_cobradas),
                    float(t_gastos),
                    float(balance_dia),
                    st.session_state.get("usuario_nombre", "Sistema")
                ))
                conn.commit()

            st.success("✅ Cierre registrado correctamente")

        except Exception as e:
            st.error(f"Error guardando cierre: {e}")

    # --- HISTORIAL DE CIERRES ---
    st.divider()
    st.subheader("📜 Historial de Cierres")

    try:
        with conectar() as conn:
            df_cierres = pd.read_sql(
                "SELECT * FROM cierres_caja ORDER BY fecha DESC",
                conn
            )

        if not df_cierres.empty:
            st.dataframe(df_cierres, use_container_width=True)

            # Exportación
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_cierres.to_excel(writer, index=False, sheet_name='Cierres')

            st.download_button(
                "📥 Descargar Historial de Cierres",
                buffer.getvalue(),
                "cierres_caja.xlsx"
            )
        else:
            st.info("Aún no hay cierres guardados.")

    except Exception as e:
        st.info("No hay historial disponible.")



# ===========================================================
# 13. AUDITORÍA Y MÉTRICAS - VERSIÓN PROFESIONAL MEJORADA 2.1
# ===========================================================
elif menu == "📊 Auditoría y Métricas":

    st.title("📊 Auditoría Integral del Negocio")
    st.caption("Control total de insumos, producción y finanzas")

    try:
        with conectar() as conn:

            # Verificamos si existe la tabla de movimientos
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventario_movs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    tipo TEXT,
                    cantidad REAL,
                    motivo TEXT,
                    usuario TEXT,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            df_movs = pd.read_sql_query("""
                SELECT 
                    m.fecha,
                    i.item as Material,
                    m.tipo as Operacion,
                    m.cantidad as Cantidad,
                    i.unidad,
                    m.motivo
                FROM inventario_movs m
                JOIN inventario i ON m.item_id = i.id
                ORDER BY m.fecha DESC
            """, conn)

            df_ventas = pd.read_sql("SELECT * FROM ventas", conn)
            df_gastos = pd.read_sql("SELECT * FROM gastos", conn)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # Asegurar columnas necesarias
    if not df_ventas.empty and 'metodo' not in df_ventas.columns:
        df_ventas['metodo'] = ""

    tab1, tab2, tab3, tab4 = st.tabs([
        "💰 Finanzas",
        "📦 Insumos",
        "📈 Gráficos",
        "🚨 Alertas"
    ])

    # ---------------------------------------
    # TAB FINANZAS
    # ---------------------------------------
    with tab1:

        st.subheader("Resumen Financiero")

        total_ventas = float(df_ventas['monto_total'].sum()) if not df_ventas.empty else 0.0
        total_gastos = float(df_gastos['monto'].sum()) if not df_gastos.empty else 0.0

        # Solo comisiones en métodos bancarios
        if not df_ventas.empty:
            ventas_bancarias = df_ventas[
                df_ventas['metodo'].str.contains("Pago|Transferencia", case=False, na=False)
            ]
        else:
            ventas_bancarias = pd.DataFrame()

        banco_perc = st.session_state.get('banco_perc', 0.5)

        comision_est = float(ventas_bancarias['monto_total'].sum() * (banco_perc / 100)) if not ventas_bancarias.empty else 0.0

        deudas = float(
            df_ventas[
                df_ventas['metodo'].str.contains("Pendiente", case=False, na=False)
            ]['monto_total'].sum()
        ) if not df_ventas.empty else 0.0

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Ingresos", f"$ {total_ventas:,.2f}")
        c2.metric("Gastos", f"$ {total_gastos:,.2f}", delta_color="inverse")
        c3.metric("Comisiones Bancarias", f"$ {comision_est:,.2f}")
        c4.metric("Cuentas por Cobrar", f"$ {deudas:,.2f}")

        utilidad = total_ventas - total_gastos - comision_est

        st.metric("Utilidad Real Estimada", f"$ {utilidad:,.2f}")

    # ---------------------------------------
    # TAB INSUMOS
    # ---------------------------------------
    with tab2:

        st.subheader("Bitácora de Movimientos de Inventario")

        if df_movs.empty:
            st.info("Aún no hay movimientos registrados.")
        else:
            st.dataframe(df_movs, use_container_width=True)

            # Exportación
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_movs.to_excel(writer, index=False, sheet_name='Movimientos')

            st.download_button(
                "📥 Descargar Movimientos (Excel)",
                buffer.getvalue(),
                "auditoria_movimientos.xlsx"
            )

    # ---------------------------------------
    # TAB GRÁFICOS
    # ---------------------------------------
    with tab3:

        st.subheader("Consumo de Insumos")

        if not df_movs.empty:

            salidas = df_movs[df_movs['Operacion'] == 'SALIDA']

            if not salidas.empty:

                resumen = salidas.groupby("Material")["Cantidad"].sum()

                st.bar_chart(resumen)

                top = resumen.sort_values(ascending=False).head(1)

                if not top.empty:
                    st.metric(
                        "Material más usado",
                        top.index[0],
                        f"{top.values[0]:.2f}"
                    )
            else:
                st.info("No hay salidas registradas aún.")
        else:
            st.info("No hay datos para graficar.")

    # ---------------------------------------
    # TAB ALERTAS
    # ---------------------------------------
    with tab4:

        st.subheader("Control de Stock")

        df_inv = st.session_state.get('df_inv', pd.DataFrame())

        if df_inv.empty:
            st.warning("Inventario vacío.")
        else:
            criticos = df_inv[df_inv['cantidad'] <= df_inv['minimo']]

            if criticos.empty:
                st.success("Niveles de inventario óptimos")
            else:
                st.error(f"⚠️ Hay {len(criticos)} productos en nivel crítico")

                for _, r in criticos.iterrows():
                    st.warning(
                        f"**{r['item']}** bajo: {r['cantidad']} {r['unidad']} "
                        f"(mín: {r['minimo']})"
                    )

# ===========================================================
# MÓDULO DE COTIZACIONES - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
elif menu == "📝 Cotizaciones":

    st.title("📝 Cotizador Profesional")

    # Recuperamos datos provenientes de CMYK u otros módulos
    datos = st.session_state.get('datos_pre_cotizacion', {})

    consumos = datos.get('consumos', {})

    datos_pre = {
        'trabajo': datos.get('trabajo', "Trabajo General"),
        'costo_base': datos.get('costo_base', 0.0),
        'unidades': datos.get('unidades', 1),
        'C': consumos.get('C', 0.0),
        'M': consumos.get('M', 0.0),
        'Y': consumos.get('Y', 0.0),
        'K': consumos.get('K', 0.0)
    }

    usa_tinta = any([datos_pre['C'], datos_pre['M'], datos_pre['Y'], datos_pre['K']])

    # ---- CLIENTE ----
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    if df_cli.empty:
        st.warning("Registra clientes primero.")
        st.stop()

    opciones = {r['nombre']: r['id'] for _, r in df_cli.iterrows()}

    cliente_sel = st.selectbox("Cliente:", opciones.keys())
    id_cliente = opciones[cliente_sel]

    unidades = st.number_input(
        "Cantidad",
        min_value=1,
        value=int(datos_pre['unidades'])
    )

    # ---- COSTOS ----
    costo_unit = st.number_input(
        "Costo unitario base ($)",
        value=float(datos_pre['costo_base'] / unidades if unidades else 0)
    )

    margen = st.slider("Margen %", 10, 300, 100)

    costo_total = costo_unit * unidades
    precio_final = costo_total * (1 + margen / 100)

    st.metric("Precio sugerido", f"$ {precio_final:.2f}")

    # ---- CONSUMOS ----
    consumos_reales = {}

    if usa_tinta:

        df_tintas = obtener_tintas_disponibles()

        if df_tintas.empty:
            st.error("No hay tintas registradas en inventario.")
            st.stop()

        opciones_tinta = {
            f"{r['item']} ({r['cantidad']} ml)": r['id']
            for _, r in df_tintas.iterrows()
        }

        st.subheader("Asignación de Tintas a Descontar")

        for color in ['C', 'M', 'Y', 'K']:
            sel = st.selectbox(f"Tinta {color}", opciones_tinta.keys(), key=color)
            consumos_reales[opciones_tinta[sel]] = datos_pre[color] * unidades

    metodo_pago = st.selectbox(
        "Método de Pago",
        ["Efectivo", "Zelle", "Pago Móvil", "Transferencia", "Pendiente"]
    )

    # =====================================================
    # 🔐 INTEGRACIÓN CON NÚCLEO CENTRAL
    # =====================================================
    if st.button("CONFIRMAR VENTA"):

        descr = datos_pre['trabajo']

        try:
            exito, msg = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_sel,
                detalle=descr,
                monto_usd=precio_final,
                metodo=metodo_pago,
                consumos=consumos_reales,
                usuario=st.session_state.get("usuario_nombre", "Sistema")
            )

            if exito:
                st.success(msg)

                # Limpiamos datos temporales de cotización
                st.session_state.pop('datos_pre_cotizacion', None)

                cargar_datos()
                st.rerun()

            else:
                st.error(msg)

        except Exception as e:
            st.error(f"Error procesando venta: {e}")



# ===========================================================
# 🛒 MÓDULO DE VENTA DIRECTA - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
if menu == "🛒 Venta Directa":

    st.title("🛒 Venta Rápida de Materiales")

    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    df_cli = st.session_state.get('df_cli', pd.DataFrame())
    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    if df_inv.empty:
        st.warning("No hay inventario cargado.")
        st.stop()

    disponibles = df_inv[df_inv['cantidad'] > 0]

    if disponibles.empty:
        st.warning("⚠️ No hay productos con stock disponible.")
        st.stop()

    with st.container(border=True):
        c1, c2 = st.columns([2, 1])
        prod_sel = c1.selectbox(
            "📦 Seleccionar Producto:",
            disponibles['item'].tolist(),
            key="venta_directa_producto"
        )

        datos = disponibles[disponibles['item'] == prod_sel].iloc[0]
        id_producto = int(datos['id'])
        stock_actual = float(datos['cantidad'])
        precio_base = float(datos['precio_usd'])
        unidad = str(datos['unidad'])
        minimo = float(datos['minimo'])

        c2.metric("Stock Disponible", f"{stock_actual:.2f} {unidad}")

    with st.form("form_venta_directa_modulo", clear_on_submit=True):
        st.subheader("Datos de la Venta")

        if not df_cli.empty:
            opciones_cli = {row['nombre']: row['id'] for _, row in df_cli.iterrows()}
            cliente_nombre = st.selectbox(
                "Cliente:",
                list(opciones_cli.keys()),
                key="venta_directa_cliente"
            )
            id_cliente = opciones_cli[cliente_nombre]
        else:
            cliente_nombre = "Consumidor Final"
            id_cliente = None
            st.info("Venta sin cliente registrado")

        c1, c2, c3 = st.columns(3)

        cantidad = c1.number_input(
            f"Cantidad ({unidad})",
            min_value=0.0,
            max_value=stock_actual,
            step=1.0,
            key="venta_directa_cantidad"
        )

        margen = c2.number_input("Margen %", value=30.0, key="venta_directa_margen")

        metodo = c3.selectbox(
            "Método de Pago",
            ["Efectivo $", "Pago Móvil (BCV)", "Transferencia (Bs)", "Zelle", "Binance", "Pendiente"],
            key="venta_directa_metodo"
        )

        usa_desc = st.checkbox("Aplicar descuento cliente fiel", key="venta_directa_check_desc")
        desc = st.number_input(
            "Descuento %",
            value=5.0 if usa_desc else 0.0,
            disabled=not usa_desc,
            key="venta_directa_desc"
        )

        st.write("Impuestos aplicables:")
        i1, i2 = st.columns(2)
        usa_iva = i1.checkbox("Aplicar IVA", key="venta_directa_iva")
        usa_banco = i2.checkbox("Comisión bancaria", value=True, key="venta_directa_banco")

        costo_material = cantidad * precio_base
        con_margen = costo_material * (1 + margen / 100)
        con_desc = con_margen * (1 - desc / 100)

        impuestos = 0.0
        if usa_iva:
            impuestos += float(st.session_state.get('iva_perc', 16))
        if usa_banco and metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            impuestos += float(st.session_state.get('banco_perc', 0.5))

        total_usd = con_desc * (1 + impuestos / 100)

        total_bs = 0.0
        if metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            total_bs = total_usd * float(st.session_state.get('tasa_bcv', 1.0))
        elif metodo == "Binance":
            total_bs = total_usd * float(st.session_state.get('tasa_binance', 1.0))

        st.divider()
        st.metric("Total a Cobrar", f"$ {total_usd:.2f}")
        if total_bs > 0:
            st.info(f"Equivalente: Bs {total_bs:,.2f}")

        submit_venta = st.form_submit_button("🚀 PROCESAR VENTA")

    if submit_venta:
        if cantidad <= 0:
            st.error("⚠️ Debes vender al menos una unidad.")
            st.stop()

        if cantidad > stock_actual:
            st.error("⚠️ No puedes vender más de lo que hay en inventario.")
            st.stop()

        consumos = {id_producto: cantidad}

        exito, mensaje = registrar_venta_global(
            id_cliente=id_cliente,
            nombre_cliente=cliente_nombre,
            detalle=f"{cantidad} {unidad} de {prod_sel}",
            monto_usd=float(total_usd),
            metodo=metodo,
            consumos=consumos,
            usuario=usuario_actual
        )

        if exito:
            st.success(mensaje)
            if stock_actual - cantidad <= minimo:
                st.warning("⚠️ Producto quedó en nivel crítico")

            st.session_state.ultimo_ticket = {
                "cliente": cliente_nombre,
                "detalle": f"{cantidad} {unidad} de {prod_sel}",
                "total": total_usd,
                "metodo": metodo,
                "usuario": usuario_actual
            }
            st.rerun()
        else:
            st.error(mensaje)

    if 'ultimo_ticket' in st.session_state:
        st.divider()
        t = st.session_state.ultimo_ticket
        with st.expander("📄 Recibo de Venta", expanded=True):
            st.code(f"""
CLIENTE: {t['cliente']}
DETALLE: {t['detalle']}
TOTAL: $ {t['total']:.2f}
MÉTODO: {t['metodo']}
USUARIO: {t.get('usuario', 'N/D')}
""")
            if st.button("Cerrar Ticket", key="cerrar_ticket_venta_directa"):
                del st.session_state.ultimo_ticket
                st.rerun()


# ===========================================================
# 🔐 NÚCLEO CENTRAL DE REGISTRO DE VENTAS DEL IMPERIO
# ===========================================================

def registrar_venta_global(
    id_cliente=None,
    nombre_cliente="Consumidor Final",
    detalle="Venta general",
    monto_usd=0.0,
    metodo="Efectivo $",
    consumos=None,
    usuario=None
):
    """
    FUNCIÓN MAESTRA DEL IMPERIO – VERSIÓN FINANCIERA PROFESIONAL
    """

    if consumos is None:
        consumos = {}

    if monto_usd <= 0:
        return False, "⚠️ El monto de la venta debe ser mayor a 0"

    if not detalle:
        return False, "⚠️ El detalle de la venta no puede estar vacío"

    if not usuario:
        usuario = st.session_state.get("usuario_nombre", "Sistema")

    conn = None
    try:
        conn = conectar()
        cursor = conn.cursor()

        conn.execute("BEGIN TRANSACTION")

        # ================================
        # VALIDAR CLIENTE
        # ================================
        if id_cliente is not None:
            existe_cli = cursor.execute(
                "SELECT id FROM clientes WHERE id = ?",
                (id_cliente,)
            ).fetchone()

            if not existe_cli:
                conn.rollback()
                return False, "❌ Cliente no encontrado"

        # ================================
        # VALIDAR STOCK Y CALCULAR COSTO
        # ================================
        costo_total_real = 0.0

        for item_id, cant in consumos.items():

            if cant <= 0:
                conn.rollback()
                return False, f"⚠️ Cantidad inválida para insumo {item_id}"

            data = cursor.execute(
                "SELECT cantidad, precio_usd, item FROM inventario WHERE id = ?",
                (item_id,)
            ).fetchone()

            if not data:
                conn.rollback()
                return False, f"❌ Insumo {item_id} no existe"

            cantidad_disponible, precio_unitario, nombre_item = data

            if cant > cantidad_disponible:
                conn.rollback()
                return False, f"⚠️ Stock insuficiente para {nombre_item}"

            # COSTO HISTÓRICO
            if precio_unitario:
                costo_total_real += float(precio_unitario) * float(cant)

        # ================================
        # CALCULAR UTILIDAD REAL
        # ================================
        costo_operativo = calcular_costo_operativo_por_dia()
        utilidad_real = float(monto_usd) - costo_total_real - costo_operativo
        margen_real = (utilidad_real / float(monto_usd) * 100) if monto_usd > 0 else 0.0

        # ================================
        # DESCONTAR INVENTARIO
        # ================================
        for item_id, cant in consumos.items():

            cursor.execute("""
                UPDATE inventario
                SET cantidad = cantidad - ?
                WHERE id = ?
            """, (cant, item_id))

            cursor.execute("""
                INSERT INTO inventario_movs
                (item_id, tipo, cantidad, motivo, usuario)
                VALUES (?, 'SALIDA', ?, ?, ?)
            """, (item_id, cant, f"Venta: {detalle}", usuario))

        # ================================
        # INSERTAR VENTA
        # ================================
        cursor.execute("""
            INSERT INTO ventas
            (cliente_id, cliente, detalle, monto_total,
             metodo, usuario,
             costo_total, utilidad, margen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            id_cliente,
            nombre_cliente,
            detalle,
            float(monto_usd),
            metodo,
            usuario,
            costo_total_real,
            utilidad_real,
            margen_real
        ))

        conn.commit()
        conn.close()

        cargar_datos()

        return True, f"✅ Venta registrada | Utilidad: ${utilidad_real:.2f} | Margen: {margen_real:.1f}%"

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass

        return False, f"❌ Error interno: {str(e)}"
































