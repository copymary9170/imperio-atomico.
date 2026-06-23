from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text

TIPOS_USO = ["Insumo", "Reventa", "Ambos"]
USOS_VALIDOS = {"servicios", "venta_detal", "manualidades"}
TIPOS_FISICOS = {
    "lamina": "Lámina / hoja / pliego",
    "rollo": "Rollo",
    "volumen": "Volumen",
    "peso": "Peso",
    "unidad": "Unidad / pieza",
    "agrupacion": "Paquete / caja",
}
UNIDADES_BASE = [
    "unidad", "hoja", "pliego", "rollo", "g", "kg", "ml", "L",
    "cm", "m", "cm²", "m²", "cm³",
]
UNIDADES_POR_TIPO = {
    "lamina": {"hoja", "pliego", "cm²", "m²"},
    "rollo": {"rollo", "cm", "m", "cm²", "m²"},
    "volumen": {"ml", "L", "cm³"},
    "peso": {"g", "kg"},
    "unidad": {"unidad"},
    "agrupacion": {"unidad", "hoja", "pliego", "ml", "L", "cm³", "g", "kg", "cm", "m", "cm²", "m²"},
}

CAMPOS_FICHA_AVANZADA: dict[str, str] = {
    "marca": "TEXT", "color": "TEXT", "tamano": "TEXT", "gramaje": "TEXT", "acabado": "TEXT",
    "tipo_fisico": "TEXT NOT NULL DEFAULT 'unidad'",
    "cantidad_presentacion": "REAL NOT NULL DEFAULT 0",
    "unidad_presentacion": "TEXT",
    "ancho_cm": "REAL NOT NULL DEFAULT 0", "alto_cm": "REAL NOT NULL DEFAULT 0",
    "margen_izquierdo_cm": "REAL NOT NULL DEFAULT 0", "margen_derecho_cm": "REAL NOT NULL DEFAULT 0",
    "margen_superior_cm": "REAL NOT NULL DEFAULT 0", "margen_inferior_cm": "REAL NOT NULL DEFAULT 0",
    "separacion_cm": "REAL NOT NULL DEFAULT 0", "sangrado_cm": "REAL NOT NULL DEFAULT 0",
    "merma_base_pct": "REAL NOT NULL DEFAULT 0", "unidad_compra": "TEXT",
    "contenido_compra": "REAL NOT NULL DEFAULT 0", "proveedor_principal": "TEXT",
    "proveedor_principal_id": "INTEGER", "ubicacion": "TEXT",
    "stock_ideal": "REAL NOT NULL DEFAULT 0", "stock_maximo": "REAL NOT NULL DEFAULT 0",
    "punto_reorden": "REAL NOT NULL DEFAULT 0", "observaciones": "TEXT",
}


def _table_columns(conn: Any, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _normalizar_tipo_fisico(value: Any) -> str:
    raw = clean_text(value).lower()
    aliases = {
        "lámina / hoja / pliego (cm y cm²)": "lamina", "lámina / hoja / pliego": "lamina",
        "lamina": "lamina", "hoja": "lamina", "pliego": "lamina",
        "rollo": "rollo", "volumen (ml, l, cm³)": "volumen", "volumen": "volumen",
        "peso (g, kg)": "peso", "peso": "peso", "unidad / pieza": "unidad",
        "unidad": "unidad", "paquete / caja": "agrupacion", "agrupacion": "agrupacion",
    }
    tipo = aliases.get(raw, raw or "unidad")
    if tipo not in TIPOS_FISICOS:
        raise ValueError("Tipo físico inválido.")
    return tipo


def _normalizar_unidad(value: Any) -> str:
    raw = clean_text(value)
    aliases = {"l": "L", "litro": "L", "litros": "L", "cm2": "cm²", "m2": "m²", "cm3": "cm³", "gr": "g"}
    return aliases.get(raw.lower(), raw)


def validar_configuracion_fisica(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    tipo = _normalizar_tipo_fisico(out.get("tipo_fisico"))
    unidad = _normalizar_unidad(out.get("unidad_base") or "unidad")
    if unidad in {"resma", "paquete", "caja"}:
        raise ValueError("Resma, paquete y caja son unidades de compra. Selecciona la unidad contenida como unidad base.")
    permitidas = UNIDADES_POR_TIPO[tipo]
    if unidad not in permitidas:
        raise ValueError(f"La unidad base '{unidad}' no corresponde al tipo físico '{TIPOS_FISICOS[tipo]}'.")
    ancho = float(out.get("ancho_cm") or 0)
    alto = float(out.get("alto_cm") or 0)
    if tipo == "lamina" and (ancho <= 0 or alto <= 0):
        raise ValueError("Las láminas, hojas y pliegos requieren ancho y alto mayores que cero.")
    unidad_compra = _normalizar_unidad(out.get("unidad_compra"))
    contenido = float(out.get("contenido_compra") or 0)
    if unidad_compra and unidad_compra != unidad and contenido <= 0:
        raise ValueError("Indica cuánto contiene cada unidad de compra.")
    if unidad_compra == "resma" and unidad != "hoja":
        raise ValueError("Una resma debe usar 'hoja' como unidad base.")
    out["tipo_fisico"] = tipo
    out["unidad_base"] = unidad
    out["unidad_compra"] = unidad_compra
    return out


def ensure_inventario_unificado_schema() -> None:
    with db_transaction() as conn:
        cols = _table_columns(conn, "inventario")
        migrations = {
            "tipo_uso": "TEXT NOT NULL DEFAULT 'Ambos'", "unidad_base": "TEXT",
            "permite_fraccionamiento": "INTEGER NOT NULL DEFAULT 1", **CAMPOS_FICHA_AVANZADA,
        }
        for name, ddl in migrations.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {name} {ddl}")
                cols.add(name)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventario_usos (
                inventario_id INTEGER NOT NULL,
                uso TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (inventario_id, uso),
                FOREIGN KEY (inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inventario_usos_uso ON inventario_usos(uso)")
        conn.execute("""
            UPDATE inventario
            SET tipo_uso = CASE
                WHEN lower(COALESCE(tipo_uso, '')) IN ('insumo','reventa','ambos')
                    THEN upper(substr(tipo_uso,1,1)) || lower(substr(tipo_uso,2))
                ELSE 'Ambos' END,
                unidad_base = COALESCE(NULLIF(unidad_base,''), NULLIF(unidad,''), 'unidad'),
                tipo_fisico = CASE
                    WHEN COALESCE(tipo_fisico,'') <> '' AND tipo_fisico <> 'unidad' THEN tipo_fisico
                    WHEN lower(COALESCE(unidad_base, unidad, '')) IN ('hoja','pliego','cm²','m²','cm2','m2') THEN 'lamina'
                    WHEN lower(COALESCE(unidad_base, unidad, '')) IN ('rollo','cm','m') THEN 'rollo'
                    WHEN lower(COALESCE(unidad_base, unidad, '')) IN ('ml','l','cm³','cm3') THEN 'volumen'
                    WHEN lower(COALESCE(unidad_base, unidad, '')) IN ('g','kg','gr') THEN 'peso'
                    ELSE COALESCE(NULLIF(tipo_fisico,''),'unidad') END,
                permite_fraccionamiento = COALESCE(permite_fraccionamiento, 1)
        """)


def _query_inventario(activos_only: bool = True) -> pd.DataFrame:
    where = "WHERE lower(COALESCE(i.estado,'activo'))='activo'" if activos_only else ""
    with db_transaction() as conn:
        return pd.read_sql_query(f"""
            SELECT i.id, i.sku, i.nombre, i.categoria,
                   COALESCE(NULLIF(i.unidad_base,''), i.unidad, 'unidad') AS unidad_base,
                   i.unidad, COALESCE(i.tipo_uso,'Ambos') AS tipo_uso,
                   COALESCE(i.tipo_fisico,'unidad') AS tipo_fisico,
                   COALESCE(i.cantidad_presentacion,0) AS cantidad_presentacion,
                   COALESCE(i.unidad_presentacion,'') AS unidad_presentacion,
                   COALESCE(i.permite_fraccionamiento,1) AS permite_fraccionamiento,
                   COALESCE(i.stock_actual,0) AS stock_actual, COALESCE(i.stock_minimo,0) AS stock_minimo,
                   COALESCE(i.costo_unitario_usd,0) AS costo_unitario_usd,
                   COALESCE(i.precio_venta_usd,0) AS precio_venta_usd,
                   COALESCE(i.marca,'') AS marca, COALESCE(i.color,'') AS color,
                   COALESCE(i.tamano,'') AS tamano, COALESCE(i.gramaje,'') AS gramaje,
                   COALESCE(i.acabado,'') AS acabado, COALESCE(i.ancho_cm,0) AS ancho_cm,
                   COALESCE(i.alto_cm,0) AS alto_cm, COALESCE(i.margen_izquierdo_cm,0) AS margen_izquierdo_cm,
                   COALESCE(i.margen_derecho_cm,0) AS margen_derecho_cm,
                   COALESCE(i.margen_superior_cm,0) AS margen_superior_cm,
                   COALESCE(i.margen_inferior_cm,0) AS margen_inferior_cm,
                   COALESCE(i.separacion_cm,0) AS separacion_cm, COALESCE(i.sangrado_cm,0) AS sangrado_cm,
                   COALESCE(i.merma_base_pct,0) AS merma_base_pct,
                   ROUND(COALESCE(i.ancho_cm,0) * COALESCE(i.alto_cm,0), 4) AS area_total_cm2,
                   ROUND(MAX(COALESCE(i.ancho_cm,0)-COALESCE(i.margen_izquierdo_cm,0)-COALESCE(i.margen_derecho_cm,0),0)
                       * MAX(COALESCE(i.alto_cm,0)-COALESCE(i.margen_superior_cm,0)-COALESCE(i.margen_inferior_cm,0),0),4) AS area_util_cm2,
                   CASE WHEN COALESCE(i.ancho_cm,0)*COALESCE(i.alto_cm,0)>0 THEN ROUND(100-((MAX(COALESCE(i.ancho_cm,0)-COALESCE(i.margen_izquierdo_cm,0)-COALESCE(i.margen_derecho_cm,0),0)*MAX(COALESCE(i.alto_cm,0)-COALESCE(i.margen_superior_cm,0)-COALESCE(i.margen_inferior_cm,0),0))/(COALESCE(i.ancho_cm,0)*COALESCE(i.alto_cm,0))*100),2) ELSE 0 END AS merma_dimensional_pct,
                   COALESCE(i.unidad_compra,'') AS unidad_compra, COALESCE(i.contenido_compra,0) AS contenido_compra,
                   COALESCE(i.proveedor_principal,'') AS proveedor_principal,
                   i.proveedor_principal_id, COALESCE(p.nombre,i.proveedor_principal,'') AS proveedor_principal_nombre,
                   COALESCE(i.ubicacion,'') AS ubicacion, COALESCE(i.stock_ideal,0) AS stock_ideal,
                   COALESCE(i.stock_maximo,0) AS stock_maximo, COALESCE(i.punto_reorden,0) AS punto_reorden,
                   COALESCE(i.observaciones,'') AS observaciones, COALESCE(i.estado,'activo') AS estado,
                   COALESCE((SELECT group_concat(u.uso, ', ') FROM inventario_usos u WHERE u.inventario_id=i.id),'') AS usos
            FROM inventario i LEFT JOIN proveedores p ON p.id=i.proveedor_principal_id
            {where} ORDER BY i.nombre COLLATE NOCASE
        """, conn)


def _try_restore_inventory_json() -> None:
    try:
        from services.inventario_cloud_sync import restore_inventario_from_github_if_empty
        restore_inventario_from_github_if_empty("Sistema")
    except Exception:
        pass


def _try_export_inventory_json() -> None:
    try:
        from services.inventario_cloud_sync import export_inventario_to_github
        export_inventario_to_github()
    except Exception:
        pass


def listar_inventario_unificado(activos_only: bool = True) -> pd.DataFrame:
    ensure_inventario_unificado_schema()
    df = _query_inventario(activos_only)
    if df.empty:
        _try_restore_inventory_json()
        df = _query_inventario(activos_only)
    return df


def guardar_clasificacion_inventario(inventario_id: int, *, tipo_uso: str, unidad_base: str, permite_fraccionamiento: bool) -> None:
    ensure_inventario_unificado_schema()
    tipo = clean_text(tipo_uso).title()
    if tipo not in TIPOS_USO:
        raise ValueError("Tipo de uso inválido.")
    unidad = _normalizar_unidad(unidad_base) or "unidad"
    with db_transaction() as conn:
        conn.execute("UPDATE inventario SET tipo_uso=?, unidad_base=?, unidad=?, permite_fraccionamiento=? WHERE id=?",
                     (tipo, unidad, unidad, 1 if permite_fraccionamiento else 0, int(inventario_id)))
    _try_export_inventory_json()


def crear_item_unificado(data: dict[str, Any], usuario: str) -> int:
    ensure_inventario_unificado_schema()
    data = validar_configuracion_fisica(data)
    nombre, sku = clean_text(data.get("nombre")), clean_text(data.get("sku"))
    if not nombre or not sku:
        raise ValueError("Nombre y SKU son obligatorios.")
    usos = {clean_text(x).lower().replace(" ", "_") for x in data.get("usos", []) if clean_text(x)}
    usos &= USOS_VALIDOS
    if not usos:
        raise ValueError("Selecciona al menos un uso comercial.")
    tipo_uso = "Ambos" if {"servicios", "venta_detal"} <= usos else ("Reventa" if "venta_detal" in usos else "Insumo")
    unidad = data["unidad_base"]
    proveedor_id = data.get("proveedor_principal_id")
    with db_transaction() as conn:
        if conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?)", (sku,)).fetchone():
            raise ValueError("Ya existe un producto con ese SKU.")
        proveedor_nombre = ""
        if proveedor_id:
            row = conn.execute("SELECT nombre FROM proveedores WHERE id=? AND COALESCE(activo,1)=1", (int(proveedor_id),)).fetchone()
            if not row:
                raise ValueError("El proveedor seleccionado no existe o está inactivo.")
            proveedor_nombre = str(row["nombre"])
        cur = conn.execute("""
            INSERT INTO inventario(
                usuario,sku,nombre,categoria,unidad,unidad_base,tipo_uso,tipo_fisico,
                cantidad_presentacion,unidad_presentacion,permite_fraccionamiento,
                stock_actual,stock_minimo,costo_unitario_usd,precio_venta_usd,marca,color,tamano,
                gramaje,acabado,ancho_cm,alto_cm,margen_izquierdo_cm,margen_derecho_cm,
                margen_superior_cm,margen_inferior_cm,separacion_cm,sangrado_cm,merma_base_pct,
                unidad_compra,contenido_compra,proveedor_principal,proveedor_principal_id,ubicacion,
                stock_ideal,stock_maximo,punto_reorden,observaciones,estado
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'activo')
        """, (
            usuario,sku,nombre,clean_text(data.get("categoria") or "General"),unidad,unidad,tipo_uso,data["tipo_fisico"],
            float(data.get("cantidad_presentacion") or 0),clean_text(data.get("unidad_presentacion")),
            1 if data.get("permite_fraccionamiento",True) else 0,float(data.get("stock_actual") or 0),
            float(data.get("stock_minimo") or 0),float(data.get("costo_unitario_usd") or 0),
            float(data.get("precio_venta_usd") or 0),clean_text(data.get("marca")),clean_text(data.get("color")),
            clean_text(data.get("tamano")),clean_text(data.get("gramaje")),clean_text(data.get("acabado")),
            float(data.get("ancho_cm") or 0),float(data.get("alto_cm") or 0),
            float(data.get("margen_izquierdo_cm") or 0),float(data.get("margen_derecho_cm") or 0),
            float(data.get("margen_superior_cm") or 0),float(data.get("margen_inferior_cm") or 0),
            float(data.get("separacion_cm") or 0),float(data.get("sangrado_cm") or 0),
            float(data.get("merma_base_pct") or 0),clean_text(data.get("unidad_compra")),
            float(data.get("contenido_compra") or 0),proveedor_nombre,int(proveedor_id) if proveedor_id else None,
            clean_text(data.get("ubicacion")),float(data.get("stock_ideal") or 0),
            float(data.get("stock_maximo") or 0),float(data.get("punto_reorden") or 0),clean_text(data.get("observaciones")),
        ))
        item_id = int(cur.lastrowid)
        conn.executemany("INSERT OR IGNORE INTO inventario_usos(inventario_id,uso) VALUES(?,?)", [(item_id,u) for u in sorted(usos)])
    _try_export_inventory_json()
    return item_id
