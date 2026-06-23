from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.configuracion import get_current_config, DEFAULT_CONFIG, set_config_values
from services.backup_service import get_backup_status, create_backup
from services.persistent_config_service import save_persistent_rates

APP_ROOT = Path(__file__).resolve().parents[1]

RATE_FIELDS = [
    ("tasa_bcv", "BCV", "Bs/$", "diaria", 2),
    ("tasa_binance", "Binance", "Bs/$", "variable", 2),
    ("tasa_euro", "Euro", "Bs/€", "variable", 2),
    ("tasa_menudeo", "Menudeo", "Bs/$", "variable", 2),
    ("tasa_kontigo_entrada", "Kontigo entrada", "Bs/$", "variable", 2),
    ("tasa_kontigo_salida", "Kontigo salida", "Bs/$", "variable", 2),
    ("banco_perc", "Banco", "%", "variable", 3),
    ("kontigo_perc", "Kontigo general", "%", "variable", 3),
    ("kontigo_perc_entrada", "Kontigo comisión entrada", "%", "variable", 3),
    ("kontigo_perc_salida", "Kontigo comisión salida", "%", "variable", 3),
    ("kontigo_pago_movil_envio_perc", "Pago móvil → Kontigo", "%", "variable", 3),
    ("kontigo_tarjeta_envio_perc", "Kontigo → tarjeta", "%", "variable", 3),
    ("kontigo_tarjeta_envio_fija_usd", "Kontigo → tarjeta fija", "$", "variable", 2),
    ("menudeo_comision_perc", "Menudeo comisión", "%", "variable", 3),
    ("menudeo_comision_fija_usd", "Menudeo comisión fija", "$", "variable", 2),
    ("menudeo_minimo_usd", "Menudeo mínimo", "$", "variable", 2),
]

RATE_HISTORY_KEYS = "'tasa_bcv','tasa_binance','tasa_euro','tasa_menudeo','tasa_kontigo','tasa_kontigo_entrada','tasa_kontigo_salida','banco_perc','kontigo_perc','kontigo_perc_entrada','kontigo_perc_salida','kontigo_pago_movil_envio_perc','kontigo_tarjeta_envio_perc','kontigo_tarjeta_envio_fija_usd','menudeo_comision_perc','menudeo_comision_fija_usd','menudeo_minimo_usd'"

DEFAULT_RATE_VALUES = {
    "tasa_bcv": 36.50,
    "tasa_binance": 38.00,
    "tasa_euro": 0.0,
    "tasa_menudeo": 0.0,
    "tasa_kontigo": 0.0,
    "tasa_kontigo_entrada": 0.0,
    "tasa_kontigo_salida": 0.0,
    "menudeo_minimo_usd": 10.0,
}


# ---- helpers (rest of file unchanged) ----

# IVA e IGTF eliminados completamente del sistema
# ahora el ERP solo maneja tasas operativas reales
