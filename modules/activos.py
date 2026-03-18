from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, require_text
from services.diagnostics_service import (
    get_printer_diagnostic_summary,
    list_printer_diagnostics,
    list_printer_refills,
    list_printer_maintenance,
)

ALLOWED_ROLES = {"Admin", "Administration", "Administracion"}
TIPOS_UNIDAD = [
    "Impresora",
    "Corte",
    "Plastificación",
    "Sublimación",
    "Otro",
]
TIPOS_POR_EQUIPO = {
    "Impresora": {
        "categoria": "Impresora",
        "label": "Tipo de impresora",
        "opciones": [
            "Tanque de tinta",
            "Cartucho",
            "Láser monocromática",
            "Láser a color",
            "Sublimación",
        ],
    },
    "Corte": {
        "categoria": "Corte",
        "label": "Tipo de corte",
        "opciones": [
            "Cameo",
            "Cricut",
            "Guillotina",
            "Guillotina manual",
            "Tijeras",
            "Exacto",
            "Bisturí",
        ],
    },
    "Plastificación": {
        "categoria": "Plastificación",
        "label": "Tipo de máquina de plastificación",
        "opciones": [
            "Plastificadora térmica",
            "Plastificadora de credenciales",
            "Laminadora en frío",
            "Laminadora en caliente",
        ],
    },
    "Sublimación": {
        "categoria": "Sublimación",
        "label": "Tipo de sublimación",
        "opciones": [
            "Plancha",
            "Tapete",
            "Cintas",
            "Horno",
            "Resistencia",
            "Taza",
        ],
    },
    "Otro": {
        "categoria": "Otro",
        "label": "Detalle del equipo",
        "opciones": [],
    },
}
OPCION_TIPO_PERSONALIZADO = "Otro / No está en la lista"
ACTIVOS_UI_VERSION = "Activos UI v2"


def _equipo_config(tipo_equipo: str | None) -> dict:
    return TIPOS_POR_EQUIPO.get(str(tipo_equipo or "").strip(), TIPOS_POR_EQUIPO["Otro"])


def _es_equipo_impresora(tipo_equipo: str | None) -> bool:
    return str(tipo_equipo or "").strip().lower() == "impresora"


def _categoria_por_equipo(tipo_equipo: str | None) -> str:
    return str(_equipo_config(tipo_equipo).get("categoria") or "Otro")


def _normalizar_unidad(tipo_equipo: str | None) -> str:
    valor = str(tipo_equipo or "").strip()
    equivalencias = {
        "Corte / Plotter (Cameo)": "Corte",
        "Plancha de Sublimación": "Sublimación",
    }
    return equivalencias.get(valor, valor or "Otro")


def _migrar_valores_legados_activos(conn) -> None:
    unidades_legadas = {
        "Corte / Plotter (Cameo)": "Corte",
        "Plancha de Sublimación": "Sublimación",
    }
    for valor_anterior, valor_nuevo in unidades_legadas.items():
        conn.execute(
            "UPDATE activos SET unidad = ?, categoria = ? WHERE unidad = ?",
            (valor_nuevo, _categoria_por_equipo(valor_nuevo), valor_anterior),
        )


def _opciones_tipo_equipo(tipo_equipo: str | None) -> list[str]:
    opciones = list(_equipo_config(tipo_equipo).get("opciones") or [])
    return opciones + [OPCION_TIPO_PERSONALIZADO] if opciones else []


def _label_tipo_equipo(tipo_equipo: str | None) -> str:
    return str(_equipo_config(tipo_equipo).get("label") or "Detalle del equipo")


def _resolver_tipo_detalle(tipo_equipo: str, tipo_predefinido: str | None, tipo_personalizado: str | None) -> str | None:
    opciones = _equipo_config(tipo_equipo).get("opciones") or []
    tipo_predefinido = str(tipo_predefinido or "").strip()
    tipo_personalizado = str(tipo_personalizado or "").strip()
    if tipo_predefinido and tipo_predefinido != OPCION_TIPO_PERSONALIZADO:
        return tipo_predefinido
    if tipo_predefinido == OPCION_TIPO_PERSONALIZADO or not opciones:
        return require_text(tipo_personalizado, _label_tipo_equipo(tipo_equipo))
    return None

def _valor_tipo_para_formulario(tipo_equipo: str | None, valor_actual: str | None) -> tuple[str | None, str]:
    valor_actual = str(valor_actual or "").strip()
    opciones = _equipo_config(tipo_equipo).get("opciones") or []
    if not valor_actual:
        return (opciones[0] if opciones else None), ""
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
    }
    for col, alter_sql in optional_cols.items():
        if col not in cols:
            conn.execute(alter_sql)

    _migrar_valores_legados_activos(conn)


def _load_activos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        rows = conn.execute(
            """
            SELECT
                id,
                equipo,
                categoria,
                inversion,
                unidad,
                desgaste,
                modelo,
                costo_hora,
                COALESCE(vida_cabezal_pct, NULL) AS vida_cabezal_pct,
                COALESCE(vida_rodillo_pct, NULL) AS vida_rodillo_pct,
                COALESCE(vida_almohadillas_pct, NULL) AS vida_almohadillas_pct,
                COALESCE(paginas_impresas, 0) AS paginas_impresas,
                tipo_impresora,
                COALESCE(tipo_detalle, tipo_impresora) AS tipo_detalle,
                fecha,
                COALESCE(activo, 1) AS activo
            FROM activos
            WHERE COALESCE(activo, 1) = 1
            ORDER BY id DESC
            """
        ).fetchall()

    if not rows:
        return pd.DataFrame(
            columns=[
                "id", "equipo", "categoria", "inversion", "unidad", "desgaste", "modelo", "costo_hora",
                "vida_cabezal_pct", "vida_rodillo_pct", "vida_almohadillas_pct", "paginas_impresas", "tipo_impresora", "tipo_detalle", "fecha", "activo"
            ]
        )

    df = pd.DataFrame([dict(r) for r in rows])
    df["unidad"] = df["unidad"].apply(_normalizar_unidad)
    df["tipo_detalle"] = df["tipo_detalle"].where(df["tipo_detalle"].notna(), df["tipo_impresora"])
    df["inversion"] = pd.to_numeric(df["inversion"], errors="coerce").fillna(0.0)
    df["desgaste"] = pd.to_numeric(df["desgaste"], errors="coerce").fillna(0.0)
    df["vida_cabezal_pct"] = pd.to_numeric(df.get("vida_cabezal_pct"), errors="coerce")
    df["vida_rodillo_pct"] = pd.to_numeric(df.get("vida_rodillo_pct"), errors="coerce")
    df["vida_almohadillas_pct"] = pd.to_numeric(df.get("vida_almohadillas_pct"), errors="coerce")
    df["paginas_impresas"] = pd.to_numeric(df.get("paginas_impresas"), errors="coerce").fillna(0).astype(int)
    ranking_riesgo = df["desgaste"].rank(pct=True, method="average").fillna(0)
    df["riesgo"] = np.where(
        ranking_riesgo >= 0.80,
        "🔴 Alto",
        np.where(ranking_riesgo >= 0.50, "🟠 Medio", "🟢 Bajo"),
    )
    return df


def _crear_activo(
    usuario: str,
    equipo: str,
    tipo_unidad: str,
    categoria: str,
    inversion: float,
    vida_util: int,
    modelo: str,
    tipo_detalle: str | None,
) -> int:
    equipo = require_text(equipo, "Nombre del activo")
    tipo_unidad = _normalizar_unidad(require_text(tipo_unidad, "Tipo de equipo"))
    categoria = _categoria_por_equipo(tipo_unidad)
    inversion = as_positive(inversion, "Inversión", allow_zero=False)
    vida_util = max(1, int(vida_util or 1))
    desgaste_unitario = inversion / vida_util
    tipo_detalle = (tipo_detalle or "").strip() or None
    tipo_impresora = tipo_detalle if _es_equipo_impresora(tipo_unidad) else None

    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO activos
            (equipo, modelo, categoria, inversion, unidad, desgaste, costo_hora, usuario, activo, estado, tipo_impresora, tipo_detalle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'activo', ?, ?)
            """,
            (
                equipo,
                (modelo or "").strip() or None,
                categoria,
                inversion,
                tipo_unidad,
                desgaste_unitario,
                0.0,
                usuario,
                tipo_impresora,
                tipo_detalle,
            ),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (equipo, "CREACIÓN", f"Registro inicial (vida útil: {vida_util})", inversion, usuario),
        )
        return int(cur.lastrowid)


def _actualizar_activo(
    usuario: str,
    activo_id: int,
    activo_nombre: str,
    nueva_inversion: float,
    nueva_vida: int,
    nueva_categoria: str,
    nuevo_modelo: str,
    nueva_unidad: str,
    nuevo_tipo_detalle: str | None,
) -> None:
    nueva_inversion = as_positive(nueva_inversion, "Inversión")
    nueva_vida = max(1, int(nueva_vida or 1))
    nuevo_desgaste = (nueva_inversion / nueva_vida) if nueva_inversion > 0 else 0.0
    nueva_unidad = _normalizar_unidad(nueva_unidad)
    nueva_categoria = _categoria_por_equipo(nueva_unidad)
    nuevo_tipo_detalle = (nuevo_tipo_detalle or "").strip() or None
    nuevo_tipo_impresora = nuevo_tipo_detalle if _es_equipo_impresora(nueva_unidad) else None

    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        conn.execute(
            """
            UPDATE activos
            SET inversion = ?, categoria = ?, desgaste = ?, modelo = ?, unidad = ?, usuario = ?, tipo_impresora = ?, tipo_detalle = ?
            WHERE id = ?
            """,
            (
                nueva_inversion,
                nueva_categoria,
                nuevo_desgaste,
                (nuevo_modelo or "").strip() or None,
                nueva_unidad,
                usuario,
                nuevo_tipo_impresora,
                nuevo_tipo_detalle,
                int(activo_id),
            ),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                activo_nombre,
                "EDICIÓN",
                f"Actualización de valores (vida útil: {nueva_vida}, equipo: {nueva_unidad}, tipo: {nuevo_tipo_detalle or 'N/D'})",
                nueva_inversion,
                usuario,
            ),
        )


# =========================================================
# INTERFAZ ACTIVOS
# =========================================================
def render_activos(usuario: str):
    role = st.session_state.get("rol", "Admin")
    if role not in ALLOWED_ROLES:
        st.error("🚫 Acceso denegado. Solo Admin/Administración puede gestionar activos.")
        return

    st.title("🏗️ Gestión Integral de Activos")
    st.caption(
        f"{ACTIVOS_UI_VERSION} · catálogo unificado por tipo de equipo. Si ves opciones legadas como `Plancha de Sublimación`, recarga la app para tomar esta versión."
    )

    try:
        df = _load_activos_df()
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")
        return

    if not df.empty:
        st.subheader("🧠 Salud de Activos")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Inversión instalada", f"$ {df['inversion'].sum():,.2f}")
        m2.metric("Desgaste promedio", f"$ {df['desgaste'].mean():.4f}/uso")
        m3.metric("Activos en riesgo alto", int((df["riesgo"] == "🔴 Alto").sum()))
        activo_critico = df.sort_values("desgaste", ascending=False).iloc[0]["equipo"]
        m4.metric("Activo más crítico", str(activo_critico))

        with st.expander("🔎 Activos con prioridad de mantenimiento", expanded=False):
            st.dataframe(
                df.sort_values("desgaste", ascending=False)[
                    ["equipo", "unidad", "tipo_detalle", "inversion", "desgaste", "riesgo"]
                ].head(10),
                use_container_width=True,
                hide_index=True,
            )
            fig_riesgo = px.histogram(
                df,
                x="riesgo",
                color="riesgo",
                title="Distribución de riesgo por desgaste",
                category_orders={"riesgo": ["🔴 Alto", "🟠 Medio", "🟢 Bajo"]},
            )
            st.plotly_chart(fig_riesgo, use_container_width=True)

    with st.expander("➕ Registrar Nuevo Activo", expanded=True):
        st.info("Esta es la versión renovada del formulario de activos. La categoría se calcula automáticamente según el tipo de equipo.")

        with st.form("form_activos_pro_v2"):
            c1, c2 = st.columns(2)
            nombre_eq = c1.text_input("Nombre del activo")
            tipo_unidad_nuevo = c2.selectbox("Tipo de equipo", TIPOS_UNIDAD, key="activos_tipo_equipo_nuevo_v2")

            opciones_tipo_nuevo = _opciones_tipo_equipo(tipo_unidad_nuevo)
            label_tipo_nuevo = _label_tipo_equipo(tipo_unidad_nuevo)

            c3, c4, c5 = st.columns(3)
            monto_inv = c3.number_input("Inversión ($)", min_value=0.0, step=10.0)
            vida_util = c4.number_input("Vida útil (usos)", min_value=1, value=1000, step=1)
            c5.text_input("Categoría detectada", value=_categoria_por_equipo(tipo_unidad_nuevo), disabled=True)

            tipo_predefinido_nuevo = None
            tipo_personalizado_nuevo = ""
            if opciones_tipo_nuevo:
                tipo_predefinido_nuevo = st.selectbox(label_tipo_nuevo, opciones_tipo_nuevo, key="activos_tipo_detalle_nuevo_v2")
                if tipo_predefinido_nuevo == OPCION_TIPO_PERSONALIZADO:
                    tipo_personalizado_nuevo = st.text_input(f"Especifica {label_tipo_nuevo.lower()}", key="activos_tipo_detalle_custom_nuevo_v2")
            else:
                tipo_personalizado_nuevo = st.text_input(label_tipo_nuevo, key="activos_tipo_detalle_libre_nuevo_v2")

            modelo = st.text_input("Modelo (opcional)")
            guardar = st.form_submit_button("🚀 Guardar activo")
        if guardar:
            try:
                tipo_detalle_nuevo = _resolver_tipo_detalle(
                    tipo_unidad_nuevo,
                    tipo_predefinido_nuevo,
                    tipo_personalizado_nuevo,
                )
                aid = _crear_activo(
                    usuario=usuario,
                    equipo=nombre_eq,
                    tipo_unidad=tipo_unidad_nuevo,
                    categoria=_categoria_por_equipo(tipo_unidad_nuevo),
                    inversion=monto_inv,
                    vida_util=int(vida_util),
                    modelo=modelo,
                    tipo_detalle=tipo_detalle_nuevo,
                )
                st.success(f"✅ Activo registrado correctamente. ID #{aid}")
                st.rerun()
            except Exception as e:
                st.error(f"Error al registrar activo: {e}")

    st.divider()

    with st.expander("✏️ Editar Activo Existente"):
        if df.empty:
            st.info("No hay activos para editar.")
        else:
            opciones = {f"{row.equipo} · {row.unidad}": int(row.id) for row in df.itertuples()}
            label = st.selectbox("Seleccionar activo:", list(opciones.keys()))
            activo_id = opciones[label]
            datos = df[df["id"] == activo_id].iloc[0]

            vida_sugerida = int(max(1, round(datos["inversion"] / max(datos["desgaste"], 1e-9)))) if datos["inversion"] > 0 else 1000
            unidad_actual = str(datos.get("unidad") or "Otro")
            idx_unidad = TIPOS_UNIDAD.index(unidad_actual) if unidad_actual in TIPOS_UNIDAD else len(TIPOS_UNIDAD) - 1
            tipo_detalle_actual = str(datos.get("tipo_detalle") or datos.get("tipo_impresora") or "")
            nueva_unidad = st.selectbox(
                "Tipo de equipo",
                TIPOS_UNIDAD,
                index=idx_unidad,
                key=f"activos_editar_unidad_v2_{activo_id}",
            )
            tipo_predefinido_actual, tipo_personalizado_actual = _valor_tipo_para_formulario(nueva_unidad, tipo_detalle_actual)
            opciones_tipo_edicion = _opciones_tipo_equipo(nueva_unidad)
            label_tipo_edicion = _label_tipo_equipo(nueva_unidad)

            with st.form("editar_activo"):
                e1, e2, e3 = st.columns(3)
                nueva_inv = e1.number_input("Inversión ($)", min_value=0.0, value=float(datos["inversion"]), step=10.0)
                nueva_vida = e2.number_input("Vida útil", min_value=1, value=int(vida_sugerida), step=1)
                e3.text_input("Categoría detectada", value=_categoria_por_equipo(nueva_unidad), disabled=True)

                nuevo_modelo = st.text_input("Modelo", value=str(datos.get("modelo") or ""))

                nuevo_tipo_predefinido = None
                nuevo_tipo_personalizado = tipo_personalizado_actual
                if opciones_tipo_edicion:
                    idx_tipo_edicion = opciones_tipo_edicion.index(tipo_predefinido_actual) if tipo_predefinido_actual in opciones_tipo_edicion else 0
                    nuevo_tipo_predefinido = st.selectbox(
                        label_tipo_edicion,
                        opciones_tipo_edicion,
                        index=idx_tipo_edicion,
                        key=f"activos_editar_tipo_detalle_v2_{activo_id}",
                    )
                    if nuevo_tipo_predefinido == OPCION_TIPO_PERSONALIZADO:
                        nuevo_tipo_personalizado = st.text_input(
                            f"Especifica {label_tipo_edicion.lower()}",
                            value=tipo_personalizado_actual,
                            key=f"activos_editar_tipo_detalle_custom_v2_{activo_id}",
                        )
                else:
                    nuevo_tipo_personalizado = st.text_input(
                        label_tipo_edicion,
                        value=tipo_personalizado_actual,
                        key=f"activos_editar_tipo_detalle_libre_v2_{activo_id}",
                    )

                guardar_edicion = st.form_submit_button("💾 Guardar Cambios")

            if guardar_edicion:
                try:
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
                        nueva_categoria=_categoria_por_equipo(nueva_unidad),
                        nuevo_modelo=nuevo_modelo,
                        nueva_unidad=nueva_unidad,
                        nuevo_tipo_detalle=nuevo_tipo_detalle,
                    )
                    st.success("✅ Activo actualizado correctamente.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error al registrar activo: {e}")

    st.divider()

    with st.expander("✏️ Editar Activo Existente"):
        if df.empty:
            st.info("No hay activos para editar.")
        else:
            opciones = {f"{row.equipo} · {row.unidad}": int(row.id) for row in df.itertuples()}
            label = st.selectbox("Seleccionar activo:", list(opciones.keys()))
            activo_id = opciones[label]
            datos = df[df["id"] == activo_id].iloc[0]

            vida_sugerida = int(max(1, round(datos["inversion"] / max(datos["desgaste"], 1e-9)))) if datos["inversion"] > 0 else 1000
            unidad_actual = str(datos.get("unidad") or "Otro")
            idx_unidad = TIPOS_UNIDAD.index(unidad_actual) if unidad_actual in TIPOS_UNIDAD else len(TIPOS_UNIDAD) - 1
            tipo_detalle_actual = str(datos.get("tipo_detalle") or datos.get("tipo_impresora") or "")
            nueva_unidad = st.selectbox(
                "Equipo",
                TIPOS_UNIDAD,
                index=idx_unidad,
                key=f"activos_editar_unidad_{activo_id}",
            )
            tipo_predefinido_actual, tipo_personalizado_actual = _valor_tipo_para_formulario(nueva_unidad, tipo_detalle_actual)
            opciones_tipo_edicion = _opciones_tipo_equipo(nueva_unidad)
            label_tipo_edicion = _label_tipo_equipo(nueva_unidad)

            with st.form("editar_activo"):
                e1, e2 = st.columns(2)
                nueva_inv = e1.number_input("Inversión ($)", min_value=0.0, value=float(datos["inversion"]), step=10.0)
                nueva_vida = e2.number_input("Vida útil", min_value=1, value=int(vida_sugerida), step=1)

                u1, u2 = st.columns(2)
                u1.caption(
                    f"Equipo seleccionado: **{nueva_unidad}** · Categoría automática: **{_categoria_por_equipo(nueva_unidad)}**"
                )
                nuevo_modelo = u2.text_input("Modelo", value=str(datos.get("modelo") or ""))

                nuevo_tipo_predefinido = None
                nuevo_tipo_personalizado = tipo_personalizado_actual
                if opciones_tipo_edicion:
                    idx_tipo_edicion = opciones_tipo_edicion.index(tipo_predefinido_actual) if tipo_predefinido_actual in opciones_tipo_edicion else 0
                    nuevo_tipo_predefinido = st.selectbox(
                        label_tipo_edicion,
                        opciones_tipo_edicion,
                        index=idx_tipo_edicion,
                        key=f"activos_editar_tipo_detalle_{activo_id}",
                    )
                    if nuevo_tipo_predefinido == OPCION_TIPO_PERSONALIZADO:
                        nuevo_tipo_personalizado = st.text_input(
                            f"Especifica {label_tipo_edicion.lower()}",
                            value=tipo_personalizado_actual,
                            key=f"activos_editar_tipo_detalle_custom_{activo_id}",
                        )
                else:
                    nuevo_tipo_personalizado = st.text_input(
                        label_tipo_edicion,
                        value=tipo_personalizado_actual,
                        key=f"activos_editar_tipo_detalle_libre_{activo_id}",
                    )

                guardar_edicion = st.form_submit_button("💾 Guardar Cambios")

            if guardar_edicion:
                try:
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
                        nueva_categoria=_categoria_por_equipo(nueva_unidad),
                        nuevo_modelo=nuevo_modelo,
                        nueva_unidad=nueva_unidad,
                        nuevo_tipo_detalle=nuevo_tipo_detalle,
                    )
                    st.success("✅ Activo actualizado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al actualizar activo: {e}")

    st.divider()

    t1, t2, t3, t4, t5, t6 = st.tabs([
        "🖨️ Impresoras",
        "✂️ Corte",
        "🪪 Plastificación",
        "🔥 Sublimación",
        "🧰 Otros",
       "📊 Resumen Global",
    ])

    if df.empty:
        with t1:
            st.info("No hay activos registrados todavía.")
        return

    with t1:
        st.subheader("Impresoras")
        df_imp = df[df["unidad"].fillna("").str.contains("Impresora", case=False)].copy()
        if not df_imp.empty:
            df_imp["desgaste_cabezal_pct"] = 100.0 - pd.to_numeric(df_imp["vida_cabezal_pct"], errors="coerce")
            c_imp1, c_imp2, c_imp3 = st.columns(3)
            c_imp1.metric("Vida cabezal promedio", f"{df_imp['vida_cabezal_pct'].mean(skipna=True):.2f}%")
            c_imp2.metric("Desgaste cabezal promedio", f"{df_imp['desgaste_cabezal_pct'].mean(skipna=True):.2f}%")
            c_imp3.metric("Páginas impresas (total)", int(df_imp["paginas_impresas"].sum()))

            mostrar_cols = [
                "id", "equipo", "modelo", "tipo_detalle", "vida_cabezal_pct", "vida_rodillo_pct",
                "vida_almohadillas_pct", "desgaste_cabezal_pct", "paginas_impresas", "desgaste", "riesgo"
            ]
            st.dataframe(df_imp[mostrar_cols], use_container_width=True, hide_index=True)

            st.markdown("#### 🩺 Resumen de diagnóstico por impresora")
            opciones_imp = {f"#{int(r.id)} · {r.equipo}": int(r.id) for r in df_imp.itertuples()}
            sel_label = st.selectbox("Seleccionar impresora para ver resumen", list(opciones_imp.keys()), key="activos_diag_sel")
            sel_id = opciones_imp[sel_label]
            resumen = get_printer_diagnostic_summary(sel_id)
            if resumen and resumen.get("diagnostico_id"):
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Último diagnóstico", str(resumen.get("fecha") or "N/D"))
                r2.metric("Páginas totales", int(resumen.get("total_pages") or 0))
                r3.metric("Desgaste cabezal", f"{float(resumen.get('head_wear_pct') or 0.0):.2f}%")
                r4.metric("Depreciación estimada", f"$ {float(resumen.get('depreciation_amount') or 0.0):.4f}")

                st.caption(
                    f"Niveles actuales (ml): BK {float(resumen.get('black_ml') or 0.0):.2f} | C {float(resumen.get('cyan_ml') or 0.0):.2f} | "
                    f"M {float(resumen.get('magenta_ml') or 0.0):.2f} | Y {float(resumen.get('yellow_ml') or 0.0):.2f}"
                )
                st.write("Consumo acumulado por color (ml):", resumen.get("consumos") or {})
                st.caption(
                    f"Sistema tinta: {resumen.get('ink_system_type') or 'N/D'} · Uso tinta: {resumen.get('ink_usage_type') or 'N/D'}"
                )
                if resumen.get("low_ink_alerts"):
                    st.warning(f"Alertas de bajo nivel: {', '.join(resumen.get('low_ink_alerts') or [])}")
                st.info(
                    "Exactitud de datos: "
                    + str(resumen.get("diagnostic_accuracy") or "estimated")
                    + f" · Confianza: {resumen.get('confidence_level') or 'medium'}"
                )
            else:
                st.info("Esta impresora aún no tiene diagnósticos técnicos registrados.")

            st.markdown("#### 📜 Historial de diagnósticos")
            historial = pd.DataFrame(list_printer_diagnostics(sel_id, limit=50))
            if not historial.empty:
                cols_show = [
                    "id", "fecha", "total_pages", "color_pages", "bw_pages", "borderless_pages", "scanned_pages",
                    "black_ml", "cyan_ml", "magenta_ml", "yellow_ml", "estimation_mode", "confidence_level", "files_count"
                ]
                cols_show = [c for c in cols_show if c in historial.columns]
                st.dataframe(historial[cols_show], use_container_width=True, hide_index=True)
            else:
                st.caption("Sin historial disponible.")

            st.markdown("#### 💧 Historial de recargas")
            refills = pd.DataFrame(list_printer_refills(sel_id, limit=50))
            if not refills.empty:
                st.dataframe(refills, use_container_width=True, hide_index=True)
            else:
                st.caption("Sin recargas registradas.")

            st.markdown("#### 🛠️ Historial de mantenimiento")
            maint = pd.DataFrame(list_printer_maintenance(sel_id, limit=50))
            if not maint.empty:
                st.dataframe(maint, use_container_width=True, hide_index=True)
            else:
                st.caption("Sin mantenimientos registrados.")
        else:
            st.info("No hay impresoras activas registradas.")

    with t2:
        st.subheader("Equipos de corte")
        df_corte = df[df["unidad"].fillna("").eq("Corte")].copy()
        st.dataframe(df_corte, use_container_width=True, hide_index=True)

    with t3:
        st.subheader("Equipos de plastificación")
        df_plast = df[df["unidad"].fillna("").eq("Plastificación")].copy()
        st.dataframe(df_plast, use_container_width=True, hide_index=True)

    with t4:
        st.subheader("Equipos de sublimación")
        df_subl = df[df["unidad"].fillna("").eq("Sublimación")].copy()
        st.dataframe(df_subl, use_container_width=True, hide_index=True)

    with t5:
        st.subheader("Otros equipos")
        df_otro = df[df["unidad"].fillna("").eq("Otro")].copy()
        st.dataframe(df_otro, use_container_width=True, hide_index=True)

    with t6:
        c_inv, c_des, c_prom = st.columns(3)
        c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
        c_des.metric("Activos Registrados", len(df))
        c_prom.metric("Desgaste Promedio por Uso", f"$ {df['desgaste'].mean():.4f}")

        fig = px.bar(df, x="equipo", y="inversion", color="unidad", title="Distribución de Inversión por Activo")
        st.plotly_chart(fig, use_container_width=True)

