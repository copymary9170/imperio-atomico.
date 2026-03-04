
        'Y': r'(?:amarillo|yellow|y)\s*[:=\-]?\s*(\d{1,3})\s*%?',
        'K': r'(?:negro|black|k)\s*[:=\-]?\s*(\d{1,3})\s*%?',
    }
    niveles = {}
    text = str(texto or '').lower()
    for canal, pattern in patrones.items():
        m = re.search(pattern, text)
        if m:
            valor = int(m.group(1))
            if 0 <= valor <= 100:
                niveles[canal] = valor
    return niveles


def registrar_diagnostico_impresora(activo_id, hoja_texto, foto_texto, mapa_tinta_item_id, usuario='Sistema'):
    niveles = {}
    niveles.update(_extraer_niveles(hoja_texto))
    for canal, val in _extraer_niveles(foto_texto).items():
        niveles[canal] = int(round((niveles.get(canal, val) + val) / 2)) if canal in niveles else val

    if not niveles:
        raise ValueError('No se detectaron niveles válidos de tanques (0 a 100).')

    with get_conn() as conn:
        conn.execute(
            'INSERT INTO diagnosticos_impresora(activo_id, hoja_diagnostico, foto_tanques, niveles_json, observacion) VALUES (?, ?, ?, ?, ?)',
            (activo_id, str(hoja_texto), str(foto_texto), json.dumps(niveles, ensure_ascii=False), 'Diagnóstico IA validado'),
        )

        for canal, nivel in niveles.items():
            if canal in mapa_tinta_item_id:
                consumo_estimado = max((100 - nivel) * 0.1, 0)
                if consumo_estimado > 0:
                    registrar_movimiento_inventario(mapa_tinta_item_id[canal], 'SALIDA', consumo_estimado, motivo=f'Diagnóstico IA tanque {canal}', referencia=f'DIAG-{activo_id}', usuario=usuario)

        vida_cabezal_delta = sum((100 - n) for n in niveles.values()) / max(len(niveles), 1) * 0.05
        row = conn.execute('SELECT vida_cabezal FROM activos WHERE id=?', (activo_id,)).fetchone()
        actual = float(row['vida_cabezal'] or 0) if row else 0
        nuevo = max(actual - vida_cabezal_delta, 0)
        conn.execute('UPDATE activos SET vida_cabezal=? WHERE id=?', (nuevo, activo_id))
        registrar_auditoria(conn, usuario, 'Diagnóstico impresora IA', f'activo_id={activo_id},vida_cabezal={actual}', f'activo_id={activo_id},vida_cabezal={nuevo},niveles={niveles}')

    registrar_uso_activo(activo_id, uso_incremental=1, usuario=usuario, referencia='DIAGNOSTICO_IA')
    return niveles
