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

# --- 3. FUNCIONES DE LÓGICA DE NEGOCIO ---

def cargar_datos():
    """Actualiza las variables de estado desde la DB."""
    conn = conectar()
    st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
    st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
    conf = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')
    st.session_state.tasa_bcv = float(conf.loc['tasa_bcv', 'valor'])
    st.session_state.tasa_binance = float(conf.loc['tasa_binance', 'valor'])
    st.session_state.costo_tinta_ml = float(conf.loc['costo_tinta_ml', 'valor'])
    conn.close()

def login():
    """Pantalla de acceso principal."""
    st.title("🛡️ Acceso al Imperio Atómico")
    with st.form("login_form"):
        user = st.text_input("Usuario")
        pw = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar al Sistema"):
            conn = conectar()
            u_data = pd.read_sql_query("SELECT * FROM usuarios WHERE username=? AND password=?", 
                                     conn, params=(user, pw))
            conn.close()
            
            if not u_data.empty:
                st.session_state.autenticado = True
                st.session_state.rol = u_data.iloc[0]['rol']
                st.session_state.usuario_nombre = u_data.iloc[0]['nombre']
                st.rerun()
            else:
                st.error("Credenciales incorrectas. Verifica mayúsculas/minúsculas.")

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

# --- 6. MÓDULOS DE INTERFAZ: INVENTARIO ---
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    
    # Asegurar que los datos estén frescos
    df_inv = st.session_state.get('df_inv', pd.DataFrame())

    # --- MÉTRICAS DE ENCABEZADO ---
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        moneda_ver = st.radio("Ver valores en:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], horizontal=True)

    tasa_ver = 1.0 if "USD" in moneda_ver else (t_bcv if "BCV" in moneda_ver else t_bin)
    simbolo = "$" if "USD" in moneda_ver else "Bs"

    if not df_inv.empty:
        valor_usd = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Valor Total ({simbolo})", f"{simbolo} {(valor_usd * tasa_ver):,.2f}")
        c2.metric("Referencia BCV", f"{t_bcv:.2f} Bs")
        c3.metric("Referencia Binance", f"{t_bin:.2f} Bs")

    st.divider()

    tab_lista, tab_registro, tab_edicion = st.tabs(["📋 Inventario Actual", "🆕 Registro / Carga", "🛠️ Modificar / Borrar"])

    # --- TAB: REGISTRO DE MERCANCÍA ---
    with tab_registro:
        with st.form("form_registro_pro"):
            st.subheader("🆕 Cargar Nueva Mercancía")
            c_u, c_n = st.columns([1, 2])
            u_medida = c_u.selectbox("Unidad de Medida:", ["ml", "Hojas", "Resma", "Unidad", "Metros"])
            it_nombre = c_n.text_input("Nombre del Material (Ej: Tinta Epson Cian)").strip()

            # Lógica especial para tintas (ml)
            if u_medida == "ml":
                col1, col2 = st.columns(2)
                ml_bote = col1.number_input("Contenido por bote (ml):", min_value=1.0, value=100.0)
                cant_botes = col2.number_input("Número de botes:", min_value=1, value=1)
                total_unidades = ml_bote * cant_botes
            else:
                total_unidades = st.number_input(f"Cantidad total ({u_medida}):", min_value=0.1, value=1.0)

            st.markdown("---")
            st.write("💰 **Costos y Comisiones (Combatiendo la Inflación)**")

            cc1, cc2, cc3 = st.columns(3)
            monto_pago = cc1.number_input("Monto pagado:", min_value=0.0, format="%.2f")
            moneda_pago = cc2.selectbox("Moneda de pago:", ["USD $", "Bs (Tasa BCV)", "Bs (Tasa Binance)"])
            imp_ley = cc3.selectbox("Impuestos aplicados:", ["Ninguno", "16% IVA", "3% IGTF"])

            comision_banco = st.slider("Comisión Bancaria / Transacción (%)", 0.0, 5.0, 0.5, step=0.1)

            if st.form_submit_button("🚀 REGISTRAR ENTRADA"):
                if it_nombre and total_unidades > 0:
                    # 1. Convertir a USD base
                    t_compra = 1.0
                    if "BCV" in moneda_pago: t_compra = t_bcv
                    elif "Binance" in moneda_pago: t_compra = t_bin
                    
                    base_usd = monto_pago / t_compra
                    
                    # 2. Sumar impuestos y comisiones
                    pct_gob = 0.16 if "16%" in imp_ley else (0.03 if "3%" in imp_ley else 0.0)
                    costo_total_usd = base_usd * (1 + pct_gob + (comision_banco / 100))
                    costo_unitario_final = costo_total_usd / total_unidades

                    # 3. Guardar en Base de Datos
                    conn = conectar()
                    c = conn.cursor()
                    try:
                        # Insertar o actualizar
                        c.execute("INSERT OR IGNORE INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?, 0, ?, ?)",
                                 (it_nombre, u_medida, costo_unitario_final))
                        
                        c.execute("UPDATE inventario SET cantidad = cantidad + ?, precio_usd = ? WHERE item = ?",
                                 (total_unidades, costo_unitario_final, it_nombre))
                        
                        # Registrar movimiento
                        c.execute("INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario) VALUES ((SELECT id FROM inventario WHERE item=?), 'ENTRADA', ?, 'Compra de material', ?)",
                                 (it_nombre, total_unidades, st.session_state.usuario_nombre))
                        
                        conn.commit()
                        st.success(f"✅ {it_nombre} cargado. Costo unitario real: ${costo_unitario_final:.4f}")
                        cargar_datos_seguros()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("⚠️ El nombre y la cantidad son obligatorios.")

    # --- TAB: LISTADO ---
    with tab_lista:
        if not df_inv.empty:
            df_ver = df_inv.copy()
            # Aplicar conversión de moneda para visualización
            df_ver['precio_usd'] = df_ver['precio_usd'] * tasa_ver
            
            # Formateo estético
            st.dataframe(
                df_ver.rename(columns={
                    'item': 'Material',
                    'cantidad': 'Stock',
                    'unidad': 'Unidad',
                    'precio_usd': f'Costo Unit. ({simbolo})'
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("El inventario está vacío.")

    # --- TAB: EDICIÓN ---
    with tab_edicion:
        if not df_inv.empty:
            item_edit = st.selectbox("Seleccionar ítem para modificar:", df_inv['item'].tolist())
            datos_e = df_inv[df_inv['item'] == item_edit].iloc[0]

            with st.form("form_edit"):
                col_e1, col_e2 = st.columns(2)
                new_q = col_e1.number_input("Corregir Stock Actual", value=float(datos_e['cantidad']))
                new_p = col_e2.number_input("Corregir Precio Unitario ($)", value=float(datos_e['precio_usd']), format="%.4f")

                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 Guardar Cambios"):
                    conn = conectar()
                    c = conn.cursor()
                    c.execute("UPDATE inventario SET cantidad=?, precio_usd=? WHERE id=?", (new_q, new_p, datos_e['id']))
                    conn.commit()
                    conn.close()
                    st.success("Cambios aplicados.")
                    cargar_datos_seguros()
                    st.rerun()
                
                if c2.form_submit_button("🗑️ Eliminar Ítem"):
                    conn = conectar()
                    c = conn.cursor()
                    c.execute("DELETE FROM inventario WHERE id=?", (datos_e['id'],))
                    conn.commit()
                    conn.close()
                    st.warning("Ítem eliminado.")
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


# --- 10. ANALIZADOR CMYK (CORREGIDO) ---
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador de Cobertura y Costos Reales")

    # Llamamos a la función que ya definimos arriba
    df_tintas_db = obtener_tintas_disponibles()

    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, desgaste FROM activos", conn)
    conn.close()

    impresoras_disponibles = [
        e['equipo'] for e in df_act_db.to_dict('records')
        if e['categoria'] == "Impresora (Gasta Tinta)"
    ]

    if not impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en 'Activos'.")
        st.stop()

    c_printer, c_file = st.columns([1, 2])

    with c_printer:
        impresora_sel = st.selectbox("🖨️ Selecciona la Impresora", impresoras_disponibles)
        
        datos_imp = next((e for e in df_act_db.to_dict('records') if e['equipo'] == impresora_sel), None)
        costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        # Precio de seguridad por si no hay stock
        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)

        # Si hay tintas cargadas en inventario, usamos ese precio
        if not df_tintas_db.empty:
            tintas_maquina = df_tintas_db[
                df_tintas_db['item'].str.contains(impresora_sel, case=False, na=False)
            ]
            if not tintas_maquina.empty:
                precio_tinta_ml = tintas_maquina['precio_usd'].mean()
                st.success(f"✅ Precio real: ${precio_tinta_ml:.4f}/ml")

    with c_file:
        archivos_multiples = st.file_uploader(
            "Sube tus diseños (PDF, JPG, PNG)",
            type=['pdf', 'png', 'jpg', 'jpeg'],
            accept_multiple_files=True
        )

    if archivos_multiples:
        import fitz  # PyMuPDF
        
        resultados = []
        totales_canales = {'c': 0.0, 'm': 0.0, 'y': 0.0, 'k': 0.0}
        total_paginas_lote = 0

        with st.spinner('🚀 Analizando píxeles...'):
            for arc in archivos_multiples:
                imagenes = []
                arc_bytes = arc.read()

                if arc.name.lower().endswith('.pdf'):
                    doc = fitz.open(stream=arc_bytes, filetype="pdf")
                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)
                        pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)
                        img_pil = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                        imagenes.append((f"{arc.name} (P{page_num+1})", img_pil))
                    doc.close()
                else:
                    img_pil = Image.open(io.BytesIO(arc_bytes)).convert('CMYK')
                    imagenes.append((arc.name, img_pil))

                for nombre_item, img in imagenes:
                    total_paginas_lote += 1
                    datos = np.array(img)
                    
                    # Media de cobertura (0-1)
                    c_p, m_p, y_p, k_p = [np.mean(datos[:, :, i]) / 255 for i in range(4)]

                    # Multiplicadores según máquina
                    n_low = impresora_sel.lower()
                    multi = 2.5 if "j210" in n_low else (1.8 if "subli" in n_low else 1.2)

                    ml_c, ml_m, ml_y, ml_k = [p * 0.15 * multi for p in [c_p, m_p, y_p, k_p]]

                    totales_canales['c'] += ml_c
                    totales_canales['m'] += ml_m
                    totales_canales['y'] += ml_y
                    totales_canales['k'] += ml_k

                    consumo_t = ml_c + ml_m + ml_y + ml_k
                    total_usd = (consumo_t * precio_tinta_ml) + costo_desgaste

                    resultados.append({
                        "Archivo": nombre_item,
                        "ml Total": round(consumo_t, 4),
                        "Costo USD": round(total_usd, 4)
                    })

        if resultados:
            st.dataframe(pd.DataFrame(resultados), use_container_width=True, hide_index=True)
            
            total_lote = sum(r['Costo USD'] for r in resultados)
            st.metric("Costo Total de Producción", f"$ {total_lote:.2f}")

            if st.button("📝 ENVIAR A COTIZACIÓN"):
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Prod. {impresora_sel}",
                    'costo_base': total_lote,
                    'unidades': total_paginas_lote
                }
                st.success("Cargado. Ve al menú Cotizaciones.")


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









