importar streamlit como st
importar pandas como pd
importar sqlite3
importar numpy como np
importar io
importar plotly.express como px
desde PIL importar imagen
desde datetime importar datetime, fecha, timedelta
tiempo de importación
importar sistema operativo
importar hashlib
importar hmac
secretos de importación

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide", page_icon="⚛️")

# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():
    """Conexión principal a la base de datos del Imperio."""
    conn = sqlite3.connect('imperio_v2.db', comprobar_el_mismo_hilo=Falso)
    conn.execute("PRAGMA claves_foráneas = ON")
    conexión de retorno


def hash_password(contraseña: str, salt: str | Ninguno = Ninguno) -> str:
    """Genera hash PBKDF2 para almacenar contraseñas sin texto plano."""
    sal = sal o secretos.token_hex(16)
    iteraciones = 120_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iteraciones).hex()
    devolver f"pbkdf2_sha256${iteraciones}${sal}${digesto}"


def verificar_contraseña(contraseña: str, hash_contraseña: str | Ninguno) -> bool:
    si no es password_hash:
        devuelve Falso
    intentar:
        algoritmo, iteraciones, sal, resumen = password_hash.split('$', 3)
        si algoritmo != 'pbkdf2_sha256':
            devuelve Falso
        resumen_de_prueba = hashlib.pbkdf2_hmac(
            'sha256',
            contraseña.encode('utf-8'),
            sal.encode('utf-8'),
            int(iteraciones)
        ).maleficio()
        devolver hmac.compare_digest(test_digest, digest)
    excepto (ValueError, TypeError):
        devuelve Falso


def obtener_contraseña_admin_inicial() -> str:
    """Obtiene la contraseña inicial desde el entorno para evitar el código total en el código."""
    devolver os.getenv('IMPERIO_ADMIN_PASSWORD', 'atomica2026')

# --- 3. INICIALIZACIÓN DEL SISTEMA ---
def inicializar_sistema():
    con conectar() como conexión:
        c = conexión.cursor()

        tablas = [

            # CLIENTES
            "CREAR TABLA SI NO EXISTE clientes (id ENTERO CLAVE PRIMARIA AUTOINCREMENT, nombre TEXTO, whatsapp TEXTO)",

            # INVENTARIO (MEJORADO)
            """CREAR TABLA SI NO EXISTE inventario (
                id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                artículo TEXTO ÚNICO,
                cantidad REAL,
                unidad TEXTO,
                precio_usd REAL,
                minimo REAL PREDETERMINADO 5.0,
                ultima_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # CONFIGURACIÓN
            "CREAR TABLA SI NO EXISTE configuración (parámetro TEXTO CLAVE PRIMARIA, valor REAL)",

            # USUARIOS
            "CREAR TABLA SI NO EXISTE usuarios (nombre de usuario TEXTO CLAVE PRINCIPAL, contraseña TEXTO, hash_de_contraseña TEXTO, rol TEXTO, nombre TEXTO)",

            # VENTAS
            "CREAR TABLA SI NO EXISTE ventas (id ENTERO CLAVE PRINCIPAL AUTOINCREMENT, cliente_id ENTERO, cliente TEXTO, detalle TEXTO, monto_total REAL, método TEXTO, fecha FECHA Y HORA PREDETERMINADA ESTAMPA_DE_TIEMPO_ACTUAL)",

            #GASTOS
            "CREAR TABLA SI NO EXISTE gastos (id INTEGER CLAVE PRINCIPAL AUTOINCREMENT, descripción TEXTO, monto REAL, categoría TEXTO, método TEXTO, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",

            # MOVIMIENTOS DE INVENTARIO (MEJORADO)
            """CREAR TABLA SI NO EXISTE inventario_movs (
                id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                item_id ENTERO,
                tipo TEXTO,
                cantidad REAL,
                motivo TEXTO,
                usuario TEXTO,
                fecha FECHA Y HORA PREDETERMINADA MARCA_DE_TIEMPO_ACTUAL,
                CLAVE EXTERNA(item_id) REFERENCIAS inventario(id)
            )""",

            # PROVEEDORES
            """CREAR TABLA SI NO EXISTE proveedores (
                id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                nombre TEXTO ÚNICO,
                teléfono TEXTO,
                TEXTO rif,
                contacto TEXTO,
                observaciones TEXTO,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # HISTORIAL DE COMPRAS
            """CREAR TABLA SI NO EXISTE historial_compras (
                id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                artículo TEXTO,
                proveedor_id ENTERO,
                cantidad REAL,
                unidad TEXTO,
                costo_total_usd REAL,
                costo_unidad_usd REAL,
                impuestos REALES,
                entrega REAL,
                tasa_usada REAL,
                moneda_pago TEXTO,
                usuario TEXTO,
                fecha FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
            )"""
        ]

        para tabla en tablas:
            c.execute(tabla)

        # MIGRACIONES LIGERAS
        columnas_usuarios = {fila[1] para fila en c.execute("PRAGMA table_info(usuarios)").fetchall()}
        si 'password_hash' no está en columnas_usuarios:
            c.execute("ALTER TABLE usuarios ADD COLUMN password_hash TEXT")

        columnas_movs = {fila[1] para la fila en c.execute("PRAGMA table_info(inventario_movs)").fetchall()}
        si 'item_id' no está en columnas_movs:
            c.execute("ALTER TABLE inventario_movs AGREGAR COLUMNA item_id ENTERO")
        si 'item' en columnas_movs:
            c.ejecutar(
                """
                ACTUALIZAR inventario_movs
                ESTABLECER item_id = (
                    SELECCIONAR i.id DE inventario i DONDE i.item = inventario_movs.item LÍMITE 1
                )
                DONDE item_id ES NULO
                """
            )

        columnas_inventario = {fila[1] para fila en c.execute("PRAGMA table_info(inventario)").fetchall()}
        si 'cantidad' no está en columnas_inventario:
            c.execute("ALTER TABLE inventario ADD COLUMN cantidad REAL DEFAULT 0")
        si 'unidad' no está en columnas_inventario:
            c.execute("ALTER TABLE inventario ADD COLUMN unidad TEXT DEFAULT 'Unidad'")
        si 'precio_usd' no está en columnas_inventario:
            c.execute("ALTER TABLE inventario ADD COLUMN precio_usd REAL DEFAULT 0")
        si 'minimo' no está en columnas_inventario:
            c.execute("ALTER TABLE inventario ADD COLUMN minimo REAL DEFAULT 5.0")
        si 'ultima_actualizacion' no está en columnas_inventario:
            c.execute("ALTER TABLE inventario ADD COLUMN ultima_actualizacion DATETIME")
            c.execute("ACTUALIZAR inventario SET ultima_actualizacion = CURRENT_TIMESTAMP WHERE ultima_actualizacion IS NULL")
        si 'imprimible_cmyk' no está en columnas_inventario:
            c.execute("ALTER TABLE inventario ADD COLUMN imprimible_cmyk INTEGER DEFAULT 0")

        c.execute("CREAR ÍNDICE SI NO EXISTE idx_inventario_movs_item_id EN inventario_movs(item_id)")

        columnas_proveedores = {row[1] for row in c.execute("PRAGMA table_info(proveedores)").fetchall()}
        si "telefono" no está en columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN telefono TEXT")
        si "rif" no está en columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN rif TEXT")
        si "contacto" no está en columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN contacto TEXT")
        si "observaciones" no está en columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN observaciones TEXT")
        si "fecha_creacion" no está en columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN fecha_creacion TEXT")
            c.execute("UPDATE proveedores SET fecha_creacion = CURRENT_TIMESTAMP WHERE fecha_creacion IS NULL")

        # USUARIO ADMIN POR DEFECTO
        admin_password = obtener_contraseña_admin_inicial()
        c.ejecutar(
            """
            INSERTAR O IGNORAR EN usuarios (nombre de usuario, contraseña, hash de contraseña, rol, nombre)
            VALORES (?, ?, ?, ?, ?)
            """,
            ('jefa', '', hash_password(admin_password), 'Admin', 'Dueña del Imperio')
        )
        c.ejecutar(
            """
            ACTUALIZAR usuarios
            ESTABLECER password_hash = ?, contraseña = ''
            DONDE nombre_usuario = 'jefa' Y (password_hash ES NULO O password_hash = '')
            """,
            (hash_contraseña(contraseña_de_administrador),)
        )

        # CONFIGURACIÓN INICIAL
        configuración_init = [
            ('tasa_bcv', 36.50),
            ('tasa_binance', 38.00),
            ('costo_tinta_ml', 0.10),
            ('iva_perc', 16.0),
            ('igtf_perc', 3.0),
            ('banco_perc', 0.5),
            ('costo_tinta_auto', 1.0)
        ]

        para p, v en config_init:
            c.execute("INSERTAR O IGNORAR EN LOS VALORES de configuración (?,?)", (p, v))

        conexión.commit()


# --- 4. CARGA DE DATOS ---
def cargar_datos():
    con conectar() como conexión:
        intentar:
            st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
            st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)
            conf_df = pd.read_sql("SELECT * FROM configuracion", conn)
            para _, fila en conf_df.iterrows():
                st.session_state[fila['parámetro']] = float(fila['valor'])
        excepto (sqlite3.DatabaseError, ValueError, KeyError) como e:
            st.warning(f"No se pudieron cargar todos los datos de sesión: {e}")

# Alias ​​de compatibilidad para módulos que lo usan
def cargar_datos_seguros():
    cargar_datos()

# --- 5. LÓGICA DE ACCESO ---
si 'autenticado' no está en st.session_state:
    st.session_state.autenticado = Falso
    inicializar_sistema()

definición de inicio de sesión():
    st.title("⚛️ Acceso al Imperio Atómico")
    con st.container(border=True):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", tipo="contraseña")
        si st.button("Entrar", use_container_width=True):
            con conectar() como conexión:
                res = conn.execute(
                    "SELECT nombredeusuario, rol, nombre, contraseña, hash_de_contraseña FROM usuarios WHERE nombredeusuario=?",
                    (u,)
                ).fetchone()

            acceso_ok = Falso
            si res:
                nombre de usuario, rol, nombre, contraseña simple, contraseña hash = res
                si verificar_contraseña(p, hash_contraseña):
                    acceso_ok = Verdadero
                elif password_plain y hmac.compare_digest(password_plain, p):
                    acceso_ok = Verdadero
                    con conectar() como conexión:
                        conn.execute(
                            "ACTUALIZAR usuarios ESTABLECER contraseña_hash=?, contraseña='' DONDE nombre_usuario=?",
                            (hash_password(p), nombre de usuario)
                        )
                        conexión.commit()

            si acceso_ok:
                st.session_state.autenticado = Verdadero
                st.session_state.rol = rol
                st.session_state.usuario_nombre = nombre
                cargar_datos()
                st.rerun()
            demás:
                st.error("Acceso denegado")

si no es st.session_state.autenticado:
    acceso()
    st.stop()

# --- 6. VARIABLES DE LA BARRA LATERAL Y ---
cargar_datos()
t_bcv = st.session_state.get('tasa_bcv', 1.0)
t_bin = st.session_state.get('tasa_binance', 1.0)
ROL = st.session_state.get('rol', "Producción")

con st.sidebar:
    st.header(f"👋 {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 Bin: {t_bin}")

    menú = st.radio(
        "Secciones:",
        [
            "📊 Panel de control",
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

        
# ===========================================================
# 📊 TABLERO GENERAL
# ===========================================================
si el menú == "📊 Tablero":

    st.title("📊 Panel Ejecutivo")
    st.caption("Resumen general del negocio: ventas, gastos, clientes e inventario.")

    con conectar() como conexión:
        intentar:
            df_ventas = pd.read_sql("SELECT fecha, monto_total FROM ventas", conn)
        excepto Excepción:
            df_ventas = pd.DataFrame(columnas=["fecha", "monto_total"])

        intentar:
            df_gastos = pd.read_sql("SELECT fecha, monto FROM gastos", conn)
        excepto Excepción:
            df_gastos = pd.DataFrame(columnas=["fecha", "monto"])

        intentar:
            total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        excepto Excepción:
            total_clientes = 0

        intentar:
            df_inv_dash = pd.read_sql("SELECT cantidad, precio_usd, minimo FROM inventario", conn)
        excepto Excepción:
            df_inv_dash = pd.DataFrame(columns=["cantidad", "precio_usd", "minimo"])

    ventas_total = float(df_ventas["monto_total"].sum()) si no df_ventas.empty sino 0.0
    gastos_total = float(df_gastos["monto"].sum()) si no df_gastos.empty si no 0.0
    utilidad = ventas_total - gastos_total

    capital_inv = 0.0
    stock_bajo = 0
    si no es df_inv_dash.empty:
        capital_inv = float((df_inv_dash["cantidad"] * df_inv_dash["precio_usd"]).sum())
        stock_bajo = int((df_inv_dash["cantidad"] <= df_inv_dash["minimo"]).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💰 Ventas Acumuladas", f"${ventas_total:,.2f}")
    c2.metric("💸 Gastos Acumulados", f"${gastos_total:,.2f}")
    c3.metric("📈 Resultado Neto", f"${utilidad:,.2f}")
    c4.metric("👥 Clientes", total_clientes)
    c5.metric("🚨 Ítems en Mínimo", stock_bajo)

    st.divider()

    col_a, col_b = st.columns(2)

    con col_a:
        st.subheader("📆 Ventas por día")
        si df_ventas.empty:
            st.info("No hay ventas registradas.")
        demás:
            dfv = df_ventas.copy()
            dfv["fecha"] = pd.to_datetime(dfv["fecha"], errores="coaccionar")
            dfv = dfv.dropna(subconjunto=["fecha"])
            si dfv.vacío:
                st.info("No hay fechas válidas de ventas para graficar.")
            demás:
                dfv["día"] = dfv["fecha"].dt.date.astype(str)
                resumen_v = dfv.groupby("dia", as_index=False)["monto_total"].sum()
                fig_v = px.line(resumen_v, x="dia", y="monto_total", marcadores=Verdadero)
                fig_v.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
                st.plotly_chart(fig_v, use_container_width=True)

    con col_b:
        st.subheader("📉 Gastos por día")
        si df_gastos.empty:
            st.info("No hay gastos registrados.")
        demás:
            dfg = df_gastos.copia()
            dfg["fecha"] = pd.to_datetime(dfg["fecha"], errors="coerce")
            dfg = dfg.dropna(subconjunto=["fecha"])
            si dfg.vacío:
                st.info("No hay fechas válidas de gastos para graficar.")
            demás:
                dfg["dia"] = dfg["fecha"].dt.date.astype(str)
                resumen_g = dfg.groupby("dia", as_index=False)["monto"].sum()
                fig_g = px.bar(resumen_g, x="dia", y="monto")
                fig_g.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
                st.plotly_chart(fig_g, use_container_width=True)

    st.divider()
    st.subheader("📦 Estado del Inventario")
    st.metric("💼 Capital inmovilizado en inventario", f"${capital_inv:,.2f}")

# ===========================================================
# 📦 MÓDULO DE INVENTARIO – ESTRUCTURA CORREGIDA
# ===========================================================
menú elif == "📦 Inventario":

    st.title("📦 Centro de Control de Suministros")

    # --- SINCRONIZACIÓN CON SESIÓN ---
    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    t_ref = st.session_state.get('tasa_bcv', 36.5)
    t_bin = st.session_state.get('tasa_binance', 38.0)
    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    # =======================================================
    # 1️⃣ TABLERO EJECUTIVO
    # =======================================================
    si no df_inv.empty:

        con st.container(border=True):

            c1, c2, c3, c4 = st.columns(4)

            capital_total = (df_inv["cantidad"] * df_inv["precio_usd"]).sum()
            items_criticos = df_inv[df_inv["cantidad"] <= df_inv["minimo"]]
            total_de_artículos = len(df_inv)

            salud = ((total_items - len(items_criticos)) / total_items) * 100 si total_items > 0 de lo contrario 0

            c1.metric("💰 Capital en Inventario", f"${capital_total:,.2f}")
            c2.metric("📦 Total de elementos", total_elementos)
            c3.metric("🚨 Stock Bajo", len(items_criticos), delta="Revisar" if len(items_criticos) > 0 else "OK", delta_color="inverse")
            c4.metric("🧠 Salud del Almacén", f"{salud:.0f}%")

    # =======================================================
    # 2️⃣ PESTAÑAS
    # =======================================================
    pestañas = st.tabs([
        "📋 Existencias",
        "📥 Registrar Compra",
        "📊 Compras históricas",
        "👤 Proveedores",
        "🔧 Ajustes"
    ])

    # =======================================================
    # 📋 PESTAÑA 1 — EXISTENCIAS
    # =======================================================
    con pestañas[0]:

        si df_inv.empty:
            st.info("Inventario vacío.")
        demás:
            col1, col2, col3 = st.columns([2, 1, 1])
            filtro = col1.text_input("🔍 Buscar insumo")
            moneda_vista = col2.selectbox("Moneda", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], key="inv_moneda_vista")
            solo_bajo = col3.checkbox("🚨 Solo stock bajo")

            tasa_vista = 1.0
            símbolo = "$"

            si "BCV" en moneda_vista:
                tasa_vista = t_ref
                símbolo = "Bs"
            elif "Binance" en moneda_vista:
                tasa_vista = t_bin
                símbolo = "Bs"

            df_v = df_inv.copiar()

            si filtro:
                df_v = df_v[df_v["item"].str.contains(filtro, case=False)]

            si solo_bajo:
                df_v = df_v[df_v["cantidad"] <= df_v["minimo"]]

            df_v["Costo Unitario"] = df_v["precio_usd"] * tasa_vista
            df_v["Valor Total"] = df_v["cantidad"] * df_v["Costo Unitario"]


            def resaltar_critico(fila):
                if fila["cantidad"] <= fila["minimo"]:
                    devolver ['color de fondo: rgba(255,0,0,0.15)'] * len(fila)
                devolver [''] * len(fila)
          
            st.dataframe(
               df_v.style.apply(resaltar_critico, eje=1),
                configuración_de_columna={
                    "item": "Insumo",
                    "cantidad": "Stock",
                    "unidad": "Unidad",
                    "Costo Unitario": st.column_config.NumberColumn(
                        f"Costo ({simbolo})", formato="%.4f"
                    ),
                    "Valor total": st.column_config.NumberColumn(
                        f"Valor Total ({simbolo})", formato="%.2f"
                    ),
                    "minimo": "Mínimo",
                    "imprimible_cmyk": st.column_config.CheckboxColumn("CMYK", help="Disponible para impresión en Análisis CMYK"),
                    "precio_usd": Ninguno,
                    "id": Ninguno,
                    "ultima_actualizacion": Ninguna
                },
                use_container_width=Verdadero,
                hide_index=Verdadero
            )

        st.divider()
        st.subheader("🛠 Gestión de Insumo Existente")

        si no df_inv.empty:

            insumo_sel = st.selectbox("Seleccionar Insumo", df_inv["item"].tolist())
            fila_sel = df_inv[df_inv["item"] == insumo_sel].iloc[0]
            colA, colB, colC = st.columnas(3)
            nuevo_min = colA.number_input("Nuevo Stock Mínimo", min_value=0.0, value=float(fila_sel.get('minimo', 0)))
            flag_cmyk = colB.checkbox("Visible en CMYK", valor=bool(fila_sel.get('imprimible_cmyk', 0)))

            if colA.button("Actualizar Mínimo"):
                con conectar() como conexión:
                    conn.execute(
                        "ACTUALIZAR inventario SET minimo=?, imprimible_cmyk=? ¿DONDE elemento=?",
                        (nuevo_min, 1 si flag_cmyk sino 0, insumo_sel)
                    )
                    conexión.commit()
                cargar_datos()
                st.success("Stock mínimo actualizado.")
                st.rerun()

            # Conversión para inventarios viejos cargados como cm2
            if str(fila_sel.get('unidad', '')).lower() == 'cm2':
                cm2_por_hoja = colC.number_input("cm² por hoja", valor_min=1.0, valor=100.0)
                if colC.button("🔄 Convertir stock cm2 → hojas"):
                    hojas = float(fila_sel.get('cantidad', 0)) / float(cm2_por_hoja)
                    con conectar() como conexión:
                        conn.execute(
                            "ACTUALIZAR inventario SET cantidad=?, unidad='hojas' WHERE item=?",
                            (hojas, insumo_sel)
                        )
                        conexión.commit()
                    st.success(f"Convertido a {hojas:.3f} hojas.")
                    cargar_datos()
                    st.rerun()
            if colB.button("🗑 Eliminar Insumo"):
                con conectar() como conexión:
                    existe_historial = conn.execute(
                        "SELECCIONAR CONTEO(*) DE historial_compras DONDE articulo=?",
                        (insumo_sel,)
                    ).fetchone()[0]
                    si existe_historial > 0:
                        st.error("No se puede eliminar: el insumo tiene historial de compras.")
                    demás:
                        st.session_state.confirmar_borrado = Verdadero

            si st.session_state.get("confirmar_borrado", Falso):
                st.warning(f"⚠ Confirmar eliminación de '{insumo_sel}'")
                colC, colD = st.columns(2)

                if colC.button("✅ Confirmar"):
                    con conectar() como conexión:
                        conn.execute(
                            "ELIMINAR DEL inventario DONDE artículo=?",
                            (insumo_sel,)
                        )
                        conexión.commit()
                    st.session_state.confirmar_borrado = Falso
                    cargar_datos()
                    st.success("Insumo eliminado.")
                    st.rerun()

                si colD.button("❌ Cancelar"):
                    st.session_state.confirmar_borrado = Falso

    # =======================================================
    # 📥 PESTAÑA 2 — COMPRA DE REGISTRO
    # =======================================================
    con pestañas[1]:

        st.subheader("📥 Registrador Nueva Compra")

        con conectar() como conexión:
            intentar:
                proveedores_existentes = pd.read_sql(
                    "SELECCIONAR nombre DE proveedores ORDENAR POR nombre ASC",
                    conexión
                )["nombre"].dropna().astype(str).tolist()
            excepto (sqlite3.DatabaseError, pd.errors.DatabaseError):
                proveedores_existentes = []

        col_base1, col_base2 = st.columns(2)
        nombre_c = col_base1.text_input("Nombre del Insumo")
        proveedor_sel = col_base2.selectbox(
            "Proveedor",
            ["(Sin proveedor)", "➕ Nuevo proveedor"] + proveedores_existentes,
            clave="inv_proveedor_compra"
        )

        proveedor = ""
        if proveedor_sel == "➕ Nuevo proveedor":
            proveedor = st.text_input("Nombre del nuevo proveedor", key="inv_proveedor_nuevo")
        elif proveedor_sel != "(Sin proveedor)":
            proveedor = proveedor_sel

        minimo_stock = st.number_input("Stock mínimo", min_value=0.0)
        imprimible_cmyk = st.casilla(
            "✅ Se puede imprimir (mostrar en módulo CMYK)",
            valor=Falso,
            help="Marca solo los insumos que sí participan en impresión (tintas, acetato imprimible, papeles de impresión)".
        )

        # ------------------------------
        # TIPO DE UNIDAD
        # ------------------------------
        tipo_unidad = st.selectbox(
            "Tipo de Unidad",
            ["Unidad", "Área (cm²)", "Líquido (ml)", "Peso (gr)"]
        )

        stock_real = 0
        unidad_final = "Unidad"

        if tipo_unidad == "Área (cm²)":
            c1, c2, c3 = st.columns(3)
            ancho = c1.number_input("Ancho (cm)", valor_mín=0.1)
            alto = c2.number_input("Alto (cm)", valor_mín=0.1)
            cantidad_envases = c3.number_input("Cantidad de Pliegos", min_value=0.001)

            # Inventario se controla por unidades físicas (hojas/pliegos),
            # no por área total acumulada. El área queda como referencia técnica.
            area_por_pliego = ancho * alto
            area_total_ref = area_por_pliego * cantidad_envases
            stock_real = cantidad_envases
            unidad_final = "hojas"

            st.caption(
                f"Referencia técnica: {area_por_pliego:,.2f} cm² por pliego | "
                f"Área total cargada: {area_total_ref:,.2f} cm²"
            )

        elif tipo_unidad == "Líquido (ml)":
            c1, c2 = st.columns(2)
            ml_por_envase = c1.number_input("ml por Envase", min_value=1.0)
            cantidad_envases = c2.number_input("Cantidad de Envases", min_value=0.001)
            stock_real = ml_por_envase * cantidad_envases
            unidad_final = "ml"

        elif tipo_unidad == "Peso (gr)":
            c1, c2 = st.columns(2)
            gr_por_envase = c1.number_input("gramos por Envase", min_value=1.0)
            cantidad_envases = c2.number_input("Cantidad de Envases", min_value=0.001)
            stock_real = gr_por_envase * cantidad_envases
            unidad_final = "gr"

        demás:
            cantidad_envases = st.number_input("Cantidad Comprada", min_value=0.001)
            stock_real = cantidad_envases
            unidad_final = "Unidad"

        # ------------------------------
        # DATOS FINANCIEROS
        # ------------------------------
        col4, col5 = st.columns(2)
        monto_factura = col4.number_input("Monto Factura", min_value=0.0)
        moneda_pago = col5.selectbox(
            "Moneda",
            ["USD $", "Bs (BCV)", "Bs (Binance)"],
            clave="inv_moneda_pago"
        )

        col6, col7, col8 = st.columns(3)
        iva_activo = col6.checkbox(f"IVA (+{st.session_state.get('iva_perc',16)}%)")
        igtf_activo = col7.checkbox(f"IGTF (+{st.session_state.get('igtf_perc',3)}%)")
        banco_activo = col8.checkbox(f"Banco (+{st.session_state.get('banco_perc',0.5)}%)")

        st.caption(f"Sugerencia de impuesto total para compras: {st.session_state.get('inv_impuesto_default', 16.0):.2f}%")

        entrega = st.number_input("Gastos Logística / Entrega ($)", valor=float(st.session_state.get("inv_delivery_default", 0.0)))

        # ------------------------------
        # BOTÓN GUARDAR
        # ------------------------------
        si st.button("💾 Guardar Compra", use_container_width=True):

            si no nombre_c:
                st.error("Debe indicar el nombre del insumo.")
                st.stop()

            si stock_real <= 0:
                st.error("Cantidad inválida.")
                st.stop()

            si "BCV" en moneda_pago:
                tasa_usada = t_ref
            elif "Binance" en moneda_pago:
                tasa_usada = t_bin

            demás:
                tasa_usada = 1.0

            porc_impuestos = 0
            si iva_activo:
                porc_impuestos += st.session_state.get("iva_perc", 16)
            si igtf_activo:
                porc_impuestos += st.session_state.get("igtf_perc", 3)
            si banco_activo:
                porc_impuestos += st.session_state.get("banco_perc", 0.5)

            costo_total_usd = ((monto_factura / tasa_usada) * (1 + (porc_impuestos / 100))) + entrega
            costo_unitario = costo_total_usd / stock_real

            con conectar() como conexión:
                cur = conn.cursor()


                proveedor_id = Ninguno
                si proveedor:
                    cur.execute("SELECT id FROM proveedores WHERE nombre=?", (proveedor,))
                    prov = cur.fetchone()
                    si no se prueba:
                        cur.execute("INSERT INTO proveedores (nombre) VALUES (?)", (proveedor,))
                        proveedor_id = cur.lastrowid
                    demás:
                        proveedor_id = prov[0]

                viejo = cur.execute(
                    "SELECT cantidad, precio_usd FROM inventario WHERE item=?",
                    (nombre_c,)
                ).fetchone()

                si es viejo:
                    nueva_cant = antiguo[0] + stock_real
                    precio_ponderado = (
                        (antiguo[0] * antiguo[1] + stock_real * costo_unitario)
                        / nueva_cant
                    )
                demás:
                    nueva_cant = stock_real
                    precio_ponderado = costo_unitario

                si es viejo:
                    cur.ejecutar(
                        """
                        ACTUALIZAR inventario
                        SET cantidad=?, unidad=?, precio_usd=?, minimo=?, imprimible_cmyk=?, ultima_actualizacion=CURRENT_TIMESTAMP
                        ¿DONDE artículo=?
                        """,
                        (nueva_cant, unidad_final, precio_ponderado, minimo_stock, 1 if imprimible_cmyk else 0, nombre_c)
                    )
                demás:
                    cur.ejecutar(
                        """
                        INSERTAR EN inventario
                        (item, cantidad, unidad, precio_usd, minimo, imprimible_cmyk, ultima_actualizacion)
                        VALORES (?, ?, ?, ?, ?, ?, MARCA_DE_TIEMPO_ACTUAL)
                        """,
                        (nombre_c, nueva_cant, unidad_final, precio_ponderado, minimo_stock, 1 if imprimible_cmyk else 0)
                    )

                cur.execute("""
                    INSERTAR EN historial_compras
                    (item, proveedor_id, cantidad, unidad, costo_total_usd, costo_unit_usd, impuestos, entrega, tasa_usada, moneda_pago, usuario)
                    VALORES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    nombre_c,
                    proveedor_id,
                    stock_real,
                    unidad_final,
                    costo_total_usd,
                    costo_unitario,
                    porc_impuestos,
                    entrega,
                    tasa_usada,
                    moneda_pago,
                    usuario_actual
                ))

                item_id_row = cur.execute(
                    "SELECCIONAR id DE inventario DONDE artículo = ?",
                    (nombre_c,)
                ).fetchone()

                si item_id_row:
                    cur.execute("""
                        INSERTAR EN inventario_movs
                        (item_id, tipo, cantidad, motivo, usuario)
                        VALORES (?,?,?,?,?)
                    """, (
                        item_id_row[0],
                        "ENTRADA",
                        stock_real,
                        "Compra registrada",
                        usuario_actual
                    ))

                conexión.commit()

            cargar_datos()
            st.success("Compra registrada correctamente.")
            st.rerun()


    # =======================================================
    # 📊 PESTAÑA 3 — HISTORIAL DE COMPRAS
    # =======================================================
    con pestañas[2]:

        st.subheader("📊 Historial Profesional de Compras")

        con conectar() como conexión:
            df_hist = pd.read_sql("""
                SELECCIONAR 
                    h.fecha,
                    h.item,
                    h.cantidad,
                    h.unidad,
                    h.costo_total_usd,
                    h.costo_unidad_usd,
                    h.impuestos,
                    h.entrega,
                    h.moneda_pago,
                    p.nombre como proveedor
                DESDE historial_compras h
                LEFT JOIN proveedores p ON h.proveedor_id = p.id
                ORDENAR POR h.fecha DESC
            """, conexión)

        si df_hist.empty:
            st.info("No hay compras registradas.")
        demás:

            col1, col2 = st.columns(2)

            filtro_item = col1.text_input("🔍 Filtrar por Insumo")
            filtro_proveedor = col2.text_input("👤 Filtrar por Proveedor")

            df_v = df_hist.copiar()

            si filtro_item:
                df_v = df_v[df_v["item"].str.contains(filtro_item, case=False)]

            si filtro_proveedor:
                df_v = df_v[df_v["proveedor"].fillna("").str.contains(filtro_proveedor, case=False)]

            total_compras = df_v["costo_total_usd"].sum()

            st.metric("💰 Total Comprado (USD)", f"${total_compras:,.2f}")

            st.dataframe(
                df_v,
                configuración_de_columna={
                    "fecha": "Fecha",
                    "item": "Insumo",
                    "cantidad": "Cantidad",
                    "unidad": "Unidad",
                    "costo_total_usd": st.column_config.NumberColumn("Costo total ($)", formato="%.2f"),
                    "costo_unit_usd": st.column_config.NumberColumn("Costo Unidad ($)", formato="%.4f"),
                    "impuestos": "Impuestos %",
                    "entrega": "Entrega $",
                    "moneda_pago": "Moneda",
                    "proveedor": "Proveedor"
                },
                use_container_width=Verdadero,
                hide_index=Verdadero
            )

    # =======================================================
    # 👤 PESTAÑA 4 — PROVEEDORES
    # =======================================================
    con pestañas[3]:

        st.subheader("👤 Directorio de Proveedores")

        con conectar() como conexión:
            intentar:
                columnas_proveedores = {
                    fila[1] para fila en conn.execute("PRAGMA table_info(proveedores)").fetchall()
                }
                si no columnas_proveedores:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS proveedores (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nombre TEXT UNIQUE,
                            telefono TEXT,
                            rif TEXT,
                            contacto TEXT,
                            observaciones TEXT,
                            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    conn.commit()
                    columnas_proveedores = {
                        row[1] for row in conn.execute("PRAGMA table_info(proveedores)").fetchall()
                    }

                def sel_col(nombre_columna):
                    return nombre_columna if nombre_columna in columnas_proveedores else f"NULL AS {nombre_columna}"

                query_proveedores = f"""
                    SELECT
                        {sel_col('id')},
                        {sel_col('nombre')},
                        {sel_col('telefono')},
                        {sel_col('rif')},
                        {sel_col('contacto')},
                        {sel_col('observaciones')},
                        {sel_col('fecha_creacion')}
                    FROM proveedores
                    ORDER BY nombre ASC
                """
                df_prov = pd.read_sql(query_proveedores, conn)
            except (sqlite3.DatabaseError, pd.errors.DatabaseError) as e:
                st.error(f"No se pudo cargar la tabla de proveedores: {e}")
                df_prov = pd.DataFrame(columns=[
                    'id', 'nombre', 'telefono', 'rif', 'contacto', 'observaciones', 'fecha_creacion'
                ])

        if df_prov.empty:
            st.info("No hay proveedores registrados todavía.")
        else:
            filtro_proveedor = st.text_input("🔍 Buscar proveedor")
            df_prov_view = df_prov.copy()

            if filtro_proveedor:
                mask_nombre = df_prov_view["nombre"].fillna("").str.contains(filtro_proveedor, case=False)
                mask_contacto = df_prov_view["contacto"].fillna("").str.contains(filtro_proveedor, case=False)
                mask_rif = df_prov_view["rif"].fillna("").str.contains(filtro_proveedor, case=False)
                df_prov_view = df_prov_view[mask_nombre | mask_contacto | mask_rif]

            st.dataframe(
                df_prov_view,
                column_config={
                    "id": None,
                    "nombre": "Proveedor",
                    "telefono": "Teléfono",
                    "rif": "RIF",
                    "contacto": "Contacto",
                    "observaciones": "Observaciones",
                    "fecha_creacion": "Creado"
                },
                use_container_width=True,
                hide_index=True
            )

        st.divider()
        st.subheader("➕ Registrar / Editar proveedor")

        nombre_edit = st.selectbox(
            "Proveedor a editar",
            ["Nuevo proveedor"] + (df_prov["nombre"].tolist() if not df_prov.empty else []),
            key="inv_proveedor_selector"
        )

        prov_actual = None
        if nombre_edit != "Nuevo proveedor" and not df_prov.empty:
            prov_actual = df_prov[df_prov["nombre"] == nombre_edit].iloc[0]

        with st.form("form_proveedor"):
            c1, c2 = st.columns(2)
            nombre_prov = c1.text_input("Nombre", value="" if prov_actual is None else str(prov_actual["nombre"] or ""))
            telefono_prov = c2.text_input("Teléfono", value="" if prov_actual is None else str(prov_actual["telefono"] or ""))
            c3, c4 = st.columns(2)
            rif_prov = c3.text_input("RIF", value="" if prov_actual is None else str(prov_actual["rif"] or ""))
            contacto_prov = c4.text_input("Persona de contacto", value="" if prov_actual is None else str(prov_actual["contacto"] or ""))
            observaciones_prov = st.text_area("Observaciones", value="" if prov_actual is None else str(prov_actual["observaciones"] or ""))

            guardar_proveedor = st.form_submit_button("💾 Guardar proveedor", use_container_width=True)

        if guardar_proveedor:
            if not nombre_prov.strip():
                st.error("El nombre del proveedor es obligatorio.")
            else:
                try:
                    with conectar() as conn:
                        if prov_actual is None:
                            conn.execute(
                                """
                                INSERT INTO proveedores (nombre, telefono, rif, contacto, observaciones)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (nombre_prov.strip(), telefono_prov.strip(), rif_prov.strip(), contacto_prov.strip(), observaciones_prov.strip())
                            )
                        demás:
                            conn.execute(
                                """
                                ACTUALIZACIÓN proveedores
                                SET nombre=?, telefono=?, rif=?, contacto=?, observaciones=?
                                ¿DONDE id=?
                                """,
                                (
                                    nombre_prov.strip(),
                                    teléfono_prov.strip(),
                                    rif_prov.strip(),
                                    contacto_prov.strip(),
                                    observaciones_prov.strip(),
                                    int(prov_actual["id"])
                                )
                            )
                        conexión.commit()
                    st.success("Proveedor guardado correctamente.")
                    st.rerun()
                excepto sqlite3.IntegrityError:
                    st.error("Ya existe un proveedor con ese nombre.")

        si prov_actual no es Ninguno:
            if st.button("🗑 Eliminar proveedor seleccionado", type="secundario"):
                con conectar() como conexión:
                    compras = conn.execute(
                        "SELECCIONAR CUENTA(*) DE historial_compras DONDE proveedor_id=?",
                        (int(prov_actual["id"]),)
                    ).fetchone()[0]

                    si compras > 0:
                        st.error("No se puede eliminar: el proveedor tiene compras asociadas.")
                    demás:
                        conn.execute("ELIMINAR DE proveedores DONDE id=?", (int(prov_actual["id"]),))
                        conexión.commit()
                        st.success("Proveedor eliminado.")
                        st.rerun()

    # =======================================================
    # 🔧 PESTAÑA 5 — AJUSTES
    # =======================================================
    con pestañas[4]:

        st.subheader("🔧 Ajustes del módulo de inventario")
        st.caption("Estos parámetros precargan valores al registrador de compras y ayudan al control de inventario.")

        con conectar() como conexión:
            cfg_inv = pd.read_sql(
                """
                SELECT parámetro, valor
                DESDE configuracion
                DONDE parámetro IN ('inv_alerta_dias', 'inv_impuesto_default', 'inv_delivery_default')
                """,
                conexión
            )

        cfg_map = {row["parámetro"]: float(row["valor"]) for _, row in cfg_inv.iterrows()}

        con st.form("form_ajustes_inventario"):
            alerta_dias = st.number_input(
                "Días para alerta de reposición",
                valor mínimo=1,
                valor máximo=120,
                valor=int(cfg_map.get("inv_alerta_dias", 14)),
                help="Referencia para revisar proveedores y planificar compras preventivas."
            )
            impuesto_default = st.number_input(
                "Impuesto por defecto en compras (%)",
                valor mínimo=0.0,
                valor máximo=100.0,
                valor=flotante(cfg_map.get("inv_impuesto_default", 16.0)),
                formato="%.2f"
            )
            entrega_predeterminada = st.number_input(
                "Entrega por defecto por compra ($)",
                valor mínimo=0.0,
                valor=flotante(cfg_map.get("inv_delivery_default", 0.0)),
                formato="%.2f"
            )

            guardar_ajustes = st.form_submit_button("💾 Guardar ajustes", use_container_width=True)

        si guardar_ajustes:
            con conectar() como conexión:
                ajustes = [
                    ("inv_alerta_dias", flotante(alerta_dias)),
                    ("inv_impuesto_default", float(impuesto_default)),
                    ("inv_entrega_predeterminado", float(entrega_predeterminado))
                ]
                para parámetro, valor en ajustes:
                    conn.execute(
                        "INSERTAR O REEMPLAZAR EN configuración (parámetro, valor) VALORES (?, ?)",
                        (parámetro, valor)
                    )
                conexión.commit()

            st.session_state["inv_alerta_dias"] = float(alerta_dias)
            st.session_state["inv_impuesto_default"] = float(impuesto_default)
            st.session_state["inv_delivery_default"] = float(delivery_default)
            st.success("Ajustes de inventario actualizados.")

        c1, c2, c3 = st.columns(3)
        c1.metric("⏱️ Alerta reposición", f"{int(cfg_map.get('inv_alerta_dias', 14))} días")
        c2.metric("🛡️ Impuesto impuesto", f"{cfg_map.get('inv_impuesto_default', 16.0):.2f}%")
        c3.metric("🚚 Entrega sugerida", f"${cfg_map.get('inv_delivery_default', 0.0):.2f}")

# --- configuración --- #
menú elif == "⚙️ Configuración":

    # --- SEGURIDAD DE ACCESO ---
    si ROL no está en ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden cambiar tasas y costos.")
        st.stop()

    st.title("⚙️ Configuración del Sistema")
    st.info("💡 Estos efectos valores globalmente a cotizaciones, inventario y reportes financieros.")

    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    # --- CARGA SEGURA DE CONFIGURACIÓN ---
    intentar:
        con conectar() como conexión:
            conf_df = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')
    excepto Excepción como e:
        st.error(f"Error al cargar configuración: {e}")
        st.stop()

    # Función auxiliar para obtener valores seguros
    def get_conf(clave, predeterminado):
        intentar:
            devuelve float(conf_df.loc[clave, 'valor'])
        excepto Excepción:
            devolver el valor predeterminado

    costo_tinta_detectado = Ninguno
    intentar:
        con conectar() como conexión:
            df_tintas_cfg = pd.read_sql(
                """
                SELECCIONAR artículo, precio_usd
                DESDE inventario
                DONDE el artículo COMO '%tinta%' Y precio_usd NO ES NULO
                """,
                conexión
            )
        si no df_tintas_cfg.empty:
            df_tintas_cfg = df_tintas_cfg[df_tintas_cfg['precio_usd'] > 0]
            si no df_tintas_cfg.empty:
                costo_tinta_detectado = float(df_tintas_cfg['precio_usd'].mean())
    excepto Excepción:
        costo_tinta_detectado = Ninguno

    con st.form("config_general"):

        st.subheader("💵 Tasas de Cambio (Actualización Diaria)")
        c1, c2 = st.columns(2)

        nueva_bcv = c1.número_entrada(
            "Tasa BCV (Bs/$)",
            valor=get_conf('tasa_bcv', 36.5),
            formato="%.2f",
            help="Usada para pagos en bolívares de cuentas nacionales."
        )

        nueva_bin = c2.número_entrada(
            "Taza Binance (Bs/$)",
            valor=get_conf('tasa_binance', 38.0),
            formato="%.2f",
            help="Usada para pagos mediante USDT o mercado paralelo."
        )

        st.divider()

        st.subheader("🎨 Costos Operativos Base")

        costo_tinta_auto = st.casilla(
            "Calcular costo de tinta automáticamente desde Inventario",
            valor=bool(get_conf('costo_tinta_auto', 1.0))
        )

        si costo_tinta_auto:
            si costo_tinta_detectado no es Ninguno:
                costo_tinta = float(costo_tinta_detectado)
                st.success(f"💧 Costo detectado desde inventario: ${costo_tinta:.4f}/ml")
            demás:
                costo_tinta = float(get_conf('costo_tinta_ml', 0.10))
                st.warning("No se detectaron tintas válidas en inventario; se mantendrá el último costo guardado.")
        demás:
            costo_tinta = st.número_entrada(
                "Costo de Tinta por ml ($)",
                valor=get_conf('costo_tinta_ml', 0.10),
                formato="%.4f",
                paso=0.0001
            )

        st.divider()

        st.subheader("🛡️ Impuestos y Comisiones")
        st.caption("Define los porcentajes numéricos (Ej: 16 para 16%)")

        c3, c4, c5 = st.columns(3)

        n_iva = c3.número_entrada(
            "IVA (%)",
            valor=get_conf('iva_perc', 16.0),
            formato="%.2f"
        )

        n_igtf = c4.número_entrada(
            "IGTF (%)",
            valor=get_conf('igtf_perc', 3.0),
            formato="%.2f"
        )

        n_banco = c5.número_entrada(
            "Comisión Bancaria (%)",
            valor=get_conf('banco_perc', 0.5),
            formato="%.3f"
        )

        st.divider()

        # --- GUARDADO CON HISTORIAL ---
        if st.form_submit_button("💾 GUARDAR CAMBIOS ATÓMICOS", use_container_width=True):

            Actualizaciones = [
                ('tasa_bcv', nueva_bcv),
                ('tasa_binance', nueva_bin),
                ('costo_tinta_ml', costo_tinta),
                ('costo_tinta_auto', 1.0 si costo_tinta_auto otro 0.0),
                ('iva_perc', n_iva),
                ('igtf_perc', n_igtf),
                ('banco_perc', n_banco)
            ]

            intentar:
                con conectar() como conexión:
                    cur = conn.cursor()

                    # Crear tabla de historial si no existe
                    cur.execute("""
                        CREAR TABLA SI NO EXISTE historial_config (
                            id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                            parámetro TEXTO,
                            valor_anterior REAL,
                            valor_nuevo REAL,
                            usuario TEXTO,
                            fecha FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
                        )
                    """)

                    # Guardar cambios y registrador histórico
                    para param, val en actualizaciones:

                        intentar:
                            val_anterior = float(conf_df.loc[param, 'valor'])
                        excepto Excepción:
                            val_anterior = Ninguno

                        cur.ejecutar(
                            "ACTUALIZAR configuracion SET valor = ? DONDE parametro = ?",
                            (valor, parámetro)
                        )

                        si val_anterior != val:
                            cur.execute("""
                                INSERTAR EN historial_config
                                (parámetro, valor_anterior, valor_nuevo, usuario)
                                VALORES (?,?,?,?)
                            """, (param, val_anterior, val, usuario_actual))

                    conexión.commit()

                # Actualización inmediata en memoria
                st.session_state.tasa_bcv = nueva_bcv
                st.session_state.tasa_binance = nueva_bin
                st.session_state.costo_tinta_ml = costo_tinta
                st.session_state.costo_tinta_auto = 1.0 si costo_tinta_auto otro 0.0
                st.session_state.iva_perc = n_iva
                st.session_state.igtf_perc = n_igtf
                st.session_state.banco_perc = n_banco

                st.success("✅ ¡Configuración actualizada y registrada en historial!")
                globos de San Valentín()
                st.rerun()

            excepto Excepción como e:
                st.error(f"❌ Error al guardar: {e}")

    # --- VISUALIZAR HISTORIAL DE CAMBIOS ---
    con st.expander("📜 Ver Historial de Cambios"):

        intentar:
            con conectar() como conexión:
                df_hist = pd.read_sql("""
                    SELECCIONAR fecha, parámetro, valor_anterior, valor_nuevo, usuario
                    DESDE historial_config
                    ORDENAR POR fecha DESC
                    LÍMITE 50
                """, conexión)

            si no df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            demás:
                st.info("Aún no hay cambios registrados.")

        excepto Excepción:
            st.info("Historial aún no disponible.")


# --- 8. MÓDULO PROFESIONAL DE CLIENTES (VERSIÓN 2.0 MEJORADA) ---
menú elif == "👥 Clientes":

    st.title("👥 Gestión Integral de Clientes")
    st.caption("Directorio inteligente con análisis comercial y control de deudas")

    # --- CARGA SEGURA DE DATOS ---
    intentar:
        con conectar() como conexión:
            df_clientes = pd.read_sql("SELECT * FROM clientes", conn)
            df_ventas = pd.read_sql("SELECT cliente_id, cliente, monto_total, metodo, fecha FROM ventas", conn)
    excepto Excepción como e:
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
    con st.expander("➕ Registrar / Editar Cliente"):

        modo = st.radio("Acción:", ["Registrar Nuevo", "Editar Existente"], horizontal=True)

        si modo == "Registrar Nuevo":

            con st.form("form_nuevo_cliente"):

                col1, col2 = st.columns(2)

                nombre_cli = col1.text_input("Nombre del Cliente o Negocio").strip()
                whatsapp_cli = col2.text_input("WhatsApp").strip()

                si st.form_submit_button("✅ Guardar Cliente"):

                    si no nombre_cli:
                        st.error("⚠️ El nombre es obligatorio.")
                        st.stop()

                    wa_limpio = "".join(filter(str.isdigit, whatsapp_cli))

                    si whatsapp_cli y len(wa_limpio) < 10:
                        st.error("⚠️ Número de WhatsApp inválido.")
                        st.stop()

                    intentar:
                        con conectar() como conexión:

                            existe = conn.execute(
                                "SELECT COUNT(*) FROM clientes WHERE lower(nombre) = ?",
                                (nombre_cli.lower(),)
                            ).fetchone()[0]

                            si existe:
                                st.error("⚠️ Ya existe un cliente con ese nombre.")
                            demás:
                                conn.execute(
                                    "INSERTAR EN clientes (nombre, whatsapp) VALORES (?,?)",
                                    (nombre_cli, wa_limpio)
                                )
                                conexión.commit()

                                st.success(f"✅ Cliente '{nombre_cli}' registrado correctamente.")
                                cargar_datos()
                                st.rerun()

                    excepto Excepción como e:
                        st.error(f"Error al guardar: {e}")

        demás:
            # --- EDICIÓN DE CLIENTE ---
            si df_clientes.empty:
                st.info("No hay clientes para editar.")
            demás:
                cliente_sel = st.selectbox(
                    "Seleccionar Cliente:",
                    df_clientes['nombre'].tolist()
                )

                datos = df_clientes[df_clientes['nombre'] == cliente_sel].iloc[0]

                con st.form("form_editar_cliente"):

                    col1, col2 = st.columns(2)

                    nuevo_nombre = col1.text_input("Nombre", valor=datos['nombre'])
                    nuevo_wa = col2.text_input("WhatsApp", valor=datos['whatsapp'])

                    si st.form_submit_button("💾 Actualizar Cliente"):

                        wa_limpio = "".join(filtro(str.isdigit, nuevo_wa))

                        intentar:
                            con conectar() como conexión:
                                conn.execute("""
                                    ACTUALIZACIÓN clientes
                                    ESTABLECER nombre = ?, whatsapp = ?
                                    DONDE id = ?
                                """, (nuevo_nombre, wa_limpio, int(datos['id'])))

                                conexión.commit()

                            st.success("✅ Cliente actualizado.")
                            cargar_datos()
                            st.rerun()

                        excepto Excepción como e:
                            st.error(f"Error al actualizar: {e}")

    st.divider()

    # --- ANÁLISIS COMERCIAL ---
    si df_clientes.empty:
        st.info("No hay clientes para analizar.")
    demás:
        st.write("Módulo de análisis comercial activo.")

    resumen = []

    para _, cli en df_clientes.iterrows():

        compras = df_ventas[df_ventas['cliente_id'] == cli['id']]

        total_comprado = compras['monto_total'].sum() si no compras.empty else 0

        deudas = compras[
            compras['metodo'].str.contains("Pendiente|Deuda", case=False, na=False)
        ]['monto_total'].sum() si no compras.empty de lo contrario 0

        ultima_compra = Ninguno
        si no compras.empty y 'fecha' en compras.columns:
            fechas_validas = pd.to_datetime(compras['fecha'], errores='coerce').dropna()
            si no fechas_validas.empty:
                ultima_compra = fechas_validas.max().strftime('%Y-%m-%d')

        resumen.append({
            "id": cli['id'],
            "nombre": cli['nombre'],
            "Whatsapp": cli['Whatsapp'],
            "total_comprado": total_comprado,
            "deudas": deudas,
            "operaciones": len(compras),
            "ultima_compra": ultima_compra o "Sin compras"
        })

    df_resumen = pd.DataFrame(resumen)

    # --- FILTROS ---
    si buscada:
        df_resumen = df_resumen[
            df_resumen['nombre'].str.contains(busqueda, case=False, na=False) |
            df_resumen['whatsapp'].str.contains(busqueda, case=False, na=False)
        ]

    si filtro_deudores:
        df_resumen = df_resumen[df_resumen['deudas'] > 0]

    # --- DASHBOARD DE CLIENTES ---
    si no df_resumen.empty:

        st.subheader("📊 Resumen Comercial")

        ticket_promedio = (df_resumen['total_comprado'].sum() / df_resumen['operaciones'].sum()) if df_resumen['operaciones'].sum() > 0 else 0
        mayor_deudor = df_resumen.sort_values('deudas', ascendente=False).iloc[0]

        m1, m2, m3, m4 = st.columns(4)

        m1.metric("Clientes Totales", len(df_resumen))
        m2.metric("Ventas Totales", f"$ {df_resumen['total_comprado'].sum():,.2f}")
        m3.metric("Cuentas por Cobrar", f"$ {df_resumen['deudas'].sum():,.2f}")
        m4.metric("Boleto Promedio", f"$ {boleto_promedio:,.2f}")

        st.caption(f"Alcalde deudor actual: {mayor_deudor['nombre']} (${mayor_deudor['deudas']:,.2f})")

        st.divider()

        ctop, cgraf = st.columns([1, 2])
        con ctop:
            st.subheader("🏆 Principales clientes")
            top = df_resumen.sort_values("total_comprado", ascendente=Falso).head(5)
            st.dataframe(
                top[['nombre', 'total_comprado', 'operaciones']],
                configuración_de_columna={
                    'nombre': 'Cliente',
                    'total_comprado': st.column_config.NumberColumn('Comprado ($)', format='%.2f'),
                    'operaciones': 'Operaciones'
                },
                use_container_width=Verdadero,
                hide_index=Verdadero
            )

        con cgraf:
            st.subheader("📈 Facturación por cliente")
            top10 = df_resumen.sort_values("total_comprado", ascendente=Falso).head(10)
            fig_top = px.bar(top10, x='nombre', y='total_comprado')
            fig_top.update_layout(xaxis_title='Cliente', yaxis_title='Comprado ($)')
            st.plotly_chart(fig_top, usar_ancho_del_contenedor=Verdadero)

        st.divider()

        st.subheader(f"📋 Directorio ({len(df_resumen)} clientes)")

        # --- EXPORTACIÓN ---
        búfer = io.BytesIO()
        con pd.ExcelWriter(buffer, engine='xlsxwriter') como escritor:
            df_resumen.to_excel(escritor, índice=False, nombre_hoja='Clientes')

        botón_descargar(
            "📥 Descargar Lista de Clientes (Excel)",
            datos=buffer.getvalue(),
            file_name="clientes_imperio.xlsx",
            mime="aplicación/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.dataframe(
            df_resumen.sort_values(['deudas', 'total_comprado'], ascending=[False, False]),
            configuración_de_columna={
                'id': Ninguno,
                'nombre': 'Cliente',
                'WhatsApp': 'WhatsApp',
                'total_comprado': st.column_config.NumberColumn('Total Comprado ($)', format='%.2f'),
                'deudas': st.column_config.NumberColumn('Deudas ($)', formato='%.2f'),
                'operaciones': 'Operaciones',
                'ultima_compra': 'Última compra'
            },
            use_container_width=Verdadero,
            hide_index=Verdadero
        )

        with st.expander("⚙️ Acciones rápidas por cliente"):
            cliente_accion = st.selectbox("Selecciona cliente", df_resumen['nombre'].tolist(), key='cli_accion')
            cli_row = df_resumen[df_resumen['nombre'] == cliente_accion].iloc[0]
            a1, a2 = st.columns(2)
            si cli_row['whatsapp']:
                wa_num = str(cli_row['whatsapp'])
                si no wa_num.startswith('58'):
                    wa_num = '58' + wa_num.lstrip('0')
                a1.link_button("💬 Abrir chat de WhatsApp", f"https://wa.me/{wa_num}")
            demás:
                a1.info("Cliente sin número de WhatsApp")

            if a2.button("🗑 Eliminar cliente", type='secondary'):
                con conectar() como conexión:
                    tiene_ventas = conn.execute("SELECT COUNT(*) FROM ventas WHERE cliente_id = ?", (int(cli_row['id']),)).fetchone()[0]
                    si tiene_ventas > 0:
                        st.error("No se puede eliminar: el cliente tiene ventas asociadas.")
                    demás:
                        conn.execute("ELIMINAR DE clientes DONDE id = ?", (int(cli_row['id']),))
                        conexión.commit()
                        st.success("Cliente eliminado correctamente.")
                        cargar_datos()
                        st.rerun()


    demás:
        st.info("No hay clientes que coincidan con los filtros.")




# ===========================================================
# 10. ANALIZADOR CMYK PROFESIONAL (VERSIÓN MEJORADA 2.0)
# ===========================================================
menú elif == "🎨 Análisis CMYK":

    st.title("🎨 Analizador Profesional de Cobertura CMYK")

    # --- CARGA SEGURA DE DATOS ---
    intentar:
        con conectar() como conexión:

            # Usamos el inventario como fuente de tintas
            df_tintas_db = pd.read_sql_query(
                "SELECT * FROM inventario", conexión
            )
            si 'imprimible_cmyk' en df_tintas_db.columns:
                df_impresion_db = df_tintas_db[df_tintas_db['imprimible_cmyk'].fillna(0) == 1].copy()
            demás:
                df_impresion_db = df_tintas_db.copy()
            intentar:
                df_activos_cmyk = pd.read_sql_query(
                    "SELECT equipo, categoria, unidad FROM activos", conexión
                )
            excepto Excepción:
                df_activos_cmyk = pd.DataFrame(columns=['equipo', 'categoria', 'unidad'])

            # Tabla histórica
            conn.execute("""
                CREAR TABLA SI NO EXISTE historial_cmyk (
                    id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                    impresora TEXTO,
                    paginas ENTERO,
                    costo REAL,
                    fecha FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
                )
            """)
            df_hist_cmyk = pd.read_sql(
                "SELECT fecha, impresora, paginas, costo FROM historial_cmyk ORDER BY fecha DESC LIMIT 100",
                conexión
            )

    excepto Excepción como e:
        st.error(f"Error al cargar datos: {e}")
        st.stop()

    # --- LISTA DE IMPRESORAS DISPONIBLES ---
    impresoras_disponibles = []

    # 1) Prioridad: Activos en Maquinaria categoría Tinta (como indicaste)
    si 'df_activos_cmyk' está en locals() y no en df_activos_cmyk.empty:
        acto = df_activos_cmyk.copy()
        mask_maquinaria = act['unidad'].fillna('').str.contains('Maquinaria', case=False, na=False)
        # Acepta tanta categoría Tinta como Impresión/Impresora para compatibilidad
        mask_categoria_imp = act['categoria'].fillna('').str.contains('Tinta|Impres', case=False, na=False)
        mask_equipo_imp = act['equipo'].fillna('').str.contains('Impres', case=False, na=False)
        posibles_activos = act[mask_maquinaria & (mask_categoria_imp | mask_equipo_imp)]['equipo'].dropna().astype(str).tolist()
        para eq en posibles_activos:
            nombre_limpio = eq
            si '] ' en nombre_limpio:
                nombre_limpio = nombre_limpio.split('] ', 1)[1]
            si nombre_limpio no está en impresoras_disponibles:
                impresoras_disponibles.append(nombre_limpio)

    # 2) Respaldo: equipos con palabra impresora en inventario
    si no df_impresion_db.empty:
        posibles = df_impresion_db[
            df_impresion_db['item'].str.contains("impresora", case=False, na=False)
        ]['elemento'].tolist()

        para p en posibles:
            si p no está en impresoras_disponibles:
                impresoras_disponibles.append(p)

    # 3) Último respaldo por defecto
    si no impresoras_disponibles:
        impresoras_disponibles = ["Impresora Principal", "Impresora Secundaria"]

    # --- VALIDACIÓN ---
    si no impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en el sistema.")
        st.stop()

    # --- SELECCIÓN DE IMPRESORA Y ARCHIVOS ---
    c_impresora, c_archivo = st.columns([1, 2])

    con c_printer:

        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)

        impresora_aliases = [impresora_sel.lower().strip()]
        si ' ' en impresora_aliases[0]:
            impresora_aliases.extend([x para x en impresora_aliases[0].split(' ') si len(x) > 2])

        usar_stock_por_impresora = st.checkbox(
            "Usar tintas del inventario solo de esta impresora",
            valor=Verdadero,
            help="Actívalo si registras tintas separadas por impresora en inventario."
        )
        auto_negro_inteligente = st.checkbox(
            "Conteo automático inteligente de negro (sombras y mezclas)",
            valor=Verdadero,
            help="Detecta zonas oscuras y mezclas ricas para sumar consumo real de tinta negra (K)."
        )

        costo_desgaste = st.number_input(
            "Costo desgaste por página ($)",
            valor mínimo=0.0,
            valor=0.02,
            paso=0,005,
            formato="%.3f"
        )
        ml_base_pagina = st.number_input(
            "Consumo base por página a cobertura 100% (ml)",
            valor mínimo=0,01,
            valor=0,15,
            paso=0,01,
            formato="%.3f"
        )

        precio_tinta_ml = st.session_state.get('costo_tinta_ml', 0.10)

        si no df_impresion_db.empty:
            máscara = df_impresion_db['item'].str.contains("tinta", case=False, na=False)
            tintas = df_impresion_db[máscara]

            si usar_stock_por_impresora y no tintas.empty:
                tintas_imp = tintas[tintas['item'].fillna('').str.contains('|'.join(impresora_aliases), case=False, na=False)]
                si no tintas_imp.empty:
                    tintas = tintas_imp
                demás:
                    st.info("No se encontraron tintas asociadas a esta impresora; se usará promedio global de tintas.")

            si no tintas.vacío:
                precio_tinta_ml = tintas['precio_usd'].mean()
                st.success(f"💧 Precio de tinta detectado: ${precio_tinta_ml:.4f}/ml")

        st.subheader("⚙️ Ajustes de Calibración")

        factor = st.slider(
            "Factor General de Consumo",
            1.0, 3.0, 1.5, 0.1,
            help="Ajuste global según el rendimiento real de la impresora"
        )

        factor_k = 0.8
        refuerzo_negro = 0.06
        si auto_negro_inteligente:
            st.success("🧠 Modo automático de negro activo: se detectan sombras y mezclas con negro en cada página.")
        demás:
            factor_k = st.slider(
                "Factor Especial para Negro (K)",
                0,5, 1,2, 0,8, 0,05,
                help="Modo manual: ajusta consumo base del negro."
            )
            refuerzo_negro = st.slider(
                "Refuerzo de Negro en Mezclas Oscuras",
                0.0, 0.2, 0.06, 0.01,
                help="Modo manual: simula uso extra de K en sombras."
            )

    con c_file:
        archivos_multiples = st.file_uploader(
            "Carga tus diseños",
            tipo=['pdf', 'png', 'jpg', 'jpeg'],
            aceptar_múltiples_archivos=Verdadero
        )

    si no archivos_multiples y 'cmyk_analisis_cache' en st.session_state:
        st.session_state.pop('cmyk_analisis_cache', Ninguno)

    # --- PROCESAMIENTO ---
    si archivos_multiples:

        intentar:
            importar fitz # PyMuPDF (opcional para PDF)
        excepto ModuleNotFoundError:
            fitz = Ninguno

        resultados = []
        totales_lote_cmyk = {'C': 0.0, 'M': 0.0, 'Y': 0.0, 'K': 0.0}
        total_pags = 0

        with st.spinner('🚀 Analizando cobertura real...'):

            para arco en archivos_multiples:

                intentar:
                    paginas_items = []
                    bytes_datos = arc.read()

                    si arc.name.lower().termina con('.pdf'):

                        Si fitz es Ninguno:
                            st.error(
                                f"No se puede analizar '{arc.name}' porque falta PyMuPDF (fitz). "
                                "Carga imágenes (PNG/JPG) o instala la dependencia para PDF".
                            )
                            continuar

                        doc = fitz.open(stream=bytes_data, tipo de archivo="pdf")

                        para i en rango(len(doc)):
                            página = doc.load_page(i)

                            pix = página.get_pixmap(colorspace=fitz.csCMYK, ppp=150)

                            img = Imagen.frombytes(
                                "CMYK",
                                [pix.ancho, pix.alto],
                                muestras de píxeles
                            )

                            paginas_items.append((f"{arc.name} (P{i+1})", img))

                        doc.close()

                    demás:
                        img = Imagen.open(io.BytesIO(bytes_data)).convert('CMYK')
                        paginas_items.append((arc.nombre, img))

                    para nombre, img_obj en paginas_items:

                        total_pags += 1
                        arr = np.array(img_obj)

                        c_chan = arr[:, :, 0] / 255.0
                        m_chan = arr[:, :, 1] / 255.0
                        y_chan = arr[:, :, 2] / 255.0
                        k_chan = arr[:, :, 3] / 255.0

                        c_media = float(np.mean(c_chan))
                        m_media = float(np.mean(m_chan))
                        y_media = float(np.mean(y_chan))
                        k_media = float(np.mean(k_chan))

                        ml_c = c_media * ml_base_pagina * factor
                        ml_m = m_media * ml_base_pagina * factor
                        ml_y = y_media * ml_base_pagina * factor

                        ml_k_base = k_media * ml_base_pagina * factor * factor_k
                        k_ml_extra = 0.0

                        si auto_negro_inteligente:
                            cobertura_cmy = (c_chan + m_chan + y_chan) / 3.0
                            máscara neutral = (
                                (np.abs(c_chan - m_chan) < 0,08)
                                & (np.abs(m_chan - y_chan) < 0.08)
                            )
                            máscara_sombra = (k_chan > 0,45) | (cobertura_cmy > 0,60)
                            máscara_negra_rica = máscara_sombra & (cobertura_cmy > 0.35)

                            proporción_extra = (
                                float(np.mean(máscara_de_sombra)) * 0.12
                                + float(np.mean(máscara_neutral)) * 0.10
                                + float(np.mean(máscara_negra_rica)) * 0.18
                            )
                            k_extra_ml = ml_base_pagina * factor * ratio_extra
                        demás:
                            color_promedio = (c_media + m_media + y_media) / 3
                            si promedio_color > 0.55:
                                k_extra_ml = promedio_color * refuerzo_negro * factor

                        ml_k = ml_k_base + k_extra_ml
                        consumo_total_f = ml_c + ml_m + ml_y + ml_k

                        costo_f = (consumo_total_f * precio_tinta_ml) + costo_desgaste

                        totales_lote_cmyk['C'] += ml_c
                        totales_lote_cmyk['M'] += ml_m
                        totales_lote_cmyk['Y'] += ml_y
                        totales_lote_cmyk['K'] += ml_k

                        resultados.append({
                            "Archivo": nombre,
                            "C (ml)": redondear(ml_c, 4),
                            "M (ml)": redondo(ml_m, 4),
                            "Y (ml)": round(ml_y, 4),
                            "K (ml)": redondear(ml_k, 4),
                            "K extra automático (ml)": round(k_extra_ml, 4),
                            "Total ml": round(consumo_total_f, 4),
                            "Costo $": round(costo_f, 4)
                        })

                excepto Excepción como e:
                    st.error(f"Error al analizar {arc.name}: {e}")

        # --- RESULTADOS ---
        si resultados:

            st.subheader("📋 Desglose por Archivo")
            st.dataframe(pd.DataFrame(resultados), use_container_width=True)

            st.subheader("🧪 Consumo Total de Tintas")

            col_c, col_m, col_y, col_k = st.columns(4)

            col_c.metric("Cian", f"{totales_lote_cmyk['C']:.3f} ml")
            col_m.metric("Magenta", f"{totales_lote_cmyk['M']:.3f} ml")
            col_y.metric("Amarillo", f"{totales_lote_cmyk['Y']:.3f} ml")
            col_k.metric("Negro", f"{totales_lote_cmyk['K']:.3f} ml")

            st.divider()

            total_usd_lote = suma(r['Costo $'] para r en resultados)

            costo_promedio_pagina = (total_usd_lote / total_pags) si total_pags > 0 sino 0
            st.metric(
                "💰 Costo Total Estimado de Producción",
                f"$ {lote_total_usd:.2f}",
                delta=f"$ {costo_promedio_pagina:.4f} por página"
            )

            df_totales = pd.DataFrame([
                {"Color": "C", "ml": totales_lote_cmyk['C']},
                {"Color": "M", "ml": totales_lote_cmyk['M']},
                {"Color": "Y", "ml": totales_lote_cmyk['Y']},
                {"Color": "K", "ml": totales_lote_cmyk['K']}
            ])
            fig_cmyk = px.pie(df_totales, nombres='Color', valores='ml', title='Distribución de consumo CMYK')
            st.plotly_chart(fig_cmyk, use_container_width=True)

            df_resultados = pd.DataFrame(resultados)
            botón_descargar(
                "📥Descargar desglose CMYK (CSV)",
                datos=df_resultados.to_csv(index=False).encode('utf-8'),
                nombre_de_archivo="analisis_cmyk.csv",
                mime="texto/csv"
            )

            # --- COSTEO AUTOMÁTICO POR PAPEL Y CALIDAD ---
            st.subheader("🧾 Simulación automática por Papel y Calidad")
            # Papeles desde inventario (precio_usd) con fallback por defecto
            perfiles_papel = {}
            intentar:
                papeles_inv = df_impresion_db[
                    df_impresion_db['item'].fillna('').str.contains(
                        'papel|bond|fotograf|cartulina|adhesivo|opalina|sulfato',
                        caso=Falso,
                        na=Falso
                    )
                ][['item', 'precio_usd']].dropna(subset=['precio_usd'])

                para _, fila_p en papeles_inv.iterrows():
                    nombre_p = str(fila_p['elemento']).strip()
                    precio_p = float(row_p['precio_usd'])
                    si precio_p > 0:
                        perfiles_papel[nombre_p] = precio_p
            excepto Excepción:
                perfiles_papel = {}

            si no perfiles_papel:
                perfiles_papel = {
                    "Bond 75g": 0,03,
                    "Bond 90g": 0,05,
                    "Fotográfico Brillante": 0,22,
                    "Fotográfico Mate": 0.20,
                    "Cartulina": 0,12,
                    "Adhesivo": 0,16
                }
                st.info("No se detectaron papeles en inventario; se usan costos base por defecto.")
            demás:
                st.success("📄 Costos de papeles detectados automáticamente desde inventario.")
            perfiles_calidad = {
                "Borrador": {"ink_mult": 0.82, "wear_mult": 0.90},
                "Normal": {"multiplicación de tinta": 1.00, "multiplicación de desgaste": 1.00},
                "Alta": {"ink_mult": 1.18, "wear_mult": 1.10},
                "Foto": {"multiplicación de tinta": 1.32, "multiplicación de ropa": 1.15}
            }

            total_ml_lote = float(suma(totales_lote_cmyk.values()))
            costo_tinta_base = total_ml_lote * float(precio_tinta_ml)
            costo_desgaste_base = float(costo_desgaste) * float(total_pags)

            simulaciones = []
            para papel, costo_hoja en perfiles_papel.items():
                para calidad, cfg_q en perfiles_calidad.items():
                    costo_tinta_q = costo_tinta_base * cfg_q['ink_mult']
                    costo_desgaste_q = costo_desgaste_base * cfg_q['wear_mult']
                    costo_papel_q = float(total_pags) * costo_hoja
                    total_q = costo_tinta_q + costo_desgaste_q + costo_papel_q
                    simulaciones.append({
                        "Papel": papel,
                        "Calidad": calidad,
                        "Páginas": total_pags,
                        "Tinta ($)": ronda(costo_tinta_q, 2),
                        "Desgaste ($)": round(costo_desgaste_q, 2),
                        "Papel ($)": redondo(costo_papel_q, 2),
                        "Total ($)": round(total_q, 2),
                        "Costo por página ($)": round(total_q / total_pags, 4) if total_pags else 0
                    })

            df_sim = pd.DataFrame(simulaciones).sort_values('Total ($)')
            st.dataframe(df_sim, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)
            fig_sim = px.bar(df_sim.head(12), x='Papel', y='Total ($)', color='Calidad', barmode='group', title='Comparativo de costos (top 12 más económicos)')
            st.plotly_chart(fig_sim, usar_ancho_del_contenedor=Verdadero)

            mejor = df_sim.iloc[0]
            st.éxito(
                f"Mejor costo automático: {mejor['Papel']} | {mejor['Calidad']} → ${mejor['Total ($)']:.2f} "
                f"(${mejor['Costo por página ($)']:.4f}/pág)"
            )

            st.session_state['cmyk_analisis_cache'] = {
                'resultados': resultados,
                'simulaciones': simulaciones,
                'impresora': impresora_sel,
                'páginas': total_pags
            }

            # --- VERIFICAR INVENTARIO ---
            si no df_impresion_db.empty:

                st.subheader("📦 Verificación de Inventario")

                alertas = []

                stock_base = df_impresion_db[df_impresion_db['item'].str.contains('tinta', case=False, na=False)].copy()
                si usar_stock_por_impresora:
                    stock_imp = stock_base[stock_base['item'].fillna('').str.contains('|'.join(impresora_aliases), case=False, na=False)]
                    si no stock_imp.empty:
                        base_de_stock = imp_de_stock

                alias_colores = {
                    'C': ['cian', 'cian'],
                    'M': ['magenta'],
                    'Y': ['amarillo', 'yellow'],
                    #K=Negro. Incluye variantes reales de inventario: negro/negro/black/k
                    'K': ['negro', 'negra', 'black', 'k']
                }

                para color, ml en totales_lote_cmyk.items():
                    alias = alias_colores.get(color, [])
                    stock = stock_base[(" " + stock_base['item'].fillna('').str.lower() + " " ).str.contains('|'.join(aliases), case=False, na=False)] if alias else pd.DataFrame()

                    si no está en stock.vacío:
                        disponible = stock['cantidad'].sum()

                        si disponible < ml:
                            alertas.append(
                                f"⚠️ Falta tinta {color}: necesitas {ml:.2f} ml y hay {disponible:.2f} ml"
                            )
                    demás:
                        alertas.append(f"⚠️ No se encontró tinta {color} asociada en inventario para validar stock.")

                si alertas:
                    para una en alertas:
                        st.error(a)
                demás:
                    st.success("Hay suficiente tinta para producir")


                       # --- ENVÍO A COTIZACIÓN ---
            if st.button("📝 ENVIAR A COTIZACIÓN", use_container_width=True):

                # Guardamos información completa para el cotizador
                st.session_state['datos_pre_cotización'] = {
                    'trabajo': f"Impresión {impresora_sel} ({total_pags} pgs)",
                    'costo_base': float(df_sim.iloc[0]['Total ($)']) si no df_sim.empty de lo contrario float(total_usd_lote),
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

                intentar:
                    con conectar() como conexión:
                        conn.execute("""
                            INSERTAR EN historial_cmyk
                            (impresora, paginas, costo)
                            VALORES (?,?,?)
                        """, (impresora_sel, total_pags, total_usd_lote))
                        conexión.commit()
                excepto Excepción como e:
                    st.warning(f"No se pudo guardar en historial: {e}")

                st.success("✅ Datos enviados correctamente al módulo de Cotizaciones")
                st.toast("Listo para cotizar", icon="📨")

                st.rerun()


    st.divider()
    st.subheader("🕘 Historial reciente CMYK")
    si df_hist_cmyk.empty:
        st.info("Aún no hay análisis guardados en el historial.")
    demás:
        df_hist_view = df_hist_cmyk.copy()
        df_hist_view['fecha'] = pd.to_datetime(df_hist_view['fecha'], errors='coerce')
        st.dataframe(df_hist_view, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)

        hist_ordenado = df_hist_view.dropna(subset=['fecha']).copy()
        si no hist_ordenado.empty:
            hist_ordenado['dia'] = hist_ordenado['fecha'].dt.date.astype(str)
            hist_dia = hist_ordenado.groupby('dia', as_index=False)['costo'].sum()
            fig_hist = px.line(hist_dia, x='dia', y='costo', marcadores=True, title='Costo CMYK por día (historial)')
            fig_hist.update_layout(xaxis_title='Día', yaxis_title='Costo ($)')
            st.plotly_chart(fig_hist, use_container_width=True)


# --- 9. MÓDULO PROFESIONAL DE ACTIVOS ---
menú elif == "🏗️ Activos":

    si ROL != "Admin":
        st.error("🚫 Acceso Denegado. Solo Administración puede gestionar activos.")
        st.stop()

    st.title("🏗️ Gestión Integral de Activos")

    # --- CARGA SEGURA DE DATOS ---
    intentar:
        con conectar() como conexión:
            df = pd.read_sql_query("SELECT * FROM activos", conn)

            # Crear tabla de historial si no existe
            conn.execute("""
                CREAR TABLA SI NO EXISTE activos_historial (
                    id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                    activo TEXTO,
                    acción TEXTO,
                    detalle TEXTO,
                    costo REAL,
                    fecha FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
                )
            """)
    excepto Excepción como e:
        st.error(f"Error al cargar activos: {e}")
        st.stop()

    # --- REGISTRO DE NUEVO ACTIVO ---
    con st.expander("➕ Registrador Nuevo Activo"):

        con st.form("form_activos_pro"):

            c1, c2 = st.columns(2)

            nombre_eq = c1.text_input("Nombre del Activo")
            tipo_seccion = c2.selectbox("Tipo de Activo", [
                "Maquinaria (Equipos Grandes)",
                "Manual Herramienta (Uso diario)",
                "Repuesto Crítico (Stock de seguridad)"
            ])

            col_m1, col_m2, col_m3 = st.columns(3)

            monto_inv = col_m1.number_input("Inversión ($)", valor_mínimo=0.0)
            vida_util = col_m2.number_input("Vida Útil (Usos)", min_value=1, value=1000)

            categoria_especifica = col_m3.selectbox(
                "Categoría",
                ["Corte", "Impresión", "Tinta", "Calor", "Mobiliario", "Mantenimiento"]
            )

            if st.form_submit_button("🚀 Guardar Activo"):

                si no nombre_eq:
                    st.error("Debe indicar un nombre.")
                    st.stop()

                si monto_inv <= 0:
                    st.error("La inversión debe ser mayor a cero.")
                    st.stop()

                desgaste_u = monto_inv / vida_util

                intentar:
                    con conectar() como conexión:
                        conn.execute("""
                            INSERTAR EN activos 
                            (equipo, categoría, inversión, unidad, desgaste) 
                            VALORES (?,?,?,?,?)
                        """, (
                            f"[{tipo_seccion[:3].upper()}] {nombre_eq}",
                            categoría_especifica,
                            monto_inv,
                            tipo_seccion,
                            desgaste_u
                        ))

                        conn.execute("""
                            INSERTAR EN activos_historial 
                            (activo, acción, detalle, costo)
                            VALORES (?,?,?,?)
                        """, (nombre_eq, "CREACIÓN", "Registro inicial", monto_inv))

                        conexión.commit()

                    st.success("✅ Activo registrado correctamente.")
                    st.rerun()

                excepto Excepción como e:
                    st.error(f"Error al registrar: {e}")

    st.divider()

    # --- EDICIÓN DE ACTIVOS ---
    con st.expander("✏️ Editar Activo Existente"):

        si df.vacío:
            st.info("No hay activos para editar.")
        demás:
            activo_sel = st.selectbox("Seleccionar activo:", df['equipo'].tolist())

            datos = df[df['equipo'] == activo_sel].iloc[0]

            con st.form("editar_activo"):

                c1, c2, c3 = st.columns(3)

                nueva_inv = c1.number_input("Inversión ($)", valor=float(datos['inversión']))
                nueva_vida = c2.number_input("Vida útil", valor=1000)
                nueva_cat = c3.selectbox(
                    "Categoría",
                    ["Corte", "Impresión", "Tinta", "Calor", "Mobiliario", "Mantenimiento"],
                    índice=0
                )

                si st.form_submit_button("💾 Guardar cambios"):

                    nuevo_desgaste = nueva_inv / nueva_vida

                    intentar:
                        con conectar() como conexión:
                            conn.execute("""
                                ACTUALIZAR activos
                                SET inversión = ?, categoria = ?, desgaste = ?
                                DONDE id = ?
                            """, (nueva_inv, nueva_cat, nuevo_desgaste, int(datos['id'])))

                            conn.execute("""
                                INSERTAR EN activos_historial 
                                (activo, acción, detalle, costo)
                                VALORES (?,?,?,?)
                            """, (activo_sel, "EDICIÓN", "Actualización de valores", nueva_inv))

                            conexión.commit()

                        st.success("Activo actualizado.")
                        st.rerun()

                    excepto Excepción como e:
                        st.error(f"Error al actualizar: {e}")

    st.divider()

    # --- VISUALIZACIÓN POR SECCIONES ---
    t1, t2, t3, t4, t5 = st.tabs([
        "📟 Maquinaria",
        "🛠️ Herramientas",
        "🔄 Repuestos",
        "📊 Resumen Global",
        "📜 Histórico"
    ])

    si no df.empty:

        con t1:
            st.subheader("Equipos y Maquinaria")
            df_maq = df[df['unidad'].str.contains("Maquinaria")]
            st.dataframe(df_maq, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)

        con t2:
            st.subheader("Herramientas Manuales")
            df_her = df[df['unidad'].str.contains("Herramienta")]
            st.dataframe(df_her, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)

        con t3:
            st.subheader("Repuestos Críticos")
            df_rep = df[df['unidad'].str.contains("Repuesto")]
            st.dataframe(df_rep, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)

        con t4:
            c_inv, c_des, c_prom = st.columns(3)

            c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
            c_des.metric("Activos Registrados", len(df))

            promedio = df['desgaste'].mean() si no df.empty si no 0
            c_prom.metric("Desgaste Promedio por Uso", f"$ {promedio:.4f}")

            fig = px.bar(
                df,
                x='equipo',
                y='inversión',
                color='categoría',
                title="Distribución de Inversión por Activo"
            )
            st.plotly_chart(fig, use_container_width=True)

        con t5:
            st.subheader("Historial de Movimientos de Activos")

            intentar:
                con conectar() como conexión:
                    df_hist = pd.read_sql_query(
                        "SELECT activo, acción, detalle, costo, fecha FROM activos_historial ORDER BY fecha DESC",
                        conexión
                    )

                si no df_hist.empty:
                    st.dataframe(df_hist, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)
                demás:
                    st.info("No hay movimientos registrados aún.")

            excepto Excepción como e:
                st.error(f"Error al cargar historial: {e}")

    demás:
        st.info("No hay activos registrados todavía.")


# ===========================================================
# 11. MÓDULO PROFESIONAL DE OTROS PROCESOS
# ===========================================================
elif menu == "🛠️ Otros Procesos":

    st.title("🛠️ Calculadora de Procesos Especiales")
    st.info("Cálculo de costos de procesos que no usan tinta: corte, laminado, planchado, etc.")

    # --- CARGA SEGURA DE EQUIPOS ---
    intentar:
        con conectar() como conexión:
            df_act_db = pd.read_sql_query(
                "SELECT equipo, categoria, unidad, desgaste FROM activos", conn
            )

            conn.execute("""
                CREAR TABLA SI NO EXISTE historial_procesos (
                    id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                    equipo TEXTO,
                    cantidad REAL,
                    costo REAL,
                    fecha FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
                )
            """)

    excepto Excepción como e:
        st.error(f"Error al cargar activos: {e}")
        st.stop()

    # Filtrar solo equipos que NO gastan tinta
    otros_equipos = df_act_db[
        df_act_db['categoria'] != "Impresora (Gasta Tinta)"
    ].to_dict('registros')

    si no otros_equipos:
        st.warning("⚠️ No hay equipos registrados para procesos especiales.")
        st.stop()

    nombres_eq = [e['equipo'] for e en otros_equipos]

    si "lista_procesos" no está en st.session_state:
        st.session_state.lista_procesos = []

    con st.container(border=True):

        c1, c2 = st.columns(2)

        eq_sel = c1.selectbox("Selecciona el Proceso/Equipo:", nombres_eq)

        datos_eq = next(e para e en otros_equipos si e['equipo'] == eq_sel)

        cantidad = c2.number_input(
            f"Cantidad de {datos_eq['unidad']}:",
            valor mínimo=1.0,
            valor=1.0
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
    si st.session_state.lista_procesos:

        st.subheader("📋 Procesos Acumulados")

        df_proc = pd.DataFrame(st.session_state.lista_procesos)
        st.dataframe(df_proc, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)

        total = df_proc["costo"].sum()
        st.metric("Total de procesos", f"$ {total:.2f}")

        col1, col2 = st.columns(2)

        con col1:
            if st.button("📝 Enviar a Cotización", use_container_width=True):

                st.session_state['datos_pre_cotización'] = {
                    'trabajo': " + ".join(df_proc["equipo"].tolist()),
                    'costo_base': float(total),
                    'unidades': 1,
                    'es_proceso_extra': Verdadero
                }

                st.success("Enviado a cotización")
                st.session_state.lista_procesos = []
                st.rerun()

        con col2:
            si st.button("🧹 Limpiar", use_container_width=True):
                st.session_state.lista_procesos = []
                st.rerun()

    # --- HISTÓRICO ---
    con st.expander("📜 Historial de Procesos"):

        intentar:
            con conectar() como conexión:
                df_hist = pd.read_sql_query(
                    "SELECCIONAR * DE historial_procesos ORDENAR POR fecha DESC",
                    conexión
                )

            si no df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            demás:
                st.info("Sin registros aún.")

        excepto Excepción como e:
            st.info("Historial no disponible.")


# ===========================================================
# 12. MÓDULO PROFESIONAL DE VENTAS (VERSIÓN 2.0)
# ===========================================================
menú elif == "💰 Ventas":

    st.title("💰 Gestión Profesional de Ventas")

    pestaña1, pestaña2, pestaña3 = st.tabs([
        "📝 Registrar Venta",
        "📜 Histórico",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE VENTA
    # -----------------------------------
    con pestaña1:

        df_cli = st.session_state.get("df_cli", pd.DataFrame())

        si df_cli.empty:
            st.warning("⚠️ Registra clientes primero.")
            st.stop()

        con st.form("venta_manual", clear_on_submit=True):

            st.subheader("Datos de la Venta")

            opciones_cli = {
                fila['nombre']: fila['id']
                para _, fila en df_cli.iterrows()
            }

            c1, c2 = st.columns(2)

            cliente_nombre = c1.selectbox(
                "Cliente:", lista(opciones_cli.keys())
            )

            detalle_v = c2.text_input(
                "Detalle de lo vendido:",
                placeholder="Ej: 100 volantes, 2 banner..."
            )

            c3, c4, c5 = st.columns(3)

            monto_venta = c3.número_entrada(
                "Monto ($):",
                valor mínimo=0,01,
                formato="%.2f"
            )

            método_pago = c4.selectbox(
                "Método:",
                ["Efectivo ($)", "Pago Móvil (BCV)",
                 "Zelle", "Binance (USDT)",
                 "Transferencia (Bs)", "Pendiente"]
            )

            tasa_uso = t_bcv si "BCV" en metodo_pago else (
                t_bin si "Binance" en metodo_pago de lo contrario 1.0
            )

            monto_bs = monto_venta * tasa_uso

            c5.metric("Bs equivalentes", f"{monto_bs:,.2f}")

            if st.form_submit_button("🚀 Registrar Venta"):

                si no detalle_v.strip():
                    st.error("Debes indicar el detalle de la venta.")
                    st.stop()

                intentar:
                    con conectar() como conexión:

                        conn.execute("""
                            CREAR TABLA SI NO EXISTE ventas_extra (
                                id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                                venta_id ENTERO,
                                tasa REAL,
                                monto_bs REAL
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERTAR EN ventas 
                            (cliente_id, cliente, detalle, monto_total, metodo)
                            VALORES (?, ?, ?, ?, ?)
                        """, (
                            opciones_cli[nombre_del_cliente],
                            cliente_nombre,
                            detalle_v.strip(),
                            float(monto_venta),
                            método_pago
                        ))

                        venta_id = cur.lastrowid

                        cur.execute("""
                            INSERTAR EN ventas_extra
                            (venta_id, tasa, monto_bs)
                            VALORES (?, ?, ?)
                        """, (
                            venta_id,
                            flotar(tasa_uso),
                            flotador(monto_bs)
                        ))

                        conexión.commit()

                    st.success("Venta registrada correctamente")
                    globos de San Valentín()
                    st.rerun()

                excepto Excepción como e:
                    st.error(f"Error: {e}")

    # -----------------------------------
    # HISTÓRICO
    # -----------------------------------
    con tab2:

        st.subheader("Historial de Ventas")

        intentar:
            con conectar() como conexión:
                df_historial = pd.read_sql_query("""
                    SELECCIONAR 
                        v.id,
                        v.fecha,
                        v.cliente,
                        v.detalle,
                        v.monto_total como total,
                        v.método,
                        e.tasa,
                        e.monto_bs
                    DESDE ventas v
                    IZQUIERDA UNIRSE ventas_extra e ON v.id = e.venta_id
                    ORDENAR POR v.fecha DESC
                """, conexión)
        excepto Excepción como e:
            st.error(f"Error al cargar historial: {e}")
            st.stop()

        si df_historial.empty:
            st.info("No hay ventas aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", fecha.hoy() - timedelta(dias=30))
        hasta = c2.date_input("Hasta", fecha.hoy())

        df_historial['fecha'] = pd.to_datetime(df_historial['fecha'], errores='coaccionar')

        df_fil = df_historial[
            (df_historial['fecha'].dt.date >= desde) &
            (df_historial['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por cliente o detalle:")

        si busc:
            df_fil = df_fil[
                df_fil['cliente'].str.contains(busc, case=False, na=False) |
                df_fil['detalle'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del periodo", f"$ {df_fil['total'].sum():.2f}")

        # --- GESTIÓN DE PENDIENTES ---
        st.subheader("Gestión de Cuentas Pendientes")

        pendientes = df_fil[df_fil['metodo'] == "Pendiente"]

        para _, fila en pendientes.iterrows():

            con st.container(border=True):

                st.write(f"**{fila['cliente']}** – ${fila['total']:.2f}")

                if st.button(f"Marcar como pagada #{row['id']}"):

                    intentar:
                        con conectar() como conexión:
                            conn.execute("""
                                ACTUALIZACIÓN ventas
                                SET método = 'Pagado'
                                DONDE id = ?
                            """, (int(fila['id']),))
                            conexión.commit()

                        st.success("Actualizado")
                        st.rerun()

                    excepto Excepción como e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        búfer = io.BytesIO()
        con pd.ExcelWriter(buffer, engine='xlsxwriter') como escritor:
            df_fil.to_excel(escritor, índice=Falso, nombre_hoja='Ventas')

        botón_descargar(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "ventas históricas.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    con tab3:

        st.subheader("Resumen Comercial")

        intentar:
            con conectar() como conexión:
                df_v = pd.read_sql("SELECT * FROM ventas", conn)
        excepto:
            st.info("Sin datos")
            st.stop()

        si df_v.empty:
            st.info("No hay ventas registradas.")
            st.stop()

        total = df_v['monto_total'].sum()

        c1, c2, c3 = st.columns(3)

        c1.metric("Ventas Totales", f"$ {total:.2f}")

        pendientes = df_v[
            df_v['metodo'].str.contains("Pendiente", case=False, na=False)
        ]['monto_total'].suma()

        c2.metric("Por Cobrar", f"$ {pendientes:.2f}")

        arriba = df_v.groupby('cliente')['monto_total'].sum().reset_index()

        mejor = top.sort_values("monto_total", ascending=False).head(1)

        si no mejor.vacío:
            c3.metric("Mejor Cliente", mejor.iloc[0]['cliente'])

        st.subheader("Ventas por Cliente")
        st.bar_chart(top.set_index("cliente"))


# ===========================================================
# 12. MÓDULO PROFESIONAL DE GASTOS (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menú == "📉 Gastos":

    st.title("📉 Control Integral de Gastos")
    st.info("Registro, análisis y control de egresos del negocio")

    # Solo administración puede registrar gastos
    si ROL no está en ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede gestionar gastos.")
        st.stop()

    pestaña1, pestaña2, pestaña3 = st.tabs([
        "📝 Registrador Gasto",
        "📜 Histórico",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE GASTOS
    # -----------------------------------
    con pestaña1:

        con st.form("form_gastos_pro", clear_on_submit=True):

            col_d, col_c = st.columns([2, 1])

            desc = col_d.texto_entrada(
                "Descripción del Gasto",
                placeholder="Ej: Pago de luz, resma de papel, repuesto..."
            ).banda()

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

            monto_gasto = c1.número_entrada(
                "Monto en Dólares ($):",
                valor mínimo=0,01,
                formato="%.2f"
            )

            metodo_pago = c2.selectbox("Método de Pago:", [
                "Efectivo ($)",
                "Pago Móvil (BCV)",
                "Zelle",
                "Binance (USDT)",
                Transferencia (Bs)
            ])

            tasa_ref = t_bcv si "BCV" en metodo_pago o "Bs" en metodo_pago else (
                t_bin si "Binance" en metodo_pago de lo contrario 1.0
            )

            monto_bs = monto_gasto * tasa_ref

            c3.metric("Bs equivalentes", f"{monto_bs:,.2f}")

            st.divider()

            si st.form_submit_button("📉 REGISTRADOR EGRESO"):

                si no desc:
                    st.error("⚠️ La descripción es obligatoria.")
                    st.stop()

                intentar:
                    con conectar() como conexión:

                        conn.execute("""
                            CREAR TABLA SI NO EXISTE gastos_extra (
                                id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                                gasto_id ENTERO,
                                tasa REAL,
                                monto_bs REAL,
                                usuario TEXTO
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERTAR EN gastos 
                            (descripcion, monto, categoria, metodo) 
                            VALORES (?, ?, ?, ?)
                        """, (desc, float(monto_gasto), categoria, metodo_pago))

                        gasto_id = cur.lastrowid

                        cur.execute("""
                            INSERTAR EN gastos_extra
                            (gasto_id, tasa, monto_bs, usuario)
                            VALORES (?, ?, ?, ?)
                        """, (
                            gasto_id,
                            flotar(tasa_ref),
                            flotar(monto_bs),
                            st.session_state.get("usuario_nombre", "Sistema")
                        ))

                        conexión.commit()

                    st.success("📉 Gasto registrado correctamente.")
                    globos de San Valentín()
                    st.rerun()

                excepto Excepción como e:
                    st.error(f"❌ Error al guardar el gasto: {e}")

    # -----------------------------------
    # HISTÓRICO DE GASTOS
    # -----------------------------------
    con tab2:

        st.subheader("📋 Historia de Gastos")

        intentar:
            con conectar() como conexión:
                df_g = pd.read_sql_query("""
                    SELECCIONAR 
                        g.id,
                        g.fecha,
                        g.descripcion,
                        g.categoría,
                        g.monto,
                        g.metodo,
                        e.tasa,
                        e.monto_bs,
                        usuario electrónico
                    DE gastos g
                    IZQUIERDA UNIRSE gastos_extra e ON g.id = e.gasto_id
                    ORDENAR POR g.fecha DESC
                """, conexión)
        excepto Excepción como e:
            st.error(f"Error al cargar historial: {e}")
            st.stop()

        si df_g.empty:
            st.info("No hay gastos registrados aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", fecha.hoy() - timedelta(dias=30))
        hasta = c2.date_input("Hasta", fecha.hoy())

        df_g['fecha'] = pd.to_datetime(df_g['fecha'], errors='coerce')

        df_fil = df_g[
            (df_g['fecha'].dt.date >= desde) &
            (df_g['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por descripción:")

        si busc:
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

        con st.expander("✏️ Editar Gasto"):

            nuevo_monto = st.número_entrada(
                "Monto $",
                valor=float(datos['monto']),
                formato="%.2f"
            )

            if st.button("💾 Guardar Cambios"):

                intentar:
                    con conectar() como conexión:
                        conn.execute("""
                            ACTUALIZACIÓN gastos
                            SET monto = ?
                            DONDE id = ?
                        """, (float(nuevo_monto), int(datos['id'])))
                        conexión.commit()

                    st.success("Actualizado correctamente")
                    st.rerun()

                excepto Excepción como e:
                    st.error(str(e))

        con st.expander("🗑️ Eliminar Gasto"):

            confirmar = st.checkbox("Confirma que deseo eliminar este gasto")

            if st.button("Eliminar definitivamente"):

                si no confirmar:
                    st.warning("Debes confirmar para eliminar")
                demás:
                    intentar:
                        con conectar() como conexión:
                            conn.execute(
                                "ELIMINAR DE gastos DONDE id = ?",
                                (int(datos['id']),)
                            )
                            conexión.commit()

                        st.warning("Gasto eliminado")
                        st.rerun()

                    excepto Excepción como e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        búfer = io.BytesIO()
        con pd.ExcelWriter(buffer, engine='xlsxwriter') como escritor:
            df_fil.to_excel(escritor, índice=Falso, nombre_hoja='Gastos')

        botón_descargar(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "gastos_históricos.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    con tab3:

        st.subheader("📊 Resumen de Egresos")

        intentar:
            con conectar() como conexión:
                df = pd.read_sql("SELECT * FROM gastos", conexión)
        excepto:
            st.info("Sin datos")
            st.stop()

        si df.vacío:
            st.info("No hay gastos para analizar.")
            st.stop()

        total = df['monto'].suma()

        c1, c2 = st.columns(2)

        c1.metric("Total Gastado", f"$ {total:.2f}")

        por_cat = df.groupby('categoria')['monto'].sum()

        categoria_top = por_cat.idxmax() si no es por_cat.empty de lo contrario "N/A"

        c2.metric("Categoría Principal", categoria_top)

        st.subheader("Gastos por Categoría")
        st.bar_chart(por_cat)


# ===========================================================
# 13. MÓDULO PROFESIONAL DE CIERRE DE CAJA (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "🏁 Cierre de Caja":

    st.title("🏁 Cierre de Caja y Arqueo Diario")

    # --- SEGURIDAD ---
    si ROL no está en ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede realizar cierres.")
        st.stop()

    # Selección de fecha
    fecha_cierre = st.date_input("Seleccionar fecha:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    intentar:
        con conectar() como conexión:

            # Asegurar tabla de cierres
            conn.execute("""
                CREAR TABLA SI NO EXISTE cierres_caja (
                    id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                    fecha TEXTO ÚNICO,
                    ingresos REALES,
                    egresos REALES,
                    neto REAL,
                    usuario TEXTO,
                    creado FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
                )
            """)

            df_v = pd.read_sql(
                "SELECT * FROM ventas WHERE fecha(fecha) = ?",
                conexión,
                parámetros=(fecha_str,)
            )

            df_g = pd.read_sql(
                "SELECT * FROM gastos WHERE fecha(fecha) = ?",
                conexión,
                parámetros=(fecha_str,)
            )

    excepto Excepción como e:
        st.error(f"Error al cargar datos: {e}")
        st.stop()

    # Asegurar que existen columnas esperadas
    si no está df_v.empty y 'metodo' no está en df_v.columns:
        df_v['metodo'] = ""

    # --- SEPARAR COBRADO Y PENDIENTE ---
    si no df_v.empty:
        cobradas = df_v[~df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
        pendientes = df_v[df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
    demás:
        cobradas = pd.DataFrame(columnas=df_v.columnas)
        pendientes = pd.DataFrame(columnas=df_v.columnas)

    t_ventas_cobradas = float(cobradas['monto_total'].sum()) si no cobradas.empty else 0.0
    t_pendientes = float(pendientes['monto_total'].sum()) si no pendientes.empty else 0.0
    t_gastos = float(df_g['monto'].sum()) si no df_g.empty de lo contrario 0.0

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

    con col_v:
        st.subheader("💰 Ingresos por Método")

        si no cobradas.vacio:
            resumen_v = cobradas.groupby('metodo')['monto_total'].sum()
            para el método, monto en resumen_v.items():
                st.write(f"✅ **{método}:** ${float(monto):,.2f}")
        demás:
            st.info("No hubo ingresos cobrados.")

    con col_g:
        st.subheader("💸 Salidas por Método")

        si no df_g.empty:
            resumen_g = df_g.groupby('metodo')['monto'].sum()
            para el método, monto en resumen_g.items():
                st.write(f"❌ **{método}:** ${float(monto):,.2f}")
        demás:
            st.info("No hubo gastos.")

    st.divider()

    # --- DETALLES ---
    con st.expander("📝 Ver detalle completo"):

        st.write("### Ventas Cobradas")
        si no cobradas.vacio:
            st.dataframe(cobradas, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)
        demás:
            st.info("Sin ventas cobradas")

        st.write("### Ventas Pendientes")
        si no pendientes.vacío:
            st.dataframe(pendientes, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)
        demás:
            st.info("Sin ventas pendientes")

        st.write("### Gastos")
        si no df_g.empty:
            st.dataframe(df_g, ancho_del_contenedor_de_uso=Verdadero, índice_oculto=Verdadero)
        demás:
            st.info("Sin gastos registrados")

    # --- GUARDAR CIERRE ---
    if st.button("💾 Guardar Cierre del Día"):

        intentar:
            con conectar() como conexión:
                conn.execute("""
                    INSERTAR O SUSTITUIR EN cierres_caja
                    (fecha, ingresos, egresos, neto, usuario)
                    VALORES (?, ?, ?, ?, ?)
                """, (
                    fecha_str,
                    float(t_ventas_cobradas),
                    flotador(t_gastos),
                    float(balance_dia),
                    st.session_state.get("usuario_nombre", "Sistema")
                ))
                conexión.commit()

            st.success("✅ Cierre registrado correctamente")

        excepto Excepción como e:
            st.error(f"Error guardando cierre: {e}")

    # --- HISTORIAL DE CIERRES ---
    st.divider()
    st.subheader("📜 Historial de Cierres")

    intentar:
        con conectar() como conexión:
            df_cierres = pd.read_sql(
                "SELECCIONAR * DESDE cierres_caja ORDEN POR fecha DESC",
                conexión
            )

        si no df_cierres.empty:
            st.dataframe(df_cierres, use_container_width=True)

            # Exportación
            búfer = io.BytesIO()
            con pd.ExcelWriter(buffer, engine='xlsxwriter') como escritor:
                df_cierres.to_excel(escritor, índice=Falso, nombre_hoja='Cierres')

            botón_descargar(
                "📥 Descargar Historial de Cierres",
                buffer.getvalue(),
                "cierres_caja.xlsx"
            )
        demás:
            st.info("Aún no hay cierres guardados.")

    excepto Excepción como e:
        st.info("No hay historial disponible.")



# ===========================================================
# 13. AUDITORÍA Y MÉTRICAS - VERSIÓN PROFESIONAL MEJORADA 2.1
# ===========================================================
elif menu == "📊 Auditoría y Métricas":

    st.title("📊 Auditoría Integral del Negocio")
    st.caption("Control total de insumos, producción y finanzas")

    intentar:
        con conectar() como conexión:

            # Verificamos si existe la tabla de movimientos
            conn.execute("""
                CREAR TABLA SI NO EXISTE inventario_movs (
                    id ENTERO CLAVE PRIMARIA AUTOINCREMENTO,
                    item_id ENTERO,
                    tipo TEXTO,
                    cantidad REAL,
                    motivo TEXTO,
                    usuario TEXTO,
                    fecha FECHA Y HORA PREDETERMINADA MARCA DE TIEMPO ACTUAL
                )
            """)

            df_movs = pd.read_sql_query("""
                SELECCIONAR 
                    m.fecha,
                    i.item como Material,
                    m.tipo como Operación,
                    m.cantidad como Cantidad,
                    i.unidad,
                    m.motivo
                DESDE inventario_movs m
                UNIRSE al inventario i EN m.item_id = i.id
                ORDENAR POR m.fecha DESC
            """, conexión)

            df_ventas = pd.read_sql("SELECT * FROM ventas", conn)
            df_gastos = pd.read_sql("SELECT * FROM gastos", conexión)

    excepto Excepción como e:
        st.error(f"Error al cargar datos: {e}")
        st.stop()

    # Asegurar columnas necesarias
    si no está df_ventas.empty y 'metodo' no está en df_ventas.columns:
        df_ventas['metodo'] = ""

    pestaña1, pestaña2, pestaña3, pestaña4 = st.tabs([
        "💰 Finanzas",
        "📦 Insumos",
        "📈 Gráficos",
        "🚨 Alertas"
    ])

    # ---------------------------------------
    # PESTAÑA FINANZAS
    # ---------------------------------------
    con pestaña1:

        st.subheader("Resumen Financiero")

        total_ventas = float(df_ventas['monto_total'].sum()) si no df_ventas.empty else 0.0
        total_gastos = float(df_gastos['monto'].sum()) si no df_gastos.empty de lo contrario 0.0

        # Solo comisiones en métodos bancarios
        si no df_ventas.empty:
            ventas_bancarias = df_ventas[
                df_ventas['metodo'].str.contains("Pago|Transferencia", case=False, na=False)
            ]
        demás:
            ventas_bancarias = pd.DataFrame()

        banco_perc = st.session_state.get('banco_perc', 0.5)

        comision_est = float(ventas_bancarias['monto_total'].sum() * (banco_perc / 100)) si no ventas_bancarias.empty else 0.0

        deudas = float(
            df_ventas[
                df_ventas['metodo'].str.contains("Pendiente", case=False, na=False)
            ]['monto_total'].suma()
        ) si no df_ventas.empty de lo contrario 0.0

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Ingresos", f"$ {total_ventas:,.2f}")
        c2.metric("Gastos", f"$ {total_gastos:,.2f}", delta_color="inverse")
        c3.metric("Comisiones Bancarias", f"$ {comision_est:,.2f}")
        c4.metric("Cuentas por Cobrar", f"$ {deudas:,.2f}")

        utilidad = total_ventas - total_gastos - comision_est

        st.metric("Utilidad Real Estimada", f"$ {utilidad:,.2f}")

    # ---------------------------------------
    # PESTAÑA INSUMOS
    # ---------------------------------------
    con tab2:

        st.subheader("Bitácora de Movimientos de Inventario")

        si df_movs.empty:
            st.info("Aún no hay movimientos registrados.")
        demás:
            st.dataframe(df_movs, usar_ancho_del_contenedor=Verdadero)

            # Exportación
            búfer = io.BytesIO()
            con pd.ExcelWriter(buffer, engine='xlsxwriter') como escritor:
                df_movs.to_excel(escritor, índice=False, nombre_hoja='Movimientos')

            botón_descargar(
                "📥 Descargar Movimientos (Excel)",
                buffer.getvalue(),
                "auditoria_movimientos.xlsx"
            )

    # ---------------------------------------
    # PESTAÑAS GRÁFICAS
    # ---------------------------------------
    con tab3:

        st.subheader("Consumo de Insumos")

        si no df_movs.empty:

            salidas = df_movs[df_movs['Operacion'] == 'SALIDA']

            si no salidas.vacío:

                resumen = salidas.groupby("Material")["Cantidad"].sum()

                st.bar_chart(resumen)

                superior = resumen.sort_values(ascendente=Falso).head(1)

                si no está en la parte superior vacía:
                    st.metric(
                        "Material más usado",
                        índice superior[0],
                        f"{valores superiores[0]:.2f}"
                    )
            demás:
                st.info("No hay salidas registradas aún.")
        demás:
            st.info("No hay datos para graficar.")

    # ---------------------------------------
    # PESTAÑA ALERTAS
    # ---------------------------------------
    con tab4:

        st.subheader("Control de Stock")

        df_inv = st.session_state.get('df_inv', pd.DataFrame())

        si df_inv.empty:
            st.warning("Inventario vacío.")
        demás:
            criticos = df_inv[df_inv['cantidad'] <= df_inv['minimo']]

            si criticos.vacío:
                st.success("Niveles de inventario óptimos")
            demás:
                st.error(f"⚠️ Hay {len(criticos)} productos en nivel crítico")

                para _, r en criticos.iterrows():
                    st.advertencia(
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

    si df_cli.empty:
        st.warning("Registra clientes primero.")
        st.stop()

    opciones = {r['nombre']: r['id'] para _, r en df_cli.iterrows()}

    cliente_sel = st.selectbox("Cliente:", opciones.keys())
    id_cliente = opciones[cliente_sel]

    unidades = st.numero_entrada(
        "Cantidad",
        valor mínimo=1,
        valor=int(datos_pre['unidades'])
    )

    # ---- COSTOS ----
    costo_unidad = st.numero_entrada(
        "Costo unitario base ($)",
        valor=float(datos_pre['costo_base'] / unidades if unidades else 0)
    )

    margen = st.slider("Margen %", 10, 300, 100)

    costo_total = costo_unit * unidades
    precio_final = costo_total * (1 + margen / 100)

    st.metric("Precio sugerido", f"$ {precio_final:.2f}")

    # ---- CONSUMOS ----
    consumos_reales = {}

    si usa_tinta:

        df_tintas = obtener_tintas_disponibles()

        si df_tintas.empty:
            st.error("No hay tintas registradas en inventario.")
            st.stop()

        opciones_tinta = {
            f"{r['item']} ({r['cantidad']} ml)": r['id']
            para _, r en df_tintas.iterrows()
        }

        st.subheader("Asignación de Tintas a Descontar")

        para color en ['C', 'M', 'Y', 'K']:
            sel = st.selectbox(f"Tinta {color}", opciones_tinta.keys(), clave=color)
            consumos_reales[opciones_tinta[sel]] = datos_pre[color] * unidades

    método_pago = st.selectbox(
        "Método de Pago",
        ["Efectivo", "Zelle", "Pago Móvil", "Transferencia", "Pendiente"]
    )

    # =====================================================
    # 🔐 INTEGRACIÓN CON NÚCLEO CENTRAL
    # =====================================================
    if st.boton("CONFIRMAR VENTA"):

        descr = datos_pre['trabajo']

        intentar:
            exito, msg = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_sel,
                detalle=descr,
                monto_usd=precio_final,
                método=metodo_pago,
                consumos=consumos_reales
            )

            si exito:
                st.success(msg)

                # Limpiamos datos temporales de cotización
                st.session_state.pop('datos_pre_cotizacion', Ninguno)

                cargar_datos()
                st.rerun()

            demás:
                st.error(msg)

        excepto Excepción como e:
            st.error(f"Error procesando venta: {e}")



# ===========================================================
# 🛒 MÓDULO DE VENTA DIRECTA - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
if menú == "🛒 Venta Directa":

    st.title("🛒 Venta Rápida de Materiales")

    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    si df_inv.empty:
        st.warning("No hay inventario cargado.")
        st.stop()

    disponibles = df_inv[df_inv['cantidad'] > 0]

    si está disponible.vacío:
        st.warning("⚠️ No hay productos en stock disponibles.")
        st.stop()

    # --- SELECCIÓN DE PRODUCTO ---
    con st.container(border=True):

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
    con st.form("form_venta_directa", clear_on_submit=True):

        st.subheader("Datos de la Venta")

        # Cliente integrado
        si no es df_cli.empty:
            opciones_cli = {
                fila['nombre']: fila['id']
                para _, fila en df_cli.iterrows()
            }

            cliente_nombre = st.selectbox(
                "Cliente:",
                lista(opciones_cli.keys())
            )

            id_cliente = opciones_cli[cliente_nombre]
        demás:
            cliente_nombre = "Consumidor Final"
            id_cliente = Ninguno
            st.info("Venta sin cliente registrado")

        c1, c2, c3 = st.columns(3)

        cantidad = c1.number_input(
            f"Cantidad ({unidad})",
            valor mínimo=0.0,
            valor_máximo=stock_real,
            paso=1.0
        )

        margen = c2.number_input("Margen %", valor=30.0, formato="%.2f")

        método = c3.selectbox(
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
        desc = st.numero_entrada(
            "Descuento %",
            valor=5.0 si usa_desc de lo contrario 0.0,
            deshabilitado=no usa_desc,
            formato="%.2f"
        )

        # Impuestos
        st.write("Impuestos aplicables:")

        i1, i2 = st.columns(2)

        usa_iva = i1.checkbox("Aplicar IVA")
        usa_banco = i2.checkbox("Comisión bancaria", valor=True)

        # ---- CÁLCULOS ----
        costo_material = cantidad * precio_base
        con_margen = costo_material * (1 + margen / 100)
        con_desc = con_margen * (1 - desc / 100)

        impuestos = 0.0

        si usa_iva:
            impuestos += float(st.session_state.get('iva_perc', 16))

        if usa_banco y método en ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            impuestos += float(st.session_state.get('banco_perc', 0.5))

        total_usd = con_desc * (1 + impuestos / 100)

        # Conversión a Bs SOLO si aplica
        total_bs = 0.0

        si metodo en ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            total_bs = total_usd * float(st.session_state.get('tasa_bcv', 1.0))

        elif método == "Binance":
            total_bs = total_usd * float(st.session_state.get('tasa_binance', 1.0))

        st.divider()

        st.metric("Total a Cobrar", f"$ {total_usd:.2f}")

        si total_bs > 0:
            st.info(f"Equivalente: Bs {total_bs:,.2f}")

        # ---- VALIDACIONES FINALES ----
        if st.form_submit_button("🧾 Confirmar Venta"):

            si cantidad <= 0:
                st.error("⚠️ Debe vender al menos una unidad.")
                st.stop()

            si cantidad > stock_actual:
                st.error("⚠️ No puedes vender más de lo que hay en inventario.")
                st.stop()

            # Preparar consumo para el núcleo
            consumos = {id_producto: cantidad}

            intentar:
                exito, mensaje = registrar_venta_global(
                    id_cliente=id_cliente,
                    nombre_cliente=cliente_nombre,
                    detalle=f"Venta directa de {prod_sel}",
                    monto_usd=float(total_usd),
                    método=metodo,
                    consumos=consumos
                )

                si exito:
                    st.success(mensaje)
                    cargar_datos()
                    st.rerun()
                demás:
                    st.error(mensaje)

            excepto Excepción como e:
                st.error(f"Error al registrar la venta: {e}")


      # ===========================================================
# 🛒 MÓDULO DE VENTA DIRECTA - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
if menú == "🛒 Venta Directa":

    st.title("🛒 Venta Rápida de Materiales")

    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    si df_inv.empty:
        st.warning("No hay inventario cargado.")
        st.stop()

    disponibles = df_inv[df_inv['cantidad'] > 0]

    si está disponible.vacío:
        st.warning("⚠️ No hay productos en stock disponibles.")
        st.stop()

    # --- SELECCIÓN DE PRODUCTO ---
    con st.container(border=True):

        c1, c2 = st.columns([2, 1])

        prod_sel = c1.selectbox(
            "📦 Seleccionar Producto:",
            disponibles['item'].tolist(),
            clave="venta_directa_producto"
        )

        datos = disponibles[disponibles['item'] == prod_sel].iloc[0]

        id_producto = datos['id']
        stock_actual = float(datos['cantidad'])
        precio_base = float(datos['precio_usd'])
        unidad = datos['unidad']
        minimo = float(datos['minimo'])

        c2.metric("Stock Disponible", f"{stock_actual:.2f} {unidad}")

    # --- FORMULARIO DE VENTA ---
    con st.form("form_venta_directa_modulo", clear_on_submit=True):

        st.subheader("Datos de la Venta")

        # Cliente integrado
        si no es df_cli.empty:
            opciones_cli = {
                fila['nombre']: fila['id']
                para _, fila en df_cli.iterrows()
            }

            cliente_nombre = st.selectbox(
                "Cliente:",
                opciones_cli.keys(),
                clave="venta_directa_cliente"
            )

            id_cliente = opciones_cli[cliente_nombre]
        demás:
            cliente_nombre = "Consumidor Final"
            id_cliente = Ninguno
            st.info("Venta sin cliente registrado")

        c1, c2, c3 = st.columns(3)

        cantidad = c1.number_input(
            f"Cantidad ({unidad})",
            valor mínimo=0.0,
            valor_máximo=stock_real,
            paso=1.0,
            key="venta_directa_cantidad"
        )

        margen = c2.número_entrada(
            "Margen %",
            valor=30.0,
            clave="venta_directa_margen"
        )

        método = c3.selectbox(
            "Método de Pago",
            [
                "Efectivo $",
                "Pago Móvil (BCV)",
                "Transferencia (Bs)",
                "Zelle",
                "Binance",
                "Pendiente"
            ],
            clave="venta_directa_método"
        )

        usa_desc = st.checkbox("Aplicar descuento cliente fiel", key="venta_directa_check_desc")
        desc = st.numero_entrada(
            "Descuento %",
            valor=5.0 si usa_desc de lo contrario 0.0,
            deshabilitado=no usa_desc,
            clave="venta_directa_desc"
        )

        # Impuestos
        st.write("Impuestos aplicables:")

        i1, i2 = st.columns(2)

        usa_iva = i1.checkbox("Aplicar IVA", key="venta_directa_iva")
        usa_banco = i2.checkbox("Comisión bancaria", valor=True, key="venta_directa_banco")

        # ---- CÁLCULOS ----
        costo_material = cantidad * precio_base
        con_margen = costo_material * (1 + margen / 100)
        con_desc = con_margen * (1 - desc / 100)

        impuestos = 0

        si usa_iva:
            impuestos += st.session_state.get('iva_perc', 16)

        if usa_banco y método en ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            impuestos += st.session_state.get('banco_perc', 0.5)

        total_usd = con_desc * (1 + impuestos / 100)

        si metodo en ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            total_bs = total_usd * t_bcv
        elif método == "Binance":
            total_bs = total_usd * t_bin
        demás:
            total_bs = 0

        st.divider()

        st.metric("Total a Cobrar", f"$ {total_usd:.2f}")

        si total_bs:
            st.info(f"Equivalente: Bs {total_bs:,.2f}")

        # =====================================================
        # 🔐 AQUÍ ENTRA EL NÚCLEO CENTRAL DEL IMPERIO
        # =====================================================
        si st.form_submit_button("🚀 PROCESAR VENTA"):

            si cantidad <= 0:
                st.error("Cantidad inválida")
                st.stop()

            consumos = {
                id_producto: cantidad
            }

            exito, mensaje = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_nombre,
                detalle=f"{cantidad} {unidad} de {prod_sel}",
                monto_usd=total_usd,
                método=metodo,
                consumos=consumos
            )

            si exito:
                st.success(mensaje)

                if stock_actual - cantidad <= minimo:
                    st.warning("⚠️ Producto quedó en nivel crítico")

                st.session_state.ultimo_ticket = {
                    "cliente": cliente_nombre,
                    "detalle": f"{cantidad} {unidad} de {prod_sel}",
                    "total": total_usd,
                    "método": método
                }

                st.rerun()
            demás:
                st.error(mensaje)

    # --- BOLETO ---
    si 'ultimo_ticket' en st.session_state:

        st.divider()

        t = st.session_state.ultimo_ticket

        con st.expander("📄 Recibo de Venta", expandido=True):

            st.código(
F"""
CLIENTE: {t['cliente']}
DETALLE: {t['detalle']}
TOTAL: $ {t['total']:.2f}
MÉTODO: {t['metodo']}
"""
            )

            if st.button("Cerrar Ticket", key="cerrar_ticket_venta_directa"):
                del st.session_state.ultimo_ticket
                st.rerun()


        # =====================================================
        # 🔐 AQUÍ ENTRA EL NÚCLEO CENTRAL DEL IMPERIO
        # =====================================================
        si st.form_submit_button("🚀 PROCESAR VENTA"):

            si cantidad <= 0:
                st.error("⚠️ Debes vender al menos una unidad.")
                st.stop()

            si cantidad > stock_actual:
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
                método=metodo,
                consumos=consumos
            )

            si exito:
                st.success(mensaje)

                if stock_actual - cantidad <= minimo:
                    st.warning("⚠️ Producto quedó en nivel crítico")

                st.session_state.ultimo_ticket = {
                    "cliente": cliente_nombre,
                    "detalle": f"{cantidad} {unidad} de {prod_sel}",
                    "total": total_usd,
                    "método": método
                }

                st.rerun()
            demás:
                st.error(mensaje)

    # --- BOLETO ---
    si 'ultimo_ticket' en st.session_state:

        st.divider()

        t = st.session_state.ultimo_ticket

        con st.expander("📄 Recibo de Venta", expandido=True):

            st.código(
F"""
CLIENTE: {t['cliente']}
DETALLE: {t['detalle']}
TOTAL: $ {t['total']:.2f}
MÉTODO: {t['metodo']}
"""
            )

            si st.button("Cerrar Ticket"):
                del st.session_state.ultimo_ticket
                st.rerun()


# ===========================================================
# 🔐 NÚCLEO CENTRAL DE REGISTRO DE VENTAS DEL IMPERIO
# ===========================================================

def registrar_venta_global(
    id_cliente=Ninguno,
    nombre_cliente="Consumidor Final",
    detalle="Venta general",
    monto_usd=0.0,
    método="Efectivo $",
    consumos=Ninguno
):
    """
    FUNCIÓN MAESTRA DEL IMPERIO – VERSIÓN SEGURA Y TRANSACCIONAL
    """

    Si consumos es Ninguno:
        consumos = {}

    si monto_usd <= 0:
        return False, "⚠️ El monto de la venta debe ser mayor a 0"

    si no detalle:
        return False, "⚠️ El detalle de la venta no puede estar vacío"

    intentar:
        conn = conectar()
        cursor = conn.cursor()

        conn.execute("INICIAR TRANSACCIÓN")

        si id_cliente no es Ninguno:
            existe_cli = cursor.execute(
                "SELECCIONAR id DE clientes DONDE id = ?",
                (id_cliente,)
            ).fetchone()

            si no existe_cli:
                conexión.rollback()
                return False, "❌ Cliente no encontrado en base de datos"

        para item_id, no puede en consumos.items():

            si no puede <= 0:
                conexión.rollback()
                return False, f"⚠️ Cantidad inválida para el insumo {item_id}"

            stock_actual = cursor.execute(
                "SELECT cantidad, item FROM inventario WHERE id = ?",
                (id del artículo,)
            ).fetchone()

            si no stock_actual:
                conexión.rollback()
                return False, f"❌ Insumo con ID {item_id} no existe"

            cantidad_disponible, nombre_item = stock_actual

            si no puedo > cantidad_disponible:
                conexión.rollback()
                return False, f"⚠️ Stock insuficiente para: {nombre_item}"

        para item_id, no puede en consumos.items():

            cursor.execute("""
                ACTUALIZAR inventario
                SET cantidad = cantidad - ?
                DONDE id = ?
            """, (cant, id_del_artículo))

            cursor.execute("""
                INSERTAR EN inventario_movs
                (item_id, tipo, cantidad, motivo)
                VALORES (?, 'SALIDA', ?, ?)
            """, (item_id, cant, f"Venta: {detalle}"))

        cursor.execute("""
            INSERTAR EN ventas
            (cliente_id, cliente, detalle, monto_total, metodo)
            VALORES (?, ?, ?, ?, ?)
        """, (
            id_cliente,
            nombre_cliente,
            detalle,
            flotador(monto_usd),
            método
        ))

        conexión.commit()
        conexión.close()

        cargar_datos()

        return Verdadero, "✅ Venta procesada correctamente"

    excepto Excepción como e:
        intentar:
            conexión.rollback()
        excepto:
            aprobar

        return False, f"❌ Error interno al procesar la venta: {str(e)}"



