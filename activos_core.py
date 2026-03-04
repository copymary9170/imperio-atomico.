from funciones_db import get_conn, registrar_auditoria


def obtener_activo_seleccionado(tipo='impresora'):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM activos WHERE activo=1 AND tipo=? AND seleccionada=1 ORDER BY id DESC LIMIT 1',
            (tipo,),
        ).fetchone()
        return row


def registrar_uso_activo(activo_id, uso_incremental, usuario='Sistema', referencia='PRODUCCION'):
    uso_incremental = float(uso_incremental or 0)
    if uso_incremental <= 0:
        return False, 'Uso inválido'

    with get_conn() as conn:
        row = conn.execute('SELECT id, equipo, vida_total, uso_actual, vida_restante, desgaste FROM activos WHERE id=?', (activo_id,)).fetchone()
        if not row:
            return False, 'Activo no existe'

        uso_actual = float(row['uso_actual'] or 0) + uso_incremental
        vida_total = float(row['vida_total'] or 0)
        vida_restante = max(vida_total - uso_actual, 0) if vida_total > 0 else 0
        desgaste = (uso_actual / vida_total) * 100 if vida_total > 0 else float(row['desgaste'] or 0)

        conn.execute(
            'UPDATE activos SET uso_actual=?, vida_restante=?, desgaste=? WHERE id=?',
            (uso_actual, vida_restante, desgaste, activo_id),
        )
        registrar_auditoria(
            conn,
            usuario,
            'Actualizar uso activo',
            f'activo_id={activo_id},uso_previo={row["uso_actual"]}',
            f'activo_id={activo_id},uso_nuevo={uso_actual},ref={referencia}',
        )

        alerta = vida_total > 0 and uso_actual > vida_total
        return True, ('ALERTA: vida útil excedida' if alerta else 'OK')
