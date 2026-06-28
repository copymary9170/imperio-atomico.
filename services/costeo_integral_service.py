from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from database.connection import db_transaction


BASE_UNITS = [
    "unidad", "hoja", "ml", "l", "g", "kg", "cm", "m", "cm2", "m2",
    "pliego", "rollo", "pagina", "ciclo", "minuto", "hora",
]


@dataclass(frozen=True)
class AllocationResult:
    base_usd: float
    discount_usd: float
    tax_usd: float
    delivery_usd: float
    other_usd: float

    @property
    def landed_cost_usd(self) -> float:
        return max(0.0, self.base_usd - self.discount_usd + self.tax_usd + self.delivery_usd + self.other_usd)


def ensure_integrated_costing_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS unidades_conversion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventario_id INTEGER NOT NULL,
                unidad_compra TEXT NOT NULL,
                contenido_presentacion REAL NOT NULL DEFAULT 1,
                unidad_base TEXT NOT NULL,
                ancho_cm REAL NOT NULL DEFAULT 0,
                alto_cm REAL NOT NULL DEFAULT 0,
                largo_cm REAL NOT NULL DEFAULT 0,
                peso_g REAL NOT NULL DEFAULT 0,
                volumen_ml REAL NOT NULL DEFAULT 0,
                factor_conversion REAL NOT NULL DEFAULT 1,
                merma_estandar_pct REAL NOT NULL DEFAULT 0,
                activo INTEGER NOT NULL DEFAULT 1,
                UNIQUE(inventario_id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            );

            CREATE TABLE IF NOT EXISTS compras_costeo_cabecera (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                proveedor TEXT,
                numero_factura TEXT,
                moneda TEXT NOT NULL DEFAULT 'USD',
                tasa_cambio REAL NOT NULL DEFAULT 1,
                fecha_tasa TEXT,
                fuente_tasa TEXT,
                subtotal_usd REAL NOT NULL DEFAULT 0,
                descuento_usd REAL NOT NULL DEFAULT 0,
                iva_usd REAL NOT NULL DEFAULT 0,
                otros_impuestos_usd REAL NOT NULL DEFAULT 0,
                delivery_usd REAL NOT NULL DEFAULT 0,
                otros_gastos_usd REAL NOT NULL DEFAULT 0,
                total_pagado_usd REAL NOT NULL DEFAULT 0,
                iva_tratamiento TEXT NOT NULL DEFAULT 'costo',
                metodo_reparto TEXT NOT NULL DEFAULT 'valor',
                archivo_nombre TEXT,
                observaciones TEXT
            );

            CREATE TABLE IF NOT EXISTS compras_costeo_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL,
                inventario_id INTEGER,
                descripcion TEXT NOT NULL,
                cantidad_presentaciones REAL NOT NULL DEFAULT 1,
                precio_unitario_compra_usd REAL NOT NULL DEFAULT 0,
                subtotal_linea_usd REAL NOT NULL DEFAULT 0,
                descuento_asignado_usd REAL NOT NULL DEFAULT 0,
                iva_asignado_usd REAL NOT NULL DEFAULT 0,
                delivery_asignado_usd REAL NOT NULL DEFAULT 0,
                otros_asignados_usd REAL NOT NULL DEFAULT 0,
                costo_final_linea_usd REAL NOT NULL DEFAULT 0,
                unidad_compra TEXT NOT NULL DEFAULT 'unidad',
                contenido_presentacion REAL NOT NULL DEFAULT 1,
                unidad_base TEXT NOT NULL DEFAULT 'unidad',
                cantidad_base_ingresada REAL NOT NULL DEFAULT 0,
                costo_unitario_base_usd REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(compra_id) REFERENCES compras_costeo_cabecera(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            );

            CREATE TABLE IF NOT EXISTS activos_productivos_costeo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL,
                fecha_compra TEXT,
                costo_adquisicion_usd REAL NOT NULL DEFAULT 0,
                valor_residual_usd REAL NOT NULL DEFAULT 0,
                vida_util_tipo TEXT NOT NULL DEFAULT 'ciclos',
                vida_util_total REAL NOT NULL DEFAULT 1,
                contador_actual REAL NOT NULL DEFAULT 0,
                potencia_w REAL NOT NULL DEFAULT 0,
                mantenimiento_acumulado_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'activo',
                notas TEXT
            );

            CREATE TABLE IF NOT EXISTS recetas_costeo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL DEFAULT 'Servicio',
                margen_objetivo_pct REAL NOT NULL DEFAULT 40,
                version INTEGER NOT NULL DEFAULT 1,
                estado TEXT NOT NULL DEFAULT 'activa',
                notas TEXT
            );

            CREATE TABLE IF NOT EXISTS recetas_costeo_componentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receta_id INTEGER NOT NULL,
                tipo_componente TEXT NOT NULL,
                inventario_id INTEGER,
                activo_id INTEGER,
                descripcion TEXT NOT NULL,
                cantidad_teorica REAL NOT NULL DEFAULT 0,
                unidad_base TEXT NOT NULL DEFAULT 'unidad',
                merma_pct REAL NOT NULL DEFAULT 0,
                costo_manual_usd REAL NOT NULL DEFAULT 0,
                minutos REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(receta_id) REFERENCES recetas_costeo(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id),
                FOREIGN KEY(activo_id) REFERENCES activos_productivos_costeo(id)
            );

            CREATE TABLE IF NOT EXISTS cotizaciones_costeo_integral (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                cliente_id INTEGER,
                cliente TEXT NOT NULL,
                telefono TEXT,
                receta_id INTEGER,
                descripcion TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 1,
                archivo_nombre TEXT,
                archivo_ruta TEXT,
                confidencial INTEGER NOT NULL DEFAULT 0,
                costo_materiales_usd REAL NOT NULL DEFAULT 0,
                costo_merma_usd REAL NOT NULL DEFAULT 0,
                costo_activos_usd REAL NOT NULL DEFAULT 0,
                costo_mano_obra_usd REAL NOT NULL DEFAULT 0,
                costo_indirecto_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                margen_pct REAL NOT NULL DEFAULT 0,
                precio_usd REAL NOT NULL DEFAULT 0,
                tasa_bcv REAL NOT NULL DEFAULT 1,
                fecha_tasa TEXT,
                precio_bs REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Borrador',
                detalle_json TEXT,
                orden_trabajo_id INTEGER,
                FOREIGN KEY(cliente_id) REFERENCES clientes(id),
                FOREIGN KEY(receta_id) REFERENCES recetas_costeo(id)
            );

            CREATE TABLE IF NOT EXISTS produccion_consumos_integrales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                orden_trabajo_id INTEGER,
                cotizacion_integral_id INTEGER,
                inventario_id INTEGER,
                descripcion TEXT NOT NULL,
                consumo_teorico REAL NOT NULL DEFAULT 0,
                consumo_real REAL NOT NULL DEFAULT 0,
                merma_real REAL NOT NULL DEFAULT 0,
                sobrante_recuperable REAL NOT NULL DEFAULT 0,
                unidad_base TEXT NOT NULL DEFAULT 'unidad',
                costo_real_usd REAL NOT NULL DEFAULT 0,
                motivo_merma TEXT,
                usuario TEXT NOT NULL,
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            );

            CREATE INDEX IF NOT EXISTS idx_cc_items_compra ON compras_costeo_items(compra_id);
            CREATE INDEX IF NOT EXISTS idx_rec_comp_receta ON recetas_costeo_componentes(receta_id);
            CREATE INDEX IF NOT EXISTS idx_cot_integral_cliente ON cotizaciones_costeo_integral(cliente_id);
            CREATE INDEX IF NOT EXISTS idx_prod_consumo_ot ON produccion_consumos_integrales(orden_trabajo_id);
            """
        )


def allocate_amount(total: float, bases: list[float]) -> list[float]:
    total = float(total or 0)
    clean = [max(0.0, float(x or 0)) for x in bases]
    denom = sum(clean)
    if not clean:
        return []
    if total <= 0:
        return [0.0 for _ in clean]
    if denom <= 0:
        each = total / len(clean)
        out = [each for _ in clean]
    else:
        out = [total * value / denom for value in clean]
    # Fuerza conciliación exacta por redondeo.
    rounded = [round(x, 6) for x in out]
    rounded[-1] += round(total - sum(rounded), 6)
    return rounded


def calculate_conversion_factor(*, content: float, unit_base: str, width_cm: float = 0, height_cm: float = 0, length_cm: float = 0, weight_g: float = 0, volume_ml: float = 0) -> float:
    unit = str(unit_base or "unidad").lower()
    if unit == "ml":
        return max(float(volume_ml or content or 1), 0.000001)
    if unit == "g":
        return max(float(weight_g or content or 1), 0.000001)
    if unit == "cm":
        return max(float(length_cm or content or 1), 0.000001)
    if unit == "cm2":
        if width_cm > 0 and height_cm > 0:
            return max(float(width_cm * height_cm), 0.000001)
        if width_cm > 0 and length_cm > 0:
            return max(float(width_cm * length_cm), 0.000001)
    return max(float(content or 1), 0.000001)


def asset_cost_per_use(asset: dict[str, Any], usage: float = 1.0) -> float:
    depreciable = max(0.0, float(asset.get("costo_adquisicion_usd") or 0) - float(asset.get("valor_residual_usd") or 0))
    life = max(float(asset.get("vida_util_total") or 1), 0.000001)
    maintenance = max(0.0, float(asset.get("mantenimiento_acumulado_usd") or 0))
    return (depreciable + maintenance) / life * max(float(usage or 0), 0)


def price_from_margin(cost: float, margin_pct: float) -> float:
    cost = max(0.0, float(cost or 0))
    margin = min(max(float(margin_pct or 0), 0), 99.99) / 100
    return cost / (1 - margin) if cost else 0.0


def calculate_recipe_cost(receta_id: int, quantity: float = 1.0, labor_cost_per_minute: float = 0.0, indirect_pct: float = 0.0) -> dict[str, Any]:
    ensure_integrated_costing_schema()
    qty = max(float(quantity or 1), 0.000001)
    with db_transaction() as conn:
        recipe = conn.execute("SELECT * FROM recetas_costeo WHERE id=?", (int(receta_id),)).fetchone()
        if not recipe:
            raise ValueError("Receta no encontrada")
        components = conn.execute("SELECT * FROM recetas_costeo_componentes WHERE receta_id=? ORDER BY id", (int(receta_id),)).fetchall()
        details: list[dict[str, Any]] = []
        materials = waste = assets = labor = 0.0
        for row in components:
            item = dict(row)
            theoretical = max(0.0, float(item.get("cantidad_teorica") or 0)) * qty
            waste_qty = theoretical * max(0.0, float(item.get("merma_pct") or 0)) / 100
            unit_cost = max(0.0, float(item.get("costo_manual_usd") or 0))
            if item.get("inventario_id"):
                inv = conn.execute("SELECT COALESCE(costo,0) AS costo FROM inventario WHERE id=?", (int(item["inventario_id"]),)).fetchone()
                conv = conn.execute("SELECT factor_conversion FROM unidades_conversion WHERE inventario_id=? AND activo=1", (int(item["inventario_id"]),)).fetchone()
                purchase_unit_cost = float(inv["costo"] or 0) if inv else 0.0
                factor = float(conv["factor_conversion"] or 1) if conv else 1.0
                unit_cost = purchase_unit_cost / max(factor, 0.000001)
                materials += theoretical * unit_cost
                waste += waste_qty * unit_cost
            elif item.get("activo_id"):
                asset = conn.execute("SELECT * FROM activos_productivos_costeo WHERE id=?", (int(item["activo_id"]),)).fetchone()
                unit_cost = asset_cost_per_use(dict(asset), theoretical) if asset else 0.0
                assets += unit_cost
            elif str(item.get("tipo_componente")) == "mano_obra":
                minutes = max(0.0, float(item.get("minutos") or theoretical)) * qty
                unit_cost = minutes * max(0.0, float(labor_cost_per_minute or item.get("costo_manual_usd") or 0))
                labor += unit_cost
            else:
                materials += theoretical * unit_cost
                waste += waste_qty * unit_cost
            details.append({**item, "cantidad_total": theoretical, "merma_cantidad": waste_qty, "costo_calculado_usd": round(unit_cost if item.get("activo_id") else (theoretical + waste_qty) * unit_cost, 6)})
        direct = materials + waste + assets + labor
        indirect = direct * max(0.0, float(indirect_pct or 0)) / 100
        total = direct + indirect
        margin = float(dict(recipe).get("margen_objetivo_pct") or 0)
        price = price_from_margin(total, margin)
        return {
            "receta": dict(recipe),
            "cantidad": qty,
            "materiales_usd": round(materials, 6),
            "merma_usd": round(waste, 6),
            "activos_usd": round(assets, 6),
            "mano_obra_usd": round(labor, 6),
            "indirectos_usd": round(indirect, 6),
            "costo_total_usd": round(total, 6),
            "margen_pct": margin,
            "precio_sugerido_usd": round(price, 2),
            "detalle": details,
        }


def save_integrated_quote(data: dict[str, Any]) -> int:
    ensure_integrated_costing_schema()
    detail = data.get("detalle") or {}
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cotizaciones_costeo_integral(
                usuario, cliente_id, cliente, telefono, receta_id, descripcion, cantidad,
                archivo_nombre, archivo_ruta, confidencial, costo_materiales_usd, costo_merma_usd,
                costo_activos_usd, costo_mano_obra_usd, costo_indirecto_usd, costo_total_usd,
                margen_pct, precio_usd, tasa_bcv, fecha_tasa, precio_bs, estado, detalle_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data.get("usuario", "Sistema"), data.get("cliente_id"), data.get("cliente", "Cliente General"),
                data.get("telefono", ""), data.get("receta_id"), data.get("descripcion", "Trabajo"),
                float(data.get("cantidad") or 1), data.get("archivo_nombre", ""), data.get("archivo_ruta", ""),
                1 if data.get("confidencial") else 0, float(data.get("materiales_usd") or 0),
                float(data.get("merma_usd") or 0), float(data.get("activos_usd") or 0),
                float(data.get("mano_obra_usd") or 0), float(data.get("indirectos_usd") or 0),
                float(data.get("costo_total_usd") or 0), float(data.get("margen_pct") or 0),
                float(data.get("precio_usd") or 0), float(data.get("tasa_bcv") or 1),
                data.get("fecha_tasa") or datetime.now().isoformat(timespec="seconds"),
                float(data.get("precio_bs") or 0), data.get("estado", "Borrador"),
                json.dumps(detail, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)
