from __future__ import annotations

from database.connection import db_transaction


RATE_DEFAULTS: dict[str, float] = {
    "tasa_euro": 0.0,
    "tasa_menudeo": 0.0,
    "tasa_kontigo": 0.0,
    "tasa_kontigo_entrada": 0.0,
    "tasa_kontigo_salida": 0.0,
    "kontigo_pago_movil_envio_perc": 0.0,
    "kontigo_tarjeta_envio_perc": 0.0,
    "kontigo_tarjeta_envio_fija_usd": 0.0,
    "menudeo_comision_perc": 0.0,
    "menudeo_comision_fija_usd": 0.0,
    "menudeo_minimo_usd": 10.0,
}


def ensure_rate_config_defaults() -> None:
    """Ensure newer monetary-rate settings exist and survive app reruns/reboots."""
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracion (
                parametro TEXT PRIMARY KEY,
                valor TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parametro TEXT NOT NULL,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                usuario TEXT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        legacy_row = conn.execute(
            "SELECT valor FROM configuracion WHERE parametro = 'tasa_kontigo'"
        ).fetchone()
        legacy_kontigo = legacy_row["valor"] if legacy_row and legacy_row["valor"] not in (None, "") else "0.0"

        for param, default_value in RATE_DEFAULTS.items():
            value = legacy_kontigo if param in {"tasa_kontigo_entrada", "tasa_kontigo_salida"} else str(default_value)
            conn.execute(
                """
                INSERT OR IGNORE INTO configuracion (parametro, valor)
                VALUES (?, ?)
                """,
                (param, value),
            )
