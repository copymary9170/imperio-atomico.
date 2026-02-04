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
    
    # Parámetros base (Aseguramos que existan todos)
    params = [('tasa_bcv', 36.50), ('tasa_binance', 42.00), ('iva_perc', 0.16), 
              ('igtf_perc', 0.03), ('banco_perc', 0.02), ('costo_tinta_ml', 0.05)]
    for p, v in params:
        c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))
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
    menu = st.radio("Módulos", ["📦 Inventario", "📝 Cotizaciones", "📊 Dashboard", "👥 Clientes", "🎨 Análisis CMYK", "🏗️ Activos", "⚙️ Configuración"])
    
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

# --- 10. ANALIZADOR MASIVO DE COBERTURA CMYK ---
elif menu == "🎨 Análisis CMYK":
    st.title("🎨 Analizador de Cobertura Múltiple")
    st.markdown("Arrastra todos los diseños aquí para obtener los porcentajes de tinta de cada uno.")

    impresora = st.selectbox("🖨️ Configuración de Impresora", 
                             ["HP Advantage J210a (Cartuchos)", 
                              "HP Smart Tank 580w (Tinta Continua)", 
                              "Epson L1250 (Sublimación)"])
    
    # ACTIVAMOS LA CARGA MÚLTIPLE
    archivos_multiples = st.file_uploader("Sube uno o varios archivos (JPG/PNG)", 
                                          type=['png', 'jpg', 'jpeg'], 
                                          accept_multiple_files=True)

    if archivos_multiples:
        from PIL import Image
        import numpy as np
        import pandas as pd

        resultados = []
        
        with st.spinner('Analizando cobertura de todos los archivos...'):
            for arc in archivos_multiples:
                # Abrir y procesar internamente
                img = Image.open(arc).convert('CMYK')
                datos = np.array(img)
                
                # Calcular promedios de CMYK
                c = (np.mean(datos[:,:,0]) / 255) * 100
                m = (np.mean(datos[:,:,1]) / 255) * 100
                y = (np.mean(datos[:,:,2]) / 255) * 100
                k = (np.mean(datos[:,:,3]) / 255) * 100
                
                # Cálculo de costo rápido
                multiplicador = 2.5 if "J210a" in impresora else (1.5 if "L1250" in impresora else 1.0)
                costo_base = conf.loc['costo_tinta_ml', 'valor'] * (1 + iva + igtf + banco)
                costo_est = ((c+m+y+k)/400) * 0.8 * costo_base * multiplicador

                resultados.append({
                    "Archivo": arc.name,
                    "Cian %": f"{c:.1f}%",
                    "Magenta %": f"{m:.1f}%",
                    "Amarillo %": f"{y:.1f}%",
                    "Negro %": f"{k:.1f}%",
                    "Costo Est. ($)": round(costo_est, 4)
                })

        # Mostramos la tabla técnica final
        st.subheader("📋 Resultados del Análisis")
        df_res = pd.DataFrame(resultados)
        st.table(df_res)
        
        st.success("✅ Análisis completado. No se guardó ningún archivo en el sistema.")
    else:
        st.info("💡 Arrastra varios archivos para compararlos y ver cuál gasta más tinta.")

# --- 12. LÓGICA DE ACTIVOS DINÁMICA (EQUIPOS INFINITOS) ---
elif menu == "🏗️ Activos":
    st.title("🏗️ Inventario de Maquinaria y Equipos")
    st.markdown("Registra aquí cada máquina de tu taller para calcular su desgaste.")

    # Inicializamos la lista de equipos en la sesión si no existe
    if 'lista_equipos' not in st.session_state:
        st.session_state.lista_equipos = []

    # --- Formulario para agregar nuevo equipo ---
    with st.expander("➕ Registrar Nuevo Equipo (Cameo, Plastificadora, etc.)"):
        c1, c2 = st.columns(2)
        nombre_eq = c1.text_input("Nombre del Equipo", placeholder="Ej: Cameo 5")
        tipo_uso = c2.selectbox("Unidad de Desgaste", ["Hojas", "Cortes", "Metros", "Minutos", "Usos"])
        
        c3, c4, c5 = st.columns(3)
        moneda = c3.radio("Pago en:", ["USD ($)", "BS (Bs)"])
        monto = c4.number_input("Monto Pagado", min_value=0.0)
        tasa = c5.number_input("Tasa de cambio (si fue en Bs)", min_value=1.0, value=tasa_dia)
        
        # Cálculo de costo base en USD
        costo_usd = monto if moneda == "USD ($)" else (monto / tasa)
        
        vida_util = st.number_input(f"Vida Útil estimada (Total de {tipo_uso})", min_value=1)
        
        if st.button("💾 Guardar Equipo en el Sistema"):
            nuevo_eq = {
                "Equipo": nombre_eq,
                "Inversión": costo_usd,
                "Unidad": tipo_uso,
                "Desgaste x Unidad": costo_usd / vida_util
            }
            st.session_state.lista_equipos.append(nuevo_eq)
            st.success(f"✅ {nombre_eq} agregado con éxito.")

    # --- Tabla de Activos Registrados ---
    if st.session_state.lista_equipos:
        st.subheader("📋 Tus Equipos Registrados")
        df_activos = pd.DataFrame(st.session_state.lista_equipos)
        
        st.table(df_activos.style.format({
            "Inversión": "$ {:.2f}",
            "Desgaste x Unidad": "$ {:.4f}"
        }))
        
        if st.button("🗑️ Limpiar Lista de Equipos"):
            st.session_state.lista_equipos = []
            st.rerun()
    else:
        st.info("Aún no tienes equipos registrados. Usa el formulario de arriba para empezar con tu Cameo 5 o tu Plastificadora.")
