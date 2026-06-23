from __future__ import annotations

import math
from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.inventario_operativo_service import ensure_schema as ensure_operativo_schema

UNIDADES_NORMALIZADAS = {
    "lamina": "cm²",
    "rollo": "cm²",
    "volumen": "ml",
    "peso": "g",
    "unidad": "unidad",
    "agrupacion": "unidad",
}


def _columns(conn: Any, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    ensure_operativo_schema()
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        additions = {
            "unidad_control": "TEXT",
            "stock_minimo_operativo": "REAL NOT NULL DEFAULT 0",
            "stock_seguridad": "REAL NOT NULL DEFAULT 0",
            "consumo_promedio_diario": "REAL NOT NULL DEFAULT 0",
            "dias_reposicion": "REAL NOT NULL DEFAULT 0",
            "control_profesional_activo": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {name} {ddl}")


def _to_control(tipo: str, unidad_base: str, stock: float, ancho: float, alto: float) -> tuple[float, str, float]:
    tipo = str(tipo or "unidad")
    unidad = str(unidad_base or "unidad")
    factor = 1.0
    unidad_control = UNIDADES_NORMALIZADAS.get(tipo, unidad)
    if tipo == "lamina":
        if unidad in {"hoja", "pliego"}:
            factor = max(ancho, 0) * max(alto, 0)
        elif unidad == "m²":
            factor = 10000.0
        else:
            factor = 1.0
    elif tipo == "rollo":
        if unidad == "m²": factor = 10000.0
        elif unidad == "m" and ancho > 0: factor = ancho * 100.0
        elif unidad == "cm" and ancho > 0: factor = ancho
        elif unidad == "rollo": factor = max(ancho, 0) * max(alto, 0)
    elif tipo == "volumen":
        if unidad == "L": factor = 1000.0
        elif unidad == "cm³": factor = 1.0
    elif tipo == "peso":
        if unidad == "kg": factor = 1000.0
    return float(stock) * factor, unidad_control, factor


def guardar_parametros(
    inventario_id: int,
    *,
    minimo_operativo: float,
    stock_seguridad: float,
    consumo_promedio_diario: float,
    dias_reposicion: float,
) -> None:
    ensure_schema()
    with db_transaction() as conn:
        row = conn.execute("SELECT tipo_fisico,unidad_base,stock_actual,ancho_cm,alto_cm FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
        if not row:
            raise ValueError("Artículo no encontrado.")
        _, unidad_control, _ = _to_control(row["tipo_fisico"], row["unidad_base"], row["stock_actual"], row["ancho_cm"], row["alto_cm"])
        punto = float(consumo_promedio_diario or 0) * float(dias_reposicion or 0) + float(stock_seguridad or 0)
        conn.execute(
            """UPDATE inventario SET unidad_control=?, stock_minimo_operativo=?, stock_seguridad=?,
               consumo_promedio_diario=?, dias_reposicion=?, punto_reorden=? WHERE id=?""",
            (unidad_control, float(minimo_operativo or 0), float(stock_seguridad or 0), float(consumo_promedio_diario or 0), float(dias_reposicion or 0), punto, int(inventario_id)),
        )


def inventario_fisico() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        rows = conn.execute("""
            SELECT i.id,i.sku,i.nombre,COALESCE(i.tipo_fisico,'unidad') tipo_fisico,
                   COALESCE(i.unidad_base,i.unidad,'unidad') unidad_base,
                   COALESCE(i.stock_actual,0) stock_actual,COALESCE(i.ancho_cm,0) ancho_cm,
                   COALESCE(i.alto_cm,0) alto_cm,COALESCE(i.stock_minimo_operativo,0) minimo_operativo,
                   COALESCE(i.stock_seguridad,0) stock_seguridad,COALESCE(i.punto_reorden,0) punto_reorden,
                   COALESCE(i.stock_ideal,0) stock_ideal,
                   COALESCE((SELECT SUM(r.cantidad) FROM reservas_inventario r WHERE r.inventario_id=i.id AND r.estado='activa'),0) reservado_base
            FROM inventario i WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY i.nombre COLLATE NOCASE
        """).fetchall()
    data=[]
    for r in rows:
        fisico, unidad_control, factor = _to_control(r["tipo_fisico"],r["unidad_base"],r["stock_actual"],r["ancho_cm"],r["alto_cm"])
        reservado=float(r["reservado_base"] or 0)*factor
        disponible=fisico-reservado
        minimo=float(r["minimo_operativo"] or 0)
        reorden=float(r["punto_reorden"] or 0)
        if disponible <= 0: estado="⚫ Agotado"
        elif minimo > 0 and disponible <= minimo: estado="🔴 Crítico"
        elif reorden > 0 and disponible <= reorden: estado="🟡 Comprar pronto"
        elif reservado > 0 and reservado >= fisico * 0.5: estado="🔵 Muy comprometido"
        else: estado="🟢 Suficiente"
        data.append({
            "id":int(r["id"]),"sku":r["sku"],"artículo":r["nombre"],"tipo":r["tipo_fisico"],
            "unidad_control":unidad_control,"stock_físico":round(fisico,4),"reservado":round(reservado,4),
            "disponible":round(disponible,4),"mínimo_operativo":round(minimo,4),
            "punto_reorden":round(reorden,4),"estado":estado,
        })
    return pd.DataFrame(data)


def capacidad_recetas() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        recetas = conn.execute("SELECT id,nombre,rendimiento,unidad_rendimiento FROM recetas_inventario WHERE activo=1 ORDER BY nombre").fetchall()
        inventario = inventario_fisico()
        resultados=[]
        for receta in recetas:
            detalles = conn.execute("""
                SELECT d.insumo_id,d.cantidad,d.merma_pct,i.nombre
                FROM recetas_inventario_detalle d JOIN inventario i ON i.id=d.insumo_id
                WHERE d.receta_id=?
            """, (int(receta["id"]),)).fetchall()
            capacidades=[]
            limitantes=[]
            for d in detalles:
                fila=inventario[inventario["id"]==int(d["insumo_id"])]
                if fila.empty: continue
                disponible=float(fila.iloc[0]["disponible"])
                consumo=float(d["cantidad"] or 0)*(1+float(d["merma_pct"] or 0)/100)
                if consumo <= 0: continue
                cap=math.floor(disponible/consumo)*float(receta["rendimiento"] or 1)
                capacidades.append(cap)
                limitantes.append((cap,str(d["nombre"])))
            capacidad=min(capacidades) if capacidades else 0
            material=min(limitantes,key=lambda x:x[0])[1] if limitantes else "Sin materiales"
            resultados.append({"receta":receta["nombre"],"capacidad_producción":capacidad,"unidad":receta["unidad_rendimiento"],"material_limitante":material})
    return pd.DataFrame(resultados)
