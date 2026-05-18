from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import streamlit as st

from database.connection import db_transaction


@dataclass(frozen=True)
class CheckResult:
    area: str
    item: str
    estado: str
    detalle: str


REQUIRED_TABLES: dict[str, list[str]] = {
    "permisos": ["codigo", "descripcion"],
    "roles_permisos": ["rol", "permiso_codigo"],
    "movimientos_tesoreria": ["fecha", "tipo", "metodo_pago", "monto_usd", "estado"],
    "cierres_caja": ["fecha", "usuario", "cash_start", "cash_end"],
    "cierres_caja_turnos": ["fecha_operativa", "turno", "cajero", "efectivo_esperado_usd", "efectivo_contado_usd"],
    "comprobantes_pos": ["fecha", "usuario", "cliente", "total_usd", "cuerpo"],
    "cola_impresion": ["cliente", "archivo_nombre", "estado"],
    "contadores_impresion": ["equipo", "contador_inicial", "contador_final"],
    "fichas_tecnicas_bom": ["codigo", "producto", "costo_total_usd", "precio_sugerido_usd"],
    "fichas_tecnicas_bom_componentes": ["ficha_id", "item", "cantidad", "costo_total_usd"],
    "disenos_aprobaciones": ["cliente", "nombre_diseno", "estado", "bloqueo_produccion"],
    "despachos_entregas": ["cliente", "tipo_entrega", "estado", "costo_envio_usd"],
    "unidades_fraccionadas": ["material", "unidad_compra", "unidad_consumo", "factor_conversion"],
    "proveedores": ["nombre", "rif", "telefono"],
    "ordenes_compra": ["proveedor", "estado", "total_usd"],
}

REQUIRED_IMPORTS = [
    "app",
    "database.schema",
    "security.permissions",
    "security.permission_extensions",
    "views.ventas",
    "views.caja",
    "views.inventario",
    "views.rutas_produccion",
    "views.fichas_tecnicas_bom",
    "views.disenos_aprobaciones",
    "views.despacho_entregas",
    "views.unidades_fraccionadas",
    "views.ticket_pos",
]

CRITICAL_PERMISSIONS = [
    "pos.view", "pos.create", "pos.ticket",
    "cola_impresion.view", "cola_impresion.edit",
    "contadores.view", "contadores.create",
    "despacho.view", "despacho.edit",
    "compras.view", "compras.create",
    "proveedores.view", "proveedores.edit",
    "bom.view", "bom.edit",
    "disenos.view", "disenos.edit",
    "unidades_fraccionadas.view", "unidades_fraccionadas.edit",
    "caja.turno_close",
]


def _table_exists(table: str) -> bool:
    with db_transaction() as conn:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _table_columns(table: str) -> set[str]:
    if not _table_exists(table):
        return set()
    with db_transaction() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _count_rows(table: str) -> int:
    if not _table_exists(table):
        return 0
    with db_transaction() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    try:
        return int(row["total"] if "total" in row.keys() else row[0])
    except Exception:
        return int(row[0]) if row else 0


def _check_tables() -> list[CheckResult]:
    results: list[CheckResult] = []
    for table, columns in REQUIRED_TABLES.items():
        if not _table_exists(table):
            results.append(CheckResult("Base de datos", table, "Falta", "Tabla no existe todavía o no fue migrada."))
            continue
        existing = _table_columns(table)
        missing = [col for col in columns if col not in existing]
        if missing:
            results.append(CheckResult("Base de datos", table, "Revisar", f"Faltan columnas: {', '.join(missing)}"))
        else:
            results.append(CheckResult("Base de datos", table, "OK", f"Columnas críticas presentes. Registros: {_count_rows(table)}"))
    return results


def _check_imports() -> list[CheckResult]:
    results: list[CheckResult] = []
    for module in REQUIRED_IMPORTS:
        spec = importlib.util.find_spec(module)
        if spec is None:
            results.append(CheckResult("Imports", module, "Falta", "No se encontró el módulo."))
        else:
            results.append(CheckResult("Imports", module, "OK", "Módulo encontrado."))
    return results


def _check_permissions() -> list[CheckResult]:
    results: list[CheckResult] = []
    if not _table_exists("permisos"):
        return [CheckResult("Permisos", "permisos", "Falta", "No existe la tabla permisos.")]
    with db_transaction() as conn:
        rows = conn.execute("SELECT codigo FROM permisos").fetchall()
    existing = {str(row[0]) for row in rows}
    for code in CRITICAL_PERMISSIONS:
        if code in existing:
            results.append(CheckResult("Permisos", code, "OK", "Registrado en catálogo."))
        else:
            results.append(CheckResult("Permisos", code, "Falta", "No está en el catálogo de permisos."))
    return results


def _to_df(results: Iterable[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in results])


def render_diagnostico_tecnico(usuario: str = "Sistema") -> None:
    st.subheader("🛠️ Diagnóstico técnico del ERP")
    st.caption("Verifica tablas, columnas críticas, imports y permisos para detectar errores antes de abrir los módulos.")

    if st.button("Ejecutar diagnóstico técnico", type="primary"):
        results = _check_tables() + _check_imports() + _check_permissions()
        df = _to_df(results)
        total = len(df)
        ok = int(df["estado"].eq("OK").sum()) if not df.empty else 0
        revisar = int(df["estado"].eq("Revisar").sum()) if not df.empty else 0
        faltan = int(df["estado"].eq("Falta").sum()) if not df.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Chequeos", total)
        c2.metric("OK", ok)
        c3.metric("Revisar", revisar)
        c4.metric("Faltan", faltan)

        if faltan or revisar:
            st.warning("Hay elementos para revisar. Abajo aparece el detalle exacto.")
        else:
            st.success("Diagnóstico técnico sin alertas críticas.")

        st.dataframe(df, use_container_width=True, hide_index=True)

        with st.expander("Solo problemas"):
            problemas = df[~df["estado"].eq("OK")]
            if problemas.empty:
                st.success("No hay problemas detectados.")
            else:
                st.dataframe(problemas, use_container_width=True, hide_index=True)
    else:
        st.info("Pulsa el botón para ejecutar las verificaciones técnicas.")
