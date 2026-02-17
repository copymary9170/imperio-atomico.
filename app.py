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

st.set_page_config(
    page_title="Imperio Atómico - ERP Pro",
    layout="wide",
    page_icon="⚛️"
)

# --- 2. MOTOR DE BASE DE DATOS ---

def conectar():
    """Conexión principal a la base de datos del Imperio."""
    conn = sqlite3.connect(
        "imperio_v2.db",
        check_same_thread=False
    )
    conn.execute(
        "PRAGMA foreign_keys = ON"
    )
    return conn

def hash_password(password: str, salt: str | None = None) -> str:
    """Genera hash PBKDF2 para almacenar contraseñas"""
    salt = salt or secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"

def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        test_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations)
        ).hex()
        return hmac.compare_digest(test_digest, digest)
    except:
        return False

def obtener_password_admin_inicial() -> str:
    """Obtiene contraseña inicial"""
    return os.getenv(
        "IMPERIO_ADMIN_PASSWORD",
        "atomica2026"
    )

# --- 3. INICIALIZACIÓN DEL SISTEMA ---

def inicializar_sistema():
    with conectar() as conn:
        c = conn.cursor()

        # CONFIGURACIÓN
        c.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                parametro TEXT PRIMARY KEY,
                valor REAL
            )
        """)

        # TASAS
        c.execute("""
            CREATE TABLE IF NOT EXISTS tasas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tasa_bcv REAL,
                tasa_binance REAL,
                fecha TEXT
            )
        """)

        # COSTOS OPERATIVOS
        c.execute("""
            CREATE TABLE IF NOT EXISTS costos_operativos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                monto_mensual REAL
            )
        """)

        # CLIENTES
        c.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                whatsapp TEXT
            )
        """)

        # USUARIOS
        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                username TEXT PRIMARY KEY,
                password TEXT,
                password_hash TEXT,
                rol TEXT,
                nombre TEXT
            )
        """)

        # INVENTARIO
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

        # MOVIMIENTOS INVENTARIO
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

        # COMPRAS
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

        # PROVEEDORES
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

        # VENTAS
        c.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                cliente TEXT,
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

        # GASTOS
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

        # CREAR ADMIN POR DEFECTO
        try:
            admin_password = obtener_password_admin_inicial()
            c.execute("""
                INSERT OR IGNORE INTO usuarios (username, password, password_hash, rol, nombre)
                VALUES (?, ?, ?, ?, ?)
            """, ("jefa", "", hash_password(admin_password), "Admin", "Dueña del Imperio"))
        except Exception as e:
            print(f"Error creando admin: {e}")

        conn.commit()

# --- 4. FUNCIONES FINANCIERAS ---

def calcular_costo_operativo_por_dia():
    with conectar() as conn:
        df = pd.read_sql("SELECT monto_mensual FROM costos_operativos", conn)
        if df.empty:
            return 0
        return df["monto_mensual"].sum() / 30

def cargar_datos():
    with conectar() as conn:
        try:
            st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario WHERE activo=1", conn)
            st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
            conf_df = pd.read_sql("SELECT * FROM configuracion", conn)
            for _, row in conf_df.iterrows():
                st.session_state[row['parametro']] = float(row['valor'])
        except:
            pass

# --- 5. LÓGICA DE ACCESO ---

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    inicializar_sistema()

def login():
    st.title("⚛️ Acceso al Imperio Atómico")
    with st.container(border=True):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar", use_container_width=True):
            with conectar() as conn:
                res = conn.execute(
                    "SELECT username, rol, nombre, password_hash FROM usuarios WHERE username=?",
                    (u,)
                ).fetchone()
                
                if res and verify_password(p, res[3]):
                    st.session_state.autenticado = True
                    st.session_state.rol = res[1]
                    st.session_state.usuario_nombre = res[2]
                    cargar_datos()
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")

if not st.session_state.autenticado:
    login()
    st.stop()

# --- 6. SIDEBAR Y DASHBOARD ---

with st.sidebar:

    t_bcv = st.session_state.get("tasa_bcv", 0.0)
t_bin = st.session_state.get("tasa_binance", 0.0)

with st.sidebar:

    ROL = st.session_state.get("rol", "")

    st.header(f"👋 {st.session_state.usuario_nombre}")

    st.info(f"🏦 BCV: {t_bcv} | 🔶 Bin: {t_bin}")

    menu = st.radio(
        "Secciones:",
        [
            "📊 Dashboard",
            "📦 Inventario",
            "💰 Ventas",
            "📉 Gastos",
            "🎨 Análisis CMYK",
            "🏗️ Activos",
            "🛠️ Otros Procesos",
            "🏁 Cierre de Caja",
            "📊 Auditoría y Métricas",
            "⚙️ Configuración"
        ]
    )

    if st.button("🚪 Cerrar Sesión", use_container_width=True):

        st.session_state.clear()

        st.rerun()

# --- 7. MÓDULOS ---
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Ejecutivo")
    with conectar() as conn:
        df_ventas = pd.read_sql("SELECT fecha, monto_total, utilidad FROM ventas", conn)
        df_gastos = pd.read_sql("SELECT fecha, monto FROM gastos", conn)
        df_inv_dash = pd.read_sql("SELECT cantidad, precio_usd, minimo FROM inventario", conn)
        
        ventas_total = df_ventas["monto_total"].sum() if not df_ventas.empty else 0
        gastos_total = df_gastos["monto"].sum() if not df_gastos.empty else 0
        utilidad_total = df_ventas["utilidad"].sum() if not df_ventas.empty else 0
        capital_inv = (df_inv_dash["cantidad"] * df_inv_dash["precio_usd"]).sum() if not df_inv_dash.empty else 0
        stock_bajo = (df_inv_dash["cantidad"] <= df_inv_dash["minimo"]).sum() if not df_inv_dash.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Ventas", f"${ventas_total:,.2f}")
        c2.metric("📉 Gastos", f"${gastos_total:,.2f}")
        c3.metric("💎 Utilidad", f"${utilidad_total:,.2f}")
        c4.metric("🚨 Stock Bajo", stock_bajo)
        
        st.metric("📦 Capital en Inventario", f"${capital_inv:,.2f}")
        if not df_ventas.empty:
            st.subheader("Ventas en el tiempo")
            df_ventas["fecha"] = pd.to_datetime(df_ventas["fecha"]).dt.date
            st.line_chart(df_ventas.groupby("fecha")["monto_total"].sum())

# ===========================================================
# 📦 MÓDULO DE INVENTARIO
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
            c3.metric("🚨 Stock Bajo", len(items_criticos), 
                      delta="Revisar" if len(items_criticos) > 0 else "OK", 
                      delta_color="inverse")
            c4.metric("🧠 Salud del Almacén", f"{salud:.0f}%")

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


    nombre_c = col_base1.text_input(
        "Nombre del Insumo"
    )


    proveedor_sel = col_base2.selectbox(
        "Proveedor",
        ["(Sin proveedor)", "➕ Nuevo proveedor"] + proveedores_existentes,
        key="inv_proveedor_compra"
    )



    proveedor = ""


    if proveedor_sel == "➕ Nuevo proveedor":

        proveedor = st.text_input(
            "Nombre del nuevo proveedor",
            key="inv_proveedor_nuevo"
        )


    elif proveedor_sel != "(Sin proveedor)":

        proveedor = proveedor_sel



    minimo_stock = st.number_input(
        "Stock mínimo",
        min_value=0.0
    )



    imprimible_cmyk = st.checkbox(
        "✅ Se puede imprimir (mostrar en módulo CMYK)",
        value=False,
        help="Marca solo los insumos que sí participan en impresión."
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

            area_por_pliego = ancho * alto
            area_total_ref = area_por_pliego * cantidad_envases
            stock_real = cantidad_envases
            unidad_final = "pliegos"
            area_por_pliego_val = area_por_pliego

            st.caption(f"Referencia: {area_por_pliego:,.2f} cm² por pliego")

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
        moneda_pago = col5.selectbox("Moneda", ["USD $", "Bs (BCV)", "Bs (Binance)"], key="inv_moneda_pago")

        col6, col7, col8 = st.columns(3)
        iva_activo = col6.checkbox(f"IVA (+{st.session_state.get('iva_perc',16)}%)")
        igtf_activo = col7.checkbox(f"IGTF (+{st.session_state.get('igtf_perc',3)}%)")
        banco_activo = col8.checkbox(f"Banco (+{st.session_state.get('banco_perc',0.5)}%)")

        delivery = st.number_input("Logística ($)", value=float(st.session_state.get("inv_delivery_default", 0.0)))

        # ------------------------------
        # BOTÓN GUARDAR
        # ------------------------------
        if st.button("💾 Guardar Compra", use_container_width=True):
            if not nombre_c:
                st.error("Debe indicar nombre del insumo.")
                st.stop()

            tasa_usada = 1.0
            if "BCV" in moneda_pago: tasa_usada = t_ref
            elif "Binance" in moneda_pago: tasa_usada = t_bin

            porc_impuestos = 0
            if iva_activo: porc_impuestos += st.session_state.get("iva_perc", 16)
            if igtf_activo: porc_impuestos += st.session_state.get("igtf_perc", 3)
            if banco_activo: porc_impuestos += st.session_state.get("banco_perc", 0.5)

            costo_total_usd = ((monto_factura / tasa_usada) * (1 + (porc_impuestos / 100))) + delivery
            costo_unitario = costo_total_usd / stock_real if stock_real > 0 else 0

            with conectar() as conn:
                cur = conn.cursor()
                
                # Gestión de Proveedor
                proveedor_id = None
                if proveedor:
                    cur.execute("SELECT id FROM proveedores WHERE nombre=?", (proveedor,))
                    prov = cur.fetchone()
                    if not prov:
                        cur.execute("INSERT INTO proveedores (nombre) VALUES (?)", (proveedor,))
                        proveedor_id = cur.lastrowid
                    else:
                        proveedor_id = prov[0]

                # Lógica de Stock Ponderado
                old = cur.execute("SELECT cantidad, precio_usd FROM inventario WHERE item=?", (nombre_c,)).fetchone()

                if old:
                    nueva_cant = old[0] + stock_real
                    precio_ponderado = ((old[0] * old[1]) + (stock_real * costo_unitario)) / nueva_cant
                    cur.execute("""
                        UPDATE inventario SET cantidad=?, unidad=?, precio_usd=?, minimo=?, imprimible_cmyk=?, area_por_pliego_cm2=?, activo=1, ultima_actualizacion=CURRENT_TIMESTAMP
                        WHERE item=?
                    """, (nueva_cant, unidad_final, precio_ponderado, minimo_stock, 1 if imprimible_cmyk else 0, area_por_pliego_val, nombre_c))
                else:
                    cur.execute("""
                        INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo, imprimible_cmyk, area_por_pliego_cm2, activo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (nombre_c, stock_real, unidad_final, costo_unitario, minimo_stock, 1 if imprimible_cmyk else 0, area_por_pliego_val))

                # Registrar Historial
                cur.execute("""
                    INSERT INTO historial_compras (item, proveedor_id, cantidad, unidad, costo_total_usd, costo_unit_usd, impuestos, delivery, tasa_usada, moneda_pago, usuario)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (nombre_c, proveedor_id, stock_real, unidad_final, costo_total_usd, costo_unitario, porc_impuestos, delivery, tasa_usada, moneda_pago, usuario_actual))

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
            st.subheader("Sweep 🧹 Corregir historial de compras")
            
            opciones_compra = {
                f"#{int(r.compra_id)} | {r.fecha} | {r.item} | {r.cantidad} {r.unidad} | ${r.costo_total_usd:.2f}": int(r.compra_id)
                for r in df_hist.itertuples(index=False)
            }
            
            compra_sel_label = st.selectbox("Selecciona la compra a corregir", list(opciones_compra.keys()))
            compra_sel_id = opciones_compra[compra_sel_label]
            compra_row = df_hist[df_hist["compra_id"] == compra_sel_id].iloc[0]
            
            st.caption("Si eliminas la compra, el sistema descuenta esa cantidad del inventario.")

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
                        cur.execute("""
                            INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario)
                            VALUES (?, 'SALIDA', ?, 'Corrección: eliminación de compra', ?)
                        """, (int(item_id), float(compra_row["cantidad"]), usuario_actual))

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
                st.caption(f"Se eliminarán {len(filas_item)} compras del historial.")

                confirmar_limpieza = st.checkbox("Confirmo que deseo borrar ese historial", key="hist_confirma_limpieza")
                if st.button("🗑 Borrar historial del insumo", type="secondary", disabled=not confirmar_limpieza):
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
                                cur.execute("""
                                    INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario)
                                    VALUES (?, 'SALIDA', ?, 'Corrección masiva', ?)
                                """, (int(item_id), float(row["cantidad"]), usuario_actual))

                        ids_borrar = [int(x) for x in filas_item["compra_id"].tolist()]
                        cur.executemany("DELETE FROM historial_compras WHERE id=?", [(i,) for i in ids_borrar])
                        conn.commit()

                    st.success(f"Se borró el historial de '{item_norm_sel}'.")
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
            st.rerun()

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
        st.dataframe(df_costos, use_container_width=True)

    with st.form("form_costos_operativos_config"):
        nombre_c = st.text_input("Nombre del Gasto")
        monto_c = st.number_input("Monto Mensual ($)", min_value=0.0)
        
        if st.form_submit_button("💾 Guardar Costo"):
            with conectar() as conn:
                conn.execute(
                    "INSERT INTO costos_operativos (nombre, monto_mensual) VALUES (?,?)",
                    (nombre_c, monto_c)
                )
                conn.commit()
            st.success("Costo operativo registrado.")
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

        df_tasas = pd.read_sql("SELECT * FROM tasas ORDER BY id DESC LIMIT 1", conn)

    tasa_bcv_actual = float(df_tasas["tasa_bcv"].iloc[0]) if not df_tasas.empty else 0.0
    tasa_binance_actual = float(df_tasas["tasa_binance"].iloc[0]) if not df_tasas.empty else 0.0

    with st.form(key="form_tasas"):
        col1, col2 = st.columns(2)
        tasa_bcv = col1.number_input("Tasa BCV", value=tasa_bcv_actual, format="%.4f")
        tasa_binance = col2.number_input("Tasa Binance", value=tasa_binance_actual, format="%.4f")
        
        if st.form_submit_button("💾 Guardar tasas", use_container_width=True):
            with conectar() as conn:
                conn.execute(
                    "INSERT INTO tasas (tasa_bcv, tasa_binance, fecha) VALUES (?, ?, datetime('now'))",
                    (tasa_bcv, tasa_binance)
                )
                conn.commit()
            st.success("Tasas actualizadas correctamente")
            st.rerun()


# ===========================================================
# 📊 RESUMEN COSTOS (Dentro de Configuración)
# ===========================================================

# 🔹 CARGAR COSTOS DESDE LA BASE DE DATOS
with conectar() as conn:

    df_costos = pd.read_sql(
        "SELECT * FROM costos_operativos",
        conn
    )


# 🔹 MOSTRAR RESUMEN

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


with st.form("form_reiniciar_sistema"):

    confirmar = st.checkbox(
        "Confirmo que deseo reinicializar el sistema"
    )

    reiniciar = st.form_submit_button(
        "🔄 Reinicializar Sistema (NO borra datos)",
        use_container_width=True
    )


if reiniciar and confirmar:

    inicializar_sistema()

    st.success("Sistema verificado correctamente")

    st.rerun()
# ===========================================================
# 10. ANALIZADOR CMYK PROFESIONAL (VERSIÓN MEJORADA 2.0)
# ===========================================================
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador Profesional de Cobertura CMYK")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:
            # Usamos el inventario como fuente de tintas
            df_tintas_db = pd.read_sql_query("SELECT * FROM inventario", conn)
            
            if 'imprimible_cmyk' in df_tintas_db.columns:
                df_impresion_db = df_tintas_db[df_tintas_db['imprimible_cmyk'].fillna(0) == 1].copy()
            else:
                df_impresion_db = df_tintas_db.copy()

            try:
                df_activos_cmyk = pd.read_sql_query("SELECT equipo, categoria, unidad FROM activos", conn)
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
    if 'df_activos_cmyk' in locals() and not df_activos_cmyk.empty:
        act = df_activos_cmyk.copy()
        mask_maquinaria = act['unidad'].fillna('').str.contains('Maquinaria', case=False)
        mask_categoria_imp = act['categoria'].fillna('').str.contains('Tinta|Impres', case=False)
        mask_equipo_imp = act['equipo'].fillna('').str.contains('Impres', case=False)
        posibles_activos = act[mask_maquinaria & (mask_categoria_imp | mask_equipo_imp)]['equipo'].dropna().tolist()
        for eq in posibles_activos:
            nombre_limpio = eq.split('] ', 1)[1] if '] ' in eq else eq
            if nombre_limpio not in impresoras_disponibles:
                impresoras_disponibles.append(nombre_limpio)

    if not df_impresion_db.empty:
        posibles = df_impresion_db[df_impresion_db['item'].str.contains("impresora", case=False, na=False)]['item'].tolist()
        for p in posibles:
            if p not in impresoras_disponibles:
                impresoras_disponibles.append(p)

    if not impresoras_disponibles:
        impresoras_disponibles = ["Impresora Principal", "Impresora Secundaria"]

    # --- SELECCIÓN DE IMPRESORA Y ARCHIVOS ---
    c_printer, c_file = st.columns([1, 2])

    with c_printer:
        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)
        impresora_aliases = [impresora_sel.lower().strip()]
        
        usar_stock_por_impresora = st.checkbox("Usar tintas solo de esta impresora", value=True)
        auto_negro_inteligente = st.checkbox("Conteo inteligente de negro (K)", value=True)

        costo_desgaste = st.number_input("Costo desgaste por página ($)", value=0.02, format="%.3f")
        ml_base_pagina = st.number_input("Consumo base ml (100% cob.)", value=0.15, format="%.3f")

        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)
        if not df_impresion_db.empty:
            tintas = df_impresion_db[df_impresion_db['item'].str.contains("tinta", case=False, na=False)]
            if usar_stock_por_impresora:
                tintas = tintas[tintas['item'].str.contains(impresora_sel.lower()[:5], case=False, na=False)]
            if not tintas.empty:
                precio_tinta_ml = tintas['precio_usd'].mean()
                st.success(f"💧 Precio tinta detectado: ${precio_tinta_ml:.4f}/ml")

        factor = st.slider("Factor General de Consumo", 1.0, 3.0, 1.5, 0.1)

    with c_file:
        archivos_multiples = st.file_uploader("Carga tus diseños", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True)

    # --- PROCESAMIENTO ---
    if archivos_multiples:
        try:
            import fitz
        except ImportError:
            fitz = None

        resultados = []
        totales_lote_cmyk = {'C': 0.0, 'M': 0.0, 'Y': 0.0, 'K': 0.0}
        total_pags = 0

        with st.spinner('🚀 Analizando cobertura real...'):
            for arc in archivos_multiples:
                try:
                    paginas_items = []
                    bytes_data = arc.read()

                    if arc.name.lower().endswith('.pdf') and fitz:
                        doc = fitz.open(stream=bytes_data, filetype="pdf")
                        for i in range(len(doc)):
                            page = doc.load_page(i)
                            pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)
                            img = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                            paginas_items.append((f"{arc.name} (P{i+1})", img))
                        doc.close()
                    else:
                        img = Image.open(io.BytesIO(bytes_data)).convert('CMYK')
                        paginas_items.append((arc.name, img))

                    for nombre, img_obj in paginas_items:
                        total_pags += 1
                        arr = np.array(img_obj)
                        
                        # Análisis de canales (C, M, Y, K)
                        chans = [arr[:, :, i] / 255.0 for i in range(4)]
                        medias = [float(np.mean(ch)) for ch in chans]

                        ml_c, ml_m, ml_y = [m * ml_base_pagina * factor for m in medias[:3]]
                        
                        # Lógica de Negro Inteligente
                        k_extra_ml = 0.0
                        if auto_negro_inteligente:
                            shadow_mask = (chans[3] > 0.45) | ((chans[0]+chans[1]+chans[2])/3.0 > 0.60)
                            k_extra_ml = ml_base_pagina * factor * (float(np.mean(shadow_mask)) * 0.15)
                        
                        ml_k = (medias[3] * ml_base_pagina * factor * 0.8) + k_extra_ml
                        consumo_total = ml_c + ml_m + ml_y + ml_k
                        costo_f = (consumo_total * precio_tinta_ml) + costo_desgaste

                        for color, val in zip(['C', 'M', 'Y', 'K'], [ml_c, ml_m, ml_y, ml_k]):
                            totales_lote_cmyk[color] += val

                        resultados.append({
                            "Archivo": nombre, "C (ml)": round(ml_c, 4), "M (ml)": round(ml_m, 4),
                            "Y (ml)": round(ml_y, 4), "K (ml)": round(ml_k, 4),
                            "Total ml": round(consumo_total, 4), "Costo $": round(costo_f, 4)
                        })
                except Exception as e:
                    st.error(f"Error analizando {arc.name}: {e}")

        # --- MOSTRAR RESULTADOS ---
        if resultados:
            st.subheader("📋 Desglose por Archivo")
            st.dataframe(pd.DataFrame(resultados), use_container_width=True, hide_index=True)

            cols = st.columns(4)
            for i, (color, ml) in enumerate(totales_lote_cmyk.items()):
                cols[i].metric(f"Total {color}", f"{ml:.3f} ml")

            total_usd = sum(r['Costo $'] for r in resultados)
            st.metric("💰 Costo Total de Producción", f"$ {total_usd:.2f}", delta=f"${total_usd/total_pags:.3f} p/pág")

            # --- VERIFICACIÓN DE STOCK ---
            st.subheader("📦 Verificación de Inventario")
            alertas = []
            alias_colores = {'C': ['cian', 'cyan'], 'M': ['magenta'], 'Y': ['amarillo', 'yellow'], 'K': ['negro', 'black']}
            
            for color, ml_necesario in totales_lote_cmyk.items():
                aliases = alias_colores[color]
                if not df_impresion_db.empty:
                    stock_item = df_impresion_db[df_impresion_db['item'].str.contains('|'.join(aliases), case=False, na=False)]
                    disponible = stock_item['cantidad'].sum() if not stock_item.empty else 0
                    if disponible < ml_necesario:
                        alertas.append(f"Falta {color}: necesitas {ml_necesario:.2f}ml y hay {disponible:.2f}ml")
            
            if alertas:
                for a in alertas: st.error(a)
            else:
                st.success("✅ Stock suficiente para producir.")

     # --- ENVÍO A COTIZACIÓN (Dentro de Análisis CMYK) ---
        if st.button("📝 ENVIAR A COTIZACIÓN", use_container_width=True):
            # Guardamos información completa para el cotizador
            st.session_state['datos_pre_cotizacion'] = {
                'trabajo': f"Impresión {impresora_sel} ({total_pags} pgs)",
                'costo_base': float(df_sim.iloc[0]['Total ($)']) if not df_sim.empty else float(total_usd_lote),
                'unidades': total_pags,
                'consumos': totales_lote_cmyk,
                'impresora': impresora_sel,
                'factor_consumo': factor,
                'factor_negro': factor_k,
                'refuerzo_negro': refuerzo_negro,
                'precio_tinta_ml': precio_tinta_ml,
                'costo_desgaste': costo_desgaste,
                'detalle_archivos': resultados
            }

            try:
                with conectar() as conn:
                    conn.execute("""
                        INSERT INTO historial_cmyk (impresora, paginas, costo)
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

# ===========================================================
# 9. MÓDULO PROFESIONAL DE ACTIVOS
# ===========================================================
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
            conn.commit()
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
                "Categoría", ["Corte", "Impresión", "Tinta", "Calor", "Mobiliario", "Mantenimiento"]
            )

            if st.form_submit_button("🚀 Guardar Activo"):
                if not nombre_eq:
                    st.error("Debe indicar un nombre.")
                elif monto_inv <= 0:
                    st.error("La inversión debe ser mayor a cero.")
                else:
                    desgaste_u = monto_inv / vida_util
                    try:
                        with conectar() as conn:
                            conn.execute("""
                                INSERT INTO activos (equipo, categoria, inversion, unidad, desgaste) 
                                VALUES (?,?,?,?,?)
                            """, (f"[{tipo_seccion[:3].upper()}] {nombre_eq}", categoria_especifica, monto_inv, tipo_seccion, desgaste_u))
                            
                            conn.execute("""
                                INSERT INTO activos_historial (activo, accion, detalle, costo)
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
                nueva_vida = c2.number_input("Vida útil (usos)", value=1000)
                nueva_cat = c3.selectbox(
                    "Categoría", ["Corte", "Impresión", "Tinta", "Calor", "Mobiliario", "Mantenimiento"]
                )

                if st.form_submit_button("💾 Guardar Cambios"):
                    nuevo_desgaste = nueva_inv / nueva_vida
                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE activos SET inversion = ?, categoria = ?, desgaste = ?
                                WHERE id = ?
                            """, (nueva_inv, nueva_cat, nuevo_desgaste, int(datos['id'])))
                            
                            conn.execute("""
                                INSERT INTO activos_historial (activo, accion, detalle, costo)
                                VALUES (?,?,?,?)
                            """, (activo_sel, "EDICIÓN", "Actualización de valores", nueva_inv))
                            conn.commit()
                        st.success("Activo actualizado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar: {e}")

    # --- VISUALIZACIÓN ---
    t1, t2, t3, t4, t5 = st.tabs(["📟 Maquinaria", "🛠️ Herramientas", "🔄 Repuestos", "📊 Resumen Global", "📜 Historial"])
    
    if not df.empty:
        with t1:
            st.dataframe(df[df['unidad'].str.contains("Maquinaria")], use_container_width=True, hide_index=True)
        with t2:
            st.dataframe(df[df['unidad'].str.contains("Herramienta")], use_container_width=True, hide_index=True)
        with t3:
            st.dataframe(df[df['unidad'].str.contains("Repuesto")], use_container_width=True, hide_index=True)
        with t4:
            c1, c2, c3 = st.columns(3)
            c1.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
            c2.metric("Activos", len(df))
            c3.metric("Desgaste Promedio", f"$ {df['desgaste'].mean():.4f}")
            st.plotly_chart(px.bar(df, x='equipo', y='inversion', color='categoria'), use_container_width=True)
        with t5:
            try:
                with conectar() as conn:
                    df_h = pd.read_sql_query("SELECT * FROM activos_historial ORDER BY fecha DESC", conn)
                st.dataframe(df_h, use_container_width=True, hide_index=True)
            except:
                st.info("No hay historial disponible.")
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
            conn.commit()
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
            cliente_nombre = col1.selectbox("Cliente:", list(opciones_cli.keys()))
            detalle_v = col2.text_input("Detalle de lo vendido:")

            col3, col4, col5 = st.columns(3)
            monto_venta = col3.number_input("Monto ($):", min_value=0.01, format="%.2f")
            metodo_pago = col4.selectbox(
                "Método:",
                ["Efectivo ($)", "Pago Móvil (BCV)", "Zelle", "Binance (USDT)", "Transferencia (Bs)", "Pendiente"]
            )

            # Lógica de conversión de moneda
            tasa_uso = t_bcv if "BCV" in metodo_pago else (t_bin if "Binance" in metodo_pago else 1.0)
            monto_bs = monto_venta * tasa_uso
            col5.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            submit_venta = st.form_submit_button("🚀 Registrar Venta")

            if submit_venta:
                if not detalle_v.strip():
                    st.error("Debes indicar el detalle de la venta.")
                else:
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
    # HISTORIAL (Sub-pestaña de Ventas)
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
        else:
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

            st.dataframe(df_fil, use_container_width=True, hide_index=True)
            st.metric("Total del periodo", f"$ {df_fil['total'].sum():.2f}")

            # --- GESTIÓN DE PENDIENTES ---
            st.subheader("Gestión de Cuentas Pendientes")
            pendientes = df_fil[df_fil['metodo'] == "Pendiente"]

            if pendientes.empty:
                st.success("No hay cuentas pendientes en este periodo.")
            else:
                for _, row in pendientes.iterrows():
                    with st.container(border=True):
                        col_p1, col_p2 = st.columns([3, 1])
                        col_p1.write(f"**{row['cliente']}** – ${row['total']:.2f}")
                        if col_p2.button(f"Pagar #{row['id']}", key=f"btn_pay_{row['id']}"):
                            try:
                                with conectar() as conn:
                                    conn.execute("""
                                        UPDATE ventas
                                        SET metodo = 'Pagado'
                                        WHERE id = ?
                                    """, (int(row['id']),))
                                    conn.commit()
                                st.success(f"Venta #{row['id']} marcada como pagada")
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
                "historial_ventas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # -----------------------------------
    # RESUMEN (Sub-pestaña de Ventas)
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
        else:
            total = df_v['monto_total'].sum()
            c1, c2, c3 = st.columns(3)

            c1.metric("Ventas Totales", f"$ {total:.2f}")
            
            por_cobrar = df_v[
                df_v['metodo'].str.contains("Pendiente", case=False, na=False)
            ]['monto_total'].sum()
            
            c2.metric("Por Cobrar", f"$ {por_cobrar:.2f}")

            top = df_v.groupby('cliente')['monto_total'].sum().reset_index()
            mejor = top.sort_values("monto_total", ascending=False).head(1)
            if not mejor.empty:
                c3.metric("Mejor Cliente", mejor.iloc[0]['cliente'])

            st.subheader("Ventas por Cliente")
            st.bar_chart(top.set_index("cliente"))

# ===========================================================
# 12. MÓDULO PROFESIONAL DE GASTOS
# ===========================================================
elif menu == "📉 Gastos":
    st.title("📉 Control Integral de Gastos")
    st.info("Registro, análisis y control de egresos del negocio")

    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede gestionar gastos.")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📝 Registrar Gasto", "📜 Historial", "📊 Resumen"])

    # -----------------------------------
    # REGISTRO DE GASTOS
    # -----------------------------------
    with tab1:
        with st.form("form_gastos_pro", clear_on_submit=True):
            col_d, col_c = st.columns([2, 1])
            desc = col_d.text_input("Descripción del Gasto", placeholder="Ej: Pago de luz, resma...").strip()
            categoria = col_c.selectbox("Categoría:", [
                "Materia Prima", "Mantenimiento de Equipos", "Servicios (Luz/Internet)", 
                "Publicidad", "Sueldos/Retiros", "Logística", "Otros"
            ])

            c1, c2, c3 = st.columns(3)
            monto_gasto = c1.number_input("Monto en Dólares ($):", min_value=0.01, format="%.2f")
            metodo_pago = c2.selectbox("Método de Pago:", [
                "Efectivo ($)", "Pago Móvil (BCV)", "Zelle", "Binance (USDT)", "Transferencia (Bs)"
            ])

            tasa_ref = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (t_bin if "Binance" in metodo_pago else 1.0)
            monto_bs = monto_gasto * tasa_ref
            c3.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            st.divider()
            if st.form_submit_button("📉 REGISTRAR EGRESO"):
                if not desc:
                    st.error("⚠️ La descripción es obligatoria.")
                else:
                    try:
                        with conectar() as conn:
                            # Asegurar existencia de tabla extra
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
                                INSERT INTO gastos (descripcion, monto, categoria, metodo) 
                                VALUES (?, ?, ?, ?)
                            """, (desc, float(monto_gasto), categoria, metodo_pago))
                            
                            gasto_id = cur.lastrowid
                            cur.execute("""
                                INSERT INTO gastos_extra (gasto_id, tasa, monto_bs, usuario)
                                VALUES (?, ?, ?, ?)
                            """, (gasto_id, float(tasa_ref), float(monto_bs), st.session_state.get("usuario_nombre", "Sistema")))
                            conn.commit()
                        
                        st.success("📉 Gasto registrado correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error al guardar el gasto: {e}")

# -----------------------------------
    # HISTORIAL DE GASTOS (Sub-pestaña de Gastos)
    # -----------------------------------
    with tab2:
        st.subheader("📋 Historial de Gastos")
        try:
            with conectar() as conn:
                df_g = pd.read_sql_query("""
                    SELECT g.id, g.fecha, g.descripcion, g.categoria, g.monto, g.metodo,
                           e.tasa, e.monto_bs, e.usuario
                    FROM gastos g
                    LEFT JOIN gastos_extra e ON g.id = e.gasto_id
                    ORDER BY g.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_g.empty:
            st.info("No hay gastos registrados aún.")
        else:
            c1, c2 = st.columns(2)
            desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="g_desde")
            hasta = c2.date_input("Hasta", date.today(), key="g_hasta")

            df_g['fecha'] = pd.to_datetime(df_g['fecha'], errors='coerce')
            df_fil = df_g[(df_g['fecha'].dt.date >= desde) & (df_g['fecha'].dt.date <= hasta)]

            busc = st.text_input("Buscar por descripción:", key="busc_gasto")
            if busc:
                df_fil = df_fil[df_fil['descripcion'].str.contains(busc, case=False, na=False)]

            st.dataframe(df_fil, use_container_width=True, hide_index=True)
            st.metric("Total del Periodo", f"$ {df_fil['monto'].sum():.2f}")

            # --- EDICIÓN Y ELIMINACIÓN ---
            st.subheader("Gestión de Gastos")
            gasto_sel = st.selectbox("Seleccionar gasto para editar/eliminar:", df_fil['descripcion'].tolist())
            datos_g = df_fil[df_fil['descripcion'] == gasto_sel].iloc[0]

            col_ed1, col_ed2 = st.columns(2)
            with col_ed1.expander("✏️ Editar Gasto"):
                nuevo_monto = st.number_input("Monto $", value=float(datos_g['monto']), format="%.2f", key="edit_g_monto")
                if st.button("💾 Guardar Cambios", key="btn_save_gasto"):
                    try:
                        with conectar() as conn:
                            conn.execute("UPDATE gastos SET monto = ? WHERE id = ?", (float(nuevo_monto), int(datos_g['id'])))
                            conn.commit()
                        st.success("Actualizado")
                        st.rerun()
                    except Exception as e: st.error(str(e))

            with col_ed2.expander("🗑️ Eliminar Gasto"):
                confirmar = st.checkbox("Confirmo que deseo eliminar este gasto", key="conf_del_g")
                if st.button("Eliminar definitivamente", key="btn_del_gasto"):
                    if confirmar:
                        try:
                            with conectar() as conn:
                                conn.execute("DELETE FROM gastos WHERE id = ?", (int(datos_g['id']),))
                                conn.commit()
                            st.warning("Gasto eliminado")
                            st.rerun()
                        except Exception as e: st.error(str(e))
                    else: st.warning("Confirma primero")

    # -----------------------------------
    # RESUMEN (Sub-pestaña de Gastos)
    # -----------------------------------
    with tab3:
        st.subheader("📊 Resumen de Egresos")
        if not df_g.empty:
            total = df_g['monto'].sum()
            c1, c2 = st.columns(2)
            c1.metric("Total Gastado", f"$ {total:.2f}")
            por_cat = df_g.groupby('categoria')['monto'].sum()
            c2.metric("Categoría Principal", por_cat.idxmax() if not por_cat.empty else "N/A")
            st.bar_chart(por_cat)
        else:
            st.info("Sin datos para analizar.")

# ===========================================================
# 13. MÓDULO PROFESIONAL DE CIERRE DE CAJA
# ===========================================================
elif menu == "🏁 Cierre de Caja":
    st.title("🏁 Cierre de Caja y Arqueo Diario")
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado.")
        st.stop()

    fecha_cierre = st.date_input("Seleccionar fecha:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    try:
        with conectar() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS cierres_caja (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT UNIQUE, 
                ingresos REAL, egresos REAL, neto REAL, usuario TEXT, creado DATETIME DEFAULT CURRENT_TIMESTAMP)""")
            df_v = pd.read_sql("SELECT * FROM ventas WHERE date(fecha) = ?", conn, params=(fecha_str,))
            df_g = pd.read_sql("SELECT * FROM gastos WHERE date(fecha) = ?", conn, params=(fecha_str,))
    except Exception as e:
        st.error(f"Error: {e}"); st.stop()

    cobradas = df_v[~df_v['metodo'].str.contains("Pendiente", case=False, na=False)] if not df_v.empty else pd.DataFrame()
    t_ingresos = float(cobradas['monto_total'].sum()) if not cobradas.empty else 0.0
    t_egresos = float(df_g['monto'].sum()) if not df_g.empty else 0.0
    balance = t_ingresos - t_egresos

    m1, m2, m3 = st.columns(3)
    m1.metric("Ingresos (Cobrados)", f"$ {t_ingresos:,.2f}")
    m2.metric("Egresos", f"$ {t_egresos:,.2f}", delta_color="inverse")
    m3.metric("Neto en Caja", f"$ {balance:,.2f}")

    if st.button("💾 Guardar Cierre del Día"):
        try:
            with conectar() as conn:
                conn.execute("INSERT OR REPLACE INTO cierres_caja (fecha, ingresos, egresos, neto, usuario) VALUES (?,?,?,?,?)",
                            (fecha_str, t_ingresos, t_egresos, balance, st.session_state.get("usuario_nombre", "Sistema")))
                conn.commit()
            st.success("✅ Cierre guardado")
        except Exception as e: st.error(str(e))

# ===========================================================
# 14. AUDITORÍA Y MÉTRICAS
# ===========================================================
elif menu == "📊 Auditoría y Métricas":
    st.title("📊 Auditoría Integral")
    try:
        with conectar() as conn:
            df_movs = pd.read_sql_query("""
                SELECT m.fecha, i.item as Material, m.tipo as Operacion, m.cantidad as Cantidad, i.unidad, m.motivo
                FROM inventario_movs m JOIN inventario i ON m.item_id = i.id ORDER BY m.fecha DESC""", conn)
            df_ventas = pd.read_sql("SELECT * FROM ventas", conn)
            df_gastos = pd.read_sql("SELECT * FROM gastos", conn)
    except Exception as e: st.error(str(e)); st.stop()

    t_fin, t_ins, t_gra = st.tabs(["💰 Finanzas", "📦 Insumos", "📈 Gráficos"])
    
    with t_fin:
        ing = df_ventas['monto_total'].sum() if not df_ventas.empty else 0
        egr = df_gastos['monto'].sum() if not df_gastos.empty else 0
        st.metric("Utilidad Bruta", f"$ {ing - egr:,.2f}", delta=f"{ing:,.2f} Ingresos")

    with t_ins:
        st.dataframe(df_movs, use_container_width=True, hide_index=True)

    with t_gra:
        if not df_movs.empty:
            resumen = df_movs[df_movs['Operacion'] == 'SALIDA'].groupby("Material")["Cantidad"].sum()
            st.bar_chart(resumen)

# ===========================================================
# 15. NÚCLEO CENTRAL DE VENTAS (FUNCIÓN)
# ===========================================================
def registrar_venta_global(id_cliente=None, nombre_cliente="Consumidor Final", detalle="Venta", monto_usd=0.0, metodo="Efectivo", consumos=None, usuario="Sistema"):
    if consumos is None: consumos = {}
    conn = conectar()
    try:
        cursor = conn.cursor()
        conn.execute("BEGIN TRANSACTION")
        
        costo_real = 0.0
        for item_id, cant in consumos.items():
            data = cursor.execute("SELECT cantidad, precio_usd, item FROM inventario WHERE id = ?", (item_id,)).fetchone()
            if not data or data[0] < cant:
                conn.rollback(); return False, f"Stock insuficiente: {data[2] if data else item_id}"
            
            costo_real += (data[1] * cant)
            cursor.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE id = ?", (cant, item_id))
            cursor.execute("INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario) VALUES (?, 'SALIDA', ?, ?, ?)",
                          (item_id, cant, f"Venta: {detalle}", usuario))

        utilidad = float(monto_usd) - costo_real
        cursor.execute("""INSERT INTO ventas (cliente_id, cliente, detalle, monto_total, metodo, usuario, costo_total, utilidad) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
                       (id_cliente, nombre_cliente, detalle, float(monto_usd), metodo, usuario, costo_real, utilidad))
        
        conn.commit()
        return True, f"✅ Venta Exitosa | Utilidad: ${utilidad:.2f}"
    except Exception as e:
        if conn: conn.rollback()
        return False, f"Error: {str(e)}"
    finally:
        if conn: conn.close()







