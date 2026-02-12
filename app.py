import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import io
import plotly.express as px
from PIL import Image
from datetime import datetime, date, timedelta
import time

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide", page_icon="⚛️")

# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():
    """Conexión principal a la base de datos del Imperio."""
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)

# --- 3. INICIALIZACIÓN DEL SISTEMA ---
def inicializar_sistema():
    with conectar() as conn:
        c = conn.cursor()
        tablas = [
            "CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)",
            "CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)",
            "CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)",
            "CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)",
            "CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, cliente TEXT, detalle TEXT, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)"
        ]
        for tabla in tablas:
            c.execute(tabla)

        c.execute("INSERT OR IGNORE INTO usuarios VALUES ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio')")

        config_init = [
            ('tasa_bcv', 36.50), ('tasa_binance', 38.00), ('costo_tinta_ml', 0.10),
            ('iva_perc', 16.0), ('igtf_perc', 3.0), ('banco_perc', 0.5)
        ]
        for p, v in config_init:
            c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))
        conn.commit()

# --- 4. CARGA DE DATOS ---
def cargar_datos():
    with conectar() as conn:
        try:
            st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
            st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
            conf_df = pd.read_sql("SELECT * FROM configuracion", conn)
            for _, row in conf_df.iterrows():
                st.session_state[row['parametro']] = float(row['valor'])
        except:
            pass

# Alias de compatibilidad para módulos que lo usan
def cargar_datos_seguros():
    cargar_datos()

# --- 5. LOGICA DE ACCESO ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    inicializar_sistema()

def login():
    st.title("⚛️ Acceso al Imperio Atómico")
    with st.container(border=True):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar", use_container_width=True):
            with conectar() as conn:
                res = conn.execute(
                    "SELECT rol, nombre FROM usuarios WHERE username=? AND password=?",
                    (u, p)
                ).fetchone()
            if res:
                st.session_state.autenticado = True
                st.session_state.rol = res[0]
                st.session_state.usuario_nombre = res[1]
                cargar_datos()
                st.rerun()
            else:
                st.error("Acceso denegado")

if not st.session_state.autenticado:
    login()
    st.stop()

# --- 6. SIDEBAR Y VARIABLES ---
cargar_datos()
t_bcv = st.session_state.get('tasa_bcv', 1.0)
t_bin = st.session_state.get('tasa_binance', 1.0)
ROL = st.session_state.get('rol', "Produccion")

with st.sidebar:
    st.header(f"👋 {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 Bin: {t_bin}")

    menu = st.radio(
        "Secciones:",
        [
            "📊 Dashboard",
            "🛒 Venta Directa",
            "📦 Inventario",
            "👥 Clientes",
            "🎨 Análisis CMYK",
            "🏗️ Activos",
            "🛠️ Otros Procesos",
            "💰 Ventas",
            "📉 Gastos",
            "🏁 Cierre de Caja",
            "📊 Auditoría y Métricas",
            "📝 Cotizaciones",
            "⚙️ Configuración"
        ]
    )

    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

        
# --- MÓDULO DE INVENTARIO REINGENIERIZADO Y PROFESIONAL ---
if menu == "📦 Inventario":
    st.title("📦 Centro de Control de Suministros")

    # Sincronización con sesión
    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    t_ref = st.session_state.get('tasa_bcv', 36.5)
    t_bin = st.session_state.get('tasa_binance', 38.0)
    usuario = st.session_state.get('usuario_nombre', 'Sistema')

    # --- DASHBOARD DE INDICADORES ---
    if not df_inv.empty:
        with st.container(border=True):
            c_val, c_alert, c_salud = st.columns(3)

            v_inv = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
            c_val.metric(
                "Capital en Stock",
                f"$ {v_inv:,.2f}",
                help=f"Bs {v_inv * t_ref:,.2f}"
            )

            crit_df = df_inv[df_inv['cantidad'] <= df_inv['minimo']]
            c_alert.metric(
                "Items Críticos",
                f"{len(crit_df)}",
                delta=f"{len(crit_df)} Reabastecer" if len(crit_df) > 0 else "OK",
                delta_color="inverse"
            )

            salud = ((len(df_inv) - len(crit_df)) / len(df_inv)) * 100 if len(df_inv) > 0 else 0
            c_salud.write(f"**Salud del Almacén: {salud:.0f}%**")
            c_salud.progress(salud / 100)

    # --- TABS PRINCIPALES ---
    tabs = st.tabs([
        "📋 Existencias",
        "📥 Registrar Compra",
        "🧮 Calculadora",
        "🔧 Ajustes",
        "📊 Análisis"
    ])

    # ========================================================
    # TAB 1 – EXISTENCIAS
    # ========================================================
    with tabs[0]:
        if not df_inv.empty:
            c1, c2, c3 = st.columns([2, 1, 1])

            busq = c1.text_input("🔍 Filtro rápido", placeholder="Buscar por nombre...", key="f_busq")
            moneda_v = c2.selectbox("Mostrar en:", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], key="f_mon")

            t_v = t_ref if "BCV" in moneda_v else (t_bin if "Binance" in moneda_v else 1.0)
            simbolo = "$" if "USD" in moneda_v else "Bs"

            df_v = df_inv.copy()

            if busq:
                df_v = df_v[df_v['item'].str.contains(busq, case=False)]

            if c3.checkbox("🚨 Ver solo stock bajo"):
                df_v = df_v[df_v['cantidad'] <= df_v['minimo']]

            df_v['Costo Unit.'] = df_v['precio_usd'] * t_v
            df_v['Total'] = df_v['cantidad'] * df_v['Costo Unit.']

            st.dataframe(
                df_v,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Inventario vacío.")

    # ========================================================
    # TAB 2 – REGISTRO DE COMPRA
    # ========================================================
    with tabs[1]:
        st.subheader("📥 Entrada de Mercancía")

        with st.form("form_compra_atoma", clear_on_submit=True):

            f1, f2, f3 = st.columns(3)

            nombre_c = f1.text_input("Nombre del Material").strip().upper()
            monto_neto = f2.number_input("Monto Factura", min_value=0.0)
            cant_recibida = f3.number_input("Cantidad Comprada", min_value=0.001)

            if st.form_submit_button("💾 GUARDAR COMPRA EN INVENTARIO"):

                if not nombre_c:
                    st.error("Debe colocar un nombre de material válido.")
                    st.stop()

                if cant_recibida <= 0:
                    st.error("Cantidad inválida.")
                    st.stop()

                with conectar() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT INTO inventario (item, cantidad, unidad, precio_usd)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(item) DO UPDATE SET
                        cantidad = cantidad + ?
                    """, (
                        nombre_c,
                        cant_recibida,
                        "Unidad",
                        monto_neto,
                        cant_recibida
                    ))

                    conn.commit()

                cargar_datos_seguros()
                st.success("Compra registrada.")
                st.rerun()

    # ========================================================
    # TAB 3 – CALCULADORA
    # ========================================================
    with tabs[2]:
        st.subheader("🧮 Calculadora de Costos por Trabajo")

        if 'calc_list' not in st.session_state:
            st.session_state.calc_list = []

        if not df_inv.empty:

            item_sel = st.selectbox("Seleccionar Insumo", df_inv['item'].tolist(), key="sel_calc")

            datos_i = df_inv[df_inv['item'] == item_sel].iloc[0]

            uso_f = st.number_input(f"Cantidad a usar ({datos_i['unidad']})", min_value=0.0)

            if st.button("➕ Agregar al Cálculo"):
                costo_c = uso_f * datos_i['precio_usd']
                st.session_state.calc_list.append({
                    "Item": item_sel,
                    "Uso": uso_f,
                    "Costo $": round(costo_c, 4)
                })

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

    # ========================================================
    # TAB 4 – AJUSTES
    # ========================================================
    with tabs[3]:
        st.subheader("🔧 Corrección Manual")

        if not df_inv.empty:
            with st.form("form_ajuste"):

                it_aj = st.selectbox("Seleccionar Insumo", df_inv['item'].tolist())

                val_actual = df_inv[df_inv['item'] == it_aj].iloc[0]

                cant_r = st.number_input("Cantidad Real", value=float(val_actual['cantidad']))

                if st.form_submit_button("🔨 ACTUALIZAR DATOS"):

                    with conectar() as conn:
                        conn.execute(
                            "UPDATE inventario SET cantidad=? WHERE item=?",
                            (cant_r, it_aj)
                        )
                        conn.commit()

                    cargar_datos()
                    st.success("Ajuste aplicado.")
                    st.rerun()

    # ========================================================
    # TAB 5 – ANÁLISIS  (CORREGIDO)
    # ========================================================
    with tabs[4]:
        st.subheader("📊 Reporte de Almacén")

        if not df_inv.empty:

            df_inv['Capital USD'] = df_inv['cantidad'] * df_inv['precio_usd']

            fig = px.pie(
                df_inv,
                values='Capital USD',
                names='item',
                title="Distribución de Valor en Inventario",
                hole=0.4
            )

            st.plotly_chart(fig, use_container_width=True)

            buffer = io.BytesIO()

            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_inv.to_excel(writer, index=False, sheet_name='Inventario')

            st.download_button(
                label="📥 Descargar Reporte Completo (Excel)",
                data=buffer.getvalue(),
                file_name="inventario_atoma.xlsx"
            )

        else:
            st.info("No hay datos para análisis.")

# ----- FIN DEL MÓDULO DE INVENTARIO -----

elif menu == "📊 Dashboard":

    st.title("📊 Panel de Control Imperio")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:
            df_ventas = pd.read_sql("SELECT * FROM ventas", conn, parse_dates=['fecha'])
            df_gastos = pd.read_sql("SELECT * FROM gastos", conn, parse_dates=['fecha'])
            df_inv = pd.read_sql("SELECT * FROM inventario", conn)

    except Exception as e:
        st.error(f"Error al cargar datos del dashboard: {e}")
        st.stop()

    # --- ALERTAS CRÍTICAS DE INVENTARIO ---
    items_criticos = df_inv[df_inv['cantidad'] <= df_inv['minimo']] if not df_inv.empty else pd.DataFrame()

    if not items_criticos.empty:
        with st.container(border=True):
            st.error(f"⚠️ **ATENCIÓN:** Tienes {len(items_criticos)} productos en nivel crítico.")

            cols = st.columns(min(len(items_criticos), 3))
            for i, (_, row) in enumerate(items_criticos.head(3).iterrows()):
                cols[i % 3].warning(
                    f"**{row['item']}**\n\nQuedan: {row['cantidad']} {row['unidad']}"
                )

    st.divider()

    # --- CÁLCULO DE MÉTRICAS PRINCIPALES ---
    ingresos = df_ventas['monto_total'].sum() if not df_ventas.empty else 0
    egresos = df_gastos['monto'].sum() if not df_gastos.empty else 0

    flujo_caja = ingresos - egresos

    deudas_pendientes = 0
    if not df_ventas.empty and 'metodo' in df_ventas.columns:
        deudas_pendientes = df_ventas[
            df_ventas['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)
        ]['monto_total'].sum()

    margen = (flujo_caja / ingresos * 100) if ingresos > 0 else 0

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Ingresos Totales", f"$ {ingresos:,.2f}")
    c2.metric("Egresos Totales", f"$ {egresos:,.2f}", delta=f"-{egresos:,.2f}", delta_color="inverse")
    c3.metric("Flujo de Caja", f"$ {flujo_caja:,.2f}", delta=f"{margen:.1f}% Margen")
    c4.metric("Por Cobrar (Deudas)", f"$ {deudas_pendientes:,.2f}", delta="Pendiente", delta_color="off")

    st.divider()

    # --- GRÁFICOS PRINCIPALES ---
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

        if not df_ventas.empty and 'metodo' in df_ventas.columns:
            metodos = df_ventas.groupby('metodo')['monto_total'].sum()
            st.bar_chart(metodos)
        else:
            st.info("Sin datos de métodos de pago.")

    st.divider()

    # --- ANÁLISIS FINANCIERO ADICIONAL ---
    with st.expander("📅 Análisis Mensual de Ingresos vs Gastos"):

        if not df_ventas.empty:
            df_ventas['mes'] = df_ventas['fecha'].dt.to_period('M').astype(str)
            ventas_mes = df_ventas.groupby('mes')['monto_total'].sum()
        else:
            ventas_mes = pd.Series(dtype=float)

        if not df_gastos.empty:
            df_gastos['mes'] = df_gastos['fecha'].dt.to_period('M').astype(str)
            gastos_mes = df_gastos.groupby('mes')['monto'].sum()
        else:
            gastos_mes = pd.Series(dtype=float)

        df_mes = pd.DataFrame({
            "Ingresos": ventas_mes,
            "Gastos": gastos_mes
        }).fillna(0)

        if not df_mes.empty:
            st.bar_chart(df_mes)
        else:
            st.info("Aún no hay suficientes datos para análisis mensual.")

    # --- DESGLOSE DE IMPUESTOS Y COMISIONES ---
    with st.expander("🏦 Desglose de Impuestos y Comisiones Estimados"):

        banco_perc = st.session_state.get('banco_perc', 0.5)
        iva_perc = st.session_state.get('iva_perc', 16)

        comision_banco = ingresos * (banco_perc / 100)
        iva_estimado = ingresos * (iva_perc / 100)

        i1, i2 = st.columns(2)

        i1.write(f"🔹 **Comisión Bancaria ({banco_perc}%):** ${comision_banco:,.2f}")
        i2.write(f"🔹 **IVA Estimado ({iva_perc}%):** ${iva_estimado:,.2f}")

        st.caption("Estos valores son referenciales basados en ingresos brutos.")

    # --- ÚLTIMOS MOVIMIENTOS ---
    st.divider()
    st.subheader("📑 Últimos Movimientos")

    tab_v, tab_g, tab_d = st.tabs([
        "Últimas Ventas",
        "Últimos Gastos",
        "🛑 Deudas por Cobrar"
    ])

    with tab_v:
        if not df_ventas.empty:
            st.dataframe(
                df_ventas.sort_values('fecha', ascending=False).head(10),
                use_container_width=True
            )
        else:
            st.info("Sin ventas registradas.")

    with tab_g:
        if not df_gastos.empty:
            st.dataframe(
                df_gastos.sort_values('fecha', ascending=False).head(10),
                use_container_width=True
            )
        else:
            st.info("Sin gastos registrados.")

    with tab_d:
        if not df_ventas.empty and 'metodo' in df_ventas.columns:

            deudores = df_ventas[
                df_ventas['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)
            ]

            if not deudores.empty and {'cliente', 'detalle', 'monto_total'}.issubset(deudores.columns):
                st.dataframe(
                    deudores[['fecha', 'cliente', 'detalle', 'monto_total']],
                    use_container_width=True
                )
            else:
                st.success("No hay deudas pendientes actualmente.")
        else:
            st.info("No hay información de deudas disponible.")


elif menu == "⚙️ Configuración":

    # --- SEGURIDAD DE ACCESO ---
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden cambiar tasas y costos.")
        st.stop()

    st.title("⚙️ Configuración del Sistema")
    st.info("💡 Estos valores afectan globalmente a cotizaciones, inventario y reportes financieros.")

    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    # --- CARGA SEGURA DE CONFIGURACIÓN ---
    try:
        with conectar() as conn:
            conf_df = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')
    except Exception as e:
        st.error(f"Error al cargar configuración: {e}")
        st.stop()

    # Función auxiliar para obtener valores seguros
    def get_conf(key, default):
        try:
            return float(conf_df.loc[key, 'valor'])
        except Exception:
            return default

    with st.form("config_general"):

        st.subheader("💵 Tasas de Cambio (Actualización Diaria)")
        c1, c2 = st.columns(2)

        nueva_bcv = c1.number_input(
            "Tasa BCV (Bs/$)",
            value=get_conf('tasa_bcv', 36.5),
            format="%.2f",
            help="Usada para pagos en bolívares de cuentas nacionales."
        )

        nueva_bin = c2.number_input(
            "Tasa Binance (Bs/$)",
            value=get_conf('tasa_binance', 38.0),
            format="%.2f",
            help="Usada para pagos mediante USDT o mercado paralelo."
        )

        st.divider()

        st.subheader("🎨 Costos Operativos Base")

        costo_tinta = st.number_input(
            "Costo de Tinta por ml ($)",
            value=get_conf('costo_tinta_ml', 0.10),
            format="%.4f",
            step=0.0001
        )

        st.divider()

        st.subheader("🛡️ Impuestos y Comisiones")
        st.caption("Define los porcentajes numéricos (Ej: 16 para 16%)")

        c3, c4, c5 = st.columns(3)

        n_iva = c3.number_input(
            "IVA (%)",
            value=get_conf('iva_perc', 16.0),
            format="%.2f"
        )

        n_igtf = c4.number_input(
            "IGTF (%)",
            value=get_conf('igtf_perc', 3.0),
            format="%.2f"
        )

        n_banco = c5.number_input(
            "Comisión Bancaria (%)",
            value=get_conf('banco_perc', 0.5),
            format="%.3f"
        )

        st.divider()

        # --- GUARDADO CON HISTORIAL ---
        if st.form_submit_button("💾 GUARDAR CAMBIOS ATÓMICOS", use_container_width=True):

            actualizaciones = [
                ('tasa_bcv', nueva_bcv),
                ('tasa_binance', nueva_bin),
                ('costo_tinta_ml', costo_tinta),
                ('iva_perc', n_iva),
                ('igtf_perc', n_igtf),
                ('banco_perc', n_banco)
            ]

            try:
                with conectar() as conn:
                    cur = conn.cursor()

                    # Crear tabla de historial si no existe
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS historial_config (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            parametro TEXT,
                            valor_anterior REAL,
                            valor_nuevo REAL,
                            usuario TEXT,
                            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Guardar cambios y registrar historial
                    for param, val in actualizaciones:

                        try:
                            val_anterior = float(conf_df.loc[param, 'valor'])
                        except Exception:
                            val_anterior = None

                        cur.execute(
                            "UPDATE configuracion SET valor = ? WHERE parametro = ?",
                            (val, param)
                        )

                        if val_anterior != val:
                            cur.execute("""
                                INSERT INTO historial_config
                                (parametro, valor_anterior, valor_nuevo, usuario)
                                VALUES (?,?,?,?)
                            """, (param, val_anterior, val, usuario_actual))

                    conn.commit()

                # Actualización inmediata en memoria
                st.session_state.tasa_bcv = nueva_bcv
                st.session_state.tasa_binance = nueva_bin
                st.session_state.costo_tinta_ml = costo_tinta
                st.session_state.iva_perc = n_iva
                st.session_state.igtf_perc = n_igtf
                st.session_state.banco_perc = n_banco

                st.success("✅ ¡Configuración actualizada y registrada en historial!")
                st.balloons()
                st.rerun()

            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    # --- VISUALIZAR HISTORIAL DE CAMBIOS ---
    with st.expander("📜 Ver Historial de Cambios"):

        try:
            with conectar() as conn:
                df_hist = pd.read_sql("""
                    SELECT fecha, parametro, valor_anterior, valor_nuevo, usuario
                    FROM historial_config
                    ORDER BY fecha DESC
                    LIMIT 50
                """, conn)

            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("Aún no hay cambios registrados.")

        except Exception:
            st.info("Historial aún no disponible.")


# --- 8. MÓDULO PROFESIONAL DE CLIENTES (VERSIÓN 2.0 MEJORADA) ---
elif menu == "👥 Clientes":

    st.title("👥 Gestión Integral de Clientes")
    st.caption("Directorio inteligente con análisis comercial y control de deudas")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:
            df_clientes = pd.read_sql("SELECT * FROM clientes", conn)
            df_ventas = pd.read_sql("SELECT cliente_id, cliente, monto_total, metodo FROM ventas", conn)
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        st.stop()

    # --- BUSCADOR AVANZADO ---
    col_b1, col_b2 = st.columns([3, 1])

    busqueda = col_b1.text_input(
        "🔍 Buscar cliente (nombre o teléfono)...",
        placeholder="Escribe nombre, apellido o número..."
    )

    filtro_deudores = col_b2.checkbox("Solo con deudas")

    # --- FORMULARIO DE REGISTRO Y EDICIÓN ---
    with st.expander("➕ Registrar / Editar Cliente"):

        modo = st.radio("Acción:", ["Registrar Nuevo", "Editar Existente"], horizontal=True)

        if modo == "Registrar Nuevo":

            with st.form("form_nuevo_cliente"):

                col1, col2 = st.columns(2)

                nombre_cli = col1.text_input("Nombre del Cliente o Negocio").strip()
                whatsapp_cli = col2.text_input("WhatsApp").strip()

                if st.form_submit_button("✅ Guardar Cliente"):

                    if not nombre_cli:
                        st.error("⚠️ El nombre es obligatorio.")
                        st.stop()

                    wa_limpio = "".join(filter(str.isdigit, whatsapp_cli))

                    if whatsapp_cli and len(wa_limpio) < 10:
                        st.error("⚠️ Número de WhatsApp inválido.")
                        st.stop()

                    try:
                        with conectar() as conn:

                            existe = conn.execute(
                                "SELECT COUNT(*) FROM clientes WHERE lower(nombre) = ?",
                                (nombre_cli.lower(),)
                            ).fetchone()[0]

                            if existe:
                                st.error("⚠️ Ya existe un cliente con ese nombre.")
                            else:
                                conn.execute(
                                    "INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)",
                                    (nombre_cli, wa_limpio)
                                )
                                conn.commit()

                                st.success(f"✅ Cliente '{nombre_cli}' registrado correctamente.")
                                cargar_datos()
                                st.rerun()

                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

        else:
            # --- EDICIÓN DE CLIENTE ---
            if df_clientes.empty:
                st.info("No hay clientes para editar.")
            else:
                cliente_sel = st.selectbox(
                    "Seleccionar Cliente:",
                    df_clientes['nombre'].tolist()
                )

                datos = df_clientes[df_clientes['nombre'] == cliente_sel].iloc[0]

                with st.form("form_editar_cliente"):

                    col1, col2 = st.columns(2)

                    nuevo_nombre = col1.text_input("Nombre", value=datos['nombre'])
                    nuevo_wa = col2.text_input("WhatsApp", value=datos['whatsapp'])

                    if st.form_submit_button("💾 Actualizar Cliente"):

                        wa_limpio = "".join(filter(str.isdigit, nuevo_wa))

                        try:
                            with conectar() as conn:
                                conn.execute("""
                                    UPDATE clientes
                                    SET nombre = ?, whatsapp = ?
                                    WHERE id = ?
                                """, (nuevo_nombre, wa_limpio, int(datos['id'])))

                                conn.commit()

                            st.success("✅ Cliente actualizado.")
                            cargar_datos()
                            st.rerun()

                        except Exception as e:
                            st.error(f"Error al actualizar: {e}")

    st.divider()

    # --- ANÁLISIS COMERCIAL ---
    if df_clientes.empty:
        st.info("No hay clientes para analizar.")
    else:
        st.write("Módulo de análisis comercial activo.")

    resumen = []

    for _, cli in df_clientes.iterrows():

        compras = df_ventas[df_ventas['cliente_id'] == cli['id']]

        total_comprado = compras['monto_total'].sum() if not compras.empty else 0

        deudas = compras[
            compras['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)
        ]['monto_total'].sum() if not compras.empty else 0

        resumen.append({
            "id": cli['id'],
            "nombre": cli['nombre'],
            "whatsapp": cli['whatsapp'],
            "total_comprado": total_comprado,
            "deudas": deudas,
            "operaciones": len(compras)
        })

    df_resumen = pd.DataFrame(resumen)

    # --- FILTROS ---
    if busqueda:
        df_resumen = df_resumen[
            df_resumen['nombre'].str.contains(busqueda, case=False, na=False) |
            df_resumen['whatsapp'].str.contains(busqueda, case=False, na=False)
        ]

    if filtro_deudores:
        df_resumen = df_resumen[df_resumen['deudas'] > 0]

    # --- DASHBOARD DE CLIENTES ---
    if not df_resumen.empty:

        st.subheader("📊 Resumen Comercial")

        m1, m2, m3 = st.columns(3)

        m1.metric("Clientes Totales", len(df_resumen))
        m2.metric("Ventas Totales", f"$ {df_resumen['total_comprado'].sum():,.2f}")
        m3.metric("Cuentas por Cobrar", f"$ {df_resumen['deudas'].sum():,.2f}")

        st.divider()

        st.subheader("🏆 Top Clientes")

        top = df_resumen.sort_values("total_comprado", ascending=False).head(5)

        st.dataframe(
            top[['nombre', 'total_comprado', 'operaciones']],
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader(f"📋 Directorio ({len(df_resumen)} clientes)")

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_resumen.to_excel(writer, index=False, sheet_name='Clientes')

        st.download_button(
            "📥 Descargar Lista de Clientes (Excel)",
            data=buffer.getvalue(),
            file_name="clientes_imperio.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # --- VISUALIZACIÓN DETALLADA ---
        for _, row in df_resumen.iterrows():

            with st.container(border=True):

                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])

                c1.write(f"**{row['nombre']}**")
                c2.write(f"📞 {row['whatsapp'] or 'Sin número'}")
                c3.write(f"💵 Compras: ${row['total_comprado']:.2f}")

                if row['deudas'] > 0:
                    c4.error(f"Debe: ${row['deudas']:.2f}")
                else:
                    c4.success("Al día")

                if row['whatsapp']:

                    wa_num = row['whatsapp']
                    if not wa_num.startswith('58'):
                        wa_num = '58' + wa_num.lstrip('0')

                    link_wa = f"https://wa.me/{wa_num}"
                    c5.link_button("💬 Chat", link_wa)

                with st.expander("⚙️ Acciones"):

                    if row['operaciones'] > 0:
                        st.warning("Este cliente tiene ventas registradas y no puede ser eliminado.")
                    else:
                        if st.button(f"🗑️ Eliminar {row['nombre']}", key=f"del_{row['id']}"):

                            try:
                                with conectar() as conn:
                                    conn.execute(
                                        "DELETE FROM clientes WHERE id = ?",
                                        (int(row['id']),)
                                    )
                                    conn.commit()

                                st.warning("Cliente eliminado.")
                                cargar_datos()
                                st.rerun()

                            except Exception as e:
                                st.error(f"No se pudo eliminar: {e}")

    else:
        st.info("No hay clientes que coincidan con los filtros.")




# ===========================================================
# 10. ANALIZADOR CMYK PROFESIONAL (VERSIÓN MEJORADA 2.0)
# ===========================================================
elif menu == "🎨 Análisis CMYK":

    st.title("🎨 Analizador Profesional de Cobertura CMYK")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:

            # Usamos el inventario como fuente de tintas
            df_tintas_db = pd.read_sql_query(
                "SELECT * FROM inventario", conn
            )

            # Tabla histórica
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial_cmyk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    impresora TEXT,
                    paginas INTEGER,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # --- LISTA DE IMPRESORAS DISPONIBLES ---
    impresoras_disponibles = [
        "Impresora Principal",
        "Impresora Secundaria"
    ]

    # Si hay equipos registrados en inventario que parezcan impresoras, los agregamos
    if not df_tintas_db.empty:
        posibles = df_tintas_db[
            df_tintas_db['item'].str.contains("impresora", case=False, na=False)
        ]['item'].tolist()

        for p in posibles:
            if p not in impresoras_disponibles:
                impresoras_disponibles.append(p)

    # --- VALIDACIÓN ---
    if not impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en el sistema.")
        st.stop()

    # --- SELECCIÓN DE IMPRESORA Y ARCHIVOS ---
    c_printer, c_file = st.columns([1, 2])

    with c_printer:

        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)

        costo_desgaste = 0.02  # costo base por página

        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)

        if not df_tintas_db.empty:
            mask = df_tintas_db['item'].str.contains("tinta", case=False, na=False)
            tintas = df_tintas_db[mask]

            if not tintas.empty:
                precio_tinta_ml = tintas['precio_usd'].mean()
                st.success(f"💧 Precio de tinta detectado: ${precio_tinta_ml:.4f}/ml")

        st.subheader("⚙️ Ajustes de Calibración")

        factor = st.slider(
            "Factor General de Consumo",
            1.0, 3.0, 1.5, 0.1,
            help="Ajuste global según rendimiento real de la impresora"
        )

        factor_k = st.slider(
            "Factor Especial para Negro (K)",
            0.5, 1.2, 0.8, 0.05,
            help="El negro suele rendir más que CMY"
        )

        refuerzo_negro = st.slider(
            "Refuerzo de Negro en Mezclas Oscuras",
            0.0, 0.2, 0.06, 0.01,
            help="Simula el uso real de K en grises y sombras"
        )

    with c_file:
        archivos_multiples = st.file_uploader(
            "Carga tus diseños",
            type=['pdf', 'png', 'jpg', 'jpeg'],
            accept_multiple_files=True
        )

    # --- PROCESAMIENTO ---
    if archivos_multiples:

        import fitz

        resultados = []
        totales_lote_cmyk = {'C': 0.0, 'M': 0.0, 'Y': 0.0, 'K': 0.0}
        total_pags = 0

        with st.spinner('🚀 Analizando cobertura real...'):

            for arc in archivos_multiples:

                try:
                    paginas_items = []
                    bytes_data = arc.read()

                    if arc.name.lower().endswith('.pdf'):

                        doc = fitz.open(stream=bytes_data, filetype="pdf")

                        for i in range(len(doc)):
                            page = doc.load_page(i)

                            pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)

                            img = Image.frombytes(
                                "CMYK",
                                [pix.width, pix.height],
                                pix.samples
                            )

                            paginas_items.append((f"{arc.name} (P{i+1})", img))

                        doc.close()

                    else:
                        img = Image.open(io.BytesIO(bytes_data)).convert('CMYK')
                        paginas_items.append((arc.name, img))

                    for nombre, img_obj in paginas_items:

                        total_pags += 1
                        arr = np.array(img_obj)

                        c_media, m_media, y_media, k_media = [
                            np.mean(arr[:, :, i]) / 255 for i in range(4)
                        ]

                        ml_c = c_media * 0.15 * factor
                        ml_m = m_media * 0.15 * factor
                        ml_y = y_media * 0.15 * factor

                        ml_k = k_media * 0.15 * factor * factor_k

                        promedio_color = (c_media + m_media + y_media) / 3

                        if promedio_color > 0.55:
                            refuerzo = promedio_color * refuerzo_negro * factor
                            ml_k += refuerzo

                        consumo_total_f = ml_c + ml_m + ml_y + ml_k

                        costo_f = (consumo_total_f * precio_tinta_ml) + costo_desgaste

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
                    st.error(f"Error analizando {arc.name}: {e}")

        # --- RESULTADOS ---
        if resultados:

            st.subheader("📋 Desglose por Archivo")
            st.dataframe(pd.DataFrame(resultados), use_container_width=True)

            st.subheader("🧪 Consumo Total de Tintas")

            col_c, col_m, col_y, col_k = st.columns(4)

            col_c.metric("Cian", f"{totales_lote_cmyk['C']:.3f} ml")
            col_m.metric("Magenta", f"{totales_lote_cmyk['M']:.3f} ml")
            col_y.metric("Amarillo", f"{totales_lote_cmyk['Y']:.3f} ml")
            col_k.metric("Negro", f"{totales_lote_cmyk['K']:.3f} ml")

            st.divider()

            total_usd_lote = sum(r['Costo $'] for r in resultados)

            st.metric(
                "💰 Costo Total Estimado de Producción",
                f"$ {total_usd_lote:.2f}"
            )

            # --- VERIFICAR INVENTARIO ---
            if not df_tintas_db.empty:

                st.subheader("📦 Verificación de Inventario")

                alertas = []

                for color, ml in totales_lote_cmyk.items():

                    stock = df_tintas_db[
                        df_tintas_db['item'].str.contains(color, case=False)
                    ]

                    if not stock.empty:
                        disponible = stock['cantidad'].sum()

                        if disponible < ml:
                            alertas.append(
                                f"⚠️ Falta tinta {color}: necesitas {ml:.2f} ml y hay {disponible:.2f} ml"
                            )

                if alertas:
                    for a in alertas:
                        st.error(a)
                else:
                    st.success("✅ Hay suficiente tinta para producir")


                       # --- ENVÍO A COTIZACIÓN ---
            if st.button("📝 ENVIAR A COTIZACIÓN", use_container_width=True):

                # Guardamos información completa para el cotizador
                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': f"Impresión {impresora_sel} ({total_pags} pgs)",
                    'costo_base': float(total_usd_lote),
                    'unidades': total_pags,

                    # Desglose de consumo real
                    'consumos': totales_lote_cmyk,

                    # Información técnica adicional
                    'impresora': impresora_sel,
                    'factor_consumo': factor,
                    'factor_negro': factor_k,
                    'refuerzo_negro': refuerzo_negro,
                    'precio_tinta_ml': precio_tinta_ml,
                    'costo_desgaste': costo_desgaste,

                    # Historial detallado por archivo
                    'detalle_archivos': resultados
                }

                try:
                    with conectar() as conn:
                        conn.execute("""
                            INSERT INTO historial_cmyk
                            (impresora, paginas, costo)
                            VALUES (?,?,?)
                        """, (impresora_sel, total_pags, total_usd_lote))
                        conn.commit()
                except Exception as e:
                    st.warning(f"No se pudo guardar en historial: {e}")

                st.success("✅ Datos enviados correctamente al módulo de Cotizaciones")
                st.toast("Listo para cotizar", icon="📨")

                st.rerun()


# --- 9. MÓDULO PROFESIONAL DE ACTIVOS ---
elif menu == "🏗️ Activos":

    if ROL != "Admin":
        st.error("🚫 Acceso Denegado. Solo Administración puede gestionar activos.")
        st.stop()

    st.title("🏗️ Gestión Integral de Activos")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:
            df = pd.read_sql_query("SELECT * FROM activos", conn)

            # Crear tabla de historial si no existe
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activos_historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activo TEXT,
                    accion TEXT,
                    detalle TEXT,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")
        st.stop()

    # --- REGISTRO DE NUEVO ACTIVO ---
    with st.expander("➕ Registrar Nuevo Activo"):

        with st.form("form_activos_pro"):

            c1, c2 = st.columns(2)

            nombre_eq = c1.text_input("Nombre del Activo")
            tipo_seccion = c2.selectbox("Tipo de Activo", [
                "Maquinaria (Equipos Grandes)",
                "Herramienta Manual (Uso diario)",
                "Repuesto Crítico (Stock de seguridad)"
            ])

            col_m1, col_m2, col_m3 = st.columns(3)

            monto_inv = col_m1.number_input("Inversión ($)", min_value=0.0)
            vida_util = col_m2.number_input("Vida Útil (Usos)", min_value=1, value=1000)

            categoria_especifica = col_m3.selectbox(
                "Categoría",
                ["Corte", "Impresión", "Calor", "Mobiliario", "Mantenimiento"]
            )

            if st.form_submit_button("🚀 Guardar Activo"):

                if not nombre_eq:
                    st.error("Debe indicar un nombre.")
                    st.stop()

                if monto_inv <= 0:
                    st.error("La inversión debe ser mayor a cero.")
                    st.stop()

                desgaste_u = monto_inv / vida_util

                try:
                    with conectar() as conn:
                        conn.execute("""
                            INSERT INTO activos 
                            (equipo, categoria, inversion, unidad, desgaste) 
                            VALUES (?,?,?,?,?)
                        """, (
                            f"[{tipo_seccion[:3].upper()}] {nombre_eq}",
                            categoria_especifica,
                            monto_inv,
                            tipo_seccion,
                            desgaste_u
                        ))

                        conn.execute("""
                            INSERT INTO activos_historial 
                            (activo, accion, detalle, costo)
                            VALUES (?,?,?,?)
                        """, (nombre_eq, "CREACIÓN", "Registro inicial", monto_inv))

                        conn.commit()

                    st.success("✅ Activo registrado correctamente.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al registrar: {e}")

    st.divider()

    # --- EDICIÓN DE ACTIVOS ---
    with st.expander("✏️ Editar Activo Existente"):

        if df.empty:
            st.info("No hay activos para editar.")
        else:
            activo_sel = st.selectbox("Seleccionar activo:", df['equipo'].tolist())

            datos = df[df['equipo'] == activo_sel].iloc[0]

            with st.form("editar_activo"):

                c1, c2, c3 = st.columns(3)

                nueva_inv = c1.number_input("Inversión ($)", value=float(datos['inversion']))
                nueva_vida = c2.number_input("Vida útil", value=1000)
                nueva_cat = c3.selectbox(
                    "Categoría",
                    ["Corte", "Impresión", "Calor", "Mobiliario", "Mantenimiento"],
                    index=0
                )

                if st.form_submit_button("💾 Guardar Cambios"):

                    nuevo_desgaste = nueva_inv / nueva_vida

                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE activos
                                SET inversion = ?, categoria = ?, desgaste = ?
                                WHERE id = ?
                            """, (nueva_inv, nueva_cat, nuevo_desgaste, int(datos['id'])))

                            conn.execute("""
                                INSERT INTO activos_historial 
                                (activo, accion, detalle, costo)
                                VALUES (?,?,?,?)
                            """, (activo_sel, "EDICIÓN", "Actualización de valores", nueva_inv))

                            conn.commit()

                        st.success("Activo actualizado.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error al actualizar: {e}")

    st.divider()

    # --- VISUALIZACIÓN POR SECCIONES ---
    t1, t2, t3, t4, t5 = st.tabs([
        "📟 Maquinaria",
        "🛠️ Herramientas",
        "🔄 Repuestos",
        "📊 Resumen Global",
        "📜 Historial"
    ])

    if not df.empty:

        with t1:
            st.subheader("Equipos y Maquinaria")
            df_maq = df[df['unidad'].str.contains("Maquinaria")]
            st.dataframe(df_maq, use_container_width=True, hide_index=True)

        with t2:
            st.subheader("Herramientas Manuales")
            df_her = df[df['unidad'].str.contains("Herramienta")]
            st.dataframe(df_her, use_container_width=True, hide_index=True)

        with t3:
            st.subheader("Repuestos Críticos")
            df_rep = df[df['unidad'].str.contains("Repuesto")]
            st.dataframe(df_rep, use_container_width=True, hide_index=True)

        with t4:
            c_inv, c_des, c_prom = st.columns(3)

            c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
            c_des.metric("Activos Registrados", len(df))

            promedio = df['desgaste'].mean() if not df.empty else 0
            c_prom.metric("Desgaste Promedio por Uso", f"$ {promedio:.4f}")

            fig = px.bar(
                df,
                x='equipo',
                y='inversion',
                color='categoria',
                title="Distribución de Inversión por Activo"
            )
            st.plotly_chart(fig, use_container_width=True)

        with t5:
            st.subheader("Historial de Movimientos de Activos")

            try:
                with conectar() as conn:
                    df_hist = pd.read_sql_query(
                        "SELECT activo, accion, detalle, costo, fecha FROM activos_historial ORDER BY fecha DESC",
                        conn
                    )

                if not df_hist.empty:
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay movimientos registrados aún.")

            except Exception as e:
                st.error(f"Error cargando historial: {e}")

    else:
        st.info("No hay activos registrados todavía.")


# ===========================================================
# 11. MÓDULO PROFESIONAL DE OTROS PROCESOS
# ===========================================================
elif menu == "🛠️ Otros Procesos":

    st.title("🛠️ Calculadora de Procesos Especiales")
    st.info("Cálculo de costos de procesos que no usan tinta: corte, laminado, planchado, etc.")

    # --- CARGA SEGURA DE EQUIPOS ---
    try:
        with conectar() as conn:
            df_act_db = pd.read_sql_query(
                "SELECT equipo, categoria, unidad, desgaste FROM activos", conn
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial_procesos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equipo TEXT,
                    cantidad REAL,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    except Exception as e:
        st.error(f"Error cargando activos: {e}")
        st.stop()

    # Filtrar solo equipos que NO gastan tinta
    otros_equipos = df_act_db[
        df_act_db['categoria'] != "Impresora (Gasta Tinta)"
    ].to_dict('records')

    if not otros_equipos:
        st.warning("⚠️ No hay equipos registrados para procesos especiales.")
        st.stop()

    nombres_eq = [e['equipo'] for e in otros_equipos]

    if "lista_procesos" not in st.session_state:
        st.session_state.lista_procesos = []

    with st.container(border=True):

        c1, c2 = st.columns(2)

        eq_sel = c1.selectbox("Selecciona el Proceso/Equipo:", nombres_eq)

        datos_eq = next(e for e in otros_equipos if e['equipo'] == eq_sel)

        cantidad = c2.number_input(
            f"Cantidad de {datos_eq['unidad']}:",
            min_value=1.0,
            value=1.0
        )

        # Conversión segura del desgaste
        costo_unitario = float(datos_eq.get('desgaste', 0.0))
        costo_total = costo_unitario * cantidad

        st.divider()

        r1, r2 = st.columns(2)
        r1.metric("Costo Unitario", f"$ {costo_unitario:.4f}")
        r2.metric("Costo Total", f"$ {costo_total:.2f}")

        if st.button("➕ Agregar Proceso"):
            st.session_state.lista_procesos.append({
                "equipo": eq_sel,
                "cantidad": cantidad,
                "costo": costo_total
            })
            st.toast("Proceso añadido")

    # --- RESUMEN DE PROCESOS EN SESIÓN ---
    if st.session_state.lista_procesos:

        st.subheader("📋 Procesos Acumulados")

        df_proc = pd.DataFrame(st.session_state.lista_procesos)
        st.dataframe(df_proc, use_container_width=True, hide_index=True)

        total = df_proc["costo"].sum()
        st.metric("Total Procesos", f"$ {total:.2f}")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📝 Enviar a Cotización", use_container_width=True):

                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': " + ".join(df_proc["equipo"].tolist()),
                    'costo_base': float(total),
                    'unidades': 1,
                    'es_proceso_extra': True
                }

                st.success("Enviado a cotización")
                st.session_state.lista_procesos = []
                st.rerun()

        with col2:
            if st.button("🧹 Limpiar", use_container_width=True):
                st.session_state.lista_procesos = []
                st.rerun()

    # --- HISTORIAL ---
    with st.expander("📜 Historial de Procesos"):

        try:
            with conectar() as conn:
                df_hist = pd.read_sql_query(
                    "SELECT * FROM historial_procesos ORDER BY fecha DESC",
                    conn
                )

            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("Sin registros aún.")

        except Exception as e:
            st.info("Historial no disponible.")


# ===========================================================
# 12. MÓDULO PROFESIONAL DE VENTAS (VERSIÓN 2.0)
# ===========================================================
elif menu == "💰 Ventas":

    st.title("💰 Gestión Profesional de Ventas")

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar Venta",
        "📜 Historial",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE VENTA
    # -----------------------------------
    with tab1:

        df_cli = st.session_state.get("df_cli", pd.DataFrame())

        if df_cli.empty:
            st.warning("⚠️ Registra clientes primero.")
            st.stop()

        with st.form("venta_manual", clear_on_submit=True):

            st.subheader("Datos de la Venta")

            opciones_cli = {
                row['nombre']: row['id']
                for _, row in df_cli.iterrows()
            }

            c1, c2 = st.columns(2)

            cliente_nombre = c1.selectbox(
                "Cliente:", list(opciones_cli.keys())
            )

            detalle_v = c2.text_input(
                "Detalle de lo vendido:",
                placeholder="Ej: 100 volantes, 2 banner..."
            )

            c3, c4, c5 = st.columns(3)

            monto_venta = c3.number_input(
                "Monto ($):",
                min_value=0.01,
                format="%.2f"
            )

            metodo_pago = c4.selectbox(
                "Método:",
                ["Efectivo ($)", "Pago Móvil (BCV)",
                 "Zelle", "Binance (USDT)",
                 "Transferencia (Bs)", "Pendiente"]
            )

            tasa_uso = t_bcv if "BCV" in metodo_pago else (
                t_bin if "Binance" in metodo_pago else 1.0
            )

            monto_bs = monto_venta * tasa_uso

            c5.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            if st.form_submit_button("🚀 Registrar Venta"):

                if not detalle_v.strip():
                    st.error("Debes indicar el detalle de la venta.")
                    st.stop()

                try:
                    with conectar() as conn:

                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS ventas_extra (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                venta_id INTEGER,
                                tasa REAL,
                                monto_bs REAL
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO ventas 
                            (cliente_id, cliente, detalle, monto_total, metodo)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            opciones_cli[cliente_nombre],
                            cliente_nombre,
                            detalle_v.strip(),
                            float(monto_venta),
                            metodo_pago
                        ))

                        venta_id = cur.lastrowid

                        cur.execute("""
                            INSERT INTO ventas_extra
                            (venta_id, tasa, monto_bs)
                            VALUES (?, ?, ?)
                        """, (
                            venta_id,
                            float(tasa_uso),
                            float(monto_bs)
                        ))

                        conn.commit()

                    st.success("Venta registrada correctamente")
                    st.balloons()
                    st.rerun()

                except Exception as e:
                    st.error(f"Error: {e}")

    # -----------------------------------
    # HISTORIAL
    # -----------------------------------
    with tab2:

        st.subheader("Historial de Ventas")

        try:
            with conectar() as conn:
                df_historial = pd.read_sql_query("""
                    SELECT 
                        v.id,
                        v.fecha,
                        v.cliente,
                        v.detalle,
                        v.monto_total as total,
                        v.metodo,
                        e.tasa,
                        e.monto_bs
                    FROM ventas v
                    LEFT JOIN ventas_extra e ON v.id = e.venta_id
                    ORDER BY v.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_historial.empty:
            st.info("No hay ventas aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", date.today() - timedelta(days=30))
        hasta = c2.date_input("Hasta", date.today())

        df_historial['fecha'] = pd.to_datetime(df_historial['fecha'], errors='coerce')

        df_fil = df_historial[
            (df_historial['fecha'].dt.date >= desde) &
            (df_historial['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por cliente o detalle:")

        if busc:
            df_fil = df_fil[
                df_fil['cliente'].str.contains(busc, case=False, na=False) |
                df_fil['detalle'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del periodo", f"$ {df_fil['total'].sum():.2f}")

        # --- GESTIÓN DE PENDIENTES ---
        st.subheader("Gestión de Cuentas Pendientes")

        pendientes = df_fil[df_fil['metodo'] == "Pendiente"]

        for _, row in pendientes.iterrows():

            with st.container(border=True):

                st.write(f"**{row['cliente']}** – ${row['total']:.2f}")

                if st.button(f"Marcar como pagada #{row['id']}"):

                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE ventas
                                SET metodo = 'Pagado'
                                WHERE id = ?
                            """, (int(row['id']),))
                            conn.commit()

                        st.success("Actualizado")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fil.to_excel(writer, index=False, sheet_name='Ventas')

        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "historial_ventas.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    with tab3:

        st.subheader("Resumen Comercial")

        try:
            with conectar() as conn:
                df_v = pd.read_sql("SELECT * FROM ventas", conn)
        except:
            st.info("Sin datos")
            st.stop()

        if df_v.empty:
            st.info("No hay ventas registradas.")
            st.stop()

        total = df_v['monto_total'].sum()

        c1, c2, c3 = st.columns(3)

        c1.metric("Ventas Totales", f"$ {total:.2f}")

        pendientes = df_v[
            df_v['metodo'].str.contains("Pendiente", case=False, na=False)
        ]['monto_total'].sum()

        c2.metric("Por Cobrar", f"$ {pendientes:.2f}")

        top = df_v.groupby('cliente')['monto_total'].sum().reset_index()

        mejor = top.sort_values("monto_total", ascending=False).head(1)

        if not mejor.empty:
            c3.metric("Mejor Cliente", mejor.iloc[0]['cliente'])

        st.subheader("Ventas por Cliente")
        st.bar_chart(top.set_index("cliente"))


# ===========================================================
# 12. MÓDULO PROFESIONAL DE GASTOS (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "📉 Gastos":

    st.title("📉 Control Integral de Gastos")
    st.info("Registro, análisis y control de egresos del negocio")

    # Solo administración puede registrar gastos
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede gestionar gastos.")
        st.stop()

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar Gasto",
        "📜 Historial",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE GASTOS
    # -----------------------------------
    with tab1:

        with st.form("form_gastos_pro", clear_on_submit=True):

            col_d, col_c = st.columns([2, 1])

            desc = col_d.text_input(
                "Descripción del Gasto",
                placeholder="Ej: Pago de luz, resma de papel, repuesto..."
            ).strip()

            categoria = col_c.selectbox("Categoría:", [
                "Materia Prima",
                "Mantenimiento de Equipos",
                "Servicios (Luz/Internet)",
                "Publicidad",
                "Sueldos/Retiros",
                "Logística",
                "Otros"
            ])

            c1, c2, c3 = st.columns(3)

            monto_gasto = c1.number_input(
                "Monto en Dólares ($):",
                min_value=0.01,
                format="%.2f"
            )

            metodo_pago = c2.selectbox("Método de Pago:", [
                "Efectivo ($)",
                "Pago Móvil (BCV)",
                "Zelle",
                "Binance (USDT)",
                "Transferencia (Bs)"
            ])

            tasa_ref = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (
                t_bin if "Binance" in metodo_pago else 1.0
            )

            monto_bs = monto_gasto * tasa_ref

            c3.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            st.divider()

            if st.form_submit_button("📉 REGISTRAR EGRESO"):

                if not desc:
                    st.error("⚠️ La descripción es obligatoria.")
                    st.stop()

                try:
                    with conectar() as conn:

                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS gastos_extra (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                gasto_id INTEGER,
                                tasa REAL,
                                monto_bs REAL,
                                usuario TEXT
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO gastos 
                            (descripcion, monto, categoria, metodo) 
                            VALUES (?, ?, ?, ?)
                        """, (desc, float(monto_gasto), categoria, metodo_pago))

                        gasto_id = cur.lastrowid

                        cur.execute("""
                            INSERT INTO gastos_extra
                            (gasto_id, tasa, monto_bs, usuario)
                            VALUES (?, ?, ?, ?)
                        """, (
                            gasto_id,
                            float(tasa_ref),
                            float(monto_bs),
                            st.session_state.get("usuario_nombre", "Sistema")
                        ))

                        conn.commit()

                    st.success("📉 Gasto registrado correctamente.")
                    st.balloons()
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Error al guardar el gasto: {e}")

    # -----------------------------------
    # HISTORIAL DE GASTOS
    # -----------------------------------
    with tab2:

        st.subheader("📋 Historial de Gastos")

        try:
            with conectar() as conn:
                df_g = pd.read_sql_query("""
                    SELECT 
                        g.id,
                        g.fecha,
                        g.descripcion,
                        g.categoria,
                        g.monto,
                        g.metodo,
                        e.tasa,
                        e.monto_bs,
                        e.usuario
                    FROM gastos g
                    LEFT JOIN gastos_extra e ON g.id = e.gasto_id
                    ORDER BY g.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_g.empty:
            st.info("No hay gastos registrados aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", date.today() - timedelta(days=30))
        hasta = c2.date_input("Hasta", date.today())

        df_g['fecha'] = pd.to_datetime(df_g['fecha'], errors='coerce')

        df_fil = df_g[
            (df_g['fecha'].dt.date >= desde) &
            (df_g['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por descripción:")

        if busc:
            df_fil = df_fil[
                df_fil['descripcion'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del Periodo", f"$ {df_fil['monto'].sum():.2f}")

        # --- EDICIÓN Y ELIMINACIÓN ---
        st.subheader("Gestión de Gastos")

        gasto_sel = st.selectbox(
            "Seleccionar gasto para editar/eliminar:",
            df_fil['descripcion'].tolist()
        )

        datos = df_fil[df_fil['descripcion'] == gasto_sel].iloc[0]

        with st.expander("✏️ Editar Gasto"):

            nuevo_monto = st.number_input(
                "Monto $",
                value=float(datos['monto']),
                format="%.2f"
            )

            if st.button("💾 Guardar Cambios"):

                try:
                    with conectar() as conn:
                        conn.execute("""
                            UPDATE gastos
                            SET monto = ?
                            WHERE id = ?
                        """, (float(nuevo_monto), int(datos['id'])))
                        conn.commit()

                    st.success("Actualizado correctamente")
                    st.rerun()

                except Exception as e:
                    st.error(str(e))

        with st.expander("🗑️ Eliminar Gasto"):

            confirmar = st.checkbox("Confirmo que deseo eliminar este gasto")

            if st.button("Eliminar definitivamente"):

                if not confirmar:
                    st.warning("Debes confirmar para eliminar")
                else:
                    try:
                        with conectar() as conn:
                            conn.execute(
                                "DELETE FROM gastos WHERE id = ?",
                                (int(datos['id']),)
                            )
                            conn.commit()

                        st.warning("Gasto eliminado")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fil.to_excel(writer, index=False, sheet_name='Gastos')

        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "historial_gastos.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    with tab3:

        st.subheader("📊 Resumen de Egresos")

        try:
            with conectar() as conn:
                df = pd.read_sql("SELECT * FROM gastos", conn)
        except:
            st.info("Sin datos")
            st.stop()

        if df.empty:
            st.info("No hay gastos para analizar.")
            st.stop()

        total = df['monto'].sum()

        c1, c2 = st.columns(2)

        c1.metric("Total Gastado", f"$ {total:.2f}")

        por_cat = df.groupby('categoria')['monto'].sum()

        categoria_top = por_cat.idxmax() if not por_cat.empty else "N/A"

        c2.metric("Categoría Principal", categoria_top)

        st.subheader("Gastos por Categoría")
        st.bar_chart(por_cat)


# ===========================================================
# 13. MÓDULO PROFESIONAL DE CIERRE DE CAJA (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "🏁 Cierre de Caja":

    st.title("🏁 Cierre de Caja y Arqueo Diario")

    # --- SEGURIDAD ---
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede realizar cierres.")
        st.stop()

    # Selección de fecha
    fecha_cierre = st.date_input("Seleccionar fecha:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    try:
        with conectar() as conn:

            # Asegurar tabla de cierres
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cierres_caja (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT UNIQUE,
                    ingresos REAL,
                    egresos REAL,
                    neto REAL,
                    usuario TEXT,
                    creado DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            df_v = pd.read_sql(
                "SELECT * FROM ventas WHERE date(fecha) = ?",
                conn,
                params=(fecha_str,)
            )

            df_g = pd.read_sql(
                "SELECT * FROM gastos WHERE date(fecha) = ?",
                conn,
                params=(fecha_str,)
            )

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # Asegurar que existan columnas esperadas
    if not df_v.empty and 'metodo' not in df_v.columns:
        df_v['metodo'] = ""

    # --- SEPARAR COBRADO Y PENDIENTE ---
    if not df_v.empty:
        cobradas = df_v[~df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
        pendientes = df_v[df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
    else:
        cobradas = pd.DataFrame(columns=df_v.columns)
        pendientes = pd.DataFrame(columns=df_v.columns)

    t_ventas_cobradas = float(cobradas['monto_total'].sum()) if not cobradas.empty else 0.0
    t_pendientes = float(pendientes['monto_total'].sum()) if not pendientes.empty else 0.0
    t_gastos = float(df_g['monto'].sum()) if not df_g.empty else 0.0

    balance_dia = t_ventas_cobradas - t_gastos

    # --- MÉTRICAS PRINCIPALES ---
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Ingresos Cobrados", f"$ {t_ventas_cobradas:,.2f}")
    c2.metric("Cuentas Pendientes", f"$ {t_pendientes:,.2f}")
    c3.metric("Egresos del Día", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c4.metric("Neto en Caja", f"$ {balance_dia:,.2f}")

    st.divider()

    # --- DESGLOSE POR MÉTODO ---
    col_v, col_g = st.columns(2)

    with col_v:
        st.subheader("💰 Ingresos por Método")

        if not cobradas.empty:
            resumen_v = cobradas.groupby('metodo')['monto_total'].sum()
            for metodo, monto in resumen_v.items():
                st.write(f"✅ **{metodo}:** ${float(monto):,.2f}")
        else:
            st.info("No hubo ingresos cobrados.")

    with col_g:
        st.subheader("💸 Egresos por Método")

        if not df_g.empty:
            resumen_g = df_g.groupby('metodo')['monto'].sum()
            for metodo, monto in resumen_g.items():
                st.write(f"❌ **{metodo}:** ${float(monto):,.2f}")
        else:
            st.info("No hubo gastos.")

    st.divider()

    # --- DETALLES ---
    with st.expander("📝 Ver detalle completo"):

        st.write("### Ventas Cobradas")
        if not cobradas.empty:
            st.dataframe(cobradas, use_container_width=True, hide_index=True)
        else:
            st.info("Sin ventas cobradas")

        st.write("### Ventas Pendientes")
        if not pendientes.empty:
            st.dataframe(pendientes, use_container_width=True, hide_index=True)
        else:
            st.info("Sin ventas pendientes")

        st.write("### Gastos")
        if not df_g.empty:
            st.dataframe(df_g, use_container_width=True, hide_index=True)
        else:
            st.info("Sin gastos registrados")

    # --- GUARDAR CIERRE ---
    if st.button("💾 Guardar Cierre del Día"):

        try:
            with conectar() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cierres_caja
                    (fecha, ingresos, egresos, neto, usuario)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    fecha_str,
                    float(t_ventas_cobradas),
                    float(t_gastos),
                    float(balance_dia),
                    st.session_state.get("usuario_nombre", "Sistema")
                ))
                conn.commit()

            st.success("✅ Cierre registrado correctamente")

        except Exception as e:
            st.error(f"Error guardando cierre: {e}")

    # --- HISTORIAL DE CIERRES ---
    st.divider()
    st.subheader("📜 Historial de Cierres")

    try:
        with conectar() as conn:
            df_cierres = pd.read_sql(
                "SELECT * FROM cierres_caja ORDER BY fecha DESC",
                conn
            )

        if not df_cierres.empty:
            st.dataframe(df_cierres, use_container_width=True)

            # Exportación
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_cierres.to_excel(writer, index=False, sheet_name='Cierres')

            st.download_button(
                "📥 Descargar Historial de Cierres",
                buffer.getvalue(),
                "cierres_caja.xlsx"
            )
        else:
            st.info("Aún no hay cierres guardados.")

    except Exception as e:
        st.info("No hay historial disponible.")



# ===========================================================
# 13. AUDITORÍA Y MÉTRICAS - VERSIÓN PROFESIONAL MEJORADA 2.1
# ===========================================================
elif menu == "📊 Auditoría y Métricas":

    st.title("📊 Auditoría Integral del Negocio")
    st.caption("Control total de insumos, producción y finanzas")

    try:
        with conectar() as conn:

            # Verificamos si existe la tabla de movimientos
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventario_movs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    tipo TEXT,
                    cantidad REAL,
                    motivo TEXT,
                    usuario TEXT,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            df_movs = pd.read_sql_query("""
                SELECT 
                    m.fecha,
                    i.item as Material,
                    m.tipo as Operacion,
                    m.cantidad as Cantidad,
                    i.unidad,
                    m.motivo
                FROM inventario_movs m
                JOIN inventario i ON m.item_id = i.id
                ORDER BY m.fecha DESC
            """, conn)

            df_ventas = pd.read_sql("SELECT * FROM ventas", conn)
            df_gastos = pd.read_sql("SELECT * FROM gastos", conn)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # Asegurar columnas necesarias
    if not df_ventas.empty and 'metodo' not in df_ventas.columns:
        df_ventas['metodo'] = ""

    tab1, tab2, tab3, tab4 = st.tabs([
        "💰 Finanzas",
        "📦 Insumos",
        "📈 Gráficos",
        "🚨 Alertas"
    ])

    # ---------------------------------------
    # TAB FINANZAS
    # ---------------------------------------
    with tab1:

        st.subheader("Resumen Financiero")

        total_ventas = float(df_ventas['monto_total'].sum()) if not df_ventas.empty else 0.0
        total_gastos = float(df_gastos['monto'].sum()) if not df_gastos.empty else 0.0

        # Solo comisiones en métodos bancarios
        if not df_ventas.empty:
            ventas_bancarias = df_ventas[
                df_ventas['metodo'].str.contains("Pago|Transferencia", case=False, na=False)
            ]
        else:
            ventas_bancarias = pd.DataFrame()

        banco_perc = st.session_state.get('banco_perc', 0.5)

        comision_est = float(ventas_bancarias['monto_total'].sum() * (banco_perc / 100)) if not ventas_bancarias.empty else 0.0

        deudas = float(
            df_ventas[
                df_ventas['metodo'].str.contains("Pendiente", case=False, na=False)
            ]['monto_total'].sum()
        ) if not df_ventas.empty else 0.0

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Ingresos", f"$ {total_ventas:,.2f}")
        c2.metric("Gastos", f"$ {total_gastos:,.2f}", delta_color="inverse")
        c3.metric("Comisiones Bancarias", f"$ {comision_est:,.2f}")
        c4.metric("Cuentas por Cobrar", f"$ {deudas:,.2f}")

        utilidad = total_ventas - total_gastos - comision_est

        st.metric("Utilidad Real Estimada", f"$ {utilidad:,.2f}")

    # ---------------------------------------
    # TAB INSUMOS
    # ---------------------------------------
    with tab2:

        st.subheader("Bitácora de Movimientos de Inventario")

        if df_movs.empty:
            st.info("Aún no hay movimientos registrados.")
        else:
            st.dataframe(df_movs, use_container_width=True)

            # Exportación
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_movs.to_excel(writer, index=False, sheet_name='Movimientos')

            st.download_button(
                "📥 Descargar Movimientos (Excel)",
                buffer.getvalue(),
                "auditoria_movimientos.xlsx"
            )

    # ---------------------------------------
    # TAB GRÁFICOS
    # ---------------------------------------
    with tab3:

        st.subheader("Consumo de Insumos")

        if not df_movs.empty:

            salidas = df_movs[df_movs['Operacion'] == 'SALIDA']

            if not salidas.empty:

                resumen = salidas.groupby("Material")["Cantidad"].sum()

                st.bar_chart(resumen)

                top = resumen.sort_values(ascending=False).head(1)

                if not top.empty:
                    st.metric(
                        "Material más usado",
                        top.index[0],
                        f"{top.values[0]:.2f}"
                    )
            else:
                st.info("No hay salidas registradas aún.")
        else:
            st.info("No hay datos para graficar.")

    # ---------------------------------------
    # TAB ALERTAS
    # ---------------------------------------
    with tab4:

        st.subheader("Control de Stock")

        df_inv = st.session_state.get('df_inv', pd.DataFrame())

        if df_inv.empty:
            st.warning("Inventario vacío.")
        else:
            criticos = df_inv[df_inv['cantidad'] <= df_inv['minimo']]

            if criticos.empty:
                st.success("Niveles de inventario óptimos")
            else:
                st.error(f"⚠️ Hay {len(criticos)} productos en nivel crítico")

                for _, r in criticos.iterrows():
                    st.warning(
                        f"**{r['item']}** bajo: {r['cantidad']} {r['unidad']} "
                        f"(mín: {r['minimo']})"
                    )

# ===========================================================
# MÓDULO DE COTIZACIONES - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
elif menu == "📝 Cotizaciones":

    st.title("📝 Cotizador Profesional")

    # Recuperamos datos provenientes de CMYK u otros módulos
    datos = st.session_state.get('datos_pre_cotizacion', {})

    consumos = datos.get('consumos', {})

    datos_pre = {
        'trabajo': datos.get('trabajo', "Trabajo General"),
        'costo_base': datos.get('costo_base', 0.0),
        'unidades': datos.get('unidades', 1),
        'C': consumos.get('C', 0.0),
        'M': consumos.get('M', 0.0),
        'Y': consumos.get('Y', 0.0),
        'K': consumos.get('K', 0.0)
    }

    usa_tinta = any([datos_pre['C'], datos_pre['M'], datos_pre['Y'], datos_pre['K']])

    # ---- CLIENTE ----
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    if df_cli.empty:
        st.warning("Registra clientes primero.")
        st.stop()

    opciones = {r['nombre']: r['id'] for _, r in df_cli.iterrows()}

    cliente_sel = st.selectbox("Cliente:", opciones.keys())
    id_cliente = opciones[cliente_sel]

    unidades = st.number_input(
        "Cantidad",
        min_value=1,
        value=int(datos_pre['unidades'])
    )

    # ---- COSTOS ----
    costo_unit = st.number_input(
        "Costo unitario base ($)",
        value=float(datos_pre['costo_base'] / unidades if unidades else 0)
    )

    margen = st.slider("Margen %", 10, 300, 100)

    costo_total = costo_unit * unidades
    precio_final = costo_total * (1 + margen / 100)

    st.metric("Precio sugerido", f"$ {precio_final:.2f}")

    # ---- CONSUMOS ----
    consumos_reales = {}

    if usa_tinta:

        df_tintas = obtener_tintas_disponibles()

        if df_tintas.empty:
            st.error("No hay tintas registradas en inventario.")
            st.stop()

        opciones_tinta = {
            f"{r['item']} ({r['cantidad']} ml)": r['id']
            for _, r in df_tintas.iterrows()
        }

        st.subheader("Asignación de Tintas a Descontar")

        for color in ['C', 'M', 'Y', 'K']:
            sel = st.selectbox(f"Tinta {color}", opciones_tinta.keys(), key=color)
            consumos_reales[opciones_tinta[sel]] = datos_pre[color] * unidades

    metodo_pago = st.selectbox(
        "Método de Pago",
        ["Efectivo", "Zelle", "Pago Móvil", "Transferencia", "Pendiente"]
    )

    # =====================================================
    # 🔐 INTEGRACIÓN CON NÚCLEO CENTRAL
    # =====================================================
    if st.button("CONFIRMAR VENTA"):

        descr = datos_pre['trabajo']

        try:
            exito, msg = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_sel,
                detalle=descr,
                monto_usd=precio_final,
                metodo=metodo_pago,
                consumos=consumos_reales
            )

            if exito:
                st.success(msg)

                # Limpiamos datos temporales de cotización
                st.session_state.pop('datos_pre_cotizacion', None)

                cargar_datos()
                st.rerun()

            else:
                st.error(msg)

        except Exception as e:
            st.error(f"Error procesando venta: {e}")



# ===========================================================
# 🛒 MÓDULO DE VENTA DIRECTA - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
if menu == "🛒 Venta Directa":

    st.title("🛒 Venta Rápida de Materiales")

    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    if df_inv.empty:
        st.warning("No hay inventario cargado.")
        st.stop()

    disponibles = df_inv[df_inv['cantidad'] > 0]

    if disponibles.empty:
        st.warning("⚠️ No hay productos con stock disponible.")
        st.stop()

    # --- SELECCIÓN DE PRODUCTO ---
    with st.container(border=True):

        c1, c2 = st.columns([2, 1])

        prod_sel = c1.selectbox(
            "📦 Seleccionar Producto:",
            disponibles['item'].tolist()
        )

        datos = disponibles[disponibles['item'] == prod_sel].iloc[0]

        id_producto = int(datos['id'])
        stock_actual = float(datos['cantidad'])
        precio_base = float(datos['precio_usd'])
        unidad = datos['unidad']
        minimo = float(datos['minimo'])

        c2.metric("Stock Disponible", f"{stock_actual:.2f} {unidad}")

    # --- FORMULARIO DE VENTA ---
    with st.form("form_venta_directa", clear_on_submit=True):

        st.subheader("Datos de la Venta")

        # Cliente integrado
        if not df_cli.empty:
            opciones_cli = {
                row['nombre']: row['id']
                for _, row in df_cli.iterrows()
            }

            cliente_nombre = st.selectbox(
                "Cliente:",
                list(opciones_cli.keys())
            )

            id_cliente = opciones_cli[cliente_nombre]
        else:
            cliente_nombre = "Consumidor Final"
            id_cliente = None
            st.info("Venta sin cliente registrado")

        c1, c2, c3 = st.columns(3)

        cantidad = c1.number_input(
            f"Cantidad ({unidad})",
            min_value=0.0,
            max_value=stock_actual,
            step=1.0
        )

        margen = c2.number_input("Margen %", value=30.0, format="%.2f")

        metodo = c3.selectbox(
            "Método de Pago",
            [
                "Efectivo $",
                "Pago Móvil (BCV)",
                "Transferencia (Bs)",
                "Zelle",
                "Binance",
                "Pendiente"
            ]
        )

        usa_desc = st.checkbox("Aplicar descuento cliente fiel")
        desc = st.number_input(
            "Descuento %",
            value=5.0 if usa_desc else 0.0,
            disabled=not usa_desc,
            format="%.2f"
        )

        # Impuestos
        st.write("Impuestos aplicables:")

        i1, i2 = st.columns(2)

        usa_iva = i1.checkbox("Aplicar IVA")
        usa_banco = i2.checkbox("Comisión bancaria", value=True)

        # ---- CÁLCULOS ----
        costo_material = cantidad * precio_base
        con_margen = costo_material * (1 + margen / 100)
        con_desc = con_margen * (1 - desc / 100)

        impuestos = 0.0

        if usa_iva:
            impuestos += float(st.session_state.get('iva_perc', 16))

        if usa_banco and metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            impuestos += float(st.session_state.get('banco_perc', 0.5))

        total_usd = con_desc * (1 + impuestos / 100)

        # Conversión a Bs SOLO si aplica
        total_bs = 0.0

        if metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            total_bs = total_usd * float(st.session_state.get('tasa_bcv', 1.0))

        elif metodo == "Binance":
            total_bs = total_usd * float(st.session_state.get('tasa_binance', 1.0))

        st.divider()

        st.metric("Total a Cobrar", f"$ {total_usd:.2f}")

        if total_bs > 0:
            st.info(f"Equivalente: Bs {total_bs:,.2f}")

        # ---- VALIDACIONES FINALES ----
        if st.form_submit_button("🧾 Confirmar Venta"):

            if cantidad <= 0:
                st.error("⚠️ Debe vender al menos una unidad.")
                st.stop()

            if cantidad > stock_actual:
                st.error("⚠️ No puedes vender más de lo que hay en inventario.")
                st.stop()

            # Preparar consumo para el núcleo
            consumos = {id_producto: cantidad}

            try:
                exito, mensaje = registrar_venta_global(
                    id_cliente=id_cliente,
                    nombre_cliente=cliente_nombre,
                    detalle=f"Venta directa de {prod_sel}",
                    monto_usd=float(total_usd),
                    metodo=metodo,
                    consumos=consumos
                )

                if exito:
                    st.success(mensaje)
                    cargar_datos()
                    st.rerun()
                else:
                    st.error(mensaje)

            except Exception as e:
                st.error(f"Error registrando venta: {e}")


       # ===========================================================
# 🛒 MÓDULO DE VENTA DIRECTA - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
if menu == "🛒 Venta Directa":

    st.title("🛒 Venta Rápida de Materiales")

    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    if df_inv.empty:
        st.warning("No hay inventario cargado.")
        st.stop()

    disponibles = df_inv[df_inv['cantidad'] > 0]

    if disponibles.empty:
        st.warning("⚠️ No hay productos con stock disponible.")
        st.stop()

    # --- SELECCIÓN DE PRODUCTO ---
    with st.container(border=True):

        c1, c2 = st.columns([2, 1])

        prod_sel = c1.selectbox(
            "📦 Seleccionar Producto:",
            disponibles['item'].tolist(),
            key="venta_directa_producto"
        )

        datos = disponibles[disponibles['item'] == prod_sel].iloc[0]

        id_producto = datos['id']
        stock_actual = float(datos['cantidad'])
        precio_base = float(datos['precio_usd'])
        unidad = datos['unidad']
        minimo = float(datos['minimo'])

        c2.metric("Stock Disponible", f"{stock_actual:.2f} {unidad}")

    # --- FORMULARIO DE VENTA ---
    with st.form("form_venta_directa", clear_on_submit=True):

        st.subheader("Datos de la Venta")

        # Cliente integrado
        if not df_cli.empty:
            opciones_cli = {
                row['nombre']: row['id']
                for _, row in df_cli.iterrows()
            }

            cliente_nombre = st.selectbox(
                "Cliente:",
                opciones_cli.keys(),
                key="venta_directa_cliente"
            )

            id_cliente = opciones_cli[cliente_nombre]
        else:
            cliente_nombre = "Consumidor Final"
            id_cliente = None
            st.info("Venta sin cliente registrado")

        c1, c2, c3 = st.columns(3)

        cantidad = c1.number_input(
            f"Cantidad ({unidad})",
            min_value=0.0,
            max_value=stock_actual,
            step=1.0,
            key="venta_directa_cantidad"
        )

        margen = c2.number_input(
            "Margen %",
            value=30.0,
            key="venta_directa_margen"
        )

        metodo = c3.selectbox(
            "Método de Pago",
            [
                "Efectivo $",
                "Pago Móvil (BCV)",
                "Transferencia (Bs)",
                "Zelle",
                "Binance",
                "Pendiente"
            ],
            key="venta_directa_metodo"
        )

        usa_desc = st.checkbox(
            "Aplicar descuento cliente fiel",
            key="venta_directa_usa_descuento"
        )

        desc = st.number_input(
            "Descuento %",
            value=5.0 if usa_desc else 0.0,
            disabled=not usa_desc,
            key="venta_directa_descuento"
        )

        # Impuestos
        st.write("Impuestos aplicables:")

        i1, i2 = st.columns(2)

        usa_iva = i1.checkbox(
            "Aplicar IVA",
            key="venta_directa_iva"
        )

        usa_banco = i2.checkbox(
            "Comisión bancaria",
            value=True,
            key="venta_directa_banco"
        )

        # ---- CÁLCULOS ----
        costo_material = cantidad * precio_base
        con_margen = costo_material * (1 + margen / 100)
        con_desc = con_margen * (1 - desc / 100)

        impuestos = 0

        if usa_iva:
            impuestos += st.session_state.get('iva_perc', 16)

        if usa_banco and metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            impuestos += st.session_state.get('banco_perc', 0.5)

        total_usd = con_desc * (1 + impuestos / 100)

        if metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            total_bs = total_usd * t_bcv
        elif metodo == "Binance":
            total_bs = total_usd * t_bin
        else:
            total_bs = 0

        st.divider()

        st.metric("Total a Cobrar", f"$ {total_usd:.2f}")

        if total_bs:
            st.info(f"Equivalente: Bs {total_bs:,.2f}")

        # =====================================================
        # 🔐 AQUÍ ENTRA EL NÚCLEO CENTRAL DEL IMPERIO
        # =====================================================
        if st.form_submit_button("🚀 PROCESAR VENTA"):

            if cantidad <= 0:
                st.error("⚠️ Debes vender al menos una unidad.")
                st.stop()

            if cantidad > stock_actual:
                st.error("⚠️ No puedes vender más de lo que hay en inventario.")
                st.stop()

            consumos = {
                id_producto: cantidad
            }

            exito, mensaje = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_nombre,
                detalle=f"{cantidad} {unidad} de {prod_sel}",
                monto_usd=total_usd,
                metodo=metodo,
                consumos=consumos
            )

            if exito:
                st.success(mensaje)

                if stock_actual - cantidad <= minimo:
                    st.warning("⚠️ Producto quedó en nivel crítico")

                st.session_state.ultimo_ticket = {
                    "cliente": cliente_nombre,
                    "detalle": f"{cantidad} {unidad} de {prod_sel}",
                    "total": total_usd,
                    "metodo": metodo
                }

                st.rerun()
            else:
                st.error(mensaje)

    # --- TICKET ---
    if 'ultimo_ticket' in st.session_state:

        st.divider()

        t = st.session_state.ultimo_ticket

        with st.expander("📄 Recibo de Venta", expanded=True):

            st.code(
f"""
CLIENTE: {t['cliente']}
DETALLE: {t['detalle']}
TOTAL: $ {t['total']:.2f}
MÉTODO: {t['metodo']}
"""
            )

            if st.button("Cerrar Ticket"):
                del st.session_state.ultimo_ticket
                st.rerun()


# ===========================================================
# 🔐 NÚCLEO CENTRAL DE REGISTRO DE VENTAS DEL IMPERIO
# ===========================================================

def registrar_venta_global(
    id_cliente=None,
    nombre_cliente="Consumidor Final",
    detalle="Venta general",
    monto_usd=0.0,
    metodo="Efectivo $",
    consumos=None
):
    """
    FUNCIÓN MAESTRA DEL IMPERIO – VERSIÓN SEGURA Y TRANSACCIONAL
    """

    if consumos is None:
        consumos = {}

    if monto_usd <= 0:
        return False, "⚠️ El monto de la venta debe ser mayor a 0"

    if not detalle:
        return False, "⚠️ El detalle de la venta no puede estar vacío"

    try:
        conn = conectar()
        cursor = conn.cursor()

        conn.execute("BEGIN TRANSACTION")

        if id_cliente is not None:
            existe_cli = cursor.execute(
                "SELECT id FROM clientes WHERE id = ?",
                (id_cliente,)
            ).fetchone()

            if not existe_cli:
                conn.rollback()
                return False, "❌ Cliente no encontrado en base de datos"

        for item_id, cant in consumos.items():

            if cant <= 0:
                conn.rollback()
                return False, f"⚠️ Cantidad inválida para el insumo {item_id}"

            stock_actual = cursor.execute(
                "SELECT cantidad, item FROM inventario WHERE id = ?",
                (item_id,)
            ).fetchone()

            if not stock_actual:
                conn.rollback()
                return False, f"❌ Insumo con ID {item_id} no existe"

            cantidad_disponible, nombre_item = stock_actual

            if cant > cantidad_disponible:
                conn.rollback()
                return False, f"⚠️ Stock insuficiente para: {nombre_item}"

        for item_id, cant in consumos.items():

            cursor.execute("""
                UPDATE inventario
                SET cantidad = cantidad - ?
                WHERE id = ?
            """, (cant, item_id))

            cursor.execute("""
                INSERT INTO inventario_movs
                (item_id, tipo, cantidad, motivo)
                VALUES (?, 'SALIDA', ?, ?)
            """, (item_id, cant, f"Venta: {detalle}"))

        cursor.execute("""
            INSERT INTO ventas
            (cliente_id, cliente, detalle, monto_total, metodo)
            VALUES (?, ?, ?, ?, ?)
        """, (
            id_cliente,
            nombre_cliente,
            detalle,
            float(monto_usd),
            metodo
        ))

        conn.commit()
        conn.close()

        cargar_datos()

        return True, "✅ Venta procesada correctamente"

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass

        return False, f"❌ Error interno al procesar la venta: {str(e)}"

























