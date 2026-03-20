rom __future__ import annotations

from datetime import datetime

import numpy as np
importar pandas como pd
import plotly.express as px
importar streamlit como st

from database.connection import db_transaction
from modules.common import as_positive, require_text
desde services.diagnostics_service importar (
    obtener_resumen_diagnóstico_de_impresora,
    lista_diagnósticos_de_impresora,
    lista_recargas_de_impresora,
    lista_mantenimiento_impresora,
)

ROLES_PERMITIDOS = {"Admin", "Administration", "Administracion"}
TIPOS_UNIDAD = [
    "Impresora",
    "Corte",
    "Plastificación",
    "Sublimación",
    "Conexión y Energía",
    "Otro",
]
CLASES_REGISTRO = {
    "equipo_principal": "Equipo principal",
    "componente": "Componente / Repuesto",
    "herramienta": "Herramienta / Accesorio",
}
UNIDADES DE VIDA ÚTILES = [
    "usos",
    "páginas",
    "cortés",
    "trabajos",
    "horas"
    "meses"
    "manual",
]
ESTADOS_OPERATIVOS = ["Nuevo", "Bueno", "Medio", "Bajo", "Crítico", "Reemplazar"]
TIPOS_COMPONENTE_POR_UNIDAD = {
    "Impresora": [
        "Cabezal color",
        "Cabezal negro",
        "Cabezal",
        "Rodillo",
        "Almohadillas",
        "Regulador de voltaje",
        "Cable USB",
        "Cable de poder",
        "Fuente de poder",
    ],
    "Cortar": [
        "Cuchilla",
        "Estera",
        "Espátula",
        "Kit de desbaste",
        "Regleta",
        "Regulador de voltaje",
        "Cable USB",
        "Cable de poder",
    ],
    "Plastificación": [
        "Rodillo",
        "Resistencia",
        "Cable de poder",
        "Regulador de voltaje",
        "Regleta",
    ],
    "Sublimación": [
        "Resistencia",
        "Estera",
        "Olvidar",
        "Teflón",
        "Regulador de voltaje",
        "Cable de poder",
        "Regleta",
    ],
    "Conexión y Energía": [
        "Regleta",
        "UNIÓN POSTAL UNIVERSAL",
        "Regulador de voltaje",
        "Cable USB",
        "Cable de poder",
        "Cable HDMI",
        "Cable de red",
        "Extensión eléctrica",
        "Adaptador de corriente",
        "Fuente de poder",
        "Transformador",
        "Concentrador USB",
        "Conector",
        "Cargador",
        "Convertidor",
    ],
    "Otro": [],
}
TIPOS_POR_EQUIPO = {
    "Impresora": {
        "categoria": "Impresora",
        "label": "Tipo de impresora",
        "placeholder": "Selecciona el tipo de impresora",
        "opciones": [
            "Tanque de tinta"
            "Cartucho",
            "Láser monocromática",
            "Láser a color",
            "Impresora de sublimación",
            "Plotter de impresión",
            "Impresora térmica",
            "Impresora matricial",
        ],
    },
    "Cortar": {
        "categoría": "Corte",
        "label": "Tipo de corte",
        "placeholder": "Selecciona el tipo de corte",
        "opciones": [
            "Camafeo",
            "Cricut",
            "Plotter de corte",
            "Guillotina",
            "Guillotina manual",
            "Tijeras",
            "Exacto",
            "Bisturí",
            "Bisturí de precisión",
            "Cizalla",
            "Troqueladora",
        ],
    },
    "Plastificación": {
        "categoria": "Plastificación",
        "label": "Tipo de máquina de plastificación",
        "placeholder": "Selecciona el tipo de máquina de plastificación",
        "opciones": [
            "Plastificadora térmica",
            "Plastificadora de credenciales",
            "Laminadora en frío",
            "Laminadora en caliente",
            "Enmicadora",
            "Rodillo manual",
            "Plastificadora de rodillo",
            "Plastificadora industrial",
        ],
    },
    "Sublimación": {
        "categoria": "Sublimación",
        "label": "Tipo de sublimación",
        "placeholder": "Selecciona el tipo de sublimación",
        "opciones": [
            "Plancha",
            "Tapete",
            "Cinta térmica",
            "Cintas térmicas",
            "Horno",
            "Resistencia",
            "Plancha para tazas",
            "Plancha para gorras",
            "Plancha plana",
            "Plancha 8 en 1",
            "Tapete térmico",
   raise ValueError(f"Debes seleccionar {(_label_tipo_equipo(tipo_equipo)).lower()}.")

def _valor_tipo_para_formulario(tipo_equipo: str | None, valor_actual: str | None) -> tuple[str | None, str]:
    valor_actual = str(valor_actual or "").strip()
    opciones = _equipo_config(tipo_equipo).get("opciones") or []
    if not valor_actual:
        return None, ""
    if valor_actual in opciones:
        return valor_actual, ""
    if opciones:
        return OPCION_TIPO_PERSONALIZADO, valor_actual
    return None, valor_actual

# =========================================================
# CAPA DE DATOS
# =========================================================

def _ensure_activos_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            estado TEXT NOT NULL DEFAULT 'activo',
            equipo TEXT NOT NULL,
            modelo TEXT,
            categoria TEXT,
            inversion REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            desgaste REAL NOT NULL DEFAULT 0,
            costo_hora REAL NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activos_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            activo TEXT NOT NULL,
            accion TEXT NOT NULL,
            detalle TEXT,
            costo REAL NOT NULL DEFAULT 0,
            usuario TEXT
)
        """
    )

    cols = {row[1] for row in conn.execute("PRAGMA table_info(activos)").fetchall()}
    optional_cols = {
        "inversion": "ALTER TABLE activos ADD COLUMN inversion REAL NOT NULL DEFAULT 0",
        "unidad": "ALTER TABLE activos ADD COLUMN unidad TEXT",
        "desgaste": "ALTER TABLE activos ADD COLUMN desgaste REAL NOT NULL DEFAULT 0",
        "activo": "ALTER TABLE activos ADD COLUMN activo INTEGER NOT NULL DEFAULT 1",
        "modelo": "ALTER TABLE activos ADD COLUMN modelo TEXT",
        "costo_hora": "ALTER TABLE activos ADD COLUMN costo_hora REAL NOT NULL DEFAULT 0",
        "estado": "ALTER TABLE activos ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo'",
        "fecha": "ALTER TABLE activos ADD COLUMN fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "usuario": "ALTER TABLE activos ADD COLUMN usuario TEXT",
        "vida_cabezal_pct": "ALTER TABLE activos ADD COLUMN vida_cabezal_pct REAL",
        "vida_rodillo_pct": "ALTER TABLE activos ADD COLUMN vida_rodillo_pct REAL",
        "vida_almohadillas_pct": "ALTER TABLE activos ADD COLUMN vida_almohadillas_pct REAL",
        "paginas_impresas": "ALTER TABLE activos ADD COLUMN paginas_impresas INTEGER DEFAULT 0",
        "tipo_impresora": "ALTER TABLE activos ADD COLUMN tipo_impresora TEXT",
        "tipo_detalle": "ALTER TABLE activos ADD COLUMN tipo_detalle TEXT",
        "clase_registro": "ALTER TABLE activos ADD COLUMN clase_registro TEXT NOT NULL DEFAULT 'equipo_principal'",
        "activo_padre_id": "ALTER TABLE activos ADD COLUMN activo_padre_id INTEGER",
        "tipo_componente": "ALTER TABLE activos ADD COLUMN tipo_componente TEXT",
        "vida_util_unidad": "ALTER TABLE activos ADD COLUMN vida_util_unidad TEXT NOT NULL DEFAULT 'usos'",
        "vida_util_valor": "ALTER TABLE activos ADD COLUMN vida_util_valor REAL DEFAULT 0",
        "uso_inicial": "ALTER TABLE activos ADD COLUMN uso_inicial REAL DEFAULT 0",
        "uso_acumulado": "ALTER TABLE activos ADD COLUMN uso_acumulado REAL DEFAULT 0",
        "costo_reposicion": "ALTER TABLE activos ADD COLUMN costo_reposicion REAL DEFAULT 0",
        "fecha_instalacion": "ALTER TABLE activos ADD COLUMN fecha_instalacion TEXT",
        "estado_operativo": "ALTER TABLE activos ADD COLUMN estado_operativo TEXT NOT NULL DEFAULT 'Bueno'",
        "impacta_costo_padre": "ALTER TABLE activos ADD COLUMN impacta_costo_padre INTEGER NOT NULL DEFAULT 1",
        "impacta_desgaste_padre": "ALTER TABLE activos ADD COLUMN impacta_desgaste_padre INTEGER NOT NULL DEFAULT 0",
    }
    para col, alter_sql en optional_cols.items():
        Si col no está en cols:
            conn.execute(alter_sql)

    _migrar_valores_legados_activos(conn)


def _load_activos_df() -> pd.DataFrame:
    con db_transaction() como conexión:
        _ensure_activos_schema(conn)
        filas = conn.execute(
            """
            SELECCIONAR
                identificación,
                equipo,
                categoría,
                inversión,
                unidad,
                tener puesto,
                modelo,
                costo_hora,
                COALESCE(vida_cabezal_pct, NULL) AS vida_cabezal_pct,
                COALESCE(vida_rodillo_pct, NULL) AS vida_rodillo_pct,
                COALESCE(vida_almohadillas_pct, NULL) AS vida_almohadillas_pct,
                COALESCE(paginas_impresas, 0) AS paginas_impresas,
                tipo_impresora,
                COALESCE(tipo_detalle, tipo_impresora) AS tipo_detalle,
                COALESCE(clase_registro, 'equipo_principal') AS clase_registro,
                activo_padre_id,
                tipo_componente,
                COALESCE(vida_util_unidad, 'usos') AS vida_util_unidad,
                COALESCE(vida_util_valor, 0) AS vida_util_valor,
                COALESCE(uso_inicial, 0) AS uso_inicial,
                COALESCE(uso_acumulativo, 0) AS uso_acumulativo,
                COALESCE(costo_reposicion, 0) AS costo_reposicion,
                fecha_instalacion,
                COALESCE(estado_operativo, 'Bueno') AS estado_operativo,
                COALESCE(impacta_costo_padre, 1) AS impacta_costo_padre,
                COALESCE(impacta_desgaste_padre, 0) AS impacta_desgaste_padre,
                fecha,
                COALESCE(activo, 1) AS activo
            FROM activos
            WHERE COALESCE(activo, 1) = 1
            ORDENAR POR id DESC
            """
        ).fetchall()

    si no hay filas:
        devolver pd.DataFrame(
            columnas=[
                "id", "equipo", "categoria", "inversion", "unidad", "desgaste", "modelo", "costo_hora",
                "vida_cabezal_pct", "vida_rodillo_pct", "vida_almohadillas_pct", "paginas_impresas", "tipo_impresora", "tipo_detalle",
                "clase_registro", "activo_padre_id", "tipo_componente", "vida_util_unidad", "vida_util_valor", "uso_inicial", "uso_acumulado",
                "costo_reposicion", "fecha_instalacion", "estado_operativo", "impacta_costo_padre", "impacta_desgaste_padre", "fecha", "activo"
            ]
        )

    df = pd.DataFrame([dict(r) for r in rows])
    df["unidad"] = df["unidad"].apply(_normalizar_unidad)
    df["tipo_detalle"] = df["tipo_detalle"].where(df["tipo_detalle"].notna(), df["tipo_impresora"])
    df["inversión"] = pd.to_numeric(df["inversión"], errors="coerce").fillna(0.0)
    df["desgaste"] = pd.to_numeric(df["desgaste"], errors="coerce").fillna(0.0)
    df["vida_cabezal_pct"] = pd.to_numeric(df.get("vida_cabezal_pct"), errors="coerce")
    df["vida_rodillo_pct"] = pd.to_numeric(df.get("vida_rodillo_pct"), errors="coerce")
    df["vida_almohadillas_pct"] = pd.to_numeric(df.get("vida_almohadillas_pct"), errors="coerce")
    df["paginas_impresas"] = pd.to_numeric(df.get("paginas_impresas"), errors="coerce").fillna(0).astype(int)
    df["activo_padre_id"] = pd.to_numeric(df.get("activo_padre_id"), errors="coerce")
    df["vida_util_value"] = pd.to_numeric(df.get("vida_util_value"), errors="coerce").fillna(0.0)
    df["uso_inicial"] = pd.to_numeric(df.get("uso_inicial"), errors="coerce").fillna(0.0)
    df["uso_acumulado"] = pd.to_numeric(df.get("uso_acumulado"), errores="coerce").fillna(0.0)
    df["costo_reposicion"] = pd.to_numeric(df.get("costo_reposicion"), errors="coerce").fillna(0.0)
    df["clase_registro"] = df.get("clase_registro", "equipo_principal").apply(_slug_clase_registro)
    df["clase_registro_label"] = df["clase_registro"].apply(_label_clase_registro)
    df["vida_util_unidad"] = df.get("vida_util_unidad", "usos").apply(_normalizar_vida_util_unidad)
    df["estado_operativo"] = df.get("estado_operativo", "Bueno").apply(_normalizar_estado_operativo)
    df["impacta_costo_padre"] = pd.to_numeric(df.get("impacta_costo_padre"), errores="coerce").fillna(1).astype(int)
    df["impacta_desgaste_padre"] = pd.to_numeric(df.get("impacta_desgaste_padre"), errors="coerce").fillna(0).astype(int)
    ranking_riesgo = df["desgaste"].rank(pct=True, method="average").fillna(0)
    df["riesgo"] = np.where(
        ranking_riesgo >= 0.80,
        "🔴 Alto",
        np.where(ranking_riesgo >= 0.50, "🟠 Medio", "🟢 Bajo"),
    )
    devolver df


def _crear_activo(
    usuario: str,
    equipo: str,
    tipo_unidad: str,
    inversión: flotante,
    vida_util: int,
    vida_util_unidad: str,
    modelo: str,
    type_detalle: str | Ninguno,
    clase_registro: str = "equipo_principal",
    active_father_id: int | Ninguno = Ninguno,
    tipo_componente: str | Ninguno = Ninguno,
    initial_use: float = 0.0,
    uso_acumulativo: flotante = 0.0,
    costo_reposicion: float = 0.0,
    fecha_instalacion: str | None = None,
    estado_operativo: str = "Bueno",
    impacta_costo_padre: bool = True,
    impacta_desgaste_padre: bool = False,
) -> int:
    equipo = require_text(equipo, "Nombre del activo")
    tipo_unidad = _normalizar_unidad(require_text(tipo_unidad, "Tipo de equipo"))
    categoria = _categoria_por_equipo(tipo_unidad)
    inversion = as_positive(inversion, "Inversión", allow_zero=False)
    vida_util = max(1, int(vida_util or 1))
    desgaste_unitario = inversion / vida_util
    vida_util_unidad = _normalizar_vida_util_unidad(vida_util_unidad)
    tipo_detalle = (tipo_detalle or "").strip() or None
    tipo_impresora = tipo_detalle if _es_equipo_impresora(tipo_unidad) else None
    clase_registro = _slug_clase_registro(clase_registro)
    activo_padre_id = int(activo_padre_id) if activo_padre_id and clase_registro != "equipo_principal" else None
    tipo_componente = (tipo_componente o "").strip() o None
    if clase_registro != "equipo_principal":
        tipo_componente = require_text(tipo_componente, "Tipo de componente")
    uso_inicial = max(0.0, float(uso_inicial o 0.0))
    uso_acumulativo = max(0.0, float(uso_acumulativo o 0.0))
    costo_reposicion = max(0.0, float(costo_reposicion or 0.0))
    fecha_instalacion = str(fecha_instalacion or "").strip() or datetime.now().strftime("%Y-%m-%d")
    estado_operativo = _normalizar_estado_operativo(estado_operativo)

    con db_transaction() como conexión:
        _ensure_activos_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO activos
            (equipo, modelo, categoria, inversion, unidad, desgaste, costo_hora, usuario, activo, estado, tipo_impresora, tipo_detalle, clase_registro, activo_padre_id, tipo_componente, vida_util_unidad, vida_util_valor, uso_inicial, uso_acumulado, costo_reposicion, fecha_instalacion, estado_operativo, impacta_costo_padre, impacta_desgaste_padre)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'activo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                equipo,
                (modelo o "").strip() o None,
                categoría,
                inversión,
                tipo_unidad,
                desgaste_unitario,
                0.0,
                usuario,
                tipo_impresora,
                tipo_detalle,
                clase_registro,
                activo_padre_id,
                tipo_componente,
                vida_util_unidad,
                float(vida_util),
                uso_inicial,
                uso_acumulativo,
                costo_reposicion,
                fecha_instalacion,
                estado_operativo,
                _valor_bool_db(impacta_costo_padre),
                _valor_bool_db(impacta_desgaste_padre),
            ),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALORES (?, ?, ?, ?, ?)
            """,
            (
                equipo,
                "CREACIÓN",
                (
                    f"Registro inicial (vida útil: {vida_util} {vida_util_unidad})"
                    + (f" · clase: {_label_clase_registro(clase_registro)}" if clase_registro else "")
                    + (f" · activo padre ID: {activo_padre_id}" if activo_padre_id else "")
                    + (f" · componente: {tipo_componente}" if tipo_componente else "")
                ),
                inversión,
                usuario,
            ),
        )
        devolver int(cur.lastrowid)


def _actualizar_activo(
    usuario: str,
    activo_id: int,
    activo_nombre: str,
    nueva_inversión: flotante,
    nueva_vida: int,
    nueva_vida_util_unidad: str,
    nuevo_modelo: str,
    nueva_unidad: str,
    nuevo_tipo_detalle: str | None,
    clase_registro: str = "equipo_principal",
    active_father_id: int | Ninguno = Ninguno,
    tipo_componente: str | Ninguno = Ninguno,
    initial_use: float = 0.0,
    uso_acumulativo: flotante = 0.0,
    costo_reposicion: float = 0.0,
    fecha_instalacion: str | None = None,
    estado_operativo: str = "Bueno",
    impacta_costo_padre: bool = True,
    impacta_desgaste_padre: bool = False,
) -> Ninguno:
    nueva_inversion = as_positive(nueva_inversion, "Inversión")
    nueva_vida = max(1, int(nueva_vida or 1))
    nuevo_desgaste = (nueva_inversion / nueva_vida) if nueva_inversion > 0 else 0.0
    nueva_unidad = _normalizar_unidad(nueva_unidad)
    nueva_categoria = _categoria_por_equipo(nueva_unidad)
    nueva_vida_util_unidad = _normalizar_vida_util_unidad(nueva_vida_util_unidad)
    nuevo_tipo_detalle = (nuevo_tipo_detalle or "").strip() or None
    nuevo_tipo_impresora = nuevo_tipo_detalle if _es_equipo_impresora(nueva_unidad) else None
    clase_registro = _slug_clase_registro(clase_registro)
    activo_padre_id = int(activo_padre_id) if activo_padre_id and clase_registro != "equipo_principal" else None
    tipo_componente = (tipo_componente o "").strip() o None
    if clase_registro != "equipo_principal":
        tipo_componente = require_text(tipo_componente, "Tipo de componente")
    uso_inicial = max(0.0, float(uso_inicial o 0.0))
    uso_acumulativo = max(0.0, float(uso_acumulativo o 0.0))
    costo_reposicion = max(0.0, float(costo_reposicion or 0.0))
    fecha_instalacion = str(fecha_instalacion or "").strip() or datetime.now().strftime("%Y-%m-%d")
    estado_operativo = _normalizar_estado_operativo(estado_operativo)

    con db_transaction() como conexión:
        _ensure_activos_schema(conn)
        conn.execute(
            """
            UPDATE activos
            SET inversion = ?, categoria = ?, desgaste = ?, modelo = ?, unidad = ?, usuario = ?, tipo_impresora = ?, tipo_detalle = ?, clase_registro = ?, activo_padre_id = ?, tipo_componente = ?, vida_util_unidad = ?, vida_util_valor = ?, uso_inicial = ?, uso_acumulado = ?, costo_reposicion = ?, fecha_instalacion = ?, estado_operativo = ?, impacta_costo_padre = ?, impacta_desgaste_padre = ?
            DONDE id = ?
            """,
            (
                nueva_inversion,
                nueva_categoria,
                nuevo_desgaste,
                (nuevo_modelo o "").strip() o None,
                nueva_unidad,
                usuario,
                nuevo_tipo_impresora,
                nuevo_tipo_detalle,
                clase_registro,
                activo_padre_id,
                tipo_componente,
                nueva_vida_util_unidad,
                float(nueva_vida),
                uso_inicial,
                uso_acumulativo,
                costo_reposicion,
                fecha_instalacion,
                estado_operativo,
                _valor_bool_db(impacta_costo_padre),
                _valor_bool_db(impacta_desgaste_padre),
                int(activo_id),
            ),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALORES (?, ?, ?, ?, ?)
            """,
            (
                activo_nombre,
                "EDICIÓN",
                (
                    f"Actualización de valores (vida útil: {nueva_vida} {nueva_vida_util_unidad}, equipo: {nueva_unidad}, tipo: {nuevo_tipo_detalle or 'N/D'})"
                    + f" · clase: {_label_clase_registro(clase_registro)}"
                    + (f" · activo padre ID: {activo_padre_id}" if activo_padre_id else "")
                    + (f" · componente: {tipo_componente}" if tipo_componente else "")
                ),
                nueva_inversion,
                usuario,
            ),
        )


# =========================================================
# INTERFAZ ACTIVOS
# =========================================================


def render_activos(usuario: str):
    rol = st.session_state.get("rol", "Admin")
    Si el rol no está en ROLES_PERMITIDOS:
        st.error("🚫 Acceso denegado. Solo Admin/Administración puede gestionar activos.")
        devolver

    st.title("🏗️ Gestión Integral de Activos")
    st.caption(
        f"{ACTIVOS_UI_VERSION} · catálogo unificado por tipo de equipo. Ahora puedes clasificar equipos principales, componentes/repuestos y herramientas/accesorios, además de vincularlos a un activo padre."
    )

    intentar:
        df = _load_activos_df()
    excepto Exception como e:
        st.error(f"Error al cargar activos: {e}")
        devolver

    si df no está vacío:
        parent_info = _info_activo_padre(df)
        df = _enrich_components(df, parent_info)
        df["activo_padre_label"] = df["activo_padre_id"].apply(
            lambda x: parent_info.get(int(x), {}).get("label", "Sin relación") if pd.notna(x) else "Sin relación"
        )
        componentes_map = _componentes_por_padre(df)
        st.subheader("🧠 Salud de Activos")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Inversión instalada", f"$ {df['inversion'].sum():,.2f}")
        m2.metric("Desgaste promedio", f"$ {df['desgaste'].mean():.4f}/uso")
        m3.metric("Activos en riesgo alto", int((df["riesgo"] == "🔴 Alto").sum()))
        activo_critico = df.sort_values("desgaste", ascending=False).iloc[0]["equipo"]
        m4.metric("Activo más crítico", str(activo_critico))
        c_reg1, c_reg2, c_reg3 = st.columns(3)
        c_reg1.metric("Equipos principales", int((df["clase_registro"] == "equipo_principal").sum()))
        c_reg2.metric("Componentes / repuestos", int((df["clase_registro"] == "componente").sum()))
        c_reg3.metric("Herramientas / accesorios", int((df["clase_registro"] == "herramienta").sum()))

        with st.expander("🔎 Activos con prioridad de mantenimiento", expanded=False):
            st.dataframe(
                df.sort_values("desgaste", ascending=False)[
                    ["equipo", "unidad", "tipo_detalle", "clase_registro_label", "activo_padre_label", "inversion", "desgaste", "riesgo"]
                ].head(10),
                use_container_width=True,
                ocultar_índice=Verdadero,
            )
            fig_riesgo = px.histogram(
                df,
                x="riesgo",
                color="riesgo",
                title="Distribución de riesgo por desgaste",
                category_orders={"riesgo": ["🔴 Alto", "🟠 Medio", "🟢 Bajo"]},
            )
            st.plotly_chart(fig_riesgo, use_container_width=True)

    demás:
        información_parental = {}
        componentes_map = {}

    with st.expander("➕ Registrar Nuevo Activo", expanded=True):
        st.info("Selecciona el tipo de equipo, define si es equipo principal, componente o herramienta, y asócialo a un activo padre cuando corresponda. Si un tipo no aparece, puedes escribirlo manualmente.")
        c1, c2 , c3 = st.columns(3 )
        nombre_eq = c1.text_input("Nombre del activo", key="activos_nombre_nuevo_v2")
        tipo_unidad_nuevo = c2.selectbox("Tipo de equipo", TIPOS_UNIDAD, key="activos_tipo_equipo_nuevo_v2")
        clase_nueva_label = c3.selectbox("Clase de registro", list(CLASES_REGISTRO.values()), key="activos_clase_registro_nuevo_v2")
        clase_nueva = next((slug for slug, label in CLASES_REGISTRO.items() if label == clase_nueva_label), "equipo_principal")

        opciones_tipo_nuevo = _opciones_tipo_equipo(tipo_unidad_nuevo)
        label_tipo_nuevo = _label_tipo_equipo(tipo_unidad_nuevo)
        placeholder_tipo_nuevo = _placeholder_tipo_equipo(tipo_unidad_nuevo)

        c4, c5, c6 = st.columns(3)
        monto_inv = c4.number_input("Inversión ($)", min_value=0.0, step=10.0, key="activos_inversion_nuevo_v2")
        vida_util = c5.number_input("Vida útil", min_value=1, value=1000, step=1, key="activos_vida_nuevo_v2")
        vida_util_unidad_nuevo = c6.selectbox("Unidad de vida útil", UNIDADES_VIDA_UTIL, key="activos_vida_unidad_nuevo_v2")

        tipo_predefinido_nuevo = None
        tipo_personalizado_nuevo = ""
        if opciones_tipo_nuevo:
            tipo_predefinido_nuevo = st.selectbox(
                label_tipo_nuevo,
                [placeholder_tipo_nuevo] + opciones_tipo_nuevo,
                índice=0,
                key=_key_tipo_equipo("activos_tipo_detalle_nuevo_v2", tipo_unidad_nuevo),
                help="Solo se muestran tipos del equipo seleccionado.",
            )
            if tipo_predefinido_nuevo == placeholder_tipo_nuevo:
                tipo_predefinido_nuevo = None
            if tipo_predefinido_nuevo == OPCION_TIPO_PERSONALIZADO:
                tipo_personalizado_nuevo = st.text_input(
                    f"Especifica {label_tipo_nuevo.lower()}",
                    key=_key_tipo_equipo("activos_tipo_detalle_custom_nuevo_v2", tipo_unidad_nuevo),
                )
        demás:
            tipo_personalizado_nuevo = st.text_input(
                label_tipo_nuevo,
                key=_key_tipo_equipo("activos_tipo_detalle_libre_nuevo_v2", tipo_unidad_nuevo),
                help="Escribe manualmente el tipo específico si no existe una lista para este equipo.",
            )

        modelo = st.text_input("Modelo (opcional)", key="activos_modelo_nuevo_v2")
        extra_nuevo = _render_campos_componente(
            df=df,
            clase_registro=clase_nueva,
            tipo_unidad=tipo_unidad_nuevo,
            vida_util_unidad=vida_util_unidad_nuevo,
            key_prefix="activos_nuevo_componente",
            valores predeterminados={
                "impacta_costo_padre": True if clase_nueva != "equipo_principal" else False,
                "impacta_desgaste_padre": True if clase_nueva == "componente" else False,
            },
        )
        guardar = st.button("🚀 Guardar activo", key="activos_guardar_nuevo_v2", type="primary")
        if guardar:
            intentar:
                tipo_detalle_nuevo = _resolver_tipo_detalle(
                    tipo_unidad_nuevo,
                    tipo_predefinido_nuevo,
                    tipo_personalizado_nuevo,
                )
                aid = _crear_activo(
                    usuario=usuario,
                    equipo=nombre_eq,
                    tipo_unidad=tipo_unidad_nuevo,
                    inversión=mont_inv,
                    vida_util=int(vida_util),
                    vida_util_unidad=vida_util_unidad_nuevo,
                    modelo=modelo,
                    tipo_detalle=tipo_detalle_nuevo,
                    clase_registro=clase_nueva,
                    activo_padre_id=extra_nuevo.get("activo_padre_id"),
                    tipo_componente=extra_nuevo.get("tipo_componente"),
                    uso_inicial=float(extra_nuevo.get("uso_inicial") or 0.0),
                    uso_acumulado=float(extra_nuevo.get("uso_acumulado") or 0.0),
                    costo_reposicion=float(extra_nuevo.get("costo_reposicion") or 0.0),
                    fecha_instalacion=str(extra_nuevo.get("fecha_instalacion") or ""),
                    estado_operativo=str(extra_nuevo.get("estado_operativo") or "Bueno"),
                    impacta_costo_padre=bool(extra_nuevo.get("impacta_costo_padre")),
                    impacta_desgaste_padre=bool(extra_nuevo.get("impacta_desgaste_padre")),
                )
                st.success(f"✅ Activo registrado correctamente. ID #{aid}")
                st.rerun()
            excepto Exception como e:
                st.error(f"Error al registrar activo: {e}")

    st.divider()

    with st.expander("✏️ Editar Activo Existente"):
        si df.empty:
            st.info("No hay activos para editar.")
        demás:
            opciones = {f"{row.equipo} · {row.unidad}": int(row.id) for row in df.itertuples()}
            label = st.selectbox("Seleccionar activo:", list(opciones.keys()))
            activo_id = opciones[label]
            datos = df[df["id"] == asset_id].iloc[0]

            vida_sugerida = int(max(1, round(datos["inversion"] / max(datos["desgaste"], 1e-9)))) if datos["inversion"] > 0 else 1000
            unidad_actual = str(datos.get("unidad") or "Otro")
            idx_unidad = TIPOS_UNIDAD.index(unidad_actual) if unidad_actual in TIPOS_UNIDAD else len(TIPOS_UNIDAD) - 1
            tipo_detalle_actual = str(datos.get("tipo_detalle") or datos.get("tipo_impresora") or "")
            ecl1, ecl2 = st.columns(2)
            nueva_unidad = ecl1.selectbox(
                "Tipo de equipo",
                TIPOS_UNIDAD,
                index=idx_unidad,
                key=f"activos_editar_unidad_{activo_id}",
            )
            clase_actual_slug = _slug_clase_registro(datos.get("clase_registro"))
            clase_actual_label = _label_clase_registro(clase_actual_slug)
            nueva_clase_label = ecl2.selectbox(
                "Clase de registro",
                list(CLASES_REGISTRO.values()),
                index=list(CLASES_REGISTRO.values()).index(clase_actual_label),
                key=f"activos_editar_clase_{activo_id}",
            )
            nueva_clase = next((slug for slug, label in CLASES_REGISTRO.items() if label == nueva_clase_label), "equipo_principal")
            tipo_predefinido_actual, tipo_personalizado_actual = _valor_tipo_para_formulario(nueva_unidad, tipo_detalle_actual)
            opciones_tipo_edicion = _opciones_tipo_equipo(nueva_unidad)
            label_tipo_edicion = _label_tipo_equipo(nueva_unidad)
            placeholder_tipo_edicion = _placeholder_tipo_equipo(nueva_unidad)
            e1, e2 , e3 = st.columns(3 )
            nueva_inv = e1.number_input(
                "Inversión ($)",
                min_value=0.0,
                valor=flotante(datos["inversión"]),
                paso=10.0,
                key=f"activos_editar_inversion_{activo_id}",
            )
            nueva_vida = e2.number_input(
                "Vida útil"
                min_value=1,
                value=int(vida_sugerida),
                paso=1,
                key=f"activos_editar_vida_{activo_id}",
            )
            nueva_vida_unidad = e3.selectbox(
                "Unidad de vida útil",
                UNIDADES DE VIDA ÚTIL,
                index=UNIDADES_VIDA_UTIL.index(_normalizar_vida_util_unidad(datos.get("vida_util_unidad"))),
                key=f"activos_editar_vida_unidad_{activo_id}",
            )

            nuevo_modelo = st.text_input(
                "Modelo",
                valor=str(datos.get("modelo") o ""),
                key=f"activos_editar_modelo_{activo_id}",
            )

            nuevo_tipo_predefinido = None
            nuevo_tipo_personalizado = tipo_personalizado_actual
            if opciones_tipo_edicion:
                opciones_widget_edicion = [placeholder_tipo_edicion] + opciones_tipo_edicion
                valor_inicial_edicion = tipo_predefinido_actual if tipo_predefinido_actual in opciones_tipo_edicion else placeholder_tipo_edicion
                idx_tipo_edicion = opciones_widget_edicion.index(valor_inicial_edicion)
                nuevo_tipo_predefinido = st.selectbox(
                    label_tipo_edicion,
                    opciones_widget_edicion,
                    index=idx_tipo_edicion,
                    key=_key_tipo_equipo(f"activos_editar_tipo_detalle_{activo_id}", nueva_unidad),
                    help="Solo se muestran tipos del equipo seleccionado.",
                )
                if nuevo_tipo_predefinido == placeholder_tipo_edicion:
                    nuevo_tipo_predefinido = None
                if nuevo_tipo_predefinido == OPCION_TIPO_PERSONALIZADO:
                    nuevo_tipo_personalizado = st.text_input(
                        f"Especifique {edition_type_label.lower()}",
                        value=tipo_personalizado_actual,
                        key=_key_tipo_equipo(f"activos_editar_tipo_detalle_custom_{activo_id}", nueva_unidad),
                    )
            demás:
                nuevo_tipo_personalizado = st.text_input(
                    label_tipo_edicion,
                    value=tipo_personalizado_actual,
                    key=_key_tipo_equipo(f"activos_editar_tipo_detalle_libre_{activo_id}", nueva_unidad),
                    help="Escribe manualmente el tipo específico si no existe una lista para este equipo.",
                )

            extra_edicion = _render_campos_componente(
                df=df,
                clase_registro=nueva_clase,
                tipo_unidad=nueva_unidad,
                vida_util_unidad=nueva_vida_unidad,
                key_prefix=f"activos_editar_componente_{activo_id}",
                activo_id=activo_id,
                valores predeterminados={
                    "activo_padre_id": datos.get("activo_padre_id"),
                    "tipo_componente": datos.get("tipo_componente"),
                    "uso_inicial": datos.get("uso_inicial"),
                    "uso_acumulado": datos.get("uso_acumulado"),
                    "costo_reposicion": datos.get("costo_reposicion"),
                    "fecha_instalacion": datos.get("fecha_instalacion"),
                    "estado_operativo": datos.get("estado_operativo"),
                    "impacta_costo_padre": datos.get("impacta_costo_padre", 1),
                    "impacta_desgaste_padre": datos.get("impacta_desgaste_padre", 0),
                },
            )

            guardar_edicion = st.button("💾 Guardar Cambios", key=f"activos_guardar_edicion_{activo_id}")
            si save_edit:
                intentar:
                    nuevo_tipo_detalle = _resolver_tipo_detalle(
                        nueva_unidad,
                        nuevo_tipo_predefinido,
                        nuevo_tipo_personalizado,
                    )
                    _actualizar_activo(
                        usuario=usuario,
                        activo_id=activo_id,
                        activo_nombre=str(datos["equipo"]),
                        nueva_inversion=float(nueva_inv),
                        nueva_vida=int(nueva_vida),
                        nueva_vida_util_unidad=nueva_vida_unidad,
                        nuevo_modelo=nuevo_modelo,
                        nueva_unidad=nueva_unidad,
                        nuevo_tipo_detalle=nuevo_tipo_detalle,
                        clase_registro=nueva_clase,
                        activo_padre_id=extra_edicion.get("activo_padre_id"),
                        tipo_componente=extra_edicion.get("tipo_componente"),
                        uso_inicial=float(extra_edicion.get("uso_inicial") or 0.0),
                        uso_acumulado=float(extra_edicion.get("uso_acumulado") or 0.0),
                        costo_reposicion=float(extra_edicion.get("costo_reposicion") or 0.0),
                        fecha_instalacion=str(extra_edicion.get("fecha_instalacion") or ""),
                        estado_operativo=str(extra_edicion.get("estado_operativo") or "Bueno"),
                        impacta_costo_padre=bool(extra_edicion.get("impacta_costo_padre")),
                        impacta_desgaste_padre=bool(extra_edicion.get("impacta_desgaste_padre")),
                    )
                    st.success("✅ Activo actualizado correctamente.")
                    st.rerun()
                excepto Exception como e:
                    st.error(f"Error al actualizar activo: {e}")

    st.divider()

    t1, t2, t3, t4, t5, t6 , t7 = st.tabs([
        "🖨️ Impresoras",
        "✂️ Cortar",
        "🪪 Plastificación",
        "🔥 Sublimación",
        "🔌 Conexión y Energía",
        "🧰 Otros",
        "📊 Resumen Global",
    ])

    si df.empty:
        con t1:
            st.info("No hay activos registrados todavía.")
        devolver

    con t1:
        st.subheader("Impresoras")
        df_imp = df[df["unidad"].fillna("").str.contains("Impresora", case=False)].copy()
        si no df_imp.empty:
            df_imp["desgaste_cabezal_pct"] = 100.0 - pd.to_numeric(df_imp["vida_cabezal_pct"], errors="coerce")
            c_imp1, c_imp2, c_imp3 = st.columns(3)
            c_imp1.metric("Vida cabezal promedio", f"{df_imp['vida_cabezal_pct'].mean(skipna=True):.2f}%")
            c_imp2.metric("Desgaste cabezal promedio", f"{df_imp['desgaste_cabezal_pct'].mean(skipna=True):.2f}%")
            c_imp3.metric("Páginas impresas (total)", int(df_imp["paginas_impresas"].sum()))

            mostrar_cols = [
                "id", "equipo", "modelo", "tipo_detalle", "clase_registro_label", "vida_cabezal_pct", "vida_rodillo_pct",
                "vida_almohadillas_pct", "desgaste_cabezal_pct", "paginas_impresas", "desgaste", "riesgo"
            ]
            st.dataframe(df_imp[mostrar_cols], use_container_width=True, hide_index=True)

            st.markdown("#### 🩺 Resumen de diagnóstico por impresora")
            opciones_imp = {f"#{int(r.id)} · {r.equipo}": int(r.id) for r in df_imp.itertuples()}
            sel_label = st.selectbox("Seleccionar impresora para ver resumen", list(opciones_imp.keys()), key="activos_diag_sel")
            sel_id = opciones_imp[sel_label]
            resumen = get_printer_diagnostic_summary(sel_id)
            componentes_imp = componentes_map.get(int(sel_id), pd.DataFrame()).copy()
            maint = pd.DataFrame(list_printer_maintenance(sel_id, limit=50))
            costo_mantenimiento = float(pd.to_numeric(maint.get("cost"), errors="coerce").fillna(0).sum()) if not maint.empty and "cost" in maint.columns else 0.0
            costo_componentes = float(pd.to_numeric(componentes_imp.get("costo_reposicion_resuelto"), errors="coerce").fillna(0).sum()) if not componentes_imp.empty else 0.0
            vida_componentes = pd.to_numeric(componentes_imp.get("vida_restante_pct"), errors="coerce") if not componentes_imp.empty else pd.Series(dtype=float)
            proximo_reponer = str(componentes_imp.loc[vida_componentes.idxmin(), "equipo"]) if not vida_componentes.dropna().empty else "N/D"
            if resumen and resumen.get("diagnostico_id"):
                r1, r2, r3, r4, r5, r6 = st.columns(6)
                r1.metric("Último diagnóstico", str(resumen.get("fecha") or "N/D"))
                r2.metric("Páginas totales", int(resumen.get("total_pages") or 0))
                r3.metric("Desgaste cabezal", f"{float(resumen.get('head_wear_pct') or 0.0):.2f}%")
                r4.metric("Depreciación estimada", f"$ {float(resumen.get('depreciation_amount') or 0.0):.4f}")
                r5.metric("Vida rodillo", f"{float(resumen.get('vida_rodillo_pct') or 0.0):.2f}%")
                r6.metric("Vida almohadillas", f"{float(resumen.get('vida_almohadillas_pct') or 0.0):.2f}%")

                st.caption(
                    f"Niveles actuales (ml): BK {float(resumen.get('black_ml') or 0.0):.2f} | C {float(resumen.get('cyan_ml') or 0.0):.2f} | "
                    f"M {float(resumen.get('magenta_ml') or 0.0):.2f} | Y {float(resumen.get('yellow_ml') or 0.0):.2f}"
                )
                st.write("Consumo acumulado por color (ml):", resumen.get("consumos") or {})
                st.caption(
                    f"Sistema tinta: {resumen.get('ink_system_type') or 'N/D'} · Uso tinta: {resumen.get('ink_usage_type') or 'N/D'}"
                )
                rr1, rr2, rr3 = st.columns(3)
                rr1.metric("Costo acumulado componentes", f"$ {costo_componentes:,.2f}")
                rr2.metric("Costo acumulado mantenimiento", f"$ {costo_mantenimiento:,.2f}")
                rr3.metric("Próximo componente a reponer", proximo_reponer)
                _render_componentes_asociados(componentes_map, sel_id, titulo="Componentes, repuestos y accesorios vinculados")
                si resumen.get("low_ink_alerts"):
                    st.warning(f"Alertas de bajo nivel: {', '.join(summary.get('low_ink_alerts') or [])}")
                st.info(
                    "Exactitud de datos: "
                    + str(resumen.get("diagnostic_accuracy") o "estimated")
                    + f" · Confianza: {resumen.get('confidence_level') or 'medium'}"
                )
            demás:
                st.info("Esta impresora aún no tiene diagnósticos técnicos registrados.")

            st.markdown("#### 📜 Historial de diagnósticos")
            historial = pd.DataFrame(list_printer_diagnostics(sel_id, limit=50))
            si no histórico.vacío:
                cols_show = [
                    "id", "fecha", "total_pages", "color_pages", "bw_pages", "borderless_pages", "scanned_pages",
                    "black_ml", "cyan_ml", "magenta_ml", "yellow_ml", "estimation_mode", "confidence_level", "files_count"

                ]
                cols_show = [c para c en cols_show si c en historial.columns]
                st.dataframe(historial[cols_show], use_container_width=True, hide_index=True)
            demás:
                st.caption("Sin historial disponible.")

            st.markdown("#### 💧 Historial de recargas")
            recargas = pd.DataFrame(list_printer_refills(sel_id, limit=50))
            si no se rellena.vacío:
                st.dataframe(refills, use_container_width=True, hide_index=True)
            demás:
                st.caption("No se registraron recargas.")

            st.markdown("#### 🛠️ Historial de mantenimiento")
            si no está vacío:
                st.dataframe(maint, use_container_width=True, hide_index=True)
            demás:
                st.caption("Sin mantenimientos registrados.")
        demás:
            st.info("No hay impresoras activas registradas.")

    con t2:
        st.subheader("Equipos de corte")
        df_corte = df[df["unidad"].fillna("").eq("Corte")].copy()
        st.dataframe(df_corte.drop(columns=["categoria"], errors="ignore"), use_container_width=True, hide_index=True)
        for row in df_corte[df_corte["clase_registro"] == "equipo_principal"].itertuples():
            with st.expander(f"Componentes de corte · {_formatear_activo_relacion(row)}", expanded=False):
                _render_componentes_asociados(componentes_map, int(row.id), titulo="Vinculados a este equipo")

    con t3:
        st.subheader("Equipos de plastificación")
        df_plast = df[df["unidad"].fillna("").eq("Plastificación")].copy()
        st.dataframe(df_plast.drop(columns=["categoria"], errors="ignore"), use_container_width=True, hide_index=True)
        for row in df_plast[df_plast["clase_registro"] == "equipo_principal"].itertuples():
            with st.expander(f"Componentes de plastificación · {_formatear_activo_relacion(row)}", expanded=False):
                _render_componentes_asociados(componentes_map, int(row.id), titulo="Vinculados a este equipo")

    con t4:
        st.subheader("Equipos de sublimación")
        df_subl = df[df["unidad"].fillna("").eq("Sublimación")].copy()
        st.dataframe(df_subl.drop(columns=["categoria"], errors="ignore"), use_container_width=True, hide_index=True)
        para fila en df_subl[df_subl["class_of_records"] == "main_team"].itertuples():
            with st.expander(f"Componentes de sublimación · {_formatear_activo_relacion(row)}", expanded=False):
                _render_componentes_asociados(componentes_map, int(row.id), titulo="Vinculados a este equipo")

    con t5:
        st.subheader("Conexión y energía")
        df_energy = df[df["unidad"].fillna("").eq("Conexión y Energía")].copy()
        st.dataframe(df_energy.drop(columns=["categoria"], errors="ignore"), use_container_width=True, hide_index=True)
        principales_energy = df_energy[df_energy["clase_registro"] == "equipo_principal"].copy()
        para fila en principales_energy.itertuples():
            with st.expander(f"Componentes de conexión/energía · {_formatear_activo_relacion(row)}", expanded=False):
                _render_componentes_asociados(componentes_map, int(row.id), titulo="Vinculados a este equipo")

    con t6:
        st.subheader("Otros equipos")
        df_otro = df[df["unidad"].fillna("").eq("Otro")].copy()
        st.dataframe(df_otro.drop(columns=["categoria"], errors="ignore"), use_container_width=True, hide_index=True)
        for row in df_otro[df_otro["clase_registro"] == "equipo_principal"].itertuples():
            with st.expander(f"Componentes de otros equipos · {_formatear_activo_relacion(row)}", expanded=False):
                _render_componentes_asociados(componentes_map, int(row.id), titulo="Vinculados a este equipo")

    con t 7 :
        c_inv, c_des, c_prom = st.columns(3)
        c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
        c_des.metric("Activos Registrados", len(df))
        c_prom.metric("Desgaste Promedio por Uso", f"$ {df['desgaste'].mean():.4f}")

        fig = px.bar(df, x="equipo", y="inversion", color="unidad", title="Distribución de Inversión por Activo")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("#### Relaciones padre → hijo")
        relacionados = df[df["activo_padre_id"].notna()].copy()
        si está relacionado.vacío:
            st.caption("Aún no hay componentes o accesorios vinculados a equipos principales.")
        demás:
            st.dataframe(
                relacionado[
                    [
                        "identificación",
                        "equipo",
                        "unidad",
                        "clase_registro_label",
                        "activo_padre_label",
                        "tipo_componente",
                        "tipo_detalle",
                        "costo_reposicion_resuelto",
                        "fecha_instalacion",
                        "impacta_costo_padre",
                        "impacta_desgaste_padre",
                    ]
                ].asignar(
                    impacta_costo_padre=lambda x: x["impacta_costo_padre"].map({1: "Sí", 0: "No"}),
                    impacta_desgaste_padre=lambda x: x["impacta_desgaste_padre"].map({1: "Sí", 0: "No"}),
                ),
                use_container_width=True,
                ocultar_índice=Verdadero,
            )
