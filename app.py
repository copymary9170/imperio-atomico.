import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from PIL import Image
import numpy as np
import io

# --- 1. MOTOR DE BASE DE DATOS PROFESIONAL ---
def conectar():
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    
    # Crear tablas principales
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente_id INTEGER, trabajo TEXT, monto_usd REAL, estado TEXT, FOREIGN KEY(cliente_id) REFERENCES clientes(id))')
    c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo_pago TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(cliente_id) REFERENCES clientes(id))')
    c.execute('CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    
    # Tabla de Usuarios
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)')
    
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        usuarios_iniciales = [
            ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio'),
            ('mama', 'admin2026', 'Administracion', 'Mamá'),
            ('pro', 'diseno2026', 'Produccion', 'Hermana')
        ]
        c.executemany("INSERT INTO usuarios VALUES (?,?,?,?)", usuarios_iniciales)

    # Configuración inicial
    config_init = [
        ('tasa_bcv', 36.50), ('tasa_binance', 38.00),
        ('iva_perc', 0.16), ('igtf_perc', 0.03),
        ('banco_perc', 0.02), ('costo_tinta_ml', 0.10)
    ]
    for param, valor in config_init:
        c.execute("INSERT OR IGNORE INTO configuracion (parametro, valor) VALUES (?, ?)", (param, valor))
    
    conn.commit()
    conn.close()

def migrar_base_datos():
    conn = conectar()
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE cotizaciones ADD COLUMN cliente_id INTEGER")
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# --- EJECUCIÓN INICIAL ---
inicializar_sistema()
migrar_base_datos()

# --- 2. CONFIGURACIÓN DE STREAMLIT ---
st.set_page_config(page_title="Imperio Atómico - Sistema Pro", layout="wide")

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Imperio Atómico")
    with st.form("login_form"):
        u = st.text_input("Usuario")
        p = st.text_input("Clave", type="password")
        if st.form_submit_button("Entrar"):
            if u == "jefa" and p == "atomica2026": # Bypass de emergencia
                st.session_state.autenticado = True
                st.session_state.rol = "Admin"
                st.session_state.usuario_nombre = "Dueña del Imperio"
                st.rerun()
            
            conn = conectar()
            res = pd.read_sql_query("SELECT * FROM usuarios WHERE username=? AND password=?", conn, params=(u, p))
            conn.close()
            if not res.empty:
                st.session_state.autenticado = True
                st.session_state.rol = res.iloc[0]['rol']
                st.session_state.usuario_nombre = res.iloc[0]['nombre']
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# --- 3. CARGA DE DATOS Y VARIABLES ---
ROL = st.session_state.rol
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = round(float(conf.loc['tasa_bcv', 'valor']), 2)
t_bin = round(float(conf.loc['tasa_binance', 'valor']), 2)
iva, igtf, banco = conf.loc['iva_perc', 'valor'], conf.loc['igtf_perc', 'valor'], conf.loc['banco_perc', 'valor']
conn.close()

# --- 3. MENÚ LATERAL FILTRADO ---
with st.sidebar:
    st.header(f"👋 Hola, {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv:.2f} | 🔶 BIN: {t_bin:.2f}")
    
    # Filtro de opciones según ROL
    opciones = ["📝 Cotizaciones", "🎨 Análisis CMYK", "👥 Clientes"] # Todas ven esto
    
    if ROL == "Admin":
        opciones += ["📦 Inventario", "📊 Dashboard", "🏗️ Activos", "🛠️ Otros Procesos", "⚙️ Configuración"]
    elif ROL == "Administracion":
        opciones += ["📊 Dashboard", "⚙️ Configuración"]
    elif ROL == "Produccion":
        opciones += ["📦 Inventario", "🏗️ Activos", "🛠️ Otros Procesos"]

    menu = st.radio("Módulos", opciones)
    
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()


# --- 4. LÓGICA DE INVENTARIO (VERSIÓN "TASAS DE COMPRA" COMPLETA) --- 
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    
    conn = conectar()
    try:
        df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
    except:
        df_inv = pd.DataFrame()
    conn.close()

    # --- 🚨 ALERTAS PERSONALIZADAS ---
    st.subheader("📢 Avisos de Stock")
    if not df_inv.empty:
        col_min = 'minimo' if 'minimo' in df_inv.columns else 5.0
        alertas = df_inv[df_inv['cantidad'] <= (df_inv[col_min] if 'minimo' in df_inv.columns else 5.0)]
        if not alertas.empty:
            for _, row in alertas.iterrows():
                st.error(f"⚠️ **STOCK BAJO:** {row['item']} tiene {row['cantidad']:.2f} {row['unidad']}.")
        else:
            st.success("✅ Stock saludable.")

  # --- 4. MÓDULO DE INVENTARIO: AUDITORÍA Y CONTROL TOTAL --- 
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    
    # --- CONEXIÓN Y LIMPIEZA DE DATOS ---
    conn = conectar()
    try:
        df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
        # Verificación de seguridad: si la columna 'minimo' no existe por ser DB vieja, la creamos
        if 'minimo' not in df_inv.columns:
            c = conn.cursor()
            c.execute("ALTER TABLE inventario ADD COLUMN minimo REAL DEFAULT 5.0")
            conn.commit()
            df_inv['minimo'] = 5.0
    except:
        df_inv = pd.DataFrame()
    conn.close()

    # --- 📊 SECCIÓN 1: EL CORAZÓN FINANCIERO (MÉTRICAS) ---
    if not df_inv.empty:
        st.subheader("💰 Inversión Activa en Almacén")
        # Calculamos el valor real multiplicando cantidad exacta por precio exacto
        valor_usd = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total en Dólares", f"$ {valor_usd:,.2f}")
        c2.metric("Total BCV", f"Bs { (valor_usd * t_bcv):,.2f}")
        c3.metric("Total Binance", f"Bs { (valor_usd * t_bin):,.2f}")
        
        # --- 🚨 SECCIÓN 2: ALERTAS INTELIGENTES ---
        st.markdown("### 📢 Alertas de Reposición")
        # Filtramos solo los que están por debajo de su propio mínimo configurado
        alertas = df_inv[df_inv['cantidad'] <= df_inv['minimo']]
        
        if not alertas.empty:
            for _, row in alertas.iterrows():
                st.error(f"⚠️ **STOCK CRÍTICO:** {row['item']} tiene {row['cantidad']:.2f} {row['unidad']}. (Tu mínimo es {row['minimo']})")
        else:
            st.success("✅ Stock saludable: Todos los insumos están por encima del nivel de alerta.")
    else:
        st.info("El inventario está vacío. Registra tu primera compra abajo.")

    st.divider()

    # --- 📥 SECCIÓN 3: FORMULARIO DE ENTRADA PRO (DINÁMICO) ---
    st.subheader("📥 Registrar Entrada de Materiales")
    
    # El selector de unidad DEBE ir afuera para que la interfaz cambie al instante
    it_unid = st.selectbox("Unidad de Medida:", ["ml", "Hojas", "Resma", "Unidad", "Metros"], key="selector_u_final")

    with st.form("form_maestro_inventario_v5"):
        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.markdown("**📦 Identificación**")
            it_nombre = st.text_input("Nombre del Insumo", placeholder="Ej: Tinta Epson 544 / Resma Bond A4")
            
            # Lógica Condicional para Tintas
            if it_unid == "ml":
                st.info("🎨 Modo de Insumos Líquidos")
                tipo_carga = st.radio("Presentación:", 
                                     ["Bote Individual", "Dúo de Cartuchos (2)", "Kit CMYK (4 colores)"], 
                                     horizontal=True)
                capacidad = st.number_input("ml por cada bote/cartucho", min_value=0.1, value=65.0)
            else:
                tipo_carga = "Normal"
                capacidad = 1.0
            
            it_minimo = st.number_input("Punto de Alerta (Mínimo)", min_value=0.0, value=5.0, help="El sistema te avisará cuando el stock sea menor a este número.")

        with col_der:
            st.markdown("**💵 Costos e Impuestos**")
            it_cant_packs = st.number_input("Cantidad comprada (Packs/Kits)", min_value=1, value=1)
            monto_pagado = st.number_input("Monto total pagado", min_value=0.0, format="%.2f")
            moneda_pago = st.radio("Moneda de Pago:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], horizontal=True)
            
            st.write("---")
            st.write("**🛡️ Impuestos Aplicados**")
            tx1, tx2, tx3 = st.columns(3)
            p_iva = tx1.checkbox(f"IVA ({iva*100}%)", value=True)
            p_gtf = tx2.checkbox(f"IGTF ({igtf*100}%)", value=False)
            p_banco = tx3.checkbox(f"Banco ({banco*100}%)", value=True)

        if st.form_submit_button("🚀 IMPACTAR INVENTARIO"):
            if it_nombre and monto_pagado > 0:
                # 1. Convertir a USD según la tasa seleccionada
                if "BCV" in moneda_pago:
                    base_usd = monto_pagado / t_bcv
                elif "Binance" in moneda_pago:
                    base_usd = monto_pagado / t_bin
                else:
                    base_usd = monto_pagado
                
                # 2. Sumar impuestos (IVA + IGTF + Banco)
                recargo_total = (iva if p_iva else 0) + (igtf if p_gtf else 0) + (banco if p_banco else 0)
                costo_final_usd = base_usd * (1 + recargo_total)
                
                c = conectar()
                # 3. Lógica de guardado profesional
                if it_unid == "ml":
                    if tipo_carga == "Dúo de Cartuchos (2)":
                        costo_por_ml = (costo_final_usd / 2) / capacidad
                        for col in ["Negro", "Color"]:
                            c.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                                       VALUES (?,?,?,?,?) ON CONFLICT(item) DO UPDATE SET 
                                       precio_usd=excluded.precio_usd, cantidad=cantidad+excluded.cantidad, minimo=excluded.minimo""", 
                                     (f"Cartucho {it_nombre} {col}", capacidad * it_cant_packs, "ml", costo_por_ml, it_minimo))
                    elif tipo_carga == "Kit CMYK (4 colores)":
                        costo_por_ml = (costo_final_usd / 4) / capacidad
                        for col in ["Cian", "Magenta", "Amarillo", "Negro"]:
                            c.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                                       VALUES (?,?,?,?,?) ON CONFLICT(item) DO UPDATE SET 
                                       precio_usd=excluded.precio_usd, cantidad=cantidad+excluded.cantidad, minimo=excluded.minimo""", 
                                     (f"Tinta {it_nombre} {col}", capacidad * it_cant_packs, "ml", costo_por_ml, it_minimo))
                    else:
                        # Bote Individual de Tinta
                        costo_u = costo_final_usd / (capacidad * it_cant_packs)
                        c.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                                   VALUES (?,?,?,?,?) ON CONFLICT(item) DO UPDATE SET 
                                   precio_usd=excluded.precio_usd, cantidad=cantidad+excluded.cantidad, minimo=excluded.minimo""", 
                                 (it_nombre, capacidad * it_cant_packs, "ml", costo_u, it_minimo))
                else:
                    # Papelería o Resmas
                    costo_u = costo_final_usd / it_cant_packs
                    c.execute("""INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo) 
                               VALUES (?,?,?,?,?) ON CONFLICT(item) DO UPDATE SET 
                               precio_usd=excluded.precio_usd, cantidad=cantidad+excluded.cantidad, minimo=excluded.minimo""", 
                             (it_nombre, it_cant_packs, it_unid, costo_u, it_minimo))
                
                c.commit(); c.close()
                st.success("✅ Insumos cargados y costos recalculados.")
                st.rerun()

    # --- 📋 SECCIÓN 4: AUDITORÍA DE ALMACÉN ---
    st.divider()
    if not df_inv.empty:
        st.subheader("📋 Auditoría de Almacén")
        col_bus, col_vis = st.columns([2, 1])
        busc = col_bus.text_input("🔍 Buscar material...")
        m_view = col_vis.selectbox("Ver precios en:", ["Dólares ($)", "Tasa BCV (Bs)", "Tasa Binance (Bs)"])
        
        # Determinar tasa de visualización
        t_v = t_bcv if "BCV" in m_view else (t_bin if "Binance" in m_view else 1.0)
        simb = "Bs" if "Bs" in m_view else "$"

        df_f = df_inv[df_inv['item'].str.contains(busc, case=False)].copy()
        df_f['Unitario'] = df_f['precio_usd'] * t_v
        df_f['Total'] = df_f['Unitario'] * df_f['cantidad']
        
        st.dataframe(df_f[['item', 'cantidad', 'unidad', 'Unitario', 'Total']].style.format({
            'cantidad': '{:,.2f}', 'Unitario': f'{simb} {{:,.4f}}', 'Total': f'{simb} {{:,.2f}}'
        }), use_container_width=True, hide_index=True)

    # --- ⚙️ SECCIÓN 5: AJUSTES Y BORRADO ---
    st.divider()
    col_aj, col_del = st.columns(2)
    with col_aj:
        with st.expander("🔧 Corregir Stock (Mermas)"):
            if not df_inv.empty:
                it_aj = st.selectbox("Material a corregir:", df_inv['item'].tolist(), key="sel_ajuste")
                nueva_c = st.number_input("Cantidad Real en Estante:", min_value=0.0)
                if st.button("🔄 Actualizar Cantidad", key="btn_ajuste"):
                    c = conectar(); c.execute("UPDATE inventario SET cantidad=? WHERE item=?", (nueva_c, it_aj)); c.commit(); c.close()
                    st.rerun()
    with col_del:
        with st.expander("🗑️ Eliminar Producto"):
            if not df_inv.empty:
                it_del = st.selectbox("Eliminar permanentemente:", df_inv['item'].tolist(), key="sel_borrar")
                if st.button("❌ ELIMINAR", key="btn_borrar_final"):
                    c = conectar(); c.execute("DELETE FROM inventario WHERE item=?", (it_del,)); c.commit(); c.close()
                    st.rerun()
# --- 5. LÓGICA DE COTIZACIONES (VERSIÓN MAESTRA FINAL) ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Cotizaciones")
    
    # Recuperar datos de memoria (Analizador CMYK)
    pre_datos = st.session_state.get('datos_pre_cotizacion', {})
    conn = conectar()
    df_clis = pd.read_sql_query("SELECT id, nombre, whatsapp FROM clientes", conn)
    df_inv_full = pd.read_sql_query("SELECT item, precio_usd, unidad, cantidad FROM inventario", conn)
    
    # Cargamos historial uniendo clientes para ver nombres
    query_hist = """
        SELECT c.id, c.fecha, cl.nombre as cliente, c.trabajo, c.monto_usd, c.estado, c.cliente_id 
        FROM cotizaciones c
        LEFT JOIN clientes cl ON c.cliente_id = cl.id
    """
    df_cots_global = pd.read_sql_query(query_hist, conn)
    conn.close()

    if df_clis.empty:
        st.warning("⚠️ No hay clientes. Registra uno en el módulo 'Clientes'.")
    else:
        with st.form("form_cot_final_boss"):
            st.subheader("🛠️ Crear Nuevo Presupuesto")
            c1, c2 = st.columns(2)
            
            # Selector de Cliente
            dict_clientes = {row['nombre']: row['id'] for _, row in df_clis.iterrows()}
            cli_nombre = c1.selectbox("Cliente", ["--"] + list(dict_clientes.keys()))
            trabajo = c1.text_input("¿Qué trabajo es?", value=pre_datos.get('trabajo', ""))
            
            # Selector de Papel
            papeles = df_inv_full[df_inv_full['unidad'] != 'ml']['item'].tolist()
            material = c2.selectbox("Papel/Material", ["--"] + papeles)
            cant_hojas = c2.number_input("Cantidad de hojas", min_value=0, value=int(pre_datos.get('unidades', 0)))
            
            # Lógica de Tinta (ml)
            st.divider()
            cx1, cx2 = st.columns(2)
            tintas = df_inv_full[df_inv_full['unidad'] == 'ml']['item'].tolist()
            tinta_sel = cx1.selectbox("Tinta a descontar", ["--"] + tintas)
            
            # Si viene de CMYK usamos los ml exactos, si no, slider manual
            if pre_datos:
                ml_final = cx2.number_input("ML de tinta (Precisión CMYK)", value=float(pre_datos.get('ml_estimados', 0.0)), format="%.4f")
            else:
                cobertura = cx2.slider("Cobertura manual (%)", 5, 100, 15)
                ml_final = (cobertura / 5.0) * 0.05 * cant_hojas

            # Pago y Margen
            st.divider()
            sug_precio = pre_datos.get('costo_base', 0.0) * 2.5
            monto_f = st.number_input("Precio Total a Cobrar ($)", min_value=0.0, value=float(sug_precio), format="%.2f")
            metodo = st.selectbox("Método de Pago", ["Efectivo", "Pago Móvil", "Zelle", "Binance"])
            est_pago = st.selectbox("Estado", ["Pendiente", "Pagado"])

            if st.form_submit_button("🚀 GUARDAR Y PROCESAR TODO"):
                if cli_nombre != "--" and monto_f > 0:
                    id_cli = dict_clientes[cli_nombre]
                    c = conectar()
                    # 1. Guardar Cotización
                    c.execute("INSERT INTO cotizaciones (fecha, cliente_id, trabajo, monto_usd, estado) VALUES (?,?,?,?,?)",
                              (datetime.now().strftime("%d/%m/%Y"), id_cli, trabajo, monto_f, est_pago))
                    
                    # 2. Si se paga ahora, va directo a Ventas (Caja)
                    if est_pago == "Pagado":
                        c.execute("INSERT INTO ventas (cliente_id, monto_total, metodo_pago) VALUES (?,?,?)",
                                  (id_cli, monto_f, metodo))
                    
                    # 3. Descuento de Papel
                    if material != "--" and cant_hojas > 0:
                        c.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE item = ?", (cant_hojas, material))
                    
                    # 4. Descuento de Tinta
                    if tinta_sel != "--" and ml_final > 0:
                        c.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE item = ?", (ml_final, tinta_sel))
                    
                    c.commit(); c.close()
                    if 'datos_pre_cotizacion' in st.session_state: del st.session_state['datos_pre_cotizacion']
                    st.success("✅ ¡Operación Atómica exitosa!"); st.rerun()

    # --- HISTORIAL Y GESTIÓN DE COBROS ---
    if not df_cots_global.empty:
        st.divider()
        st.subheader("📑 Gestión de Facturación")
        
        # Sistema de cobro para lo que quedó pendiente
        pendientes = df_cots_global[df_cots_global['estado'] == "Pendiente"]
        if not pendientes.empty:
            with st.expander("💰 COBRAR PENDIENTES"):
                col_sel, col_met, col_btn = st.columns([1, 1, 1])
                id_c = col_sel.selectbox("ID Cotización:", pendientes['id'].tolist())
                met_at = col_met.selectbox("Recibido por:", ["Efectivo", "Pago Móvil", "Zelle", "Binance"])
                if col_btn.button("Marcar como Cobrado"):
                    fila = pendientes[pendientes['id'] == id_c].iloc[0]
                    c = conectar()
                    c.execute("UPDATE cotizaciones SET estado = 'Pagado' WHERE id = ?", (id_c,))
                    c.execute("INSERT INTO ventas (cliente_id, monto_total, metodo_pago) VALUES (?,?,?)",
                              (int(fila['cliente_id']), float(fila['monto_usd']), met_at))
                    c.commit(); c.close(); st.rerun()

        # Tabla visual
        st.dataframe(df_cots_global.sort_values('id', ascending=False), use_container_width=True, hide_index=True)
        
        # WhatsApp rápido
        st.subheader("📲 Enviar a WhatsApp")
        c_env = st.selectbox("Selecciona ID para enviar:", df_cots_global['id'].tolist())
        d_c = df_cots_global[df_cots_global['id'] == c_env].iloc[0]
        # Buscar el tlf del cliente de esa cotización
        tlf = df_clis[df_clis['id'] == d_c['cliente_id']]['whatsapp'].iloc[0]
        if tlf:
            num = "".join(filter(str.isdigit, tlf))
            if num.startswith('0'): num = "58" + num[1:]
            elif not num.startswith('58'): num = "58" + num
            msg = f"¡Hola! *Imperio Atómico* ⚛️%0A*Trabajo:* {d_c['trabajo']}%0A*Total:* {d_c['monto_usd']:.2f} USD%0A*Tasa BCV:* {(d_c['monto_usd']*t_bcv):,.2f} Bs"
            st.link_button(f"🚀 Enviar WhatsApp a {d_c['cliente']}", f"https://wa.me/{num}?text={msg}")
            
# --- 6. DASHBOARD FINANCIERO PROFESIONAL ---
elif menu == "📊 Dashboard":
    st.title("📊 Centro de Control Financiero")
    st.markdown("Análisis en tiempo real de ingresos, egresos y rentabilidad.")

    conn = conectar()
    # 1. Cargar datos de Ventas, Gastos e Inventario
    df_ventas = pd.read_sql_query("SELECT * FROM ventas", conn)
    df_gastos = pd.read_sql_query("SELECT * FROM gastos", conn)
    df_inv_dash = pd.read_sql_query("SELECT cantidad, precio_usd FROM inventario", conn)
    conn.close()

    # --- FILA 1: MÉTRICAS PRINCIPALES ---
    c1, c2, c3, c4 = st.columns(4)
    
    ingresos_totales = df_ventas['monto_total'].sum() if not df_ventas.empty else 0.0
    gastos_totales = df_gastos['monto'].sum() if not df_gastos.empty else 0.0
    balance_neto = ingresos_totales - gastos_totales
    valor_inventario = (df_inv_dash['cantidad'] * df_inv_dash['precio_usd']).sum()

    c1.metric("💰 Ingresos Totales", f"$ {ingresos_totales:.2f}")
    c2.metric("📉 Gastos Totales", f"$ {gastos_totales:.2f}", delta=f"-{gastos_totales:.2f}", delta_color="inverse")
    
    # Color dinámico para el balance
    c3.metric("⚖️ Balance Neto", f"$ {balance_neto:.2f}", 
              delta=f"{((balance_neto/ingresos_totales)*100 if ingresos_totales > 0 else 0):.1f}% Margen")
    
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

# --- 7. CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Tasas e Impuestos")
    with st.form("f_conf"):
        c1, c2 = st.columns(2)
        n_bcv = c1.number_input("Tasa BCV", value=t_bcv)
        n_bin = c1.number_input("Tasa Binance", value=t_bin)
        n_iva = c2.number_input("IVA (0.16)", value=iva)
        n_igtf = c2.number_input("IGTF (0.03)", value=igtf)
        n_banco = c2.number_input("Banco (0.02)", value=banco)
        if st.form_submit_button("💾 Guardar Cambios"):
            c = conectar()
            # Usamos round(n_bcv, 2) para que a la base de datos ya entre limpio
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (round(n_bcv, 2),))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (round(n_bin, 2),))
            # ... los demás quedan igual
            c.commit(); c.close(); st.success("✅ Configuración actualizada"); st.rerun()

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





































































