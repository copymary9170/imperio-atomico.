from funciones_db import get_conn, get_config
from inventario_core import registrar_movimiento_inventario
from activos_core import registrar_uso_activo


CALIDAD_FACTOR = {'borrador': 'factor_borrador', 'normal': 'factor_normal', 'alta': 'factor_alta'}
PAPEL_FACTOR = {'fotográfico': 'factor_papel_fotografico', 'bond': 'factor_papel_bond', 'adhesivo': 'factor_papel_adhesivo'}


def _factor_config(param):
    return float(get_config(param, '1.0') or 1.0)


def analizar_cmyk(item_ids, calidad='normal', tipo_papel='bond', impresora_id=None):
    if not item_ids:
        return []
    with get_conn() as conn:
        placeholders = ','.join(['?'] * len(item_ids))
        rows = conn.execute(
            f'''
            SELECT i.id, i.item, i.cantidad, i.perfil_color,
                   a.id as impresora_id, a.equipo as impresora
            FROM inventario i
            LEFT JOIN activos a ON a.id=?
            WHERE i.activo=1 AND i.imprimible_cmyk=1 AND i.id IN ({placeholders})
            ''',
            tuple([impresora_id] + item_ids),
        ).fetchall()

    calidad_factor = _factor_config(CALIDAD_FACTOR.get(calidad, 'factor_normal'))
    papel_factor = _factor_config(PAPEL_FACTOR.get(tipo_papel, 'factor_papel_bond'))
    perfil_factor = {'eco': 0.9, 'normal': 1.0, 'vivo': 1.2}

    salida = []
    for r in rows:
        pf = perfil_factor.get(str(r['perfil_color'] or 'normal').lower(), 1.0)
        consumo = calidad_factor * papel_factor * pf
        salida.append({'item_id': r['id'], 'item': r['item'], 'stock': float(r['cantidad'] or 0), 'consumo_estimado_ml': round(consumo, 4), 'impresora': r['impresora'] or 'No seleccionada', 'calidad': calidad, 'tipo_papel': tipo_papel})
    return salida


def _obtener_receta(proceso, producto):
    with get_conn() as conn:
        return conn.execute(
            '''
            SELECT id, item_id, consumo_unitario, unidad, activo_id, dureza_factor, area_factor
            FROM recetas_produccion
            WHERE activo=1 AND proceso=? AND producto=?
            ''',
            (proceso, producto),
        ).fetchall()


def _crear_orden(proceso, producto, cantidad, usuario, activo_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            'INSERT INTO ordenes_produccion(proceso, producto, cantidad, usuario, activo_id) VALUES (?,?,?,?,?)',
            (proceso, producto, cantidad, usuario, activo_id),
        )
        return cur.lastrowid


def _registrar_tiempo(orden_id, minutos, operador):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO tiempos_produccion(orden_id, inicio, fin, minutos_reales, operador)
            VALUES (?, datetime('now', ?), datetime('now'), ?, ?)
            ''',
            (orden_id, f'-{int(minutos)} minutes', float(minutos), operador),
        )


def ejecutar_produccion(proceso, producto, cantidad, usuario='Sistema', minutos_reales=0, area=1):
    cantidad = float(cantidad or 0)
    area = float(area or 1)
    if cantidad <= 0:
        raise ValueError('Cantidad de producción inválida.')

    receta = _obtener_receta(proceso, producto)
    if not receta:
        raise ValueError('No hay receta de producción activa para este producto.')

    activo_id = receta[0]['activo_id'] if receta[0]['activo_id'] else None
    orden_id = _crear_orden(proceso, producto, cantidad, usuario, activo_id=activo_id)

    for insumo in receta:
        consumo = float(insumo['consumo_unitario'] or 0) * cantidad
        if proceso.lower() == 'corte cameo':
            consumo *= float(insumo['dureza_factor'] or 1) * area * float(insumo['area_factor'] or 1)
        registrar_movimiento_inventario(insumo['item_id'], 'SALIDA', consumo, motivo=f'Consumo receta {proceso}', referencia=f'OP-{orden_id}', usuario=usuario)

    if activo_id:
        registrar_uso_activo(activo_id, uso_incremental=max(cantidad, minutos_reales or 0), usuario=usuario, referencia=f'OP-{orden_id}')

    _registrar_tiempo(orden_id, float(minutos_reales or 0), usuario)
    return orden_id
