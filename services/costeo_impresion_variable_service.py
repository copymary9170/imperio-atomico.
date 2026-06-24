from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction


CANALES = ("c", "m", "y", "k")


def ensure_schema() -> None:
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS perfiles_impresion_costeo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                impresora TEXT,
                tinta_costo_c_usd REAL NOT NULL DEFAULT 0,
                tinta_costo_m_usd REAL NOT NULL DEFAULT 0,
                tinta_costo_y_usd REAL NOT NULL DEFAULT 0,
                tinta_costo_k_usd REAL NOT NULL DEFAULT 0,
                rendimiento_c_5pct REAL NOT NULL DEFAULT 1,
                rendimiento_m_5pct REAL NOT NULL DEFAULT 1,
                rendimiento_y_5pct REAL NOT NULL DEFAULT 1,
                rendimiento_k_5pct REAL NOT NULL DEFAULT 1,
                mantenimiento_por_pagina_usd REAL NOT NULL DEFAULT 0,
                depreciacion_por_pagina_usd REAL NOT NULL DEFAULT 0,
                energia_por_pagina_usd REAL NOT NULL DEFAULT 0,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS costeos_impresion_variable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                perfil_id INTEGER,
                cantidad REAL NOT NULL DEFAULT 1,
                paginas_por_unidad REAL NOT NULL DEFAULT 1,
                factor_area REAL NOT NULL DEFAULT 1,
                cobertura_c_pct REAL NOT NULL DEFAULT 0,
                cobertura_m_pct REAL NOT NULL DEFAULT 0,
                cobertura_y_pct REAL NOT NULL DEFAULT 0,
                cobertura_k_pct REAL NOT NULL DEFAULT 0,
                costo_tinta_usd REAL NOT NULL DEFAULT 0,
                costo_papel_usd REAL NOT NULL DEFAULT 0,
                costo_acabados_usd REAL NOT NULL DEFAULT 0,
                costo_mano_obra_usd REAL NOT NULL DEFAULT 0,
                costo_indirectos_usd REAL NOT NULL DEFAULT 0,
                costo_merma_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                precio_sugerido_usd REAL NOT NULL DEFAULT 0,
                margen_pct REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY(perfil_id) REFERENCES perfiles_impresion_costeo(id)
            )
        """)


def guardar_perfil(
    *,
    nombre: str,
    impresora: str,
    costos_tinta: dict[str, float],
    rendimientos_5pct: dict[str, float],
    mantenimiento_por_pagina: float,
    depreciacion_por_pagina: float,
    energia_por_pagina: float,
) -> int:
    ensure_schema()
    nombre_ok = str(nombre or "").strip()
    if not nombre_ok:
        raise ValueError("El nombre del perfil es obligatorio.")
    for canal in CANALES:
        if float(costos_tinta.get(canal, 0) or 0) < 0:
            raise ValueError("Los costos de tinta no pueden ser negativos.")
        if float(rendimientos_5pct.get(canal, 0) or 0) <= 0:
            raise ValueError("El rendimiento de cada tinta debe ser mayor que cero.")
    with db_transaction() as conn:
        existente = conn.execute(
            "SELECT id FROM perfiles_impresion_costeo WHERE lower(nombre)=lower(?)",
            (nombre_ok,),
        ).fetchone()
        valores = (
            nombre_ok, str(impresora or "").strip(),
            float(costos_tinta.get("c", 0)), float(costos_tinta.get("m", 0)),
            float(costos_tinta.get("y", 0)), float(costos_tinta.get("k", 0)),
            float(rendimientos_5pct.get("c", 1)), float(rendimientos_5pct.get("m", 1)),
            float(rendimientos_5pct.get("y", 1)), float(rendimientos_5pct.get("k", 1)),
            float(mantenimiento_por_pagina or 0), float(depreciacion_por_pagina or 0),
            float(energia_por_pagina or 0),
        )
        if existente:
            conn.execute("""
                UPDATE perfiles_impresion_costeo SET
                    impresora=?,tinta_costo_c_usd=?,tinta_costo_m_usd=?,tinta_costo_y_usd=?,tinta_costo_k_usd=?,
                    rendimiento_c_5pct=?,rendimiento_m_5pct=?,rendimiento_y_5pct=?,rendimiento_k_5pct=?,
                    mantenimiento_por_pagina_usd=?,depreciacion_por_pagina_usd=?,energia_por_pagina_usd=?,activo=1
                WHERE id=?
            """, valores[1:] + (int(existente["id"]),))
            return int(existente["id"])
        cur = conn.execute("""
            INSERT INTO perfiles_impresion_costeo(
                nombre,impresora,tinta_costo_c_usd,tinta_costo_m_usd,tinta_costo_y_usd,tinta_costo_k_usd,
                rendimiento_c_5pct,rendimiento_m_5pct,rendimiento_y_5pct,rendimiento_k_5pct,
                mantenimiento_por_pagina_usd,depreciacion_por_pagina_usd,energia_por_pagina_usd
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, valores)
        return int(cur.lastrowid)


def listar_perfiles() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT * FROM perfiles_impresion_costeo
            WHERE activo=1 ORDER BY nombre COLLATE NOCASE
        """, conn)


def calcular_costeo_variable(
    *,
    perfil: dict[str, Any],
    cantidad: float,
    paginas_por_unidad: float,
    factor_area: float,
    coberturas_pct: dict[str, float],
    costo_papel_unitario: float,
    hojas_por_unidad: float,
    costo_acabado_unitario: float,
    mano_obra_total: float,
    otros_indirectos_total: float,
    merma_pct: float,
    margen_pct: float,
) -> dict[str, Any]:
    cantidad = float(cantidad or 0)
    paginas_por_unidad = float(paginas_por_unidad or 0)
    factor_area = float(factor_area or 0)
    hojas_por_unidad = float(hojas_por_unidad or 0)
    if cantidad <= 0 or paginas_por_unidad <= 0 or factor_area <= 0:
        raise ValueError("Cantidad, páginas y factor de área deben ser mayores que cero.")
    if not 0 <= float(merma_pct or 0) < 100:
        raise ValueError("La merma debe estar entre 0% y menos de 100%.")
    if not 0 <= float(margen_pct or 0) < 100:
        raise ValueError("El margen debe estar entre 0% y menos de 100%.")

    paginas_equivalentes = cantidad * paginas_por_unidad * factor_area
    detalle_tinta: dict[str, float] = {}
    costo_tinta = 0.0
    for canal in CANALES:
        cobertura = max(float(coberturas_pct.get(canal, 0) or 0), 0)
        costo_botella = max(float(perfil.get(f"tinta_costo_{canal}_usd", 0) or 0), 0)
        rendimiento = max(float(perfil.get(f"rendimiento_{canal}_5pct", 1) or 1), 0.000001)
        costo_canal = paginas_equivalentes * (cobertura / 5.0) * (costo_botella / rendimiento)
        detalle_tinta[canal] = round(costo_canal, 8)
        costo_tinta += costo_canal

    paginas_fisicas = cantidad * paginas_por_unidad
    costo_papel = cantidad * hojas_por_unidad * max(float(costo_papel_unitario or 0), 0)
    costo_acabados = cantidad * max(float(costo_acabado_unitario or 0), 0)
    costo_maquina = paginas_fisicas * sum(max(float(perfil.get(campo, 0) or 0), 0) for campo in (
        "mantenimiento_por_pagina_usd", "depreciacion_por_pagina_usd", "energia_por_pagina_usd"
    ))
    base = costo_tinta + costo_papel + costo_acabados + costo_maquina + max(float(mano_obra_total or 0), 0) + max(float(otros_indirectos_total or 0), 0)
    costo_merma = base * (float(merma_pct or 0) / 100)
    costo_total = base + costo_merma
    precio = costo_total / (1 - float(margen_pct or 0) / 100)

    return {
        "paginas_fisicas": round(paginas_fisicas, 6),
        "paginas_equivalentes_carta": round(paginas_equivalentes, 6),
        "detalle_tinta": detalle_tinta,
        "costo_tinta_usd": round(costo_tinta, 8),
        "costo_papel_usd": round(costo_papel, 6),
        "costo_acabados_usd": round(costo_acabados, 6),
        "costo_maquina_usd": round(costo_maquina, 6),
        "costo_mano_obra_usd": round(max(float(mano_obra_total or 0), 0), 6),
        "costo_indirectos_usd": round(max(float(otros_indirectos_total or 0), 0), 6),
        "costo_merma_usd": round(costo_merma, 6),
        "costo_total_usd": round(costo_total, 6),
        "costo_unitario_usd": round(costo_total / cantidad, 6),
        "precio_sugerido_usd": round(precio, 6),
        "precio_unitario_sugerido_usd": round(precio / cantidad, 6),
        "utilidad_estimada_usd": round(precio - costo_total, 6),
    }


def guardar_costeo(
    *,
    usuario: str,
    descripcion: str,
    perfil_id: int,
    cantidad: float,
    paginas_por_unidad: float,
    factor_area: float,
    coberturas_pct: dict[str, float],
    resultado: dict[str, Any],
    margen_pct: float,
    observaciones: str,
) -> int:
    ensure_schema()
    with db_transaction() as conn:
        cur = conn.execute("""
            INSERT INTO costeos_impresion_variable(
                usuario,descripcion,perfil_id,cantidad,paginas_por_unidad,factor_area,
                cobertura_c_pct,cobertura_m_pct,cobertura_y_pct,cobertura_k_pct,
                costo_tinta_usd,costo_papel_usd,costo_acabados_usd,costo_mano_obra_usd,
                costo_indirectos_usd,costo_merma_usd,costo_total_usd,precio_sugerido_usd,
                margen_pct,observaciones
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(usuario or "Sistema"), str(descripcion or "Trabajo de impresión").strip(), int(perfil_id),
            float(cantidad), float(paginas_por_unidad), float(factor_area),
            float(coberturas_pct.get("c", 0)), float(coberturas_pct.get("m", 0)),
            float(coberturas_pct.get("y", 0)), float(coberturas_pct.get("k", 0)),
            float(resultado["costo_tinta_usd"]), float(resultado["costo_papel_usd"]),
            float(resultado["costo_acabados_usd"]), float(resultado["costo_mano_obra_usd"]),
            float(resultado["costo_indirectos_usd"] + resultado["costo_maquina_usd"]),
            float(resultado["costo_merma_usd"]), float(resultado["costo_total_usd"]),
            float(resultado["precio_sugerido_usd"]), float(margen_pct), str(observaciones or "").strip(),
        ))
        return int(cur.lastrowid)


def listar_costeos(limit: int = 100) -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT c.id,c.fecha,c.descripcion,p.nombre perfil,c.cantidad,c.paginas_por_unidad,
                   c.factor_area,c.cobertura_c_pct,c.cobertura_m_pct,c.cobertura_y_pct,c.cobertura_k_pct,
                   c.costo_tinta_usd,c.costo_papel_usd,c.costo_total_usd,c.precio_sugerido_usd,c.margen_pct
            FROM costeos_impresion_variable c
            LEFT JOIN perfiles_impresion_costeo p ON p.id=c.perfil_id
            ORDER BY c.id DESC LIMIT ?
        """, conn, params=(int(limit),))
