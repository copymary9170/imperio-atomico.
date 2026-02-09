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
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)')

    c.execute('CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')

    c.execute("""
    CREATE TRIGGER IF NOT EXISTS prevent_negative_stock
    BEFORE UPDATE ON inventario
    FOR EACH ROW
    BEGIN
        SELECT CASE
            WHEN NEW.cantidad < 0 THEN
                RAISE(ABORT, 'Error: Stock insuficiente.')
        END;
    END;
    """)

    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO usuarios VALUES (?,?,?,?)", [
            ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio'),
            ('mama', 'admin2026', 'Administracion', 'Mamá'),
            ('pro', 'diseno2026', 'Produccion', 'Hermana')
        ])

    config_init = [
        ('tasa_bcv', 36.50), ('tasa_binance', 38.00),
        ('iva_perc', 0.16), ('igtf_perc', 0.03),
        ('banco_perc', 0.02), ('costo_tinta_ml', 0.10)
    ]

    for param, valor in config_init:
        c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (param, valor))

    conn.commit()
    conn.close()
def obtener_tintas_disponibles():
    if 'df_inv' not in st.session_state or st.session_state.df_inv.empty:
        return pd.DataFrame()

    df = st.session_state.df_inv.copy()
    df['unidad_check'] = df['unidad'].fillna('').str.strip().str.lower()
    return df[df['unidad_check'] == 'ml'].copy()
def cargar_datos():
    try:
        conn = conectar()
        st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
        st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)

        conf = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')

        st.session_state.tasa_bcv = float(conf.loc['tasa_bcv','valor'])
        st.session_state.tasa_binance = float(conf.loc['tasa_binance','valor'])
        st.session_state.costo_tinta_ml = float(conf.loc['costo_tinta_ml','valor'])

        conn.close()
    except Exception as e:
        st.error(f"Error cargando datos: {e}")

def cargar_datos_seguros():
    cargar_datos()
    st.toast("Datos actualizados")
t_bcv = st.session_state.tasa_bcv
t_bin = st.session_state.tasa_binance
ROL = st.session_state.rol
with st.sidebar:
    st.header(f"Hola {st.session_state.usuario_nombre}")
    st.info(f"BCV: {t_bcv:.2f} | Binance: {t_bin:.2f}")

    opciones = ["📝 Cotizaciones", "🎨 Análisis CMYK", "👥 Clientes"]

    if ROL == "Admin":
        opciones += [
            "💰 Ventas",
            "📉 Gastos",
            "📦 Inventario",
            "📊 Dashboard",
            "🏗️ Activos",
            "⚙️ Configuración"
        ]

    menu = st.radio("Menú:", opciones)

    if st.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
# --- 6. MÓDULOS DE INTERFAZ: INVENTARIO ---
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Inventario")
    df_inv = st.session_state.df_inv

    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        moneda_ver = st.radio("Ver Inventario en:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], horizontal=True)

    tasa_ver = 1.0 if "USD" in moneda_ver else (t_bcv if "BCV" in moneda_ver else t_bin)
    simbolo = "$" if "USD" in moneda_ver else "Bs"

    if not df_inv.empty:
        valor_usd = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Valor Almacén ({simbolo})", f"{simbolo} {(valor_usd * tasa_ver):,.2f}")
        c2.metric("Tasa BCV", f"{t_bcv} Bs")
        c3.metric("Tasa Binance", f"{t_bin} Bs")

    st.divider()

    tab_lista, tab_registro, tab_edicion = st.tabs(["📋 Inventario Actual", "🆕 Registro / Carga", "🛠️ Modificar / Borrar"])

    with tab_registro:
        with st.form("form_registro_pro"):
            st.subheader("🆕 Cargar Mercancía")
            c_u, c_n = st.columns([1, 2])

            u_medida = c_u.selectbox("Unidad:", ["ml", "Hojas", "Resma", "Unidad", "Metros"])
            it_nombre = c_n.text_input("Nombre del Material").strip()

            if u_medida == "ml":
                col1, col2 = st.columns(2)
                ml_bote = col1.number_input("ml por bote:", value=100.0)
                cant_botes = col2.number_input("Cantidad botes:", value=1)
                total_unidades = ml_bote * cant_botes
            else:
                total_unidades = st.number_input(f"Cantidad de {u_medida}:", value=1.0)

            st.markdown("---")
            st.write("💰 **Costos de Adquisición**")

            cc1, cc2, cc3 = st.columns(3)
            monto_pago = cc1.number_input("Monto pagado:", min_value=0.0)
            moneda_pago = cc2.selectbox("Pagado a tasa:", ["USD $", "Bs (Tasa BCV)", "Bs (Tasa Binance)"])
            imp_ley = cc3.selectbox("Impuesto Gob:", ["Ninguno", "16% IVA", "3% IGTF"])

            comision_banco = st.slider("Comisión Bancaria / Transacción (%)", 0.0, 5.0, 0.5, step=0.1)

            if st.form_submit_button("🚀 REGISTRAR ENTRADA"):
                if it_nombre:
                    t_compra = 1.0
                    if "BCV" in moneda_pago:
                        t_compra = t_bcv
                    if "Binance" in moneda_pago:
                        t_compra = t_bin

                    base_usd = monto_pago / t_compra
                    pct_gob = 0.16 if "16%" in imp_ley else (0.03 if "3%" in imp_ley else 0.0)
                    costo_total_usd = base_usd * (1 + pct_gob + (comision_banco / 100))
                    costo_unitario_final = costo_total_usd / total_unidades

                    conn = conectar()
                    c = conn.cursor()

                    c.execute(
                        "INSERT OR IGNORE INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?,0,?,?)",
                        (it_nombre, u_medida, costo_unitario_final)
                    )

                    c.execute(
                        "UPDATE inventario SET cantidad = cantidad + ?, precio_usd = ? WHERE item = ?",
                        (total_unidades, costo_unitario_final, it_nombre)
                    )

                    conn.commit()
                    conn.close()

                    st.success("✅ ¡Inventario Actualizado!")
                    cargar_datos_seguros()
                    st.rerun()

    with tab_lista:
        if not df_inv.empty:
            df_ver = df_inv.copy()
            df_ver['precio_usd'] = df_ver['precio_usd'] * tasa_ver

            st.dataframe(
                df_ver.rename(columns={'precio_usd': f'Costo ({simbolo})'}),
                use_container_width=True,
                hide_index=True
            )

    with tab_edicion:
        st.subheader("🛠️ Modificar o Eliminar")

        if not df_inv.empty:
            item_edit = st.selectbox("Seleccionar item:", df_inv['item'].tolist())
            datos_e = df_inv[df_inv['item'] == item_edit].iloc[0]

            with st.form("form_edit"):
                new_q = st.number_input("Cantidad Actual", value=float(datos_e['cantidad']))
                new_p = st.number_input("Precio ($)", value=float(datos_e['precio_usd']), format="%.4f")

                if st.form_submit_button("💾 Guardar"):
                    conn = conectar()
                    c = conn.cursor()

                    c.execute(
                        "UPDATE inventario SET cantidad=?, precio_usd=? WHERE id=?",
                        (new_q, new_p, datos_e['id'])
                    )

                    conn.commit()
                    conn.close()

                    cargar_datos_seguros()
                    st.rerun()

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

elif menu == "⚙️ Configuración":

    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden cambiar tasas y costos.")
        st.stop()

    st.title("⚙️ Configuración del Sistema")
    st.info("Desde aquí controlas los precios base y las tasas para combatir la inflación.")

    conn = conectar()
    conf_df = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')

    with st.form("config_general"):

        st.subheader("💵 Tasas de Cambio")

        c1, c2 = st.columns(2)
        nueva_bcv = c1.number_input("Tasa BCV (Bs/$)", value=float(conf_df.loc['tasa_bcv', 'valor']), format="%.2f")
        nueva_bin = c2.number_input("Tasa Binance (Bs/$)", value=float(conf_df.loc['tasa_binance', 'valor']), format="%.2f")

        st.divider()

        st.subheader("💉 Costos de Insumos Críticos")

        costo_tinta = st.number_input(
            "Costo de Tinta por ml ($)",
            value=float(conf_df.loc['costo_tinta_ml', 'valor']),
            format="%.4f"
        )

        st.divider()

        st.subheader("🛡️ Impuestos y Comisiones")

        c3, c4, c5 = st.columns(3)

        n_iva = c3.number_input("IVA", value=float(conf_df.loc['iva_perc', 'valor']), format="%.2f")
        n_igtf = c4.number_input("IGTF", value=float(conf_df.loc['igtf_perc', 'valor']), format="%.2f")
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

            st.success("✅ ¡Configuración actualizada!")
            st.rerun()

    conn.close()

# --- 8. LÓGICA DE CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Registro de Clientes")

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

    c = conectar()
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
        st.warning("⚠️ No hay impresoras registradas en 'Activos'.")
        st.stop()

    c_printer, c_file = st.columns([1, 2])

    with c_printer:
        impresora_sel = st.selectbox("🖨️ Selecciona la Impresora", impresoras_disponibles)

        datos_imp = next((e for e in df_act_db.to_dict('records') if e['equipo'] == impresora_sel), None)
        costo_desgaste = datos_imp['desgaste'] if datos_imp else 0.0

        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)

        if not df_tintas_db.empty:
            tintas_maquina = df_tintas_db[
                df_tintas_db['item'].str.contains(impresora_sel, case=False, na=False)
            ]

            if not tintas_maquina.empty:
                precio_tinta_ml = tintas_maquina['precio_usd'].mean()
                st.success(f"✅ Precio detectado: ${precio_tinta_ml:.4f}/ml")

    with c_file:
        archivos_multiples = st.file_uploader(
            "Sube tus diseños (PDF, JPG, PNG)",
            type=['pdf', 'png', 'jpg', 'jpeg'],
            accept_multiple_files=True
        )

    if archivos_multiples:
        import fitz

        resultados = []
        totales_canales = {'c': 0.0, 'm': 0.0, 'y': 0.0, 'k': 0.0}
        total_paginas_lote = 0

        with st.spinner('🚀 Analizando archivos...'):
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
                else:
                    img_pil = Image.open(io.BytesIO(arc_bytes)).convert('CMYK')
                    imagenes.append((arc.name, img_pil))

                for nombre_item, img in imagenes:
                    total_paginas_lote += 1
                    datos = np.array(img)

                    c_p, m_p, y_p, k_p = [np.mean(datos[:, :, i]) / 255 for i in range(4)]

                    nombre_low = impresora_sel.lower()
                    multi = 2.5 if "j210" in nombre_low else (1.8 if "subli" in nombre_low else 1.2)

                    ml_c, ml_m, ml_y, ml_k = [p * 0.15 * multi for p in [c_p, m_p, y_p, k_p]]

                    totales_canales['c'] += ml_c
                    totales_canales['m'] += ml_m
                    totales_canales['y'] += ml_y
                    totales_canales['k'] += ml_k

                    consumo_total = ml_c + ml_m + ml_y + ml_k
                    costo_tinta = consumo_total * precio_tinta_ml
                    total_usd = costo_tinta + costo_desgaste

                    resultados.append({
                        "Archivo": nombre_item,
                        "ml": round(consumo_total, 4),
                        "Costo USD": round(total_usd, 4)
                    })

        if resultados:
            st.dataframe(pd.DataFrame(resultados), use_container_width=True)

            total_usd_lote = sum(r['Costo USD'] for r in resultados)

            if st.button("📝 ENVIAR TODO A COTIZACIÓN"):
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Producción {impresora_sel}",
                    'costo_base': total_usd_lote,
                    'c_ml': totales_canales['c'],
                    'm_ml': totales_canales['m'],
                    'y_ml': totales_canales['y'],
                    'k_ml': totales_canales['k'],
                    'unidades': total_paginas_lote
                }
                st.toast("Datos listos para cotizar")


# --- ACTIVOS ---
elif menu == "🏗️ Activos":

    if ROL != "Admin":
        st.error("Acceso Denegado")
        st.stop()

    st.title("🏗️ Gestión de Activos")

    with st.expander("➕ Registrar Nuevo Equipo"):

        c1, c2 = st.columns(2)
        nombre_eq = c1.text_input("Nombre del Equipo")
        categoria = c2.selectbox("Categoría", [
            "Impresora (Gasta Tinta)",
            "Maquinaria (Solo Desgaste)",
            "Herramienta Manual"
        ])

        monto = st.number_input("Monto Pagado", min_value=0.0)

        vida_util = st.number_input("Vida Útil", min_value=1, value=5000)

        if st.button("Guardar Equipo"):
            desgaste_u = monto / vida_util
            conn = conectar()
            c = conn.cursor()

            c.execute(
                "INSERT INTO activos (equipo, categoria, inversion, unidad, desgaste) VALUES (?,?,?,?,?)",
                (nombre_eq, categoria, monto, "uso", desgaste_u)
            )

            conn.commit()
            conn.close()

            st.success("Equipo guardado")
            st.rerun()


# --- OTROS PROCESOS ---
elif menu == "🛠️ Otros Procesos":
    st.title("🛠️ Calculadora de Procesos Especiales")

    conn = conectar()
    df_act_db = pd.read_sql_query("SELECT equipo, categoria, unidad, desgaste FROM activos", conn)
    conn.close()

    otros_equipos = df_act_db[df_act_db['categoria'] != "Impresora (Gasta Tinta)"].to_dict('records')

    if otros_equipos:
        nombres_eq = [e['equipo'] for e in otros_equipos]
        eq_sel = st.selectbox("Equipo:", nombres_eq)

        datos_eq = next(e for e in otros_equipos if e['equipo'] == eq_sel)

        cantidad = st.number_input("Cantidad de usos:", min_value=1, value=1)

        if st.button("Calcular"):
            costo = datos_eq['desgaste'] * cantidad
            st.metric("Costo Total", f"$ {costo:.2f}")


# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("Registro de Ventas")

    with st.form("venta"):
        cliente = st.selectbox("Cliente", st.session_state.df_cli['nombre'])
        monto = st.number_input("Monto", min_value=0.0)

        if st.form_submit_button("Guardar"):
            conn = conectar()
            conn.execute("INSERT INTO ventas (cliente_id, monto_total) VALUES ((SELECT id FROM clientes WHERE nombre=?),?)", (cliente, monto))
            conn.commit()
            conn.close()

            st.success("Venta registrada")


# --- GASTOS ---
elif menu == "📉 Gastos":
    st.title("Registro de Gastos")

    with st.form("gasto"):
        desc = st.text_input("Descripción")
        monto = st.number_input("Monto", min_value=0.0)

        if st.form_submit_button("Guardar"):
            conn = conectar()
            conn.execute("INSERT INTO gastos (descripcion, monto) VALUES (?,?)", (desc, monto))
            conn.commit()
            conn.close()

            st.success("Gasto registrado")


# --- CIERRE DE CAJA ---
elif menu == "🏁 Cierre de Caja":
    st.title("Cierre de Caja del Día")

    conn = conectar()
    v = pd.read_sql("SELECT * FROM ventas", conn)
    g = pd.read_sql("SELECT * FROM gastos", conn)
    conn.close()

    total_v = v['monto_total'].sum() if not v.empty else 0
    total_g = g['monto'].sum() if not g.empty else 0

    st.metric("Ventas", f"$ {total_v:.2f}")
    st.metric("Gastos", f"$ {total_g:.2f}")
    st.metric("Balance", f"$ {(total_v-total_g):.2f}")



