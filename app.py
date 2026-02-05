import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. MOTOR DE BASE DE DATOS PROFESIONAL ---
def conectar():
    # Cambiamos 'imperio_data.db' por 'imperio_v2.db'
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    
    # 1. Crear todas las tablas (asegúrate de incluir todas las que ya definimos)
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente_id INTEGER, trabajo TEXT, monto_usd REAL, estado TEXT, FOREIGN KEY(cliente_id) REFERENCES clientes(id))')
    c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo_pago TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(cliente_id) REFERENCES clientes(id))')
    c.execute('CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    
    # 2. SEEDER: Insertar valores por defecto en CONFIGURACIÓN si no existen
    # Esto evita el KeyError: 'tasa_bcv'
    configuraciones_iniciales = [
        ('tasa_bcv', 36.50),
        ('tasa_binance', 38.00),
        ('iva_perc', 0.16),
        ('igtf_perc', 0.03),
        ('banco_perc', 0.02),
        ('costo_tinta_ml', 0.10) # Valor base para el análisis CMYK
    ]
    
    for param, valor in configuraciones_iniciales:
        c.execute("INSERT OR IGNORE INTO configuracion (parametro, valor) VALUES (?, ?)", (param, valor))
    
    conn.commit()
    conn.close()
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

# --- 2. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Imperio Atómico - Sistema Pro", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state: st.session_state.login = False
if not st.session_state.login:
    st.title("🔐 Acceso Master")
    u, p = st.text_input("Usuario"), st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u == "admin" and p == "1234":
            st.session_state.login = True
            st.rerun()
    st.stop()

# Carga de datos globales
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')

# Redondeamos a 2 decimales desde el origen
t_bcv = round(float(conf.loc['tasa_bcv', 'valor']), 2)
t_bin = round(float(conf.loc['tasa_binance', 'valor']), 2)

iva, igtf, banco = conf.loc['iva_perc', 'valor'], conf.loc['igtf_perc', 'valor'], conf.loc['banco_perc', 'valor']
# ... resto del código
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
df_cots_global = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
conn.close()

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    # Usamos f-strings con :.2f para forzar solo 2 decimales
    st.info(f"🏦 BCV: {t_bcv:.2f} | 🔶 BIN: {t_bin:.2f}")
    menu = st.radio("Módulos", ["📦 Inventario", "📝 Cotizaciones", "📊 Dashboard", "👥 Clientes", "🎨 Análisis CMYK", "🛠️ Otros Procesos", "🏗️ Activos", "⚙️ Configuración", "💰 Caja y Gastos"])
    
# --- 4. LÓGICA DE INVENTARIO (VERSIÓN INTEGRAL V2) --- 
if menu == "📦 Inventario":
    st.title("📦 Inventario y Auditoría")

    # Recarga de seguridad
    conn = conectar()
    df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
    conn.close()

    busqueda_inv = st.text_input("🔍 Buscar producto...", placeholder="Ej: Resma, Tinta...")

    # --- ALERTAS DE STOCK ---
    st.divider()
    if not df_inv.empty:
        df_bajo = df_inv[df_inv['cantidad'] <= 10]
        if not df_bajo.empty:
            for _, row in df_bajo.iterrows():
                st.warning(f"🚨 **Bajo Stock:** {row['item']} ({int(row['cantidad'])} {row['unidad']})")

    # --- FORMULARIO DE COMPRA ---
    with st.expander("📥 Registrar Nueva Compra (Paquetes/Lotes)"):
        with st.form("form_inv_v2"):
            col_a, col_b = st.columns(2)
            with col_a:
                it_nombre = st.text_input("Nombre del Producto")
                it_cant = st.number_input("Unidades que trae el lote", min_value=1.0, value=500.0)
                it_unid = st.selectbox("Unidad", ["Hojas", "ml", "Unidad", "Resma"])
            with col_b:
                precio_lote = st.number_input("Precio TOTAL Lote (USD)", min_value=0.0, format="%.2f")
                st.write("### 🧾 Impuestos Aplicados")
                p_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                p_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre and precio_lote > 0:
                    # Calculamos el costo de UNA SOLA UNIDAD para la base de datos
                    # Esto permite que la inflación se maneje por unidad
                    imp_tot = (iva if p_iva else 0) + (igtf if p_gtf else 0)
                    costo_por_unidad = (precio_lote * (1 + imp_tot)) / it_cant
                    
                    c = conectar()
                    # Si el item existe, actualizamos precio y sumamos cantidad
                    c.execute("""
                        INSERT INTO inventario (item, cantidad, unidad, precio_usd) 
                        VALUES (?,?,?,?) 
                        ON CONFLICT(item) DO UPDATE SET 
                        precio_usd = excluded.precio_usd,
                        cantidad = cantidad + excluded.cantidad
                    """, (it_nombre, float(it_cant), it_unid, costo_por_unidad))
                    c.commit(); c.close()
                    st.success(f"✅ {it_nombre} cargado al sistema.")
                    st.rerun()

    # --- TABLA DE AUDITORÍA (SOLUCIÓN DEFINITIVA BCV) ---
    st.divider()
    if not df_inv.empty:
        # Selector de moneda para la vista
        m_vista = st.radio("Moneda:", ["USD", "BCV", "Binance"], horizontal=True, key="inv_m")
        
        # Tasa dinámica basada en lo que cargaste en el config
        t_v = t_bcv if m_vista == "BCV" else (t_bin if m_vista == "Binance" else 1.0)
        s = "Bs" if m_vista != "USD" else "$"

        df_calc = df_inv[df_inv['item'].str.contains(busqueda_inv, case=False)].copy()
        
        # PRECIO_USD en la DB ahora es por unidad, así que:
        df_calc['Unitario'] = df_calc['precio_usd'] * t_v
        df_calc['Total'] = df_calc['Unitario'] * df_calc['cantidad']

        # Formateo para la vista
        df_ver = df_calc[['item', 'cantidad', 'unidad', 'Unitario', 'Total']].copy()
        df_ver.columns = ['Producto', 'Stock', 'Und', f'Unit. ({s})', f'Total Stock ({s})']

        st.dataframe(df_ver.style.format({
            'Stock': '{:,.2f}',
            f'Unit. ({s})': "{:.4f}",
            f'Total Stock ({s})': "{:,.2f}"
        }), use_container_width=True, hide_index=True)

    # --- BORRADO ---
    st.divider()
    with st.expander("🗑️ Eliminar Insumos"):
        if not df_inv.empty:
            p_borrar = st.selectbox("Producto a eliminar:", df_inv['item'].tolist())
            if st.button("❌ Confirmar Eliminación"):
                c = conectar(); c.execute("DELETE FROM inventario WHERE item=?", (p_borrar,)); c.commit(); c.close()
                st.rerun()



# --- 5. LÓGICA DE COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Cotizaciones")
    c = conectar()
    clis = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist()
    inv_l = pd.read_sql_query("SELECT item, precio_usd FROM inventario", c)
    c.close()

    with st.form("form_cot"):
        c1, c2 = st.columns(2)
        cli = c1.selectbox("Cliente", ["--"] + clis)
        trab = c1.text_input("Trabajo")
        mat = c2.selectbox("Material a usar", ["--"] + inv_l['item'].tolist())
        cant_m = c2.number_input("Cantidad (unidades completas)", min_value=0, step=1)
        monto_f = st.number_input("Precio Final a Cobrar (USD)", min_value=0.0)
        est = st.selectbox("Estado", ["Pendiente", "Pagado"])
        
        if st.form_submit_button("📋 Guardar Cotización"):
            if cli != "--" and monto_f > 0:
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bcv, monto_binance, estado) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cli, trab, monto_f, monto_f*t_bcv, monto_f*t_bin, est))
                if mat != "--":
                    c.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE item = ?", (cant_m, mat))
                c.commit(); c.close(); st.success("✅ Guardado"); st.rerun()

    st.subheader("📑 Historial de Movimientos")
    if not df_cots_global.empty:
        def color_est(val):
            color = '#ff4b4b' if val == 'Pendiente' else '#28a745'
            return f'background-color: {color}; color: white; font-weight: bold'
        st.dataframe(df_cots_global.sort_values('id', ascending=False).style.applymap(color_est, subset=['estado']), use_container_width=True)

    st.divider()
    st.subheader("📲 Enviar Cotización por WhatsApp")
    
    if not df_cots_global.empty:
        # Seleccionamos la última cotización para enviar
        c_envio = st.selectbox("Selecciona la cotización a enviar:", df_cots_global['id'].tolist())
        datos_c = df_cots_global[df_cots_global['id'] == c_envio].iloc[0]
        
        # Buscamos el teléfono del cliente
        c = conectar()
        tel = pd.read_sql_query(f"SELECT whatsapp FROM clientes WHERE nombre = '{datos_c['cliente']}'", c)
        c.close()
        
        if not tel.empty and tel['whatsapp'].iloc[0]:
            # 1. Quitamos espacios o guiones que tenga el número
            num_original = "".join(filter(str.isdigit, tel['whatsapp'].iloc[0]))
            
            # 2. Si el número empieza con '0', le quitamos el '0' y le ponemos '58'
            if num_original.startswith('0'):
                numero_final = "58" + num_original[1:]
            # 3. Si ya tiene el 58, lo dejamos igual
            elif num_original.startswith('4') or num_original.startswith('2'):
                numero_final = "58" + num_original
            else:
                numero_final = num_original

            # El mensaje con el precio en USD y Bs (BCV)
            monto_bs = datos_c['monto_usd'] * t_bcv
            mensaje = f"¡Hola! *Imperio Atómico* te saluda. 👋%0A%0A" \
                      f"Detalle: *{datos_c['trabajo']}*%0A" \
                      f"Total: *{datos_c['monto_usd']:.2f} USD*%0A" \
                      f"En Bolívares: *{monto_bs:.2f} Bs* (Tasa BCV)%0A%0A" \
                      f"¡Gracias por tu confianza! ⚛️"
            
            link_ws = f"https://wa.me/{numero_final}?text={mensaje}"
            st.link_button(f"🚀 Enviar WhatsApp a {datos_c['cliente']}", link_ws)
        else:
            st.warning("Este cliente no tiene un número de WhatsApp registrado.")


# --- NUEVO MÓDULO: CAJA Y VENTAS ---
elif menu == "💰 Caja y Gastos":
    st.title("💰 Gestión de Flujo de Caja")
    
    tab1, tab2 = st.tabs(["💵 Registrar Venta", "📉 Registrar Gasto"])
    
    with tab1:
        st.subheader("Convertir Cotización en Cobro")
        # Solo mostramos cotizaciones pendientes
        c = conectar()
        df_pendientes = pd.read_sql_query("SELECT id, cliente_id, trabajo, monto_usd FROM cotizaciones WHERE estado='Pendiente'", c)
        
        if not df_pendientes.empty:
            sel_cot = st.selectbox("Selecciona Cotización para cobrar", df_pendientes['id'].tolist())
            m_pago = st.selectbox("Método de Pago", ["Efectivo", "Zelle", "Pago Móvil", "Binance"])
            
            if st.button("Confirmar Cobro"):
                datos = df_pendientes[df_pendientes['id'] == sel_cot].iloc[0]
                # 1. Crear la venta
                c.execute("INSERT INTO ventas (cliente_id, monto_total, metodo_pago) VALUES (?,?,?)", 
                          (int(datos['cliente_id']), datos['monto_usd'], m_pago))
                # 2. Marcar cotización como Pagada
                c.execute("UPDATE cotizaciones SET estado='Pagado' WHERE id=?", (sel_cot,))
                c.commit()
                st.success("✅ Venta registrada en caja.")
                st.rerun()
        else:
            st.info("No hay cotizaciones pendientes de cobro.")
        c.close()

    with tab2:
        st.subheader("Registro de Gastos Operativos")
        with st.form("form_gastos"):
            desc_g = st.text_input("Descripción del gasto (Ej: Pago de luz, Alquiler, Comida)")
            monto_g = st.number_input("Monto (USD)", min_value=0.0)
            cat_g = st.selectbox("Categoría", ["Servicios", "Materiales", "Mantenimiento", "Otros"])
            if st.form_submit_button("Registrar Gasto"):
                c = conectar()
                c.execute("INSERT INTO gastos (descripcion, monto, categoria) VALUES (?,?,?)", (desc_g, monto_g, cat_g))
                c.commit(); c.close()
                st.warning("📉 Gasto registrado.")

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

# --- 10. ANALIZADOR MASIVO DE COBERTURA CMYK (MULTIGESTIÓN DE TINTAS) ---
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador de Cobertura por Impresora")

    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, desgaste FROM activos", conn)
    df_inv_tintas = pd.read_sql_query("SELECT item, precio_usd FROM inventario WHERE item LIKE '%Tinta%'", conn)
    conn.close()
    
    impresoras_disponibles = [e['equipo'] for e in df_act_db.to_dict('records') if e['categoria'] == "Impresora (Gasta Tinta)"]

    if not impresoras_disponibles:
        st.warning("⚠️ Registra tus impresoras en el módulo de 'Activos' primero.")
        st.stop()

    c_printer, c_file = st.columns([1, 2])
    
    with c_printer:
        impresora_sel = st.selectbox("🖨️ Selecciona la Impresora", impresoras_disponibles)
        datos_imp = next((e for e in lista_activos if e['equipo'] == impresora_sel), None)
        costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        # --- LÓGICA MULTI-TINTA ---
        # El sistema busca TODO lo que coincida con el nombre de la impresora
        # Ej: Si seleccionas "J210", buscará "Tinta J210 Negro", "Tinta J210 Cian", etc.
        
        # Filtramos el inventario para encontrar todos los insumos de esta máquina
        tintas_maquina = df_inv_tintas[df_inv_tintas['item'].str.contains(impresora_sel, case=False, na=False)]
        
        if not tintas_maquina.empty:
            # Calculamos el precio promedio por ml de ese grupo de tintas
            # (Suma los precios de los 4 colores y divide entre 4)
            precio_tinta_ml = tintas_maquina['precio_usd'].mean()
            
            with st.expander("🔍 Ver tintas vinculadas"):
                st.write(tintas_maquina[['item', 'precio_usd']])
            st.success(f"✅ Promedio detectado: ${precio_tinta_ml:.4f} / ml")
        else:
            precio_tinta_ml = conf.loc['costo_tinta_ml', 'valor']
            st.warning(f"⚠️ No hay tintas para '{impresora_sel}' en Inventario. Usando precio base.")
        
        st.caption(f"Costo por ml: ${precio_tinta_ml:.4f}")

    with c_file:
        archivos_multiples = st.file_uploader("Subir diseños", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if archivos_multiples:
        from PIL import Image
        import numpy as np

        resultados = []
        for arc in archivos_multiples:
            img = Image.open(arc).convert('CMYK')
            datos = np.array(img)
            
            # Promedio de cobertura
            c, m, y, k = [np.mean(datos[:,:,i]) / 255 * 100 for i in range(4)]
            
            # Multiplicadores de consumo por modelo
            nombre_low = impresora_sel.lower()
            if "j210" in nombre_low: multi = 2.5
            elif "subli" in nombre_low or "l1250" in nombre_low: multi = 1.8
            else: multi = 1.0
            
            # Cálculo de consumo (basado en cobertura total)
            cobertura_total = (c + m + y + k)
            consumo_ml = (cobertura_total / 400) * 0.15 * multi 
            
            costo_tinta = consumo_ml * precio_tinta_ml * (1 + iva + igtf)
            total_hoja = costo_tinta + costo_desgaste
            
            resultados.append({
                "Diseño": arc.name,
                "Cobertura": f"{(c+m+y+k)/4:.1f}%",
                "Tinta": f"$ {costo_tinta:.4f}",
                "Máquina": f"$ {costo_desgaste:.4f}",
                "Total ($)": round(total_hoja, 4),
                "Total (Bs)": round(total_hoja * t_bcv, 2)
            })

        st.table(pd.DataFrame(resultados))
        
        # Botón para enviar a Cotización (Pre-paso)
        if st.button("📝 Usar estos costos en una Cotización"):
            st.session_state.costo_cmyk_temp = sum(res['Total ($)'] for res in resultados)
            st.success("¡Costo guardado! Ve al módulo de Cotizaciones para aplicarlo.")
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








































