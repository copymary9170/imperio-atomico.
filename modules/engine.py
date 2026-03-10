from __future__ import annotations

import numpy as np
from PIL import Image
import io
from decimal import Decimal, ROUND_HALF_UP


# --------------------------------------------------
# UTILIDADES NUMÉRICAS
# --------------------------------------------------

def D(v, default='0'):
    try:
        return Decimal(str(v if v is not None else default))
    except Exception:
        return Decimal(default)


def money(v):
    return float(D(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_float(valor, default=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float(default)


# --------------------------------------------------
# COSTOS INDUSTRIALES
# --------------------------------------------------

def calcular_costo_total_real(tinta=0.0, papel=0.0, desgaste=0.0, otros_procesos=0.0):
    return float(tinta or 0.0) + float(papel or 0.0) + float(desgaste or 0.0) + float(otros_procesos or 0.0)


def calcular_costo_industrial_total(tinta=0.0, papel=0.0, desgaste=0.0, electricidad=0.0, operador=0.0):
    return float(tinta or 0.0) + float(papel or 0.0) + float(desgaste or 0.0) + float(electricidad or 0.0) + float(operador or 0.0)


# --------------------------------------------------
# GANANCIA
# --------------------------------------------------

def simular_ganancia_pre_impresion(costo_real, margen_pct=30.0):

    costo_real = float(costo_real or 0.0)
    margen_pct = float(margen_pct or 0.0)

    precio_sugerido = costo_real * (1 + (margen_pct / 100.0))

    ganancia = precio_sugerido - costo_real

    return {
        'costo_real': costo_real,
        'margen_pct': margen_pct,
        'precio_sugerido': precio_sugerido,
        'ganancia_estimada': ganancia
    }


# --------------------------------------------------
# ANALISIS CMYK POR PIXEL
# --------------------------------------------------

def calcular_consumo_por_pixel(imagen):

    arr = np.array(imagen.convert('CMYK'))

    pixeles_totales = int(arr.shape[0] * arr.shape[1])

    if pixeles_totales <= 0:
        return {
            'pixeles_totales': 0,
            'consumo_real_ml': 0.0,
            'precision': 0.0
        }

    cobertura = arr.astype(np.float32) / 255.0

    peso = float(cobertura.mean())

    consumo_real_ml = float(pixeles_totales * peso * 0.000001)

    return {
        'pixeles_totales': pixeles_totales,
        'consumo_real_ml': consumo_real_ml,
        'precision': max(0.0, min(1.0, 1.0 - abs(0.5 - peso)))
    }


# --------------------------------------------------
# CORTE CAMEO
# --------------------------------------------------

def calcular_corte_cameo(
    archivo_bytes,
    factor_dureza_material=1.0,
    desgaste_activo=0.0,
    nombre_archivo='',
    factor_complejidad=1.35,
    mano_obra_base=0.0
):

    nombre_archivo = str(nombre_archivo or '').lower()

    try:

        imagen = Image.open(io.BytesIO(archivo_bytes)).convert('L')

        arr = np.array(imagen)

    except Exception:

        tam = max(1, len(archivo_bytes or b''))

        lado = int(max(32, min(2048, (tam ** 0.5))))

        arr = np.zeros((lado, lado), dtype=np.uint8)

        if nombre_archivo.endswith('.svg'):
            arr[:, ::2] = 255

        elif nombre_archivo.endswith('.dxf'):
            arr[::2, :] = 255

        else:
            arr[:, :] = 200

    binario = (arr < 245).astype(np.uint8)

    pixeles_material = int(binario.sum())

    alto, ancho = binario.shape

    cm_por_pixel = 2.54 / 300.0

    area_cm2 = float(pixeles_material * (cm_por_pixel ** 2))

    bordes_h = np.abs(np.diff(binario, axis=1)).sum()

    bordes_v = np.abs(np.diff(binario, axis=0)).sum()

    longitud_cm = float((bordes_h + bordes_v) * cm_por_pixel)

    movimientos = int(max(1, (bordes_h + bordes_v) / 8))

    desgaste_real = float(longitud_cm) * float(factor_dureza_material or 1.0) * float(desgaste_activo or 0.0)

    factor_complejidad = min(2.5, max(1.0, float(factor_complejidad or 1.35)))

    costo_mano_obra = money(float(mano_obra_base or 0.0) * factor_complejidad)

    return {

        'ancho_px': int(ancho),
        'alto_px': int(alto),

        'area_cm2': area_cm2,

        'longitud_corte_cm': longitud_cm,

        'movimientos': movimientos,

        'desgaste_real': money(desgaste_real),

        'factor_complejidad': factor_complejidad,

        'costo_mano_obra': costo_mano_obra,

        'costo_total': money(desgaste_real + costo_mano_obra)

    }
