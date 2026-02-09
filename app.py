import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime
import numpy as np
import io
from PIL import Image

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide", page_icon="⚛️")

# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    # Creación de Tablas
    c.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, 
                unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)""")
    c.execute("CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)")
    c.execute("""CREATE TABLE IF NOT EXISTS activos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, 
                inversion REAL, unidad TEXT, desgaste REAL)""")
    c.execute("CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS inventario_movs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, 
                cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, 
                metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, 
                categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    # Trigger de Seguridad de Stock
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_negative_stock
        BEFORE UPDATE ON inventario
        FOR EACH ROW
        BEGIN
            SELECT CASE WHEN NEW.cantidad < 0 THEN RAISE(ABORT, 'Error: Stock insuficiente.') END;
        END;
    """)

    # Usuarios iniciales (Solo se insertan si la tabla está vacía)
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO usuarios VALUES (?,?,?,?)", [
            ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio'),
            ('mama', 'admin2026', 'Administracion', 'Mamá'),
            ('pro', 'diseno2026', 'Produccion', 'Hermana')
        ])

    # Configuración de Inflación y Costos
    config_init = [
        ('tasa_bcv', 36.50), ('tasa_binance', 38.00), ('iva_perc', 0.16),
        ('igtf_perc', 0.03), ('banco_perc', 0.005), ('costo_tinta_ml', 0.10)
    ]
    for param, valor in config_init:
        c.execute("INSERT OR IGNORE INTO configuracion (parametro, valor) VALUES (?,?)", (param, valor))

    conn.commit()
    conn.close()

# --- CONTINUACIÓN Y CIERRE DE 3. FUNCIONES DE LÓGICA DE NEGOCIO ---

def obtener_tintas_disponibles():
    """Filtra el inventario de forma segura para el Analizador CMYK."""
    # 1. Verificamos si los datos ya están en memoria
    if 'df_inv' not in st.session_state:
        cargar_datos()
    
    df = st.session_state.df_inv
    
    # 2. Si el DataFrame existe pero está vacío, devolvemos uno vacío con columnas
    if df is None or df.empty:
        return pd.DataFrame(columns=['id', 'item', 'cantidad', 'unidad', 'precio_usd'])
    
    # 3. Filtramos solo lo que sea tinta (unidad ml)
    df_copy = df.copy()
    df_copy['unidad_check'] = df_copy['unidad'].fillna('').str.strip().str.lower()
    return df_copy[df_copy['unidad_check'] == 'ml']

def actualizar_configuracion(parametro, nuevo_valor):
    """Guarda cambios de inflación/precios en la DB y sesión."""
    try:
        conn = conectar()
        c = conn.cursor()
        c.execute("UPDATE configuracion SET valor = ? WHERE parametro = ?", (nuevo_valor, parametro))
        conn.commit()
        conn.close()
        # Actualizamos la sesión para que el cambio sea inmediato en los cálculos
        st.session_state[parametro] = nuevo_valor
        return True
    except Exception as e:
        st.error(f"Error al actualizar {parametro}: {e}")
        return False

def obtener_activos_impresion():
    """Retorna las máquinas registradas para el selector del CMYK."""
    try:
        conn = conectar()
        df = pd.read_sql("SELECT equipo, desgaste FROM activos WHERE categoria = 'Impresora (Gasta Tinta)'", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame(columns=['equipo', 'desgaste'])

# --- 4. CONTROL DE FLUJO ---

# Inicialización por primera vez
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    inicializar_sistema()

# Forzar login si no está autenticado
if not st.session_state.autenticado:
    login()
    st.stop()

# Carga de datos tras autenticación
if 'df_inv' not in st.session_state:
    cargar_datos()

# Variables Globales de uso frecuente
t_bcv = st.session_state.get('tasa_bcv', 1.0)
t_bin = st.session_state.get('tasa_binance', 1.0)
ROL = st.session_state.get('rol', "")

# --- 5. SIDEBAR (NAVEGACIÓN) ---

with st.sidebar:
    st.header(f"👋 {st.session_state.usuario_nombre}")
    st.caption(f"Rol: {ROL}")
    
    # Visualizador de Tasas (Inflación)
    with st.container(border=True):
        st.write("📈 **Tasas del Día**")
        st.write(f"🏦 BCV: **{t_bcv:.2f}**")
        st.write(f"🔶 Bin: **{t_bin:.2f}**")

    # Lógica de Menú según Rol
    opciones = ["📝 Cotizaciones", "🎨 Análisis CMYK", "👥 Clientes"]
    
    if ROL in ["Admin", "Administracion"]:
        opciones += ["💰 Ventas", "📉 Gastos", "📦 Inventario", "📊 Dashboard", "🏗️ Activos", "⚙️ Configuración"]

    menu = st.radio("Ir a:", opciones)

    st.divider()
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.clear() # Limpia todo para seguridad
        st.rerun()

# --- 6. MÓDULO INVENTARIO ---
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    
    df_inv = st.session_state.get('df_inv', pd.DataFrame())

    # --- PANEL DE CONTROL FINANCIERO ---
    with st.container(border=True):
        c_tasa, c_val, c_alert = st.columns([1.5, 1, 1])
        with c_tasa:
            moneda_ver = st.radio("💰 Ver costos en:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], horizontal=True, key="moneda_inv")
            tasa_ver = 1.0 if "USD" in moneda_ver else (t_bcv if "BCV" in moneda_ver else t_bin)
            simbolo = "$" if "USD" in moneda_ver else "Bs"
        
        if not df_inv.empty:
            valor_inventario = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
            c_val.metric("Valor del Taller", f"{simbolo} {(valor_inventario * tasa_ver):,.2f}")
            
            criticos = len(df_inv[df_inv['cantidad'] <= df_inv['minimo']])
            c_alert.metric("⚠️ Reposición Urgente", f"{criticos} Items")

    st.divider()

    # DEFINICIÓN DE TABS (Esto es lo que faltaba arriba para que no diera error)
    tab_existencia, tab_compra, tab_mermas, tab_edicion = st.tabs([
        "📋 Stock", "📥 Compra", "📉 Mermas", "🛠️ Modificar/Borrar"
    ])

    # --- TAB 1: STOCK ---
    with tab_existencia:
        if not df_inv.empty:
            busqueda = st.text_input("🔍 Buscar material...", placeholder="Ej: Glase, Taza, Vinil...", key="search_bar")
            df_ver = df_inv.copy()
            if busqueda:
                df_ver = df_ver[df_ver['item'].str.contains(busqueda, case=False)]

            df_ver['Costo Reposición'] = df_ver['precio_usd'] * tasa_ver
            st.dataframe(df_ver, hide_index=True, use_container_width=True)
        else:
            st.info("No hay materiales en el sistema.")

    # --- TAB 2: COMPRA ---
    with tab_compra:
        st.subheader("📥 Registro de Factura / Compra")
        with st.form("form_compra_vzla"):
            col1, col2 = st.columns([2, 1])
            nombre_it = col1.text_input("Nombre del Insumo")
            unidad_it = col2.selectbox("Presentación:", ["ml", "Hojas", "Resma", "Unidad", "Metros"])
            
            f1, f2, f3 = st.columns(3)
            monto_fac = f1.number_input("Monto Factura", min_value=0.0)
            moneda_fac = f2.selectbox("Pagado en:", ["USD $", "Bs (BCV)", "Bs (Binance)"])
            impuesto = f3.selectbox("Extras:", ["Ninguno", "16% IVA", "3% IGTF", "Envío/Delivery"])
            
            q1, q2, q3 = st.columns(3)
            cant_recibida = q1.number_input("Cantidad total", min_value=0.1)
            stock_min_alerta = q2.number_input("Mínimo Seguridad", value=5.0)
            comision_pago = q3.slider("% Comisión Pago", 0.0, 5.0, 0.5)

            if st.form_submit_button("💾 GUARDAR COMPRA"):
                if nombre_it and cant_recibida > 0:
                    t_momento = t_bcv if "BCV" in moneda_fac else (t_bin if "Binance" in moneda_fac else 1.0)
                    costo_base_usd = (monto_fac / t_momento) * (1 + (comision_pago/100))
                    p_unit_usd = costo_base_usd / cant_recibida

                    conn = conectar()
                    conn.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                                 VALUES (?, ?, ?, ?, ?) ON CONFLICT(item) DO UPDATE SET 
                                 cantidad = cantidad + ?, precio_usd = ?, minimo = ?""", 
                              (nombre_it, cant_recibida, unidad_it, p_unit_usd, stock_min_alerta, 
                               cant_recibida, p_unit_usd, stock_min_alerta))
                    conn.commit()
                    conn.close()
                    st.success("✅ Compra registrada.")
                    cargar_datos_seguros()
                    st.rerun()

    # --- TAB 3: MERMAS ---
    with tab_mermas:
        st.subheader("📉 Registrar Material Dañado")
        if not df_inv.empty:
            with st.form("form_merma"):
                item_m = st.selectbox("Seleccionar item:", df_inv['item'].tolist(), key="select_merma")
                cant_m = st.number_input("Cantidad perdida:", min_value=0.1)
                if st.form_submit_button("🗑️ Descontar Merma"):
                    conn = conectar()
                    conn.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE item = ?", (cant_m, item_m))
                    conn.commit()
                    conn.close()
                    st.warning("Merma registrada.")
                    cargar_datos_seguros()
                    st.rerun()

    # --- TAB 4: MODIFICAR O BORRAR (EL SALVAVIDAS) ---
    with tab_edicion:
        st.subheader("🛠️ Maestro de Edición")
        if not df_inv.empty:
            item_a_editar = st.selectbox("Item a corregir:", df_inv['item'].tolist(), key="select_master_edit")
            datos_actuales = df_inv[df_inv['item'] == item_a_editar].iloc[0]

            with st.form("form_maestro_edit"):
                st.info(f"Editando ID: {datos_actuales['id']}")
                new_nombre = st.text_input("Nuevo Nombre:", value=datos_actuales['item'])
                
                c_e1, c_e2, c_e3 = st.columns(3)
                new_qty = c_e1.number_input("Existencia Real:", value=float(datos_actuales['cantidad']))
                new_prc = c_e2.number_input("Costo Unit. ($):", value=float(datos_actuales['precio_usd']), format="%.4f")
                new_min = c_e3.number_input("Mínimo:", value=float(datos_actuales['minimo']))
                
                new_und = st.selectbox("Unidad:", ["ml", "Hojas", "Resma", "Unidad", "Metros"], 
                                     index=["ml", "Hojas", "Resma", "Unidad", "Metros"].index(datos_actuales['unidad']))

                col_btn1, col_btn2 = st.columns(2)
                
                if col_btn1.form_submit_button("💾 GUARDAR CAMBIOS", use_container_width=True):
                    conn = conectar()
                    conn.execute("""UPDATE inventario SET item=?, cantidad=?, unidad=?, precio_usd=?, minimo=? 
                                 WHERE id=?""", (new_nombre, new_qty, new_und, new_prc, new_min, datos_actuales['id']))
                    conn.commit()
                    conn.close()
                    st.success("✅ Cambios aplicados correctamente.")
                    cargar_datos_seguros()
                    st.rerun()

                if col_btn2.form_submit_button("🗑️ ELIMINAR ÍTEM", use_container_width=True):
                    conn = conectar()
                    conn.execute("DELETE FROM inventario WHERE id=?", (datos_actuales['id'],))
                    conn.commit()
                    conn.close()
                    st.error(f"❌ Ítem eliminado.")
                    cargar_datos_seguros()
                    st.rerun()

elif menu == "📊 Dashboard":
    st.title("📊 Centro de Control Financiero")

    conn = conectar()
    # Cargamos datos con fechas parseadas para poder graficar
    df_ventas = pd.read_sql("SELECT * FROM ventas", conn, parse_dates=['fecha'])
    df_gastos = pd.read_sql("SELECT * FROM gastos", conn, parse_dates=['fecha'])
    conn.close()

    # --- MÉTRICAS PRINCIPALES ---
    ingresos = df_ventas['monto_total'].sum() if not df_ventas.empty else 0
    egresos = df_gastos['monto'].sum() if not df_gastos.empty else 0
    balance = ingresos - egresos

    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Totales", f"$ {ingresos:,.2f}")
    c2.metric("Egresos Totales", f"$ {egresos:,.2f}", delta=f"-{egresos:,.2f}", delta_color="inverse")
    c3.metric("Utilidad Neta", f"$ {balance:,.2f}", delta=f"{(balance/ingresos*100 if ingresos>0 else 0):.1f}% Margen")

    st.divider()

    # --- GRÁFICOS ---
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("📈 Tendencia de Ventas ($)")
        if not df_ventas.empty:
            # Agrupamos por día para ver el crecimiento
            df_ventas['fecha_dia'] = df_ventas['fecha'].dt.date
            ventas_diarias = df_ventas.groupby('fecha_dia')['monto_total'].sum()
            st.line_chart(ventas_diarias)
        else:
            st.info("No hay datos de ventas para graficar.")

    with col_g2:
        st.subheader("💳 Ventas por Método")
        if not df_ventas.empty:
            metodos = df_ventas.groupby('metodo')['monto_total'].sum()
            st.bar_chart(metodos)
        else:
            st.info("Sin datos de métodos de pago.")

    # --- TABLA DE ÚLTIMOS MOVIMIENTOS ---
    st.divider()
    st.subheader("📑 Últimos Movimientos")
    
    tab_v, tab_g = st.tabs(["Últimas Ventas", "Últimos Gastos"])
    
    with tab_v:
        if not df_ventas.empty:
            st.dataframe(df_ventas.sort_values('fecha', ascending=False).head(10), use_container_width=True)
    
    with tab_g:
        if not df_gastos.empty:
            st.dataframe(df_gastos.sort_values('fecha', ascending=False).head(10), use_container_width=True)

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
# --- 9. LÓGICA DE ACTIVOS (EQUIPOS Y MAQUINARIA) ---
elif menu == "🏗️ Activos":

    if ROL != "Admin":
        st.error("🚫 Acceso Denegado. Solo la Jefa puede gestionar los activos del Imperio.")
        st.stop()

    st.title("🏗️ Gestión de Activos y Equipos")
    st.info("💡 Registra aquí tus máquinas para calcular automáticamente el costo de desgaste por cada impresión o uso.")

    # --- FORMULARIO DE REGISTRO ---
    with st.expander("➕ Registrar Nuevo Equipo o Herramienta"):
        with st.form("form_activos"):
            c1, c2 = st.columns(2)
            nombre_eq = c1.text_input("Nombre del Equipo (Ej: Epson L805)")
            categoria = c2.selectbox("Categoría", [
                "Impresora (Gasta Tinta)",
                "Maquinaria (Solo Desgaste)",
                "Herramienta Manual",
                "Mobiliario"
            ])

            col_m1, col_m2 = st.columns(2)
            monto_inv = col_m1.number_input("Inversión / Costo ($)", min_value=0.0, format="%.2f")
            # La vida útil es cuántas veces se puede usar antes de que se pague sola
            vida_util_estimada = col_m2.number_input("Vida Útil (Cant. de usos/impresiones)", min_value=1, value=5000)

            st.caption("ℹ️ El sistema calculará el costo de 'Desgaste' dividiendo la inversión entre la vida útil.")

            if st.form_submit_button("🚀 Guardar Equipo"):
                if nombre_eq and monto_inv > 0:
                    # Cálculo del desgaste por cada uso
                    desgaste_u = monto_inv / vida_util_estimada
                    
                    conn = conectar()
                    try:
                        c = conn.cursor()
                        c.execute(
                            "INSERT INTO activos (equipo, categoria, inversion, unidad, desgaste) VALUES (?,?,?,?,?)",
                            (nombre_eq, categoria, monto_inv, "uso", desgaste_u)
                        )
                        conn.commit()
                        st.success(f"✅ {nombre_eq} registrado. Cada uso sumará ${desgaste_u:.4f} al costo de producción.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("⚠️ Debes indicar el nombre y el monto de inversión.")

    # --- VISTA DE ACTIVOS EXISTENTES ---
    st.divider()
    st.subheader("📋 Equipos Registrados")
    
    conn = conectar()
    df_activos = pd.read_sql_query("SELECT id, equipo, categoria, inversion, desgaste FROM activos", conn)
    conn.close()

    if not df_activos.empty:
        # Renombrar columnas para que se vean bien en la tabla
        df_ver = df_activos.copy().rename(columns={
            'equipo': 'Nombre',
            'categoria': 'Tipo',
            'inversion': 'Inversión ($)',
            'desgaste': 'Costo/Uso ($)'
        })
        
        st.dataframe(df_ver, use_container_width=True, hide_index=True)
        
        # Opción para eliminar
        with st.expander("🗑️ Dar de baja un equipo"):
            id_borrar = st.selectbox("Selecciona equipo a eliminar:", df_activos['id'].tolist(), 
                                     format_func=lambda x: df_activos[df_activos['id']==x]['equipo'].values[0])
            if st.button("Confirmar Eliminación", type="primary"):
                conn = conectar()
                conn.execute("DELETE FROM activos WHERE id = ?", (id_borrar,))
                conn.commit()
                conn.close()
                st.warning("Equipo eliminado del sistema.")
                st.rerun()
    else:
        st.info("Aún no has registrado ningún equipo.")

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

# --- 7. MÓDULO DE VENTAS (REGISTRO MANUAL) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    st.info("Utiliza este módulo para registrar ventas directas que no pasaron por el cotizador CMYK.")

    # Verificamos si hay clientes cargados
    if st.session_state.df_cli.empty:
        st.warning("⚠️ No hay clientes registrados. Ve al menú '👥 Clientes' primero.")
    else:
        with st.form("venta_manual", clear_on_submit=True):
            st.subheader("📝 Detalles de la Transacción")
            
            # Selector de cliente con ID oculto para mayor precisión
            opciones_cli = {row['nombre']: row['id'] for _, row in st.session_state.df_cli.iterrows()}
            cliente_nombre = st.selectbox("Seleccionar Cliente:", options=list(opciones_cli.keys()))
            
            c1, c2 = st.columns(2)
            monto_venta = c1.number_input("Monto Total ($):", min_value=0.01, format="%.2f", step=0.5)
            metodo_pago = c2.selectbox("Método de Pago:", [
                "Efectivo ($)", 
                "Pago Móvil (BCV)", 
                "Zelle", 
                "Binance (USDT)", 
                "Transferencia (Bs)"
            ])

            st.divider()
            
            # Cálculo informativo de la tasa en el momento
            tasa_momento = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (t_bin if "Binance" in metodo_pago else 1.0)
            if tasa_momento > 1.0:
                st.caption(f"💡 El cliente debe pagar aproximadamente: **Bs {(monto_venta * tasa_momento):,.2f}**")

            if st.form_submit_button("🚀 REGISTRAR VENTA"):
                cliente_id = opciones_cli[cliente_nombre]
                
                conn = conectar()
                try:
                    c = conn.cursor()
                    # Insertamos la venta incluyendo el método de pago
                    c.execute("""
                        INSERT INTO ventas (cliente_id, monto_total, metodo) 
                        VALUES (?, ?, ?)
                    """, (cliente_id, monto_venta, metodo_pago))
                    
                    conn.commit()
                    st.success(f"✅ Venta de ${monto_venta} registrada a {cliente_nombre}")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Error al guardar la venta: {e}")
                finally:
                    conn.close()

    # --- HISTORIAL RÁPIDO ---
    st.divider()
    st.subheader("📂 Últimas Ventas Registradas")
    conn = conectar()
    df_recientes = pd.read_sql_query("""
        SELECT v.fecha, c.nombre as Cliente, v.monto_total as 'Monto ($)', v.metodo as 'Método'
        FROM ventas v
        JOIN clientes c ON v.cliente_id = c.id
        ORDER BY v.fecha DESC LIMIT 5
    """, conn)
    conn.close()
    
    if not df_recientes.empty:
        st.table(df_recientes)


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

# --- 13. AUDITORÍA Y MÉTRICAS ---
elif menu == "📊 Auditoría y Métricas":
    st.title("📊 Auditoría de Producción e Insumos")
    st.info("Rastrea cada mililitro de tinta y unidad de material utilizado en el taller.")

    conn = conectar()
    query_movs = """
        SELECT 
            m.fecha, 
            i.item AS 'Material', 
            m.tipo AS 'Operación',
            m.cantidad AS 'Cant.', 
            i.unidad AS 'Unidad',
            m.motivo AS 'Motivo'
        FROM inventario_movs m
        JOIN inventario i ON m.item_id = i.id
        ORDER BY m.fecha DESC
    """
    df_movs = pd.read_sql_query(query_movs, conn)
    conn.close()

    tab_graficos, tab_historial, tab_alertas = st.tabs(["📈 Análisis Visual", "📋 Historial Detallado", "🚨 Alertas de Stock"])

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
        else:
            st.info("Sin datos.")

    with tab_historial:
        st.subheader("📜 Bitácora de Movimientos")
        if not df_movs.empty:
            # Función simple para colorear filas
            def color_operacion(val):
                color = 'background-color: #90ee90' if val == 'ENTRADA' else 'background-color: #ffcccb'
                return color

            st.dataframe(
                df_movs.style.applymap(color_operacion, subset=['Operación']),
                use_container_width=True,
                hide_index=True
            )

    with tab_alertas:
        st.subheader("🚨 Insumos en Niveles Críticos")
        df_inv = st.session_state.get('df_inv', pd.DataFrame())
        
        if not df_inv.empty:
            # Alerta si queda menos de 20 unidades/ml
            critico = df_inv[df_inv['cantidad'] < 20.0] 
            if not critico.empty:
                for _, row in critico.iterrows():
                    st.error(f"**{row['item']}** bajo: ¡Solo quedan {row['cantidad']} {row['unidad']}!")
            else:
                st.success("✅ Niveles de inventario óptimos.")

# --- 7. COTIZACIONES ---
elif menu == "📝 Cotizaciones":

    st.title("📝 Cotizador de Trabajos")

    datos_pre = st.session_state.get('datos_pre_cotizacion', {
        'trabajo': "Trabajo General",
        'costo_base': 0.0,
        'c_ml': 0.0,
        'm_ml': 0.0,
        'y_ml': 0.0,
        'k_ml': 0.0,
        'unidades': 1
    })

    # 🔑 Detectar si el trabajo usa tinta
    usa_tinta = any([
        datos_pre['c_ml'],
        datos_pre['m_ml'],
        datos_pre['y_ml'],
        datos_pre['k_ml']
    ])

    # --- DETALLES DEL TRABAJO ---
    with st.container():
        st.subheader("🛠️ Detalles del Trabajo")

        col1, col2 = st.columns([2, 1])

        with col1:
            descr = st.text_input(
                "Descripción del trabajo:",
                value=datos_pre['trabajo']
            )

            df_clis = st.session_state.get('df_cli', pd.DataFrame())

            if not df_clis.empty:
                opciones_cli = {
                    row['nombre']: row['id']
                    for _, row in df_clis.iterrows()
                }
                cliente_sel = st.selectbox(
                    "👤 Asignar a Cliente:",
                    opciones_cli.keys()
                )
                id_cliente = opciones_cli[cliente_sel]
            else:
                st.warning("⚠️ No hay clientes registrados.")
                st.stop()

        with col2:
            unidades = st.number_input(
                "Cantidad de piezas:",
                min_value=1,
                value=int(datos_pre['unidades'])
            )

    # --- CONSUMO DE INSUMOS ---
    st.subheader("📦 Consumo de Insumos")
    consumos_reales = {}

    if usa_tinta:
        st.info("🎨 Este trabajo consume tinta")

        df_tintas = obtener_tintas_disponibles()

        if df_tintas.empty:
            st.error("🚨 No hay tintas (unidad ml) registradas en inventario.")
            st.stop()

        dict_t = {
            f"{r['item']} ({r['cantidad']:.1f} ml)": r['id']
            for _, r in df_tintas.iterrows()
        }

        if any([
            datos_pre['c_ml'],
            datos_pre['m_ml'],
            datos_pre['y_ml'],
            datos_pre['k_ml']
        ]):
            st.info("🎨 Se detectó análisis CMYK. Asigne las botellas físicas:")

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
            st.warning("⚠️ Sin datos CMYK. Despacho manual:")

            t_gen = st.selectbox(
                "Seleccione Tinta:",
                ["Ninguno"] + list(dict_t.keys())
            )

            if t_gen != "Ninguno":
                ml_manual = st.number_input(
                    "ML totales a descontar:",
                    min_value=0.0
                )
                consumos_reales[dict_t[t_gen]] = ml_manual

    else:
        st.success("📄 Trabajo sin consumo de tinta (resma, vinil, procesos secos)")

    # --- COSTOS Y PRECIOS ---
    st.subheader("💰 Costos y Precios")

    c1, c2 = st.columns(2)

    costo_unitario_base = c1.number_input(
        "Costo Unitario Base ($)",
        value=float(
            datos_pre['costo_base'] / unidades
            if unidades > 0 else 0.0
        ),
        format="%.4f"
    )

    margen = c2.slider(
        "Margen de Ganancia %",
        10, 500, 100, 10
    )

    costo_total_prod = costo_unitario_base * unidades
    precio_venta_total = costo_total_prod * (1 + margen / 100)

    st.divider()

    v1, v2, v3 = st.columns(3)
    v1.metric("Costo Producción", f"$ {costo_total_prod:.2f}")
    v2.metric("Precio Venta Total", f"$ {precio_venta_total:.2f}")
    v3.metric("Total Bs (BCV)", f"Bs {(precio_venta_total * t_bcv):,.2f}")

    # --- PROCESAR VENTA ---
    st.divider()

    metodo_pago = st.selectbox(
        "💳 Cobro vía:",
        ["Efectivo $", "Zelle", "Pago Móvil", "Transferencia Bs", "Binance"]
    )

    llave_operacion = f"{id_cliente}_{precio_venta_total}_{unidades}_{descr}"

    if st.button("🚀 CONFIRMAR VENTA Y DESCONTAR INVENTARIO"):

        if usa_tinta and not consumos_reales:
            st.error("❌ Debe asignar las tintas a descontar.")
            st.stop()

        exito, msg = procesar_venta_grafica_completa(
            id_cliente=id_cliente,
            monto=precio_venta_total,
            metodo=metodo_pago,
            consumos_dict=consumos_reales
        )

        if exito:
            st.success(msg)
            cargar_datos_seguros()

            if 'datos_pre_cotizacion' in st.session_state:
                del st.session_state['datos_pre_cotizacion']

            st.rerun()
        else:
            st.error(msg)

    if st.button("🗑️ Cancelar Todo"):
        if 'datos_pre_cotizacion' in st.session_state:
            del st.session_state['datos_pre_cotizacion']
        st.rerun()
















