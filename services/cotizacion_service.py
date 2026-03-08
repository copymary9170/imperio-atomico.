from __future__ import annotations

from database.connection import db_transaction
from modules.common import as_positive, require_text, clean_text


class CotizacionService:

    def crear_cotizacion(
        self,
        usuario: str,
        cliente_id: int | None,
        descripcion: str,
        costo_estimado_usd: float,
        margen_pct: float,
    ) -> int:

        descripcion = require_text(descripcion, "Descripción")
        descripcion = clean_text(descripcion)

        costo_estimado_usd = as_positive(costo_estimado_usd, "Costo estimado", allow_zero=False)
        margen_pct = as_positive(margen_pct, "Margen")

        precio_final = round(costo_estimado_usd * (1 + (margen_pct / 100)), 2)

        with db_transaction() as conn:

            cur = conn.execute(
                """
                INSERT INTO cotizaciones
                (usuario, cliente_id, descripcion, costo_estimado_usd, margen_pct, precio_final_usd, estado)
                VALUES (?, ?, ?, ?, ?, ?, 'cotizacion')
                """,
                (
                    usuario,
                    cliente_id,
                    descripcion,
                    float(costo_estimado_usd),
                    float(margen_pct),
                    float(precio_final),
                ),
            )

            return int(cur.lastrowid)
