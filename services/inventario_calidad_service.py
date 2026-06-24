from __future__ import annotations

import pandas as pd

from database.connection import db_transaction
from services.inventario_maestro_profesional_service import ensure_schema as ensure_maestro_schema
from services.inventario_tipo_panaderia_service import ensure_schema as ensure_panaderia_schema


CAMPOS_CRITICOS = {
    "sku": "SKU",
    "nombre": "Nombre",
    "categoria": "Categoría",
    "unidad_base": "Unidad base",
    "clase_articulo": "Clasificación",
    "ubicacion": "Ubicación",
    "proveedor_principal": "Proveedor",
    "costo_unitario_usd": "Costo unitario",
    "stock_minimo_operativo": "Stock mínimo",
    "punto_reorden": "Punto de reorden",
    "stock_ideal": "Stock ideal",
    "stock_maximo": "Stock máximo",
    "factor_compra_base": "Contenido por compra",
}


def _columns(conn, table: str = "inventario") -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    ensure_maestro_schema()
    ensure_panaderia_schema()
    with db_transaction() as conn:
        cols = _columns(conn)
        migrations = {
            "sku": "TEXT",
            "nombre": "TEXT",
            "categoria": "TEXT",
            "unidad": "TEXT",
            "unidad_base": "TEXT",
            "estado": "TEXT NOT NULL DEFAULT 'activo'",
            "ubicacion": "TEXT",
            "proveedor_principal": "TEXT",
            "costo_unitario_usd": "REAL NOT NULL DEFAULT 0",
            "stock_actual": "REAL NOT NULL DEFAULT 0",
            "stock_minimo_operativo": "REAL NOT NULL DEFAULT 0",
            "punto_reorden": "REAL NOT NULL DEFAULT 0",
            "stock_ideal": "REAL NOT NULL DEFAULT 0",
            "stock_maximo": "REAL NOT NULL DEFAULT 0",
            "factor_compra_base": "REAL NOT NULL DEFAULT 1",
            "clase_articulo": "TEXT NOT NULL DEFAULT 'Materia prima'",
            "controla_lotes": "INTEGER NOT NULL DEFAULT 0",
            "controla_vencimiento": "INTEGER NOT NULL DEFAULT 0",
            "dias_vida_util": "INTEGER NOT NULL DEFAULT 0",
        }
        for campo, ddl in migrations.items():
            if campo not in cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {campo} {ddl}")
                cols.add(campo)


def diagnostico_calidad() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        df = pd.read_sql_query("""
            SELECT i.id, COALESCE(i.sku,'') AS sku, COALESCE(i.nombre,'') AS nombre,
                   COALESCE(i.categoria,'') AS categoria,
                   COALESCE(NULLIF(i.unidad_base,''),NULLIF(i.unidad,''),'') AS unidad_base,
                   COALESCE(i.clase_articulo,'') AS clase_articulo,
                   COALESCE(i.ubicacion,'') AS ubicacion,
                   COALESCE(i.proveedor_principal,'') AS proveedor_principal,
                   COALESCE(i.costo_unitario_usd,0) AS costo_unitario_usd,
                   COALESCE(i.stock_actual,0) AS stock_actual,
                   COALESCE(i.stock_minimo_operativo,0) AS stock_minimo_operativo,
                   COALESCE(i.punto_reorden,0) AS punto_reorden,
                   COALESCE(i.stock_ideal,0) AS stock_ideal,
                   COALESCE(i.stock_maximo,0) AS stock_maximo,
                   COALESCE(i.factor_compra_base,1) AS factor_compra_base,
                   COALESCE(i.controla_lotes,0) AS controla_lotes,
                   COALESCE(i.controla_vencimiento,0) AS controla_vencimiento,
                   COALESCE(i.dias_vida_util,0) AS dias_vida_util
            FROM inventario i
            WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY COALESCE(i.nombre,'') COLLATE NOCASE
        """, conn)
    if df.empty:
        return df

    def evaluar(row: pd.Series) -> pd.Series:
        faltantes: list[str] = []
        if not str(row["sku"]).strip(): faltantes.append("SKU")
        if not str(row["nombre"]).strip(): faltantes.append("Nombre")
        if not str(row["categoria"]).strip(): faltantes.append("Categoría")
        if not str(row["unidad_base"]).strip(): faltantes.append("Unidad base")
        if not str(row["clase_articulo"]).strip(): faltantes.append("Clasificación")
        if not str(row["ubicacion"]).strip(): faltantes.append("Ubicación")
        if not str(row["proveedor_principal"]).strip(): faltantes.append("Proveedor")
        if float(row["costo_unitario_usd"] or 0) <= 0: faltantes.append("Costo unitario")
        if float(row["stock_minimo_operativo"] or 0) <= 0: faltantes.append("Stock mínimo")
        if float(row["punto_reorden"] or 0) <= 0: faltantes.append("Punto de reorden")
        if float(row["stock_ideal"] or 0) <= 0: faltantes.append("Stock ideal")
        if float(row["stock_maximo"] or 0) <= 0: faltantes.append("Stock máximo")
        if float(row["factor_compra_base"] or 0) <= 0: faltantes.append("Contenido por compra")
        if bool(row["controla_vencimiento"]) and int(row["dias_vida_util"] or 0) <= 0:
            faltantes.append("Vida útil")
        total = 13 + (1 if bool(row["controla_vencimiento"]) else 0)
        completos = max(total - len(faltantes), 0)
        porcentaje = round(completos / total * 100, 1) if total else 0
        if porcentaje >= 90:
            estado = "EXCELENTE"
        elif porcentaje >= 75:
            estado = "ACEPTABLE"
        elif porcentaje >= 50:
            estado = "INCOMPLETO"
        else:
            estado = "CRÍTICO"
        return pd.Series({
            "calidad_pct": porcentaje,
            "estado_calidad": estado,
            "campos_faltantes": ", ".join(faltantes),
            "cantidad_faltantes": len(faltantes),
        })

    evaluacion = df.apply(evaluar, axis=1)
    return pd.concat([df, evaluacion], axis=1)


def resumen_calidad() -> dict[str, float]:
    df = diagnostico_calidad()
    if df.empty:
        return {
            "articulos": 0,
            "calidad_promedio": 0,
            "excelentes": 0,
            "incompletos": 0,
            "criticos": 0,
        }
    return {
        "articulos": float(len(df)),
        "calidad_promedio": float(df["calidad_pct"].mean()),
        "excelentes": float((df["estado_calidad"] == "EXCELENTE").sum()),
        "incompletos": float(df["estado_calidad"].isin(["ACEPTABLE", "INCOMPLETO"]).sum()),
        "criticos": float((df["estado_calidad"] == "CRÍTICO").sum()),
    }


def actualizar_datos_clave(
    inventario_id: int,
    *,
    ubicacion: str,
    proveedor: str,
    costo_unitario_usd: float,
    stock_minimo: float,
    punto_reorden: float,
    stock_ideal: float,
    stock_maximo: float,
    factor_compra: float,
) -> None:
    ensure_schema()
    if costo_unitario_usd < 0 or min(stock_minimo, punto_reorden, stock_ideal, stock_maximo) < 0:
        raise ValueError("Los valores numéricos no pueden ser negativos.")
    if stock_maximo and stock_ideal and stock_maximo < stock_ideal:
        raise ValueError("El stock máximo no puede ser menor que el stock ideal.")
    if stock_ideal and punto_reorden and stock_ideal < punto_reorden:
        raise ValueError("El stock ideal no puede ser menor que el punto de reorden.")
    with db_transaction() as conn:
        conn.execute("""
            UPDATE inventario
               SET ubicacion=?, proveedor_principal=?, costo_unitario_usd=?,
                   stock_minimo_operativo=?, punto_reorden=?, stock_ideal=?,
                   stock_maximo=?, factor_compra_base=?
             WHERE id=?
        """, (
            str(ubicacion or "").strip(), str(proveedor or "").strip(),
            float(costo_unitario_usd or 0), float(stock_minimo or 0),
            float(punto_reorden or 0), float(stock_ideal or 0),
            float(stock_maximo or 0), float(factor_compra or 1), int(inventario_id),
        ))
