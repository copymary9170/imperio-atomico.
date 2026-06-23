from __future__ import annotations

import math
import pandas as pd

from database.connection import db_transaction
from services.inventario_profesional_service import ensure_schema, inventario_fisico


def listar_capacidad() -> pd.DataFrame:
    ensure_schema()
    stock = inventario_fisico()
    salida = []
    with db_transaction() as conn:
        recetas = conn.execute("SELECT id,nombre,rendimiento,unidad_rendimiento FROM recetas_inventario WHERE activo=1").fetchall()
        for receta in recetas:
            limites = []
            detalles = conn.execute("SELECT d.insumo_id,d.cantidad,d.merma_pct,i.nombre,i.tipo_fisico,i.unidad_base,i.ancho_cm,i.alto_cm FROM recetas_inventario_detalle d JOIN inventario i ON i.id=d.insumo_id WHERE d.receta_id=?", (int(receta['id']),)).fetchall()
            for d in detalles:
                fila = stock[stock['id'] == int(d['insumo_id'])]
                if fila.empty:
                    continue
                factor = 1.0
                tipo = str(d['tipo_fisico'] or 'unidad')
                unidad = str(d['unidad_base'] or 'unidad')
                if tipo == 'lamina':
                    if unidad in {'hoja','pliego'}:
                        factor = float(d['ancho_cm'] or 0) * float(d['alto_cm'] or 0)
                    elif unidad == 'm²':
                        factor = 10000.0
                elif tipo == 'rollo':
                    if unidad == 'm²':
                        factor = 10000.0
                    elif unidad == 'm':
                        factor = float(d['ancho_cm'] or 0) * 100.0
                    elif unidad == 'cm':
                        factor = float(d['ancho_cm'] or 0)
                elif tipo == 'volumen' and unidad == 'L':
                    factor = 1000.0
                elif tipo == 'peso' and unidad == 'kg':
                    factor = 1000.0
                consumo = float(d['cantidad'] or 0) * (1 + float(d['merma_pct'] or 0) / 100) * factor
                if consumo > 0:
                    capacidad = math.floor(float(fila.iloc[0]['disponible']) / consumo) * float(receta['rendimiento'] or 1)
                    limites.append((capacidad, str(d['nombre'])))
            salida.append({'receta': receta['nombre'], 'capacidad_producción': min((x[0] for x in limites), default=0), 'unidad': receta['unidad_rendimiento'], 'material_limitante': min(limites, default=(0,'Sin materiales'))[1]})
    return pd.DataFrame(salida)
