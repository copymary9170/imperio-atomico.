import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime
from PIL import Image
import numpy as np
import io

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide")

# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

def inicializar_sistema():
    """Crea las tablas, valores iniciales y Triggers de seguridad"""
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    # Tablas Maestras
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)')

    # Auditoría y Transacciones
    c.execute('CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')

    # --- TRIGGER DE SEGURIDAD (Nivel Arquitecto) ---
    # Evita que cualquier operación deje el stock en negativo, sin importar qué pase en Python
    c.execute("""
    CREATE TRIGGER IF NOT EXISTS prevent_negative_stock
    BEFORE UPDATE ON inventario
    FOR EACH ROW
    BEGIN
        SELECT CASE
            WHEN NEW.cantidad < 0 THEN
                RAISE(ABORT, 'Error: Stock insuficiente. La operación fue cancelada por seguridad.')
        END;
    END;
    """)

    # Usuarios iniciales
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO usuarios VALUES (?,?,?,?)", [
            ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio'),
            ('mama', 'admin2026', 'Administracion', 'Mamá'),
            ('pro', 'diseno2026', 'Produccion', 'Hermana')
        ])

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

# --- 3. FUNCIONES DE CÁLCULO Y SOPORTE (LOGICA SENIOR) ---

def obtener_tintas_disponibles():
    """Filtro INFALIBLE: Detecta tintas por unidad 'ml' normalizada."""
    if 'df_inv' not in st.session_state or st.session_state.df_inv.empty:
        return pd.DataFrame()
    
    df = st.session_state.df_inv.copy()
    df['unidad_check'] = df['unidad'].fillna('').str.strip().str.lower()
    return df[df['unidad_check'] == 'ml'].copy()

def procesar_venta_grafica_completa(id_cliente, monto, metodo, consumos_dict):
    """
    Transacción ACID Multi-Tinta: Registra venta y descuenta múltiples 
    tintas simultáneamente. Si una falla, hace Rollback completo.
    """
    conn = conectar()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN TRANSACTION")

        # 1. Registrar la Venta Principal
        cur.execute("""INSERT INTO ventas (cliente_id, monto_total, metodo, fecha) 
                       VALUES (?, ?, ?, ?)""", 
                    (id_cliente, monto, metodo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        venta_id = cur.lastrowid

        # 2. Procesar cada tinta del set (C, M, Y, K)
        for item_id, ml in consumos_dict.items():
            if ml <= 0: continue
            
            # Intento de descuento. El Trigger de SQLite bloqueará si NEW.cantidad < 0
            cur.execute("""UPDATE inventario SET cantidad = cantidad - ? 
                           WHERE id = ?""", (ml, item_id))
            
            # Auditoría de movimiento por color
            cur.execute("""INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario) 
                           VALUES (?, 'SALIDA', ?, ?, ?)""",
                        (item_id, ml, f"Consumo Venta #{venta_id}", st.session_state.get('usuario_nombre', 'Sistema')))

        conn.commit()
        return True, f"✅ Venta #{venta_id} procesada con éxito."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Error de Base de Datos: {str(e)}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def cargar_datos():
    """Carga configuración y tablas maestras en la sesión"""
    try:
        conn = conectar()
        st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
        st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
        conf = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')

        st.session_state.tasa_bcv = float(conf.loc['tasa_bcv', 'valor'])
        st.session_state.tasa_binance = float(conf.loc['tasa_binance', 'valor'])
        st.session_state.iva = float(conf.loc['iva_perc', 'valor'])
        st.session_state.igtf = float(conf.loc['igtf_perc', 'valor'])
        st.session_state.banco = float(conf.loc['banco_perc', 'valor'])
        st.session_state.costo_tinta_ml = float(conf.loc['costo_tinta_ml', 'valor'])
        conn.close()
    except Exception as e:
        st.error(f"Error en carga de datos: {e}")

def cargar_datos_seguros():
    cargar_datos()
    st.toast("🔄 Datos sincronizados")

# --- 4. LÓGICA DE ACCESO ---
inicializar_sistema()

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Imperio Atómico")
    with st.form("login"):
        u = st.text_input("Usuario").lower().strip()
        p = st.text_input("Clave", type="password")
        if st.form_submit_button("Entrar"):
            conn = conectar(); cur = conn.cursor()
            cur.execute("SELECT rol, nombre FROM usuarios WHERE username=? AND password=?", (u, p))
            res = cur.fetchone(); conn.close()
            if res:
                st.session_state.autenticado, st.session_state.rol, st.session_state.usuario_nombre = True, res[0], res[1]
                cargar_datos()
                st.rerun()
            else:
                st.error("❌ Credenciales incorrectas")
    st.stop()

# --- 5. PREPARACIÓN DE INTERFAZ ---
cargar_datos()
t_bcv = st.session_state.tasa_bcv
t_bin = st.session_state.tasa_binance
ROL = st.session_state.rol

with st.sidebar:
    st.header(f"👋 Hola, {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv:.2f} | 🔶 BIN: {t_bin:.2f}")
    
    opciones = ["📝 Cotizaciones", "🎨 Análisis CMYK", "👥 Clientes"]
    
    if ROL == "Admin":
        opciones += [
            "💰 Ventas", 
            "📉 Gastos", 
            "📦 Inventario", 
            "📊 Dashboard", 
            "📊 Auditoría y Métricas", # <--- NUEVO MÓDULO PARA EL JEFE
            "🏗️ Activos", 
            "🛠️ Otros Procesos", 
            "⚙️ Configuración", 
            "🏁 Cierre de Caja"
        ]
    elif ROL == "Administracion":
        opciones += [
            "💰 Ventas", 
            "📉 Gastos", 
            "📊 Dashboard", 
            "📊 Auditoría y Métricas", # <--- TAMBIÉN PARA ADMINISTRACIÓN
            "⚙️ Configuración", 
            "🏁 Cierre de Caja"
        ]
    elif ROL == "Produccion":
        opciones += ["📦 Inventario", "🏗️ Activos", "🛠️ Otros Procesos"]

    menu = st.radio("Seleccione una opción:", opciones, key="menu_principal")
    
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
# --- 6. MÓDULOS DE INTERFAZ ---

if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    df_inv = st.session_state.df_inv
    if not df_inv.empty:
        valor_usd = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Dólares", f"$ {valor_usd:,.2f}")
        c2.metric("Total BCV", f"Bs {(valor_usd * t_bcv):,.2f}")
        c3.metric("Tasa Actual", f"{t_bcv} Bs")
    
    st.divider()
    with st.form("form_inventario"):
        it_nombre = st.text_input("Nombre del Insumo")
        it_unid = st.selectbox("Unidad:", ["ml", "Hojas", "Resma", "Unidad", "Metros"])
        it_cant = st.number_input("Cantidad", min_value=0.0)
        it_precio = st.number_input("Costo Unitario ($)", min_value=0.0, format="%.4f")
        if st.form_submit_button("🚀 GUARDAR EN INVENTARIO"):
            conn = conectar(); c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?,?,?,?)",
                      (it_nombre, it_cant, it_unid, it_precio))
            conn.commit(); conn.close()
            cargar_datos_seguros(); st.rerun()

elif menu == "📊 Dashboard":
    st.title("📊 Centro de Control Financiero")
    conn = conectar()
    df_ventas = pd.read_sql("SELECT * FROM ventas", conn)
    df_gastos = pd.read_sql("SELECT * FROM gastos", conn)
    conn.close()
    
    ingresos = df_ventas['monto_total'].sum() if not df_ventas.empty else 0
    egresos = df_gastos['monto'].sum() if not df_gastos.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos", f"$ {ingresos:.2f}")
    c2.metric("Egresos", f"$ {egresos:.2f}", delta=f"-{egresos:.2f}", delta_color="inverse")
    c3.metric("Balance", f"$ {ingresos - egresos:.2f}")

# --- CONTINÚA CON EL MÓDULO 7 EN EL SIGUIENTE BLOQUE ---
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

    # 1. Carga de datos profesional con validación de seguridad (Evita KeyError)
    df_tintas_db = obtener_tintas_disponibles()
    
    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, desgaste FROM activos", conn)
    conn.close()
    
    impresoras_disponibles = [e['equipo'] for e in df_act_db.to_dict('records') if e['categoria'] == "Impresora (Gasta Tinta)"]

    if not impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en 'Activos'.")
        st.stop()

    c_printer, c_file = st.columns([1, 2])
    
    with c_printer:
        impresora_sel = st.selectbox("🖨️ Selecciona la Impresora", impresoras_disponibles)
        datos_imp = next((e for e in df_act_db.to_dict('records') if e['equipo'] == impresora_sel), None)
        costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        # Blindaje de precio: Busca por nombre de impresora pero solo en ítems 'ml'
        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)
        if not df_tintas_db.empty and 'item' in df_tintas_db.columns:
            tintas_maquina = df_tintas_db[df_tintas_db['item'].str.contains(impresora_sel, case=False, na=False)]
            if not tintas_maquina.empty:
                precio_tinta_ml = tintas_maquina['precio_usd'].mean()
                st.success(f"✅ Precio detectado: ${precio_tinta_ml:.4f}/ml")

    with c_file:
        # Restauración de carga múltiple y filtros de archivo
        archivos_multiples = st.file_uploader(
            "Sube tus diseños (PDF, JPG, PNG)", 
            type=['pdf', 'png', 'jpg', 'jpeg'], 
            accept_multiple_files=True,
            key="uploader_cmyk_v_final"
        )

    # --- MOTOR DE PROCESAMIENTO ---
    if archivos_multiples:
        import fitz  
        from PIL import Image
        import numpy as np

        resultados = []
        totales_canales = {'c': 0.0, 'm': 0.0, 'y': 0.0, 'k': 0.0}
        total_paginas_lote = 0
        
        with st.spinner('🚀 Analizando archivos...'):
            for arc in archivos_multiples:
                imagenes_a_procesar = []
                arc_bytes = arc.read()
                
                # Identificación de tipo por extensión
                if arc.name.lower().endswith('.pdf'):
                    try:
                        doc = fitz.open(stream=arc_bytes, filetype="pdf")
                        for page_num in range(len(doc)):
                            page = doc.load_page(page_num)
                            pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)
                            img_pil = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                            imagenes_a_procesar.append((f"{arc.name} (P{page_num+1})", img_pil))
                    except Exception as e:
                        st.error(f"Error PDF {arc.name}: {e}")
                else:
                    try:
                        img_pil = Image.open(io.BytesIO(arc_bytes)).convert('CMYK')
                        imagenes_a_procesar.append((arc.name, img_pil))
                    except Exception as e:
                        st.error(f"Error Imagen {arc.name}: {e}")

                # --- CÁLCULO DE COBERTURA CON DESGLOSE VISUAL ---
                for nombre_item, img in imagenes_a_procesar:
                    total_paginas_lote += 1
                    datos = np.array(img)
                    
                    # Porcentajes de cobertura (0.0 a 1.0)
                    c_p, m_p, y_p, k_p = [np.mean(datos[:,:,i]) / 255 for i in range(4)]
                    
                    # Multiplicadores de consumo por modelo
                    nombre_low = impresora_sel.lower()
                    multi = 2.5 if "j210" in nombre_low else (1.8 if "subli" in nombre_low else 1.2)
                    
                    # ML por cada canal individual
                    ml_c, ml_m, ml_y, ml_k = [p * 0.15 * multi for p in [c_p, m_p, y_p, k_p]]
                    
                    # Acumuladores para el Módulo 11 (Cotizaciones)
                    totales_canales['c'] += ml_c
                    totales_canales['m'] += ml_m
                    totales_canales['y'] += ml_y
                    totales_canales['k'] += ml_k
                    
                    consumo_total_item = ml_c + ml_m + ml_y + ml_k
                    costo_tinta_item = consumo_total_item * precio_tinta_ml
                    total_usd_item = costo_tinta_item + costo_desgaste
                    
                    resultados.append({
                        "Archivo": nombre_item,
                        "C%": f"{c_p*100:.1f}%", "M%": f"{m_p*100:.1f}%", 
                        "Y%": f"{y_p*100:.1f}%", "K%": f"{k_p*100:.1f}%",
                        "ml": round(consumo_total_item, 4),
                        "Costo USD": round(total_usd_item, 4)
                    })

        # --- MOSTRAR RESULTADOS ---
        if resultados:
            st.divider()
            df_res = pd.DataFrame(resultados)
            st.subheader("📊 Desglose de Cobertura CMYK")
            st.dataframe(df_res, use_container_width=True, hide_index=True)
            
            total_usd_lote = sum(r['Costo USD'] for r in resultados)
            st.success(f"💰 Costo Producción Lote: **${total_usd_lote:.2f} USD**")

            if st.button("📝 ENVIAR TODO A COTIZACIÓN", use_container_width=True, type="primary"):
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Producción {impresora_sel}: {len(archivos_multiples)} archivos",
                    'costo_base': total_usd_lote,
                    'c_ml': totales_canales['c'], 'm_ml': totales_canales['m'],
                    'y_ml': totales_canales['y'], 'k_ml': totales_canales['k'],
                    'unidades': total_paginas_lote
                }
                st.toast("✅ Datos desglosados listos en Cotizaciones")
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

elif menu == "🛠️ Otros Procesos":
    st.title("🛠️ Calculadora de Procesos Especiales")
    
    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, unidad, desgaste FROM activos", conn)
    conn.close()
    
    otros_equipos = df_act_db[df_act_db['categoria'] != "Impresora (Gasta Tinta)"].to_dict('records')

    if not otros_equipos:
        st.warning("⚠️ No hay maquinaria registrada en '🏗️ Activos'.")
    else:
        with st.form("form_procesos_fijo"):
            col1, col2, col3 = st.columns(3)
            nombres_eq = [e['equipo'] for e in otros_equipos]
            eq_sel = col1.selectbox("Herramienta / Máquina", nombres_eq)
            
            datos_eq = next((e for e in otros_equipos if e['equipo'] == eq_sel), None)
            
            # Lógica completada:
            cantidad_uso = col2.number_input(f"Cantidad de {datos_eq['unidad']}:", min_value=1, value=1)
            costo_insumo_extra = col3.number_input("Insumo Extra ($) (Ej: Vinil, Foil)", min_value=0.0)
            
            if st.form_submit_button("⚖️ Calcular Proceso"):
                desgaste_total = datos_eq['desgaste'] * cantidad_uso
                costo_final = desgaste_total + costo_insumo_extra
                
                st.metric("Costo Total del Proceso", f"$ {costo_final:.2f}")
                
                # Guardar para cotización
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Proceso: {eq_sel} ({cantidad_uso} {datos_eq['unidad']})",
                    'costo_base': costo_final,
                    'ml_estimados': 0,
                    'unidades': 1
                }
                st.success("✅ Enviado a Cotizaciones")

# --- 15. MÓDULO DE VENTAS Y GASTOS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ingresos")
    with st.form("registro_venta"):
        c1, c2, c3 = st.columns(3)
        cli_v = c1.selectbox("Cliente", st.session_state.df_cli['nombre'].tolist())
        monto_v = c2.number_input("Monto Cobrado ($)", min_value=0.0)
        metodo_v = c3.selectbox("Método de Pago", ["Efectivo $", "Zelle", "Pago Móvil", "Transferencia", "Binance"])
        
        if st.form_submit_button("💸 Registrar Venta"):
            conn = conectar(); c = conn.cursor()
            c.execute("INSERT INTO ventas (cliente_id, monto_total, metodo) VALUES ((SELECT id FROM clientes WHERE nombre=?), ?, ?)",
                      (cli_v, monto_v, metodo_v))
            conn.commit(); conn.close()
            st.success("Venta guardada exitosamente.")

elif menu == "📉 Gastos":
    st.title("📉 Registro de Egresos")
    with st.form("registro_gasto"):
        c1, c2 = st.columns(2)
        desc_g = c1.text_input("Descripción del Gasto")
        monto_g = c2.number_input("Monto ($)", min_value=0.0)
        cat_g = st.selectbox("Categoría", ["Insumos", "Servicios", "Sueldos", "Mantenimiento", "Otros"])
        met_g = st.selectbox("Pagado desde", ["Caja Chica", "Zelle Personal", "Banco Bs"])
        
        if st.form_submit_button("❌ Registrar Gasto"):
            conn = conectar(); c = conn.cursor()
            c.execute("INSERT INTO gastos (descripcion, monto, categoria, metodo) VALUES (?,?,?,?)",
                      (desc_g, monto_g, cat_g, met_g))
            conn.commit(); conn.close()
            st.error(f"Gasto de ${monto_g} registrado.")

# --- 16. MÓDULO CIERRE DE CAJA (RESUMEN FINAL) ---
elif menu == "🏁 Cierre de Caja":
    st.title("🏁 Cierre de Caja del Día")
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    conn = conectar()
    v_hoy = pd.read_sql(f"SELECT * FROM ventas WHERE fecha LIKE '{hoy}%'", conn)
    g_hoy = pd.read_sql(f"SELECT * FROM gastos WHERE fecha LIKE '{hoy}%'", conn)
    conn.close()
    
    total_v = v_hoy['monto_total'].sum()
    total_g = g_hoy['monto'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Ventas Hoy", f"$ {total_v:.2f}")
    c2.metric("Gastos Hoy", f"$ {total_g:.2f}", delta=f"-{total_g:.2f}", delta_color="inverse")
    c3.metric("Neto en Caja", f"$ {(total_v - total_g):.2f}")
    
    st.subheader("Detalle de Movimientos")
    st.write("Ventas:")
    st.dataframe(v_hoy, use_container_width=True)
    st.write("Gastos:")
    st.dataframe(g_hoy, use_container_width=True)
    
    if st.button("🖨️ Generar Reporte PDF (Simulado)"):
        st.info("Función de reporte lista para conectar a impresora térmica.")

# --- 11. MÓDULO DE COTIZACIONES (SISTEMA MULTI-TINTA PROFESIONAL) ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Cotizaciones Atómicas")
    
    # 1. Recuperar datos del Analizador CMYK
    datos_pre = st.session_state.get('datos_pre_cotizacion', {
        'trabajo': "Trabajo General",
        'costo_base': 0.0,
        'c_ml': 0.0, 'm_ml': 0.0, 'y_ml': 0.0, 'k_ml': 0.0,
        'unidades': 1
    })

    with st.container(border=True):
        st.subheader("🛠️ Detalles del Trabajo")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            descr = st.text_input("Descripción del trabajo:", value=datos_pre['trabajo'])
            # Usamos el dataframe ya cargado en session_state para mayor velocidad
            df_clis = st.session_state.df_cli
            
            if not df_clis.empty:
                opciones_cli = {row['nombre']: row['id'] for _, row in df_clis.iterrows()}
                cliente_sel = st.selectbox("👤 Asignar a Cliente:", opciones_cli.keys())
                id_cliente = opciones_cli[cliente_sel]
            else:
                st.warning("⚠️ No hay clientes registrados.")
                st.stop()

        with col2:
            unidades = st.number_input("Cantidad de piezas:", min_value=1, value=int(datos_pre['unidades']))

    # --- 💉 GESTIÓN DE CONSUMO MULTI-TINTA ---
    st.subheader("💉 Despacho de Insumos por Color")
    df_tintas = obtener_tintas_disponibles()
    consumos_reales = {} 
    
    if not df_tintas.empty:
        dict_t = {f"{r['item']} ({r['cantidad']:.1f} ml)": r['id'] for _, r in df_tintas.iterrows()}
        
        if any([datos_pre['c_ml'], datos_pre['m_ml'], datos_pre['y_ml'], datos_pre['k_ml']]):
            st.info("🎨 Se detectó análisis CMYK. Asigne las botellas correspondientes:")
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                t_c = st.selectbox("Cian (C)", dict_t.keys(), key="sel_c")
                consumos_reales[dict_t[t_c]] = datos_pre['c_ml'] * unidades
            with c2:
                t_m = st.selectbox("Magenta (M)", dict_t.keys(), key="sel_m")
                consumos_reales[dict_t[t_m]] = datos_pre['m_ml'] * unidades
            with c3:
                t_y = st.selectbox("Amarillo (Y)", dict_t.keys(), key="sel_y")
                consumos_reales[dict_t[t_y]] = datos_pre['y_ml'] * unidades
            with c4:
                t_k = st.selectbox("Negro (K)", dict_t.keys(), key="sel_k")
                consumos_reales[dict_t[t_k]] = datos_pre['k_ml'] * unidades
        else:
            st.warning("⚠️ No hay datos de color. Seleccione un insumo base si desea descontar stock:")
            t_gen = st.selectbox("Insumo a descontar:", ["Ninguno"] + list(dict_t.keys()))
            if t_gen != "Ninguno":
                ml_manual = st.number_input("ML totales a descontar:", min_value=0.0, format="%.4f")
                consumos_reales[dict_t[t_gen]] = ml_manual
    else:
        st.error("🚨 No hay insumos con unidad 'ml' en el inventario.")

    # --- 💰 CÁLCULO DE PRECIOS ---
    st.subheader("💰 Estructura Comercial")
    c1, c2 = st.columns(2)
    
    costo_unitario_base = c1.number_input("Costo Unit. Base ($)", 
                                          value=float(datos_pre['costo_base'] / unidades if unidades > 0 else 0.0), 
                                          format="%.4f")
    margen = c2.slider("Margen de Ganancia %", 10, 500, 100, 10)
    
    costo_total_prod = costo_unitario_base * unidades
    precio_venta_total = costo_total_prod * (1 + (margen / 100))

    st.divider()
    v1, v2, v3 = st.columns(3)
    v1.metric("Costo Total", f"$ {costo_total_prod:.2f}")
    v2.metric("Precio Venta", f"$ {precio_venta_total:.2f}", delta=f"${precio_venta_total-costo_total_prod:.2f} Ganancia")
    v3.metric("Total Bs (BCV)", f"Bs {(precio_venta_total * t_bcv):,.2f}")

    # --- 🚀 REGISTRO ATÓMICO Y PREVENCIÓN DE DUPLICADOS ---
    st.divider()
    metodo_pago = st.selectbox("💳 Método de Pago:", ["Efectivo $", "Zelle", "Pago Móvil", "Transferencia Bs", "Binance"])
    
    # Generamos la llave de integridad para evitar doble clic
    llave_operacion = f"v_{id_cliente}_{precio_venta_total:.2f}_{unidades}_{descr}"

    if st.button("🚀 REGISTRAR VENTA Y DESCONTAR STOCK", use_container_width=True, type="primary"):
        # Verificación anti-duplicados
        if st.session_state.get('last_op_key') == llave_operacion:
            st.warning("⚠️ Esta operación ya fue procesada.")
        elif not consumos_reales and any([datos_pre['c_ml'], datos_pre['m_ml']]):
            st.error("Debe asignar las tintas para poder descontar el stock.")
        else:
            with st.spinner("Registrando transacción en el Imperio..."):
                exito, msg = procesar_venta_grafica_completa(
                    id_cliente=id_cliente,
                    monto=precio_venta_total,
                    metodo=metodo_pago,
                    consumos_dict=consumos_reales
                )
                
                if exito:
                    # Bloqueamos la llave y limpiamos datos
                    st.session_state['last_op_key'] = llave_operacion
                    st.balloons()
                    st.success(msg)
                    if 'datos_pre_cotizacion' in st.session_state:
                        del st.session_state['datos_pre_cotizacion']
                    
                    cargar_datos_seguros()
                    st.rerun()
                else:
                    # El Trigger de SQLite o la lógica de stock dispararán este error si falla
                    st.error(msg)

    if st.button("🗑️ Limpiar Cotización"):
        if 'datos_pre_cotizacion' in st.session_state:
            del st.session_state['datos_pre_cotizacion']
        st.rerun()

# --- 13. MÓDULO DE AUDITORÍA Y MÉTRICAS (VISIÓN GERENCIAL) ---
elif menu == "📊 Auditoría y Métricas":
    st.title("📊 Auditoría de Producción e Insumos")
    
    conn = conectar()
    cursor = conn.cursor()
    
    # --- 🛡️ BLINDAJE: CREACIÓN Y ACTUALIZACIÓN AUTOMÁTICA ---
    # 1. Asegurar que la tabla base exista
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario_movs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. CIRUJANO DE DB: Inyectar columnas si la tabla existía pero estaba incompleta
    columnas_necesarias = [
        ("item", "TEXT"),
        ("cantidad", "REAL"),
        ("unidad", "TEXT"),
        ("tipo_mov", "TEXT"),
        ("referencia", "TEXT")
    ]
    
    for col_nombre, col_tipo in columnas_necesarias:
        try:
            cursor.execute(f"ALTER TABLE inventario_movs ADD COLUMN {col_nombre} {col_tipo}")
        except:
            # Si da error es que la columna ya existe, ignoramos y seguimos
            pass
            
    conn.commit()

    # 3. Consulta segura
    query_movs = """
        SELECT fecha, item, cantidad, unidad, tipo_mov 
        FROM inventario_movs 
        WHERE unidad = 'ml' 
        ORDER BY fecha DESC
    """
    
    try:
        df_movs = pd.read_sql_query(query_movs, conn)
    except Exception as e:
        st.error(f"Error al leer auditoría: {e}")
        df_movs = pd.DataFrame()
    finally:
        conn.close()

    tab1, tab2 = st.tabs(["🧪 Consumo de Tinta", "📈 Flujo General"])

    with tab1:
        st.subheader("Análisis de Consumo por Color")
        if not df_movs.empty:
            # Filtramos solo salidas (ventas)
            df_salidas = df_movs[df_movs['tipo_mov'] == 'SALIDA'].copy()
            
            if not df_salidas.empty:
                df_salidas['fecha'] = pd.to_datetime(df_salidas['fecha']).dt.date
                consumo_total = df_salidas.groupby('item')['cantidad'].sum().reset_index()
                
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.bar_chart(data=consumo_total, x='item', y='cantidad')
                with c2:
                    st.write("📋 **Resumen de Gastos**")
                    st.table(consumo_total)
                
                st.divider()
                st.write("🔍 **Log de Salidas CMYK**")
                st.dataframe(df_salidas, use_container_width=True, hide_index=True)
            else:
                st.info("💡 No hay registros de 'SALIDA' aún. Procesa una venta para ver datos.")
        else:
            st.info("🔍 No hay movimientos de tinta registrados en la base de datos.")

    with tab2:
        st.subheader("Historial Completo de Movimientos")
        if not df_movs.empty:
            st.dataframe(df_movs, use_container_width=True)
        else:
            st.warning("El historial está vacío. Realiza operaciones en Inventario o Ventas.")







