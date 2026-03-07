from __future__ import annotations

from database.connection import db_transaction


class CotizacionService:
    def crear_cotizacion(
        self,
        usuario: str,
        cliente_id: int | None,
        descripcion: str,
        costo_estimado_usd: float,
        margen_pct: float,
    ) -> int:
        precio = round(float(costo_estimado_usd) * (1 + (float(margen_pct) / 100.0)), 2)
        with db_transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO cotizaciones (usuario, cliente_id, descripcion, costo_estimado_usd, margen_pct, precio_final_usd, estado)
                VALUES (?, ?, ?, ?, ?, ?, 'Cotización')
                """,
                (usuario, cliente_id, descripcion, float(costo_estimado_usd), float(margen_pct), precio),
            )
            return int(cur.lastrowid)
          
