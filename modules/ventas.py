import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text
from modules.integration_hub import dispatch_to_module, render_send_buttons
from services.contabilidad_service import contabilizar_venta
from services.conciliacion_service import periodo_esta_cerrado
from services.costeo_service import actualizar_vinculos_costeo
from services.cxc_cobranza_service import CobranzaInput, registrar_abono_cuenta_por_cobrar
from services.cuentas_por_cobrar_service import ensure_cuentas_por_cobrar_tables
from services.tesoreria_service import registrar_ingreso
from utils.currency import convert_to_bs


METODOS_PAGO_VENTA = [
    "efectivo",
    "transferencia",
    "pago_movil",
    "zelle",
    "binance",
    "tarjeta",
    "mixto",
    "kontigo",
    "credito",
]

MONEDAS_VENTA = ["USD", "BS", "USDT", "KONTIGO"]
