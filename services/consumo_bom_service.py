from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from database.connection import db_transaction
from services.audit_service import log_audit_event


@dataclass(frozen=True)
class ConsumptionResult:
    ok: bool
    consumed_rows: int = 0
    total_cost_usd: float = 0.0
    message: str = ""


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_consumption_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ordenes_trabajo_consumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            orden_id INTEGER NOT NULL,
            bom_id INTEGER NOT NULL,
            componente_id INTEGER,
            inventario_id INTEGER,
            item TEXT NOT NULL,
            unidad TEXT,
            cantidad_base REAL NOT NULL DEFAULT 0,
            cantidad_orden REAL NOT NULL DEFAULT 1,
            cantidad_consumida REAL NOT NULL DEFAULT 0,
            costo_unitario_usd REAL NOT NULL DEFAULT 0,
            costo_total_usd REAL NOT NULL DEFAULT 0,
            usuario TEXT NOT NULL DEFAULT 'Sistema',
            estado TEXT NOT NULL DEFAULT 'registrado',
            observaciones TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ot_consumos_orden ON ordenes_trabajo_consumos(orden_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ot_consumos_bom ON ordenes_trabajo_consumos(bom_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ot_consumos_unicos ON ordenes_trabajo_consumos(orden_id, componente_id)")


def _stock_column(conn) -> str | None:
    cols = _columns(conn, "inventario")
    for candidate in ["stock", "cantidad", "existencia", "stock_actual"]:
        if candidate in cols:
            return candidate
    return None


def _maybe_discount_inventory(conn, inventario_id: Any, cantidad: float) -> str:
    if not inventario_id or not _table_exists(conn, "inventario"):
        return "sin inventario asociado"
    cols = _columns(conn, "inventario")
    if "id" not in cols:
        return "inventario sin columna id"
    stock_col = _stock_column(conn)
    if not stock_col:
        return "inventario sin columna de stock detectable"
    row = conn.execute(f"SELECT {stock_col} FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
    if not row:
        return "inventario_id no encontrado"
    actual = float(row[0] or 0)
    nuevo = max(actual - float(cantidad or 0), 0.0)
    conn.execute(f"UPDATE inventario SET {stock_col}=? WHERE id=?", (nuevo, int(inventario_id)))
    return f"stock descontado {actual:,.4f}->{nuevo:,.4f}"


def consume_bom_for_order(orden_id: int, usuario: str = "Sistema") -> ConsumptionResult:
    """Consume materiales de la BOM asociada a una OT. Es idempotente por componente."""
    try:
        with db_transaction() as conn:
            _ensure_consumption_table(conn)
            if not _table_exists(conn, "ordenes_trabajo"):
                return ConsumptionResult(False, message="No existe la tabla ordenes_trabajo.")
            if not _table_exists(conn, "fichas_tecnicas_bom_componentes"):
                return ConsumptionResult(False, message="No existe la tabla de componentes BOM.")

            ot = conn.execute(
                "SELECT id, codigo, bom_id, cantidad, costo_real_usd FROM ordenes_trabajo WHERE id=?",
                (int(orden_id),),
            ).fetchone()
            if not ot:
                return ConsumptionResult(False, message="Orden de trabajo no encontrada.")
            bom_id = int(ot[2] or 0)
            cantidad_orden = float(ot[3] or 1)
            if not bom_id:
                return ConsumptionResult(False, message="La orden no tiene BOM asociada.")

            cols = _columns(conn, "fichas_tecnicas_bom_componentes")
            required = {"id", "ficha_id", "item", "cantidad"}
            if not required.issubset(cols):
                return ConsumptionResult(False, message="La tabla BOM no tiene columnas mínimas para consumir.")

            components = conn.execute(
                """
                SELECT id, inventario_id, item, unidad, cantidad, costo_unitario_usd, merma_pct, costo_total_usd
                FROM fichas_tecnicas_bom_componentes
                WHERE ficha_id=?
                ORDER BY orden, id
                """,
                (bom_id,),
            ).fetchall()
            if not components:
                return ConsumptionResult(False, message="La BOM asociada no tiene componentes.")

            consumed = 0
            total_cost = 0.0
            notes: list[str] = []
            for comp in components:
                comp_id = int(comp[0])
                existing = conn.execute(
                    "SELECT id FROM ordenes_trabajo_consumos WHERE orden_id=? AND componente_id=?",
                    (int(orden_id), comp_id),
                ).fetchone()
                if existing:
                    continue

                inventario_id = comp[1]
                item = str(comp[2] or "")
                unidad = str(comp[3] or "unidad")
                cantidad_base = float(comp[4] or 0)
                costo_unitario = float(comp[5] or 0)
                merma_pct = float(comp[6] or 0)
                costo_total_base = float(comp[7] or 0)
                cantidad_consumida = cantidad_base * cantidad_orden * (1 + merma_pct / 100)
                costo_linea = costo_total_base * cantidad_orden if costo_total_base else cantidad_consumida * costo_unitario
                inventory_note = _maybe_discount_inventory(conn, inventario_id, cantidad_consumida)

                conn.execute(
                    """
                    INSERT INTO ordenes_trabajo_consumos(
                        orden_id, bom_id, componente_id, inventario_id, item, unidad,
                        cantidad_base, cantidad_orden, cantidad_consumida,
                        costo_unitario_usd, costo_total_usd, usuario, estado, observaciones
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(orden_id), bom_id, comp_id, inventario_id, item, unidad,
                        cantidad_base, cantidad_orden, cantidad_consumida,
                        costo_unitario, costo_linea, usuario, "consumido", inventory_note,
                    ),
                )
                consumed += 1
                total_cost += costo_linea
                notes.append(f"{item}: {cantidad_consumida:,.4f} {unidad} ({inventory_note})")

            if consumed:
                current_real_cost = float(ot[4] or 0)
                new_real_cost = current_real_cost + total_cost
                conn.execute(
                    """
                    UPDATE ordenes_trabajo
                    SET costo_real_usd=?, margen_real_usd=COALESCE(precio_venta_usd,0)-?
                    WHERE id=?
                    """,
                    (new_real_cost, new_real_cost, int(orden_id)),
                )
                conn.execute(
                    """
                    INSERT INTO ordenes_trabajo_eventos(orden_id, usuario, estado, comentario, costo_real_usd)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        int(orden_id), usuario, "Consumo BOM",
                        f"Consumo automático BOM: {consumed} componente(s), costo ${total_cost:,.2f}", total_cost,
                    ),
                )

            message = "Consumo registrado." if consumed else "La OT ya tenía consumos BOM registrados."

        log_audit_event(
            usuario=usuario,
            modulo="Producción",
            accion="consumir_bom_ot",
            entidad="ordenes_trabajo",
            entidad_id=orden_id,
            detalle=message,
            metadata={"componentes_consumidos": consumed, "costo_total_usd": total_cost, "notas": notes},
        )
        return ConsumptionResult(True, consumed_rows=consumed, total_cost_usd=total_cost, message=message)
    except Exception as exc:
        return ConsumptionResult(False, message=str(exc))
