rom funciones_db import get_conn, get_config, registrar_auditoria, now_iso


def obtener_stock(item_id):
    with get_conn() as conn:
        row = conn.execute('SELECT cantidad FROM inventario WHERE id=?', (item_id,)).fetchone()
        return float(row['cantidad']) if row else 0.0


def registrar_movimiento_inventario(item_id, tipo, cantidad, motivo='', referencia='', usuario='Sistema'):
    cantidad = float(cantidad or 0)
    if cantidad <= 0:
        raise ValueError('La cantidad debe ser mayor a cero.')

    tipo = str(tipo).upper().strip()
    if tipo not in ('ENTRADA', 'SALIDA', 'AJUSTE_POSITIVO', 'AJUSTE_NEGATIVO', 'MERMA'):
        raise ValueError('Tipo de movimiento inválido.')

    with get_conn() as conn:
        item = conn.execute('SELECT id, item, cantidad, precio_usd FROM inventario WHERE id=?', (item_id,)).fetchone()
        if not item:
            raise ValueError('Insumo no encontrado en inventario.')

        anterior = float(item['cantidad'] or 0)
        signo = -1 if tipo in ('SALIDA', 'AJUSTE_NEGATIVO', 'MERMA') else 1
        nuevo = anterior + (signo * cantidad)

        no_negativo = get_config('stock_no_negativo', '1') == '1'
        if no_negativo and nuevo < 0:
            raise ValueError('Stock insuficiente: el stock no puede ser negativo.')

        conn.execute(
            'UPDATE inventario SET cantidad=?, ultima_actualizacion=? WHERE id=?',
            (max(nuevo, 0.0) if no_negativo else nuevo, now_iso(), item_id),
        )

        conn.execute(
            '''
            INSERT INTO inventario_movs(item_id, tipo, cantidad, motivo, referencia, usuario)
            VALUES (?,?,?,?,?,?)
            ''',
            (item_id, tipo, cantidad, motivo, referencia, usuario),
        )

        entrada = cantidad if signo > 0 else 0
        salida = cantidad if signo < 0 else 0
        conn.execute(
            '''
            INSERT INTO kardex(item_id, entrada, salida, saldo, costo_unitario, referencia)
            VALUES (?,?,?,?,?,?)
            ''',
            (item_id, entrada, salida, max(nuevo, 0.0) if no_negativo else nuevo, float(item['precio_usd'] or 0), referencia),
        )

        registrar_auditoria(
            conn,
            usuario=usuario,
            accion=f'Movimiento inventario {tipo}',
            valor_anterior=f'item_id={item_id},stock={anterior}',
            valor_nuevo=f'item_id={item_id},stock={nuevo},cantidad={cantidad},motivo={motivo}',
        )


def aplicar_ajuste(item_id, nuevo_stock, motivo='Ajuste manual', usuario='Sistema'):
    actual = obtener_stock(item_id)
    delta = float(nuevo_stock) - float(actual)
    if delta > 0:
        registrar_movimiento_inventario(item_id, 'AJUSTE_POSITIVO', delta, motivo=motivo, referencia='AJUSTE', usuario=usuario)
    elif delta < 0:
        registrar_movimiento_inventario(item_id, 'AJUSTE_NEGATIVO', abs(delta), motivo=motivo, referencia='AJUSTE', usuario=usuario)


def alertas_minimos():
    with get_conn() as conn:
        return conn.execute(
            'SELECT id, item, cantidad, minimo, unidad FROM inventario WHERE activo=1 AND cantidad <= minimo ORDER BY cantidad ASC'
        ).fetchall()
