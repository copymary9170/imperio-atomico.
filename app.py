import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import io
import plotly.express as px
from PIL import Image
import datetime  # Importación base para fechas
import time      # Para generar los números de ticket únicos

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide", page_icon="⚛️")

# --- 2. MOTOR DE BASE DE DATOS Y FUNCIONES CRÍTICAS ---
# --- 2. MOTOR DE BASE DE DATOS Y FUNCIONES CRÍTICAS ---

def conectar():
    """Conexión principal a la base de datos del Imperio."""
    # Mantenemos tu nombre de archivo 'imperio_v2.db'
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

def inicializar_sistema():
    """Crea las tablas y configura los parámetros iniciales (Tasas, Impuestos, Usuario)."""
    conn = conectar()
    c = conn.cursor()
    tablas = [
        "CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)",
        # Tabla de inventario optimizada: id único e item único para evitar duplicados
        "CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)",
        "CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)",
        "CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)",
        "CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)",
        "CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS historial_precios (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, precio_usd REAL, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)"
    ]
    for tabla in tablas: 
        c.execute(tabla)
    
    # Usuario Maestro
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio')")
    
    # 💡 PARÁMETROS CRÍTICOS: Tasas e Impuestos (Incluye Impuesto Bancario del 10-Feb)
    config_init = [
        ('tasa_bcv', 36.50), 
        ('tasa_binance', 38.00), 
        ('costo_tinta_ml', 0.10), # Precio base editable para inflación
        ('iva_perc', 16.0),       # IVA 16%
        ('igtf_perc', 3.0),      # IGTF 3%
        ('banco_perc', 0.5),     # Impuesto del Banco 0.5% (Agregado)
        ('delivery_predet', 0.0) # Gastos logísticos base
    ]
    
    for p, v in config_init: 
        # INSERT OR IGNORE evita que se sobrescriban tus cambios manuales cada vez que abras la app
        c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))
    
    conn.commit()
    conn.close()

def cargar_datos():
    """Sincroniza la DB con la memoria de la App (session_state)."""
    try:
        conn = conectar()
        # Carga de inventario y clientes
        st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
        st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
        
        # Carga dinámica de configuración (Tasas, Impuestos, etc.)
        conf_df = pd.read_sql("SELECT * FROM configuracion", conn)
        for _, row in conf_df.iterrows():
            # Esto crea variables como st.session_state.tasa_bcv automáticamente
            st.session_state[row['parametro']] = float(row['valor'])
            
        conn.close()
    except Exception as e:
        st.error(f"⚠️ Error al sincronizar con el Imperio: {e}")
        # Aseguramos que existan dataframes vacíos para no romper la UI
        if 'df_inv' not in st.session_state: st.session_state.df_inv = pd.DataFrame()
        if 'df_cli' not in st.session_state: st.session_state.df_cli = pd.DataFrame()

def cargar_datos_seguros():
    """Recarga datos y muestra confirmación visual."""
    cargar_datos()
    st.toast("🔄 Imperio Sincronizado", icon="⚛️")

def obtener_tintas_disponibles():
    """Filtra el inventario para obtener solo consumibles de impresión (ml)."""
    if 'df_inv' in st.session_state and not st.session_state.df_inv.empty:
        df = st.session_state.df_inv
        return df[df['unidad'].str.contains('ml', case=False, na=False)]
    return pd.DataFrame()

def procesar_venta_grafica_completa(id_cliente, monto, metodo, consumos_dict):
    """Registra venta y descuenta stock (incluyendo tintas y cm2)."""
    try:
        conn = conectar()
        cursor = conn.cursor()
        # 1. Registrar Venta
        cursor.execute(
            "INSERT INTO ventas (cliente_id, monto_total, metodo) VALUES (?, ?, ?)",
            (id_cliente, monto, metodo)
        )
        # 2. Descuento de Inventario Automático
        for id_insumo, cantidad_a_descontar in consumos_dict.items():
            if cantidad_a_descontar > 0:
                cursor.execute(
                    "UPDATE inventario SET cantidad = cantidad - ? WHERE id = ?",
                    (cantidad_a_descontar, id_insumo)
                )
        conn.commit()
        conn.close()
        cargar_datos_seguros()
        return True, "✅ Venta y Stock procesados."
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    tablas = [
        "CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)",
        "CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)",
        "CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)",
        "CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)",
        # 🛡️ TABLA ACTUALIZADA CON CLIENTE (TEXTO) Y DETALLE:
        "CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, cliente TEXT, detalle TEXT, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)",
        "CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS historial_precios (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, precio_usd REAL, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)"
    ]
    for tabla in tablas: c.execute(tabla)
    
    # Verificación de seguridad: Si la tabla ya existía sin las nuevas columnas, las agregamos
    try:
        c.execute("ALTER TABLE ventas ADD COLUMN cliente TEXT")
        c.execute("ALTER TABLE ventas ADD COLUMN detalle TEXT")
    except:
        pass # Ya existen
        
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio')")
    
    config_init = [
        ('tasa_bcv', 36.50), ('tasa_binance', 38.00), ('costo_tinta_ml', 0.10),
        ('iva_perc', 16.0), ('igtf_perc', 3.0), ('banco_perc', 0.5)
    ]
    for p, v in config_init: c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))
    conn.commit()
    conn.close()
def login():
    st.title("⚛️ Acceso al Imperio Atómico")
    with st.container(border=True):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar al Sistema", use_container_width=True):
            conn = conectar()
            res = conn.execute("SELECT rol, nombre FROM usuarios WHERE username=? AND password=?", (u, p)).fetchone()
            conn.close()
            if res:
                st.session_state.autenticado = True
                st.session_state.rol = "Admin" if u == 'jefa' else res[0]
                st.session_state.usuario_nombre = res[1]
                cargar_datos()
                st.rerun()
            else: st.error("Acceso denegado")

# --- 3. CONTROL DE FLUJO ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    inicializar_sistema() # Se asegura que las tablas existan al abrir la app

if not st.session_state.autenticado:
    login()
    st.stop()

# Si llegó aquí, está autenticado. Cargamos datos si la sesión está limpia.
if 'df_inv' not in st.session_state: cargar_datos()

# Variables globales de fácil acceso para todo el código
t_bcv = st.session_state.get('tasa_bcv', 1.0)
t_bin = st.session_state.get('tasa_binance', 1.0)
ROL = st.session_state.get('rol', "Produccion")

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header(f"👋 {st.session_state.usuario_nombre}")
    
    # Mostramos las tasas actuales directamente en el sidebar
    st.info(f"🏦 BCV: {t_bcv} | 🔶 Bin: {t_bin}")
    
    opciones = [
        "📦 Inventario",           # Gestión de stock de materiales
        "🛒 Venta Directa",        # Venta de insumos con descuento de stock
        "🛠️ Otros Procesos",       # Servicios, mano de obra y trabajos especiales
        "🎨 Análisis CMYK",        # Calculadora de tintas y cm2
        "📝 Cotizaciones",         # Presupuestos
        "💰 Ventas",               # Historial detallado (quién, qué y cuánto)
        "👥 Clientes",             # Base de datos de contactos
        "📊 Dashboard",            # Gráficas de rendimiento
        "📉 Gastos",               # Registro de egresos
        "🏗️ Activos",              # Maquinarias e inversión
        "🏁 Cierre de Caja",       # Reporte final del día
        "📊 Auditoría y Métricas", # Control de gestión
        "⚙️ Configuración"         # Ajustes de Tasas, IVA, IGTF e Impuesto Bancario
    ]
    
    menu = st.radio("Secciones del Imperio:", opciones)
    
    st.divider()
    
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# --- INICIO DEL MÓDULO DE INVENTARIO COMPLETO Y BLINDADO (VERSIÓN FINAL INTEGRADA) ---
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Suministros")
    
    # 0. Sincronización con el Estado de Sesión
    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    t_ref = st.session_state.get('tasa_bcv', 36.5)
    t_bin = st.session_state.get('tasa_binance', 38.0)

    # --- 1. DASHBOARD DE INDICADORES ---
    if not df_inv.empty:
        with st.container(border=True):
            c_val, c_alert, c_salud = st.columns(3)
            v_inv = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
            c_val.metric("Capital en Stock", f"$ {v_inv:,.2f}", help=f"Bs {v_inv * t_ref:,.2f}")
            
            crit_df = df_inv[df_inv['cantidad'] <= df_inv['minimo']]
            c_alert.metric("Items Críticos", f"{len(crit_df)}", 
                         delta=f"{len(crit_df)} Reabastecer" if len(crit_df) > 0 else "OK", 
                         delta_color="inverse")
            
            salud = ((len(df_inv) - len(crit_df)) / len(df_inv)) * 100 if len(df_inv) > 0 else 0
            c_salud.write(f"**Salud del Almacén: {salud:.0f}%**")
            c_salud.progress(salud / 100)

    # --- 2. PANEL DE OPERACIONES (TABS) ---
    tabs = st.tabs(["📋 Existencias", "📥 Registrar Compra", "🧮 Calculadora", "🔧 Ajustes", "📊 Análisis"])

    with tabs[0]: # PESTAÑA: EXISTENCIAS
        if not df_inv.empty:
            c1, c2, c3 = st.columns([2, 1, 1])
            busq = c1.text_input("🔍 Filtro rápido", placeholder="Buscar por nombre...", key="f_busq")
            moneda_v = c2.selectbox("Mostrar en:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], key="f_mon")
            
            t_v = t_ref if "BCV" in moneda_v else (t_bin if "Binance" in moneda_v else 1.0)
            simbolo = "$" if "USD" in moneda_v else "Bs"
            
            df_v = df_inv.copy()
            if busq: df_v = df_v[df_v['item'].str.contains(busq, case=False)]
            if c3.checkbox("🚨 Ver solo stock bajo"): df_v = df_v[df_v['cantidad'] <= df_v['minimo']]

            df_v['Costo Unit.'] = df_v['precio_usd'] * t_v
            df_v['Total'] = df_v['cantidad'] * df_v['Costo Unit.']
            
            def style_critico(row):
                return ['background-color: rgba(255, 75, 75, 0.15)' if row.cantidad <= row.minimo else '' for _ in row]

            st.dataframe(
                df_v.style.apply(style_critico, axis=1),
                column_config={
                    "item": "Insumo", "cantidad": "Stock Actual", "unidad": "Und",
                    "Costo Unit.": st.column_config.NumberColumn(f"Costo {simbolo}", format="%.4f"),
                    "Total": st.column_config.NumberColumn(f"Subtotal {simbolo}", format="%.2f"),
                    "minimo": "Mín", "precio_usd": None, "id": None
                },
                hide_index=True, use_container_width=True
            )
        else: st.info("Inventario vacío.")

    with tabs[1]: # PESTAÑA: REGISTRO DE COMPRA (DINÁMICO)
        st.subheader("📥 Entrada de Mercancía")
        
        c_nom, c_und, c_min = st.columns([2, 1, 1])
        nombre_c = c_nom.text_input("Nombre del Material").strip().upper()
        # Unidades simplificadas a medibles
        und_c = c_und.selectbox("Unidad de Medida", ["Unidad", "Área (cm/m)", "Líquido (ml/L)", "Peso (gr/kg)"])
        min_c = c_min.number_input("Alerta Stock Mínimo", value=5.0)

        # Lógica de conversión dinámica mejorada
        mult_stock = 1.0
        und_final = "Unidad"

        if und_c == "Área (cm/m)":
            with st.container(border=True):
                m1, m2 = st.columns(2)
                ancho_c = m1.number_input("Ancho (cm)", min_value=0.1, value=21.0)
                alto_c = m2.number_input("Alto/Largo (cm)", min_value=0.1, value=29.7)
                mult_stock = ancho_c * alto_c
                und_final = "cm2"
        elif und_c == "Líquido (ml/L)":
            with st.container(border=True):
                mult_stock = st.number_input("Capacidad por envase (ml)", min_value=1.0, value=100.0)
                und_final = "ml"
        elif und_c == "Peso (gr/kg)":
            with st.container(border=True):
                mult_stock = st.number_input("Peso por envase (gramos)", min_value=1.0, value=1000.0)
                und_final = "gr"

        with st.form("form_compra_atoma", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            monto_neto = f1.number_input("Monto Factura", min_value=0.0)
            mon_pago = f2.selectbox("Moneda de Pago", ["USD $", "Bs (BCV)", "Bs (Binance)"])
            cant_recibida = f3.number_input("Cantidad de Envases/Unidades Compradas", min_value=0.001)

            st.markdown("⚖️ **Impuestos y Comisiones**")
            v_iva = st.session_state.get('iva_perc', 16.0)
            v_igtf = st.session_state.get('igtf_perc', 3.0)
            v_ban = st.session_state.get('banco_perc', 0.5) 
            
            i1, i2, i3 = st.columns(3)
            usa_iva, usa_igtf, usa_ban = i1.checkbox(f"IVA (+{v_iva}%)"), i2.checkbox(f"IGTF (+{v_igtf}%)"), i3.checkbox(f"Banco (+{v_ban}%)")

            delivery = st.number_input("Gastos Logística (Delivery/Envío/Pasajes) $", value=0.0)

            if st.form_submit_button("💾 GUARDAR COMPRA EN INVENTARIO"):
                if nombre_c and cant_recibida > 0:
                    t_p = t_ref if "BCV" in mon_pago else (t_bin if "Binance" in mon_pago else 1.0)
                    p_i = (v_iva if usa_iva else 0) + (v_igtf if usa_igtf else 0) + (v_ban if usa_ban else 0)
                    
                    costo_usd_total = (monto_neto / t_p) * (1 + (p_i/100)) + delivery
                    stock_ingreso = cant_recibida * mult_stock
                    costo_u = costo_usd_total / stock_ingreso

                    conn = conectar()
                    cursor = conn.cursor()
                    old = cursor.execute("SELECT cantidad, precio_usd FROM inventario WHERE item=?", (nombre_c,)).fetchone()
                    p_ponderado = ((old[0]*old[1]) + (stock_ingreso*costo_u)) / (old[0]+stock_ingreso) if old else costo_u
                    
                    cursor.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                                   VALUES (?,?,?,?,?) ON CONFLICT(item) DO UPDATE SET 
                                   cantidad=cantidad+?, unidad=?, precio_usd=?, minimo=?""", 
                                   (nombre_c, stock_ingreso, und_final, p_ponderado, min_c, stock_ingreso, und_final, p_ponderado, min_c))
                    conn.commit(); conn.close(); cargar_datos_seguros(); st.rerun()

    with tabs[2]: # PESTAÑA: CALCULADORA (INTEGRADA)
        st.subheader("🧮 Calculadora de Costos por Trabajo")
        if 'calc_list' not in st.session_state: 
            st.session_state.calc_list = []
        
        item_sel = st.selectbox("Seleccionar Insumo", df_inv['item'].tolist() if not df_inv.empty else [], key="sel_calc")
        
        if not df_inv.empty:
            datos_i = df_inv[df_inv['item'] == item_sel].iloc[0]
            if datos_i['unidad'] == "cm2":
                c1, c2 = st.columns(2)
                an_u = c1.number_input("Ancho a usar (cm)", min_value=0.0, key="an_c")
                al_u = c2.number_input("Alto a usar (cm)", min_value=0.0, key="al_c")
                uso_f = an_u * al_u
            else:
                uso_f = st.number_input(f"Cantidad a usar ({datos_i['unidad']})", min_value=0.0, key="ca_c")

            if st.button("➕ Agregar al Cálculo"):
                costo_c = uso_f * datos_i['precio_usd']
                st.session_state.calc_list.append({"Item": item_sel, "Uso": f"{uso_f:.2f} {datos_i['unidad']}", "Costo $": round(costo_c, 4)})

        if st.session_state.calc_list:
            df_calc = pd.DataFrame(st.session_state.calc_list)
            st.table(df_calc)
            total_b = df_calc["Costo $"].sum()
            st.metric("Subtotal de Materiales", f"${total_b:.4f}")
            margen = st.slider("Margen de Ganancia %", 0, 500, 100)
            st.subheader(f"💰 Precio Sugerido: ${total_b * (1 + margen/100):.2f}")
            if st.button("🗑️ Reiniciar"): 
                st.session_state.calc_list = []
                st.rerun()

    with tabs[3]: # PESTAÑA: AJUSTES
        st.subheader("🔧 Corrección Manual")
        if not df_inv.empty:
            with st.form("form_ajuste"):
                col_it, col_ca, col_pr = st.columns([2, 1, 1])
                it_aj = col_it.selectbox("Seleccionar Insumo", df_inv['item'].tolist())
                val_actual = df_inv[df_inv['item'] == it_aj].iloc[0]
                
                cant_r = col_ca.number_input("Cantidad Real", min_value=0.0, value=float(val_actual['cantidad']))
                prec_r = col_pr.number_input("Precio USD Unit.", min_value=0.0, value=float(val_actual['precio_usd']), format="%.4f")
                
                if st.form_submit_button("🔨 ACTUALIZAR DATOS"):
                    conn = conectar()
                    conn.execute("UPDATE inventario SET cantidad=?, precio_usd=? WHERE item=?", (cant_r, prec_r, it_aj))
                    conn.commit(); conn.close(); cargar_datos(); st.rerun()
            
            st.divider()
            st.subheader("⚠️ Zona de Peligro")
            with st.expander("Haz clic aquí para eliminar un insumo"):
                it_del = st.selectbox("Insumo a eliminar", df_inv['item'].tolist(), key="del_sel")
                confirmar = st.checkbox(f"Confirmo que deseo borrar '{it_del}'")
                if st.button("❌ ELIMINAR PERMANENTEMENTE"):
                    if confirmar:
                        conn = conectar()
                        conn.execute("DELETE FROM inventario WHERE item=?", (it_del,))
                        conn.commit(); conn.close(); cargar_datos(); st.rerun()
                    else:
                        st.warning("Confirma la casilla para borrar.")
        else:
            st.info("No hay insumos para ajustar.")

    with tabs[4]: # PESTAÑA: ANÁLISIS
        st.subheader("📊 Reporte de Almacén")
        if not df_inv.empty:
            df_inv['Capital USD'] = df_inv['cantidad'] * df_inv['precio_usd']
            fig = px.pie(df_inv, values='Capital USD', names='item', 
                         title="Distribución de Valor en Inventario",
                         hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig, use_container_width=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_inv.to_excel(writer, index=False, sheet_name='Inventario')
            
            st.download_button(
                label="📥 Descargar Reporte Completo (Excel)",
                data=buffer.getvalue(),
                file_name="inventario_atoma.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        elif menu == "📊 Dashboard":
    st.title("📊 Panel de Control Imperio")

    conn = conectar()
    # Cargamos datos con fechas parseadas
    df_ventas = pd.read_sql("SELECT * FROM ventas", conn, parse_dates=['fecha'])
    df_gastos = pd.read_sql("SELECT * FROM gastos", conn, parse_dates=['fecha'])
    df_inv = pd.read_sql("SELECT * FROM inventario", conn) # Cargamos inventario para alertas
    conn.close()

    # --- 🚨 SECCIÓN DE ALERTAS CRÍTICAS (NUEVO) ---
    # Esto aparecerá solo si hay productos por debajo del mínimo
    items_criticos = df_inv[df_inv['cantidad'] <= df_inv['minimo']]
    if not items_criticos.empty:
        with st.container(border=True):
            st.error(f"⚠️ **ATENCIÓN:** Tienes {len(items_criticos)} productos en nivel crítico.")
            cols = st.columns(len(items_criticos) if len(items_criticos) <= 3 else 3)
            for i, (_, row) in enumerate(items_criticos.head(3).iterrows()):
                cols[i % 3].warning(f"**{row['item']}**\n\nQuedan: {row['cantidad']} {row['unidad']}")
    
    st.divider()

    # --- MÉTRICAS PRINCIPALES ---
    ingresos = df_ventas['monto_total'].sum() if not df_ventas.empty else 0
    egresos = df_gastos['monto'].sum() if not df_gastos.empty else 0
    balance = ingresos - egresos
    
    # Cálculo de deudas pendientes (NUEVO)
    deudas_pendientes = df_ventas[df_ventas['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)]['monto_total'].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos Totales", f"$ {ingresos:,.2f}")
    c2.metric("Egresos Totales", f"$ {egresos:,.2f}", delta=f"-{egresos:,.2f}", delta_color="inverse")
    c3.metric("Utilidad Neta", f"$ {balance:,.2f}", delta=f"{(balance/ingresos*100 if ingresos>0 else 0):.1f}% Margen")
    c4.metric("Por Cobrar (Deudas)", f"$ {deudas_pendientes:,.2f}", delta="Pendiente", delta_color="off")

    st.divider()

    # --- GRÁFICOS ---
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("📈 Tendencia de Ventas ($)")
        if not df_ventas.empty:
            df_ventas['fecha_dia'] = df_ventas['fecha'].dt.date
            ventas_diarias = df_ventas.groupby('fecha_dia')['monto_total'].sum()
            st.line_chart(ventas_diarias)
        else:
            st.info("No hay datos de ventas para graficar.")

    with col_g2:
        st.subheader("💳 Ventas por Método")
        if not df_ventas.empty:
            # Mostramos cuánto dinero entra por cada vía
            metodos = df_ventas.groupby('metodo')['monto_total'].sum()
            st.bar_chart(metodos)
        else:
            st.info("Sin datos de métodos de pago.")

    # --- ANALÍTICA DE IMPUESTOS Y COMISIONES (NUEVO - Instrucción 10-02) ---
    with st.expander("🏦 Desglose de Impuestos y Comisiones Estimados"):
        # Calculamos el 0.5% de banco que definiste
        comision_banco = ingresos * (st.session_state.get('banco_perc', 0.5) / 100)
        iva_estimado = ingresos * (st.session_state.get('iva_perc', 16) / 100)
        
        i1, i2 = st.columns(2)
        i1.write(f"🔹 **Comisión Bancaria (0.5%):** ${comision_banco:,.2f}")
        i2.write(f"🔹 **IVA Estimado (16%):** ${iva_estimado:,.2f}")
        st.caption("Nota: Estos valores son calculados sobre el ingreso bruto total.")

    # --- TABLA DE ÚLTIMOS MOVIMIENTOS ---
    st.divider()
    st.subheader("📑 Últimos Movimientos")
    
    tab_v, tab_g, tab_d = st.tabs(["Últimas Ventas", "Últimos Gastos", "🛑 Deudas por Cobrar"])
    
    with tab_v:
        if not df_ventas.empty:
            st.dataframe(df_ventas.sort_values('fecha', ascending=False).head(10), use_container_width=True)
    
    with tab_g:
        if not df_gastos.empty:
            st.dataframe(df_gastos.sort_values('fecha', ascending=False).head(10), use_container_width=True)

    with tab_d:
        # Filtrado rápido de clientes que deben (NUEVO)
        if not df_ventas.empty:
            deudores = df_ventas[df_ventas['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)]
            if not deudores.empty:
                st.dataframe(deudores[['fecha', 'cliente', 'detalle', 'monto_total']], use_container_width=True)
            else:
                st.success("No hay deudas pendientes actualmente.")
elif menu == "⚙️ Configuración":

    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden cambiar tasas y costos.")
        st.stop()

    st.title("⚙️ Configuración del Sistema")
    st.info("💡 Estos valores afectan globalmente a las cotizaciones, inventario y reportes financieros.")

    conn = conectar()
    # Cargamos la configuración actual
    conf_df = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')

    with st.form("config_general"):
        st.subheader("💵 Tasas de Cambio (Actualización Diaria)")
        c1, c2 = st.columns(2)
        nueva_bcv = c1.number_input("Tasa BCV (Bs/$)", 
                                    value=float(conf_df.loc['tasa_bcv', 'valor']), 
                                    format="%.2f", help="Usada para pagos en bolívares de cuentas nacionales.")
        nueva_bin = c2.number_input("Tasa Binance (Bs/$)", 
                                    value=float(conf_df.loc['tasa_binance', 'valor']), 
                                    format="%.2f", help="Usada para pagos mediante USDT o mercado paralelo.")

        st.divider()

        st.subheader("🎨 Costos Operativos Base")
        # El costo de la tinta es vital para el análisis CMYK
        costo_tinta = st.number_input(
            "Costo de Tinta por ml ($)", 
            value=float(conf_df.loc['costo_tinta_ml', 'valor']), 
            format="%.4f", step=0.0001
        )

        st.divider()

        st.subheader("🛡️ Impuestos y Comisiones")
        st.caption("Define los porcentajes decimales (Ej: 0.16 para 16%)")
        c3, c4, c5 = st.columns(3)

        n_iva = c3.number_input("IVA (16% = 0.16)", value=float(conf_df.loc['iva_perc', 'valor']), format="%.2f")
        n_igtf = c4.number_input("IGTF (3% = 0.03)", value=float(conf_df.loc['igtf_perc', 'valor']), format="%.2f")
        n_banco = c5.number_input("Comisión Bancaria (Punto/Transf)", value=float(conf_df.loc['banco_perc', 'valor']), format="%.3f")

        st.divider()
        
        # Botón de guardado destacado
        if st.form_submit_button("💾 GUARDAR CAMBIOS ATÓMICOS", use_container_width=True):
            try:
                cur = conn.cursor()
                actualizaciones = [
                    ('tasa_bcv', nueva_bcv),
                    ('tasa_binance', nueva_bin),
                    ('costo_tinta_ml', costo_tinta),
                    ('iva_perc', n_iva),
                    ('igtf_perc', n_igtf),
                    ('banco_perc', n_banco)
                ]

                for param, val in actualizaciones:
                    cur.execute("UPDATE configuracion SET valor = ? WHERE parametro = ?", (val, param))

                conn.commit()
                
                # ACTUALIZACIÓN INMEDIATA DEL STATE
                st.session_state.tasa_bcv = nueva_bcv
                st.session_state.tasa_binance = nueva_bin
                st.session_state.costo_tinta_ml = costo_tinta
                
                st.success("✅ ¡Configuración actualizada en todo el Imperio!")
                st.balloons() # Un pequeño toque de éxito
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    conn.close()

# --- 8. LÓGICA DE CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")

    # --- BUSCADOR SEGURO ---
    busqueda = st.text_input("🔍 Buscar cliente por nombre...", placeholder="Escribe aquí para filtrar...")

    # --- FORMULARIO DE REGISTRO ---
    with st.expander("➕ Registrar Nuevo Cliente", expanded=not busqueda):
        with st.form("form_clientes"):
            col1, col2 = st.columns(2)
            nombre_cli = col1.text_input("Nombre del Cliente o Negocio").strip()
            whatsapp_cli = col2.text_input("WhatsApp (Ej: 04121234567)").strip()

            if st.form_submit_button("✅ Guardar en Directorio"):
                if nombre_cli:
                    # Limpieza simple del número: quitar espacios o guiones
                    wa_limpio = "".join(filter(str.isdigit, whatsapp_cli))
                    
                    conn = conectar()
                    try:
                        conn.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nombre_cli, wa_limpio))
                        conn.commit()
                        st.success(f"✅ {nombre_cli} ha sido registrado.")
                        cargar_datos_seguros()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("⚠️ El nombre del cliente es obligatorio.")

    # --- LISTADO Y ACCIONES ---
    st.divider()
    conn = conectar()
    # Búsqueda segura usando parámetros para evitar errores de SQL
    query = "SELECT id, nombre, whatsapp FROM clientes WHERE nombre LIKE ?"
    df_clis = pd.read_sql_query(query, conn, params=(f'%{busqueda}%',))
    conn.close()

    if not df_clis.empty:
        st.subheader(f"📋 Directorio ({len(df_clis)} clientes)")
        
        # Presentación mejorada con botón de WhatsApp
        for index, row in df_clis.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.write(f"**{row['nombre']}**")
                c2.write(f"📞 {row['whatsapp']}")
                
                # Crear link de WhatsApp API
                if row['whatsapp']:
                    # Si el número no tiene código de país, asumimos Venezuela (58)
                    wa_num = row['whatsapp']
                    if not wa_num.startswith('58'):
                        wa_num = '58' + wa_num.lstrip('0')
                    
                    link_wa = f"https://wa.me/{wa_num}"
                    c3.link_button("💬 Chat", link_wa)
                
                st.divider()
    else:
        st.info("No hay clientes que coincidan con la búsqueda.")


# --- 10. ANALIZADOR MASIVO DE COBERTURA CMYK (DETALLADO) ---
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador de Cobertura y Costos Reales")

    df_tintas_db = obtener_tintas_disponibles()
    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, desgaste FROM activos", conn)
    conn.close()

    impresoras_disponibles = [
        e['equipo'] for e in df_act_db.to_dict('records')
        if e['categoria'] == "Impresora (Gasta Tinta)"
    ]

    if not impresoras_disponibles:
        st.warning("⚠️ Registra una Impresora en el módulo de 'Activos' para continuar.")
        st.stop()

    c_printer, c_file = st.columns([1, 2])

    with c_printer:
        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)
        datos_imp = next((e for e in df_act_db.to_dict('records') if e['equipo'] == impresora_sel), None)
        costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)
        if not df_tintas_db.empty:
            mask = df_tintas_db['item'].str.contains(impresora_sel, case=False, na=False)
            tintas_especificas = df_tintas_db[mask]
            if not tintas_especificas.empty:
                precio_tinta_ml = tintas_especificas['precio_usd'].mean()
                st.success(f"✅ Precio Ref: ${precio_tinta_ml:.4f}/ml")

    with c_file:
        archivos_multiples = st.file_uploader("Carga tus diseños", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if archivos_multiples:
        import fitz  
        resultados = []
        # Diccionario para acumular el consumo total del lote por color
        totales_lote_cmyk = {'C': 0.0, 'M': 0.0, 'Y': 0.0, 'K': 0.0}
        total_pags = 0

        with st.spinner('🚀 Analizando canales de color...'):
            for arc in archivos_multiples:
                try:
                    paginas_items = []
                    bytes_data = arc.read()
                    
                    if arc.name.lower().endswith('.pdf'):
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
                        
                        # 1. Obtener la media de cada canal (0 a 1)
                        c_media, m_media, y_media, k_media = [np.mean(arr[:, :, i]) / 255 for i in range(4)]
                        
                        # 2. Aplicar multiplicadores de eficiencia por máquina
                        n_low = impresora_sel.lower()
                        multi = 2.5 if "j210" in n_low else (1.8 if "subli" in n_low else 1.2)
                        
                        # 3. Calcular ML individuales (Base 0.15ml por cobertura 100% en A4)
                        ml_c = c_media * 0.15 * multi
                        ml_m = m_media * 0.15 * multi
                        ml_y = y_media * 0.15 * multi
                        ml_k = k_media * 0.15 * multi
                        
                        consumo_total_f = ml_c + ml_m + ml_y + ml_k
                        costo_f = (consumo_total_f * precio_tinta_ml) + costo_desgaste
                        
                        # Acumular para el gran total
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
                            "Total ml": round(consumo_total_f, 4),
                            "Costo $": round(costo_f, 4)
                        })
                except Exception as e:
                    st.error(f"Error en {arc.name}: {e}")

        if resultados:
            # Mostrar tabla detallada
            st.subheader("📋 Desglose por Página/Imagen")
            st.dataframe(pd.DataFrame(resultados), use_container_width=True, hide_index=True)

            # Resumen de consumo de tintas
            st.subheader("🧪 Consumo Total de Tintas (Lote)")
            col_c, col_m, col_y, col_k = st.columns(4)
            col_c.metric("Cian", f"{totales_lote_cmyk['C']:.3f} ml")
            col_m.metric("Magenta", f"{totales_lote_cmyk['M']:.3f} ml")
            col_y.metric("Amarillo", f"{totales_lote_cmyk['Y']:.3f} ml")
            col_k.metric("Negro", f"{totales_lote_cmyk['K']:.3f} ml")

            st.divider()
            total_usd_lote = sum(r['Costo $'] for r in resultados)
            st.metric("💰 Costo Total de Producción", f"$ {total_usd_lote:.2f}")

            if st.button("📝 ENVIAR A COTIZACIÓN", use_container_width=True):
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Prod. {impresora_sel} ({total_pags} pgs)",
                    'costo_base': total_usd_lote,
                    'unidades': total_pags,
                    'consumos': totales_lote_cmyk # Guardamos el desglose para descontar inventario luego
                }
                st.success("✅ Datos enviados. Ahora ve al menú de Cotizaciones.")
# --- 9. LÓGICA DE ACTIVOS CATEGORIZADOS (MAQUINARIA, HERRAMIENTAS, REPUESTOS) ---
elif menu == "🏗️ Activos":

    if ROL != "Admin":
        st.error("🚫 Acceso Denegado.")
        st.stop()

    st.title("🏗️ Gestión de Activos del Imperio")
    
    # --- 1. REGISTRO CATEGORIZADO ---
    with st.expander("➕ Registrar Nuevo Activo"):
        with st.form("form_activos_pro"):
            c1, c2 = st.columns(2)
            nombre_eq = c1.text_input("Nombre del Activo (Ej: Cameo 5, Prensa, Cabezal)")
            
            # SECCIÓN DE CATEGORÍA DETERMINANTE
            tipo_seccion = c2.selectbox("Tipo de Activo", [
                "Maquinaria (Equipos Grandes)", 
                "Herramienta Manual (Uso diario)", 
                "Repuesto Crítico (Stock de seguridad)"
            ])

            col_m1, col_m2, col_m3 = st.columns(3)
            monto_inv = col_m1.number_input("Inversión ($)", min_value=0.0)
            vida_util = col_m2.number_input("Vida Útil (Usos)", min_value=1, value=1000)
            categoria_especifica = col_m3.selectbox("Categoría", ["Corte", "Impresión", "Calor", "Mobiliario", "Mantenimiento"])

            if st.form_submit_button("🚀 Guardar en Sección"):
                if nombre_eq and monto_inv > 0:
                    desgaste_u = monto_inv / vida_util
                    conn = conectar()
                    conn.execute(
                        "INSERT INTO activos (equipo, categoria, inversion, unidad, desgaste) VALUES (?,?,?,?,?)",
                        (f"[{tipo_seccion[:3].upper()}] {nombre_eq}", categoria_especifica, monto_inv, tipo_seccion, desgaste_u)
                    )
                    conn.commit(); conn.close()
                    st.success(f"✅ Registrado en {tipo_seccion}")
                    st.rerun()

    # --- 2. VISUALIZACIÓN POR SECCIONES (TABS) ---
    st.divider()
    t1, t2, t3, t4 = st.tabs(["📟 Maquinaria", "🛠️ Herramientas", "🔄 Repuestos", "📊 Resumen Global"])

    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM activos", conn)
    conn.close()

    if not df.empty:
        with t1:
            st.subheader("Equipos y Maquinaria Principal")
            df_maq = df[df['unidad'].str.contains("Maquinaria")]
            st.dataframe(df_maq[['equipo', 'categoria', 'inversion', 'desgaste']], use_container_width=True, hide_index=True)

        with t2:
            st.subheader("Herramientas Manuales y Accesorios")
            df_her = df[df['unidad'].str.contains("Herramienta")]
            st.dataframe(df_her[['equipo', 'categoria', 'inversion', 'desgaste']], use_container_width=True, hide_index=True)

        with t3:
            st.subheader("Repuestos y Componentes Críticos")
            df_rep = df[df['unidad'].str.contains("Repuesto")]
            st.dataframe(df_rep[['equipo', 'categoria', 'inversion', 'desgaste']], use_container_width=True, hide_index=True)

        with t4:
            c_inv, c_des = st.columns(2)
            c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
            c_des.metric("Equipos Registrados", len(df))
            
            # Gráfico de distribución
            import plotly.express as px
            fig = px.bar(df, x='equipo', y='inversion', color='categoria', title="Valor por Activo")
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No hay activos registrados aún.")
# --- 11. OTROS PROCESOS (LAMINADO, CORTE, PLANCHADO) ---
elif menu == "🛠️ Otros Procesos":
    st.title("🛠️ Calculadora de Procesos Especiales")
    st.info("Calcula el costo de desgaste para procesos que no usan tinta (ej. Guillotina, Plotter de Corte, Planchas).")

    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, unidad, desgaste FROM activos", conn)
    conn.close()

    # Filtramos para no mostrar impresoras aquí (eso va en CMYK)
    otros_equipos = df_act_db[df_act_db['categoria'] != "Impresora (Gasta Tinta)"].to_dict('records')

    if otros_equipos:
        nombres_eq = [e['equipo'] for e in otros_equipos]
        
        with st.container(border=True):
            c1, c2 = st.columns(2)
            eq_sel = c1.selectbox("Selecciona el Proceso/Equipo:", nombres_eq)
            
            # Buscamos los datos del equipo seleccionado
            datos_eq = next(e for e in otros_equipos if e['equipo'] == eq_sel)
            
            cantidad = c2.number_input(f"Cantidad de {datos_eq['unidad']}:", min_value=1, value=1)
            
            costo_unitario = datos_eq['desgaste']
            costo_total = costo_unitario * cantidad
            
            st.divider()
            col_res1, col_res2 = st.columns(2)
            col_res1.metric("Costo Unitario", f"$ {costo_unitario:.4f}")
            col_res2.metric("Costo Total de Desgaste", f"$ {costo_total:.2f}")

        # BOTÓN PARA VINCULAR CON COTIZACIÓN
        if st.button("➕ Añadir a sesión de Cotización", use_container_width=True):
            # Si ya hay algo en la sesión, lo sumamos, si no, lo creamos
            if 'datos_pre_cotizacion' not in st.session_state:
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Proceso: {eq_sel}",
                    'costo_base': costo_total,
                    'unidades': cantidad,
                    'es_proceso_extra': True
                }
            else:
                # Sumamos el costo al trabajo que ya viene del CMYK
                st.session_state['datos_pre_cotizacion']['costo_base'] += costo_total
                st.session_state['datos_pre_cotizacion']['trabajo'] += f" + {eq_sel}"
            
            st.success(f"✅ Se han sumado ${costo_total:.2f} a la cotización actual.")
            st.toast("Costo de proceso añadido")

    else:
        st.warning("⚠️ No hay equipos de 'Maquinaria' o 'Herramientas' registrados en el módulo de Activos.")
        if st.button("Ir a Activos para registrar"):
            st.session_state.menu = "🏗️ Activos" # Intento de redirección
            st.rerun()

# --- 7. MÓDULO DE VENTAS (HISTORIAL Y REGISTRO) ---
elif menu == "💰 Ventas":
    st.title("💰 Historial y Registro de Ventas")
    
    # Pestañas para organizar: una para registrar y otra para ver todo el historial
    tab1, tab2 = st.tabs(["📝 Registrar Venta Manual", "📜 Historial Completo"])

    with tab1:
        if st.session_state.df_cli.empty:
            st.warning("⚠️ No hay clientes registrados. Ve al menú '👥 Clientes' primero.")
        else:
            with st.form("venta_manual", clear_on_submit=True):
                st.subheader("📝 Detalles de la Transacción")
                
                # Selector de cliente
                opciones_cli = {row['nombre']: row['id'] for _, row in st.session_state.df_cli.iterrows()}
                cliente_nombre = st.selectbox("Seleccionar Cliente:", options=list(opciones_cli.keys()))
                
                # NUEVO: Campo de Detalle para saber qué se vendió
                detalle_v = st.text_area("¿Qué se vendió? (Detalle)", placeholder="Ej: 2 Impresiones Banner 2x1m / 3 Tintas Cyan")
                
                c1, c2 = st.columns(2)
                monto_venta = c1.number_input("Monto Total ($):", min_value=0.01, format="%.2f", step=0.5)
                metodo_pago = c2.selectbox("Método de Pago:", [
                    "Efectivo ($)", "Pago Móvil (BCV)", "Zelle", "Binance (USDT)", "Transferencia (Bs)"
                ])

                st.divider()
                tasa_momento = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (t_bin if "Binance" in metodo_pago else 1.0)
                if tasa_momento > 1.0:
                    st.caption(f"💡 El cliente debe pagar aproximadamente: **Bs {(monto_venta * tasa_momento):,.2f}**")

                if st.form_submit_button("🚀 REGISTRAR VENTA"):
                    cliente_id = opciones_cli[cliente_nombre]
                    conn = conectar()
                    try:
                        c = conn.cursor()
                        # Insertamos incluyendo los nuevos campos: cliente (nombre) y detalle
                        c.execute("""
                            INSERT INTO ventas (cliente_id, cliente, detalle, monto_total, metodo) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (cliente_id, cliente_nombre, detalle_v, monto_venta, metodo_pago))
                        
                        conn.commit()
                        st.success(f"✅ Venta registrada a {cliente_nombre}")
                        st.balloons()
                        st.rerun() # Para que se actualice el historial en la otra pestaña
                    except Exception as e:
                        st.error(f"❌ Error al guardar: {e}")
                    finally:
                        conn.close()

    with tab2:
        st.subheader("📂 Buscador de Ventas")
        
        # Carga de datos completa
        conn = conectar()
        # Traemos todos los datos relevantes
        df_historial = pd.read_sql_query("""
            SELECT fecha, cliente, detalle, monto_total as 'Monto ($)', metodo as 'Método'
            FROM ventas 
            ORDER BY fecha DESC
        """, conn)
        conn.close()

        if not df_historial.empty:
            # Buscador dinámico por Cliente o por Producto
            busc = st.text_input("🔍 Buscar por Cliente o por Detalle del producto:")
            
            if busc:
                # Filtra si el texto está en el nombre del cliente O en el detalle del producto
                df_historial = df_historial[
                    df_historial['cliente'].str.contains(busc, case=False, na=False) | 
                    df_historial['detalle'].str.contains(busc, case=False, na=False)
                ]

            # Mostramos la tabla interactiva
            st.dataframe(
                df_historial,
                column_config={
                    "fecha": "Fecha",
                    "cliente": "Cliente",
                    "detalle": "Lo vendido (Items)",
                    "Monto ($)": st.column_config.NumberColumn("Total $", format="$ %.2f"),
                    "Método": "Pago"
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Resumen de lo filtrado
            st.metric("Total en Ventas (Filtro actual)", f"$ {df_historial['Monto ($)'].sum():.2f}")
        else:
            st.info("Aún no hay ventas registradas en el historial.")

# --- 12. MÓDULO DE GASTOS ---
elif menu == "📉 Gastos":
    st.title("📉 Registro de Gastos y Egresos")
    st.info("Registra aquí cualquier salida de dinero (alquiler, servicios, papelería, repuestos, etc.)")

    with st.form("form_gastos_pro", clear_on_submit=True):
        col_d, col_c = st.columns([2, 1])
        desc = col_d.text_input("Descripción del Gasto (Ej: Pago de luz, Resma de papel)")
        categoria = col_c.selectbox("Categoría:", [
            "Materia Prima", 
            "Mantenimiento de Equipos", 
            "Servicios (Luz/Internet)", 
            "Publicidad", 
            "Sueldos/Retiros",
            "Otros"
        ])

        c1, c2 = st.columns(2)
        monto_gasto = c1.number_input("Monto en Dólares ($):", min_value=0.01, format="%.2f")
        metodo_pago = c2.selectbox("Pagado mediante:", [
            "Efectivo ($)", 
            "Pago Móvil (Bs)", 
            "Zelle", 
            "Binance (USDT)", 
            "Transferencia (Bs)"
        ])

        st.divider()
        
        # Cálculo informativo de la tasa
        tasa_ref = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (t_bin if "Binance" in metodo_pago else 1.0)
        if tasa_ref > 1.0:
            st.caption(f"💵 Valor referencial del gasto en bolívares: **Bs {(monto_gasto * tasa_ref):,.2f}**")

        if st.form_submit_button("📉 REGISTRAR EGRESO"):
            if desc:
                conn = conectar()
                try:
                    c = conn.cursor()
                    # Insertamos el gasto con todas sus dimensiones
                    c.execute("""
                        INSERT INTO gastos (descripcion, monto, categoria, metodo) 
                        VALUES (?, ?, ?, ?)
                    """, (desc, monto_gasto, categoria, metodo_pago))
                    
                    conn.commit()
                    st.warning(f"📉 Gasto de ${monto_gasto} registrado correctamente.")
                except Exception as e:
                    st.error(f"❌ Error al guardar el gasto: {e}")
                finally:
                    conn.close()
                st.rerun()
            else:
                st.error("⚠️ La descripción es obligatoria.")

    # --- LISTADO DE GASTOS RECIENTES ---
    st.divider()
    st.subheader("📋 Últimos Gastos")
    conn = conectar()
    df_gastos_recientes = pd.read_sql_query("""
        SELECT fecha, descripcion as 'Detalle', categoria as 'Categoría', monto as 'Monto ($)', metodo as 'Pago'
        FROM gastos 
        ORDER BY fecha DESC LIMIT 10
    """, conn)
    conn.close()

    if not df_gastos_recientes.empty:
        st.dataframe(df_gastos_recientes, use_container_width=True, hide_index=True)
    else:
        st.info("No hay gastos registrados aún.")

# --- 13. MÓDULO DE CIERRE DE CAJA ---
elif menu == "🏁 Cierre de Caja":
    st.title("🏁 Cierre de Caja y Arqueo")
    
    # Selector de fecha para ver cierres anteriores si es necesario
    fecha_cierre = st.date_input("Seleccionar fecha de cierre:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    conn = conectar()
    # Filtramos ventas y gastos solo para la fecha seleccionada
    query_v = "SELECT * FROM ventas WHERE date(fecha) = ?"
    query_g = "SELECT * FROM gastos WHERE date(fecha) = ?"
    
    df_v_hoy = pd.read_sql(query_v, conn, params=(fecha_str,))
    df_g_hoy = pd.read_sql(query_g, conn, params=(fecha_str,))
    conn.close()

    # --- MÉTRICAS GENERALES DEL DÍA ---
    t_ventas = df_v_hoy['monto_total'].sum() if not df_v_hoy.empty else 0
    t_gastos = df_g_hoy['monto'].sum() if not df_g_hoy.empty else 0
    balance_dia = t_ventas - t_gastos

    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Hoy", f"$ {t_ventas:,.2f}")
    c2.metric("Egresos Hoy", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c3.metric("Efectivo Neto", f"$ {balance_dia:,.2f}")

    st.divider()

    # --- ARQUEO POR MÉTODO DE PAGO ---
    col_v, col_g = st.columns(2)

    with col_v:
        st.subheader("💰 Ingresos por Método")
        if not df_v_hoy.empty:
            resumen_v = df_v_hoy.groupby('metodo')['monto_total'].sum().reset_index()
            for _, row in resumen_v.iterrows():
                st.write(f"✅ **{row['metodo']}:** ${row['monto_total']:,.2f}")
        else:
            st.info("No hubo ventas hoy.")

    with col_g:
        st.subheader("💸 Egresos por Método")
        if not df_g_hoy.empty:
            resumen_g = df_g_hoy.groupby('metodo')['monto'].sum().reset_index()
            for _, row in resumen_g.iterrows():
                st.write(f"❌ **{row['metodo']}:** ${row['monto']:,.2f}")
        else:
            st.info("No hubo gastos hoy.")

    st.divider()

    # --- VALIDACIÓN FINAL ---
    with st.expander("📝 Ver detalle de transacciones de hoy"):
        st.write("**Ventas:**")
        st.dataframe(df_v_hoy, use_container_width=True, hide_index=True)
        st.write("**Gastos:**")
        st.dataframe(df_g_hoy, use_container_width=True, hide_index=True)

    if st.button("🖨️ Generar Reporte de Cierre (Simulado)"):
        st.toast("Generando resumen para imprimir...")
        st.success(f"Cierre de caja del {fecha_str} completado exitosamente.")

# --- 13. MÓDULO DE CIERRE DE CAJA ---
elif menu == "🏁 Cierre de Caja":
    st.title("🏁 Cierre de Caja y Arqueo")
    
    # Selector de fecha para ver cierres anteriores si es necesario
    fecha_cierre = st.date_input("Seleccionar fecha de cierre:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    conn = conectar()
    # Filtramos ventas y gastos solo para la fecha seleccionada
    query_v = "SELECT * FROM ventas WHERE date(fecha) = ?"
    query_g = "SELECT * FROM gastos WHERE date(fecha) = ?"
    
    df_v_hoy = pd.read_sql(query_v, conn, params=(fecha_str,))
    df_g_hoy = pd.read_sql(query_g, conn, params=(fecha_str,))
    conn.close()

    # --- MÉTRICAS GENERALES DEL DÍA ---
    t_ventas = df_v_hoy['monto_total'].sum() if not df_v_hoy.empty else 0
    t_gastos = df_g_hoy['monto'].sum() if not df_g_hoy.empty else 0
    balance_dia = t_ventas - t_gastos

    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Hoy", f"$ {t_ventas:,.2f}")
    c2.metric("Egresos Hoy", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c3.metric("Efectivo Neto", f"$ {balance_dia:,.2f}")

    st.divider()

    # --- ARQUEO POR MÉTODO DE PAGO ---
    col_v, col_g = st.columns(2)

    with col_v:
        st.subheader("💰 Ingresos por Método")
        if not df_v_hoy.empty:
            resumen_v = df_v_hoy.groupby('metodo')['monto_total'].sum().reset_index()
            for _, row in resumen_v.iterrows():
                st.write(f"✅ **{row['metodo']}:** ${row['monto_total']:,.2f}")
        else:
            st.info("No hubo ventas hoy.")

    with col_g:
        st.subheader("💸 Egresos por Método")
        if not df_g_hoy.empty:
            resumen_g = df_g_hoy.groupby('metodo')['monto'].sum().reset_index()
            for _, row in resumen_g.iterrows():
                st.write(f"❌ **{row['metodo']}:** ${row['monto']:,.2f}")
        else:
            st.info("No hubo gastos hoy.")

    st.divider()

    # --- VALIDACIÓN FINAL ---
    with st.expander("📝 Ver detalle de transacciones de hoy"):
        st.write("**Ventas:**")
        st.dataframe(df_v_hoy, use_container_width=True, hide_index=True)
        st.write("**Gastos:**")
        st.dataframe(df_g_hoy, use_container_width=True, hide_index=True)

    if st.button("🖨️ Generar Reporte de Cierre (Simulado)"):
        st.toast("Generando resumen para imprimir...")
        st.success(f"Cierre de caja del {fecha_str} completado exitosamente.")

# --- 13. AUDITORÍA Y MÉTRICAS (FINANCIERO + OPERATIVO) ---
elif menu == "📊 Auditoría y Métricas":
    st.title("📊 Auditoría de Producción, Insumos y Finanzas")
    st.info("Rastrea cada mililitro de tinta, unidad de material y cada centavo del flujo de caja.")

    conn = conectar()
    # 1. Datos de Movimientos (Tu código original)
    query_movs = """
        SELECT m.fecha, i.item AS 'Material', m.tipo AS 'Operación',
               m.cantidad AS 'Cant.', i.unidad AS 'Unidad', m.motivo AS 'Motivo'
        FROM inventario_movs m
        JOIN inventario i ON m.item_id = i.id
        ORDER BY m.fecha DESC
    """
    df_movs = pd.read_sql_query(query_movs, conn)
    
    # 2. Datos de Ventas y Gastos (Para métricas de dinero)
    df_ventas = pd.read_sql_query("SELECT * FROM ventas", conn)
    df_gastos = pd.read_sql_query("SELECT * FROM gastos", conn)
    conn.close()

    tab_finanzas, tab_graficos, tab_historial, tab_alertas = st.tabs([
        "💰 Auditoría Financiera", "📈 Análisis Visual", "📋 Historial Insumos", "🚨 Alertas de Stock"
    ])

    with tab_finanzas:
        st.subheader("🕵️ Flujo de Caja Auditable")
        
        # Cálculos clave
        total_ventas = df_ventas['monto_total'].sum() if not df_ventas.empty else 0
        total_gastos = df_gastos['monto'].sum() if not df_gastos.empty else 0
        
        # Instrucción 10-02: Impuesto bancario disponible
        banco_perc = st.session_state.get('banco_perc', 0.5)
        comision_est = total_ventas * (banco_perc / 100)
        
        # Deudas (Cuentas por cobrar)
        deudas_df = df_ventas[df_ventas['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)]
        total_deudas = deudas_df['monto_total'].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos Brutos", f"$ {total_ventas:,.2f}")
        m2.metric("Comisión Banco (Est.)", f"$ {comision_est:,.2f}", delta=f"-{banco_perc}%", delta_color="inverse")
        m3.metric("Cuentas por Cobrar", f"$ {total_deudas:,.2f}", delta="⚠️ Pendiente")

        if not deudas_df.empty:
            with st.expander("🔍 Ver Detalle de Deudores"):
                st.dataframe(deudas_df[['fecha', 'cliente', 'detalle', 'monto_total']], use_container_width=True)

    with tab_graficos:
        if not df_movs.empty:
            df_salidas = df_movs[df_movs['Operación'] == 'SALIDA']
            if not df_salidas.empty:
                st.subheader("🔥 Consumo Acumulado por Material")
                resumen = df_salidas.groupby("Material")["Cant."].sum().reset_index()
                st.bar_chart(data=resumen, x="Material", y="Cant.", color="#FF4B4B")
                
                c1, c2 = st.columns(2)
                id_max = resumen['Cant.'].idxmax()
                mas_usado = resumen.loc[id_max]
                c1.metric("Material más demandado", mas_usado['Material'], f"{mas_usado['Cant.']:.2f} uds")
                c2.metric("Total Operaciones", len(df_movs))
            else:
                st.info("No hay salidas registradas.")

    with tab_historial:
        st.subheader("📜 Bitácora de Movimientos de Almacén")
        if not df_movs.empty:
            def color_operacion(val):
                return 'background-color: #d1f7d1' if val == 'ENTRADA' else 'background-color: #ffd1d1'
            
            st.dataframe(
                df_movs.style.applymap(color_operacion, subset=['Operación']),
                use_container_width=True, hide_index=True
            )

    with tab_alertas:
        st.subheader("🚨 Control de Reposición")
        df_inv = st.session_state.get('df_inv', pd.DataFrame())
        if not df_inv.empty:
            # Usamos el 'minimo' configurado o 20 por defecto
            critico = df_inv[df_inv['cantidad'] <= df_inv.get('minimo', 20.0)] 
            if not critico.empty:
                for _, row in critico.iterrows():
                    st.error(f"**{row['item']}** bajo: ¡Quedan {row['cantidad']} {row['unidad']}! (Mínimo: {row['minimo']})")
            else:
                st.success("✅ Niveles de inventario óptimos.")

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizador de Trabajos")

    # 1. Recuperamos datos de sesión de forma segura
    datos_crudos = st.session_state.get('datos_pre_cotizacion', {})
    
    # 2. Normalizamos los datos para evitar el KeyError (Blindaje contra errores)
    consumos_base = datos_crudos.get('consumos', {})
    
    datos_pre = {
        'trabajo': datos_crudos.get('trabajo', "Trabajo General"),
        'costo_base': datos_crudos.get('costo_base', 0.0),
        'unidades': datos_crudos.get('unidades', 1),
        'c_ml': consumos_base.get('C', 0.0),
        'm_ml': consumos_base.get('M', 0.0),
        'y_ml': consumos_base.get('Y', 0.0),
        'k_ml': consumos_base.get('K', 0.0)
    }

    # 🔑 Detectar si el trabajo usa tinta
    usa_tinta = any([datos_pre['c_ml'], datos_pre['m_ml'], datos_pre['y_ml'], datos_pre['k_ml']])

    # --- DETALLES DEL TRABAJO ---
    with st.container(border=True):
        st.subheader("🛠️ Detalles del Trabajo")
        col1, col2 = st.columns([2, 1])

        with col1:
            descr = st.text_input("Descripción del trabajo:", value=datos_pre['trabajo'])
            df_clis = st.session_state.get('df_cli', pd.DataFrame())

            if not df_clis.empty:
                opciones_cli = {row['nombre']: row['id'] for _, row in df_clis.iterrows()}
                cliente_sel = st.selectbox("👤 Asignar a Cliente:", opciones_cli.keys())
                id_cliente = opciones_cli[cliente_sel]
            else:
                st.warning("⚠️ No hay clientes registrados. Registra uno en el módulo Clientes.")
                st.stop()

        with col2:
            unidades = st.number_input("Cantidad de piezas:", min_value=1, value=int(datos_pre['unidades']))

    # --- CONSUMO DE INSUMOS ---
    st.subheader("📦 Consumo de Insumos")
    consumos_reales = {}

    if usa_tinta:
        st.info("🎨 Este trabajo consume tinta (Análisis CMYK detectado)")
        df_tintas = obtener_tintas_disponibles()

        if df_tintas.empty:
            st.error("🚨 No hay tintas (unidad ml) registradas en inventario.")
            st.stop()

        dict_t = {f"{r['item']} ({r['cantidad']:.1f} ml)": r['id'] for _, r in df_tintas.iterrows()}

        st.info("Asigne las botellas físicas para el descuento:")
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            t_c = st.selectbox("Cian (C)", dict_t.keys(), key="c_sel")
            consumos_reales[dict_t[t_c]] = datos_pre['c_ml'] * unidades
        with c2:
            t_m = st.selectbox("Magenta (M)", dict_t.keys(), key="m_sel")
            consumos_reales[dict_t[t_m]] = datos_pre['m_ml'] * unidades
        with c3:
            t_y = st.selectbox("Amarillo (Y)", dict_t.keys(), key="y_sel")
            consumos_reales[dict_t[t_y]] = datos_pre['y_ml'] * unidades
        with c4:
            t_k = st.selectbox("Negro (K)", dict_t.keys(), key="k_sel")
            consumos_reales[dict_t[t_k]] = datos_pre['k_ml'] * unidades
    else:
        st.success("📄 Trabajo sin consumo de tinta analizado.")

    # --- COSTOS Y PRECIOS ---
    st.subheader("💰 Costos y Precios")
    c1, c2 = st.columns(2)

    costo_unitario_base = c1.number_input(
        "Costo Unitario Base ($)",
        value=float(datos_pre['costo_base'] / unidades if unidades > 0 else 0.0),
        format="%.4f"
    )

    margen = c2.slider("Margen de Ganancia %", 10, 500, 100, 10)

    costo_total_prod = costo_unitario_base * unidades
    precio_venta_total = costo_total_prod * (1 + margen / 100)

    st.divider()
    v1, v2, v3 = st.columns(3)
    v1.metric("Costo Producción", f"$ {costo_total_prod:.2f}")
    v2.metric("Precio Venta Total", f"$ {precio_venta_total:.2f}")
    v3.metric("Total Bs (BCV)", f"Bs {(precio_venta_total * t_bcv):,.2f}")

    # --- CIERRE DE VENTA ---
    st.subheader("💳 Método de Pago")
    metodo_pago = st.selectbox(
        "Seleccione cómo paga el cliente:",
        ["Efectivo $", "Zelle", "Pago Móvil", "Transferencia Bs", "Binance"]
    )

    if st.button("🚀 CONFIRMAR VENTA Y DESCONTAR INVENTARIO", use_container_width=True):
        with st.spinner("Registrando en el Imperio..."):
            # Ejecutamos la función crítica de base de datos
            exito, msg = procesar_venta_grafica_completa(
                id_cliente=id_cliente,
                monto=precio_venta_total,
                metodo=metodo_pago,
                consumos_dict=consumos_reales
            )

            if exito:
                st.success(msg)
                st.balloons()
                # Limpiamos los datos temporales para que no se duplique la venta
                if 'datos_pre_cotizacion' in st.session_state:
                    del st.session_state['datos_pre_cotizacion']
                
                # Forzamos recarga para ver el stock actualizado
                cargar_datos()
                st.rerun()
            else:
                st.error(msg)


# --- 🛒 MÓDULO DE VENTA DIRECTA "IMPERIO ELITE" ---
if menu == "🛒 Venta Directa":
    st.title("🛒 Venta de Materiales e Insumos")
    
    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    
    if not df_inv.empty:
        items_disponibles = df_inv[df_inv['cantidad'] > 0]
        
        if items_disponibles.empty:
            st.warning("⚠️ No hay stock disponible en el inventario.")
        else:
            # --- 1. SELECCIÓN DE PRODUCTO Y VISUALIZACIÓN ---
            with st.container(border=True):
                col1, col2 = st.columns([2, 1])
                prod_sel = col1.selectbox("📦 Seleccionar Material/Insumo:", items_disponibles['item'].tolist())
                
                datos_p = items_disponibles[items_disponibles['item'] == prod_sel].iloc[0]
                stock_actual = datos_p['cantidad']
                costo_base = datos_p['precio_usd']
                unidad_p = datos_p['unidad']
                stock_minimo = datos_p.get('minimo', 5.0)

                # Barra de Stock
                nivel = min(stock_actual / (stock_minimo * 3), 1.0)
                col2.metric("Stock Actual", f"{stock_actual:.2f} {unidad_p}")
                col2.progress(nivel, text="Disponibilidad en Almacén")

            # --- 2. FORMULARIO DE VENTA ---
            with st.form("venta_directa_form", clear_on_submit=True):
                st.subheader("📝 Datos de la Operación")
                cliente_v = st.text_input("👤 Cliente:", placeholder="Nombre del Cliente")
                
                c1, c2, c3 = st.columns(3)
                cantidad_v = c1.number_input(f"Cantidad ({unidad_p}):", min_value=0.0, max_value=float(stock_actual), step=1.0)
                margen_v = c2.number_input("Margen %:", value=30.0)
                metodo_p = c3.selectbox("Método de Pago:", ["Efectivo $", "Pago Móvil (BCV)", "Zelle", "Binance", "Pendiente"])

                st.divider()
                
                # --- NUEVO: DESCUENTO Y FIDELIZACIÓN ---
                col_d1, col_d2 = st.columns(2)
                usa_desc = col_d1.checkbox("💎 Aplicar Descuento 'Cliente Fiel'")
                pct_desc = col_d2.number_input("Descuento %", value=5.0 if usa_desc else 0.0, disabled=not usa_desc)

                st.write("⚖️ **Impuestos y Comisiones:**")
                i1, i2, i3 = st.columns(3)
                usa_iva = i1.checkbox(f"IVA (+{st.session_state.get('iva_perc', 16)}%)")
                usa_igtf = i2.checkbox(f"IGTF (+{st.session_state.get('igtf_perc', 3)}%)")
                # Impuesto del banco por instrucción del 10-02
                usa_banco = i3.checkbox(f"Banco (+{st.session_state.get('banco_perc', 0.5)}%)", value=True)

                # --- CÁLCULOS INTEGRADOS ---
                costo_total_material = cantidad_v * costo_base
                
                # Precio con margen
                precio_con_margen = costo_total_material * (1 + (margen_v / 100))
                
                # Aplicar Descuento (Si aplica)
                precio_tras_desc = precio_con_margen * (1 - (pct_desc / 100))
                
                # Sumar Impuestos
                p_imp = (st.session_state.get('iva_perc', 0) if usa_iva else 0) + \
                        (st.session_state.get('igtf_perc', 0) if usa_igtf else 0) + \
                        (st.session_state.get('banco_perc', 0) if usa_banco else 0)
                
                total_usd = precio_tras_desc * (1 + (p_imp / 100))
                
                # Conversión de Tasa
                tasa_uso = t_bin if "Binance" in metodo_p else t_bcv
                total_bs = total_usd * tasa_uso

                st.info(f"💰 **TOTAL FINAL:** ${total_usd:.2f} | {total_bs:.2f} Bs.")
                if usa_desc: st.warning(f"Ahorro por fidelidad: -${(precio_con_margen - precio_tras_desc):.2f}")

                # --- 3. PROCESAMIENTO Y ACTUALIZACIÓN DE INVENTARIO ---
                if st.form_submit_button("🚀 PROCESAR VENTA Y DESCONTAR STOCK"):
                    if cantidad_v <= 0:
                        st.error("❌ Introduce una cantidad válida.")
                    else:
                        try:
                            nombre_c = cliente_v if cliente_v else "Consumidor Final"
                            detalle_f = f"{cantidad_v:.2f} {unidad_p} de {prod_sel}"
                            
                            conn = conectar()
                            cursor = conn.cursor()
                            
                            # A. DESCUENTO REAL DEL INVENTARIO (SQL)
                            cursor.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE item = ?", (cantidad_v, prod_sel))
                            
                            # B. REGISTRO DE VENTA
                            cursor.execute("INSERT INTO ventas (monto_total, metodo, cliente, detalle) VALUES (?, ?, ?, ?)", 
                                         (total_usd, metodo_p, nombre_c, detalle_f))
                            
                            conn.commit()
                            conn.close()

                            # C. ALERTA DE STOCK CRÍTICO (Visual e Inmediata)
                            nuevo_stock = stock_actual - cantidad_v
                            if nuevo_stock <= stock_minimo:
                                st.error(f"🚨 ¡STOCK CRÍTICO! {prod_sel} queda en {nuevo_stock:.2f}. Reponer pronto.")
                                st.toast(f"Reordenar {prod_sel}", icon="🔥")
                            
                            # D. DATOS DEL TICKET
                            st.session_state.ultimo_ticket = {
                                "nro": "V-" + str(int(time.time())),
                                "cliente": nombre_c, "detalle": detalle_f,
                                "total_usd": total_usd, "total_bs": total_bs, "metodo": metodo_p
                            }
                            
                            cargar_datos() # Sincroniza stock en la app
                            st.success("✅ Inventario actualizado y venta registrada.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error técnico: {e}")

    # --- TICKET Y ÚLTIMOS MOVIMIENTOS ---
    if 'ultimo_ticket' in st.session_state:
        st.divider()
        t = st.session_state.ultimo_ticket
        with st.expander("📄 RECIBO DE VENTA", expanded=True):
            st.code(f"CLIENTE: {t['cliente']}\nITEM: {t['detalle']}\nTOTAL: ${t['total_usd']:.2f}\nMÉTODO: {t['metodo']}")
            if st.button("🗑️ Cerrar Ticket"):
                del st.session_state.ultimo_ticket
                st.rerun()











