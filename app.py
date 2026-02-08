import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime
from PIL import Image
import numpy as np
import io

# --- 1. MOTOR DE BASE DE DATOS PROFESIONAL ---
def conectar():
    # Asegúrate de que este nombre sea el mismo que usabas antes si quieres tus datos viejos
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    
    # Tablas principales
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente_id INTEGER, trabajo TEXT, monto_usd REAL, estado TEXT, FOREIGN KEY(cliente_id) REFERENCES clientes(id))')
    c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo_pago TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(cliente_id) REFERENCES clientes(id))')
    c.execute('CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)')

    # --- REPARACIÓN DE USUARIOS ---
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        usuarios_iniciales = [
            ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio'),
            ('mama', 'admin2026', 'Administracion', 'Mamá'),
            ('pro', 'diseno2026', 'Produccion', 'Hermana')
        ]
        c.executemany("INSERT INTO usuarios VALUES (?,?,?,?)", usuarios_iniciales)

    # --- CONFIGURACIÓN DE INFLACIÓN (TINTA Y TASAS) ---
    config_init = [
        ('tasa_bcv', 36.50),
        ('tasa_binance', 38.00),
        ('iva_perc', 0.16),
        ('igtf_perc', 0.03),
        ('banco_perc', 0.02),
        ('costo_tinta_ml', 0.10) # <--- ¡Aquí puedes cambiar el precio base!
    ]
    for param, valor in config_init:
        c.execute("INSERT OR IGNORE INTO configuracion (parametro, valor) VALUES (?, ?)", (param, valor))
    
   # --- 2. MOTORES DE CÁLCULO (PÉGALO AQUÍ) ---

def calcular_precio_con_impuestos(costo_base_usd, margen_ganancia_perc, usar_impuestos=True):
    """Calcula el precio final de venta al cliente"""
    # 1. Aplicamos tu ganancia
    precio_neto = costo_base_usd * (1 + (margen_ganancia_perc / 100))
    
    if not usar_impuestos:
        return precio_neto
    
    # 2. Sumamos los impuestos (traídos de la configuración que maneja la inflación)
    # Usamos .get() con valores por defecto por si la base de datos está cargando
    iva = st.session_state.get('iva', 0.16)
    igtf = st.session_state.get('igtf', 0.03)
    banco = st.session_state.get('banco', 0.02)
    
    # Retornamos el precio con el recargo de impuestos
    return precio_neto * (1 + iva + igtf + banco)

def ejecutar_movimiento_stock(item_id, cantidad_cambio, tipo_mov, motivo=""):
    """Registra entradas/salidas y actualiza el stock real"""
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE inventario SET cantidad = cantidad + ? WHERE id = ?", (cantidad_cambio, item_id))
        cur.execute("""INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario) 
                       VALUES (?, ?, ?, ?, ?)""", 
                    (item_id, tipo_mov, cantidad_cambio, motivo, st.session_state.get('usuario_nombre', 'Sistema')))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error actualizando stock: {e}")
        return False

# Ahora sí, continúa el resto de tu código
inicializar_sistema()
# --- 2. LOGIN REFORZADO ---
st.set_page_config(page_title="Imperio Atómico - Sistema Pro", layout="wide")

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Imperio Atómico")
    with st.form("login_form"):
        u = st.text_input("Usuario").lower().strip() # Limpiamos espacios y mayúsculas
        p = st.text_input("Clave", type="password")
        if st.form_submit_button("Entrar"):
            # Primero intentamos con la base de datos
            conn = conectar()
            res = pd.read_sql_query("SELECT * FROM usuarios WHERE username=? AND password=?", conn, params=(u, p))
            conn.close()
            
            if not res.empty:
                st.session_state.autenticado = True
                st.session_state.rol = res.iloc[0]['rol']
                st.session_state.usuario_nombre = res.iloc[0]['nombre']
                st.rerun()
            # Bypass de emergencia alineado correctamente
            elif u == "jefa" and p == "atomica2026":
                st.session_state.autenticado = True
                st.session_state.rol = "Admin"
                st.session_state.usuario_nombre = "Dueña del Imperio"
                st.rerun()
            else:
                st.error("❌ Usuario o clave incorrecta")
    st.stop()

# --- 2.5 FUNCIONES DE APOYO (Alineadas al borde izquierdo) ---
def ejecutar_movimiento_stock(item_id, cantidad_cambio, tipo_mov, motivo=""):
    """Registra movimientos y actualiza el stock real contra la inflación"""
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE inventario SET cantidad = cantidad + ? WHERE id = ?", (cantidad_cambio, item_id))
        cur.execute("""INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario) 
                       VALUES (?, ?, ?, ?, ?)""", 
                    (item_id, tipo_mov, cantidad_cambio, motivo, st.session_state.get('usuario_nombre', 'Sistema')))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error en movimiento: {e}")
        return False

def calcular_costo_total(base_usd, logistica_usd=0, aplicar_impuestos=True):
    """Calcula el costo real sumando logística e impuestos (IVA/IGTF/Banco)"""
    costo_con_logistica = base_usd + logistica_usd
    if not aplicar_impuestos:
        return costo_con_logistica
    
    iva = st.session_state.get('iva', 0.16)
    igtf = st.session_state.get('igtf', 0.03)
    banco = st.session_state.get('banco', 0.02)
    return costo_con_logistica * (1 + iva + igtf + banco)

# --- 2. INICIALIZAR SISTEMA ---
def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    
    # --- Tablas de Usuarios y Configuración (Ya las tienes) ---
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    username TEXT PRIMARY KEY, 
                    password TEXT, 
                    rol TEXT, 
                    nombre TEXT)''')
    
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # --- Tablas de Operaciones (Asegúrate de tener estas 4) ---
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    
    # TU TABLA DE MOVIMIENTOS (Tal cual la tenías)
    c.execute('''CREATE TABLE IF NOT EXISTS inventario_movs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    item_id INTEGER, 
                    tipo TEXT, 
                    cantidad REAL, 
                    motivo TEXT, 
                    usuario TEXT, 
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # NUEVA TABLA DE GASTOS (Agrégala aquí abajo)
    c.execute('''CREATE TABLE IF NOT EXISTS gastos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    descripcion TEXT, 
                    monto REAL, 
                    categoria TEXT, 
                    metodo TEXT, 
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Tablas de Ventas (Para que el Dashboard no falle al leerlas)
    c.execute('''CREATE TABLE IF NOT EXISTS ventas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    cliente_id INTEGER, 
                    monto_total REAL, 
                    metodo TEXT, 
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()
def cargar_datos_seguros():
    if 'df_inv' not in st.session_state:
        conn = conectar()
        st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
        st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
        conn.close()

# --- 3. EJECUCIÓN INICIAL Y LOGIN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

inicializar_sistema()

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Imperio Atómico")
    with st.form("login"):
        u = st.text_input("Usuario")
        p = st.text_input("Clave", type="password")
        if st.form_submit_button("Entrar"):
            conn = conectar()
            cur = conn.cursor()
            cur.execute("SELECT rol, nombre FROM usuarios WHERE username=? AND password=?", (u, p))
            res = cur.fetchone()
            conn.close()
            
            if res:
                st.session_state.autenticado = True
                st.session_state.rol = res[0]
                st.session_state.usuario_nombre = res[1]
                st.rerun()
            else:
                st.error("❌ Usuario o clave incorrecta")
    st.stop()

# --- 4. SI LLEGA AQUÍ, ESTÁ LOGUEADO ---
st.set_page_config(page_title="Imperio Atómico - ERP", layout="wide")
cargar_datos_seguros()
ROL = st.session_state.rol

# Cargar tasas globales
conn = conectar()
conf = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = float(conf.loc['tasa_bcv', 'valor'])
t_bin = float(conf.loc['tasa_binance', 'valor'])
st.session_state.iva = float(conf.loc['iva_perc', 'valor'])
st.session_state.igtf = float(conf.loc['igtf_perc', 'valor'])
st.session_state.banco = float(conf.loc['banco_perc', 'valor'])
conn.close()
# --- 3. MENÚ LATERAL FILTRADO ---
with st.sidebar:
    st.header(f"👋 Hola, {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv:.2f} | 🔶 BIN: {t_bin:.2f}")
    
    # 1. Definimos la lista de opciones (Lógica de Roles)
    opciones = ["📝 Cotizaciones", "🎨 Análisis CMYK", "👥 Clientes"]
    
    if ROL == "Admin":
        opciones += ["💰 Ventas", "📉 Gastos", "📦 Inventario", "📊 Dashboard", "🏗️ Activos", "🛠️ Otros Procesos", "⚙️ Configuración", "🏁 Cierre de Caja"]
    elif ROL == "Administracion":
        opciones += ["💰 Ventas", "📉 Gastos", "📊 Dashboard", "⚙️ Configuración", "🏁 Cierre de Caja"]
    elif ROL == "Produccion":
        opciones += ["📦 Inventario", "🏗️ Activos", "🛠️ Otros Procesos"]

    # 2. ÚNICA LLAMADA AL MENÚ (Eliminamos la duplicidad)
    menu = st.radio("Seleccione una opción:", opciones, key="menu_unico_final")
    
    st.divider() # Una línea visual para separar el botón de salir
    
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

# --- 4. MÓDULO DE INVENTARIO: AUDITORÍA Y CONTROL TOTAL --- 
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    
    # 1. Usar datos frescos de la memoria global
    df_inv = st.session_state.df_inv

    # --- 📊 MÉTRICAS FINANCIERAS (Calculadas al momento) ---
    if not df_inv.empty:
        st.subheader("💰 Inversión Activa en Almacén")
        valor_usd = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Dólares", f"$ {valor_usd:,.2f}")
        c2.metric("Total BCV", f"Bs {(valor_usd * t_bcv):,.2f}")
        c3.metric("Tasa Actual", f"{t_bcv} Bs")
        
        alertas = df_inv[df_inv['cantidad'] <= df_inv['minimo']]
        if not alertas.empty:
            st.error(f"⚠️ Tienes {len(alertas)} insumos bajo el mínimo de stock.")
    else:
        st.info("Inventario vacío.")

    st.divider()

    # --- 📥 FORMULARIO DE ENTRADA (USANDO EL MOTOR TRANSACCIONAL) ---
    st.subheader("📥 Registrar Entrada de Mercancía")
    it_unid = st.selectbox("Unidad de Medida:", ["ml", "Hojas", "Resma", "Unidad", "Metros"], key="u_medida_root")

    with st.form("form_inventario_manual"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**📦 Detalles del Producto**")
            it_nombre = st.text_input("Nombre del Insumo (Ej: Papel Fotográfico)")
            if it_unid == "ml":
                tipo_carga = st.radio("Presentación:", ["Individual", "Dúo (2)", "Kit CMYK (4)"], horizontal=True)
                capacidad = st.number_input("ml por cada bote", min_value=0.1, value=100.0)
            else:
                tipo_carga, capacidad = "Normal", 1.0
            it_minimo = st.number_input("Punto de Alerta (Mínimo)", min_value=0.0, value=5.0)

        with col2:
            st.markdown("**💵 Costos y Logística**")
            it_cant_packs = st.number_input("Cantidad comprada", min_value=1, value=1)
            monto_compra = st.number_input("Precio pagado (Total)", min_value=0.0, format="%.2f")
            moneda_pago = st.radio("Moneda de Pago:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], horizontal=True)
            gastos_bs = st.number_input("Gastos Extras / Delivery (Bs)", min_value=0.0)
            
            st.markdown("**🛡️ Impuestos aplicados al costo**")
            tx1, tx2, tx3 = st.columns(3)
            p_iva = tx1.checkbox(f"IVA", value=False)
            p_igtf = tx2.checkbox(f"IGTF", value=False)
            p_banco = tx3.checkbox(f"Banco", value=False)

        if st.form_submit_button("🚀 IMPACTAR INVENTARIO"):
            if it_nombre and (monto_compra > 0 or gastos_bs > 0):
                try:
                    # 1. Cálculo de tasa y base
                    tasa_u = t_bcv if "BCV" in moneda_pago else (t_bin if "Binance" in moneda_pago else 1.0)
                    base_usd = monto_compra / tasa_u
                    logistica_usd = gastos_bs / t_bcv
                    
                    # 2. Uso del Motor Único de Costos (LO NUEVO)
                    # Aplicamos impuestos solo si alguno está marcado
                    tiene_impuestos = p_iva or p_igtf or p_banco
                    costo_final_usd = calcular_costo_total(base_usd, logistica_usd, aplicar_impuestos=tiene_impuestos)
                    
                    conn = conectar(); cur = conn.cursor()
                    
                    # 3. Lógica de distribución para Kits CMYK o individuales
                    div = 4 if it_unid == "ml" and "Kit" in tipo_carga else (2 if it_unid == "ml" and "Dúo" in tipo_carga else 1)
                    costo_por_ml_o_unidad = (costo_final_usd / (div * it_cant_packs)) / (capacidad if it_unid == "ml" else 1)
                    
                    colores = ["Cian", "Magenta", "Amarillo", "Negro"] if div==4 else (["Negro", "Color"] if div==2 else [""])
                    
                    for col in colores:
                        n_item = f"{it_nombre} {col}".strip()
                        cant_a_sumar = capacidad * it_cant_packs
                        
                        # Guardar/Actualizar en Inventario
                        cur.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                                       VALUES (?, 0, ?, ?, ?) 
                                       ON CONFLICT(item) DO UPDATE SET 
                                       precio_usd=excluded.precio_usd, minimo=excluded.minimo""", 
                                    (n_item, it_unid, costo_por_ml_o_unidad, it_minimo))
                        
                        conn.commit() 
                        cur.execute("SELECT id FROM inventario WHERE item=?", (n_item,))
                        prod_id = cur.fetchone()[0]
                        
                        # Auditoría
                        ejecutar_movimiento_stock(prod_id, cant_a_sumar, "ENTRADA", motivo=f"Compra en {moneda_pago}")
                    
                    st.success("✅ Insumos registrados y auditados correctamente.")
                    cargar_datos_seguros()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                finally:
                    conn.close()

    st.divider()

    # --- 📋 TABLA DE AUDITORÍA PROFESIONAL ---
    if not df_inv.empty:
        st.subheader("📋 Auditoría de Almacén")
        
        modo_ver = st.radio("Visualizar costos en:", ["Dólares ($)", "BCV (Bs)"], horizontal=True)
        busc = st.text_input("🔍 Filtrar material...", placeholder="Ej: Tinta, Papel, Resma...")
        
        df_f = df_inv[df_inv['item'].str.contains(busc, case=False)].copy()
        
        tasa_vista = t_bcv if "BCV" in modo_ver else 1.0
        df_f['Costo Unit.'] = df_f['precio_usd'] * tasa_vista
        df_f['Valor Total'] = (df_f['cantidad'] * df_f['precio_usd']) * tasa_vista

        st.dataframe(
            df_f[['item', 'cantidad', 'unidad', 'Costo Unit.', 'Valor Total']], 
            column_config={
                "item": "Insumo", "cantidad": "Stock", "unidad": "Medida",
                "Costo Unit.": st.column_config.NumberColumn("Costo Unit.", format="%.4f"),
                "Valor Total": st.column_config.NumberColumn("Total", format="%.2f")
            },
            use_container_width=True, hide_index=True
        )

        # --- PANEL DE AJUSTES ---
        st.write("🔧 **Ajustes de Inventario**")
        col_aj, col_log = st.columns([1, 1])
        
        with col_aj:
            with st.expander("📝 Corregir Stock Manual"):
                it_aj = st.selectbox("Insumo:", df_f['item'].tolist(), key="sel_ajuste")
                nueva_c = st.number_input("Cantidad Real en Estante:", min_value=0.0)
                if st.button("Confirmar Cambio"):
                    try:
                        fila = df_f[df_f['item'] == it_aj].iloc[0]
                        diferencia = nueva_c - fila['cantidad']
                        ejecutar_movimiento_stock(fila['id'], diferencia, "AJUSTE", motivo="Conteo físico manual")
                        st.success("Stock actualizado."); cargar_datos_seguros(); st.rerun()
                    except Exception as e: st.error(e)
        
        with col_log:
            with st.expander("📜 Historial Reciente"):
                if it_aj:
                    id_log = df_f[df_f['item'] == it_aj]['id'].values[0]
                    conn_h = conectar()
                    log = pd.read_sql(f"""SELECT m.fecha, m.tipo, m.cantidad, m.usuario 
                                          FROM inventario_movs m 
                                          WHERE m.item_id = {id_log} 
                                          ORDER BY m.id DESC LIMIT 5""", conn_h)
                    conn_h.close()
                    st.table(log)
                    


            
# --- 6. DASHBOARD FINANCIERO PROFESIONAL ---
elif menu == "📊 Dashboard":
    st.title("📊 Centro de Control Financiero")
    
    conn = conectar()
    # CARGA COMPLETA DE DATOS PARA EL DASHBOARD
    df_ventas = pd.read_sql_query("SELECT * FROM ventas", conn)
    df_gastos = pd.read_sql_query("SELECT * FROM gastos", conn)
    df_inv_dash = pd.read_sql_query("SELECT cantidad, precio_usd FROM inventario", conn)
    conn.close()

    # --- FILA 1: MÉTRICAS PRINCIPALES ---
    c1, c2, c3, c4 = st.columns(4)
    # ... resto de tus métricas ...
    
    # Cálculos seguros
    ingresos_totales = df_ventas['monto_total'].sum() if not df_ventas.empty else 0.0
    gastos_totales = df_gastos['monto'].sum() if not df_gastos.empty else 0.0
    balance_neto = ingresos_totales - gastos_totales
    valor_inventario = (df_inv_dash['cantidad'] * df_inv_dash['precio_usd']).sum() if not df_inv_dash.empty else 0.0

    # Renderizado de métricas
    c1.metric("💰 Ingresos Totales", f"$ {ingresos_totales:.2f}")
    
    # El delta en rojo indica que es una salida de dinero
    c2.metric("📉 Gastos Totales", f"$ {gastos_totales:.2f}", 
              delta=f"-{gastos_totales:.2f}", delta_color="inverse")
    
    # El balance muestra el margen porcentual si hay ingresos
    margen = (balance_neto / ingresos_totales * 100) if ingresos_totales > 0 else 0.0
    c3.metric("⚖️ Balance Neto", f"$ {balance_neto:.2f}", delta=f"{margen:.1f}% Margen")
    
    c4.metric("📦 Valor Inventario", f"$ {valor_inventario:.2f}")
    # --- FILA 2: GRÁFICOS ---
    st.divider()
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("📈 Histórico de Ventas ($)")
        if not df_ventas.empty:
            # Convertir fecha a formato datetime para graficar
            df_ventas['fecha'] = pd.to_datetime(df_ventas['fecha']).dt.date
            ventas_diarias = df_ventas.groupby('fecha')['monto_total'].sum().reset_index()
            st.area_chart(data=ventas_diarias, x='fecha', y='monto_total', color="#28a745")
        else:
            st.info("Aún no hay ventas registradas.")

    with col_der:
        st.subheader("🍕 Distribución de Gastos")
        if not df_gastos.empty:
            gastos_cat = df_gastos.groupby('categoria')['monto'].sum().reset_index()
            st.bar_chart(data=gastos_cat, x='categoria', y='monto', color="#ff4b4b")
        else:
            st.info("No hay gastos registrados.")

    # --- FILA 3: TABLAS DE DETALLE ---
    st.divider()
    exp1 = st.expander("📄 Ver Últimos Movimientos de Caja")
    with exp1:
        col_v, col_g = st.columns(2)
        with col_v:
            st.write("**Últimas Ventas**")
            st.dataframe(df_ventas.tail(10), use_container_width=True, hide_index=True)
        with col_g:
            st.write("**Últimos Gastos**")
            st.dataframe(df_gastos.tail(10), use_container_width=True, hide_index=True)

# --- 7. MÓDULO DE CONFIGURACIÓN (EL PANEL DE CONTROL) ---
elif menu == "⚙️ Configuración":
    # --- AGREGA ESTAS 3 LÍNEAS JUSTO DEBAJO ---
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden cambiar tasas y costos.")
        st.stop()
    st.title("⚙️ Configuración del Sistema")
    st.info("Desde aquí controlas los precios base y las tasas para combatir la inflación.")

    conn = conectar()
    # Cargamos los valores actuales de la base de datos
    conf_df = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')
    
    with st.form("config_general"):
        st.subheader("💵 Tasas de Cambio")
        c1, c2 = st.columns(2)
        nueva_bcv = c1.number_input("Tasa BCV (Bs/$)", value=float(conf_df.loc['tasa_bcv', 'valor']), format="%.2f")
        nueva_bin = c2.number_input("Tasa Binance (Bs/$)", value=float(conf_df.loc['tasa_binance', 'valor']), format="%.2f")

        st.divider()
        st.subheader("💉 Costos de Insumos Críticos")
        # Aquí es donde manejas la inflación de la tinta
        costo_tinta = st.number_input("Costo de Tinta por ml ($)", 
                                      value=float(conf_df.loc['costo_tinta_ml', 'valor']), 
                                      format="%.4f", 
                                      help="Este valor afecta los cálculos automáticos de las cotizaciones CMYK.")

        st.divider()
        st.subheader("🛡️ Impuestos y Comisiones")
        c3, c4, c5 = st.columns(3)
        n_iva = c3.number_input("IVA (0.16 = 16%)", value=float(conf_df.loc['iva_perc', 'valor']), format="%.2f")
        n_igtf = c4.number_input("IGTF (0.03 = 3%)", value=float(conf_df.loc['igtf_perc', 'valor']), format="%.2f")
        n_banco = c5.number_input("Comisión Bancaria", value=float(conf_df.loc['banco_perc', 'valor']), format="%.2f")

        if st.form_submit_button("💾 GUARDAR CAMBIOS ATÓMICOS"):
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
            st.success("✅ ¡Configuración actualizada! Los cambios se aplicarán en todo el sistema de inmediato.")
            st.rerun()
    
    conn.close()

    # --- GESTIÓN DE USUARIOS (Solo para la Jefa) ---
    if st.session_state.rol == "Admin":
        st.divider()
        with st.expander("👤 Gestión de Usuarios y Claves"):
            st.write("Aquí puedes ver quién tiene acceso al sistema.")
            conn = conectar()
            users = pd.read_sql("SELECT username, rol, nombre FROM usuarios", conn)
            conn.close()
            st.table(users)

# --- 8. LÓGICA DE CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Registro de Clientes")
    
    # --- BARRA DE BÚSQUEDA (ESTO ES LO NUEVO) ---
    busqueda = st.text_input("🔍 Buscar cliente por nombre...", placeholder="Escribe aquí para filtrar...")

    with st.form("form_clientes"):
        col1, col2 = st.columns(2)
        nombre_cli = col1.text_input("Nombre del Cliente o Negocio")
        whatsapp_cli = col2.text_input("WhatsApp (Ej: 04121234567)")
        
        if st.form_submit_button("✅ Registrar Cliente"):
            if nombre_cli:
                c = conectar()
                c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nombre_cli, whatsapp_cli))
                c.commit()
                c.close()
                st.success(f"Cliente {nombre_cli} guardado con éxito.")
                st.rerun()
            else:
                st.error("El nombre es obligatorio.")

    # Mostrar lista de clientes registrados CON FILTRO
    c = conectar()
    # Esta línea busca en la base de datos lo que escribiste arriba
    query = f"SELECT nombre as 'Nombre', whatsapp as 'WhatsApp' FROM clientes WHERE nombre LIKE '%{busqueda}%'"
    df_clis = pd.read_sql_query(query, c)
    c.close()
    
    if not df_clis.empty:
        st.subheader("📋 Directorio de Clientes")
        st.dataframe(df_clis, use_container_width=True, hide_index=True)
    else:
        st.info("No se encontraron clientes con ese nombre.")

# --- 10. ANALIZADOR MASIVO DE COBERTURA CMYK (SOPORTA PDF, JPG, PNG) ---
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador de Cobertura y Costos Reales")

    # 1. Carga de datos base desde la base de datos
    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, desgaste FROM activos", conn)
    df_inv_tintas = pd.read_sql_query("SELECT item, precio_usd FROM inventario WHERE item LIKE '%Tinta%'", conn)
    conn.close()
    
    lista_activos = df_act_db.to_dict('records')
    impresoras_disponibles = [e['equipo'] for e in lista_activos if e['categoria'] == "Impresora (Gasta Tinta)"]

    if not impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en 'Activos'. Por favor, agrega una primero.")
        st.stop()

    c_printer, c_file = st.columns([1, 2])
    
    with c_printer:
        impresora_sel = st.selectbox("🖨️ Selecciona la Impresora", impresoras_disponibles)
        datos_imp = next((e for e in lista_activos if e['equipo'] == impresora_sel), None)
        costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        # Buscamos precio de tinta específico para esa máquina
        tintas_maquina = df_inv_tintas[df_inv_tintas['item'].str.contains(impresora_sel, case=False, na=False)]
        if not tintas_maquina.empty:
            precio_tinta_ml = tintas_maquina['precio_usd'].mean()
            st.success(f"✅ Precio detectado: ${precio_tinta_ml:.4f}/ml")
        else:
            precio_tinta_ml = 0.10 # Precio de respaldo si no hay en inventario
            st.info(f"💡 Usando precio base: ${precio_tinta_ml}/ml")

    with c_file:
        archivos_multiples = st.file_uploader("Sube tus diseños (PDF, JPG, PNG)", 
                                             type=['pdf', 'png', 'jpg', 'jpeg'], 
                                             accept_multiple_files=True,
                                             key="uploader_cmyk_v3")

    # --- MOTOR DE PROCESAMIENTO ---
    if archivos_multiples:
        from PIL import Image
        import numpy as np
        import fitz  # PyMuPDF (Ya lo tienes en requirements.txt)
        import io

        resultados = []
        total_paginas_lote = 0
        
        with st.spinner('🚀 Analizando archivos...'):
            for arc in archivos_multiples:
                imagenes_a_procesar = []
                
                # SI ES PDF
                if arc.type == "application/pdf":
                    try:
                        # Leemos el contenido del archivo
                        file_content = arc.read()
                        doc = fitz.open(stream=file_content, filetype="pdf")
                        for page_num in range(len(doc)):
                            page = doc.load_page(page_num)
                            # Renderizamos la página a CMYK
                            pix = page.get_pixmap(colorspace=fitz.csCMYK)
                            img_pil = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                            imagenes_a_procesar.append((f"{arc.name} (Pág {page_num+1})", img_pil))
                    except Exception as e:
                        st.error(f"❌ Error leyendo PDF {arc.name}: {e}")
                
                # SI ES IMAGEN
                else:
                    try:
                        img_pil = Image.open(arc).convert('CMYK')
                        imagenes_a_procesar.append((arc.name, img_pil))
                    except Exception as e:
                        st.error(f"❌ Error con imagen {arc.name}: {e}")

                # ANALIZAR CADA PÁGINA/IMAGEN EXTRAÍDA
                for nombre_item, img in imagenes_a_procesar:
                    total_paginas_lote += 1
                    datos = np.array(img)
                    
                    # Promedio de canales
                    c = (np.mean(datos[:,:,0]) / 255) * 100
                    m = (np.mean(datos[:,:,1]) / 255) * 100
                    y = (np.mean(datos[:,:,2]) / 255) * 100
                    k = (np.mean(datos[:,:,3]) / 255) * 100
                    
                    # Multiplicador por modelo (Ajusta los ml según la máquina)
                    nombre_low = impresora_sel.lower()
                    multi = 2.5 if "j210" in nombre_low else (1.8 if "subli" in nombre_low else 1.2)
                    
                    # Cálculo de consumo y costo
                    consumo_ml = ((c + m + y + k) / 400) * 0.15 * multi 
                    costo_tinta = consumo_ml * precio_tinta_ml * (1 + 0.16 + 0.03) # IVA + IGTF
                    total_usd = costo_tinta + costo_desgaste
                    
                    resultados.append({
                        "Archivo": nombre_item,
                        "C%": f"{c:.1f}%", "M%": f"{m:.1f}%", "Y%": f"{y:.1f}%", "K%": f"{k:.1f}%",
                        "ml": round(consumo_ml, 4),
                        "Costo USD": round(total_usd, 4),
                        "Costo Bs": round(total_usd * t_bcv, 2)
                    })

        # --- MOSTRAR RESULTADOS ---
        if resultados:
            st.divider()
            df_res = pd.DataFrame(resultados)
            st.table(df_res) # Mostramos la tabla de costos por archivo
            
            total_lote_usd = df_res['Costo USD'].sum()
            total_ml_lote = df_res['ml'].sum()
            
            st.success(f"💰 Costo Total de Producción: **${total_lote_usd:.2f} USD** | **{(total_lote_usd * t_bcv):,.2f} Bs**")
            st.info(f"🧪 Consumo Total de Tinta: **{total_ml_lote:.2f} ml**")

            # Botón para pasar a Cotizaciones
            if st.button("📝 ENVIAR TODO A COTIZACIÓN"):
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Impresión: {len(archivos_multiples)} archivos ({total_paginas_lote} páginas)",
                    'costo_base': total_lote_usd,
                    'ml_estimados': total_ml_lote,
                    'unidades': total_paginas_lote
                }
                st.toast("✅ Datos enviados. ¡Ve a la pestaña Cotizaciones!")
# --- 12. LÓGICA DE ACTIVOS PERMANENTES ---
elif menu == "🏗️ Activos":
    # --- AGREGA ESTAS 3 LÍNEAS ---
    if ROL != "Admin":
        st.error("🚫 Acceso Denegado. Solo el Administrador puede gestionar activos fijos.")
        st.stop()
    st.title("🏗️ Gestión de Equipos y Activos")
    st.markdown("Los equipos registrados aquí se guardan permanentemente en la base de datos.")

    with st.expander("➕ Registrar Nuevo Equipo"):
        c1, c2 = st.columns(2)
        nombre_eq = c1.text_input("Nombre del Equipo")
        categoria = c2.selectbox("Categoría", ["Impresora (Gasta Tinta)", "Maquinaria (Solo Desgaste)", "Herramienta Manual"])
        
        c3, c4 = st.columns(2)
        moneda = c3.radio("¿Moneda?", ["USD ($)", "BS (Bs)"], horizontal=True)
        monto = c4.number_input("Monto Pagado", min_value=0.0)
        
        # Usamos t_bcv y t_bin que ya cargamos arriba
        costo_usd = monto if moneda == "USD ($)" else (monto / t_bcv if st.checkbox("¿Usar Tasa BCV?") else monto / t_bin)

        if categoria == "Impresora (Gasta Tinta)":
            unidad_medida = "Hojas"
        else:
            unidad_medida = st.selectbox("Se desgasta por cada:", ["Corte", "Laminado", "Uso", "Metro"])

        vida_util = st.number_input(f"Vida Útil Total ({unidad_medida})", min_value=1, value=5000)
        
        if st.button("💾 Guardar Equipo"):
            if nombre_eq:
                desgaste_u = costo_usd / vida_util
                conn = conectar()
                c = conn.cursor()
                c.execute("INSERT INTO activos (equipo, categoria, inversion, unidad, desgaste) VALUES (?,?,?,?,?)",
                          (nombre_eq, categoria, costo_usd, unidad_medida, desgaste_u))
                conn.commit(); conn.close()
                st.success(f"✅ {nombre_eq} guardado en la base de datos.")
                st.rerun()

    # --- Cargar y Mostrar de la Base de Datos ---
    conn = conectar()
    df_activos_db = pd.read_sql_query("SELECT id, equipo as 'Equipo', categoria as 'Categoría', inversion as 'Inversión ($)', unidad as 'Unidad', desgaste as 'Desgaste ($)' FROM activos", conn)
    conn.close()

    if not df_activos_db.empty:
        st.subheader("📋 Tus Activos Guardados")
        st.dataframe(df_activos_db.drop(columns=['id']), use_container_width=True, hide_index=True)
        
        if st.button("🗑️ Borrar Todos los Activos"):
            conn = conectar(); c = conn.cursor(); c.execute("DELETE FROM activos"); conn.commit(); conn.close()
            st.rerun()
# --- 13. LÓGICA DE OTROS PROCESOS (CAMEO, PLASTIFICADORA, ETC.) ---
elif menu == "🛠️ Otros Procesos":
    st.title("🛠️ Calculadora de Procesos Especiales")
    st.markdown("Calcula el costo de acabados usando los activos guardados.")

    # 1. Cargar activos desde la base de datos
    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, unidad, desgaste FROM activos", conn)
    conn.close()
    
    lista_activos = df_act_db.to_dict('records')
    # Filtramos activos que NO son impresoras
    otros_equipos = [e for e in lista_activos if e['categoria'] != "Impresora (Gasta Tinta)"]

    if not otros_equipos:
        st.warning("⚠️ No hay maquinaria registrada (Cameo, Plastificadora, etc.) en '🏗️ Activos'.")
    else:
        # TODO el formulario debe estar dentro de este 'with'
        with st.form("form_procesos_fijo"):
            col1, col2, col3 = st.columns(3)
            
            # Nombres de equipos usando minúsculas 'equipo'
            nombres_eq = [e['equipo'] for e in otros_equipos]
            eq_sel = col1.selectbox("Herramienta / Máquina", nombres_eq)
            
            # Buscamos los datos de esa máquina
            datos_eq = next(e for e in otros_equipos if e['equipo'] == eq_sel)
            
            unidad = datos_eq['unidad']
            costo_u = datos_eq['desgaste']

            cantidad_uso = col2.number_input(f"Cantidad de {unidad}", min_value=1, value=1)
            
            # Insumos (usando el df_inv que cargas al inicio de la app)
            insumos = ["-- Ninguno --"] + df_inv['item'].tolist()
            insumo_sel = col3.selectbox("Insumo extra", insumos)
            cant_insumo = col3.number_input("Cantidad de insumo", min_value=0.0, value=0.0)

            # EL BOTÓN DEBE ESTAR DENTRO DEL FORMULARIO
            boton_calcular = st.form_submit_button("💎 Calcular Costo de Proceso")

        # Lógica después de presionar el botón
        if boton_calcular:
            # Cálculo de desgaste
            total_desgaste = costo_u * cantidad_uso
            
            # Cálculo de insumo
            total_insumo = 0.0
            if insumo_sel != "-- Ninguno --":
                # Buscamos el precio en el inventario
                precio_u_insumo = df_inv[df_inv['item'] == insumo_sel]['precio_usd'].values[0]
                total_insumo = precio_u_insumo * cant_insumo
            
            costo_total = total_desgaste + total_insumo
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Desgaste {eq_sel}", f"$ {total_desgaste:.4f}")
            c2.metric("Costo Insumos", f"$ {total_insumo:.4f}")
            c3.metric("COSTO TOTAL", f"$ {costo_total:.2f}")
            
            st.success(f"💡 Tu costo base es **$ {costo_total:.2f}**. ¡Añade tu margen de ganancia!")


elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Presupuestos")
    
    # Si venimos del Analizador CMYK, precargamos los datos
    datos_cmyk = st.session_state.get('datos_pre_cotizacion', {})
    
    with st.expander("💎 Datos del Trabajo", expanded=True):
        col1, col2 = st.columns(2)
        desc = col1.text_input("Trabajo:", value=datos_cmyk.get('trabajo', ""))
        
        # Validación de seguridad para la lista de clientes
        lista_clientes = st.session_state.df_cli['nombre'].tolist() if not st.session_state.df_cli.empty else ["Cliente Genérico"]
        cliente = col2.selectbox("Cliente:", lista_clientes)
        
        st.divider()
        
        # --- ENTRADA DE DATOS PARA EL MOTOR ---
        c1, c2, c3 = st.columns(3)
        # 1. Recuperamos el costo base (ya sea del Analizador CMYK o manual)
        costo_base = c1.number_input("Costo Base de Producción ($)", 
                                    value=float(datos_cmyk.get('costo_base', 0.0)), 
                                    format="%.4f")
        
        # 2. Definimos el margen (Aquí es donde evitamos duplicar)
        margen_ganancia = c2.number_input("Margen de Ganancia (%)", min_value=0, value=100)
        
        # 3. Opción de impuestos
        incluir_impuestos = c3.checkbox("¿Aplicar Impuestos? (IVA/IGTF/Banc)", value=True)

        # --- LLAMADA ÚNICA AL MOTOR (Cero duplicidad) ---
        # El motor recibe Costo -> Suma Margen -> Suma Impuestos (si aplica)
        precio_final_usd = calcular_precio_con_impuestos(costo_base, margen_ganancia, incluir_impuestos)

        # --- RESULTADOS VISUALES ---
        st.divider()
        res1, res2, res3 = st.columns(3)
        res1.metric("Costo Real", f"$ {costo_base:.2f}")
        res2.metric("PRECIO VENTA (USD)", f"$ {precio_final_usd:.2f}", delta=f"Ganancia: ${(precio_final_usd/(1.21 if incluir_impuestos else 1) - costo_base):.2f}")
        res3.metric("PRECIO VENTA (BS)", f"Bs {(precio_final_usd * t_bcv):,.2f}")
        if st.button("💾 Guardar Cotización"):
            st.success("Cotización guardada exitosamente (Simulado)")

if menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    
    with st.form("nueva_venta"):
        col1, col2 = st.columns(2)
        # 1. Selección de producto (traído del inventario)
        item_sel = col1.selectbox("Producto Vendido", st.session_state.df_inv['item'].tolist())
        cant_vender = col2.number_input("Cantidad", min_value=0.1, step=1.0)
        
        # 2. Datos financieros
        monto_venta = col1.number_input("Monto Total Cobrado ($)", min_value=0.0)
        metodo = col2.selectbox("Método de Pago", ["Efectivo", "Zelle", "Pago Móvil", "Transferencia"])
        
        if st.form_submit_button("💳 FINALIZAR VENTA ATÓMICA"):
            if item_sel and cant_vender > 0:
                # OBTENEMOS EL ID DEL ITEM
                item_id = st.session_state.df_inv[st.session_state.df_inv['item'] == item_sel]['id'].values[0]
                
                # --- PASO CRÍTICO: IMPACTO EN INVENTARIO ---
                # Usamos el motor con cantidad negativa para restar
                exito_stock, mensaje_stock = ejecutar_movimiento_stock(
                    item_id, 
                    -cant_vender, 
                    "SALIDA", 
                    motivo=f"Venta a {metodo}"
                )
                
                if exito_stock:
                    # SI EL STOCK FUE EXITOSO, GUARDAMOS LA VENTA
                    try:
                        conn = conectar()
                        cur = conn.cursor()
                        cur.execute("""INSERT INTO ventas (fecha, producto_id, cantidad, monto_total, metodo) 
                                       VALUES (?, ?, ?, ?, ?)""", 
                                    (datetime.now(), item_id, cant_vender, monto_venta, metodo))
                        conn.commit()
                        conn.close()
                        st.success("✅ Venta registrada y stock descontado.")
                        cargar_datos_seguros()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar venta: {e}")
                else:
                    # SI EL MOTOR DIJO QUE NO HAY STOCK, BLOQUEAMOS TODO
                    st.error(f"❌ VENTA CANCELADA: {mensaje_stock}")


# --- 14. MÓDULO DE CIERRE DE CAJA ---
elif menu == "🏁 Cierre de Caja":
    st.title("🏁 Cierre de Jornada y Balance")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn = conectar()
        # 1. Ventas del día
        query_v = f"SELECT * FROM ventas WHERE date(fecha) = '{fecha_hoy}'"
        df_ventas_dia = pd.read_sql(query_v, conn)
        
        # 2. Movimientos de inventario del día
        query_m = f"""
            SELECT i.item, m.tipo, m.cantidad, m.usuario 
            FROM inventario_movs m 
            LEFT JOIN inventario i ON m.item_id = i.id 
            WHERE date(m.fecha) = '{fecha_hoy}'
        """
        df_movs_dia = pd.read_sql(query_m, conn)
        conn.close()
    except Exception as e:
        st.warning("Iniciando balance del día...")
        df_ventas_dia = pd.DataFrame(columns=['monto_total', 'metodo'])
        df_movs_dia = pd.DataFrame(columns=['item', 'tipo', 'cantidad', 'usuario'])

    # --- MÉTRICAS ---
    c1, c2, c3 = st.columns(3) 
    
    total_usd = df_ventas_dia['monto_total'].sum() if not df_ventas_dia.empty else 0.0
    
    c1.metric("💰 Ventas Totales", f"$ {total_usd:.2f}")
    c2.metric("📦 Movimientos de Stock", len(df_movs_dia))
    c3.metric("🧾 Facturas Emitidas", len(df_ventas_dia))

    # 3. Arqueo por Método de Pago
    st.subheader("💵 Arqueo por Método de Pago")
    if not df_ventas_dia.empty:
        arqueo = df_ventas_dia.groupby('metodo')['monto_total'].sum().reset_index()
        st.table(arqueo)
    else:
        st.info("No hay ventas registradas hoy.")

    # 4. Auditoría de Insumos
    st.subheader("📋 Consumo de Almacén hoy")
    if not df_movs_dia.empty:
        st.dataframe(df_movs_dia, use_container_width=True, hide_index=True)
    else:
        st.info("No hubo movimientos de inventario hoy.")

    # 5. Botón de Cierre Oficial y Exportación
    st.divider()
    if st.button("🔒 Ejecutar Cierre y Generar Reporte"):
        st.success(f"✅ Cierre de caja del {fecha_hoy} completado con éxito.")
        
        # Generación de CSV para respaldo físico
        csv = df_ventas_dia.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Reporte de Ventas (CSV)",
            data=csv,
            file_name=f"cierre_{fecha_hoy}.csv",
            mime="text/csv",
        )
# --- 15. MÓDULO DE GASTOS ---
elif menu == "📉 Gastos":
    st.title("📉 Registro de Egresos")
    
    with st.form("nuevo_gasto"):
        col1, col2 = st.columns(2)
        desc = col1.text_input("Descripción del Gasto", placeholder="Ej: Pago de Local, Electricidad...")
        monto = col2.number_input("Monto en Dólares ($)", min_value=0.0, format="%.2f")
        
        cat = st.selectbox("Categoría", ["Servicios", "Local", "Sueldos", "Mantenimiento", "Otros"])
        metodo_g = st.radio("Pagado desde:", ["Efectivo", "Zelle", "Pago Móvil", "Banesco"], horizontal=True)
        
        if st.form_submit_button("💸 Registrar Egreso"):
            if desc and monto > 0:
                conn = conectar()
                cur = conn.cursor()
                fecha_g = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute("INSERT INTO gastos (descripcion, monto, categoria, metodo, fecha) VALUES (?,?,?,?,?)",
                            (desc, monto, cat, metodo_g, fecha_g))
                conn.commit()
                conn.close()
                st.success(f"Gasto de $ {monto} registrado.")
                st.rerun()

    # Historial de Gastos del Mes
    st.subheader("📋 Historial de Egresos")
    conn = conectar()
    df_g = pd.read_sql("SELECT descripcion, monto, categoria, metodo, fecha FROM gastos ORDER BY id DESC LIMIT 20", conn)
    conn.close()
    
    if not df_g.empty:
        st.dataframe(df_g, use_container_width=True, hide_index=True)


























