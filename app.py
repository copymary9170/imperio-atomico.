import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. MOTOR DE BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # NUEVA TABLA PARA TUS EQUIPOS
    c.execute('''CREATE TABLE IF NOT EXISTS activos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)''')
    
    # ... (el resto de tus params se queda igual)
    conn.commit()
    conn.close()

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
t_bcv = conf.loc['tasa_bcv', 'valor']
t_bin = conf.loc['tasa_binance', 'valor']
iva, igtf, banco = conf.loc['iva_perc', 'valor'], conf.loc['igtf_perc', 'valor'], conf.loc['banco_perc', 'valor']
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
df_cots_global = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
conn.close()

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📦 Inventario", "📝 Cotizaciones", "📊 Dashboard", "👥 Clientes", "🎨 Análisis CMYK", "🛠️ Otros Procesos", "🏗️ Activos", "⚙️ Configuración"])
    
# --- 4. LÓGICA DE INVENTARIO ---
if menu == "📦 Inventario":
    st.title("📦 Inventario y Auditoría")

    # --- BUSCADOR DE INVENTARIO ---
    busqueda_inv = st.text_input("🔍 Buscar producto en inventario...", placeholder="Ej: Resma, Tinta...")

    # --- BLOQUE DE ALERTAS DE STOCK BAJO (SOLO AGREGAR) ---
    st.divider()
    
    # Definimos el límite de alerta (puedes cambiar el 10 por el número que prefieras)
    limite_alerta = 10 
    
    # Buscamos los productos que tienen 10 o menos unidades
    if not df_inv.empty:
        df_bajo_stock = df_inv[df_inv['cantidad'] <= limite_alerta]
        
        if not df_bajo_stock.empty:
            st.subheader("⚠️ Materiales por Agotarse")
            for index, row in df_bajo_stock.iterrows():
                # Mostramos un mensaje llamativo por cada producto bajo
                st.warning(f"🚨 **¡Atención!** Quedan pocas unidades de: **{row['item']}** (Solo hay {int(row['cantidad'])} {row['unidad']})")
        else:
            st.success("✅ Tienes suficiente stock de todos tus materiales.")

    # Modificamos la carga del DataFrame para que filtre
    df_inv_filtrado = df_inv[df_inv['item'].str.contains(busqueda_inv, case=False)] if not df_inv.empty else df_inv
    
    with st.expander("📥 Registrar Nueva Compra (Paquetes/Lotes)"):
        with st.form("form_inv"):
            c_info, c_tasa, c_imp = st.columns([2, 1, 1])
            with c_info:
                it_nombre = st.text_input("Nombre del Producto")
                it_cant = st.number_input("¿Unidades que trae el lote?", min_value=1, value=500, step=1)
                it_unid = st.selectbox("Unidad", ["Hojas", "ml", "Unidad", "Resma"])
                precio_lote = st.number_input("Precio TOTAL Lote (USD)", min_value=0.0, format="%.2f")
            with c_tasa:
                st.markdown("### 💱 Tasa")
                tipo_t = st.radio("Tasa de compra:", ["Binance", "BCV"])
                tasa_a = t_bin if tipo_t == "Binance" else t_bcv
            with c_imp:
                st.markdown("### 🧾 Impuestos")
                p_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                p_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)
                p_banco = st.checkbox(f"Banco ({banco*100}%)", value=False)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre:
                    imp_t = (iva if p_iva else 0) + (igtf if p_gtf else 0) + (banco if p_banco else 0)
                    costo_u = (precio_lote * (1 + imp_t)) / it_cant
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it_nombre, float(it_cant), it_unid, costo_u))
                    c.commit(); c.close()
                    st.success(f"✅ Guardado: {it_nombre}")
                    st.rerun()

    st.divider()
    if not df_inv.empty:
        moneda = st.radio("Ver precios en:", ["USD", "BCV", "Binance"], horizontal=True)
        df_audit = df_inv.copy()
        df_audit.columns = ['Producto', 'Stock', 'Unidad', 'Costo Unitario']
        f = t_bcv if moneda == "BCV" else (t_bin if moneda == "Binance" else 1.0)
        sim = "Bs" if moneda != "USD" else "$"
        
        df_audit['Costo Unit.'] = df_audit['Costo Unitario'] * f
        df_audit['Inversión Stock'] = (df_audit['Stock'] * df_audit['Costo Unitario']) * f
        
        st.dataframe(df_audit[['Producto', 'Stock', 'Unidad', 'Costo Unit.', 'Inversión Stock']].style.format({
            'Stock': '{:,.0f}', 'Costo Unit.': f"{sim} {{:.4f}}", 'Inversión Stock': f"{sim} {{:.2f}}"
        }), use_container_width=True, hide_index=True)


        # --- BLOQUE DE ALERTAS DE STOCK BAJO (SOLO AGREGAR) ---
        st.subheader("⚠️ Alertas de Reposición")
        
        # Definimos el límite de alerta (puedes cambiar el 10 por el número que prefieras)
        limite_alerta = 10 
        
        # Filtramos los productos que tienen poco stock
        df_bajo_stock = df_inv[df_inv['cantidad'] <= limite_alerta]
        
        if not df_bajo_stock.empty:
            for index, row in df_bajo_stock.iterrows():
                # Mostramos un mensaje llamativo por cada producto bajo
                st.warning(f"🚨 **¡Atención!** Quedan pocas unidades de: **{row['item']}** (Solo hay {int(row['cantidad'])} {row['unidad']})")
        else:
            st.success("✅ Tienes suficiente stock de todos tus productos.")
        
        # --- SECCIÓN PARA CORREGIR ERRORES ---
        st.divider()
        with st.expander("🗑️ Borrar o Corregir Insumos"):
            prod_b = st.selectbox("Selecciona producto a eliminar:", df_inv['item'].tolist())
            if st.button("❌ Eliminar Producto"):
                c = conectar(); c.execute("DELETE FROM inventario WHERE item=?", (prod_b,))
                c.commit(); c.close(); st.warning(f"Producto {prod_b} eliminado."); st.rerun()

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

# --- 6. DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    if not df_cots_global.empty:
        c1, c2, c3 = st.columns(3)
        total = df_cots_global['monto_usd'].sum()
        c1.metric("Ingresos Totales", f"$ {total:.2f}")
        c2.metric("Total en Bs (BCV)", f"{total * t_bcv:.2f} Bs")
        c3.metric("Cotizaciones", len(df_cots_global))
        st.subheader("📈 Ventas Recientes")
        df_g = df_cots_global.groupby('fecha')['monto_usd'].sum()
        st.area_chart(df_g)
    else:
        st.info("No hay datos registrados.")

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
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (n_bcv,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (n_bin,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='iva_perc'", (n_iva,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='igtf_perc'", (n_igtf,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='banco_perc'", (n_banco,))
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

# --- 10. ANALIZADOR MASIVO DE COBERTURA CMYK (INTELIGENTE) ---
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador de Cobertura y Desgaste")

    # --- CARGA DESDE BASE DE DATOS ---
    conn = conectar()
    # Traemos los activos de la base de datos
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, desgaste FROM activos", conn)
    conn.close()
    
    lista_activos = df_act_db.to_dict('records')
    # Filtramos solo impresoras (usando minúsculas como vienen de la DB)
    impresoras_disponibles = [e['equipo'] for e in lista_activos if e['categoria'] == "Impresora (Gasta Tinta)"]

    if not impresoras_disponibles:
        st.warning("⚠️ No has registrado ninguna Impresora en el módulo de '🏗️ Activos'.")
        st.info("Ve a 'Activos' y registra tus máquinas para que aparezcan aquí.")
    else:
        c_printer, c_file = st.columns([1, 2])
        
        with c_printer:
            impresora_sel = st.selectbox("🖨️ Selecciona la Impresora", impresoras_disponibles)
            
            # Buscamos los datos de la impresora seleccionada
            datos_imp = next((e for e in lista_activos if e['equipo'] == impresora_sel), None)
            
            # El desgaste ahora es directo porque lo guardamos así en la tabla 'activos'
            costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        with c_file:
            archivos_multiples = st.file_uploader("Sube tus diseños (JPG/PNG)", 
                                                 type=['png', 'jpg', 'jpeg'], 
                                                 accept_multiple_files=True)

        if archivos_multiples and datos_imp:
            from PIL import Image
            import numpy as np

            resultados = []
            with st.spinner('Analizando píxeles y calculando costos...'):
                for arc in archivos_multiples:
                    img = Image.open(arc).convert('CMYK')
                    datos = np.array(img)
                    
                    # Porcentajes de cobertura
                    c = (np.mean(datos[:,:,0]) / 255) * 100
                    m = (np.mean(datos[:,:,1]) / 255) * 100
                    y = (np.mean(datos[:,:,2]) / 255) * 100
                    k = (np.mean(datos[:,:,3]) / 255) * 100
                    
                    # Lógica de multiplicador
                    nombre_low = impresora_sel.lower()
                    multi = 2.5 if "j210" in nombre_low else (1.5 if "l1250" in nombre_low or "subli" in nombre_low else 1.0)
                    
                    # Cálculo de Tinta (usando el valor de configuración que ya tienes)
                    costo_tinta_base = conf.loc['costo_tinta_ml', 'valor'] * (1 + iva + igtf + banco)
                    costo_tinta_final = ((c+m+y+k)/400) * 0.8 * costo_tinta_base * multi
                    
                    # COSTO TOTAL = Tinta + Desgaste
                    costo_total_obra = costo_tinta_final + costo_desgaste

                    resultados.append({
                        "Diseño": arc.name,
                        "Cian %": f"{c:.1f}%",
                        "Magenta %": f"{m:.1f}%",
                        "Amarillo %": f"{y:.1f}%",
                        "Negro %": f"{k:.1f}%",
                        "Costo Tinta": f"$ {costo_tinta_final:.4f}",
                        "Desgaste Máq.": f"$ {costo_desgaste:.4f}",
                        "TOTAL": round(costo_total_obra, 4)
                    })

            st.subheader(f"📋 Reporte para {impresora_sel}")
            df_res = pd.DataFrame(resultados)
            st.table(df_res)
            st.success(f"✅ Análisis completado. Costo base calculado.")
    elif not archivos_multiples:
        st.info("💡 Arrastra los archivos para ver cuánto te cuesta imprimirlos en la máquina seleccionada.")
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

    # --- AQUÍ VA LA PARTE 3 (Versión para Otros Procesos) ---
    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, unidad, desgaste FROM activos", conn)
    conn.close()
    
    lista_activos = df_act_db.to_dict('records')
    # Filtramos todo lo que NO sea impresora
    otros_equipos = [e for e in lista_activos if e['categoria'] != "Impresora (Gasta Tinta)"]


    if not otros_equipos:
        st.warning("⚠️ No hay maquinaria registrada (Cameo, Plastificadora, etc.) en el módulo de '🏗️ Activos'.")
    else:
        with st.form("form_procesos"):
            col1, col2, col3 = st.columns(3)
            
            # 1. Seleccionar la máquina
            nombres_eq = [e['Equipo'] for e in otros_equipos]
            eq_sel = col1.selectbox("Herramienta / Máquina", nombres_eq)
            
            # Buscamos los datos de esa máquina
            datos_eq = next(e for e in otros_equipos if e['Equipo'] == eq_sel)
            
            # 2. Cantidad de usos
            unidad = "Usos"
            for clave in datos_eq:
                if "Desgaste x" in clave:
                    unidad = clave.replace("Desgaste x ", "")
                    costo_u = datos_eq[clave]

            cantidad_uso = col2.number_input(f"Cantidad de {unidad}", min_value=1, value=1)
            
            # 3. Material adicional (Opcional, de tu inventario)
            insumos = ["-- Ninguno --"] + df_inv['item'].tolist()
            insumo_sel = col3.selectbox("Insumo extra (Ej: Vinil, Foil)", insumos)
            cant_insumo = col3.number_input("Cantidad de insumo", min_value=0.0, value=0.0)

            if st.form_submit_button("💎 Calcular Costo de Proceso"):
                # Cálculo de desgaste
                total_desgaste = costo_u * cantidad_uso
                
                # Cálculo de insumo
                total_insumo = 0.0
                if insumo_sel != "-- Ninguno --":
                    precio_u_insumo = df_inv[df_inv['item'] == insumo_sel]['precio_usd'].values[0]
                    total_insumo = precio_u_insumo * cant_insumo
                
                costo_total = total_desgaste + total_insumo
                
                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Desgaste {eq_sel}", f"$ {total_desgaste:.4f}")
                c2.metric("Costo Insumos", f"$ {total_insumo:.4f}")
                c3.metric("COSTO TOTAL", f"$ {costo_total:.2f}")
                
                st.success(f"💡 Para este proceso, tu costo base es **$ {costo_total:.2f}**. Sugerimos cobrar al menos el doble para tener ganancia.")





