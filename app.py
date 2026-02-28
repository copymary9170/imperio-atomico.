import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import io
import plotly.express as px
from PIL import Image
from datetime import datetime, date, timedelta
from config import DATABASE, VERSION, EMPRESA
import time
import os
import hashlib
import hmac
import secrets
import re
from decimal import Decimal, ROUND_HALF_UP

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide", page_icon="⚛️")

# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():

    import sqlite3

    db_path = DATABASE if str(DATABASE or '').strip() else "database.db"

    conn = sqlite3.connect(
        db_path,
        timeout=30,
        isolation_level=None,
        detect_types=sqlite3.PARSE_DECLTYPES
    )

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -10000;")
    conn.execute("PRAGMA busy_timeout = 30000;")

    return conn

def calcular_precio_real_ml(item_id):
    with conectar() as conn:
        row = conn.execute(
            "SELECT precio_usd, capacidad_ml FROM inventario WHERE id = ?",
            (item_id,)
        ).fetchone()
    if not row:
        return 0.0
    precio_usd, capacidad_ml = row
    precio_usd = float(precio_usd or 0.0)
    capacidad_ml = float(capacidad_ml) if capacidad_ml is not None else None
    if capacidad_ml and capacidad_ml > 0:
        return precio_usd / capacidad_ml
    return precio_usd


def calcular_costo_real_ml(precio, capacidad_ml=None, rendimiento_paginas=None):
    precio = float(precio or 0.0)
    capacidad_ml = float(capacidad_ml) if capacidad_ml not in (None, "") else None
    rendimiento_paginas = int(rendimiento_paginas) if rendimiento_paginas not in (None, "") else None

    if capacidad_ml and capacidad_ml > 0:
        return precio / capacidad_ml

    if rendimiento_paginas and rendimiento_paginas > 0:
        ml_estimado_total = float(rendimiento_paginas) * 0.05
        if ml_estimado_total > 0:
            return precio / ml_estimado_total

    return precio


def actualizar_costo_real_ml_inventario(conn=None):
    def _run(cn):
        filas = cn.execute(
            "SELECT id, precio_usd, capacidad_ml, rendimiento_paginas FROM inventario WHERE COALESCE(activo,1)=1"
        ).fetchall()
        for item_id, precio_usd, capacidad_ml, rendimiento_paginas in filas:
            costo_real_ml = calcular_costo_real_ml(precio_usd, capacidad_ml, rendimiento_paginas)
            cn.execute(
                "UPDATE inventario SET costo_real_ml=?, ultima_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
                (float(costo_real_ml), int(item_id))
            )

    if conn is None:
        with conectar() as conn_local:
            _run(conn_local)
            conn_local.commit()
        return

    _run(conn)

def analizar_consumo_promedio(dias=30):
    with conectar() as conn:
        df = pd.read_sql_query(
            """
            SELECT date(fecha) AS dia, item_id, SUM(cantidad) AS consumo
            FROM inventario_movs
            WHERE tipo='SALIDA' AND fecha >= datetime('now', ?)
            GROUP BY date(fecha), item_id
            """,
            conn,
            params=(f'-{int(max(1, dias))} days',)
        )
        if df.empty:
            return pd.DataFrame(columns=['item_id', 'consumo_promedio_diario', 'stock_actual', 'dias_restantes_stock'])

        promedio = df.groupby('item_id', as_index=False)['consumo'].mean().rename(columns={'consumo': 'consumo_promedio_diario'})
        stock = pd.read_sql_query("SELECT id AS item_id, cantidad AS stock_actual FROM inventario", conn)
        out = promedio.merge(stock, on='item_id', how='left')
        out['stock_actual'] = out['stock_actual'].fillna(0.0)
        out['dias_restantes_stock'] = np.where(
            out['consumo_promedio_diario'] > 0,
            out['stock_actual'] / out['consumo_promedio_diario'],
            np.nan
        )
        return out


def calcular_costo_total_real(tinta=0.0, papel=0.0, desgaste=0.0, otros_procesos=0.0):
    return float(tinta or 0.0) + float(papel or 0.0) + float(desgaste or 0.0) + float(otros_procesos or 0.0)

def _safe_float(valor, default=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float(default)


def D(v, default='0'):
    try:
        return Decimal(str(v if v is not None else default))
    except Exception:
        return Decimal(default)


def money(v):
    return float(D(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


KANBAN_ESTADOS = ['Cotización', 'Pendiente', 'Diseño', 'Producción', 'Control de Calidad', 'Listo', 'Entregado']


def normalizar_estado_kanban(estado):
    estado_txt = str(estado or '').strip()
    map_antiguo = {
        'cotización': 'Cotización', 'cotizacion': 'Cotización',
        'pendiente': 'Pendiente',
        'aprobado por cliente': 'Pendiente',
        'diseño': 'Diseño',
        'impresión/corte': 'Producción', 'en producción': 'Producción', 'producción': 'Producción',
        'acabado': 'Control de Calidad', 'acabado/control de calidad': 'Control de Calidad', 'control de calidad': 'Control de Calidad',
        'listo para entrega': 'Listo', 'listo': 'Listo',
        'finalizado': 'Entregado', 'cerrado': 'Entregado', 'entregado': 'Entregado'
    }
    if estado_txt.lower() in map_antiguo:
        return map_antiguo[estado_txt.lower()]
    return estado_txt if estado_txt in KANBAN_ESTADOS else 'Cotización'


def registrar_log_actividad(conn, accion, tabla_afectada, usuario=None):
    usuario_final = str(usuario or st.session_state.get('usuario_nombre', 'Sistema'))
    conn.execute(
        """
        INSERT INTO logs_actividad (usuario, accion, tabla_afectada)
        VALUES (?, ?, ?)
        """,
        (usuario_final, str(accion), str(tabla_afectada))
    )



def registrar_auditoria(conn, accion, valor_anterior, valor_nuevo, usuario=None):
    usuario_final = str(usuario or st.session_state.get('usuario_nombre', 'Sistema'))
    conn.execute(
        """
        INSERT INTO auditoria (usuario, accion, valor_anterior, valor_nuevo)
        VALUES (?, ?, ?, ?)
        """,
        (usuario_final, str(accion), str(valor_anterior), str(valor_nuevo))
    )


def calcular_precio_final(costo_base, metodo_pago, tiene_iva, recargo_urgencia=0.0):
    base = D(costo_base).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    metodo = str(metodo_pago or '').lower()
    porcentaje_total = Decimal('0')

    if bool(tiene_iva):
        porcentaje_total += D(st.session_state.get('iva_perc', 16.0))

    if 'kontigo' in metodo:
        porcentaje_total += D(st.session_state.get('kontigo_perc_entrada', st.session_state.get('kontigo_perc', 5.0)))
    elif any(m in metodo for m in ['pago móvil', 'pago movil', 'transferencia', 'zelle']):
        porcentaje_total += D(st.session_state.get('banco_perc', 0.5))

    if any(m in metodo for m in ['efectivo $', 'usd efectivo', 'cash usd']):
        porcentaje_total += D(st.session_state.get('igtf_perc', 0.0))

    urgencia = D(recargo_urgencia)
    if urgencia < 0:
        urgencia = Decimal('0')

    total = base * (Decimal('1') + (porcentaje_total / Decimal('100')))
    total = total * (Decimal('1') + (urgencia / Decimal('100')))
    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        'base': float(base),
        'porcentaje_total': float(porcentaje_total.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)),
        'recargo_urgencia': float(urgencia),
        'total': float(total)
    }

def _calcular_vida_util_desde_activo(inversion, desgaste, default=1000):
    inversion_f = _safe_float(inversion)
    desgaste_f = _safe_float(desgaste)
    if inversion_f > 0 and desgaste_f > 0:
        return max(1, int(round(inversion_f / desgaste_f)))
    return int(default)


def calcular_consumo_por_pixel(imagen):
    arr = np.array(imagen.convert('CMYK'))
    pixeles_totales = int(arr.shape[0] * arr.shape[1])
    if pixeles_totales <= 0:
        return {'pixeles_totales': 0, 'consumo_real_ml': 0.0, 'precision': 0.0}
    cobertura = arr.astype(np.float32) / 255.0
    peso = float(cobertura.mean())
    consumo_real_ml = float(pixeles_totales * peso * 0.000001)
    return {
        'pixeles_totales': pixeles_totales,
        'consumo_real_ml': consumo_real_ml,
        'precision': max(0.0, min(1.0, 1.0 - abs(0.5 - peso)))
    }


def ajustar_factores_automaticamente():
    with conectar() as conn:
        row = conn.execute(
            "SELECT AVG(consumo_real-consumo_estimado) FROM aprendizaje_consumo WHERE consumo_real IS NOT NULL AND consumo_estimado IS NOT NULL"
        ).fetchone()
    error_prom = float(row[0] or 0.0) if row else 0.0
    ajuste = 1.0
    if error_prom > 0:
        ajuste = 1.05
    elif error_prom < 0:
        ajuste = 0.95
    return {'factor': ajuste, 'factor_k': ajuste}


def predecir_falla(umbral_desgaste=0.85):
    with conectar() as conn:
        df = pd.read_sql_query(
            "SELECT impresora, vida_total, vida_restante FROM vida_cabezal",
            conn
        )
    if df.empty:
        return pd.DataFrame(columns=['impresora', 'riesgo'])
    df['riesgo'] = np.where(
        (df['vida_total'].fillna(0) > 0) & ((df['vida_restante'].fillna(0) / df['vida_total'].fillna(1)) < (1.0 - float(umbral_desgaste))),
        'ALTO',
        'NORMAL'
    )
    return df[['impresora', 'riesgo']]


def calcular_costo_industrial_total(tinta=0.0, papel=0.0, desgaste=0.0, electricidad=0.0, operador=0.0):
    return float(tinta or 0.0) + float(papel or 0.0) + float(desgaste or 0.0) + float(electricidad or 0.0) + float(operador or 0.0)


def optimizar_costos(df_simulaciones):
    if df_simulaciones is None or len(df_simulaciones) == 0:
        return None
    if isinstance(df_simulaciones, pd.DataFrame) and 'Total ($)' in df_simulaciones.columns:
        return df_simulaciones.sort_values('Total ($)', ascending=True).head(1)
    return None


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


def actualizar_vida_cabezal(impresora, paginas):
    impresora = str(impresora or '').strip()
    if not impresora:
        return
    paginas = int(max(0, paginas or 0))
    if paginas <= 0:
        return

    with conectar() as conn:
        row = conn.execute(
            "SELECT id, vida_total, vida_restante FROM vida_cabezal WHERE lower(trim(impresora)) = lower(trim(?)) ORDER BY id DESC LIMIT 1",
            (impresora,)
        ).fetchone()

        if row:
            vid, vida_total, vida_restante = row
            vida_total = float(vida_total or 100000.0)
            vida_restante = float(vida_restante or vida_total)
            nueva_vida = max(0.0, vida_restante - float(paginas))
            conn.execute(
                "UPDATE vida_cabezal SET vida_restante=?, fecha=CURRENT_TIMESTAMP WHERE id=?",
                (nueva_vida, int(vid))
            )
        else:
            vida_total = 100000.0
            nueva_vida = max(0.0, vida_total - float(paginas))
            conn.execute(
                "INSERT INTO vida_cabezal (impresora, vida_total, vida_restante) VALUES (?,?,?)",
                (impresora, vida_total, nueva_vida)
            )
        conn.commit()


def actualizar_estadisticas_avanzadas():
    with conectar() as conn:
        df = pd.read_sql_query(
            "SELECT fecha, cliente, impresora, costo_real, precio_cobrado, ganancia FROM trabajos_historial",
            conn
        )
        if df.empty:
            return None

        df['ganancia'] = df['ganancia'].fillna(df['precio_cobrado'].fillna(0) - df['costo_real'].fillna(0))
        top_trabajo = df.sort_values('ganancia', ascending=False).head(1)
        top_cliente = df.groupby('cliente', as_index=False)['ganancia'].sum().sort_values('ganancia', ascending=False).head(1)
        top_imp = df.groupby('impresora', as_index=False)['ganancia'].sum().sort_values('ganancia', ascending=False).head(1)

        trabajo_val = str(top_trabajo.iloc[0]['fecha']) if not top_trabajo.empty else ''
        cliente_val = str(top_cliente.iloc[0]['cliente']) if not top_cliente.empty else ''
        impresora_val = str(top_imp.iloc[0]['impresora']) if not top_imp.empty else ''

        conn.execute(
            "INSERT INTO estadisticas_avanzadas (trabajo_mas_rentable, cliente_mas_rentable, impresora_mas_rentable) VALUES (?,?,?)",
            (trabajo_val, cliente_val, impresora_val)
        )
        conn.commit()
        return {
            'trabajo_mas_rentable': trabajo_val,
            'cliente_mas_rentable': cliente_val,
            'impresora_mas_rentable': impresora_val
        }


def actualizar_desgaste_activo(activo_id, uso):
    uso = float(uso or 0.0)
    if uso <= 0:
        return False

    try:
        with conectar() as conn:
            conn.execute("BEGIN IMMEDIATE TRANSACTION")
            row = conn.execute(
                "SELECT vida_total, vida_restante, COALESCE(uso_actual, 0), COALESCE(activo,1) FROM activos WHERE id=?",
                (int(activo_id),)
            ).fetchone()
            if not row:
                conn.rollback()
                return False

            vida_total, vida_restante, uso_actual, activo = row
            if int(activo or 1) != 1:
                conn.rollback()
                return False

            vida_total = float(vida_total or 0.0)
            vida_restante = float(vida_restante if vida_restante is not None else vida_total)
            uso_actual = float(uso_actual or 0.0)

            nueva_vida = max(0.0, vida_restante - uso)
            nuevo_uso = max(0.0, uso_actual + uso)

            conn.execute(
                "UPDATE activos SET vida_restante=?, uso_actual=? WHERE id=?",
                (nueva_vida, nuevo_uso, int(activo_id))
            )
            conn.commit()
        return True
    except Exception:
        return False

def calcular_costo_activo(activo_id, uso):
    uso = float(uso or 0.0)
    if uso <= 0:
        return 0.0

    with conectar() as conn:
        row = conn.execute(
            "SELECT inversion, vida_total, COALESCE(activo,1) FROM activos WHERE id=?",
            (int(activo_id),)
        ).fetchone()
    if not row:
        return 0.0

    inversion, vida_total, activo = row
    if int(activo or 1) != 1:
        return 0.0

    inversion_d = D(inversion)
    vida_total_d = D(vida_total)
    uso_d = D(uso)
    if vida_total_d <= 0:
        return 0.0

    costo = (inversion_d / vida_total_d) * uso_d
    return money(costo)

def procesar_orden_produccion(orden_id):
    with conectar() as conn:
        row = conn.execute(
            "SELECT id, tipo, producto, estado, COALESCE(costo,0) FROM ordenes_produccion WHERE id=?",
            (int(orden_id),)
        ).fetchone()
        if not row:
            return False, 'Orden no encontrada'

        oid, tipo, producto, estado, costo_base = row
        if str(estado).lower() in ('finalizado', 'cerrado', 'entregado'):
            return True, 'Orden ya procesada'

        conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_id ON inventario(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_item ON inventario(item)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movs_item ON inventario_movs(item_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha)")

        # Si existe receta para el producto, descontar inventario automáticamente
        recetas = conn.execute(
            "SELECT inventario_id, cantidad, activo_id, tiempo FROM recetas_produccion WHERE producto=?",
            (str(producto),)
        ).fetchall()

        costo_total = float(costo_base or 0.0)

        consumos = {}
        for inv_id, cantidad, activo_id, tiempo in recetas:
            if inv_id is not None and float(cantidad or 0) > 0:
                consumos[int(inv_id)] = consumos.get(int(inv_id), 0.0) + float(cantidad)
            if activo_id is not None and float(tiempo or 0) > 0:
                uso = float(tiempo)
                costo_total += float(calcular_costo_activo(int(activo_id), uso))
                actualizar_desgaste_activo(int(activo_id), uso)

        if consumos:
            ok, msg = descontar_materiales_produccion(
                consumos,
                usuario=st.session_state.get('usuario_nombre', 'Sistema'),
                detalle=f"Consumo orden #{int(oid)} - {producto}"
            )
            if not ok:
                return False, msg

        conn.execute(
            "UPDATE ordenes_produccion SET estado='Entregado', costo=? WHERE id=?",
            (float(costo_total), int(oid))
        )
        conn.commit()

    return True, f'Orden #{int(oid)} procesada'


def calcular_corte_cameo(archivo_bytes, factor_dureza_material=1.0, desgaste_activo=0.0, nombre_archivo='', factor_complejidad=1.35, mano_obra_base=0.0):
    nombre_archivo = str(nombre_archivo or '').lower()
    try:
        imagen = Image.open(io.BytesIO(archivo_bytes)).convert('L')
        arr = np.array(imagen)
    except Exception:
        # Fallback compatible para SVG/DXF u otros formatos no raster
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
    # Conversión base para compatibilidad (300 dpi aproximado)
    cm_por_pixel = 2.54 / 300.0
    area_cm2 = float(pixeles_material * (cm_por_pixel ** 2))

    # Perímetro aproximado por cambios de borde
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
        'complejidad_diseno': f'Factor {factor_complejidad:.2f}',
        'factor_complejidad': factor_complejidad,
        'costo_mano_obra': costo_mano_obra,
        'costo_total': money(desgaste_real + costo_mano_obra)
    }


def calcular_sublimacion_industrial(ancho_cm, alto_cm, precio_tinta_ml, consumo_ml_cm2=0.0008, costo_papel_cm2=0.0025, desgaste_activo=0.0, tiempo_uso_min=0.0, costo_bajada_plancha=0.0):
    area_cm2 = float(ancho_cm or 0.0) * float(alto_cm or 0.0)
    consumo_tinta_ml = area_cm2 * float(consumo_ml_cm2 or 0.0)
    costo_tinta = consumo_tinta_ml * float(precio_tinta_ml or 0.0)
    costo_papel = area_cm2 * float(costo_papel_cm2 or 0.0)
    desgaste_plancha = float(desgaste_activo or 0.0) * float(tiempo_uso_min or 0.0)
    costo_total = costo_tinta + costo_papel + desgaste_plancha + float(costo_bajada_plancha or 0.0)
    return {
        'area_cm2': area_cm2,
        'consumo_tinta_ml': consumo_tinta_ml,
        'costo_tinta': money(costo_tinta),
        'costo_papel': money(costo_papel),
        'desgaste_plancha': money(desgaste_plancha),
        'bajada_plancha': money(costo_bajada_plancha),
        'costo_total': money(costo_total)
    }


def calcular_produccion_manual(materiales, activos):
    costo_materiales = sum(float(m.get('cantidad', 0.0)) * float(m.get('precio_unit', 0.0)) for m in (materiales or []))
    costo_desgaste = sum(float(a.get('tiempo', 0.0)) * float(a.get('desgaste_hora', 0.0)) for a in (activos or []))
    return {
        'costo_materiales': float(costo_materiales),
        'costo_desgaste_activos': float(costo_desgaste),
        'costo_total': float(costo_materiales + costo_desgaste)
    }


def registrar_orden_produccion(tipo, cliente, producto, estado='Cotización', costo=0.0, trabajo=''):
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ordenes_produccion (tipo, cliente, producto, estado, costo, trabajo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(tipo), str(cliente), str(producto), normalizar_estado_kanban(estado), money(costo), str(trabajo or ''))
        )
        registrar_log_actividad(conn, 'INSERT', 'ordenes_produccion')
        oid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO ordenes_estado_historial (orden_id, estado_anterior, estado_nuevo, usuario) VALUES (?, ?, ?, ?)",
            (oid, None, normalizar_estado_kanban(estado), st.session_state.get('usuario_nombre', 'Sistema'))
        )
        conn.commit()
        return oid


def registrar_tiempo_produccion(orden_id, inicio, fin):
    inicio_dt = pd.to_datetime(inicio)
    fin_dt = pd.to_datetime(fin)
    minutos = max(0.0, float((fin_dt - inicio_dt).total_seconds() / 60.0))
    with conectar() as conn:
        conn.execute(
            """
            INSERT INTO tiempos_produccion (orden_id, inicio, fin, minutos_reales)
            VALUES (?, ?, ?, ?)
            """,
            (int(orden_id), str(inicio_dt), str(fin_dt), minutos)
        )
        conn.commit()
    return minutos


def enviar_a_cotizacion_desde_produccion(datos):
    st.session_state['datos_pre_cotizacion'] = dict(datos or {})


def descontar_materiales_produccion(consumos, usuario=None, detalle='Consumo de producción'):
    if not isinstance(consumos, dict):
        return False, "Error interno: consumos inválidos"

    consumos_limpios = {int(k): float(v) for k, v in consumos.items() if float(v) > 0}
    if not consumos_limpios:
        return False, '⚠️ No hay consumos válidos para descontar'

    return registrar_venta_global(
        id_cliente=None,
        nombre_cliente='Consumo Interno Producción',
        detalle=str(detalle),
        monto_usd=0.01,
        metodo='Interno',
        consumos=consumos_limpios,
        usuario=usuario or st.session_state.get('usuario_nombre', 'Sistema')
    )


def convertir_area_cm2_a_unidad_inventario(item_id, area_cm2):
    area_cm2 = float(area_cm2 or 0.0)
    if area_cm2 <= 0:
        return 0.0

    with conectar() as conn:
        row = conn.execute(
            "SELECT unidad, COALESCE(factor_conversion, 1.0) FROM inventario WHERE id=?",
            (int(item_id),)
        ).fetchone()

    if not row:
        return area_cm2

    unidad, factor = row
    unidad = str(unidad or '').strip().lower()
    factor = float(factor or 1.0)

    if unidad in ('cm2', 'cm²'):
        return area_cm2

    if factor > 0:
        return area_cm2 / factor

    return area_cm2


def obtener_tintas_impresora(conn, impresora_sel):
    impresora = str(impresora_sel or '').strip()
    if not impresora:
        return pd.DataFrame()

    try:
        existe_activos = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activos'").fetchone()
        existe_inventario = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventario'").fetchone()
        if not existe_activos or not existe_inventario:
            return pd.DataFrame()

        cols_act = {r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()}
        cols_inv = {r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}

        if 'id' not in cols_act or 'id' not in cols_inv or 'item' not in cols_inv:
            return pd.DataFrame()

        campo_equipo = 'equipo' if 'equipo' in cols_act else ('nombre' if 'nombre' in cols_act else None)
        if not campo_equipo:
            return pd.DataFrame()

        campos_act = ['id', campo_equipo]
        if 'modelo' in cols_act:
            campos_act.append('modelo')
        if 'activo' in cols_act:
            campos_act.append('activo')

        q_act = f"SELECT {', '.join(campos_act)} FROM activos"
        if 'activo' in cols_act:
            q_act += " WHERE COALESCE(activo,1)=1"

        df_act = pd.read_sql_query(q_act, conn)
        if df_act.empty:
            return pd.DataFrame()

        if campo_equipo != 'equipo':
            df_act = df_act.rename(columns={campo_equipo: 'equipo'})

        serie_equipo = df_act['equipo'].fillna('').astype(str).str.strip()
        act_row = df_act[serie_equipo.str.lower() == impresora.lower()]
        if act_row.empty:
            act_row = df_act[serie_equipo.str.contains(re.escape(impresora), case=False, na=False)]
        if act_row.empty:
            return pd.DataFrame()

        activo_id = int(act_row.iloc[0]['id'])
        modelo_activo = str(act_row.iloc[0].get('modelo', '') or '').strip().lower()

        existe_rel = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activos_insumos'").fetchone()
        if existe_rel:
            cols_ai = {r[1] for r in conn.execute("PRAGMA table_info(activos_insumos)").fetchall()}
            where_ai = ["ai.activo_id=?"]
            if 'activo' in cols_ai:
                where_ai.append("COALESCE(ai.activo,1)=1")
            if 'activo' in cols_inv:
                where_ai.append("COALESCE(i.activo,1)=1")

            q_rel = f"""
                SELECT i.*
                FROM activos_insumos ai
                JOIN inventario i ON i.id = ai.inventario_id
                WHERE {' AND '.join(where_ai)}
                  AND lower(COALESCE(i.item,'')) LIKE '%tinta%'
                ORDER BY i.item
            """
            df_rel = pd.read_sql_query(q_rel, conn, params=(activo_id,))
            if not df_rel.empty:
                return df_rel

        q_inv = "SELECT * FROM inventario"
        if 'activo' in cols_inv:
            q_inv += " WHERE COALESCE(activo,1)=1"
        df_inv = pd.read_sql_query(q_inv, conn)
        if df_inv.empty:
            return pd.DataFrame()

        df_tintas = df_inv[df_inv['item'].fillna('').astype(str).str.contains('tinta', case=False, na=False)].copy()
        if df_tintas.empty:
            return df_tintas

        if modelo_activo and 'modelo_referencia' in cols_inv:
            serie_modelo = df_tintas['modelo_referencia'].fillna('').astype(str).str.lower().str.strip()
            df_mod = df_tintas[serie_modelo.str.contains(re.escape(modelo_activo), na=False)].copy()
            if not df_mod.empty:
                return df_mod.sort_values('item')

        patron_imp = re.escape(impresora.lower())
        df_nom = df_tintas[
            df_tintas['item'].fillna('').astype(str).str.lower().str.contains(patron_imp, na=False)
        ].copy()
        if not df_nom.empty:
            return df_nom.sort_values('item')

        return df_tintas.sort_values('item')

    except (pd.errors.DatabaseError, sqlite3.DatabaseError):
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def mapear_consumos_cmyk_a_inventario(totales_cmyk, df_tintas):
    if df_tintas is None or df_tintas.empty:
        return {}

    alias_colores = {
        'C': ['cian', 'cyan'],
        'M': ['magenta'],
        'Y': ['amarillo', 'yellow'],
        'K': ['negro', 'black', 'key']
    }

    base = df_tintas.copy()
    if 'id' not in base.columns or 'item' not in base.columns:
        return {}

    for col in ['cantidad', 'precio_usd', 'costo_real_ml']:
        if col not in base.columns:
            base[col] = 0.0

    base['item_norm'] = base['item'].fillna('').astype(str).str.lower()
    base['cantidad'] = pd.to_numeric(base['cantidad'], errors='coerce').fillna(0.0)
    base['precio_usd'] = pd.to_numeric(base['precio_usd'], errors='coerce').fillna(0.0)
    base['costo_real_ml'] = pd.to_numeric(base['costo_real_ml'], errors='coerce').fillna(0.0)

    consumos_ids = {}
    for color, ml in (totales_cmyk or {}).items():
        ml = float(ml or 0.0)
        if ml <= 0:
            continue

        aliases = alias_colores.get(str(color), [])
        if not aliases:
            continue
        patron = '|'.join([re.escape(a) for a in aliases])
        cand = base[base['item_norm'].str.contains(patron, na=False)]
        if cand.empty:
            continue

        cand = cand.sort_values(['cantidad', 'costo_real_ml', 'precio_usd'], ascending=[False, True, True])
        row = cand.iloc[0]
        iid = int(row['id'])
        consumos_ids[iid] = consumos_ids.get(iid, 0.0) + ml

    return consumos_ids

def registrar_movimiento_inventario(item_id, tipo, cantidad, motivo, usuario, conn=None):
    cantidad = float(cantidad or 0.0)
    if cantidad <= 0:
        return False

    payload = (int(item_id), str(tipo), float(cantidad), str(motivo), str(usuario))

    if conn is not None:
        conn.execute(
            """
            INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            payload
        )
        return True

    with conectar() as conn_local:
        conn_local.execute("BEGIN IMMEDIATE TRANSACTION")
        conn_local.execute(
            """
            INSERT INTO inventario_movs (item_id, tipo, cantidad, motivo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            payload
        )
        conn_local.commit()
    return True

def descontar_consumo_cmyk(consumos_dict, usuario=None, detalle="Consumo CMYK automático", metodo="Interno", monto_usd=0.01):
    consumos_limpios = {int(k): float(v) for k, v in (consumos_dict or {}).items() if float(v) > 0}
    if not consumos_limpios:
        return False, "⚠️ No hay consumos CMYK válidos para descontar"

    usuario_final = usuario or st.session_state.get("usuario_nombre", "Sistema")
    monto_final = money(monto_usd)
    if monto_final <= 0:
        monto_final = 0.01

    return registrar_venta_global(
        id_cliente=None,
        nombre_cliente="Consumo Interno CMYK",
        detalle=str(detalle),
        monto_usd=float(monto_final),
        metodo=str(metodo),
        consumos=consumos_limpios,
        usuario=usuario_final,
        tiene_iva=False,
        recargo_urgencia=0.0
    )

def hash_password(password: str, salt: str | None = None) -> str:
    """Genera hash PBKDF2 para almacenar contraseñas sin texto plano."""
    salt = salt or secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, digest = password_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        test_digest = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            int(iterations)
        ).hex()
        return hmac.compare_digest(test_digest, digest)
    except (ValueError, TypeError):
        return False


def obtener_password_admin_inicial() -> str:
    """Obtiene contraseña inicial desde entorno para evitar hardcode total en el código."""
    return os.getenv('IMPERIO_ADMIN_PASSWORD', 'atomica2026')

# --- 3. INICIALIZACIÓN DEL SISTEMA ---
def inicializar_sistema():
    with conectar() as conn:
        c = conn.cursor()

        tablas = [

            # CLIENTES
            "CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, categoria TEXT DEFAULT 'Nuevo')",

            # INVENTARIO (MEJORADO)
            """CREATE TABLE IF NOT EXISTS inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT UNIQUE,
                cantidad REAL,
                unidad TEXT,
                precio_usd REAL,
                minimo REAL DEFAULT 5.0,
                area_por_pliego_cm2 REAL,
                activo INTEGER DEFAULT 1,
                ultima_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # CONFIGURACION
            "CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)",

            # USUARIOS
            "CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, password_hash TEXT, rol TEXT, nombre TEXT)",

            # VENTAS
            "CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, cliente TEXT, detalle TEXT, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",

            # GASTOS
            "CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)",

            # MOVIMIENTOS DE INVENTARIO (MEJORADO)
            """CREATE TABLE IF NOT EXISTS inventario_movs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                tipo TEXT,
                cantidad REAL,
                motivo TEXT,
                usuario TEXT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(item_id) REFERENCES inventario(id)
            )""",

            # PROVEEDORES
            """CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE,
                telefono TEXT,
                rif TEXT,
                contacto TEXT,
                observaciones TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # ACTIVOS
            """CREATE TABLE IF NOT EXISTS activos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipo TEXT,
                categoria TEXT,
                inversion REAL,
                unidad TEXT,
                desgaste REAL,
                vida_total REAL,
                vida_restante REAL,
                uso_actual REAL DEFAULT 0,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # HISTORIAL DE ACTIVOS
            """CREATE TABLE IF NOT EXISTS activos_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activo TEXT,
                accion TEXT,
                detalle TEXT,
                costo REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS activos_insumos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activo_id INTEGER,
                inventario_id INTEGER,
                activo INTEGER DEFAULT 1,
                FOREIGN KEY(activo_id) REFERENCES activos(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )""",

            # HISTORIAL DE COMPRAS
            """CREATE TABLE IF NOT EXISTS historial_compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT,
                proveedor_id INTEGER,
                cantidad REAL,
                unidad TEXT,
                costo_total_usd REAL,
                costo_unit_usd REAL,
                impuestos REAL,
                delivery REAL,
                tasa_usada REAL,
                moneda_pago TEXT,
                usuario TEXT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS impresoras_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_impresora TEXT,
                consumo_base_ml REAL,
                factor_color REAL,
                factor_negro REAL,
                factor_foto REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS trabajos_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                cliente TEXT,
                impresora TEXT,
                costo_real REAL,
                precio_cobrado REAL,
                ganancia REAL,
                paginas INTEGER,
                ml_c REAL,
                ml_m REAL,
                ml_y REAL,
                ml_k REAL
            )""",

            """CREATE TABLE IF NOT EXISTS analisis_pixel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                archivo TEXT,
                pixeles_totales INTEGER,
                consumo_real_ml REAL,
                precision REAL
            )""",

            """CREATE TABLE IF NOT EXISTS aprendizaje_consumo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                archivo TEXT,
                consumo_estimado REAL,
                consumo_real REAL,
                error REAL,
                impresora TEXT
            )""",

            """CREATE TABLE IF NOT EXISTS perfiles_color (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                precision REAL,
                factor_c REAL,
                factor_m REAL,
                factor_y REAL,
                factor_k REAL,
                impresora TEXT
            )""",

            """CREATE TABLE IF NOT EXISTS vida_cabezal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                impresora TEXT,
                vida_total REAL,
                vida_restante REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS costos_impresora (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                impresora TEXT,
                electricidad REAL,
                mantenimiento REAL,
                desgaste_real REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS ordenes_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT,
                trabajo TEXT,
                tipo TEXT,
                producto TEXT,
                estado TEXT,
                costo REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS tiempos_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER,
                inicio DATETIME,
                fin DATETIME,
                minutos_reales REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS estadisticas_avanzadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                trabajo_mas_rentable TEXT,
                cliente_mas_rentable TEXT,
                impresora_mas_rentable TEXT
            )""",

            """CREATE TABLE IF NOT EXISTS materiales_corte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                factor_dureza REAL,
                inventario_id INTEGER
            )""",

            """CREATE TABLE IF NOT EXISTS recetas_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto TEXT,
                inventario_id INTEGER,
                cantidad REAL,
                activo_id INTEGER,
                tiempo REAL
            )""",

            """CREATE TABLE IF NOT EXISTS costo_energia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                costo_kwh REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS operadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                costo_por_hora REAL,
                activo INTEGER DEFAULT 1,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            """CREATE TABLE IF NOT EXISTS rentabilidad_productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto TEXT,
                costo_total REAL,
                precio_venta REAL,
                ganancia REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        ]

        for tabla in tablas:
            c.execute(tabla)

        c.execute("""
            CREATE TABLE IF NOT EXISTS logs_actividad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                accion TEXT,
                tabla_afectada TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                accion TEXT,
                valor_anterior TEXT,
                valor_nuevo TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS ordenes_estado_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER,
                estado_anterior TEXT,
                estado_nuevo TEXT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT
            )
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_auditoria_inventario_update
            AFTER UPDATE ON inventario
            BEGIN
                INSERT INTO auditoria (usuario, accion, valor_anterior, valor_nuevo)
                VALUES ('DB_TRIGGER', 'UPDATE_INVENTARIO',
                        'id=' || OLD.id || ';cant=' || OLD.cantidad || ';activo=' || COALESCE(OLD.activo,1),
                        'id=' || NEW.id || ';cant=' || NEW.cantidad || ';activo=' || COALESCE(NEW.activo,1));
            END;
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_auditoria_ventas_insert
            AFTER INSERT ON ventas
            BEGIN
                INSERT INTO auditoria (usuario, accion, valor_anterior, valor_nuevo)
                VALUES (COALESCE(NEW.usuario,'DB_TRIGGER'), 'INSERT_VENTA', '',
                        'id=' || NEW.id || ';monto=' || NEW.monto_total || ';metodo=' || NEW.metodo);
            END;
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_auditoria_gastos_update
            AFTER UPDATE ON gastos
            BEGIN
                INSERT INTO auditoria (usuario, accion, valor_anterior, valor_nuevo)
                VALUES ('DB_TRIGGER', 'UPDATE_GASTO',
                        'id=' || OLD.id || ';monto=' || OLD.monto || ';activo=' || COALESCE(OLD.activo,1),
                        'id=' || NEW.id || ';monto=' || NEW.monto || ';activo=' || COALESCE(NEW.activo,1));
            END;
        """)

        # ===========================================================
        # MIGRACIONES LIGERAS — BLOQUE FINAL SEGURO
        # ===========================================================

        # =========================
        # TABLA USUARIOS
        # =========================

        columnas_usuarios = {
            row[1]
            for row in c.execute(
                "PRAGMA table_info(usuarios)"
            ).fetchall()
        }

        if 'password_hash' not in columnas_usuarios:

            c.execute(
                "ALTER TABLE usuarios ADD COLUMN password_hash TEXT"
            )


        # =========================
        # TABLA INVENTARIO MOVIMIENTOS
        # =========================

        columnas_movs = {
            row[1]
            for row in c.execute(
                "PRAGMA table_info(inventario_movs)"
            ).fetchall()
        }

        if 'item_id' not in columnas_movs:

            c.execute(
                "ALTER TABLE inventario_movs ADD COLUMN item_id INTEGER"
            )


        # migración datos antiguos
        if 'item' in columnas_movs:

            c.execute(
                """
                UPDATE inventario_movs
                SET item_id = (

                    SELECT i.id

                    FROM inventario i

                    WHERE i.item = inventario_movs.item

                    LIMIT 1

                )
                WHERE item_id IS NULL
                """
            )


        # =========================
        # TABLA INVENTARIO
        # =========================

        columnas_inventario = {
            row[1]
            for row in c.execute(
                "PRAGMA table_info(inventario)"
            ).fetchall()
        }


        def agregar_columna(col, definicion):

            if col not in columnas_inventario:

                c.execute(
                    f"ALTER TABLE inventario ADD COLUMN {col} {definicion}"
                )


        agregar_columna("cantidad", "REAL DEFAULT 0")

        agregar_columna("unidad", "TEXT DEFAULT 'Unidad'")

        agregar_columna("precio_usd", "REAL DEFAULT 0")

        agregar_columna("minimo", "REAL DEFAULT 5.0")


        if 'ultima_actualizacion' not in columnas_inventario:

            c.execute(
                """
                ALTER TABLE inventario
                ADD COLUMN ultima_actualizacion DATETIME
                """
            )

            c.execute(
                """
                UPDATE inventario
                SET ultima_actualizacion = CURRENT_TIMESTAMP
                WHERE ultima_actualizacion IS NULL
                """
            )


        agregar_columna("imprimible_cmyk", "INTEGER DEFAULT 0")

        agregar_columna("area_por_pliego_cm2", "REAL")

        agregar_columna("activo", "INTEGER DEFAULT 1")

        agregar_columna("unidad_base", "TEXT DEFAULT 'ml'")

        agregar_columna("factor_conversion", "REAL DEFAULT 1.0")

        agregar_columna("capacidad_ml", "REAL DEFAULT NULL")

        agregar_columna("rendimiento_paginas", "INTEGER DEFAULT NULL")

        agregar_columna("costo_real_ml", "REAL DEFAULT NULL")
        agregar_columna("modelo_referencia", "TEXT")


        # =========================
        # NORMALIZACIÓN
        # =========================

        c.execute(
            """
            UPDATE inventario
            SET activo = 1
            WHERE activo IS NULL
            """
        )


        c.execute(
            """
            UPDATE inventario
            SET unidad_base = 'ml'
            WHERE unidad_base IS NULL
            """
        )


        c.execute(
            """
            UPDATE inventario
            SET factor_conversion = 1.0
            WHERE factor_conversion IS NULL
            OR factor_conversion <= 0
            """
        )


        # =========================
        # ACTUALIZAR COSTO REAL
        # =========================

        try:

            actualizar_costo_real_ml_inventario(conn)

        except Exception as e:

            print(
                "Aviso actualizar_costo_real_ml_inventario:",
                e
            )


        # =========================
        # ÍNDICES
        # =========================

        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ventas_cliente_id
            ON ventas(cliente_id)
            """
        )


        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_inventario_item
            ON inventario(item)
            """
        )


        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_inventario_movs_item_id
            ON inventario_movs(item_id)
            """
        )

        # Guardas lógicas de inventario (sin tocar estructura de tabla)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_inventario_no_negativo_insert
            BEFORE INSERT ON inventario
            FOR EACH ROW
            WHEN NEW.cantidad < 0
            BEGIN
                SELECT RAISE(ABORT, 'Stock no puede ser negativo');
            END;
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_inventario_no_negativo_update
            BEFORE UPDATE OF cantidad ON inventario
            FOR EACH ROW
            WHEN NEW.cantidad < 0
            BEGIN
                SELECT RAISE(ABORT, 'Stock no puede ser negativo');
            END;
        """)

        columnas_ventas = {row[1] for row in c.execute("PRAGMA table_info(ventas)").fetchall()}
        if 'usuario' not in columnas_ventas:
            c.execute("ALTER TABLE ventas ADD COLUMN usuario TEXT")

        columnas_activos = {row[1] for row in c.execute("PRAGMA table_info(activos)").fetchall()}
        if 'activo' not in columnas_activos:
            c.execute("ALTER TABLE activos ADD COLUMN activo INTEGER DEFAULT 1")
        if 'vida_total' not in columnas_activos:
            c.execute("ALTER TABLE activos ADD COLUMN vida_total REAL")
        if 'vida_restante' not in columnas_activos:
            c.execute("ALTER TABLE activos ADD COLUMN vida_restante REAL")
        if 'uso_actual' not in columnas_activos:
            c.execute("ALTER TABLE activos ADD COLUMN uso_actual REAL DEFAULT 0")
        if 'modelo' not in columnas_activos:
            c.execute("ALTER TABLE activos ADD COLUMN modelo TEXT")
        c.execute("UPDATE activos SET uso_actual = 0 WHERE uso_actual IS NULL")
        c.execute("UPDATE activos SET activo=1 WHERE activo IS NULL")
        c.execute("UPDATE activos SET vida_total = inversion WHERE vida_total IS NULL")
        c.execute("UPDATE activos SET vida_restante = vida_total WHERE vida_restante IS NULL")

        columnas_proveedores = {row[1] for row in c.execute("PRAGMA table_info(proveedores)").fetchall()}
        if "telefono" not in columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN telefono TEXT")
        if "rif" not in columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN rif TEXT")
        if "contacto" not in columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN contacto TEXT")
        if "observaciones" not in columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN observaciones TEXT")
        if "fecha_creacion" not in columnas_proveedores:
            c.execute("ALTER TABLE proveedores ADD COLUMN fecha_creacion TEXT")
            c.execute("UPDATE proveedores SET fecha_creacion = CURRENT_TIMESTAMP WHERE fecha_creacion IS NULL")

        for tabla_soft in ('clientes', 'proveedores', 'gastos', 'historial_compras', 'ventas', 'ordenes_produccion', 'inventario'):
            cols_soft = {row[1] for row in c.execute(f"PRAGMA table_info({tabla_soft})").fetchall()}
            if 'activo' not in cols_soft:
                c.execute(f"ALTER TABLE {tabla_soft} ADD COLUMN activo INTEGER DEFAULT 1")
            c.execute(f"UPDATE {tabla_soft} SET activo=1 WHERE activo IS NULL")

        cols_clientes = {row[1] for row in c.execute("PRAGMA table_info(clientes)").fetchall()}
        if 'categoria' not in cols_clientes:
            c.execute("ALTER TABLE clientes ADD COLUMN categoria TEXT DEFAULT 'General'")
        c.execute("UPDATE clientes SET categoria='General' WHERE categoria IS NULL OR trim(categoria)=''")

        columnas_conf = {row[1] for row in c.execute("PRAGMA table_info(configuracion)").fetchall()}

        # USUARIO ADMIN POR DEFECTO
        admin_password = obtener_password_admin_inicial()
        c.execute(
            """
            INSERT OR IGNORE INTO usuarios (username, password, password_hash, rol, nombre)
            VALUES (?, ?, ?, ?, ?)
            """,
            ('jefa', '', hash_password(admin_password), 'Admin', 'Dueña del Imperio')
        )
        c.execute(
            """
            UPDATE usuarios
            SET password_hash = ?, password = ''
            WHERE username = 'jefa' AND (password_hash IS NULL OR password_hash = '')
            """,
            (hash_password(admin_password),)
        )

        # CONFIGURACIÓN INICIAL
        config_init = [
            ('tasa_bcv', 36.50),
            ('tasa_binance', 38.00),
            ('costo_tinta_ml', 0.10),
            ('iva_perc', 16.0),
            ('igtf_perc', 3.0),
            ('banco_perc', 0.5),
            ('kontigo_perc', 5.0),
            ('kontigo_perc_entrada', 5.0),
            ('kontigo_perc_salida', 5.0),
            ('kontigo_saldo', 0.0),
            ('costo_tinta_auto', 1.0),
            ('factor_desperdicio_cmyk', 1.15),
            ('desgaste_cabezal_ml', 0.005),
            ('costo_bajada_plancha', 0.03),
            ('recargo_urgente_pct', 0.0),
            ('costo_limpieza_cabezal', 0.02)
        ]

        for p, v in config_init:
            c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))

        conn.commit()


# --- 4. CARGA DE DATOS ---
def _cargar_sesion_desde_db(conn, filtrar_inventario_activo=True):
    columnas_inventario = {row[1] for row in conn.execute("PRAGMA table_info(inventario)").fetchall()}
    query_inv = "SELECT * FROM inventario"
    if filtrar_inventario_activo and 'activo' in columnas_inventario:
        query_inv += " WHERE COALESCE(activo,1)=1"

    st.session_state.df_inv = pd.read_sql(query_inv, conn)
    st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes WHERE COALESCE(activo,1)=1", conn)
    conf_df = pd.read_sql("SELECT * FROM configuracion", conn)
    for _, row in conf_df.iterrows():
        st.session_state[row['parametro']] = float(row['valor'])


def cargar_datos():
    with conectar() as conn:
        try:
            _cargar_sesion_desde_db(conn)
        except (sqlite3.DatabaseError, ValueError, KeyError) as e:
            # Si el esquema aún no existe (p.ej. DB nueva o sesión antigua),
            # intentamos crear/migrar estructura y recargar una sola vez.
            inicializar_sistema()
            try:
                _cargar_sesion_desde_db(conn, filtrar_inventario_activo=False)
            except sqlite3.DatabaseError:
                st.warning(f"No se pudieron cargar todos los datos de sesión: {e}")
            
# Alias de compatibilidad para módulos que lo usan
def cargar_datos_seguros():
    cargar_datos()

# --- 5. LOGICA DE ACCESO ---
# Garantiza esquema base en cada arranque (idempotente).
inicializar_sistema()

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

def login():
    st.title("⚛️ Acceso al Imperio Atómico")
    with st.container(border=True):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar", use_container_width=True):
            with conectar() as conn:
                res = conn.execute(
                    "SELECT username, rol, nombre, password, password_hash FROM usuarios WHERE username=?",
                    (u,)
                ).fetchone()

            acceso_ok = False
            if res:
                username, rol, nombre, password_plain, password_hash = res
                if verify_password(p, password_hash):
                    acceso_ok = True
                elif password_plain and hmac.compare_digest(password_plain, p):
                    acceso_ok = True
                    with conectar() as conn:
                        conn.execute(
                            "UPDATE usuarios SET password_hash=?, password='' WHERE username=?",
                            (hash_password(p), username)
                        )
                        conn.commit()

            if acceso_ok:
                st.session_state.autenticado = True
                st.session_state.rol = rol
                st.session_state.usuario_nombre = nombre
                cargar_datos()
                st.rerun()
            else:
                st.error("Acceso denegado")

if not st.session_state.autenticado:
    login()
    st.stop()

# --- 6. SIDEBAR Y VARIABLES ---
cargar_datos()
t_bcv = st.session_state.get('tasa_bcv', 1.0)
t_bin = st.session_state.get('tasa_binance', 1.0)
ROL = st.session_state.get('rol', "Produccion")

with st.sidebar:
    st.header(f"👋 {st.session_state.usuario_nombre}")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 Bin: {t_bin}")

    menu = st.radio(
        "Secciones:",
        [
            "📊 Dashboard",
            "🛒 Venta Directa",
            "📦 Inventario",
            "👥 Clientes",
            "🎨 Análisis CMYK",
            "🏗️ Activos",
            "🛠️ Otros Procesos",
            "✂️ Corte Industrial",
            "🔥 Sublimación Industrial",
            "🎨 Producción Manual",
            "💰 Ventas",
            "📉 Gastos",
            "🏁 Cierre de Caja",
            "📊 Auditoría y Métricas",
            "📝 Cotizaciones",
            "💳 Kontigo",
            "⚙️ Configuración"
        ]
    )

    if st.button("🚪 Cerrar Sesión", use_container_width=True, key="btn_logout_sidebar"):
        st.session_state.clear()
        st.rerun()

        
# ===========================================================
# 📊 DASHBOARD GENERAL
# ===========================================================
if menu == "📊 Dashboard":

    st.title("📊 Dashboard Ejecutivo")
    st.caption("Resumen general del negocio: ventas, gastos, comisiones, clientes e inventario.")

    with conectar() as conn:
        try:
            df_ventas = pd.read_sql("SELECT fecha, cliente, metodo, monto_total FROM ventas", conn)
        except Exception:
            df_ventas = pd.DataFrame(columns=["fecha", "cliente", "metodo", "monto_total"])

        try:
            df_gastos = pd.read_sql("SELECT fecha, monto, categoria FROM gastos WHERE COALESCE(activo,1)=1", conn)
        except Exception:
            df_gastos = pd.DataFrame(columns=["fecha", "monto", "categoria"])

        try:
            total_clientes = conn.execute("SELECT COUNT(*) FROM clientes WHERE COALESCE(activo,1)=1").fetchone()[0]
        except Exception:
            total_clientes = 0

        try:
            df_inv_dash = pd.read_sql("SELECT cantidad, precio_usd, minimo FROM inventario WHERE COALESCE(activo,1)=1", conn)
        except Exception:
            df_inv_dash = pd.DataFrame(columns=["cantidad", "precio_usd", "minimo"])
        try:
            df_tiempos_dash = pd.read_sql("SELECT minutos_reales FROM tiempos_produccion", conn)
        except Exception:
            df_tiempos_dash = pd.DataFrame(columns=['minutos_reales'])

    # ------------------------------
    # Filtro temporal
    # ------------------------------
    rango = st.selectbox("Periodo", ["Hoy", "7 días", "30 días", "Todo"], index=2)
    desde = None
    if rango != "Todo":
        dias = {"Hoy": 0, "7 días": 7, "30 días": 30}[rango]
        desde = pd.Timestamp.now().normalize() - pd.Timedelta(days=dias)

    dfv = df_ventas.copy()
    dfg = df_gastos.copy()

    if not dfv.empty:
        dfv["fecha"] = pd.to_datetime(dfv["fecha"], errors="coerce")
        dfv = dfv.dropna(subset=["fecha"])
        if desde is not None:
            dfv = dfv[dfv["fecha"] >= desde]

    if not dfg.empty:
        dfg["fecha"] = pd.to_datetime(dfg["fecha"], errors="coerce")
        dfg = dfg.dropna(subset=["fecha"])
        if desde is not None:
            dfg = dfg[dfg["fecha"] >= desde]

    ventas_total = float(dfv["monto_total"].sum()) if not dfv.empty else 0.0
    gastos_total = float(dfg["monto"].sum()) if not dfg.empty else 0.0

    banco_perc = float(st.session_state.get('banco_perc', 0.5))
    kontigo_perc = float(st.session_state.get('kontigo_perc_entrada', st.session_state.get('kontigo_perc', 5.0)))

    comision_est = 0.0
    if not dfv.empty:
        ventas_bancarias = dfv[dfv['metodo'].str.contains("Pago|Transferencia", case=False, na=False)]
        ventas_kontigo = dfv[dfv['metodo'].str.contains("Kontigo", case=False, na=False)]
        if not ventas_bancarias.empty:
            comision_est += float(ventas_bancarias['monto_total'].sum() * (banco_perc / 100))
        if not ventas_kontigo.empty:
            comision_est += float(ventas_kontigo['monto_total'].sum() * (kontigo_perc / 100))

    utilidad = ventas_total - gastos_total - comision_est

    utilidad_neta_mes = 0.0
    if not df_ventas.empty:
        dvm = df_ventas.copy()
        dvm['fecha'] = pd.to_datetime(dvm['fecha'], errors='coerce')
        ini_mes = pd.Timestamp.now().replace(day=1).normalize()
        ventas_mes = float(dvm[dvm['fecha'] >= ini_mes]['monto_total'].sum()) if 'monto_total' in dvm.columns else 0.0
        gastos_mes = 0.0
        if not df_gastos.empty:
            dgm = df_gastos.copy()
            dgm['fecha'] = pd.to_datetime(dgm['fecha'], errors='coerce')
            gastos_mes = float(dgm[dgm['fecha'] >= ini_mes]['monto'].sum()) if 'monto' in dgm.columns else 0.0
        utilidad_neta_mes = money(ventas_mes - gastos_mes)

    eficiencia_horas = float(df_tiempos_dash['minutos_reales'].mean() / 60.0) if not df_tiempos_dash.empty else 0.0
    insumos_criticos = int((df_inv_dash['cantidad'] <= df_inv_dash['minimo']).sum()) if not df_inv_dash.empty else 0

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric('Utilidad Neta del Mes', f"$ {utilidad_neta_mes:,.2f}")
    kpi2.metric('Eficiencia Producción (prom. entrega)', f"{eficiencia_horas:.2f} h")
    kpi3.metric('Alerta Insumos Críticos', insumos_criticos)
    st.divider()

    capital_inv = 0.0
    stock_bajo = 0
    if not df_inv_dash.empty:
        capital_inv = float((df_inv_dash["cantidad"] * df_inv_dash["precio_usd"]).sum())
        stock_bajo = int((df_inv_dash["cantidad"] <= df_inv_dash["minimo"]).sum())

    # KPI v4.0 de mando
    costos_fijos_hoy = float(dfg[dfg['fecha'].dt.date == pd.Timestamp.now().date()]['monto'].sum()) if (not dfg.empty and 'fecha' in dfg.columns) else 0.0
    punto_equilibrio_restante = max(0.0, money(costos_fijos_hoy - ventas_total))

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💰 Ventas", f"${ventas_total:,.2f}")
    c2.metric("💸 Gastos", f"${gastos_total:,.2f}")
    c3.metric("🏦 Comisiones", f"${comision_est:,.2f}")
    c4.metric("📈 Utilidad", f"${utilidad:,.2f}")
    c5.metric("👥 Clientes", total_clientes)
    c6.metric("🚨 Ítems Mínimo", stock_bajo)

    st.divider()

    dpe1, dpe2 = st.columns(2)
    dpe1.metric('Punto de Equilibrio (faltante hoy)', f"$ {punto_equilibrio_restante:,.2f}")
    dpe2.metric('Costos fijos hoy', f"$ {costos_fijos_hoy:,.2f}")

    with conectar() as conn:
        df_top = pd.read_sql_query("SELECT detalle, monto_total FROM ventas WHERE COALESCE(activo,1)=1 ORDER BY fecha DESC LIMIT 500", conn)
        try:
            df_costos = pd.read_sql_query("SELECT trabajo, COALESCE(costo,0) AS costo FROM ordenes_produccion WHERE COALESCE(activo,1)=1", conn)
        except Exception:
            df_costos = pd.DataFrame(columns=['trabajo', 'costo'])
    if not df_top.empty:
        ventas_det = df_top.groupby('detalle', as_index=False)['monto_total'].sum().rename(columns={'monto_total': 'ventas'})
        if not df_costos.empty:
            costos_det = df_costos.groupby('trabajo', as_index=False)['costo'].sum().rename(columns={'trabajo': 'detalle', 'costo': 'costos'})
            top3 = ventas_det.merge(costos_det, on='detalle', how='left')
        else:
            top3 = ventas_det.copy()
            top3['costos'] = 0.0
        top3['costos'] = top3['costos'].fillna(0.0)
        top3['utilidad_neta'] = top3['ventas'] - top3['costos']
        top3 = top3.sort_values('utilidad_neta', ascending=False).head(3)
        st.subheader('🏆 Ranking de Rentabilidad Neta por producto')
        st.dataframe(top3, use_container_width=True, hide_index=True)

    st.subheader('🚦 Monitor de Insumos')
    if not df_inv_dash.empty:
        monitor = df_inv_dash.copy()
        monitor['nivel'] = np.where(monitor['cantidad'] <= monitor['minimo'], '🔴 Crítico', np.where(monitor['cantidad'] <= (monitor['minimo']*1.5), '🟡 Bajo', '🟢 OK'))
        st.dataframe(monitor[['cantidad','minimo','nivel']].head(20), use_container_width=True, hide_index=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("📆 Ventas por día")
        if dfv.empty:
            st.info("No hay ventas registradas en el periodo.")
        else:
            d1 = dfv.copy()
            d1["dia"] = d1["fecha"].dt.date.astype(str)
            resumen_v = d1.groupby("dia", as_index=False)["monto_total"].sum()
            fig_v = px.line(resumen_v, x="dia", y="monto_total", markers=True)
            fig_v.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
            st.plotly_chart(fig_v, use_container_width=True)

    with col_b:
        st.subheader("📉 Gastos por día")
        if dfg.empty:
            st.info("No hay gastos registrados en el periodo.")
        else:
            d2 = dfg.copy()
            d2["dia"] = d2["fecha"].dt.date.astype(str)
            resumen_g = d2.groupby("dia", as_index=False)["monto"].sum()
            fig_g = px.bar(resumen_g, x="dia", y="monto")
            fig_g.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
            st.plotly_chart(fig_g, use_container_width=True)

    cA, cB = st.columns(2)
    with cA:
        st.subheader("💳 Ventas por método")
        if dfv.empty:
            st.info("Sin datos para métodos de pago.")
        else:
            vm = dfv.groupby('metodo', as_index=False)['monto_total'].sum().sort_values('monto_total', ascending=False)
            fig_m = px.pie(vm, names='metodo', values='monto_total')
            st.plotly_chart(fig_m, use_container_width=True)

    with cB:
        st.subheader("🏆 Top clientes")
        if dfv.empty or 'cliente' not in dfv.columns:
            st.info("Sin datos de clientes en el periodo.")
        else:
            topc = dfv.groupby('cliente', as_index=False)['monto_total'].sum().sort_values('monto_total', ascending=False).head(10)
            st.dataframe(topc, use_container_width=True)

    st.divider()
    st.subheader("📦 Estado del Inventario")
    st.metric("💼 Capital inmovilizado en inventario", f"${capital_inv:,.2f}")

# ===========================================================
# 📦 MÓDULO DE INVENTARIO – ESTRUCTURA CORREGIDA
# ===========================================================
elif menu == "📦 Inventario":

    st.title("📦 Centro de Control de Suministros")

    # --- SINCRONIZACIÓN CON SESIÓN ---
    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    t_ref = st.session_state.get('tasa_bcv', 36.5)
    t_bin = st.session_state.get('tasa_binance', 38.0)
    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    # =======================================================
    # 1️⃣ DASHBOARD EJECUTIVO
    # =======================================================
    if not df_inv.empty:

        with st.container(border=True):

            c1, c2, c3, c4 = st.columns(4)

            capital_total = (df_inv["cantidad"] * df_inv["precio_usd"]).sum()
            items_criticos = df_inv[df_inv["cantidad"] <= df_inv["minimo"]]
            total_items = len(df_inv)

            salud = ((total_items - len(items_criticos)) / total_items) * 100 if total_items > 0 else 0

            c1.metric("💰 Capital en Inventario", f"${capital_total:,.2f}")
            c2.metric("📦 Total Ítems", total_items)
            c3.metric("🚨 Stock Bajo", len(items_criticos), delta="Revisar" if len(items_criticos) > 0 else "OK", delta_color="inverse")
            c4.metric("🧠 Salud del Almacén", f"{salud:.0f}%")

    # =======================================================
    # 2️⃣ TABS
    # =======================================================
    tabs = st.tabs([
        "📋 Existencias",
        "📥 Registrar Compra",
        "📊 Historial Compras",
        "👤 Proveedores",
        "🔧 Ajustes"
    ])

    # =======================================================
    # 📋 TAB 1 — EXISTENCIAS
    # =======================================================
    with tabs[0]:

        if df_inv.empty:
            st.info("Inventario vacío.")
        else:
            col1, col2, col3 = st.columns([2, 1, 1])
            filtro = col1.text_input("🔍 Buscar insumo")
            moneda_vista = col2.selectbox("Moneda", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], key="inv_moneda_vista")
            solo_bajo = col3.checkbox("🚨 Solo stock bajo")

            tasa_vista = 1.0
            simbolo = "$"

            if "BCV" in moneda_vista:
                tasa_vista = t_ref
                simbolo = "Bs"
            elif "Binance" in moneda_vista:
                tasa_vista = t_bin
                simbolo = "Bs"

            df_v = df_inv.copy()

            if filtro:
                df_v = df_v[df_v["item"].str.contains(filtro, case=False)]

            if solo_bajo:
                df_v = df_v[df_v["cantidad"] <= df_v["minimo"]]

            df_v["Costo Unitario"] = df_v["precio_usd"] * tasa_vista
            df_v["Valor Total"] = df_v["cantidad"] * df_v["Costo Unitario"]


            def resaltar_critico(row):
                if row["cantidad"] <= row["minimo"]:
                    return ['background-color: rgba(255,0,0,0.15)'] * len(row)
                return [''] * len(row)
          
            st.dataframe(
               df_v.style.apply(resaltar_critico, axis=1),
                column_config={
                    "item": "Insumo",
                    "cantidad": "Stock",
                    "unidad": "Unidad",
                    "Costo Unitario": st.column_config.NumberColumn(
                        f"Costo ({simbolo})", format="%.2f"
                    ),
                    "Valor Total": st.column_config.NumberColumn(
                        f"Valor Total ({simbolo})", format="%.2f"
                    ),
                    "minimo": "Mínimo",
                    "imprimible_cmyk": st.column_config.CheckboxColumn("CMYK", help="Disponible para impresión en Análisis CMYK"),
                    "area_por_pliego_cm2": st.column_config.NumberColumn("cm²/pliego", format="%.2f"),
                    "precio_usd": None,
                    "id": None,
                    "activo": None,
                    "ultima_actualizacion": None
                },
                use_container_width=True,
                hide_index=True
            )

        st.divider()
        st.subheader("🛠 Gestión de Insumo Existente")

        if not df_inv.empty:

            insumo_sel = st.selectbox("Seleccionar Insumo", df_inv["item"].tolist())
            fila_sel = df_inv[df_inv["item"] == insumo_sel].iloc[0]
            colA, colB, colC = st.columns(3)
            nuevo_min = colA.number_input("Nuevo Stock Mínimo", min_value=0.0, value=float(fila_sel.get('minimo', 0)))
            flag_cmyk = colB.checkbox("Visible en CMYK", value=bool(fila_sel.get('imprimible_cmyk', 0)))

            if colA.button("Actualizar Mínimo"):
                with conectar() as conn:
                    conn.execute(
                        "UPDATE inventario SET minimo=?, imprimible_cmyk=? WHERE item=?",
                        (nuevo_min, 1 if flag_cmyk else 0, insumo_sel)
                    )
                    conn.commit()
                cargar_datos()
                st.success("Stock mínimo actualizado.")
                st.rerun()

            merma_qty = colC.number_input('Registrar merma (cantidad)', min_value=0.0, value=0.0, key='inv_merma_qty')
            if colC.button('⚠️ Registrar merma') and merma_qty > 0:
                with conectar() as conn:
                    row_item = conn.execute("SELECT id, cantidad, COALESCE(precio_usd,0) FROM inventario WHERE item=?", (insumo_sel,)).fetchone()
                    if row_item:
                        iid, cant_act, precio_u = int(row_item[0]), float(row_item[1] or 0.0), float(row_item[2] or 0.0)
                        nueva = max(0.0, cant_act - float(merma_qty))
                        conn.execute("UPDATE inventario SET cantidad=?, ultima_actualizacion=CURRENT_TIMESTAMP WHERE id=?", (nueva, iid))
                        registrar_movimiento_inventario(iid, 'SALIDA', float(merma_qty), 'Merma/Material dañado', st.session_state.get('usuario_nombre','Sistema'), conn=conn)
                        costo_merma = money(float(merma_qty) * precio_u)
                        conn.execute("INSERT INTO gastos (descripcion, monto, categoria, metodo, usuario, activo) VALUES (?,?,?,?,?,1)", (f'Merma de inventario: {insumo_sel}', float(costo_merma), 'Gasto por Falla de Calidad', 'Interno', st.session_state.get('usuario_nombre','Sistema')))
                        registrar_log_actividad(conn, 'MERMA', 'inventario')
                        registrar_auditoria(conn, 'MERMA_INVENTARIO', cant_act, nueva)
                        conn.commit()
                st.toast('Merma registrada como pérdida', icon='⚠️')
                cargar_datos()
                st.rerun()

            # Conversión para inventarios viejos cargados como cm2
            if str(fila_sel.get('unidad', '')).lower() == 'cm2':
                st.warning("Este insumo aún está en cm². Conviene convertirlo a pliegos para control real de stock.")
                ref_default = float(fila_sel.get('area_por_pliego_cm2') or fila_sel.get('cantidad', 1) or 1)
                cm2_por_hoja = colC.number_input("cm² por pliego", min_value=1.0, value=ref_default)
                if colC.button("🔄 Convertir stock cm2 → pliegos"):
                    pliegos = float(fila_sel.get('cantidad', 0)) / float(cm2_por_hoja)
                    with conectar() as conn:
                        conn.execute(
                            "UPDATE inventario SET cantidad=?, unidad='pliegos', area_por_pliego_cm2=?, activo=1 WHERE item=?",
                            (pliegos, cm2_por_hoja, insumo_sel)
                        )
                        item_row = conn.execute("SELECT id FROM inventario WHERE item=?", (insumo_sel,)).fetchone()
                        if item_row:
                            registrar_movimiento_inventario(
                                item_id=int(item_row[0]),
                                tipo='AJUSTE',
                                cantidad=float(pliegos),
                                motivo='Conversión cm2 -> pliegos',
                                usuario=st.session_state.get("usuario_nombre", "Sistema"),
                                conn=conn
                            )
                        conn.commit()
                    st.success(f"Convertido a {pliegos:.3f} pliegos.")
                    cargar_datos()
                    st.rerun()
            if colB.button("🗑 Eliminar Insumo"):
                with conectar() as conn:
                    existe_historial = conn.execute(
                        "SELECT COUNT(*) FROM historial_compras WHERE item=?",
                        (insumo_sel,)
                    ).fetchone()[0]
                    existe_movs = conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM inventario_movs m
                        JOIN inventario i ON i.id = m.item_id
                        WHERE i.item=?
                        """,
                        (insumo_sel,)
                    ).fetchone()[0]
                    if existe_historial > 0 or existe_movs > 0:
                        conn.execute(
                            "UPDATE inventario SET activo=0, cantidad=0 WHERE item=?",
                            (insumo_sel,)
                        )
                        conn.commit()
                        st.success("Insumo archivado (tiene movimientos/historial y no se elimina físicamente).")
                        cargar_datos()
                        st.rerun()
                    else:
                        st.session_state.confirmar_borrado = True

            if st.session_state.get("confirmar_borrado", False):
                st.warning(f"⚠ Confirmar eliminación de '{insumo_sel}'")
                colC, colD = st.columns(2)

                if colC.button("✅ Confirmar"):
                    with conectar() as conn:
                        existe_movs = conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM inventario_movs m
                            JOIN inventario i ON i.id = m.item_id
                            WHERE i.item=?
                            """,
                            (insumo_sel,)
                        ).fetchone()[0]
                        if existe_movs > 0:
                            conn.execute(
                                "UPDATE inventario SET activo=0, cantidad=0 WHERE item=?",
                                (insumo_sel,)
                            )
                        else:
                            conn.execute(
                                "UPDATE inventario SET activo=0, ultima_actualizacion=CURRENT_TIMESTAMP WHERE item=?",
                                (insumo_sel,)
                            )
                        conn.commit()
                    st.session_state.confirmar_borrado = False
                    cargar_datos()
                    st.success("Insumo eliminado.")
                    st.rerun()

                if colD.button("❌ Cancelar"):
                    st.session_state.confirmar_borrado = False

    # =======================================================
    # 📥 TAB 2 — REGISTRAR COMPRA
    # =======================================================
    with tabs[1]:

        st.subheader("📥 Registrar Nueva Compra")

        with conectar() as conn:
            try:
                proveedores_existentes = pd.read_sql(
                    "SELECT nombre FROM proveedores WHERE COALESCE(activo,1)=1 ORDER BY nombre ASC",
                    conn
                )["nombre"].dropna().astype(str).tolist()
            except (sqlite3.DatabaseError, pd.errors.DatabaseError):
                proveedores_existentes = []

        col_base1, col_base2 = st.columns(2)
        nombre_c = col_base1.text_input("Nombre del Insumo")
        proveedor_sel = col_base2.selectbox(
            "Proveedor",
            ["(Sin proveedor)", "➕ Nuevo proveedor"] + proveedores_existentes,
            key="inv_proveedor_compra"
        )

        proveedor = ""
        if proveedor_sel == "➕ Nuevo proveedor":
            proveedor = st.text_input("Nombre del nuevo proveedor", key="inv_proveedor_nuevo")
        elif proveedor_sel != "(Sin proveedor)":
            proveedor = proveedor_sel

        minimo_stock = st.number_input("Stock mínimo", min_value=0.0)
        imprimible_cmyk = st.checkbox(
            "✅ Se puede imprimir (mostrar en módulo CMYK)",
            value=False,
            help="Marca solo los insumos que sí participan en impresión (tintas, acetato imprimible, papeles de impresión)."
        )

        # ------------------------------
        # TIPO DE UNIDAD
        # ------------------------------
        tipo_unidad = st.selectbox(
            "Tipo de Unidad",
            ["Unidad", "Área (cm²)", "Líquido (ml)", "Peso (gr)"]
        )

        stock_real = 0
        unidad_final = "Unidad"
        area_por_pliego_val = None

        if tipo_unidad == "Área (cm²)":
            c1, c2, c3 = st.columns(3)
            ancho = c1.number_input("Ancho (cm)", min_value=0.1)
            alto = c2.number_input("Alto (cm)", min_value=0.1)
            cantidad_envases = c3.number_input("Cantidad de Pliegos", min_value=0.001)

            # Inventario se controla por unidades físicas (hojas/pliegos),
            # no por área total acumulada. El área queda como referencia técnica.
            area_por_pliego = ancho * alto
            area_total_ref = area_por_pliego * cantidad_envases
            stock_real = cantidad_envases
            unidad_final = "pliegos"
            area_por_pliego_val = area_por_pliego

            st.caption(
                f"Referencia técnica: {area_por_pliego:,.2f} cm² por pliego | "
                f"Área total cargada: {area_total_ref:,.2f} cm²"
            )

        elif tipo_unidad == "Líquido (ml)":
            c1, c2 = st.columns(2)
            ml_por_envase = c1.number_input("ml por Envase", min_value=1.0)
            cantidad_envases = c2.number_input("Cantidad de Envases", min_value=0.001)
            stock_real = ml_por_envase * cantidad_envases
            unidad_final = "ml"

        elif tipo_unidad == "Peso (gr)":
            c1, c2 = st.columns(2)
            gr_por_envase = c1.number_input("gramos por Envase", min_value=1.0)
            cantidad_envases = c2.number_input("Cantidad de Envases", min_value=0.001)
            stock_real = gr_por_envase * cantidad_envases
            unidad_final = "gr"

        else:
            cantidad_envases = st.number_input("Cantidad Comprada", min_value=0.001)
            stock_real = cantidad_envases
            unidad_final = "Unidad"

        # ------------------------------
        # DATOS FINANCIEROS
        # ------------------------------
        col4, col5 = st.columns(2)
        monto_factura = col4.number_input("Monto Factura", min_value=0.0)
        moneda_pago = col5.selectbox(
            "Moneda",
            ["USD $", "Bs (BCV)", "Bs (Binance)"],
            key="inv_moneda_pago"
        )

        col6, col7, col8 = st.columns(3)
        iva_activo = col6.checkbox(f"IVA (+{st.session_state.get('iva_perc',16)}%)")
        igtf_activo = col7.checkbox(f"IGTF (+{st.session_state.get('igtf_perc',3)}%)")
        banco_activo = col8.checkbox(f"Banco (+{st.session_state.get('banco_perc',0.5)}%)")

        st.caption(f"Sugerencia de impuesto total para compras: {st.session_state.get('inv_impuesto_default', 16.0):.2f}%")

        # DELIVERY INTELIGENTE

        col_del1, col_del2, col_del3 = st.columns([1.2, 1, 1])

        delivery_monto = col_del1.number_input(
            "Gastos Logística / Delivery",
            min_value=0.0,
            value=float(st.session_state.get("inv_delivery_default", 0.0))
        )

        delivery_moneda = col_del2.selectbox(
            "Moneda Delivery",
            ["USD $", "Bs (BCV)", "Bs (Binance)"],
            key="inv_delivery_moneda"
        )

        usar_tasa_manual = col_del3.checkbox("Tasa manual")

        if usar_tasa_manual:

            tasa_delivery = st.number_input(
                "Tasa usada en delivery",
                min_value=0.0001,
                value=float(
                    t_ref if "BCV" in delivery_moneda else
                    t_bin if "Binance" in delivery_moneda else
                    1.0
                ),
                format="%.2f",
                key="inv_delivery_tasa_manual"
            )

        else:

            if "BCV" in delivery_moneda:
                tasa_delivery = t_ref

            elif "Binance" in delivery_moneda:
                tasa_delivery = t_bin

            else:
                tasa_delivery = 1.0

        delivery = delivery_monto / tasa_delivery if tasa_delivery > 0 else delivery_monto

        st.caption(f"Delivery equivalente: ${delivery:.2f}")

        
        # =======================================================
        # 🎨 GENERADOR DE VARIANTES EDITABLES (COLORES / MODELOS)
        # =======================================================
        
        st.divider()
        st.subheader("🎨 Variantes rápidas (colores, modelos, etc)")
        
        # crear memoria
        if "variantes_editor" not in st.session_state:
        
            st.session_state.variantes_editor = {}
        
        
        colv1, colv2 = st.columns([2,1])
        
        nombre_base_var = colv1.text_input(
            "Nombre base del producto",
            value=nombre_c,
            key="base_variante"
        )
        
        variantes_txt = colv1.text_input(
            "Escribe variantes separadas por coma",
            placeholder="Rojo, Azul, Verde, Negro",
            key="lista_variantes"
        )
        
        
        if colv2.button("Crear barras"):
        
            if variantes_txt:
        
                lista = [v.strip() for v in variantes_txt.split(",")]
        
                st.session_state.variantes_editor = {
        
                    var: 0.0 for var in lista
        
                }
        
        
        # Mostrar barras editables
        
        if st.session_state.variantes_editor:
        
            st.write("### Cantidades por variante")
        
            cantidades_finales = {}
        
            for var in st.session_state.variantes_editor:
        
                cantidades_finales[var] = st.number_input(
        
                    f"{nombre_base_var} - {var}",
        
                    min_value=0.0,
        
                    value=0.0,
        
                    key=f"var_{var}"
        
                )
        
        
            # guardar variantes
        
            if st.button("💾 Guardar TODAS las variantes"):
        
        
                if "BCV" in moneda_pago:
                    tasa_usada = t_ref
                elif "Binance" in moneda_pago:
                    tasa_usada = t_bin
                else:
                    tasa_usada = 1.0
        
        
                porc_impuestos = 0
        
                if iva_activo:
                    porc_impuestos += st.session_state.get("iva_perc",16)
        
                if igtf_activo:
                    porc_impuestos += st.session_state.get("igtf_perc",3)
        
                if banco_activo:
                    porc_impuestos += st.session_state.get("banco_perc",0.5)
        
        
                # ===============================
                # CALCULO CORRECTO PROPORCIONAL
                # ===============================
        
                costo_factura_total = ((monto_factura / tasa_usada) * (1 + (porc_impuestos/100))) + delivery
        
        
                total_cantidad_variantes = sum(cantidades_finales.values())
        
        
                if total_cantidad_variantes <= 0:
        
                    st.error("Debes colocar cantidades válidas")
        
                    st.stop()
        
        
                costo_unitario = costo_factura_total / total_cantidad_variantes
        
        
                with conectar() as conn:
        
                    cur = conn.cursor()
        
        
                    proveedor_id = None
        
                    if proveedor:
        
                        cur.execute("SELECT id FROM proveedores WHERE nombre=?", (proveedor,))
        
                        row = cur.fetchone()
        
                        proveedor_id = row[0] if row else None
        
        
                    for var, cantidad in cantidades_finales.items():
        
                        if cantidad <= 0:
        
                            continue
        
        
                        nombre_final = f"{nombre_base_var} - {var}"
        
        
                        costo_total_item = cantidad * costo_unitario
        
        
                        old = cur.execute(
        
                            "SELECT cantidad, precio_usd FROM inventario WHERE item=?",
        
                            (nombre_final,)
        
                        ).fetchone()
        
        
                        if old:
        
                            nueva_cant = old[0] + cantidad
        
                            precio_ponderado = (
        
                                (old[0]*old[1] + cantidad*costo_unitario)
        
                                / nueva_cant
        
                            )
        
                        else:
        
                            nueva_cant = cantidad
        
                            precio_ponderado = costo_unitario
        
        
                        # INVENTARIO
        
                        cur.execute("""
        
                        INSERT OR REPLACE INTO inventario
        
                        (item,cantidad,unidad,precio_usd,minimo,imprimible_cmyk,area_por_pliego_cm2,activo)
        
                        VALUES (?,?,?,?,?,?,?,1)
        
                        """,
        
                        (
        
                            nombre_final,
        
                            nueva_cant,
        
                            unidad_final,
        
                            precio_ponderado,
        
                            minimo_stock,
        
                            1 if imprimible_cmyk else 0,
        
                            area_por_pliego_val
        
                        ))
        
        
                        # HISTORIAL
        
                        cur.execute("""
        
                        INSERT INTO historial_compras
        
                        (item, proveedor_id, cantidad, unidad, costo_total_usd, costo_unit_usd, impuestos, delivery, tasa_usada, moneda_pago, usuario)
        
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        
                        """,
        
                        (
        
                            nombre_final,
        
                            proveedor_id,
        
                            cantidad,
        
                            unidad_final,
        
                            costo_total_item,
        
                            costo_unitario,
        
                            porc_impuestos,
        
                            delivery,
        
                            tasa_usada,
        
                            moneda_pago,
        
                            usuario_actual
        
                        ))
        
        
                    conn.commit()
        
        
                cargar_datos()
        
                st.session_state.variantes_editor = {}
        
                st.success("✅ Variantes guardadas correctamente")
        
                st.rerun()
        
# =======================================================
# 📊 TAB 3 — HISTORIAL DE COMPRAS (VERSION PRO SEGURA)
# =======================================================
with tabs[2]:

    st.subheader("📊 Historial Profesional de Compras")

    with conectar() as conn:

        # ==========================================
        # ASEGURAR COLUMNA ACTIVO
        # ==========================================

        columnas = [

            col[1]

            for col in conn.execute(

                "PRAGMA table_info(historial_compras)"

            ).fetchall()

        ]

        if "activo" not in columnas:

            conn.execute(

                "ALTER TABLE historial_compras ADD COLUMN activo INTEGER DEFAULT 1"

            )

            conn.commit()


        # ==========================================
        # CARGAR DATA
        # ==========================================

        df_hist = pd.read_sql("""

            SELECT 

            h.id compra_id,

            h.fecha,

            h.item,

            h.cantidad,

            h.unidad,

            h.costo_total_usd,

            h.costo_unit_usd,

            h.impuestos,

            h.delivery,

            h.moneda_pago,

            COALESCE(p.nombre,'SIN PROVEEDOR') proveedor

            FROM historial_compras h

            LEFT JOIN proveedores p

            ON p.id = h.proveedor_id

            WHERE h.activo=1

            ORDER BY h.fecha DESC

        """, conn)



    if df_hist.empty:

        st.info("Sin compras registradas")

        st.stop()


    # ==========================================
    # FILTROS
    # ==========================================

    c1,c2 = st.columns(2)

    filtro_item = c1.text_input("🔍 Filtrar Insumo")

    filtro_proveedor = c2.text_input("🔍 Filtrar Proveedor")


    df_view = df_hist.copy()


    if filtro_item:

        df_view = df_view[

            df_view.item.str.contains(

                filtro_item,

                case=False,

                na=False

            )

        ]


    if filtro_proveedor:

        df_view = df_view[

            df_view.proveedor.str.contains(

                filtro_proveedor,

                case=False,

                na=False

            )

        ]


    # ==========================================
    # METRICAS
    # ==========================================

    total = df_view.costo_total_usd.sum()

    st.metric(

        "💰 Total Comprado",

        f"${total:,.2f}"

    )


    # ==========================================
    # TABLA
    # ==========================================

    st.dataframe(

        df_view,

        use_container_width=True,

        hide_index=True

    )


    # ==========================================
    # ELIMINAR COMPRA
    # ==========================================

    st.divider()

    st.subheader("🧹 Corregir compra")


    opciones = {

        f"#{r.compra_id} | {r.item} | {r.cantidad} {r.unidad}":

        r.compra_id

        for r in df_hist.itertuples()

    }


    sel = st.selectbox(

        "Seleccionar",

        list(opciones.keys())

    )


    id_sel = opciones[sel]


    row = df_hist[

        df_hist.compra_id == id_sel

    ].iloc[0]


    if st.button("🗑 Eliminar compra"):


        try:


            with conectar() as conn:


                conn.execute("BEGIN")


                # INVENTARIO

                inv = conn.execute(

                    """

                    SELECT id,cantidad

                    FROM inventario

                    WHERE item=?

                    """,

                    (row.item,)

                ).fetchone()


                if inv:


                    nueva = max(

                        0,

                        inv[1] - row.cantidad

                    )


                    conn.execute(

                        """

                        UPDATE inventario

                        SET cantidad=?

                        WHERE id=?

                        """,

                        (

                            nueva,

                            inv[0]

                        )

                    )


                    registrar_movimiento_inventario(

                        inv[0],

                        "SALIDA",

                        row.cantidad,

                        "Corrección",

                        usuario_actual,

                        conn

                    )


                # HISTORIAL

                conn.execute(

                    """

                    UPDATE historial_compras

                    SET activo=0

                    WHERE id=?

                    """,

                    (id_sel,)

                )


                conn.commit()


            st.success("Compra eliminada")


            cargar_datos()

            st.rerun()


        except Exception as e:


            st.error(f"Error: {e}")

# =======================================================
# 👤 TAB 4 — PROVEEDORES (VERSIÓN SEGURA PRO)
# =======================================================
with tabs[3]:

    st.subheader("👤 Directorio de Proveedores")

    with conectar() as conn:

        # =====================================================
        # CREAR TABLA SI NO EXISTE (CON ACTIVO)
        # =====================================================

        conn.execute("""

        CREATE TABLE IF NOT EXISTS proveedores (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            nombre TEXT UNIQUE,

            telefono TEXT,

            rif TEXT,

            contacto TEXT,

            observaciones TEXT,

            activo INTEGER DEFAULT 1,

            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP

        )

        """)

        conn.commit()


        # =====================================================
        # CREAR PROVEEDOR SEGURO ID 0
        # =====================================================

        existe = conn.execute(

            "SELECT id FROM proveedores WHERE id=0"

        ).fetchone()

        if not existe:

            conn.execute("""

            INSERT OR IGNORE INTO proveedores

            (id,nombre,telefono,rif,contacto,observaciones,activo)

            VALUES

            (0,'SIN PROVEEDOR','','','','',1)

            """)

            conn.commit()


        # =====================================================
        # CARGAR DATAFRAME
        # =====================================================

        df_prov = pd.read_sql("""

            SELECT

            id,

            nombre,

            telefono,

            rif,

            contacto,

            observaciones,

            fecha_creacion

            FROM proveedores

            WHERE activo=1

            ORDER BY nombre ASC

        """, conn)


    # =====================================================
    # BUSCADOR
    # =====================================================

    if df_prov.empty:

        st.info("No hay proveedores registrados todavía.")

    else:

        filtro = st.text_input("🔍 Buscar proveedor")

        df_view = df_prov.copy()

        if filtro:

            df_view = df_view[

                df_view.astype(str)

                .apply(lambda x: x.str.contains(filtro, case=False))

                .any(axis=1)

            ]

        st.dataframe(

            df_view,

            use_container_width=True,

            hide_index=True

        )


    # =====================================================
    # EDITOR
    # =====================================================

    st.divider()

    st.subheader("➕ Registrar / Editar proveedor")


    lista_proveedores = df_prov["nombre"].tolist()


    nombre_edit = st.selectbox(

        "Proveedor",

        ["Nuevo proveedor"] + lista_proveedores

    )


    prov_actual = None

    if nombre_edit != "Nuevo proveedor":

        prov_actual = df_prov[

            df_prov["nombre"] == nombre_edit

        ].iloc[0]


    with st.form("form_proveedor"):

        c1,c2 = st.columns(2)

        nombre = c1.text_input(

            "Nombre",

            value="" if prov_actual is None else prov_actual["nombre"]

        )

        telefono = c2.text_input(

            "Telefono",

            value="" if prov_actual is None else prov_actual["telefono"]

        )


        c3,c4 = st.columns(2)

        rif = c3.text_input(

            "RIF",

            value="" if prov_actual is None else prov_actual["rif"]

        )

        contacto = c4.text_input(

            "Contacto",

            value="" if prov_actual is None else prov_actual["contacto"]

        )


        observaciones = st.text_area(

            "Observaciones",

            value="" if prov_actual is None else prov_actual["observaciones"]

        )


        guardar = st.form_submit_button(

            "💾 Guardar",

            use_container_width=True

        )


    # =====================================================
    # GUARDAR
    # =====================================================

    if guardar:

        if not nombre.strip():

            st.error("Nombre obligatorio")

        else:

            try:

                with conectar() as conn:

                    if prov_actual is None:

                        conn.execute("""

                        INSERT INTO proveedores

                        (nombre,telefono,rif,contacto,observaciones)

                        VALUES (?,?,?,?,?)

                        """,

                        (

                        nombre.strip(),

                        telefono.strip(),

                        rif.strip(),

                        contacto.strip(),

                        observaciones.strip()

                        ))

                    else:

                        conn.execute("""

                        UPDATE proveedores

                        SET

                        nombre=?,

                        telefono=?,

                        rif=?,

                        contacto=?,

                        observaciones=?

                        WHERE id=?

                        """,

                        (

                        nombre.strip(),

                        telefono.strip(),

                        rif.strip(),

                        contacto.strip(),

                        observaciones.strip(),

                        int(prov_actual["id"])

                        ))


                    conn.commit()


                st.success("Proveedor guardado")

                st.rerun()


            except sqlite3.IntegrityError:

                st.error("Proveedor ya existe")


    # =====================================================
    # ELIMINAR
    # =====================================================

    if prov_actual is not None:

        if st.button("🗑 Eliminar proveedor"):


            with conectar() as conn:


                compras = conn.execute(

                    """

                    SELECT COUNT(*)

                    FROM historial_compras

                    WHERE proveedor_id=?

                    """,

                    (int(prov_actual["id"]),)

                ).fetchone()[0]


                if compras > 0:

                    st.error("Tiene compras asociadas")

                else:

                    conn.execute(

                        "UPDATE proveedores SET activo=0 WHERE id=?",

                        (int(prov_actual["id"]),)

                    )

                    conn.commit()


                    st.success("Proveedor eliminado")

                    st.rerun()
    # =======================================================
    # 🔧 TAB 5 — AJUSTES
    # =======================================================
    with tabs[4]:

        st.subheader("🔧 Ajustes del módulo de inventario")
        st.caption("Estos parámetros precargan valores al registrar compras y ayudan al control de inventario.")

        with conectar() as conn:
            cfg_inv = pd.read_sql(
                """
                SELECT parametro, valor
                FROM configuracion
                WHERE parametro IN ('inv_alerta_dias', 'inv_impuesto_default', 'inv_delivery_default')
                """,
                conn
            )

        cfg_map = {row["parametro"]: float(row["valor"]) for _, row in cfg_inv.iterrows()}

        with st.form("form_ajustes_inventario"):
            alerta_dias = st.number_input(
                "Días para alerta de reposición",
                min_value=1,
                max_value=120,
                value=int(cfg_map.get("inv_alerta_dias", 14)),
                help="Referencia para revisar proveedores y planificar compras preventivas."
            )
            impuesto_default = st.number_input(
                "Impuesto por defecto en compras (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(cfg_map.get("inv_impuesto_default", 16.0)),
                format="%.2f"
            )
            delivery_default = st.number_input(
                "Delivery por defecto por compra ($)",
                min_value=0.0,
                value=float(cfg_map.get("inv_delivery_default", 0.0)),
                format="%.2f"
            )

            guardar_ajustes = st.form_submit_button("💾 Guardar ajustes", use_container_width=True)

        if guardar_ajustes:
            with conectar() as conn:
                ajustes = [
                    ("inv_alerta_dias", float(alerta_dias)),
                    ("inv_impuesto_default", float(impuesto_default)),
                    ("inv_delivery_default", float(delivery_default))
                ]
                for parametro, valor in ajustes:
                    conn.execute(
                        "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES (?, ?)",
                        (parametro, valor)
                    )
                conn.commit()

            st.session_state["inv_alerta_dias"] = float(alerta_dias)
            st.session_state["inv_impuesto_default"] = float(impuesto_default)
            st.session_state["inv_delivery_default"] = float(delivery_default)
            st.success("Ajustes de inventario actualizados.")

            c1, c2, c3 = st.columns(3)
            c1.metric("⏱️ Alerta reposición", f"{int(cfg_map.get('inv_alerta_dias', 14))} días")
            c2.metric("🛡️ Impuesto sugerido", f"{cfg_map.get('inv_impuesto_default', 16.0):.2f}%")
            c3.metric("🚚 Delivery sugerido", f"${cfg_map.get('inv_delivery_default', 0.0):.2f}")

 
# --- Kontigo --- #
elif menu == "💳 Kontigo":
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden gestionar Kontigo.")
        st.stop()

    st.title("💳 Control de Cuenta Kontigo")

    pct_ent = float(st.session_state.get('kontigo_perc_entrada', st.session_state.get('kontigo_perc', 5.0)))
    pct_sal = float(st.session_state.get('kontigo_perc_salida', st.session_state.get('kontigo_perc', 5.0)))
    saldo_actual = float(st.session_state.get('kontigo_saldo', 0.0))

    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo actual", f"$ {saldo_actual:,.2f}")
    c2.metric("Comisión Entrada", f"{pct_ent:.2f}%")
    c3.metric("Comisión Salida", f"{pct_sal:.2f}%")

    try:
        with conectar() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kontigo_movs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT,
                    monto_bruto REAL,
                    comision_pct REAL,
                    comision_usd REAL,
                    monto_neto REAL,
                    detalle TEXT,
                    usuario TEXT,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    except Exception as e:
        st.error(f"No se pudo preparar la tabla de Kontigo: {e}")
        st.stop()

    t1, t2 = st.tabs(["➕ Registrar movimiento", "📜 Historial"])

    with t1:
        with st.form("form_kontigo"):
            k1, k2 = st.columns(2)
            tipo = k1.selectbox("Tipo", ["Entrada", "Salida"])
            monto_bruto = k2.number_input("Monto bruto ($)", min_value=0.01, format="%.2f")
            detalle = st.text_input("Detalle", placeholder="Ej: Cobro cliente / Pago proveedor")

            pct = pct_ent if tipo == "Entrada" else pct_sal
            comision = monto_bruto * (pct / 100.0)
            if tipo == "Entrada":
                monto_sin_comision = monto_bruto - comision
                impacto_saldo = monto_sin_comision
                st.info(f"Entrada sin comisión: $ {monto_sin_comision:,.2f}")
            else:
                monto_sin_comision = monto_bruto
                impacto_saldo = -(monto_bruto + comision)
                st.info(f"Salida sin comisión: $ {monto_sin_comision:,.2f}")
                st.warning(f"Salida total descontada de cuenta (con comisión): $ {abs(impacto_saldo):,.2f}")

            nuevo_saldo = saldo_actual + impacto_saldo
            st.metric("Saldo luego de registrar", f"$ {nuevo_saldo:,.2f}")

            if st.form_submit_button("💾 Registrar movimiento", use_container_width=True):
                try:
                    with conectar() as conn:
                        conn.execute(
                            """
                            INSERT INTO kontigo_movs
                            (tipo, monto_bruto, comision_pct, comision_usd, monto_neto, detalle, usuario)
                            VALUES (?,?,?,?,?,?,?)
                            """,
                            (
                                tipo,
                                float(monto_bruto),
                                float(pct),
                                float(comision),
                                float(impacto_saldo),
                                detalle.strip() if detalle else "",
                                st.session_state.get("usuario_nombre", "Sistema")
                            )
                        )
                        conn.execute(
                            "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES (?, ?)",
                            ('kontigo_saldo', float(nuevo_saldo))
                        )
                        conn.commit()
                    st.session_state.kontigo_saldo = float(nuevo_saldo)
                    st.success("Movimiento registrado en Kontigo")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar movimiento: {e}")

    with t2:
        try:
            with conectar() as conn:
                df_k = pd.read_sql_query(
                    "SELECT fecha, tipo, monto_bruto, comision_pct, comision_usd, monto_neto, detalle, usuario FROM kontigo_movs ORDER BY fecha DESC LIMIT 200",
                    conn
                )
            if df_k.empty:
                st.info("No hay movimientos de Kontigo aún.")
            else:
                st.dataframe(df_k, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error cargando historial de Kontigo: {e}")

# --- configuracion --- #
elif menu == "⚙️ Configuración":

    # --- SEGURIDAD DE ACCESO ---
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Acceso Denegado. Solo la Jefa o Administración pueden cambiar tasas y costos.")
        st.stop()

    st.title("⚙️ Configuración del Sistema")
    st.info("💡 Estos valores afectan globalmente a cotizaciones, inventario y reportes financieros.")

    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    # --- CARGA SEGURA DE CONFIGURACIÓN ---
    try:
        with conectar() as conn:
            conf_df = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')
    except Exception as e:
        st.error(f"Error al cargar configuración: {e}")
        st.stop()

    # Función auxiliar para obtener valores seguros
    def get_conf(key, default):
        try:
            return float(conf_df.loc[key, 'valor'])
        except Exception:
            return default

    costo_tinta_detectado = None
    try:
        with conectar() as conn:
            df_tintas_cfg = pd.read_sql(
                """
                SELECT item, COALESCE(costo_real_ml, precio_usd) AS precio_usd
                FROM inventario
                WHERE item LIKE '%tinta%'
                  AND (precio_usd IS NOT NULL OR costo_real_ml IS NOT NULL)
                  AND lower(trim(COALESCE(unidad, ''))) = 'ml'
                """,
                conn
            )
        if not df_tintas_cfg.empty:
            df_tintas_cfg = df_tintas_cfg[df_tintas_cfg['precio_usd'] > 0]
            if not df_tintas_cfg.empty:
                costo_tinta_detectado = float(df_tintas_cfg['precio_usd'].mean())
    except Exception:
        costo_tinta_detectado = None

    with st.form("config_general"):

        st.subheader("💵 Tasas de Cambio (Actualización Diaria)")
        c1, c2 = st.columns(2)

        nueva_bcv = c1.number_input(
            "Tasa BCV (Bs/$)",
            value=get_conf('tasa_bcv', 36.5),
            format="%.2f",
            help="Usada para pagos en bolívares de cuentas nacionales."
        )

        nueva_bin = c2.number_input(
            "Tasa Binance (Bs/$)",
            value=get_conf('tasa_binance', 38.0),
            format="%.2f",
            help="Usada para pagos mediante USDT o mercado paralelo."
        )

        st.divider()

        st.subheader("🎨 Costos Operativos Base")

        costo_tinta_auto = st.checkbox(
            "Calcular costo de tinta automáticamente desde Inventario",
            value=bool(get_conf('costo_tinta_auto', 1.0))
        )

        if costo_tinta_auto:
            if costo_tinta_detectado is not None:
                costo_tinta = float(costo_tinta_detectado)
                st.success(f"💧 Costo detectado desde inventario: ${costo_tinta:.4f}/ml")
            else:
                costo_tinta = float(get_conf('costo_tinta_ml', 0.10))
                st.warning("No se detectaron tintas válidas en inventario; se mantendrá el último costo guardado.")
        else:
            costo_tinta = st.number_input(
                "Costo de Tinta por ml ($)",
                value=get_conf('costo_tinta_ml', 0.10),
                format="%.4f",
                step=0.0001
            )

        st.divider()

        st.subheader("🛡️ Impuestos y Comisiones")
        st.caption("Define los porcentajes numéricos (Ej: 16 para 16%)")

        c3, c4, c5, c6, c7 = st.columns(5)

        n_iva = c3.number_input(
            "IVA (%)",
            value=get_conf('iva_perc', 16.0),
            format="%.2f"
        )

        n_igtf = c4.number_input(
            "IGTF (%)",
            value=get_conf('igtf_perc', 3.0),
            format="%.2f"
        )

        n_banco = c5.number_input(
            "Comisión Bancaria (%)",
            value=get_conf('banco_perc', 0.5),
            format="%.3f"
        )

        n_kontigo = c6.number_input(
            "Comisión Kontigo (%)",
            value=get_conf('kontigo_perc', 5.0),
            format="%.3f"
        )
        n_kontigo_ent = c7.number_input(
            "Kontigo Entrada (%)",
            value=get_conf('kontigo_perc_entrada', get_conf('kontigo_perc', 5.0)),
            format="%.3f"
        )

        c8, c9 = st.columns(2)
        n_kontigo_sal = c8.number_input(
            "Kontigo Salida (%)",
            value=get_conf('kontigo_perc_salida', get_conf('kontigo_perc', 5.0)),
            format="%.3f"
        )
        n_kontigo_saldo = c9.number_input(
            "Saldo Cuenta Kontigo ($)",
            value=get_conf('kontigo_saldo', 0.0),
            format="%.2f"
        )

        c10, c11, c12, c13, c14 = st.columns(5)
        n_factor_desperdicio = c10.number_input("Factor desperdicio CMYK", value=get_conf('factor_desperdicio_cmyk', 1.15), format='%.3f')
        n_desgaste_cabezal = c11.number_input("Desgaste cabezal por ml ($)", value=get_conf('desgaste_cabezal_ml', 0.005), format='%.4f')
        n_bajada_plancha = c12.number_input("Bajada de plancha ($/u)", value=get_conf('costo_bajada_plancha', 0.03), format='%.2f')
        n_recargo_urg = c13.selectbox("Recargo urgencia global", [0.0, 25.0, 50.0], index=[0.0,25.0,50.0].index(get_conf('recargo_urgente_pct',0.0)) if get_conf('recargo_urgente_pct',0.0) in [0.0,25.0,50.0] else 0)
        n_limpieza_cabezal = c14.number_input("Costo limpieza cabezal por trabajo ($)", value=get_conf('costo_limpieza_cabezal', 0.02), format='%.2f')

        st.divider()

        # --- GUARDADO CON HISTORIAL ---
        if st.form_submit_button("💾 GUARDAR CAMBIOS ATÓMICOS", use_container_width=True):

            actualizaciones = [
                ('tasa_bcv', nueva_bcv),
                ('tasa_binance', nueva_bin),
                ('costo_tinta_ml', costo_tinta),
                ('costo_tinta_auto', 1.0 if costo_tinta_auto else 0.0),
                ('iva_perc', n_iva),
                ('igtf_perc', n_igtf),
                ('banco_perc', n_banco),
                ('kontigo_perc', n_kontigo),
                ('kontigo_perc_entrada', n_kontigo_ent),
                ('kontigo_perc_salida', n_kontigo_sal),
                ('kontigo_saldo', n_kontigo_saldo),
                ('factor_desperdicio_cmyk', n_factor_desperdicio),
                ('desgaste_cabezal_ml', n_desgaste_cabezal),
                ('costo_bajada_plancha', n_bajada_plancha),
                ('recargo_urgente_pct', n_recargo_urg),
                ('costo_limpieza_cabezal', n_limpieza_cabezal)
            ]

            try:
                with conectar() as conn:
                    cur = conn.cursor()

                    # Crear tabla de historial si no existe
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS historial_config (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            parametro TEXT,
                            valor_anterior REAL,
                            valor_nuevo REAL,
                            usuario TEXT,
                            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Guardar cambios y registrar historial
                    for param, val in actualizaciones:

                        try:
                            val_anterior = float(conf_df.loc[param, 'valor'])
                        except Exception:
                            val_anterior = None

                        cur.execute(
                            "UPDATE configuracion SET valor = ? WHERE parametro = ?",
                            (val, param)
                        )

                        if val_anterior != val:
                            cur.execute("""
                                INSERT INTO historial_config
                                (parametro, valor_anterior, valor_nuevo, usuario)
                                VALUES (?,?,?,?)
                            """, (param, val_anterior, val, usuario_actual))

                    conn.commit()

                # Actualización inmediata en memoria
                st.session_state.tasa_bcv = nueva_bcv
                st.session_state.tasa_binance = nueva_bin
                st.session_state.costo_tinta_ml = costo_tinta
                st.session_state.costo_tinta_auto = 1.0 if costo_tinta_auto else 0.0
                st.session_state.iva_perc = n_iva
                st.session_state.igtf_perc = n_igtf
                st.session_state.banco_perc = n_banco
                st.session_state.kontigo_perc = n_kontigo
                st.session_state.kontigo_perc_entrada = n_kontigo_ent
                st.session_state.kontigo_perc_salida = n_kontigo_sal
                st.session_state.kontigo_saldo = n_kontigo_saldo
                st.session_state.recargo_urgente_pct = n_recargo_urg

                st.success("✅ ¡Configuración actualizada y registrada en historial!")
                st.balloons()
                st.rerun()

            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    st.subheader("📋 Tabla de Control (Tasas, Impuestos y Comisiones)")
    tabla_cfg = pd.DataFrame([
        {"Concepto": "Tasa BCV (Bs/$)", "Valor": get_conf('tasa_bcv', 36.5)},
        {"Concepto": "Tasa Binance (Bs/$)", "Valor": get_conf('tasa_binance', 38.0)},
        {"Concepto": "IVA (%)", "Valor": get_conf('iva_perc', 16.0)},
        {"Concepto": "IGTF (%)", "Valor": get_conf('igtf_perc', 3.0)},
        {"Concepto": "Comisión Bancaria (%)", "Valor": get_conf('banco_perc', 0.5)},
        {"Concepto": "Comisión Kontigo (%)", "Valor": get_conf('kontigo_perc', 5.0)},
        {"Concepto": "Kontigo Entrada (%)", "Valor": get_conf('kontigo_perc_entrada', get_conf('kontigo_perc', 5.0))},
        {"Concepto": "Kontigo Salida (%)", "Valor": get_conf('kontigo_perc_salida', get_conf('kontigo_perc', 5.0))},
        {"Concepto": "Saldo Cuenta Kontigo ($)", "Valor": get_conf('kontigo_saldo', 0.0)},
        {"Concepto": "Costo Tinta por ml ($)", "Valor": get_conf('costo_tinta_ml', 0.10)}
    ])
    st.dataframe(tabla_cfg, use_container_width=True, hide_index=True)

    # --- VISUALIZAR HISTORIAL DE CAMBIOS ---
    with st.expander("📜 Ver Historial de Cambios"):

        try:
            with conectar() as conn:
                df_hist = pd.read_sql("""
                    SELECT fecha, parametro, valor_anterior, valor_nuevo, usuario
                    FROM historial_config
                    ORDER BY fecha DESC
                    LIMIT 50
                """, conn)

            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("Aún no hay cambios registrados.")

        except Exception:
            st.info("Historial aún no disponible.")

# ============================================================
# 👥 MODULO CLIENTES ERP PRO v7.0 ULTRA ROBUSTO
# Sin errores IndexError • Nivel Producción Real
# ============================================================

elif menu == "👥 Clientes":

    import streamlit as st
    import pandas as pd
    import numpy as np
    import plotly.express as px
    import io
    from datetime import datetime


    st.title("👥 CRM Profesional de Clientes")
    st.caption("ERP • Finanzas • Inteligencia Comercial")


    # =====================================================
    # CARGA SEGURA
    # =====================================================

    @st.cache_data(ttl=300)
    def cargar_clientes():

        query = """

        SELECT

        c.id,
        c.nombre,
        c.whatsapp,
        COALESCE(c.categoria,'General') categoria,

        COUNT(v.id) operaciones,

        COALESCE(SUM(v.monto_total),0) total,

        COALESCE(SUM(

            CASE

                WHEN v.metodo LIKE '%Pendiente%'
                OR v.metodo LIKE '%Deuda%'

                THEN v.monto_total
                ELSE 0

            END

        ),0) deuda,

        MAX(v.fecha) ultima_compra

        FROM clientes c

        LEFT JOIN ventas v
        ON v.cliente_id = c.id
        AND COALESCE(v.activo,1)=1

        WHERE COALESCE(c.activo,1)=1

        GROUP BY c.id

        ORDER BY total DESC

        """

        with conectar() as conn:

            return pd.read_sql(query, conn)


    df = cargar_clientes()


    # =====================================================
    # REGISTRAR / EDITAR
    # =====================================================

    st.divider()
    st.subheader("➕ Registro y Edición")


    modo = st.radio(

        "Modo",

        ["Registrar","Editar"],

        horizontal=True

    )


    # REGISTRAR

    if modo == "Registrar":

        with st.form("form_registro"):

            col1,col2,col3 = st.columns(3)

            nombre = col1.text_input("Nombre")

            whatsapp = col2.text_input("WhatsApp")

            categoria = col3.selectbox(

                "Categoria",

                ["General","VIP","Revendedor"]

            )

            guardar = st.form_submit_button("Guardar")


            if guardar:

                if nombre.strip() == "":

                    st.error("Nombre obligatorio")
                    st.stop()


                whatsapp = "".join(filter(str.isdigit, whatsapp))


                with conectar() as conn:

                    existe = conn.execute(

                        "SELECT COUNT(*) FROM clientes WHERE nombre=?",

                        (nombre,)

                    ).fetchone()[0]


                    if existe:

                        st.error("Cliente ya existe")
                        st.stop()


                    conn.execute(

                        """

                        INSERT INTO clientes
                        (nombre, whatsapp, categoria)

                        VALUES (?,?,?)

                        """,

                        (nombre, whatsapp, categoria)

                    )

                    conn.commit()


                st.success("Cliente registrado")
                st.rerun()


    # EDITAR

    else:

        if df.empty:

            st.info("No hay clientes")
            st.stop()


        lista = df[["id","nombre"]]

        cliente_id = st.selectbox(

            "Seleccionar",

            lista["id"],

            format_func=lambda x: lista.loc[
                lista["id"]==x,"nombre"
            ].values[0]

        )


        cliente_df = df[df["id"]==cliente_id]

        if cliente_df.empty:

            st.stop()


        row = cliente_df.iloc[0]


        with st.form("form_editar"):

            col1,col2,col3 = st.columns(3)

            nombre_n = col1.text_input("Nombre",row["nombre"])

            whatsapp_n = col2.text_input("WhatsApp",row["whatsapp"])

            categoria_n = col3.selectbox(

                "Categoria",

                ["General","VIP","Revendedor"],

                index=["General","VIP","Revendedor"].index(row["categoria"])

            )


            actualizar = st.form_submit_button("Actualizar")


            if actualizar:

                with conectar() as conn:

                    conn.execute(

                        """

                        UPDATE clientes

                        SET nombre=?,
                        whatsapp=?,
                        categoria=?

                        WHERE id=?

                        """,

                        (

                            nombre_n,
                            whatsapp_n,
                            categoria_n,
                            int(cliente_id)

                        )

                    )

                    conn.commit()


                st.success("Cliente actualizado")
                st.rerun()


    # =====================================================
    # ANALISIS
    # =====================================================

    if df.empty:

        st.warning("Sin clientes")
        st.stop()


    df["ultima_compra"] = pd.to_datetime(df["ultima_compra"])


    df["recencia"] = (

        datetime.now() - df["ultima_compra"]

    ).dt.days


    df["score"] = (

        df["total"] * 0.5 +
        df["operaciones"] * 10 +
        (100 - df["recencia"].fillna(100))

    )


    df["segmento"] = np.select(

        [

            df["score"] > 1000,
            df["score"] > 500,
            df["score"] > 200

        ],

        [

            "VIP",
            "Frecuente",
            "Ocasional"

        ],

        default="Riesgo"

    )


    # =====================================================
    # DASHBOARD
    # =====================================================

    st.divider()

    c1,c2,c3,c4 = st.columns(4)

    c1.metric("Clientes",len(df))

    c2.metric("Ventas",f"$ {df['total'].sum():,.2f}")

    c3.metric("Deuda",f"$ {df['deuda'].sum():,.2f}")

    c4.metric(

        "Ticket",

        f"$ {(df['total'].sum()/df['operaciones'].sum()):,.2f}"

    )


    # =====================================================
    # GRAFICO
    # =====================================================

    fig = px.bar(

        df.head(10),

        x="nombre",

        y="total",

        color="segmento"

    )

    st.plotly_chart(fig,use_container_width=True)


    # =====================================================
    # EXPORTAR
    # =====================================================

    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer):

        df.to_excel(buffer,index=False)

    st.download_button(

        "📥 Exportar Excel",

        buffer.getvalue(),

        "clientes.xlsx"

    )


    # =====================================================
    # TABLA
    # =====================================================

    st.dataframe(df,use_container_width=True)


    # =====================================================
    # CONTACTO SEGURO
    # =====================================================

    st.subheader("Contacto")


    lista = df[["id","nombre"]]


    cliente_id = st.selectbox(

        "Seleccionar cliente",

        lista["id"],

        format_func=lambda x: lista.loc[
            lista["id"]==x,"nombre"
        ].values[0],

        key="contacto"

    )


    row = df[df["id"]==cliente_id].iloc[0]


    if pd.notna(row["whatsapp"]):

        wa = "".join(filter(str.isdigit,str(row["whatsapp"])))

        if not wa.startswith("58"):

            wa="58"+wa


        st.link_button(

            "💬 WhatsApp",

            f"https://wa.me/{wa}"

        )


    # =====================================================
    # ELIMINAR
    # =====================================================

    if st.button("🗑 Eliminar Cliente"):

        with conectar() as conn:

            conn.execute(

                "UPDATE clientes SET activo=0 WHERE id=?",

                (int(cliente_id),)

            )

            conn.commit()


        st.success("Cliente eliminado")
        st.rerun()
# ===========================================================
# 10. ANALIZADOR CMYK PROFESIONAL (VERSIÓN MEJORADA 2.0)
# ===========================================================
elif menu == "🎨 Análisis CMYK":

    st.title("🎨 Analizador Profesional de Cobertura CMYK")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:

            # Usamos el inventario como fuente de tintas
            cols_inv_mod = {r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}
            q_inv_mod = "SELECT * FROM inventario"
            if 'activo' in cols_inv_mod:
                q_inv_mod += " WHERE COALESCE(activo,1)=1"
            df_tintas_db = pd.read_sql_query(q_inv_mod, conn)
            if 'imprimible_cmyk' in df_tintas_db.columns:
                df_impresion_db = df_tintas_db[df_tintas_db['imprimible_cmyk'].fillna(0) == 1].copy()
            else:
                df_impresion_db = df_tintas_db.copy()
            try:
                cols_act = {r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()}
                campo_equipo = 'equipo' if 'equipo' in cols_act else ('nombre' if 'nombre' in cols_act else None)
                if cols_act and 'id' in cols_act and campo_equipo:
                    campos = ['id', campo_equipo]
                    if 'categoria' in cols_act:
                        campos.append('categoria')
                    if 'unidad' in cols_act:
                        campos.append('unidad')
                    if 'modelo' in cols_act:
                        campos.append('modelo')
                    q_act = "SELECT " + ", ".join(campos) + " FROM activos"
                    if 'activo' in cols_act:
                        q_act += " WHERE COALESCE(activo,1)=1"
                    df_activos_cmyk = pd.read_sql_query(q_act, conn)
                    if campo_equipo != 'equipo':
                        df_activos_cmyk = df_activos_cmyk.rename(columns={campo_equipo: 'equipo'})
                    for col in ['categoria', 'unidad', 'modelo']:
                        if col not in df_activos_cmyk.columns:
                            df_activos_cmyk[col] = ''
                else:
                    df_activos_cmyk = pd.DataFrame(columns=['id', 'equipo', 'categoria', 'unidad', 'modelo'])
            except Exception:
                df_activos_cmyk = pd.DataFrame(columns=['id', 'equipo', 'categoria', 'unidad', 'modelo'])

            # Tabla histórica
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial_cmyk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    impresora TEXT,
                    paginas INTEGER,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            df_hist_cmyk = pd.read_sql(
                "SELECT fecha, impresora, paginas, costo FROM historial_cmyk ORDER BY fecha DESC LIMIT 100",
                conn
            )

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # --- LISTA DE IMPRESORAS DISPONIBLES ---
    impresoras_disponibles = []

    # 1) Prioridad: todos los activos de impresión registrados por el usuario
    if 'df_activos_cmyk' in locals() and not df_activos_cmyk.empty and 'equipo' in df_activos_cmyk.columns:
        posibles_activos = (
            df_activos_cmyk['equipo']
            .dropna()
            .astype(str)
            .str.strip()
            .replace('', np.nan)
            .dropna()
            .tolist()
        )
        for eq in posibles_activos:
            if eq not in impresoras_disponibles:
                impresoras_disponibles.append(eq)

    # 2) Fallback: equipos con palabra impresora en inventario
    if not df_impresion_db.empty:
        posibles = df_impresion_db[
            df_impresion_db['item'].str.contains("impresora", case=False, na=False)
        ]['item'].tolist()

        for p in posibles:
            if p not in impresoras_disponibles:
                impresoras_disponibles.append(p)

    # 3) Último fallback por defecto
    if not impresoras_disponibles:
        impresoras_disponibles = ["Impresora Principal", "Impresora Secundaria"]

    # --- VALIDACIÓN ---
    if not impresoras_disponibles:
        st.warning("⚠️ No hay impresoras registradas en el sistema.")
        st.stop()

    # --- SELECCIÓN DE IMPRESORA Y ARCHIVOS ---
    c_printer, c_file = st.columns([1, 2])

    with c_printer:

        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)

        impresora_aliases = [impresora_sel.lower().strip()]
        if ' ' in impresora_aliases[0]:
            impresora_aliases.extend([x for x in impresora_aliases[0].split(' ') if len(x) > 2])

        usar_stock_por_impresora = st.checkbox(
            "Usar tintas del inventario solo de esta impresora",
            value=True,
            help="Actívalo si registras tintas separadas por impresora en inventario."
        )
        auto_negro_inteligente = st.checkbox(
            "Conteo automático inteligente de negro (sombras y mezclas)",
            value=True,
            help="Detecta zonas oscuras y mezclas ricas para sumar consumo real de tinta negra (K)."
        )

        # Mantener separador decimal estilo Python (.) para evitar SyntaxError por locales con coma.
        step_desgaste = 0.005
        step_base_ml = 0.01

        costo_desgaste = st.number_input(
            "Costo desgaste por página ($)",
            min_value=0.0,
            value=0.02,
            step=step_desgaste,
            format="%.3f"
        )
        ml_base_pagina = st.number_input(
            "Consumo base por página a cobertura 100% (ml)",
            min_value=0.01,
            value=0.15,
            step=step_base_ml,
            format="%.3f"
        )

        precio_tinta_ml = float(st.session_state.get('costo_tinta_ml', 0.10))
        costo_limpieza_cabezal = float(st.session_state.get('costo_limpieza_cabezal', 0.02))

        with conectar() as conn:
            tintas_vinculadas = obtener_tintas_impresora(conn, impresora_sel)

        if tintas_vinculadas is not None and not tintas_vinculadas.empty:
            if 'costo_real_ml' in tintas_vinculadas.columns:
                costos_ml = pd.to_numeric(tintas_vinculadas['costo_real_ml'], errors='coerce').dropna()
                costos_ml = costos_ml[costos_ml > 0]
            else:
                costos_ml = pd.Series(dtype=float)

            if costos_ml.empty:
                precios_validos = pd.to_numeric(tintas_vinculadas['precio_usd'], errors='coerce').dropna()
                precios_validos = precios_validos[precios_validos > 0]
                if not precios_validos.empty:
                    precio_tinta_ml = float(precios_validos.mean())
            else:
                precio_tinta_ml = float(costos_ml.mean())

            st.success(f"💧 Costo dinámico tinta ({impresora_sel}): ${precio_tinta_ml:.4f}/ml")
            st.caption(f"Tintas vinculadas detectadas: {len(tintas_vinculadas)}")
        else:
            st.info("No se encontró vínculo activo-insumo; se usa costo global configurado.")

        consumos_ids_cmyk = mapear_consumos_cmyk_a_inventario({}, tintas_vinculadas if 'tintas_vinculadas' in locals() else pd.DataFrame())

        st.subheader("⚙️ Ajustes de Calibración")

        factor = st.slider(
            "Factor General de Consumo",
            1.0, 3.0, 1.5, 0.1,
            help="Ajuste global según rendimiento real de la impresora"
        )

        factor_k = 0.8
        refuerzo_negro = 0.06
        if auto_negro_inteligente:
            st.success("🧠 Modo automático de negro activo: se detectan sombras y mezclas con negro en cada página.")
        else:
            factor_k = st.slider(
                "Factor Especial para Negro (K)",
                0.5, 1.2, 0.8, 0.05,
                help="Modo manual: ajusta consumo base del negro."
            )
            refuerzo_negro = st.slider(
                "Refuerzo de Negro en Mezclas Oscuras",
                0.0, 0.2, 0.06, 0.01,
                help="Modo manual: simula uso extra de K en sombras."
            )

    with c_file:
        archivos_multiples = st.file_uploader(
            "Carga tus diseños",
            type=['pdf', 'png', 'jpg', 'jpeg'],
            accept_multiple_files=True
        )

    if not archivos_multiples and 'cmyk_analisis_cache' in st.session_state:
        st.session_state.pop('cmyk_analisis_cache', None)

    # --- PROCESAMIENTO ---
    if archivos_multiples:

        try:
            import fitz  # PyMuPDF (opcional para PDF)
        except ModuleNotFoundError:
            fitz = None

        resultados = []
        totales_lote_cmyk = {'C': 0.0, 'M': 0.0, 'Y': 0.0, 'K': 0.0}
        total_pags = 0

        with st.spinner('🚀 Analizando cobertura real...'):

            for arc in archivos_multiples:

                try:
                    paginas_items = []
                    bytes_data = arc.read()

                    if arc.name.lower().endswith('.pdf'):

                        if fitz is None:
                            st.error(
                                f"No se puede analizar '{arc.name}' porque falta PyMuPDF (fitz). "
                                "Carga imágenes (PNG/JPG) o instala la dependencia para PDF."
                            )
                            continue

                        doc = fitz.open(stream=bytes_data, filetype="pdf")

                        for i in range(len(doc)):
                            page = doc.load_page(i)

                            pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)

                            img = Image.frombytes(
                                "CMYK",
                                [pix.width, pix.height],
                                pix.samples
                            )

                            paginas_items.append((f"{arc.name} (P{i+1})", img))

                        doc.close()

                    else:
                        img = Image.open(io.BytesIO(bytes_data)).convert('CMYK')
                        paginas_items.append((arc.name, img))

                    for nombre, img_obj in paginas_items:

                        total_pags += 1
                        arr = np.array(img_obj)

                        c_chan = arr[:, :, 0] / 255.0
                        m_chan = arr[:, :, 1] / 255.0
                        y_chan = arr[:, :, 2] / 255.0
                        k_chan = arr[:, :, 3] / 255.0

                        c_media = float(np.mean(c_chan))
                        m_media = float(np.mean(m_chan))
                        y_media = float(np.mean(y_chan))
                        k_media = float(np.mean(k_chan))

                        ml_c = c_media * ml_base_pagina * factor
                        ml_m = m_media * ml_base_pagina * factor
                        ml_y = y_media * ml_base_pagina * factor

                        ml_k_base = k_media * ml_base_pagina * factor * factor_k
                        k_extra_ml = 0.0

                        if auto_negro_inteligente:
                            cobertura_cmy = (c_chan + m_chan + y_chan) / 3.0
                            neutral_mask = (
                                (np.abs(c_chan - m_chan) < 0.08)
                                & (np.abs(m_chan - y_chan) < 0.08)
                            )
                            shadow_mask = (k_chan > 0.45) | (cobertura_cmy > 0.60)
                            rich_black_mask = shadow_mask & (cobertura_cmy > 0.35)

                            ratio_extra = (
                                float(np.mean(shadow_mask)) * 0.12
                                + float(np.mean(neutral_mask)) * 0.10
                                + float(np.mean(rich_black_mask)) * 0.18
                            )
                            k_extra_ml = ml_base_pagina * factor * ratio_extra
                        else:
                            promedio_color = (c_media + m_media + y_media) / 3
                            if promedio_color > 0.55:
                                k_extra_ml = promedio_color * refuerzo_negro * factor

                        ml_k = ml_k_base + k_extra_ml
                        consumo_total_f = ml_c + ml_m + ml_y + ml_k
                        factor_desperdicio = float(st.session_state.get('factor_desperdicio_cmyk', 1.15))
                        desgaste_cabezal_ml = float(st.session_state.get('desgaste_cabezal_ml', 0.005))
                        consumo_total_ajustado = consumo_total_f * max(1.0, factor_desperdicio)

                        costo_limpieza_prorrateado = (costo_limpieza_cabezal / max(1, len(paginas_items)))
                        costo_f = (consumo_total_ajustado * precio_tinta_ml) + costo_desgaste + (consumo_total_ajustado * desgaste_cabezal_ml) + costo_limpieza_prorrateado

                        totales_lote_cmyk['C'] += ml_c
                        totales_lote_cmyk['M'] += ml_m
                        totales_lote_cmyk['Y'] += ml_y
                        totales_lote_cmyk['K'] += ml_k

                        resultados.append({
                            "Archivo": nombre,
                            "C (ml)": round(ml_c, 4),
                            "M (ml)": round(ml_m, 4),
                            "Y (ml)": round(ml_y, 4),
                            "K (ml)": round(ml_k, 4),
                            "K extra auto (ml)": round(k_extra_ml, 4),
                            "Total ml": round(consumo_total_ajustado, 4),
                            "Costo $": round(costo_f, 4)
                        })

                except Exception as e:
                    st.error(f"Error analizando {arc.name}: {e}")

        # --- RESULTADOS ---
        if resultados:

            st.subheader("📋 Desglose por Archivo")
            st.dataframe(pd.DataFrame(resultados), use_container_width=True)

            st.subheader("🧪 Consumo Total de Tintas")

            col_c, col_m, col_y, col_k = st.columns(4)

            col_c.metric("Cian", f"{totales_lote_cmyk['C']:.3f} ml")
            col_m.metric("Magenta", f"{totales_lote_cmyk['M']:.3f} ml")
            col_y.metric("Amarillo", f"{totales_lote_cmyk['Y']:.3f} ml")
            col_k.metric("Negro", f"{totales_lote_cmyk['K']:.3f} ml")

            st.divider()

            total_usd_lote = sum(r['Costo $'] for r in resultados)

            costo_promedio_pagina = (total_usd_lote / total_pags) if total_pags > 0 else 0
            st.metric(
                "💰 Costo Total Estimado de Producción",
                f"$ {total_usd_lote:.2f}",
                delta=f"$ {costo_promedio_pagina:.4f} por pág"
            )

            st.subheader("🚀 Inteligencia de Producción CMYK")
            k1, k2, k3 = st.columns(3)
            ml_por_pagina = (float(sum(totales_lote_cmyk.values())) / float(total_pags)) if total_pags else 0.0
            paginas_por_dolar = (float(total_pags) / float(total_usd_lote)) if total_usd_lote > 0 else 0.0
            peso_negro = (totales_lote_cmyk['K'] / float(sum(totales_lote_cmyk.values()))) if sum(totales_lote_cmyk.values()) > 0 else 0.0
            k1.metric("Consumo promedio", f"{ml_por_pagina:.4f} ml/pág")
            k2.metric("Rendimiento", f"{paginas_por_dolar:.2f} pág/$")
            k3.metric("Participación K", f"{peso_negro * 100:.1f}%")

            if costo_promedio_pagina > 0.35:
                st.warning("Costo por página alto: considera calidad 'Normal/Borrador' o papel de menor costo para mejorar margen.")
            elif peso_negro > 0.55:
                st.info("Dominio de negro detectado: revisa modo escala de grises para reducir mezcla de color innecesaria.")
            else:
                st.success("Parámetros de consumo estables para producción continua.")

            with st.expander("💸 Precio sugerido rápido", expanded=False):
                margen_objetivo = st.slider("Margen objetivo (%)", min_value=10, max_value=120, value=35, step=5, key='cmyk_margen_obj')
                sugerido = simular_ganancia_pre_impresion(total_usd_lote, margen_objetivo)
                s1, s2 = st.columns(2)
                s1.metric("Precio sugerido", f"$ {sugerido['precio_sugerido']:.2f}")
                s2.metric("Ganancia estimada", f"$ {sugerido['ganancia_estimada']:.2f}")


            
            df_totales = pd.DataFrame([
                {"Color": "C", "ml": totales_lote_cmyk['C']},
                {"Color": "M", "ml": totales_lote_cmyk['M']},
                {"Color": "Y", "ml": totales_lote_cmyk['Y']},
                {"Color": "K", "ml": totales_lote_cmyk['K']}
            ])
            fig_cmyk = px.pie(df_totales, names='Color', values='ml', title='Distribución de consumo CMYK')
            st.plotly_chart(fig_cmyk, use_container_width=True)

            df_resultados = pd.DataFrame(resultados)
            st.download_button(
                "📥 Descargar desglose CMYK (CSV)",
                data=df_resultados.to_csv(index=False).encode('utf-8'),
                file_name="analisis_cmyk.csv",
                mime="text/csv"
            )

            # --- COSTEO AUTOMÁTICO POR PAPEL Y CALIDAD ---
            st.subheader("🧾 Simulación automática por Papel y Calidad")
            # Papeles desde inventario (precio_usd) con fallback por defecto
            perfiles_papel = {}
            try:
                papeles_inv = df_impresion_db[
                    df_impresion_db['item'].fillna('').str.contains(
                        'papel|bond|fotograf|cartulina|adhesivo|opalina|sulfato',
                        case=False,
                        na=False
                    )
                ][['item', 'precio_usd']].dropna(subset=['precio_usd'])

                for _, row_p in papeles_inv.iterrows():
                    nombre_p = str(row_p['item']).strip()
                    precio_p = float(row_p['precio_usd'])
                    if precio_p > 0:
                        perfiles_papel[nombre_p] = precio_p
            except Exception:
                perfiles_papel = {}

            if not perfiles_papel:
                perfiles_papel = {
                    "Bond 75g": 0.03,
                    "Bond 90g": 0.05,
                    "Fotográfico Brillante": 0.22,
                    "Fotográfico Mate": 0.20,
                    "Cartulina": 0.12,
                    "Adhesivo": 0.16
                }
                st.info("No se detectaron papeles en inventario; se usan costos base por defecto.")
            else:
                st.success("📄 Costos de papeles detectados automáticamente desde inventario.")
            perfiles_calidad = {
                "Borrador": {"ink_mult": 0.82, "wear_mult": 0.90},
                "Normal": {"ink_mult": 1.00, "wear_mult": 1.00},
                "Alta": {"ink_mult": 1.18, "wear_mult": 1.10},
                "Foto": {"ink_mult": 1.32, "wear_mult": 1.15}
            }

            total_ml_lote = float(sum(totales_lote_cmyk.values()))
            costo_tinta_base = total_ml_lote * float(precio_tinta_ml)
            costo_desgaste_base = float(costo_desgaste) * float(total_pags)

            simulaciones = []
            for papel, costo_hoja in perfiles_papel.items():
                for calidad, cfg_q in perfiles_calidad.items():
                    costo_tinta_q = costo_tinta_base * cfg_q['ink_mult']
                    costo_desgaste_q = costo_desgaste_base * cfg_q['wear_mult']
                    costo_papel_q = float(total_pags) * costo_hoja
                    total_q = costo_tinta_q + costo_desgaste_q + costo_papel_q
                    simulaciones.append({
                        "Papel": papel,
                        "Calidad": calidad,
                        "Páginas": total_pags,
                        "Tinta ($)": round(costo_tinta_q, 2),
                        "Desgaste ($)": round(costo_desgaste_q, 2),
                        "Papel ($)": round(costo_papel_q, 2),
                        "Total ($)": round(total_q, 2),
                        "Costo por pág ($)": round(total_q / total_pags, 4) if total_pags else 0
                    })

            df_sim = pd.DataFrame(simulaciones).sort_values('Total ($)')
            st.dataframe(df_sim, use_container_width=True, hide_index=True)
            fig_sim = px.bar(df_sim.head(12), x='Papel', y='Total ($)', color='Calidad', barmode='group', title='Comparativo de costos (top 12 más económicos)')
            st.plotly_chart(fig_sim, use_container_width=True)

            mejor = df_sim.iloc[0]
            st.success(
                f"Mejor costo automático: {mejor['Papel']} | {mejor['Calidad']} → ${mejor['Total ($)']:.2f} "
                f"(${mejor['Costo por pág ($)']:.4f}/pág)"
            )

            st.session_state['cmyk_analisis_cache'] = {
                'resultados': resultados,
                'simulaciones': simulaciones,
                'impresora': impresora_sel,
                'paginas': total_pags
            }

            # --- VERIFICAR INVENTARIO ---
            if not df_impresion_db.empty:

                st.subheader("📦 Verificación de Inventario")

                alertas = []

                stock_base = tintas_vinculadas.copy() if 'tintas_vinculadas' in locals() and tintas_vinculadas is not None else pd.DataFrame()
                if stock_base.empty:
                    stock_base = df_impresion_db[
                        df_impresion_db['item'].str.contains('tinta', case=False, na=False)
                    ].copy()

                consumos_val_stock = mapear_consumos_cmyk_a_inventario(totales_lote_cmyk, stock_base)

                if consumos_val_stock:
                    for item_id, ml_req in consumos_val_stock.items():
                        fila = stock_base[stock_base['id'] == int(item_id)] if 'id' in stock_base.columns else pd.DataFrame()
                        if fila.empty:
                            alertas.append(f"⚠️ No se encontró inventario ID {item_id} para validar stock.")
                            continue

                        disponible = float(pd.to_numeric(fila['cantidad'], errors='coerce').fillna(0.0).sum())
                        if float(ml_req) > disponible:
                            nombre_tinta = str(fila.iloc[0].get('item', f'ID {item_id}'))
                            alertas.append(
                                f"⚠️ Stock insuficiente para {nombre_tinta}: necesitas {float(ml_req):.2f} ml y hay {disponible:.2f} ml"
                            )
                else:
                    alias_colores = {
                        'C': ['cian', 'cyan'],
                        'M': ['magenta'],
                        'Y': ['amarillo', 'yellow'],
                        'K': ['negro', 'negra', 'black', ' k ']
                    }

                    for color, ml in totales_lote_cmyk.items():
                        aliases = alias_colores.get(color, [])
                        stock = stock_base[
                            (" " + stock_base['item'].fillna('').str.lower() + " ").str.contains(
                                '|'.join(aliases), case=False, na=False
                            )
                        ] if aliases else pd.DataFrame()

                        if not stock.empty:
                            disponible = float(pd.to_numeric(stock['cantidad'], errors='coerce').fillna(0.0).sum())
                            if disponible < ml:
                                alertas.append(
                                    f"⚠️ Falta tinta {color}: necesitas {ml:.2f} ml y hay {disponible:.2f} ml"
                                )
                        else:
                            alertas.append(
                                f"⚠️ No se encontró tinta {color} asociada en inventario para validar stock."
                            )

                if alertas:
                    for a in alertas:
                        st.error(a)
                else:
                    st.success("✅ Hay suficiente tinta para producir")



            consumos_ids_cmyk = mapear_consumos_cmyk_a_inventario(
                totales_lote_cmyk,
                tintas_vinculadas if 'tintas_vinculadas' in locals() else pd.DataFrame()
            )

            # --- ENVÍO A COTIZACIÓN ---
            if st.button("📝 ENVIAR A COTIZACIÓN", use_container_width=True):

                # Guardamos información completa para el cotizador
                st.session_state['datos_pre_cotizacion'] = {

                    # BASE
                    'tipo': tipo_produccion,

                    'trabajo': f"{tipo_produccion} - {impresora_sel}",

                    'cantidad': total_pags,

                    'costo_base': float(df_sim.iloc[0]['Total ($)']),


                    # CMYK
                    'consumos_cmyk': totales_lote_cmyk,

                    'consumos': totales_lote_cmyk,
                    'consumos_ids': consumos_ids_cmyk,


                    # ARCHIVOS
                    'archivos': resultados,

                    'detalle_archivos': resultados,


                    # PRODUCCIÓN
                    'impresora': impresora_sel,

                    'papel': mejor['Papel'],

                    'calidad': mejor['Calidad'],


                    # COSTOS
                    'precio_tinta_ml': precio_tinta_ml,

                    'costo_desgaste': costo_desgaste,

                    'factor_consumo': factor,

                    'factor_negro': factor_k,

                    'refuerzo_negro': refuerzo_negro,


                    # CONTROL
                    'origen': "CMYK",

                    'fecha': pd.Timestamp.now()

                }


                try:

                    with conectar() as conn:

                        conn.execute("""

                            INSERT INTO historial_cmyk

                            (impresora, paginas, costo)

                            VALUES (?,?,?)

                        """, (

                            impresora_sel,

                            total_pags,

                            total_usd_lote

                        ))

                        conn.commit()


                except Exception as e:

                    st.warning(

                        f"No se pudo guardar en historial: {e}"

                    )


                st.success(

                    "✅ Datos enviados correctamente al módulo de Cotizaciones"

                )

                st.toast(

                    "Listo para cotizar",

                    icon="📨"

                )

                st.rerun()



    st.divider()


    st.subheader("🕘 Historial reciente CMYK")


    if df_hist_cmyk.empty:

        st.info(

            "Aún no hay análisis guardados en el historial."

        )

    else:

        df_hist_view = df_hist_cmyk.copy()

        df_hist_view['fecha'] = pd.to_datetime(

            df_hist_view['fecha'],

            errors='coerce'

        )

        st.dataframe(

            df_hist_view,

            use_container_width=True,

            hide_index=True

        )


        hist_ordenado = df_hist_view.dropna(

            subset=['fecha']

        ).copy()


        if not hist_ordenado.empty:

            hist_ordenado['dia'] = (

                hist_ordenado['fecha']
                .dt.date
                .astype(str)

            )


            hist_dia = hist_ordenado.groupby(

                'dia',

                as_index=False

            )['costo'].sum()


            fig_hist = px.line(

                hist_dia,

                x='dia',

                y='costo',

                markers=True,

                title='Costo CMYK por día (historial)'

            )


            fig_hist.update_layout(

                xaxis_title='Día',

                yaxis_title='Costo ($)'

            )


            st.plotly_chart(

                fig_hist,

                use_container_width=True

            )



    st.subheader("🏭 Tipo de Producción")


    procesos_disponibles = [
        "Impresión CMYK",
        "Sublimación",
        "Corte Cameo",
        "Producción Manual",
    ]

    tipo_produccion = st.selectbox("Selecciona proceso", procesos_disponibles)

    st.subheader("🧩 Tablero de Taller (Kanban)")
    with conectar() as conn:
        df_kanban = pd.read_sql_query("SELECT id, tipo, producto, estado, fecha FROM ordenes_produccion WHERE COALESCE(activo,1)=1 ORDER BY fecha DESC LIMIT 150", conn)

    if df_kanban.empty:
        st.info("No hay órdenes de producción activas.")
    else:
        df_kanban['estado'] = df_kanban['estado'].apply(normalizar_estado_kanban)
        cols_k = st.columns(len(KANBAN_ESTADOS))
        for i, estado_k in enumerate(KANBAN_ESTADOS):
            with cols_k[i]:
                st.markdown(f"**{estado_k}**")
                sub = df_kanban[df_kanban['estado'] == estado_k].head(8)
                if sub.empty:
                    st.caption('—')
                for _, ord_row in sub.iterrows():
                    st.caption(f"#{int(ord_row['id'])} · {ord_row['producto']}")

        try:
            with conectar() as conn:
                df_hist_est = pd.read_sql_query("SELECT orden_id, fecha FROM ordenes_estado_historial ORDER BY orden_id, fecha", conn)
            if not df_hist_est.empty:
                df_hist_est['fecha'] = pd.to_datetime(df_hist_est['fecha'], errors='coerce')
                df_hist_est = df_hist_est.dropna(subset=['fecha']).sort_values(['orden_id', 'fecha'])
                df_hist_est['delta_min'] = df_hist_est.groupby('orden_id')['fecha'].diff().dt.total_seconds() / 60.0
                prom_min = float(df_hist_est['delta_min'].dropna().mean()) if not df_hist_est['delta_min'].dropna().empty else 0.0
                st.caption(f"⏱️ Tiempo promedio entre estados: {prom_min:.1f} min")
        except Exception:
            pass

        op_orden = st.selectbox("Orden a mover", df_kanban['id'].astype(int).tolist(), key='kanban_orden_sel')
        op_estado = st.selectbox("Nuevo estado", KANBAN_ESTADOS, key='kanban_estado_sel')
        if st.button("Mover orden", key='kanban_move_btn'):
            with conectar() as conn:
                previo = conn.execute("SELECT estado FROM ordenes_produccion WHERE id=?", (int(op_orden),)).fetchone()
                estado_prev = str(previo[0]) if previo else ''
                conn.execute("UPDATE ordenes_produccion SET estado=? WHERE id=?", (op_estado, int(op_orden)))
                conn.execute(
                    "INSERT INTO ordenes_estado_historial (orden_id, estado_anterior, estado_nuevo, usuario) VALUES (?, ?, ?, ?)",
                    (int(op_orden), estado_prev, op_estado, st.session_state.get('usuario_nombre', 'Sistema'))
                )
                registrar_log_actividad(conn, 'UPDATE_ESTADO', 'ordenes_produccion')
                registrar_auditoria(conn, 'CAMBIO_ESTADO_ORDEN', estado_prev, op_estado)
                conn.commit()
            st.toast(f"Orden #{op_orden} movida a {op_estado}", icon='✅')
            st.rerun()

# ============================================================
# 🔥 MÓDULO SUBLIMACIÓN INDUSTRIAL
# ============================================================

elif menu == "🔥 Sublimación":

    st.title("🔥 Producción Sublimación")

    cola = st.session_state.get("cola_sublimacion", [])


    if not cola:

        st.info("No hay trabajos recibidos desde CMYK")

        st.stop()


    df_cola = pd.DataFrame(cola)

    st.subheader("📥 Trabajos pendientes")

    st.dataframe(df_cola, use_container_width=True)


    total_transfer = df_cola["costo_transfer_total"].sum()

    total_unidades = df_cola["cantidad"].sum()

    costo_unitario_transfer = total_transfer / max(total_unidades, 1)


    # =====================================================
    # COSTOS SUBLIMACIÓN
    # =====================================================

    st.subheader("⚙ Costos de sublimación")

    c1,c2,c3 = st.columns(3)

    potencia = c1.number_input("Potencia kW", value=1.5)

    tiempo = c2.number_input("Min por unidad", value=5.0)

    costo_kwh = c3.number_input("Costo kWh", value=0.15)


    energia_unit = (potencia * tiempo / 60) * costo_kwh


    salario = st.number_input("Salario hora operador", value=3.0)

    prod_hora = st.number_input("Unidades por hora", value=12.0)


    mano_unit = salario / prod_hora


    valor_maquina = st.number_input("Valor máquina", value=1500.0)

    vida = st.number_input("Vida útil horas", value=5000.0)


    dep_unit = (valor_maquina / vida) / prod_hora


    costo_unitario = (

        costo_unitario_transfer
        + energia_unit
        + mano_unit
        + dep_unit

    )


    costo_total = costo_unitario * total_unidades


    st.divider()

    m1,m2 = st.columns(2)

    m1.metric("Costo unitario final", f"$ {costo_unitario:.4f}")

    m2.metric("Costo total", f"$ {costo_total:.2f}")


    # =====================================================
    # CREAR ORDEN PRODUCCIÓN
    # =====================================================

    if st.button("🏭 Crear Orden Producción"):

        try:

            with conectar() as conn:

                conn.execute("""

                INSERT INTO ordenes_produccion

                (tipo, producto, estado, costo)

                VALUES (?,?,?,?)

                """,

                (

                    "Sublimación",

                    f"{total_unidades} unidades",

                    "Pendiente",

                    costo_total

                ))

                conn.commit()


            st.success("Orden creada en Kanban")


        except Exception as e:

            st.error(e)


    # =====================================================
    # FINALIZAR
    # =====================================================

    if st.button("✅ Finalizar Sublimación"):

        st.session_state["cola_sublimacion"] = []

        st.success("Producción completada")

        st.rerun()


    # ============================================================
    # 📤 ENVIAR A SUBLIMACIÓN
    # ============================================================

    if st.button("📤 Enviar a Sublimación", key="btn_enviar_subl"):

        datos = {

            "trabajo": nombre_trabajo,

            "costo_transfer_total": float(costo_total),

            "cantidad": int(unidades),

            "costo_transfer_unitario": float(
                costo_total / max(unidades, 1)
            ),

            "fecha": datetime.now().isoformat()

        }

        if "cola_sublimacion" not in st.session_state:

            st.session_state["cola_sublimacion"] = []

        st.session_state["cola_sublimacion"].append(datos)

        st.success("Enviado a Sublimación")


# --- 9. MÓDULO PROFESIONAL DE ACTIVOS ---
elif menu == "🏗️ Activos":

    if ROL != "Admin":
        st.error("🚫 Acceso Denegado. Solo Administración puede gestionar activos.")
        st.stop()


    st.title("🏗️ Gestión Integral de Activos")

    # --- CARGA SEGURA DE DATOS ---
    try:
        with conectar() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equipo TEXT,
                    categoria TEXT,
                    inversion REAL,
                    unidad TEXT,
                    desgaste REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            df = pd.read_sql_query("SELECT * FROM activos", conn)
            
            # Crear tabla de historial si no existe
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activos_historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activo TEXT,
                    accion TEXT,
                    detalle TEXT,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")
        st.stop()
    if not df.empty:
        df['inversion'] = pd.to_numeric(df['inversion'], errors='coerce').fillna(0.0)
        df['desgaste'] = pd.to_numeric(df['desgaste'], errors='coerce').fillna(0.0)
        ranking_riesgo = df['desgaste'].rank(pct=True, method='average').fillna(0)
        df['riesgo'] = np.where(ranking_riesgo >= 0.80, '🔴 Alto', np.where(ranking_riesgo >= 0.50, '🟠 Medio', '🟢 Bajo'))

        st.subheader("🧠 Salud de Activos")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Inversión instalada", f"$ {df['inversion'].sum():,.2f}")
        m2.metric("Desgaste promedio", f"$ {df['desgaste'].mean():.4f}/uso")
        m3.metric("Activos en riesgo alto", int((df['riesgo'] == '🔴 Alto').sum()))
        activo_critico = df.sort_values('desgaste', ascending=False).iloc[0]['equipo']
        m4.metric("Activo más crítico", str(activo_critico))

        with st.expander("🔎 Activos con prioridad de mantenimiento", expanded=False):
            st.dataframe(
                df.sort_values('desgaste', ascending=False)[['equipo', 'categoria', 'unidad', 'inversion', 'desgaste', 'riesgo']].head(10),
                use_container_width=True,
                hide_index=True
            )
            fig_riesgo = px.histogram(df, x='riesgo', color='riesgo', title='Distribución de riesgo por desgaste')
            st.plotly_chart(fig_riesgo, use_container_width=True)


    # --- REGISTRO DE NUEVO ACTIVO ---
    with st.expander("➕ Registrar Nuevo Activo"):

        with st.form("form_activos_pro"):

            c1, c2 = st.columns(2)

            nombre_eq = c1.text_input("Nombre del Activo")
            tipo_seccion = c2.selectbox("Tipo de Equipo", [
                "Impresora",
                "Corte / Plotter (Cameo)",
                "Plancha de Sublimación",
                "Otro"
            ])

            col_m1, col_m2, col_m3 = st.columns(3)

            monto_inv = col_m1.number_input("Inversión ($)", min_value=0.0)
            vida_util = col_m2.number_input("Vida Útil (Usos)", min_value=1, value=1000)

            categoria_especifica = col_m3.selectbox(
                "Categoría",
                ["Impresora", "Corte", "Sublimación", "Tinta", "Calor", "Mantenimiento", "Otro"]
            )

            if st.form_submit_button("🚀 Guardar Activo"):

                if not nombre_eq:
                    st.error("Debe indicar un nombre.")
                    st.stop()

                if monto_inv <= 0:
                    st.error("La inversión debe ser mayor a cero.")
                    st.stop()

                desgaste_u = monto_inv / vida_util

                try:
                    with conectar() as conn:
                        conn.execute("""
                            INSERT INTO activos 
                            (equipo, categoria, inversion, unidad, desgaste) 
                            VALUES (?,?,?,?,?)
                        """, (
                            nombre_eq,
                            categoria_especifica,
                            monto_inv,
                            tipo_seccion,
                            desgaste_u
                        ))

                        conn.execute("""
                            INSERT INTO activos_historial 
                            (activo, accion, detalle, costo)
                            VALUES (?,?,?,?)
                        """, (nombre_eq, "CREACIÓN", "Registro inicial", monto_inv))

                        conn.commit()

                    st.success("✅ Activo registrado correctamente.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al registrar: {e}")

    st.divider()

    # --- EDICIÓN DE ACTIVOS ---
    with st.expander("✏️ Editar Activo Existente"):

        if df.empty:
            st.info("No hay activos para editar.")
        else:
            activo_sel = st.selectbox("Seleccionar activo:", df['equipo'].tolist())

            datos = df[df['equipo'] == activo_sel].iloc[0]

            with st.form("editar_activo"):

                c1, c2, c3 = st.columns(3)

                categorias_activo = ["Impresora", "Corte", "Sublimación", "Tinta", "Calor", "Mantenimiento", "Otro"]
                categoria_actual = str(datos.get('categoria', 'Otro'))
                idx_categoria = categorias_activo.index(categoria_actual) if categoria_actual in categorias_activo else len(categorias_activo) - 1

                nueva_inv = c1.number_input("Inversión ($)", min_value=0.0, value=_safe_float(datos['inversion']))
                vida_sugerida = _calcular_vida_util_desde_activo(datos.get('inversion', 0.0), datos.get('desgaste', 0.0), default=1000)
                nueva_vida = c2.number_input("Vida útil", min_value=1, value=int(vida_sugerida), step=1)
                nueva_cat = c3.selectbox(
                    "Categoría",
                    categorias_activo,
                    index=idx_categoria
                )

                if st.form_submit_button("💾 Guardar Cambios"):

                    nuevo_desgaste = (nueva_inv / max(1, int(nueva_vida))) if nueva_inv > 0 else 0.0
                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE activos
                                SET inversion = ?, categoria = ?, desgaste = ?
                                WHERE id = ?
                            """, (nueva_inv, nueva_cat, nuevo_desgaste, int(datos['id'])))

                            conn.execute("""
                                INSERT INTO activos_historial 
                                (activo, accion, detalle, costo)
                                VALUES (?,?,?,?)
                            """, (activo_sel, "EDICIÓN", "Actualización de valores", nueva_inv))

                            conn.commit()

                        st.success("Activo actualizado.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error al actualizar: {e}")

    st.divider()

    # --- VISUALIZACIÓN POR SECCIONES ---
    t1, t2, t3, t4, t5, t6 = st.tabs([
        "🖨️ Impresoras",
        "✂️ Corte / Plotter",
        "🔥 Planchas",
        "🧰 Otros",
        "📊 Resumen Global",
        "📜 Historial"
    ])

    if not df.empty:

        with t1:
            st.subheader("Impresoras")
            df_imp = df[df['unidad'].fillna('').str.contains("Impresora", case=False)]
            st.dataframe(df_imp, use_container_width=True, hide_index=True)

        with t2:
            st.subheader("Corte / Plotter")
            df_corte = df[df['unidad'].fillna('').str.contains("Corte|Plotter|Cameo", case=False)]
            st.dataframe(df_corte, use_container_width=True, hide_index=True)

        with t3:
            st.subheader("Planchas de Sublimación")
            df_plancha = df[df['unidad'].fillna('').str.contains("Plancha|Sublim", case=False)]
            st.dataframe(df_plancha, use_container_width=True, hide_index=True)

        with t4:
            st.subheader("Otros equipos")
            mask_otro = ~df['unidad'].fillna('').str.contains("Impresora|Corte|Plotter|Cameo|Plancha|Sublim", case=False)
            st.dataframe(df[mask_otro], use_container_width=True, hide_index=True)

        with t5:
            c_inv, c_des, c_prom = st.columns(3)

            c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
            c_des.metric("Activos Registrados", len(df))

            promedio = df['desgaste'].mean() if not df.empty else 0
            c_prom.metric("Desgaste Promedio por Uso", f"$ {promedio:.4f}")

            fig = px.bar(
                df,
                x='equipo',
                y='inversion',
                color='categoria',
                title="Distribución de Inversión por Activo"
            )
            st.plotly_chart(fig, use_container_width=True)

        with t6:
            st.subheader("Historial de Movimientos de Activos")

            try:
                with conectar() as conn:
                    df_hist = pd.read_sql_query(
                        "SELECT activo, accion, detalle, costo, fecha FROM activos_historial ORDER BY fecha DESC",
                        conn
                    )

                if not df_hist.empty:
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay movimientos registrados aún.")

            except Exception as e:
                st.error(f"Error cargando historial: {e}")

    else:
        st.info("No hay activos registrados todavía.")




# ===========================================================
# 11. MÓDULO PROFESIONAL DE OTROS PROCESOS
# ===========================================================
elif menu == "🛠️ Otros Procesos":

    st.title("🛠️ Calculadora de Procesos Especiales")
    st.info("Cálculo de costos de procesos que no usan tinta: corte, laminado, planchado, etc.")
    if 'datos_proceso_desde_cmyk' in st.session_state:
        p_cmyk = st.session_state.get('datos_proceso_desde_cmyk', {})
        st.success(f"Trabajo recibido desde CMYK: {p_cmyk.get('trabajo', 'N/D')} ({p_cmyk.get('unidades', 0)} uds)")
        st.caption(str(p_cmyk.get('observacion', '')))
        if st.button("Limpiar envío CMYK (Procesos)", key='btn_clear_cmyk_proc'):
            st.session_state.pop('datos_proceso_desde_cmyk', None)
            st.rerun()

    # --- CARGA SEGURA DE EQUIPOS ---
    try:
        with conectar() as conn:
            df_act_db = pd.read_sql_query(
                "SELECT equipo, categoria, unidad, desgaste FROM activos", conn
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial_procesos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equipo TEXT,
                    cantidad REAL,
                    costo REAL,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    except Exception as e:
        st.error(f"Error cargando activos: {e}")
        st.stop()

    # Filtrar solo equipos que NO gastan tinta
    
    mask_no_tinta = ~(
        df_act_db['categoria'].fillna('').str.contains('impres|tinta', case=False, na=False)
        | df_act_db['unidad'].fillna('').str.contains('impres', case=False, na=False)
    )
    otros_equipos = df_act_db[mask_no_tinta].copy()
    otros_equipos['desgaste'] = pd.to_numeric(otros_equipos['desgaste'], errors='coerce').fillna(0.0)
    otros_equipos = otros_equipos.to_dict('records')

    if not otros_equipos:
        st.warning("⚠️ No hay equipos registrados para procesos especiales.")
        st.stop()

    nombres_eq = [e['equipo'] for e in otros_equipos]

    if "lista_procesos" not in st.session_state:
        st.session_state.lista_procesos = []

    with st.container(border=True):

        c1, c2 = st.columns(2)

        eq_sel = c1.selectbox("Selecciona el Proceso/Equipo:", nombres_eq)

        datos_eq = next(e for e in otros_equipos if e['equipo'] == eq_sel)

        cantidad = c2.number_input(
            f"Cantidad de {datos_eq['unidad']}:",
            min_value=1.0,
            value=1.0
        )

        # Conversión segura del desgaste
        costo_unitario = float(datos_eq.get('desgaste', 0.0))
        costo_total = costo_unitario * cantidad

        st.divider()

        r1, r2 = st.columns(2)
        r1.metric("Costo Unitario", f"$ {costo_unitario:.4f}")
        r2.metric("Costo Total", f"$ {costo_total:.2f}")

        if st.button("➕ Agregar Proceso"):
            st.session_state.lista_procesos.append({
                "equipo": eq_sel,
                "cantidad": cantidad,
                           "costo_unitario": costo_unitario,
                "costo": costo_total,
                "fecha": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
            })
            st.toast("Proceso añadido")

    # --- RESUMEN DE PROCESOS EN SESIÓN ---
    if st.session_state.lista_procesos:

        st.subheader("📋 Procesos Acumulados")

        df_proc = pd.DataFrame(st.session_state.lista_procesos)
        st.dataframe(df_proc, use_container_width=True, hide_index=True)

        total = df_proc["costo"].sum()
        st.metric("Total Procesos", f"$ {total:.2f}")

        p1, p2, p3 = st.columns(3)
        p1.metric("Procesos cargados", int(len(df_proc)))
        p2.metric("Costo promedio por proceso", f"$ {df_proc['costo'].mean():.2f}")
        p3.metric("Equipo más usado", str(df_proc['equipo'].mode().iloc[0]) if not df_proc['equipo'].mode().empty else "N/D")

        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📝 Enviar a Cotización", use_container_width=True):

                st.session_state['datos_pre_cotizacion'] = {
                    'trabajo': " + ".join(df_proc["equipo"].tolist()),
                    'costo_base': float(total),
                    'unidades': 1,
                    'es_proceso_extra': True
                }

                st.success("Enviado a cotización")
                st.session_state.lista_procesos = []
                st.rerun()

        with col2:
            if st.button("🧹 Limpiar", use_container_width=True):
                st.session_state.lista_procesos = []
                st.rerun()

    
        with col3:
            limpiar_tras_guardar = st.checkbox("Limpiar lista tras guardar", value=True, key='proc_limpiar_tras_guardar')
            if st.button("💾 Guardar en historial", use_container_width=True):
                try:
                    with conectar() as conn:
                        conn.executemany(
                            "INSERT INTO historial_procesos (equipo, cantidad, costo) VALUES (?,?,?)",
                            [
                                (str(r['equipo']), float(r['cantidad']), float(r['costo']))
                                for _, r in df_proc.iterrows()
                            ]
                        )
                        conn.commit()
                    st.success("Procesos guardados en historial.")
                    if limpiar_tras_guardar:
                        st.session_state.lista_procesos = []
                        st.rerun()
                except Exception as e:
                    st.error(f"No se pudo guardar historial: {e}")

    # --- HISTORIAL ---
    with st.expander("📜 Historial de Procesos"):

        try:
            with conectar() as conn:
                df_hist = pd.read_sql_query(
                    "SELECT * FROM historial_procesos ORDER BY fecha DESC",
                    conn
                )

            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("Sin registros aún.")

        except Exception as e:
            st.info("Historial no disponible.")


# ===========================================================
# ✂️ MÓDULO CORTE INDUSTRIAL
# ===========================================================
elif menu == "✂️ Corte Industrial":

    st.title("✂️ Corte / Cameo Industrial")
    st.caption("Módulo complementario industrial. No altera los flujos base del ERP.")
    if 'datos_corte_desde_cmyk' in st.session_state:
        c_cmyk = st.session_state.get('datos_corte_desde_cmyk', {})
        st.success(f"Trabajo recibido desde CMYK: {c_cmyk.get('trabajo', 'N/D')} ({c_cmyk.get('unidades', 0)} uds)")
        st.caption(str(c_cmyk.get('observacion', '')))
        if st.button("Limpiar envío CMYK (Corte)", key='btn_clear_cmyk_corte'):
            st.session_state.pop('datos_corte_desde_cmyk', None)
            st.rerun()

    up = st.file_uploader("Archivo de corte (SVG/PNG/JPG/DXF)", type=['svg', 'png', 'jpg', 'jpeg', 'dxf'], key='corte_file_ind')

    with conectar() as conn:
        try:
            df_mat = pd.read_sql_query("SELECT id, nombre, factor_dureza, inventario_id FROM materiales_corte ORDER BY nombre", conn)
        except Exception:
            df_mat = pd.DataFrame(columns=['id', 'nombre', 'factor_dureza', 'inventario_id'])
        try:
            df_act = pd.read_sql_query("SELECT id, equipo, categoria, desgaste FROM activos", conn)
        except Exception:
            df_act = pd.DataFrame(columns=['id', 'equipo', 'categoria', 'desgaste'])

    df_act_corte = df_act[df_act['categoria'].fillna('').str.contains('Corte|Plotter|Cameo', case=False, na=False)].copy() if not df_act.empty else pd.DataFrame(columns=['id', 'equipo', 'categoria', 'desgaste'])
    mat_opts = {f"{r['nombre']} (x{float(r['factor_dureza'] or 1.0):.2f})": (int(r['inventario_id']) if pd.notna(r['inventario_id']) else None, float(r['factor_dureza'] or 1.0)) for _, r in df_mat.iterrows()} if not df_mat.empty else {}
    act_opts = {str(r['equipo']): float(r['desgaste'] or 0.0) for _, r in df_act_corte.iterrows()} if not df_act_corte.empty else {}

    col1, col2, col3 = st.columns(3)
    mat_sel = col1.selectbox("Material", list(mat_opts.keys()) if mat_opts else ["Sin material configurado"])
    act_sel = col2.selectbox("Equipo de corte", list(act_opts.keys()) if act_opts else ["Sin equipo configurado"])
    factor_comp = col3.slider('Factor complejidad', min_value=1.0, max_value=2.5, value=1.35, step=0.05)
    mano_obra_base = st.number_input("Mano de obra base ($)", min_value=0.0, value=0.5, step=0.1)

    if up is not None:
        inv_id, fac_dur = mat_opts.get(mat_sel, (None, 1.0))
        desgaste_act = act_opts.get(act_sel, 0.0)
        r = calcular_corte_cameo(up.getvalue(), factor_dureza_material=fac_dur, desgaste_activo=desgaste_act, nombre_archivo=up.name, factor_complejidad=factor_comp, mano_obra_base=mano_obra_base)
        st.json(r)

        if st.button("Guardar orden de corte", key='btn_guardar_orden_corte'):
            oid = registrar_orden_produccion('Corte', 'Interno', up.name, 'Pendiente', float(r.get('costo_total', 0.0)), f"Corte industrial {up.name}")
            st.success(f"Orden registrada #{oid}")

        if inv_id and st.button("Descontar material de inventario", key='btn_desc_mat_corte'):
            cant_desc = convertir_area_cm2_a_unidad_inventario(int(inv_id), float(r.get('area_cm2', 0.0)))
            ok, msg = descontar_materiales_produccion({int(inv_id): float(cant_desc)}, usuario=st.session_state.get('usuario_nombre', 'Sistema'), detalle=f"Consumo corte industrial: {up.name}")
            st.success(msg) if ok else st.warning(msg)

        if st.button("Enviar a Cotización", key='btn_send_corte_cot'):
            enviar_a_cotizacion_desde_produccion({'trabajo': f"Corte industrial {up.name}", 'costo_base': float(r.get('desgaste_real', 0.0)), 'unidades': 1, 'detalle': r})
            st.success("Datos enviados a Cotizaciones")
        sobrante_cm = st.number_input("Largo sobrante (cm)", min_value=0.0, value=0.0, step=1.0, key='corte_sobrante_cm')
        nombre_retal = st.text_input("Nombre retal", value=f"Retal {up.name}", key='corte_retal_nombre')
        if sobrante_cm > 30 and st.button("Registrar retal en inventario", key='btn_reg_retal'):
            with conectar() as conn:
                conn.execute("INSERT INTO inventario (item, cantidad, unidad, precio_usd, minimo, activo) VALUES (?, ?, 'unidad', 0, 0, 1)", (nombre_retal, 1.0))
                registrar_log_actividad(conn, 'INSERT_RETAL', 'inventario')
                conn.commit()
            st.toast("Retal registrado con costo $0 para futuras ventas", icon="✅")

# ===========================================================
# 🔥 SUBLIMACIÓN INDUSTRIAL PRO v4.0
# Recibe transfer desde CMYK y suma costos reales
# ===========================================================

elif menu == "🔥 Sublimación Industrial":

    import streamlit as st
    import pandas as pd
    import plotly.express as px
    from datetime import datetime, timedelta
    import io


    st.title("🔥 Sublimación Industrial")
    st.caption("Producción desde transfer CMYK")


    # =====================================================
    # RECIBIR COLA DESDE CMYK
    # =====================================================

    cola = st.session_state.get("cola_sublimacion", [])


    if not cola:

        st.warning("No hay trabajos recibidos desde CMYK")

        st.stop()


    df_cola = pd.DataFrame(cola)


    st.subheader("📥 Trabajos pendientes")

    st.dataframe(df_cola, use_container_width=True)


    total_transfer = df_cola["costo_transfer_total"].sum()

    total_unidades = df_cola["cantidad"].sum()


    costo_transfer_unitario = total_transfer / max(total_unidades,1)


    c1,c2,c3 = st.columns(3)

    c1.metric("Unidades", total_unidades)

    c2.metric("Costo transfer total", f"$ {total_transfer:,.2f}")

    c3.metric("Costo transfer unitario", f"$ {costo_transfer_unitario:,.4f}")


    # =====================================================
    # COSTOS SUBLIMACIÓN
    # =====================================================

    st.divider()

    st.subheader("⚙ Costos sublimación")


    e1,e2,e3 = st.columns(3)


    potencia_kw = e1.number_input(

        "Potencia plancha (kW)",

        value=1.5

    )


    tiempo_min = e2.number_input(

        "Tiempo por unidad (min)",

        value=5.0

    )


    costo_kwh = e3.number_input(

        "Costo kWh ($)",

        value=0.15

    )


    energia_unitaria = (

        potencia_kw * (tiempo_min/60)

    ) * costo_kwh


    # MANO OBRA


    m1,m2 = st.columns(2)


    salario_hora = m1.number_input(

        "Salario por hora",

        value=3.0

    )


    unidades_hora = m2.number_input(

        "Unidades por hora",

        value=12.0

    )


    mano_obra_unitaria = salario_hora / unidades_hora


    # DEPRECIACION


    d1,d2 = st.columns(2)


    valor_maquina = d1.number_input(

        "Valor máquina",

        value=1500.0

    )


    vida_util = d2.number_input(

        "Vida útil horas",

        value=5000.0

    )


    depreciacion_unitaria = (

        valor_maquina / vida_util

    ) / unidades_hora


    # =====================================================
    # COSTO FINAL
    # =====================================================

    costo_unitario = (

        costo_transfer_unitario

        + energia_unitaria

        + mano_obra_unitaria

        + depreciacion_unitaria

    )


    costo_total = costo_unitario * total_unidades


    st.divider()


    r1,r2 = st.columns(2)


    r1.metric(

        "Costo unitario final",

        f"$ {costo_unitario:,.4f}"

    )


    r2.metric(

        "Costo total producción",

        f"$ {costo_total:,.2f}"

    )


    # =====================================================
    # GRAFICO
    # =====================================================

    df_costos = pd.DataFrame({

        "Concepto":[

            "Transfer CMYK",

            "Energia",

            "Mano obra",

            "Depreciacion"

        ],

        "Costo":[

            costo_transfer_unitario,

            energia_unitaria,

            mano_obra_unitaria,

            depreciacion_unitaria

        ]

    })


    fig = px.pie(

        df_costos,

        names="Concepto",

        values="Costo"

    )


    st.plotly_chart(fig,use_container_width=True)


    # =====================================================
    # GUARDAR PRODUCCION
    # =====================================================

    if st.button("💾 Guardar orden producción"):


        oid = registrar_orden_produccion(

            "Sublimación",

            "Interno",

            f"{total_unidades} unidades",

            "pendiente",

            costo_total,

            "Producción desde CMYK"

        )


        inicio = datetime.now()

        fin = inicio + timedelta(

            hours = total_unidades / unidades_hora

        )


        registrar_tiempo_produccion(

            oid,

            inicio,

            fin

        )


        st.success(f"Orden #{oid} creada")


    # =====================================================
    # ENVIAR A COTIZACION
    # =====================================================

    if st.button("📤 Enviar a Cotización"):


        enviar_a_cotizacion_desde_produccion({

            "trabajo":"Sublimación industrial",

            "costo_base":costo_total,

            "unidades":total_unidades,

            "costo_unitario":costo_unitario

        })


        st.success("Enviado a cotización")


    # =====================================================
    # FINALIZAR
    # =====================================================

    if st.button("✅ Finalizar producción"):


        st.session_state["cola_sublimacion"] = []


        st.success("Producción completada")

        st.rerun()


    # =====================================================
    # EXPORTAR
    # =====================================================

    if st.button("📥 Exportar Excel"):


        df_export = pd.DataFrame({

            "Unidades":[total_unidades],

            "Costo unitario":[costo_unitario],

            "Costo total":[costo_total]

        })


        buffer = io.BytesIO()

        df_export.to_excel(buffer,index=False)


        st.download_button(

            "Descargar Excel",

            buffer.getvalue(),

            "sublimacion.xlsx"

        )
# ===========================================================
# 🎨 MÓDULO PRODUCCIÓN MANUAL
# ===========================================================
elif menu == "🎨 Producción Manual":

    st.title("🎨 Producción Manual")
    st.caption("Módulo complementario industrial. No altera los flujos base del ERP.")

    with conectar() as conn:
        try:
            df_inv_m = pd.read_sql_query("SELECT id, item, precio_usd FROM inventario WHERE COALESCE(activo,1)=1", conn)
        except Exception:
            df_inv_m = pd.DataFrame(columns=['id', 'item', 'precio_usd'])
        try:
            df_act_m = pd.read_sql_query("SELECT id, equipo, desgaste FROM activos", conn)
        except Exception:
            df_act_m = pd.DataFrame(columns=['id', 'equipo', 'desgaste'])

    if df_inv_m.empty:
        st.info("No hay inventario activo para producción manual.")
    else:
        item_opts = {f"{r['item']} (ID {int(r['id'])})": (int(r['id']), float(r['precio_usd'] or 0.0)) for _, r in df_inv_m.iterrows()}
        act_opts = {f"{r['equipo']} (ID {int(r['id'])})": float(r['desgaste'] or 0.0) for _, r in df_act_m.iterrows()} if not df_act_m.empty else {}

        prod = st.text_input("Producto", value='Producto manual')
        mat_sel = st.multiselect("Materiales", list(item_opts.keys()))
        act_sel = st.multiselect("Activos usados", list(act_opts.keys()))

        materiales = []
        consumos = {}
        for m in mat_sel:
            q = st.number_input(f"Cantidad {m}", min_value=0.0, value=1.0, key=f'q_{m}')
            item_id, p_u = item_opts[m]
            materiales.append({'cantidad': float(q), 'precio_unit': float(p_u)})
            consumos[item_id] = consumos.get(item_id, 0.0) + float(q)

        activos = []
        for a in act_sel:
            t = st.number_input(f"Tiempo (h) {a}", min_value=0.0, value=1.0, key=f't_{a}')
            activos.append({'tiempo': float(t), 'desgaste_hora': float(act_opts[a])})

        r = calcular_produccion_manual(materiales, activos)
        st.json(r)

        if st.button("Guardar receta", key='btn_guardar_receta_manual'):
            with conectar() as conn:
                for m in mat_sel:
                    item_id, _ = item_opts[m]
                    conn.execute("INSERT INTO recetas_produccion (producto, inventario_id, cantidad, activo_id, tiempo) VALUES (?, ?, ?, ?, ?)", (prod, int(item_id), float(consumos.get(item_id, 0.0)), None, 0.0))
                conn.commit()
            st.success("Receta guardada")

        if st.button("Descontar inventario producción manual", key='btn_desc_manual_inv'):
            ok, msg = descontar_materiales_produccion(consumos, usuario=st.session_state.get('usuario_nombre', 'Sistema'), detalle=f'Producción manual: {prod}')
            st.success(msg) if ok else st.warning(msg)

        if st.button("Guardar orden manual", key='btn_guardar_orden_manual'):
            oid = registrar_orden_produccion('Manual', 'Interno', prod, 'pendiente', float(r['costo_total']), f'Producción manual {prod}')
            st.success(f"Orden registrada #{oid}")

        if st.button("Enviar a Cotización", key='btn_send_manual_cot'):
            enviar_a_cotizacion_desde_produccion({'trabajo': f'Producción manual {prod}', 'costo_base': float(r['costo_total']), 'unidades': 1})
            st.success("Datos enviados a Cotizaciones")

# ===========================================================
# 12. MÓDULO PROFESIONAL DE VENTAS (VERSIÓN 2.0)
# ===========================================================
elif menu == "💰 Ventas":

    st.title("💰 Gestión Profesional de Ventas")

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar Venta",
        "📜 Historial",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE VENTA
    # -----------------------------------
    with tab1:

        df_cli = st.session_state.get("df_cli", pd.DataFrame())

        if df_cli.empty:
            st.warning("⚠️ Registra clientes primero.")
            st.stop()

        with st.form("venta_manual", clear_on_submit=True):

            st.subheader("Datos de la Venta")

            opciones_cli = {
                row['nombre']: row['id']
                for _, row in df_cli.iterrows()
            }

            c1, c2 = st.columns(2)

            cliente_nombre = c1.selectbox(
                "Cliente:", list(opciones_cli.keys())
            )

            detalle_v = c2.text_input(
                "Detalle de lo vendido:",
                placeholder="Ej: 100 volantes, 2 banner..."
            )

            c3, c4, c5, c6, c7 = st.columns(5)

            monto_venta = c3.number_input(
                "Monto ($):",
                min_value=0.01,
                format="%.2f"
            )

            metodo_pago = c4.selectbox(
                "Método:",
                ["Efectivo ($)", "Pago Móvil (BCV)",
                 "Zelle", "Binance (USDT)",
                 "Transferencia (Bs)", "Kontigo", "Pendiente"]
            )

            tasa_uso = t_bcv if "BCV" in metodo_pago else (
                t_bin if "Binance" in metodo_pago else 1.0
            )

            monto_bs = monto_venta * tasa_uso

            c5.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            if st.form_submit_button("🚀 Registrar Venta"):

                if not detalle_v.strip():
                    st.error("Debes indicar el detalle de la venta.")
                    st.stop()

                try:
                    with conectar() as conn:

                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS ventas_extra (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                venta_id INTEGER,
                                tasa REAL,
                                monto_bs REAL
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO ventas 
                            (cliente_id, cliente, detalle, monto_total, metodo)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            opciones_cli[cliente_nombre],
                            cliente_nombre,
                            detalle_v.strip(),
                            float(monto_venta),
                            metodo_pago
                        ))

                        venta_id = cur.lastrowid

                        cur.execute("""
                            INSERT INTO ventas_extra
                            (venta_id, tasa, monto_bs)
                            VALUES (?, ?, ?)
                        """, (
                            venta_id,
                            float(tasa_uso),
                            float(monto_bs)
                        ))

                        conn.commit()

                    # 🚀 DESCONTAR INVENTARIO AUTOMÁTICO (solo si hay consumos CMYK válidos mapeables)
                    consumos_tmp = globals().get('totales_lote_cmyk', {}) if isinstance(globals().get('totales_lote_cmyk', {}), dict) else {}
                    if consumos_tmp:
                        with conectar() as conn_desc:
                            df_tintas_desc = obtener_tintas_impresora(conn_desc, str(st.session_state.get('impresora_sel', '')))
                            consumos_ids_desc = mapear_consumos_cmyk_a_inventario(consumos_tmp, df_tintas_desc)
                            for iid, qty in consumos_ids_desc.items():
                                conn_desc.execute(
                                    """
                                    UPDATE inventario
                                    SET cantidad = cantidad - ?,
                                        ultima_actualizacion = CURRENT_TIMESTAMP
                                    WHERE id = ? AND COALESCE(activo,1)=1 AND cantidad >= ?
                                    """,
                                    (float(qty), int(iid), float(qty))
                                )
                            conn_desc.commit()
                        st.success("📦 Inventario CMYK descontado automáticamente")

                    st.success("Venta registrada correctamente")

                    st.balloons()

                    st.rerun()

                except Exception as e:

                    st.error(f"Error: {e}")
    # -----------------------------------
    # HISTORIAL
    # -----------------------------------
    with tab2:

        st.subheader("Historial de Ventas")

        try:
            with conectar() as conn:
                df_historial = pd.read_sql_query("""
                    SELECT 
                        v.id,
                        v.fecha,
                        v.cliente,
                        v.detalle,
                        v.monto_total as total,
                        v.metodo,
                        e.tasa,
                        e.monto_bs
                    FROM ventas v
                    LEFT JOIN ventas_extra e ON v.id = e.venta_id
                    ORDER BY v.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_historial.empty:
            st.info("No hay ventas aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", date.today() - timedelta(days=30))
        hasta = c2.date_input("Hasta", date.today())

        df_historial['fecha'] = pd.to_datetime(df_historial['fecha'], errors='coerce')

        df_fil = df_historial[
            (df_historial['fecha'].dt.date >= desde) &
            (df_historial['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por cliente o detalle:")

        if busc:
            df_fil = df_fil[
                df_fil['cliente'].str.contains(busc, case=False, na=False) |
                df_fil['detalle'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del periodo", f"$ {df_fil['total'].sum():.2f}")

        # --- GESTIÓN DE PENDIENTES ---
        st.subheader("Gestión de Cuentas Pendientes")

        pendientes = df_fil[df_fil['metodo'] == "Pendiente"]

        for _, row in pendientes.iterrows():

            with st.container(border=True):

                st.write(f"**{row['cliente']}** – ${row['total']:.2f}")

                if st.button(f"Marcar como pagada #{row['id']}"):

                    try:
                        with conectar() as conn:
                            conn.execute("""
                                UPDATE ventas
                                SET metodo = 'Pagado'
                                WHERE id = ?
                            """, (int(row['id']),))
                            conn.commit()

                        st.success("Actualizado")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fil.to_excel(writer, index=False, sheet_name='Ventas')

        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "historial_ventas.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    with tab3:

        st.subheader("Resumen Comercial")

        try:
            with conectar() as conn:
                df_v = pd.read_sql("SELECT * FROM ventas", conn)
        except:
            st.info("Sin datos")
            st.stop()

        if df_v.empty:
            st.info("No hay ventas registradas.")
            st.stop()

        total = df_v['monto_total'].sum()

        c1, c2, c3 = st.columns(3)

        c1.metric("Ventas Totales", f"$ {total:.2f}")

        pendientes = df_v[
            df_v['metodo'].str.contains("Pendiente", case=False, na=False)
        ]['monto_total'].sum()

        c2.metric("Por Cobrar", f"$ {pendientes:.2f}")

        top = df_v.groupby('cliente')['monto_total'].sum().reset_index()

        mejor = top.sort_values("monto_total", ascending=False).head(1)

        if not mejor.empty:
            c3.metric("Mejor Cliente", mejor.iloc[0]['cliente'])

        st.subheader("Ventas por Cliente")
        st.bar_chart(top.set_index("cliente"))


# ===========================================================
# 12. MÓDULO PROFESIONAL DE GASTOS (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "📉 Gastos":

    st.title("📉 Control Integral de Gastos")
    st.info("Registro, análisis y control de egresos del negocio")

    # Solo administración puede registrar gastos
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede gestionar gastos.")
        st.stop()

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar Gasto",
        "📜 Historial",
        "📊 Resumen"
    ])

    # -----------------------------------
    # REGISTRO DE GASTOS
    # -----------------------------------
    with tab1:

        with st.form("form_gastos_pro", clear_on_submit=True):

            col_d, col_c = st.columns([2, 1])

            desc = col_d.text_input(
                "Descripción del Gasto",
                placeholder="Ej: Pago de luz, resma de papel, repuesto..."
            ).strip()

            categoria = col_c.selectbox("Categoría:", [
                "Materia Prima",
                "Mantenimiento de Equipos",
                "Servicios (Luz/Internet)",
                "Publicidad",
                "Sueldos/Retiros",
                "Logística",
                "Otros"
            ])

            c1, c2, c3 = st.columns(3)

            monto_gasto = c1.number_input(
                "Monto en Dólares ($):",
                min_value=0.01,
                format="%.2f"
            )

            metodo_pago = c2.selectbox("Método de Pago:", [
                "Efectivo ($)",
                "Pago Móvil (BCV)",
                "Zelle",
                "Binance (USDT)",
                "Transferencia (Bs)",
                "Kontigo"
            ])

            tasa_ref = t_bcv if "BCV" in metodo_pago or "Bs" in metodo_pago else (
                t_bin if "Binance" in metodo_pago else 1.0
            )

            monto_bs = monto_gasto * tasa_ref

            c3.metric("Equivalente Bs", f"{monto_bs:,.2f}")

            st.divider()

            if st.form_submit_button("📉 REGISTRAR EGRESO"):

                if not desc:
                    st.error("⚠️ La descripción es obligatoria.")
                    st.stop()

                try:
                    with conectar() as conn:

                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS gastos_extra (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                gasto_id INTEGER,
                                tasa REAL,
                                monto_bs REAL,
                                usuario TEXT
                            )
                        """)

                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO gastos 
                            (descripcion, monto, categoria, metodo) 
                            VALUES (?, ?, ?, ?)
                        """, (desc, float(monto_gasto), categoria, metodo_pago))

                        gasto_id = cur.lastrowid

                        cur.execute("""
                            INSERT INTO gastos_extra
                            (gasto_id, tasa, monto_bs, usuario)
                            VALUES (?, ?, ?, ?)
                        """, (
                            gasto_id,
                            float(tasa_ref),
                            float(monto_bs),
                            st.session_state.get("usuario_nombre", "Sistema")
                        ))

                        conn.commit()

                    st.success("📉 Gasto registrado correctamente.")
                    st.balloons()
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Error al guardar el gasto: {e}")

    # -----------------------------------
    # HISTORIAL DE GASTOS
    # -----------------------------------
    with tab2:

        st.subheader("📋 Historial de Gastos")

        try:
            with conectar() as conn:
                df_g = pd.read_sql_query("""
                    SELECT 
                        g.id,
                        g.fecha,
                        g.descripcion,
                        g.categoria,
                        g.monto,
                        g.metodo,
                        e.tasa,
                        e.monto_bs,
                        e.usuario
                    FROM gastos g
                    LEFT JOIN gastos_extra e ON g.id = e.gasto_id
                    WHERE COALESCE(g.activo,1)=1
                    ORDER BY g.fecha DESC
                """, conn)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
            st.stop()

        if df_g.empty:
            st.info("No hay gastos registrados aún.")
            st.stop()

        c1, c2 = st.columns(2)

        desde = c1.date_input("Desde", date.today() - timedelta(days=30))
        hasta = c2.date_input("Hasta", date.today())

        df_g['fecha'] = pd.to_datetime(df_g['fecha'], errors='coerce')

        df_fil = df_g[
            (df_g['fecha'].dt.date >= desde) &
            (df_g['fecha'].dt.date <= hasta)
        ]

        busc = st.text_input("Buscar por descripción:")

        if busc:
            df_fil = df_fil[
                df_fil['descripcion'].str.contains(busc, case=False, na=False)
            ]

        st.dataframe(df_fil, use_container_width=True)

        st.metric("Total del Periodo", f"$ {df_fil['monto'].sum():.2f}")

        # --- EDICIÓN Y ELIMINACIÓN ---
        st.subheader("Gestión de Gastos")

        gasto_sel = st.selectbox(
            "Seleccionar gasto para editar/eliminar:",
            df_fil['descripcion'].tolist()
        )

        datos = df_fil[df_fil['descripcion'] == gasto_sel].iloc[0]

        with st.expander("✏️ Editar Gasto"):

            nuevo_monto = st.number_input(
                "Monto $",
                value=float(datos['monto']),
                format="%.2f"
            )

            if st.button("💾 Guardar Cambios"):

                try:
                    with conectar() as conn:
                        conn.execute("""
                            UPDATE gastos
                            SET monto = ?
                            WHERE id = ?
                        """, (float(nuevo_monto), int(datos['id'])))
                        conn.commit()

                    st.success("Actualizado correctamente")
                    st.rerun()

                except Exception as e:
                    st.error(str(e))

        with st.expander("🗑️ Eliminar Gasto"):

            confirmar = st.checkbox("Confirmo que deseo eliminar este gasto")

            if st.button("Eliminar definitivamente"):

                if not confirmar:
                    st.warning("Debes confirmar para eliminar")
                else:
                    try:
                        with conectar() as conn:
                            conn.execute(
                                "UPDATE gastos SET activo=0 WHERE id = ?",
                                (int(datos['id']),)
                            )
                            conn.commit()

                        st.warning("Gasto eliminado")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

        # --- EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fil.to_excel(writer, index=False, sheet_name='Gastos')

        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            "historial_gastos.xlsx"
        )

    # -----------------------------------
    # RESUMEN
    # -----------------------------------
    with tab3:

        st.subheader("📊 Resumen de Egresos")

        try:
            with conectar() as conn:
                df = pd.read_sql("SELECT * FROM gastos WHERE COALESCE(activo,1)=1", conn)
        except:
            st.info("Sin datos")
            st.stop()

        if df.empty:
            st.info("No hay gastos para analizar.")
            st.stop()

        total = df['monto'].sum()

        c1, c2 = st.columns(2)

        c1.metric("Total Gastado", f"$ {total:.2f}")

        por_cat = df.groupby('categoria')['monto'].sum()

        categoria_top = por_cat.idxmax() if not por_cat.empty else "N/A"

        c2.metric("Categoría Principal", categoria_top)

        st.subheader("Gastos por Categoría")
        st.bar_chart(por_cat)


# ===========================================================
# 13. MÓDULO PROFESIONAL DE CIERRE DE CAJA (VERSIÓN 2.1 MEJORADA)
# ===========================================================
elif menu == "🏁 Cierre de Caja":

    st.title("🏁 Cierre de Caja y Arqueo Diario")

    # --- SEGURIDAD ---
    if ROL not in ["Admin", "Administracion"]:
        st.error("🚫 Solo Administración puede realizar cierres.")
        st.stop()

    # Selección de fecha
    fecha_cierre = st.date_input("Seleccionar fecha:", datetime.now())
    fecha_str = fecha_cierre.strftime('%Y-%m-%d')

    try:
        with conectar() as conn:

            # Asegurar tabla de cierres
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cierres_caja (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT UNIQUE,
                    ingresos REAL,
                    egresos REAL,
                    neto REAL,
                    usuario TEXT,
                    creado DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            df_v = pd.read_sql(
                "SELECT * FROM ventas WHERE date(fecha) = ?",
                conn,
                params=(fecha_str,)
            )

            df_g = pd.read_sql(
                "SELECT * FROM gastos WHERE COALESCE(activo,1)=1 AND date(fecha) = ?",
                conn,
                params=(fecha_str,)
            )

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # Asegurar que existan columnas esperadas
    if not df_v.empty and 'metodo' not in df_v.columns:
        df_v['metodo'] = ""

    # --- SEPARAR COBRADO Y PENDIENTE ---
    if not df_v.empty:
        cobradas = df_v[~df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
        pendientes = df_v[df_v['metodo'].str.contains("Pendiente", case=False, na=False)]
    else:
        cobradas = pd.DataFrame(columns=df_v.columns)
        pendientes = pd.DataFrame(columns=df_v.columns)

    t_ventas_cobradas = float(cobradas['monto_total'].sum()) if not cobradas.empty else 0.0
    t_pendientes = float(pendientes['monto_total'].sum()) if not pendientes.empty else 0.0
    t_gastos = float(df_g['monto'].sum()) if not df_g.empty else 0.0

    balance_dia = t_ventas_cobradas - t_gastos

    # --- MÉTRICAS PRINCIPALES ---
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Ingresos Cobrados", f"$ {t_ventas_cobradas:,.2f}")
    c2.metric("Cuentas Pendientes", f"$ {t_pendientes:,.2f}")
    c3.metric("Egresos del Día", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c4.metric("Neto en Caja", f"$ {balance_dia:,.2f}")

    st.divider()

    # --- DESGLOSE POR MÉTODO ---
    col_v, col_g = st.columns(2)

    with col_v:
        st.subheader("💰 Ingresos por Método")

        if not cobradas.empty:
            resumen_v = cobradas.groupby('metodo')['monto_total'].sum()
            for metodo, monto in resumen_v.items():
                st.write(f"✅ **{metodo}:** ${float(monto):,.2f}")
        else:
            st.info("No hubo ingresos cobrados.")

    with col_g:
        st.subheader("💸 Egresos por Método")

        if not df_g.empty:
            resumen_g = df_g.groupby('metodo')['monto'].sum()
            for metodo, monto in resumen_g.items():
                st.write(f"❌ **{metodo}:** ${float(monto):,.2f}")
        else:
            st.info("No hubo gastos.")

    st.divider()

    # --- DETALLES ---
    with st.expander("📝 Ver detalle completo"):

        st.write("### Ventas Cobradas")
        if not cobradas.empty:
            st.dataframe(cobradas, use_container_width=True, hide_index=True)
        else:
            st.info("Sin ventas cobradas")

        st.write("### Ventas Pendientes")
        if not pendientes.empty:
            st.dataframe(pendientes, use_container_width=True, hide_index=True)
        else:
            st.info("Sin ventas pendientes")

        st.write("### Gastos")
        if not df_g.empty:
            st.dataframe(df_g, use_container_width=True, hide_index=True)
        else:
            st.info("Sin gastos registrados")

    # --- GUARDAR CIERRE ---
    if st.button("💾 Guardar Cierre del Día"):

        try:
            with conectar() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cierres_caja
                    (fecha, ingresos, egresos, neto, usuario)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    fecha_str,
                    float(t_ventas_cobradas),
                    float(t_gastos),
                    float(balance_dia),
                    st.session_state.get("usuario_nombre", "Sistema")
                ))
                conn.commit()

            st.success("✅ Cierre registrado correctamente")

        except Exception as e:
            st.error(f"Error guardando cierre: {e}")

    # --- HISTORIAL DE CIERRES ---
    st.divider()
    st.subheader("📜 Historial de Cierres")

    try:
        with conectar() as conn:
            df_cierres = pd.read_sql(
                "SELECT * FROM cierres_caja ORDER BY fecha DESC",
                conn
            )

        if not df_cierres.empty:
            st.dataframe(df_cierres, use_container_width=True)

            # Exportación
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_cierres.to_excel(writer, index=False, sheet_name='Cierres')

            st.download_button(
                "📥 Descargar Historial de Cierres",
                buffer.getvalue(),
                "cierres_caja.xlsx"
            )
        else:
            st.info("Aún no hay cierres guardados.")

    except Exception as e:
        st.info("No hay historial disponible.")



# ===========================================================
# 13. AUDITORÍA Y MÉTRICAS - VERSIÓN PROFESIONAL MEJORADA 2.1
# ===========================================================
elif menu == "📊 Auditoría y Métricas":

    st.title("📊 Auditoría Integral del Negocio")
    st.caption("Control total de insumos, producción y finanzas")

    try:
        with conectar() as conn:

            # Verificamos si existe la tabla de movimientos
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventario_movs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    tipo TEXT,
                    cantidad REAL,
                    motivo TEXT,
                    usuario TEXT,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            df_movs = pd.read_sql_query("""
                SELECT 
                    m.fecha,
                    i.item as Material,
                    m.tipo as Operacion,
                    m.cantidad as Cantidad,
                    i.unidad,
                    m.motivo
                FROM inventario_movs m
                JOIN inventario i ON m.item_id = i.id
                ORDER BY m.fecha DESC
            """, conn)

            df_ventas = pd.read_sql("SELECT * FROM ventas", conn)
            df_gastos = pd.read_sql("SELECT * FROM gastos WHERE COALESCE(activo,1)=1", conn)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # Asegurar columnas necesarias
    if not df_ventas.empty and 'metodo' not in df_ventas.columns:
        df_ventas['metodo'] = ""

    tab1, tab2, tab3, tab4 = st.tabs([
        "💰 Finanzas",
        "📦 Insumos",
        "📈 Gráficos",
        "🚨 Alertas"
    ])

    # ---------------------------------------
    # TAB FINANZAS
    # ---------------------------------------
    with tab1:

        st.subheader("Resumen Financiero")

        total_ventas = float(df_ventas['monto_total'].sum()) if not df_ventas.empty else 0.0
        total_gastos = float(df_gastos['monto'].sum()) if not df_gastos.empty else 0.0

        # Solo comisiones en métodos bancarios
        if not df_ventas.empty:
            ventas_bancarias = df_ventas[
                df_ventas['metodo'].str.contains("Pago|Transferencia", case=False, na=False)
            ]
            ventas_kontigo = df_ventas[df_ventas['metodo'].str.contains("Kontigo", case=False, na=False)]
        else:
            ventas_bancarias = pd.DataFrame()
            ventas_kontigo = pd.DataFrame()

        banco_perc = st.session_state.get('banco_perc', 0.5)
        kontigo_perc = st.session_state.get('kontigo_perc_entrada', st.session_state.get('kontigo_perc', 5.0))

        comision_est = 0.0
        if not ventas_bancarias.empty:
            comision_est += float(ventas_bancarias['monto_total'].sum() * (banco_perc / 100))
        if not ventas_kontigo.empty:
            comision_est += float(ventas_kontigo['monto_total'].sum() * (kontigo_perc / 100))

        deudas = float(
            df_ventas[
                df_ventas['metodo'].str.contains("Pendiente", case=False, na=False)
            ]['monto_total'].sum()
        ) if not df_ventas.empty else 0.0

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Ingresos", f"$ {total_ventas:,.2f}")
        c2.metric("Gastos", f"$ {total_gastos:,.2f}", delta_color="inverse")
        c3.metric("Comisiones Bancarias", f"$ {comision_est:,.2f}")
        c4.metric("Cuentas por Cobrar", f"$ {deudas:,.2f}")

        utilidad = total_ventas - total_gastos - comision_est

        st.metric("Utilidad Real Estimada", f"$ {utilidad:,.2f}")

    # ---------------------------------------
    # TAB INSUMOS
    # ---------------------------------------
    with tab2:

        st.subheader("Bitácora de Movimientos de Inventario")

        if df_movs.empty:
            st.info("Aún no hay movimientos registrados.")
        else:
            st.dataframe(df_movs, use_container_width=True)

            # Exportación
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_movs.to_excel(writer, index=False, sheet_name='Movimientos')

            st.download_button(
                "📥 Descargar Movimientos (Excel)",
                buffer.getvalue(),
                "auditoria_movimientos.xlsx"
            )

    # ---------------------------------------
    # TAB GRÁFICOS
    # ---------------------------------------
    with tab3:

        st.subheader("Consumo de Insumos")

        if not df_movs.empty:

            salidas = df_movs[df_movs['Operacion'] == 'SALIDA']

            if not salidas.empty:

                resumen = salidas.groupby("Material")["Cantidad"].sum()

                st.bar_chart(resumen)

                top = resumen.sort_values(ascending=False).head(1)

                if not top.empty:
                    st.metric(
                        "Material más usado",
                        top.index[0],
                        f"{top.values[0]:.2f}"
                    )
            else:
                st.info("No hay salidas registradas aún.")
        else:
            st.info("No hay datos para graficar.")

    # ---------------------------------------
    # TAB ALERTAS
    # ---------------------------------------
    with tab4:

        st.subheader("Control de Stock")

        df_inv = st.session_state.get('df_inv', pd.DataFrame())

        if df_inv.empty:
            st.warning("Inventario vacío.")
        else:
            criticos = df_inv[df_inv['cantidad'] <= df_inv['minimo']]

            if criticos.empty:
                st.success("Niveles de inventario óptimos")
            else:
                st.error(f"⚠️ Hay {len(criticos)} productos en nivel crítico")

                for _, r in criticos.iterrows():
                    st.warning(
                        f"**{r['item']}** bajo: {r['cantidad']} {r['unidad']} "
                        f"(mín: {r['minimo']})"
                    )

# ===========================================================
# MÓDULO DE COTIZACIONES - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
elif menu == "📝 Cotizaciones":

    st.title("📝 Cotizador Profesional")

    # Recuperamos datos provenientes de CMYK u otros módulos
    datos = st.session_state.get('datos_pre_cotizacion', {})

    consumos = datos.get('consumos', {})
    consumos_ids_pre = datos.get('consumos_ids', {}) if isinstance(datos.get('consumos_ids', {}), dict) else {}

    datos_pre = {
        'trabajo': datos.get('trabajo', "Trabajo General"),
        'costo_base': datos.get('costo_base', 0.0),
        'unidades': datos.get('unidades', 1),
        'C': consumos.get('C', 0.0),
        'M': consumos.get('M', 0.0),
        'Y': consumos.get('Y', 0.0),
        'K': consumos.get('K', 0.0)
    }

    usa_tinta = any([datos_pre['C'], datos_pre['M'], datos_pre['Y'], datos_pre['K']])

    # ---- CLIENTE ----
    df_cli = st.session_state.get('df_cli', pd.DataFrame())

    if df_cli.empty:
        st.warning("Registra clientes primero.")
        st.stop()

    opciones = {r['nombre']: r['id'] for _, r in df_cli.iterrows()}

    cliente_sel = st.selectbox("Cliente:", opciones.keys())
    id_cliente = opciones[cliente_sel]

    unidades = st.number_input(
        "Cantidad",
        min_value=1,
        value=int(datos_pre['unidades'])
    )

    # ---- COSTOS ----
    costo_unit = st.number_input(
        "Costo unitario base ($)",
        value=float(datos_pre['costo_base'] / unidades if unidades else 0)
    )

    margen = st.slider("Margen %", 10, 300, 100)

    costo_total = costo_unit * unidades
    precio_final = costo_total * (1 + margen / 100)

    st.metric("Precio sugerido", f"$ {precio_final:.2f}")

    # ---- CONSUMOS ----
    consumos_reales = {}

    if usa_tinta:

        if consumos_ids_pre:
            consumos_reales = {int(k): float(v) * float(unidades) for k, v in consumos_ids_pre.items() if float(v) > 0}
            st.success("Tintas vinculadas cargadas automáticamente desde CMYK.")
        else:
            if datos.get('impresora'):
                with conectar() as conn:
                    df_tintas = obtener_tintas_impresora(conn, datos.get('impresora', ''))
            else:
                df_tintas = pd.DataFrame()
            if df_tintas.empty:
                with conectar() as conn:
                    df_tintas = pd.read_sql_query("SELECT id, item, cantidad FROM inventario WHERE COALESCE(activo,1)=1 AND item LIKE '%tinta%'", conn)

            if df_tintas.empty:
                st.error("No hay tintas registradas en inventario.")
                st.stop()

            opciones_tinta = {
                f"{r['item']} ({r['cantidad']} ml)": r['id']
                for _, r in df_tintas.iterrows()
            }

            st.subheader("Asignación de Tintas a Descontar")

            for color in ['C', 'M', 'Y', 'K']:
                sel = st.selectbox(f"Tinta {color}", opciones_tinta.keys(), key=color)
                iid = int(opciones_tinta[sel])
                consumos_reales[iid] = consumos_reales.get(iid, 0.0) + float(datos_pre[color]) * float(unidades)

    metodo_pago = st.selectbox(
        "Método de Pago",
        ["Efectivo", "Zelle", "Pago Móvil", "Transferencia", "Pendiente"]
    )

    # =====================================================
    # 🔐 INTEGRACIÓN CON NÚCLEO CENTRAL
    # =====================================================
    if st.button("CONFIRMAR VENTA"):

        descr = datos_pre['trabajo']

        try:
            exito, msg = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_sel,
                detalle=descr,
                monto_usd=precio_final,
                metodo=metodo_pago,
                consumos=consumos_reales,
                usuario=st.session_state.get("usuario_nombre", "Sistema")
            )

            if exito:
                st.success(msg)

                try:
                    oid_auto = registrar_orden_produccion(
                        tipo='Cotización',
                        cliente=cliente_sel,
                        producto=str(descr),
                        estado='pendiente',
                        costo=float(costo_total),
                        trabajo=f"Orden automática desde cotización: {descr}"
                    )
                    with conectar() as conn:
                        conn.execute(
                            "INSERT INTO rentabilidad_productos (producto, costo_total, precio_venta, ganancia) VALUES (?,?,?,?)",
                            (str(descr), float(costo_total), float(precio_final), float(precio_final - costo_total))
                        )
                        conn.commit()
                    st.info(f"Orden de producción automática creada: #{oid_auto}")
                except Exception:
                    pass

                # Limpiamos datos temporales de cotización
                st.session_state.pop('datos_pre_cotizacion', None)

                cargar_datos()
                st.rerun()

            else:
                st.error(msg)

        except Exception as e:
            st.error(f"Error procesando venta: {e}")



# ===========================================================
# 🛒 MÓDULO DE VENTA DIRECTA - INTEGRADO CON NÚCLEO GLOBAL
# ===========================================================
if menu == "🛒 Venta Directa":

    st.title("🛒 Venta Rápida de Materiales")

    df_inv = st.session_state.get('df_inv', pd.DataFrame())
    df_cli = st.session_state.get('df_cli', pd.DataFrame())
    usuario_actual = st.session_state.get("usuario_nombre", "Sistema")

    if df_inv.empty:
        st.warning("No hay inventario cargado.")
        st.stop()

    disponibles = df_inv[df_inv['cantidad'] > 0]

    if disponibles.empty:
        st.warning("⚠️ No hay productos con stock disponible.")
        st.stop()

    with st.container(border=True):
        c1, c2 = st.columns([2, 1])
        prod_sel = c1.selectbox(
            "📦 Seleccionar Producto:",
            disponibles['item'].tolist(),
            key="venta_directa_producto"
        )

        datos = disponibles[disponibles['item'] == prod_sel].iloc[0]
        id_producto = int(datos['id'])
        stock_actual = float(datos['cantidad'])
        precio_base = float(datos['precio_usd'])
        unidad = str(datos['unidad'])
        minimo = float(datos['minimo'])

        c2.metric("Stock Disponible", f"{stock_actual:.2f} {unidad}")

    with st.form("form_venta_directa_modulo", clear_on_submit=True):
        st.subheader("Datos de la Venta")

        if not df_cli.empty:
            opciones_cli = {row['nombre']: row['id'] for _, row in df_cli.iterrows()}
            cliente_nombre = st.selectbox(
                "Cliente:",
                list(opciones_cli.keys()),
                key="venta_directa_cliente"
            )
            id_cliente = opciones_cli[cliente_nombre]
            fila_cli = df_cli[df_cli['id'] == id_cliente].iloc[0] if 'id' in df_cli.columns else None
            categoria_cli = str(fila_cli.get('categoria', 'General')) if fila_cli is not None else 'General'
        else:
            cliente_nombre = "Consumidor Final"
            id_cliente = None
            categoria_cli = 'General'
            st.info("Venta sin cliente registrado")

        c1, c2, c3 = st.columns(3)

        cantidad = c1.number_input(
            f"Cantidad ({unidad})",
            min_value=0.0,
            max_value=stock_actual,
            step=1.0,
            key="venta_directa_cantidad"
        )

        margen = c2.number_input("Margen %", value=30.0, key="venta_directa_margen")

        metodo = c3.selectbox(
            "Método de Pago",
            ["Efectivo $", "Pago Móvil (BCV)", "Transferencia (Bs)", "Kontigo", "Zelle", "Binance", "Pendiente"],
            key="venta_directa_metodo"
        )

        usa_desc = st.checkbox("Aplicar descuento cliente fiel", key="venta_directa_check_desc")
        desc = st.number_input(
            "Descuento %",
            value=5.0 if usa_desc else 0.0,
            disabled=not usa_desc,
            key="venta_directa_desc"
        )

        descuentos_categoria = {'General': 0.0, 'VIP': 10.0, 'Revendedor': 12.0}
        desc_categoria = float(descuentos_categoria.get(categoria_cli, 0.0))
        st.caption(f"Categoría cliente: {categoria_cli} | Descuento auto: {desc_categoria:.1f}%")

        st.write("Impuestos aplicables:")
        i1, i2 = st.columns(2)
        usa_iva = i1.checkbox("Aplicar IVA", key="venta_directa_iva")
        usa_banco = i2.checkbox("Comisión bancaria", value=True, key="venta_directa_banco")

        costo_material = cantidad * precio_base
        con_margen = costo_material * (1 + margen / 100)
        desc_total = max(float(desc), desc_categoria)
        con_desc = con_margen * (1 - desc_total / 100)

        if not usa_banco and ('pago móvil' in metodo.lower() or 'pago movil' in metodo.lower() or 'transferencia' in metodo.lower() or 'kontigo' in metodo.lower() or 'zelle' in metodo.lower()):
            metodo_tmp = 'Efectivo'
        else:
            metodo_tmp = metodo

        recargo_urgente = st.selectbox('Recargo urgencia', ['0%', '25%', '50%'], index=0, key='venta_directa_urgencia')
        urg_pct = 50.0 if recargo_urgente == '50%' else (25.0 if recargo_urgente == '25%' else float(st.session_state.get('recargo_urgente_pct', 0.0)))
        precio_calc = calcular_precio_final(con_desc, metodo_tmp, usa_iva, recargo_urgencia=urg_pct)
        total_usd = float(precio_calc['total'])

        total_bs = 0.0
        if metodo in ["Pago Móvil (BCV)", "Transferencia (Bs)"]:
            total_bs = total_usd * float(st.session_state.get('tasa_bcv', 1.0))
        elif metodo == "Binance":
            total_bs = total_usd * float(st.session_state.get('tasa_binance', 1.0))

        st.divider()
        st.metric("Total a Cobrar", f"$ {total_usd:.2f}")
        if total_bs > 0:
            st.info(f"Equivalente: Bs {total_bs:,.2f}")

        submit_venta = st.form_submit_button("🚀 PROCESAR VENTA")

    if submit_venta:
        if cantidad <= 0:
            st.error("⚠️ Debes vender al menos una unidad.")
            st.stop()

        if cantidad > stock_actual:
            st.error("⚠️ No puedes vender más de lo que hay en inventario.")
            st.stop()

        consumos = {id_producto: cantidad}

        with st.status('Procesando venta y descontando inventario...', expanded=False) as estado_proc:
            exito, mensaje = registrar_venta_global(
                id_cliente=id_cliente,
                nombre_cliente=cliente_nombre,
                detalle=f"{cantidad} {unidad} de {prod_sel}",
                monto_usd=float(total_usd),
                metodo=metodo,
                consumos=consumos,
                usuario=usuario_actual,
                tiene_iva=usa_iva,
                recargo_urgencia=urg_pct
            )
            estado_proc.update(label='Proceso finalizado', state='complete')

        if exito:
            st.success(mensaje)
            if stock_actual - cantidad <= minimo:
                st.warning("⚠️ Producto quedó en nivel crítico")

            st.session_state.ultimo_ticket = {
                "cliente": cliente_nombre,
                "detalle": f"{cantidad} {unidad} de {prod_sel}",
                "total": total_usd,
                "metodo": metodo,
                "usuario": usuario_actual
            }
            st.rerun()
        else:
            st.error(mensaje)

    if 'ultimo_ticket' in st.session_state:
        st.divider()
        t = st.session_state.ultimo_ticket
        with st.expander("📄 Recibo de Venta", expanded=True):
            st.code(f"""
CLIENTE: {t['cliente']}
DETALLE: {t['detalle']}
TOTAL: $ {t['total']:.2f}
MÉTODO: {t['metodo']}
USUARIO: {t.get('usuario', 'N/D')}
""")
            if st.button("Cerrar Ticket", key="cerrar_ticket_venta_directa"):
                del st.session_state.ultimo_ticket
                st.rerun()


# ===========================================================
# 🔐 NÚCLEO CENTRAL DE REGISTRO DE VENTAS DEL IMPERIO
# ===========================================================

def registrar_venta_global(
    id_cliente=None,
    nombre_cliente="Consumidor Final",
    detalle="Venta general",
    monto_usd=0.0,
    metodo="Efectivo $",
    consumos=None,
    usuario=None,
    conn=None,
    tiene_iva=False,
    recargo_urgencia=0.0
):
    """
    FUNCIÓN MAESTRA DEL IMPERIO – VERSIÓN SEGURA Y TRANSACCIONAL
    """

    consumos = consumos or {}
    detalle_txt = str(detalle or '').strip()
    metodo_txt = str(metodo or 'Efectivo $').strip() or 'Efectivo $'
    nombre_cliente_txt = str(nombre_cliente or 'Consumidor Final').strip() or 'Consumidor Final'
    usuario_final = str(usuario or st.session_state.get("usuario_nombre", "Sistema")).strip() or "Sistema"

    monto_base = money(monto_usd)
    if monto_base <= 0:
        return False, "⚠️ El monto de la venta debe ser mayor a 0"
    if not detalle_txt:
        return False, "⚠️ El detalle de la venta no puede estar vacío"

    conn_local = conn
    conn_creada = False
    inicio_explicito = False
    savepoint_name = None

    try:
        if conn_local is None:
            conn_local = conectar()
            conn_creada = True

        cursor = conn_local.cursor()

        if conn_local.in_transaction:
            savepoint_name = f"sp_venta_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
            conn_local.execute(f"SAVEPOINT {savepoint_name}")
        else:
            conn_local.execute("BEGIN IMMEDIATE TRANSACTION")
            inicio_explicito = True

        precio_final = calcular_precio_final(
            costo_base=monto_base,
            metodo_pago=metodo_txt,
            tiene_iva=tiene_iva,
            recargo_urgencia=recargo_urgencia
        )
        monto_total = money(precio_final.get('total', 0.0))
        if monto_total <= 0:
            raise ValueError("Monto final inválido")

        if id_cliente is not None:
            id_cliente = int(id_cliente)
            existe_cli = cursor.execute(
                "SELECT id FROM clientes WHERE id = ? AND COALESCE(activo,1)=1",
                (id_cliente,)
            ).fetchone()
            if not existe_cli:
                raise ValueError("Cliente no encontrado en base de datos")

        consumos_normalizados = {}
        for item_id, cant in consumos.items():
            iid = int(item_id)
            qty = float(cant or 0.0)
            if qty <= 0:
                raise ValueError(f"Cantidad inválida para el insumo {iid}")
            consumos_normalizados[iid] = consumos_normalizados.get(iid, 0.0) + qty

        if consumos_normalizados:
            placeholders = ','.join(['?'] * len(consumos_normalizados))
            rows_stock = cursor.execute(
                f"""
                SELECT id, item, cantidad
                FROM inventario
                WHERE COALESCE(activo,1)=1
                  AND id IN ({placeholders})
                """,
                tuple(consumos_normalizados.keys())
            ).fetchall()
            stock_map = {int(r[0]): (str(r[1]), float(r[2] or 0.0)) for r in rows_stock}

            for item_id, cant in consumos_normalizados.items():
                data = stock_map.get(int(item_id))
                if not data:
                    raise ValueError(f"Insumo con ID {item_id} no existe")
                nombre_item, cantidad_disponible = data
                if cant > cantidad_disponible:
                    raise ValueError(f"Stock insuficiente para: {nombre_item}")

            for item_id, cant in consumos_normalizados.items():
                cursor.execute(
                    """
                    UPDATE inventario
                    SET cantidad = cantidad - ?,
                        ultima_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                      AND COALESCE(activo,1)=1
                      AND cantidad >= ?
                    """,
                    (float(cant), int(item_id), float(cant))
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Stock insuficiente para consumo concurrente (ID {item_id})")

                registrar_movimiento_inventario(
                    item_id=int(item_id),
                    tipo='SALIDA',
                    cantidad=float(cant),
                    motivo=f"Venta: {detalle_txt}",
                    usuario=usuario_final,
                    conn=conn_local
                )

        cursor.execute(
            """
            INSERT INTO ventas
            (cliente_id, cliente, detalle, monto_total, metodo, usuario)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                id_cliente,
                nombre_cliente_txt,
                detalle_txt,
                float(monto_total),
                metodo_txt,
                usuario_final
            )
        )

        registrar_log_actividad(conn_local, 'INSERT', 'ventas', usuario=usuario_final)

        if savepoint_name:
            conn_local.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        elif inicio_explicito or conn_creada:
            conn_local.commit()

        cargar_datos()
        return True, "✅ Venta procesada correctamente"

    except (sqlite3.DatabaseError, ValueError, TypeError) as e:
        try:
            if conn_local is not None:
                if savepoint_name:
                    conn_local.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    conn_local.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                elif inicio_explicito or conn_creada:
                    conn_local.rollback()
        except sqlite3.Error:
            pass
        return False, f"❌ Error de datos al procesar la venta: {str(e)}"

    except Exception as e:
        try:
            if conn_local is not None:
                if savepoint_name:
                    conn_local.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    conn_local.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                elif inicio_explicito or conn_creada:
                    conn_local.rollback()
        except sqlite3.Error:
            pass
        return False, f"❌ Error interno al procesar la venta: {str(e)}"

    finally:
        if conn_creada and conn_local is not None:
            conn_local.close()





















