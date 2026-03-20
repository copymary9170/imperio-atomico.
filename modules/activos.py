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
    "Conexión y Energía",
    "Otro",
]
CLASES_REGISTRO = {
    "equipo_principal": "Equipo principal",
    "componente": "Componente / Repuesto",
    "herramienta": "Herramienta / Accesorio",
}
UNIDADES_VIDA_UTIL = [
    "usos",
    "páginas",
    "cortes",
    "trabajos",
    "horas",
    "meses",
    "manual",
]
TIPOS_POR_EQUIPO = {
    "Impresora": {
        "categoria": "Impresora",
        "label": "Tipo de impresora",
        "placeholder": "Selecciona el tipo de impresora",
        "opciones": [
            "Tanque de tinta",
            "Cartucho",
            "Láser monocromática",
            "Láser a color",
            "Impresora de sublimación",
            "Plotter de impresión",
            "Impresora térmica",
            "Impresora matricial",
        ],
    },
    "Corte": {
        "categoria": "Corte",
        "label": "Tipo de corte",
        "placeholder": "Selecciona el tipo de corte",
        "opciones": [
            "Cameo",
            "Cricut",
            "Plotter de corte",
            "Guillotina",
            "Guillotina manual",
            "Cuchilla",
            "Cuchilla premium",
            "Tapete de corte",
            "Tapete 12x12",
            "Tapete 12x24",
            "Espátula",
            "Kit de desbaste",
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
            "Papel de sublimación",
        ],
    },
    "Conexión y Energía": {
        "categoria": "Conexión y Energía",
        "label": "Tipo de conexión o energía",
        "placeholder": "Selecciona el tipo de conexión o energía",
        "opciones": [
            "Regleta",
            "UPS",
            "Regulador de voltaje",
            "Cable USB",
            "Cable de poder",
            "Cable HDMI",
            "Cable de red",
            "Extensión eléctrica",
            "Adaptador de corriente",
            "Fuente de poder",
            "Transformador",
            "Hub USB",
            "Conector",
            "Cargador",
            "Convertidor",
        ],
    },
    "Otro": {
        "categoria": "Otro",
        "label": "Detalle del equipo",
        "placeholder": "Escribe el detalle del equipo",
        "opciones": [
            "Repuesto genérico",
            "Herramienta manual",
            "Accesorio",
            "Componente eléctrico",
            "Componente mecánico",
            "Consumible durable",
        ],
    },
}
OPCION_TIPO_PERSONALIZADO = "Otro / No está en la lista"
ACTIVOS_UI_VERSION = "Activos UI v 4 "


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


def _slug_clase_registro(clase_registro: str | None) -> str:
    valor = str(clase_registro or "equipo_principal").strip().lower()
    return valor if valor in CLASES_REGISTRO else "equipo_principal"


def _label_clase_registro(clase_registro: str | None) -> str:
    return CLASES_REGISTRO.get(_slug_clase_registro(clase_registro), CLASES_REGISTRO["equipo_principal"])


def _valor_bool_db(valor: bool | int | None) -> int:
    return 1 if bool(valor) else 0


def _normalizar_vida_util_unidad(valor: str | None) -> str:
    texto = str(valor or "usos").strip().lower()
    return texto if texto in UNIDADES_VIDA_UTIL else "usos"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _estado_componente_desde_vida(vida_restante_pct: float | None) -> str:
    if vida_restante_pct is None:
        return "Sin seguimiento"
    if vida_restante_pct <= 20:
        return "Crítico"
    if vida_restante_pct <= 50:
        return "En seguimiento"
    return "Operativo"


def _calcular_vida_restante_pct(uso_acumulado: float | int | None, vida_util_valor: float | int | None) -> float | None:
    vida = _safe_float(vida_util_valor, 0.0)
    if vida <= 0:
        return None
    uso = max(0.0, _safe_float(uso_acumulado, 0.0))
    restante = 100.0 - ((uso / vida) * 100.0)
    return max(0.0, min(100.0, restante))


def _formatear_activo_relacion(row: dict | pd.Series, incluir_unidad: bool = True) -> str:
    if isinstance(row, pd.Series):
        data = row.to_dict()
    elif isinstance(row, dict):
        data = dict(row)
    elif hasattr(row, "_asdict"):
        data = row._asdict()
    else:
        data = dict(getattr(row, "__dict__", {}))
    equipo = str(data.get("equipo") or "Activo").strip()
    modelo = str(data.get("modelo") or "").strip()
    unidad = str(data.get("unidad") or "").strip()
    partes = [f"#{int(data.get('id') or 0)} · {equipo}"]
    if modelo:
        partes.append(f"({modelo})")
    if incluir_unidad and unidad:
        partes.append(f"· {unidad}")
    return " ".join(partes).strip()


def _opciones_activo_padre(df: pd.DataFrame, excluir_id: int | None = None) -> dict[str, int]:
    if df.empty:
        return {}
    base = df.copy()
    if excluir_id is not None:
        base = base[base["id"] != int(excluir_id)]
    base = base[base["clase_registro"].fillna("equipo_principal") == "equipo_principal"].copy()
    if base.empty:
        return {}
    base = base.sort_values(["unidad", "equipo", "id"], ascending=[True, True, True])
    return {_formatear_activo_relacion(row): int(row["id"]) for _, row in base.iterrows()}


def _info_activo_padre(df: pd.DataFrame) -> dict[int, dict]:
    if df.empty:
        return {}
    return {
        int(row["id"]): {
            "equipo": str(row.get("equipo") or ""),
            "modelo": str(row.get("modelo") or ""),
            "unidad": str(row.get("unidad") or ""),
            "label": _formatear_activo_relacion(row),
        }
        for _, row in df.iterrows()
    }


def _componentes_por_padre(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    if df.empty or "activo_padre_id" not in df.columns:
        return {}
    hijos = df[df["activo_padre_id"].notna()].copy()
    if hijos.empty:
        return {}
    grupos: dict[int, pd.DataFrame] = {}
    for padre_id, grupo in hijos.groupby(hijos["activo_padre_id"].astype(int)):
        grupos[int(padre_id)] = grupo.sort_values(["unidad", "equipo", "id"], ascending=[True, True, True]).copy()
    return grupos


def _agregar_metricas_relacionadas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    base = df.copy()
    for col, default in (
        ("componentes_vinculados", 0),
        ("componentes_criticos_vinculados", 0),
        ("costo_componentes_asociados", 0.0),
        ("vida_restante_minima_vinculada", np.nan),
    ):
        if col not in base.columns:
            base[col] = default

    if "activo_padre_id" not in base.columns:
        base["inversion_total_relacionada"] = base["inversion"]
        return base

    relacionados = base[base["activo_padre_id"].notna()].copy()
    if relacionados.empty:
        base["inversion_total_relacionada"] = base["inversion"]
        return base

    relacionados["activo_padre_id"] = pd.to_numeric(relacionados["activo_padre_id"], errors="coerce")
    relacionados = relacionados[relacionados["activo_padre_id"].notna()].copy()
    if relacionados.empty:
        base["inversion_total_relacionada"] = base["inversion"]
        return base

    resumen = (
        relacionados.groupby(relacionados["activo_padre_id"].astype(int))
        .apply(
            lambda grupo: pd.Series(
                {
                    "componentes_vinculados": int(len(grupo)),
                    "componentes_criticos_vinculados": int((grupo["estado_componente"] == "Crítico").sum()),
                    "costo_componentes_asociados": float(
                        grupo.loc[grupo["impacta_costo_padre"] == 1, "inversion"].sum()
                    ),
                    "vida_restante_minima_vinculada": pd.to_numeric(
                        grupo["vida_restante_pct"], errors="coerce"
                    ).min(),
                }
            )
        )
        .reset_index()
        .rename(columns={"activo_padre_id": "id"})
    )
    base = base.merge(resumen, how="left", on="id", suffixes=("", "_resumen"))
    for col, default in (
        ("componentes_vinculados", 0),
        ("componentes_criticos_vinculados", 0),
        ("costo_componentes_asociados", 0.0),
    ):
        if f"{col}_resumen" in base.columns:
            base[col] = pd.to_numeric(base[f"{col}_resumen"], errors="coerce").fillna(default)
            base = base.drop(columns=[f"{col}_resumen"])
    if "vida_restante_minima_vinculada_resumen" in base.columns:
        base["vida_restante_minima_vinculada"] = pd.to_numeric(
            base["vida_restante_minima_vinculada_resumen"], errors="coerce"
        )
        base = base.drop(columns=["vida_restante_minima_vinculada_resumen"])

    base["componentes_vinculados"] = base["componentes_vinculados"].fillna(0).astype(int)
    base["componentes_criticos_vinculados"] = base["componentes_criticos_vinculados"].fillna(0).astype(int)
    base["costo_componentes_asociados"] = pd.to_numeric(
        base["costo_componentes_asociados"], errors="coerce"
    ).fillna(0.0)
    base["inversion_total_relacionada"] = base["inversion"] + np.where(
        base["clase_registro"].eq("equipo_principal"),
        base["costo_componentes_asociados"],
        0.0,
    )
    return base


def _selector_activo_padre(df: pd.DataFrame, key: str, excluir_id: int | None = None, seleccionado_id: int | None = None) -> int | None:
    opciones = _opciones_activo_padre(df, excluir_id=excluir_id)
    if not opciones:
        st.caption("No hay equipos principales disponibles para asociar como activo padre.")
        return None
    labels = ["Sin relación"] + list(opciones.keys())
    default_label = "Sin relación"
    if seleccionado_id:
        for label, value in opciones.items():
            if int(value) == int(seleccionado_id):
                default_label = label
                break
    index = labels.index(default_label) if default_label in labels else 0
    elegido = st.selectbox("Activo principal asociado", labels, index=index, key=key)
    return int(opciones[elegido]) if elegido != "Sin relación" else None


def _render_componentes_asociados(componentes_map: dict[int, pd.DataFrame], activo_id: int, titulo: str = "Componentes asociados") -> None:
    componentes = componentes_map.get(int(activo_id))
    if componentes is None or componentes.empty:
        st.caption("Sin componentes o accesorios asociados.")
        return
    vista = componentes[
        [
            "id",
            "equipo",
            "unidad",
            "tipo_detalle",
            "clase_registro_label",
            "fecha_instalacion",
            "uso_acumulado",
            "vida_util_valor",
            "vida_util_unidad",
            "vida_restante_pct",
            "estado_componente",
            "impacta_costo_padre",
            "impacta_desgaste_padre",
            "inversion",
            "desgaste",
            "riesgo",
        ]
    ].copy()
    vista["impacta_costo_padre"] = vista["impacta_costo_padre"].map({1: "Sí", 0: "No"})
    vista["impacta_desgaste_padre"] = vista["impacta_desgaste_padre"].map({1: "Sí", 0: "No"})
    st.markdown(f"##### {titulo}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Componentes vinculados", len(vista))
    c2.metric("Costo asociado", f"$ {vista.loc[componentes['impacta_costo_padre'] == 1, 'inversion'].sum():,.2f}")
    c3.metric("Componentes críticos", int((vista["estado_componente"] == "Crítico").sum()))
    tracked = componentes[componentes["vida_restante_pct"].notna()].copy()
    if not tracked.empty:
        siguiente = tracked.sort_values(["vida_restante_pct", "id"], ascending=[True, True]).iloc[0]
        st.caption(
            f"Próximo a reponer: {siguiente['equipo']} · {float(siguiente['vida_restante_pct']):.1f}% de vida restante"
        )
    st.dataframe(vista, use_container_width=True, hide_index=True)


def _aplicar_filtros_activos(
    df: pd.DataFrame,
    texto_busqueda: str = "",
    unidades: lista[str] | Ninguno = Ninguno,
    clases: lista[str] | Ninguno = Ninguno,
    riesgos: lista[str] | Ninguno = Ninguno,
    solo_con_relacion: bool = False,
) -> pd.DataFrame:
    si df.empty:
        devolver df.copy()

    vista = df.copy()

    texto = str(texto_busqueda or "").strip().lower()
    if texto:
        columnas_busqueda = [
            "equipo",
            "modelo",
            "unidad",
            "tipo_detalle",
            "clase_registro_label",
            "activo_padre_label",
        ]
        máscara = pd.Series(False, index=vista.index)
        for columna in columnas_busqueda:
            if columna in vista.columns:
                máscara = máscara | vista[columna].fillna("").astype(str).str.lower().str.contains(texto, regex=False)
        vista = vista[máscara].copia()

    si unidades:
        vista = vista[vista["unidad"].fillna("").isin(unidades)].copy()
    si clases:
        vista = vista[vista["clase_registro_label"].fillna("").isin(clases)].copy()
    if riesgos:
        vista = vista[vista["riesgo"].fillna("").isin(riesgos)].copy()
    if solo_con_relacion:
        vista = vista[vista["activo_padre_id"].notna()].copy()

    vista de regreso


def _key_tipo_equipo(base_key: str, tipo_equipo: str | None) -> str:
    slug = str(tipo_equipo or "otro").strip().lower()
    slug = slug.replace(" ", "_").replace("/", "_")
    return f"{base_key}_{slug}"


def _label_tipo_equipo(tipo_equipo: str | None) -> str:
    return str(_equipo_config(tipo_equipo).get("label") or "Detalle del equipo")


def _placeholder_tipo_equipo(tipo_equipo: str | None) -> str:
    return str(_equipo_config(tipo_equipo).get("placeholder") or "Selecciona un tipo")


def _resolver_tipo_detalle(tipo_equipo: str, tipo_predefinido: str | None, tipo_personalizado: str | None) -> str | None:
    opciones = _equipo_config(tipo_equipo).get("opciones") or []
    tipo_predefinido = str(tipo_predefinido or "").strip()
    tipo_personalizado = str(tipo_personalizado or "").strip()
    if tipo_predefinido and tipo_predefinido != OPCION_TIPO_PERSONALIZADO:
        return tipo_predefinido
    if tipo_predefinido == OPCION_TIPO_PERSONALIZADO or not opciones:
        return require_text(tipo_personalizado, _label_tipo_equipo(tipo_equipo))
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
        "vida_util_valor": "ALTER TABLE activos ADD COLUMN vida_util_valor REAL NOT NULL DEFAULT 1",
        "vida_util_unidad": "ALTER TABLE activos ADD COLUMN vida_util_unidad TEXT NOT NULL DEFAULT 'usos'",
        "uso_acumulado": "ALTER TABLE activos ADD COLUMN uso_acumulado REAL NOT NULL DEFAULT 0",
        "fecha_instalacion": "ALTER TABLE activos ADD COLUMN fecha_instalacion TEXT",
        "impacta_costo_padre": "ALTER TABLE activos ADD COLUMN impacta_costo_padre INTEGER NOT NULL DEFAULT 1",
        "impacta_desgaste_padre": "ALTER TABLE activos ADD COLUMN impacta_desgaste_padre INTEGER NOT NULL DEFAULT 0",
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
                COALESCE(clase_registro, 'equipo_principal') AS clase_registro,
                activo_padre_id,
                COALESCE(vida_util_valor, 1) AS vida_util_valor,
                COALESCE(vida_util_unidad, 'usos') AS vida_util_unidad,
                COALESCE(uso_acumulado, 0) AS uso_acumulado,
                fecha_instalacion,
                COALESCE(impacta_costo_padre, 1) AS impacta_costo_padre,
                COALESCE(impacta_desgaste_padre, 0) AS impacta_desgaste_padre,
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
                "vida_cabezal_pct", "vida_rodillo_pct", "vida_almohadillas_pct", "paginas_impresas", "tipo_impresora", "tipo_detalle",
                "clase_registro", "activo_padre_id", "vida_util_valor", "vida_util_unidad", "uso_acumulado", "fecha_instalacion",
                "impacta_costo_padre", "impacta_desgaste_padre", "fecha", "activo"
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
    df["activo_padre_id"] = pd.to_numeric(df.get("activo_padre_id"), errors="coerce")
    df["clase_registro"] = df.get("clase_registro", "equipo_principal").apply(_slug_clase_registro)
    df["clase_registro_label"] = df["clase_registro"].apply(_label_clase_registro)
    df["vida_util_valor"] = pd.to_numeric(df.get("vida_util_valor"), errors="coerce").fillna(1.0)
    df["vida_util_unidad"] = df.get("vida_util_unidad", "usos").apply(_normalizar_vida_util_unidad)
    df["uso_acumulado"] = pd.to_numeric(df.get("uso_acumulado"), errors="coerce").fillna(0.0)
    df["fecha_instalacion"] = df.get("fecha_instalacion").fillna("")
    df["vida_restante_pct"] = df.apply(
        lambda row: _calcular_vida_restante_pct(row.get("uso_acumulado"), row.get("vida_util_valor")),
        axis=1,
    )
    df["estado_componente"] = df["vida_restante_pct"].apply(_estado_componente_desde_vida)
    df["impacta_costo_padre"] = pd.to_numeric(df.get("impacta_costo_padre"), errors="coerce").fillna(1).astype(int)
    df["impacta_desgaste_padre"] = pd.to_numeric(df.get("impacta_desgaste_padre"), errors="coerce").fillna(0).astype(int)
    ranking_riesgo = df["desgaste"].rank(pct=True, method="average").fillna(0)
    df["riesgo"] = np.where(
        ranking_riesgo >= 0.80,
        "🔴 Alto",
        np.where(ranking_riesgo >= 0.50, "🟠 Medio", "🟢 Bajo"),
    )
    return _agregar_metricas_relacionadas(df)


def _crear_activo(
    usuario: str,
    equipo: str,
    tipo_unidad: str,
    inversion: float,
    vida_util: int,
    vida_util_unidad: str,
    uso_acumulado: float,
    fecha_instalacion: str | None,
    modelo: str,
    tipo_detalle: str | None,
    clase_registro: str = "equipo_principal",
    activo_padre_id: int | None = None,
    impacta_costo_padre: bool = True,
    impacta_desgaste_padre: bool = False,
) -> int:
    equipo = require_text(equipo, "Nombre del activo")
    tipo_unidad = _normalizar_unidad(require_text(tipo_unidad, "Tipo de equipo"))
    categoria = _categoria_por_equipo(tipo_unidad)
    inversion = as_positive(inversion, "Inversión", allow_zero=False)
    vida_util = max(1, int(vida_util or 1))
    uso_acumulado = max(0.0, _safe_float(uso_acumulado, 0.0))
    desgaste_unitario = inversion / vida_util
    vida_util_unidad = _normalizar_vida_util_unidad(vida_util_unidad)
    fecha_instalacion = str(fecha_instalacion or "").strip() or None
    tipo_detalle = (tipo_detalle or "").strip() or None
    tipo_impresora = tipo_detalle if _es_equipo_impresora(tipo_unidad) else None
    clase_registro = _slug_clase_registro(clase_registro)
    activo_padre_id = int(activo_padre_id) if activo_padre_id and clase_registro != "equipo_principal" else None

    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO activos
            (equipo, modelo, categoria, inversion, unidad, desgaste, costo_hora, usuario, activo, estado, tipo_impresora, tipo_detalle, clase_registro, activo_padre_id, vida_util_valor, vida_util_unidad, uso_acumulado, fecha_instalacion, impacta_costo_padre, impacta_desgaste_padre)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'activo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                clase_registro,
                activo_padre_id,
                float(vida_util),
                vida_util_unidad,
                uso_acumulado,
                fecha_instalacion,
                _valor_bool_db(impacta_costo_padre),
                _valor_bool_db(impacta_desgaste_padre),
            ),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                equipo,
                "CREACIÓN",
                (
                    f"Registro inicial (vida útil: {vida_util} {vida_util_unidad})"
                    + (f" · uso acumulado: {uso_acumulado:g}" if uso_acumulado > 0 else "")
                    + (f" · fecha instalación: {fecha_instalacion}" if fecha_instalacion else "")
                    + (f" · clase: {_label_clase_registro(clase_registro)}" if clase_registro else "")
                    + (f" · activo padre ID: {activo_padre_id}" if activo_padre_id else "")
                ),
                inversion,
                usuario,
            ),
        )
        return int(cur.lastrowid)


def _actualizar_activo(
    usuario: str,
    activo_id: int,
    activo_nombre: str,
    nueva_inversion: float,
    nueva_vida: int,
    nueva_vida_util_unidad: str,
    nuevo_uso_acumulado: float,
    nueva_fecha_instalacion: str | None,
    nuevo_modelo: str,
    nueva_unidad: str,
    nuevo_tipo_detalle: str | None,
    clase_registro: str = "equipo_principal",
    activo_padre_id: int | None = None,
    impacta_costo_padre: bool = True,
    impacta_desgaste_padre: bool = False,
) -> None:
    nueva_inversion = as_positive(nueva_inversion, "Inversión")
    nueva_vida = max(1, int(nueva_vida or 1))
    nuevo_uso_acumulado = max(0.0, _safe_float(nuevo_uso_acumulado, 0.0))
    nuevo_desgaste = (nueva_inversion / nueva_vida) if nueva_inversion > 0 else 0.0
    nueva_unidad = _normalizar_unidad(nueva_unidad)
    nueva_categoria = _categoria_por_equipo(nueva_unidad)
    nueva_vida_util_unidad = _normalizar_vida_util_unidad(nueva_vida_util_unidad)
    nueva_fecha_instalacion = str(nueva_fecha_instalacion or "").strip() or None
    nuevo_tipo_detalle = (nuevo_tipo_detalle or "").strip() or None
    nuevo_tipo_impresora = nuevo_tipo_detalle if _es_equipo_impresora(nueva_unidad) else None
    clase_registro = _slug_clase_registro(clase_registro)
    activo_padre_id = int(activo_padre_id) if activo_padre_id and clase_registro != "equipo_principal" else None

    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        conn.execute(
            """
            UPDATE activos
            SET inversion = ?, categoria = ?, desgaste = ?, modelo = ?, unidad = ?, usuario = ?, tipo_impresora = ?, tipo_detalle = ?, clase_registro = ?, activo_padre_id = ?, vida_util_valor = ?, vida_util_unidad = ?, uso_acumulado = ?, fecha_instalacion = ?, impacta_costo_padre = ?, impacta_desgaste_padre = ?
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
                clase_registro,
                activo_padre_id,
                float(nueva_vida),
                nueva_vida_util_unidad,
                nuevo_uso_acumulado,
                nueva_fecha_instalacion,
                _valor_bool_db(impacta_costo_padre),
                _valor_bool_db(impacta_desgaste_padre),
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
                (
                    f"Actualización de valores (vida útil: {nueva_vida} {nueva_vida_util_unidad}, equipo: {nueva_unidad}, tipo: {nuevo_tipo_detalle or 'N/D'})"
                    + f" · uso acumulado: {nuevo_uso_acumulado:g}"
                    + (f" · fecha instalación: {nueva_fecha_instalacion}" if nueva_fecha_instalacion else "")
                    + f" · clase: {_label_clase_registro(clase_registro)}"
                    + (f" · activo padre ID: {activo_padre_id}" if activo_padre_id else "")
                ),
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
        f"{ACTIVOS_UI_VERSION} · catálogo unificado por tipo de equipo. Ahora puedes clasificar equipos principales, componentes/repuestos y herramientas/accesorios, además de vincularlos a un activo padre."
    )

    try:
        df = _load_activos_df()
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")
        return

    if not df.empty:
        parent_info = _info_activo_padre(df)
        df["activo_padre_label"] = df["activo_padre_id"].apply(
            lambda x: parent_info.get(int(x), {}).get("label", "Sin relación") if pd.notna(x) else "Sin relación"
        )
        componentes_map = _componentes_por_padre(df)
        st.subheader("🧠 Salud de Activos")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Inversión instalada", f"$ {df['inversion_total_relacionada'].sum():,.2f}")
        m2.metric("Desgaste promedio", f"$ {df['desgaste'].mean():.4f}/uso")
        m3.metric("Activos en riesgo alto", int((df["riesgo"] == "🔴 Alto").sum()))
        activo_critico = df.sort_values("desgaste", ascending=False).iloc[0]["equipo"]
        m4.metric("Activo más crítico", str(activo_critico))
        c_reg1, c_reg2, c_reg3 = st.columns(3)
        c_reg1.metric("Equipos principales", int((df["clase_registro"] == "equipo_principal").sum()))
        c_reg2.metric("Componentes / repuestos", int((df["clase_registro"] == "componente").sum()))
        c_reg3.metric("Herramientas / accesorios", int((df["clase_registro"] == "herramienta").sum()))
        if int(df["componentes_criticos_vinculados"].sum()) > 0:
            st.warning(
                "Hay equipos principales con componentes críticos vinculados. "
                "Revísalos en su categoría o en el Resumen Global para planificar reposiciones."
            )

        with st.expander("🔎 Activos con prioridad de mantenimiento", expanded=False):
            st.dataframe(
                df.sort_values("desgaste", ascending=False)[
                    [
                        "equipo",
                        "unidad",
                        "tipo_detalle",
                        "clase_registro_label",
                        "activo_padre_label",
                        "inversion_total_relacionada",
                        "componentes_vinculados",
                        "componentes_criticos_vinculados",
                        "desgaste",
                        "riesgo",
                    ]
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

        st.divider()
        st.subheader("🧭 Vista operativa actualizada")
        st.caption("Filtra, busca y revisa relaciones padre → hijo sin perder la edición completa del catálogo.")
        f1, f2, f3, f4 = st.columns([1.4, 1, 1, 0.8])
        texto_busqueda = f1.text_input(
            "Buscar activo, modelo o tipo",
            key="activos_busqueda_general_v4",
            placeholder="Ej. Epson, Cameo, rodillo, UPS…",
        )
        unidades_sel = f2.multiselect(
            "Tipo de equipo",
            options=TIPOS_UNIDAD,
            predeterminado=[],
            key="activos_filtro_unidad_v4",
        )
        clases_sel = f3.multiselect(
            "Clase de registro",
            opciones=lista(CLASES_REGISTRO.values()),
            predeterminado=[],
            key="activos_filtro_clase_v4",
        )
        solo_relacionados = f4.checkbox(
            "Solo vinculados",
            valor=Falso,
            key="activos_filtro_relacionados_v4",
            help="Muestra solo componentes, repuestos o accesorios asociados a un activo principal.",
        )
        riesgos_sel = st.multiselect(
            "Riesgo",
            options=["🔴 Alto", "🟠 Medio", "🟢 Bajo"],
            predeterminado=[],
            key="activos_filtro_riesgo_v4",
        )
        df_vista = _aplicar_filtros_activos(
            df,
            texto_busqueda=texto_busqueda,
            unidades=unidades_seleccionar,
            clases=clases_sel,
            riesgos=riesgos_sel,
            solo_con_relacion=solo_relacionados,
        )

        vr1, vr2, vr3, vr4 = st.columns(4)
        vr1.metric("Activos visibles", len(df_vista))
        vr2.metric("Inversión visible", f"$ {df_vista['inversion_total_relacionada'].sum():,.2f}")
        vr3.metric("Con relación padre/hijo", int(df_vista["activo_padre_id"].notna().sum()))
        vr4.metric("Riesgo alto visible", int((df_vista["riesgo"] == "🔴 Alto").sum()))

        columnas_vista_operativa = [
            "identificación",
            "equipo",
            "modelo",
            "unidad",
            "tipo_detalle",
            "clase_registro_label",
            "activo_padre_label",
            "estado_componente",
            "componentes_vinculados",
            "componentes_criticos_vinculados",
            "inversion_total_relacionada",
            "vida_restante_pct",
            "riesgo",
        ]
        si df_vista.empty:
            st.warning("No hay activos que coincidan con los filtros aplicados.")
        demás:
            st.dataframe(
                df_vista[columnas_vista_operativa],
                use_container_width=True,
                ocultar_índice=Verdadero,
            )

    demás:
        información_parental = {}
        componentes_map = {}
        df_vista = df.copy()

    with st.expander("➕ Registrar Nuevo Activo", expanded=True):
        st.info("Selecciona el tipo de equipo, define si es equipo principal, componente o herramienta, y asócialo a un activo padre cuando corresponda. Si un tipo no aparece, puedes escribirlo manualmente.")
        c1, c2, c3 = st.columns(3)
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
        sc1, sc2 = st.columns(2)
        uso_acumulado_nuevo = sc1.number_input(
            "Uso acumulado",
            min_value=0.0,
            step=1.0,
            key="activos_uso_acumulado_nuevo_v2",
            help="Útil para componentes o herramientas con seguimiento de vida útil por páginas, cortes, horas, trabajos o usos.",
        )
        fecha_instalacion_nueva = sc2.text_input(
            "Fecha de instalación / compra (YYYY-MM-DD, opcional)",
            key="activos_fecha_instalacion_nuevo_v2",
        )

        tipo_predefinido_nuevo = None
        tipo_personalizado_nuevo = ""
        if opciones_tipo_nuevo:
            tipo_predefinido_nuevo = st.selectbox(
                label_tipo_nuevo,
                [placeholder_tipo_nuevo] + opciones_tipo_nuevo,
                index=0,
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
        else:
            tipo_personalizado_nuevo = st.text_input(
                label_tipo_nuevo,
                key=_key_tipo_equipo("activos_tipo_detalle_libre_nuevo_v2", tipo_unidad_nuevo),
                help="Escribe manualmente el tipo específico si no existe una lista para este equipo.",
            )

        modelo = st.text_input("Modelo (opcional)", key="activos_modelo_nuevo_v2")
        cc1, cc2 = st.columns(2)
        impacta_costo_nuevo = cc1.checkbox(
            "Impacta costo del activo principal",
            value=True if clase_nueva != "equipo_principal" else False,
            key="activos_impacta_costo_padre_nuevo_v2",
            help="Útil para componentes, repuestos o accesorios que deseas sumar al costo del equipo asociado.",
        )
        impacta_desgaste_nuevo = cc2.checkbox(
            "Impacta seguimiento/desgaste del activo principal",
            value=True if clase_nueva == "componente" else False,
            key="activos_impacta_desgaste_padre_nuevo_v2",
            help="Marca esto cuando el componente afecte el estado o mantenimiento del equipo principal.",
        )
        activo_padre_id_nuevo = None
        if clase_nueva != "equipo_principal":
            activo_padre_id_nuevo = _selector_activo_padre(df, key="activos_padre_nuevo_v2")
        guardar = st.button("🚀 Guardar activo", key="activos_guardar_nuevo_v2", type="primary")
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
                    inversion=monto_inv,
                    vida_util=int(vida_util),
                    vida_util_unidad=vida_util_unidad_nuevo,
                    uso_acumulado=float(uso_acumulado_nuevo),
                    fecha_instalacion=fecha_instalacion_nueva,
                    modelo=modelo,
                    tipo_detalle=tipo_detalle_nuevo,
                    clase_registro=clase_nueva,
                    activo_padre_id=activo_padre_id_nuevo,
                    impacta_costo_padre=impacta_costo_nuevo,
                    impacta_desgaste_padre=impacta_desgaste_nuevo,
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
            e1, e2, e3 = st.columns(3)
            nueva_inv = e1.number_input(
                "Inversión ($)",
                min_value=0.0,
                value=float(datos["inversion"]),
                step=10.0,
                key=f"activos_editar_inversion_{activo_id}",
            )
            nueva_vida = e2.number_input(
                "Vida útil",
                min_value=1,
                value=int(vida_sugerida),
                step=1,
                key=f"activos_editar_vida_{activo_id}",
            )
            nueva_vida_unidad = e3.selectbox(
                "Unidad de vida útil",
                UNIDADES_VIDA_UTIL,
                index=UNIDADES_VIDA_UTIL.index(_normalizar_vida_util_unidad(datos.get("vida_util_unidad"))),
                key=f"activos_editar_vida_unidad_{activo_id}",
            )
            e4, e5 = st.columns(2)
            nuevo_uso_acumulado = e4.number_input(
                "Uso acumulado",
                min_value=0.0,
                value=float(datos.get("uso_acumulado") or 0.0),
                step=1.0,
                key=f"activos_editar_uso_acumulado_{activo_id}",
            )
            nueva_fecha_instalacion = e5.text_input(
                "Fecha de instalación / compra (YYYY-MM-DD, opcional)",
                value=str(datos.get("fecha_instalacion") or ""),
                key=f"activos_editar_fecha_instalacion_{activo_id}",
            )

            nuevo_modelo = st.text_input(
                "Modelo",
                value=str(datos.get("modelo") or ""),
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
                        f"Especifica {label_tipo_edicion.lower()}",
                        value=tipo_personalizado_actual,
                        key=_key_tipo_equipo(f"activos_editar_tipo_detalle_custom_{activo_id}", nueva_unidad),
                    )
            else:
                nuevo_tipo_personalizado = st.text_input(
                    label_tipo_edicion,
                    value=tipo_personalizado_actual,
                    key=_key_tipo_equipo(f"activos_editar_tipo_detalle_libre_{activo_id}", nueva_unidad),
                    help="Escribe manualmente el tipo específico si no existe una lista para este equipo.",
                )

            cc3, cc4 = st.columns(2)
            impacta_costo_edicion = cc3.checkbox(
                "Impacta costo del activo principal",
                value=bool(datos.get("impacta_costo_padre", 1)),
                key=f"activos_editar_impacta_costo_{activo_id}",
            )
            impacta_desgaste_edicion = cc4.checkbox(
                "Impacta seguimiento/desgaste del activo principal",
                value=bool(datos.get("impacta_desgaste_padre", 0)),
                key=f"activos_editar_impacta_desgaste_{activo_id}",
            )
            activo_padre_edicion = None
            if nueva_clase != "equipo_principal":
                activo_padre_edicion = _selector_activo_padre(
                    df,
                    key=f"activos_editar_padre_{activo_id}",
                    excluir_id=activo_id,
                    seleccionado_id=int(datos["activo_padre_id"]) if pd.notna(datos.get("activo_padre_id")) else None,
                )

            guardar_edicion = st.button("💾 Guardar Cambios", key=f"activos_guardar_edicion_{activo_id}")
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
                        nueva_vida_util_unidad=nueva_vida_unidad,
                        nuevo_uso_acumulado=float(nuevo_uso_acumulado),
                        nueva_fecha_instalacion=nueva_fecha_instalacion,
                        nuevo_modelo=nuevo_modelo,
                        nueva_unidad=nueva_unidad,
                        nuevo_tipo_detalle=nuevo_tipo_detalle,
                        clase_registro=nueva_clase,
                        activo_padre_id=activo_padre_edicion,
                        impacta_costo_padre=impacta_costo_edicion,
                        impacta_desgaste_padre=impacta_desgaste_edicion,
                    )
                    st.success("✅ Activo actualizado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al actualizar activo: {e}")

    st.divider()

    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "🖨️ Impresoras",
        "✂️ Corte",
        "🪪 Plastificación",
        "🔥 Sublimación",
        "🔌 Conexión y Energía",
        "🧰 Otros",
        "📊 Resumen Global",
    ])

    if df.empty:
        with t1:
            st.info("No hay activos registrados todavía.")
        return

    columnas_categoria = [
        "id",
        "equipo",
        "modelo",
        "tipo_detalle",
        "clase_registro_label",
        "activo_padre_label",
        "uso_acumulado",
        "vida_util_valor",
        "vida_util_unidad",
        "vida_restante_pct",
        "estado_componente",
        "componentes_vinculados",
        "componentes_criticos_vinculados",
        "inversion_total_relacionada",
        "desgaste",
        "riesgo",
    ]

    def _render_tab_activos(df_categoria: pd.DataFrame, titulo: str, prefijo_expandir: str) -> None:
        st.subheader(titulo)
        if df_categoria.empty:
            st.caption("Sin activos registrados en esta categoría.")
            return
        st.dataframe(
            df_categoria.drop(columns=["categoria"], errors="ignore")[columnas_categoria],
            use_container_width=True,
            hide_index=True,
        )
        for row in df_categoria[df_categoria["clase_registro"] == "equipo_principal"].itertuples():
            with st.expander(f"{prefijo_expandir} · {_formatear_activo_relacion(row)}", expanded=False):
                _render_componentes_asociados(componentes_map, int(row.id), titulo="Vinculados a este equipo")

    with t1:
        st.subheader("Impresoras")
        df_imp = df_vista[df_vista["unidad"].fillna("").str.contains("Impresora", case=False)].copy()
        if not df_imp.empty:
            df_imp["desgaste_cabezal_pct"] = 100.0 - pd.to_numeric(df_imp["vida_cabezal_pct"], errors="coerce")
            c_imp1, c_imp2, c_imp3 = st.columns(3)
            c_imp1.metric("Vida cabezal promedio", f"{df_imp['vida_cabezal_pct'].mean(skipna=True):.2f}%")
            c_imp2.metric("Desgaste cabezal promedio", f"{df_imp['desgaste_cabezal_pct'].mean(skipna=True):.2f}%")
            c_imp3.metric("Páginas impresas (total)", int(df_imp["paginas_impresas"].sum()))

            mostrar_cols = [
                "id",
                "equipo",
                "modelo",
                "tipo_detalle",
                "clase_registro_label",
                "activo_padre_label",
                "componentes_vinculados",
                "componentes_criticos_vinculados",
                "costo_componentes_asociados",
                "vida_cabezal_pct",
                "vida_rodillo_pct",
                "vida_almohadillas_pct",
                "desgaste_cabezal_pct",
                "paginas_impresas",
                "desgaste",
                "riesgo",
            ]
            st.dataframe(df_imp[mostrar_cols], use_container_width=True, hide_index=True)

            st.markdown("#### 🩺 Resumen de diagnóstico por impresora")
            opciones_imp = {f"#{int(r.id)} · {r.equipo}": int(r.id) for r in df_imp.itertuples()}
            sel_label = st.selectbox("Seleccionar impresora para ver resumen", list(opciones_imp.keys()), key="activos_diag_sel")
            sel_id = opciones_imp[sel_label]
            resumen = get_printer_diagnostic_summary(sel_id)
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
                _render_componentes_asociados(componentes_map, sel_id, titulo="Componentes, repuestos y accesorios vinculados")
                if resumen.get("low_ink_alerts"):
                    st.warning(f"Alertas de bajo nivel: {', '.join(resumen.get('low_ink_alerts') or [])}")
                st.info(
                    "Exactitud de datos: "
                    + str(resumen.get("diagnostic_accuracy") or "estimated")
                    + f" · Confianza: {resumen.get('confidence_level') or 'medium'}"
                )
                fila_impresora = df_imp[df_imp["id"] == sel_id]
                if not fila_impresora.empty:
                    impresora_data = fila_impresora.iloc[0]
                    rc1, rc2, rc3 = st.columns(3)
                    rc1.metric("Costo vinculado", f"$ {float(impresora_data.get('costo_componentes_asociados') or 0.0):,.2f}")
                    rc2.metric("Componentes vinculados", int(impresora_data.get("componentes_vinculados") or 0))
                    rc3.metric("Componentes críticos", int(impresora_data.get("componentes_criticos_vinculados") or 0))
            else:
                st.info("Esta impresora aún no tiene diagnósticos técnicos registrados.")
                _render_componentes_asociados(componentes_map, sel_id, titulo="Componentes, repuestos y accesorios vinculados")

            st.markdown("#### 📜 Historial de diagnósticos")
            historial = pd.DataFrame(list_printer_diagnostics(sel_id, limit=50))
            if not historial.empty:
                cols_show = [
                    "id",
                    "fecha",
                    "total_pages",
                    "color_pages",
                    "bw_pages",
                    "borderless_pages",
                    "scanned_pages",
                    "black_ml",
                    "cyan_ml",
                    "magenta_ml",
                    "yellow_ml",
                    "estimation_mode",
                    "confidence_level",
                    "files_count",
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
        _render_tab_activos(df_vista[df_vista["unidad"].fillna("").eq("Corte")].copy(), "Equipos de corte", "Componentes de corte")

    with t3:
        _render_tab_activos(df_vista[df_vista["unidad"].fillna("").eq("Plastificación")].copy(), "Equipos de plastificación", "Componentes de plastificación")

    with t4:
        _render_tab_activos(df_vista[df_vista["unidad"].fillna("").eq("Sublimación")].copy(), "Equipos de sublimación", "Componentes de sublimación")

    with t5:
        _render_tab_activos(df_vista[df_vista["unidad"].fillna("").eq("Conexión y Energía")].copy(), "Conexión y energía", "Componentes de conexión/energía")

    with t6:
        _render_tab_activos(df_vista[df_vista["unidad"].fillna("").eq("Otro")].copy(), "Otros equipos", "Componentes de otros equipos")

    with t7:
        c_inv, c_des, c_prom = st.columns(3)
        c_inv.metric("Inversión Total", f"$ {df_vista['inversion_total_relacionada'].sum():,.2f}")
        c_des.metric("Activos Registrados", len(df_vista))
        c_prom.metric("Desgaste Promedio por Uso", f"$ {df_vista['desgaste'].mean():.4f}")

        fig = px.bar(
            df_vista,
            x="equipo",
            y="inversion_total_relacionada",
            color="unidad",
            title="Distribución de inversión por activo (incluye componentes vinculados en equipos principales)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("#### Relaciones padre → hijo")
        relacionados = df_vista[df_vista["activo_padre_id"].notna()].copy()
        if relacionados.empty:
            st.caption("Aún no hay componentes o accesorios vinculados a equipos principales.")
        else:
            st.dataframe(
                relacionados[
                    [
                        "id",
                        "equipo",
                        "unidad",
                        "clase_registro_label",
                        "activo_padre_label",
                        "tipo_detalle",
                        "inversion",
                        "uso_acumulado",
                        "vida_util_valor",
                        "vida_util_unidad",
                        "estado_componente",
                        "impacta_costo_padre",
                        "impacta_desgaste_padre",
                    ]
                ].assign(
                    impacta_costo_padre=lambda x: x["impacta_costo_padre"].map({1: "Sí", 0: "No"}),
                    impacta_desgaste_padre=lambda x: x["impacta_desgaste_padre"].map({1: "Sí", 0: "No"}),
                ),
                use_container_width=True,
                hide_index=True,
            )
