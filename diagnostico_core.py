import json
import re
from typing import Dict

from activos_core import registrar_uso_activo
from funciones_db import get_conn, registrar_auditoria
from inventario_core import registrar_movimiento_inventario


def _extraer_niveles(texto: str) -> Dict[str, int]:
    patrones = {
        "C": r"(?:cian|cyan|c)\s*[:=\-]?\s*(\d{1,3})\s*%?",
        "M": r"(?:magenta|m)\s*[:=\-]?\s*(\d{1,3})\s*%?",
        "Y": r"(?:amarillo|yellow|y)\s*[:=\-]?\s*(\d{1,3})\s*%?",
        "K": r"(?:negro|black|k)\s*[:=\-]?\s*(\d{1,3})\s*%?",
    }
    niveles: Dict[str, int] = {}
    text = str(texto or "").lower()
    for canal, pattern in patrones.items():
        match = re.search(pattern, text)
        if not match:
            continue
        valor = int(match.group(1))
        if 0 <= valor <= 100:
            niveles[canal] = valor
    return niveles


def registrar_diagnostico_impresora(
    activo_id,
    hoja_texto,
    foto_texto,
    mapa_tinta_item_id,
    usuario="Sistema",
):
    niveles = {}
    niveles.update(_extraer_niveles(hoja_texto))

    for canal, val in _extraer_niveles(foto_texto).items():
        if canal in niveles:
            niveles[canal] = int(round((niveles[canal] + val) / 2))
        else:
            niveles[canal] = val

    if not niveles:
        raise ValueError("No se detectaron niveles válidos de tanques (0 a 100).")

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO diagnosticos_impresora(
                activo_id, hoja_diagnostico, foto_tanques, niveles_json, observacion
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                activo_id,
                str(hoja_texto),
                str(foto_texto),
                json.dumps(niveles, ensure_ascii=False),
                "Diagnóstico IA validado",
            ),
        )

        for canal, nivel in niveles.items():
            item_id = mapa_tinta_item_id.get(canal)
            if not item_id:
                continue
            consumo_estimado = max((100 - nivel) * 0.1, 0)
            if consumo_estimado <= 0:
                continue
            registrar_movimiento_inventario(
                item_id=item_id,
                tipo="SALIDA",
                cantidad=consumo_estimado,
                motivo=f"Diagnóstico IA tanque {canal}",
                referencia=f"DIAG-{activo_id}",
                usuario=usuario,
            )

        row = conn.execute(
            "SELECT vida_cabezal FROM activos WHERE id=?", (activo_id,)
        ).fetchone()
        actual = float(row["vida_cabezal"] or 0) if row else 0.0
        vida_cabezal_delta = (
            sum((100 - nivel) for nivel in niveles.values()) / max(len(niveles), 1)
        ) * 0.05
        nuevo = max(actual - vida_cabezal_delta, 0)

        conn.execute("UPDATE activos SET vida_cabezal=? WHERE id=?", (nuevo, activo_id))
        registrar_auditoria(
            conn,
            usuario,
            "Diagnóstico impresora IA",
            f"activo_id={activo_id},vida_cabezal={actual}",
            f"activo_id={activo_id},vida_cabezal={nuevo},niveles={niveles}",
        )

    registrar_uso_activo(
        activo_id,
        uso_incremental=1,
        usuario=usuario,
        referencia="DIAGNOSTICO_IA",
    )
    return niveles
