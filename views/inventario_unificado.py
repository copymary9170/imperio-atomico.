from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.inventario_unificado_service import (
    TIPOS_USO,
    UNIDADES_BASE,
    crear_item_unificado,
    guardar_clasificacion_inventario,
    listar_inventario_unificado,
)

CATEGORIAS_SUGERIDAS = [
    "Papel", "Cartulina", "Foami", "Carpetas", "Papelería", "Tinta", "Consumible",
    "Sublimación", "Empaque", "Herramienta", "General",
]

PEGADO_EJEMPLO = """SKU=PAP-BOND-CARTA-75G
Nombre=Papel bond carta 75 g
Categoría=Papel
Tipo de uso=Ambos
Unidad base=hoja
Fraccionable=Sí
Marca=HP
Color=Blanco
Tamaño=Carta
Gramaje=75 g
Acabado=Mate
Ancho=21.59
Alto=27.94
Merma base=2
Margen izquierdo=0.30
Margen derecho=0.30
Margen superior=0.30
Margen inferior=0.30
Separación=0.20
Sangrado=0
Unidad compra=resma
Contenido compra=500
Proveedor=
Ubicación=
Stock inicial=0
Stock mínimo=100
Punto reorden=250
Stock ideal=1000
Stock máximo=5000
Costo=0
Precio=0
Observaciones=Papel bond blanco tamaño carta de 75 g, utilizado para impresiones, copias, documentos y venta por hoja. Presentación de compra: resma de 500 hojas.
"""

ALIASES = {
    "sku": "sku",
    "codigo": "sku",
    "código": "sku",
    "nombre": "nombre",
    "descripcion": "nombre",
    "descripción": "nombre",
    "categoria": "categoria",
    "categoría": "categoria",
    "tipo": "tipo_uso",
    "tipo de uso": "tipo_uso",
    "uso": "tipo_uso",
    "unidad": "unidad_base",
    "unidad base": "unidad_base",
    "unidad_base": "unidad_base",
    "fraccionable": "permite_fraccionamiento",
    "permite fraccionamiento": "permite_fraccionamiento",
    "marca": "marca",
    "color": "color",
    "tamano": "tamano",
    "tamaño": "tamano",
    "medida": "tamano",
    "nombre comercial": "tamano",
    "gramaje": "gramaje",
    "grosor": "gramaje",
    "acabado": "acabado",
    "ancho": "ancho_cm",
    "ancho cm": "ancho_cm",
    "alto": "alto_cm",
    "alto cm": "alto_cm",
    "merma": "merma_base_pct",
    "merma base": "merma_base_pct",
    "merma base adicional": "merma_base_pct",
    "margen izquierdo": "margen_izquierdo_cm",
    "margen derecho": "margen_derecho_cm",
    "margen superior": "margen_superior_cm",
    "margen inferior": "margen_inferior_cm",
    "separacion": "separacion_cm",
    "separación": "separacion_cm",
    "sangrado": "sangrado_cm",
    "unidad compra": "unidad_compra",
    "unidad de compra": "unidad_compra",
    "contenido": "contenido_compra",
    "contenido compra": "contenido_compra",
    "contenido por unidad de compra": "contenido_compra",
    "proveedor": "proveedor_principal",
    "proveedor principal": "proveedor_principal",
    "ubicacion": "ubicacion",
    "ubicación": "ubicacion",
    "stock": "stock_actual",
    "stock inicial": "stock_actual",
    "stock mínimo": "stock_minimo",
    "stock minimo": "stock_minimo",
    "mínimo": "stock_minimo",
    "minimo": "stock_minimo",
    "punto reorden": "punto_reorden",
    "punto de reorden": "punto_reorden",
    "stock ideal": "stock_ideal",
    "stock máximo": "stock_maximo",
    "stock maximo": "stock_maximo",
    "costo": "costo_unitario_usd",
    "costo unitario": "costo_unitario_usd",
    "costo unitario usd": "costo_unitario_usd",
    "precio": "precio_venta_usd",
    "precio venta": "precio_venta_usd",
    "precio venta usd": "precio_venta_usd",
    "observacion": "observaciones",
    "observación": "observaciones",
    "observaciones": "observaciones",
}

CSV_COLUMNS = [
    "sku", "nombre", "categoria", "marca", "color", "tamano", "ancho_cm", "alto_cm",
    "gramaje", "unidad_compra", "contenido_compra", "stock_minimo", "punto_reorden",
    "stock_ideal", "stock_maximo",
]

NUMERIC_FIELDS = {
    "stock_actual", "stock_minimo", "punto_reorden", "stock_ideal", "stock_maximo",
    "costo_unitario_usd", "precio_venta_usd", "ancho_cm", "alto_cm",
    "margen_izquierdo_cm", "margen_derecho_cm", "margen_superior_cm", "margen_inferior_cm",
    "separacion_cm", "sangrado_cm", "merma_base_pct", "contenido_compra",
}

DEFAULT_ITEM = {
    "sku": "",
    "nombre": "",
    "categoria": "General",
    "tipo_uso": "Ambos",
    "unidad_base": "unidad",
    "permite_fraccionamiento": True,
    "marca": "",
    "color": "",
    "tamano": "",
    "gramaje": "",
    "acabado": "",
    "ancho_cm": 0.0,
    "alto_cm": 0.0,
    "margen_izquierdo_cm": 0.0,
    "margen_derecho_cm": 0.0,
    "margen_superior_cm": 0.0,
    "margen_inferior_cm": 0.0,
    "separacion_cm": 0.0,
    "sangrado_cm": 0.0,
    "merma_base_pct": 0.0,
    "unidad_compra": "",
    "contenido_compra": 0.0,
    "proveedor_principal": "",
    "ubicacion": "",
    "stock_actual": 0.0,
    "stock_minimo": 0.0,
    "punto_reorden": 0.0,
    "stock_ideal": 0.0,
    "stock_maximo": 0.0,
    "costo_unitario_usd": 0.0,
    "precio_venta_usd": 0.0,
    "observaciones": "",
}


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace("$", "").replace("%", "")
    text = text.replace(" cm", "").replace("g", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0


def _to_bool(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"si", "sí", "s", "true", "1", "x", "yes", "y"}


def _normalize_key(key: str) -> str:
    key = str(key or "").strip().lower().replace("_", " ").replace(":", "")
    key = re.sub(r"\s+", " ", key)
    return ALIASES.get(key, key.replace(" ", "_"))


def _normalize_item(data: dict[str, Any]) -> dict[str, Any]:
    item = dict(DEFAULT_ITEM)
    for raw_key, raw_value in data.items():
        key = _normalize_key(raw_key)
        if key not in item:
            continue
        if key in NUMERIC_FIELDS:
            item[key] = _to_float(raw_value)
        elif key == "permite_fraccionamiento":
            item[key] = _to_bool(raw_value)
        elif key == "tipo_uso":
            value = str(raw_value or "Ambos").strip().title()
            item[key] = value if value in TIPOS_USO else "Ambos"
        elif key == "unidad_base":
            value = str(raw_value or "unidad").strip()
            item[key] = value if value in UNIDADES_BASE else value or "unidad"
        else:
            item[key] = str(raw_value or "").strip()

    if not item["categoria"]:
        item["categoria"] = "General"
    if not item["unidad_base"]:
        item["unidad_base"] = "unidad"
    if not item["tipo_uso"]:
        item["tipo_uso"] = "Ambos"
    return item


def _parse_key_value_text(text: str) -> list[dict[str, Any]]:
    current: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                items.append(_normalize_item(current))
                current = {}
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        current[key.strip()] = value.strip()
    if current:
        items.append(_normalize_item(current))
    return items


def _parse_csv_text(text: str) -> list[dict[str, Any]]:
    sample = text.strip()
    if not sample:
        return []
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(sample), delimiter=delimiter))
    if not rows:
        return []
    header = [_normalize_key(col) for col in rows[0]]
    has_header = any(col in DEFAULT_ITEM for col in header)
    items: list[dict[str, Any]] = []
    if has_header:
        for row in rows[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            data = {header[i]: row[i] if i < len(row) else "" for i in range(len(header))}
            items.append(_normalize_item(data))
    else:
        for row in rows:
            if not any(str(cell).strip() for cell in row):
                continue
            data = {CSV_COLUMNS[i]: row[i] if i < len(row) else "" for i in range(min(len(CSV_COLUMNS), len(row)))}
            items.append(_normalize_item(data))
    return items


def _parse_pasted_items(text: str) -> list[dict[str, Any]]:
    text = str(text or "").strip()
    if not text:
        return []
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return [_normalize_item(loaded)]
        if isinstance(loaded, list):
            return [_normalize_item(item) for item in loaded if isinstance(item, dict)]
    except Exception:
        pass
    if "," in text or ";" in text or "\t" in text:
        parsed = _parse_csv_text(text.replace("\t", ","))
        if parsed and parsed[0].get("sku"):
            return parsed
    return _parse_key_value_text(text)


def _calcular_areas(values: dict) -> tuple[float, float, float]:
    ancho = max(float(values.get("ancho_cm") or 0), 0)
    alto = max(float(values.get("alto_cm") or 0), 0)
    ancho_util = max(ancho - float(values.get("margen_izquierdo_cm") or 0) - float(values.get("margen_derecho_cm") or 0), 0)
    alto_util = max(alto - float(values.get("margen_superior_cm") or 0) - float(values.get("margen_inferior_cm") or 0), 0)
    area_total = ancho * alto
    area_util = ancho_util * alto_util
    merma = (100 - (area_util / area_total * 100)) if area_total > 0 else 0
    return area_total, area_util, merma


def _data_para_crear(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": item.get("sku", ""),
        "nombre": item.get("nombre", ""),
        "categoria": item.get("categoria", "General"),
        "tipo_uso": item.get("tipo_uso", "Ambos"),
        "unidad_base": item.get("unidad_base", "unidad"),
        "permite_fraccionamiento": bool(item.get("permite_fraccionamiento", True)),
        "stock_actual": item.get("stock_actual", 0),
        "stock_minimo": item.get("stock_minimo", 0),
        "costo_unitario_usd": item.get("costo_unitario_usd", 0),
        "precio_venta_usd": item.get("precio_venta_usd", 0),
        "marca": item.get("marca", ""),
        "color": item.get("color", ""),
        "tamano": item.get("tamano", ""),
        "gramaje": item.get("gramaje", ""),
        "acabado": item.get("acabado", ""),
        "ancho_cm": item.get("ancho_cm", 0),
        "alto_cm": item.get("alto_cm", 0),
        "margen_izquierdo_cm": item.get("margen_izquierdo_cm", 0),
        "margen_derecho_cm": item.get("margen_derecho_cm", 0),
        "margen_superior_cm": item.get("margen_superior_cm", 0),
        "margen_inferior_cm": item.get("margen_inferior_cm", 0),
        "separacion_cm": item.get("separacion_cm", 0),
        "sangrado_cm": item.get("sangrado_cm", 0),
        "merma_base_pct": item.get("merma_base_pct", 0),
        "unidad_compra": item.get("unidad_compra", ""),
        "contenido_compra": item.get("contenido_compra", 0),
        "proveedor_principal": item.get("proveedor_principal", ""),
        "ubicacion": item.get("ubicacion", ""),
        "stock_ideal": item.get("stock_ideal", 0),
        "stock_maximo": item.get("stock_maximo", 0),
        "punto_reorden": item.get("punto_reorden", 0),
        "observaciones": item.get("observaciones", ""),
    }


def _actualizar_articulo(item_id: int, values: dict, usuario: str) -> None:
    with db_transaction() as conn:
        duplicado = conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?) AND id<>?", (values["sku"].strip(), int(item_id))).fetchone()
        if duplicado:
            raise ValueError("Ya existe otro artículo con ese SKU.")
        conn.execute("""
            UPDATE inventario SET sku=?, nombre=?, categoria=?, unidad=?, unidad_base=?, tipo_uso=?,
            permite_fraccionamiento=?, stock_minimo=?, punto_reorden=?, stock_ideal=?, stock_maximo=?,
            costo_unitario_usd=?, precio_venta_usd=?, marca=?, color=?, tamano=?, gramaje=?, acabado=?,
            ancho_cm=?, alto_cm=?, margen_izquierdo_cm=?, margen_derecho_cm=?, margen_superior_cm=?,
            margen_inferior_cm=?, separacion_cm=?, sangrado_cm=?, merma_base_pct=?,
            unidad_compra=?, contenido_compra=?, proveedor_principal=?, ubicacion=?, observaciones=?,
            actualizado_por=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?
        """, (
            values["sku"].strip(), values["nombre"].strip(), values["categoria"].strip(), values["unidad_base"],
            values["unidad_base"], values["tipo_uso"], 1 if values["fraccionable"] else 0,
            values["stock_minimo"], values["punto_reorden"], values["stock_ideal"], values["stock_maximo"],
            values["costo"], values["precio"], values["marca"].strip(), values["color"].strip(),
            values["tamano"].strip(), values["gramaje"].strip(), values["acabado"].strip(),
            values["ancho_cm"], values["alto_cm"], values["margen_izquierdo_cm"], values["margen_derecho_cm"],
            values["margen_superior_cm"], values["margen_inferior_cm"], values["separacion_cm"],
            values["sangrado_cm"], values["merma_base_pct"], values["unidad_compra"],
            values["contenido_compra"], values["proveedor"].strip(), values["ubicacion"].strip(),
            values["observaciones"].strip(), usuario, int(item_id),
        ))


def _cambiar_estado(item_id: int, estado: str, usuario: str) -> None:
    with db_transaction() as conn:
        conn.execute("UPDATE inventario SET estado=?, actualizado_por=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?", (estado, usuario, int(item_id)))


def _render_pegar_datos(usuario: str) -> None:
    st.info("Pega datos en formato campo=valor, JSON o CSV. Luego revisa la vista previa y crea el artículo sin llenar todo a mano.")
    col_a, col_b = st.columns([2, 1])
    with col_a:
        texto = st.text_area("Pegar datos del artículo", height=360, placeholder=PEGADO_EJEMPLO, key="inventario_pegado_texto")
    with col_b:
        st.markdown("#### Ejemplo rápido")
        st.code(PEGADO_EJEMPLO, language="text")

    if not texto.strip():
        return

    items = _parse_pasted_items(texto)
    if not items:
        st.warning("No pude interpretar el texto. Usa formato SKU=..., Nombre=..., Categoría=...")
        return

    st.markdown("#### Vista previa")
    preview_cols = ["sku", "nombre", "categoria", "marca", "color", "tamano", "ancho_cm", "alto_cm", "gramaje", "unidad_base", "unidad_compra", "contenido_compra", "stock_minimo", "punto_reorden", "stock_ideal", "stock_maximo"]
    st.dataframe(pd.DataFrame(items)[preview_cols], use_container_width=True, hide_index=True)

    if len(items) == 1:
        item = items[0]
        area_total, area_util, merma = _calcular_areas(item)
        c1, c2, c3 = st.columns(3)
        c1.metric("Área total", f"{area_total:.2f} cm²")
        c2.metric("Área útil", f"{area_util:.2f} cm²")
        c3.metric("Merma por márgenes", f"{merma:.2f}%")

    confirmar = st.checkbox("Confirmo que revisé la vista previa y deseo crear estos artículos", key="confirmar_pegado_inventario")
    if st.button("⚡ Crear desde pegado", type="primary", use_container_width=True, disabled=not confirmar):
        creados = 0
        errores: list[str] = []
        for item in items:
            try:
                crear_item_unificado(_data_para_crear(item), usuario)
                creados += 1
            except Exception as exc:
                errores.append(f"{item.get('sku') or item.get('nombre')}: {exc}")
        if creados:
            st.success(f"Se crearon {creados} artículo(s).")
        if errores:
            st.error("Algunos artículos no se pudieron crear:")
            for error in errores:
                st.write(f"- {error}")
        if creados and not errores:
            st.rerun()


def _render_form_crear(usuario: str) -> None:
    st.info("Si registrarás una factura de compra, deja el stock inicial y el costo en 0 para evitar duplicar existencias.")
    with st.form("form_crear_item_unificado"):
        st.markdown("#### Identificación")
        c1, c2, c3 = st.columns(3)
        sku = c1.text_input("SKU *", placeholder="Ej.: PAP-BOND-CARTA-75G")
        nombre = c2.text_input("Nombre *", placeholder="Ej.: Papel bond carta 75 g")
        categoria_sel = c3.selectbox("Categoría", CATEGORIAS_SUGERIDAS, index=CATEGORIAS_SUGERIDAS.index("General"))
        categoria_otro = st.text_input("Otra categoría")
        categoria = categoria_otro.strip() or categoria_sel
        d1, d2, d3 = st.columns(3)
        tipo_uso = d1.selectbox("Tipo de uso", TIPOS_USO, index=2)
        unidad_base = d2.selectbox("Unidad base", UNIDADES_BASE)
        fraccionable = d3.checkbox("Permite fraccionamiento", value=True)

        st.markdown("#### Características")
        a1, a2, a3, a4, a5 = st.columns(5)
        marca = a1.text_input("Marca")
        color = a2.text_input("Color")
        tamano = a3.text_input("Nombre comercial del tamaño", placeholder="Ej.: Carta")
        gramaje = a4.text_input("Gramaje / grosor")
        acabado = a5.text_input("Acabado")

        st.markdown("#### Dimensiones y aprovechamiento")
        st.caption("Estas medidas se usarán para calcular área útil y merma. Registra todo en centímetros.")
        m1, m2, m3 = st.columns(3)
        ancho_cm = m1.number_input("Ancho del material (cm)", min_value=0.0, step=0.01, format="%.2f")
        alto_cm = m2.number_input("Alto del material (cm)", min_value=0.0, step=0.01, format="%.2f")
        merma_base_pct = m3.number_input("Merma base adicional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
        n1, n2, n3, n4 = st.columns(4)
        margen_izquierdo_cm = n1.number_input("Margen izquierdo (cm)", min_value=0.0, step=0.01, format="%.2f")
        margen_derecho_cm = n2.number_input("Margen derecho (cm)", min_value=0.0, step=0.01, format="%.2f")
        margen_superior_cm = n3.number_input("Margen superior (cm)", min_value=0.0, step=0.01, format="%.2f")
        margen_inferior_cm = n4.number_input("Margen inferior (cm)", min_value=0.0, step=0.01, format="%.2f")
        p1, p2 = st.columns(2)
        separacion_cm = p1.number_input("Separación entre piezas (cm)", min_value=0.0, step=0.01, format="%.2f")
        sangrado_cm = p2.number_input("Sangrado por lado (cm)", min_value=0.0, step=0.01, format="%.2f")
        area_total, area_util, merma_dimensional = _calcular_areas(locals())
        q1, q2, q3 = st.columns(3)
        q1.metric("Área total", f"{area_total:.2f} cm²")
        q2.metric("Área útil", f"{area_util:.2f} cm²")
        q3.metric("Merma por márgenes", f"{merma_dimensional:.2f}%")

        st.markdown("#### Compra y almacenamiento")
        b1, b2, b3, b4 = st.columns(4)
        unidad_compra = b1.selectbox("Unidad de compra", [""] + UNIDADES_BASE)
        contenido_compra = b2.number_input("Contenido por unidad de compra", min_value=0.0, step=1.0, format="%.4f")
        proveedor_principal = b3.text_input("Proveedor principal")
        ubicacion = b4.text_input("Ubicación")

        st.markdown("#### Control de existencias")
        e1, e2, e3, e4 = st.columns(4)
        stock_actual = e1.number_input("Stock inicial", min_value=0.0, step=1.0, format="%.4f")
        stock_minimo = e2.number_input("Stock mínimo", min_value=0.0, step=1.0, format="%.4f")
        punto_reorden = e3.number_input("Punto de reorden", min_value=0.0, step=1.0, format="%.4f")
        stock_ideal = e4.number_input("Stock ideal", min_value=0.0, step=1.0, format="%.4f")
        stock_maximo = st.number_input("Stock máximo", min_value=0.0, step=1.0, format="%.4f")
        f1, f2 = st.columns(2)
        costo = f1.number_input("Costo unitario USD", min_value=0.0, step=0.01, format="%.4f")
        precio = f2.number_input("Precio venta USD", min_value=0.0, step=0.01, format="%.4f")
        observaciones = st.text_area("Observaciones")
        guardar = st.form_submit_button("Crear artículo", type="primary", use_container_width=True)

    if guardar:
        try:
            item_id = crear_item_unificado({
                "sku": sku, "nombre": nombre, "categoria": categoria, "tipo_uso": tipo_uso,
                "unidad_base": unidad_base, "permite_fraccionamiento": fraccionable,
                "stock_actual": stock_actual, "stock_minimo": stock_minimo,
                "costo_unitario_usd": costo, "precio_venta_usd": precio,
                "marca": marca, "color": color, "tamano": tamano, "gramaje": gramaje,
                "acabado": acabado, "ancho_cm": ancho_cm, "alto_cm": alto_cm,
                "margen_izquierdo_cm": margen_izquierdo_cm, "margen_derecho_cm": margen_derecho_cm,
                "margen_superior_cm": margen_superior_cm, "margen_inferior_cm": margen_inferior_cm,
                "separacion_cm": separacion_cm, "sangrado_cm": sangrado_cm,
                "merma_base_pct": merma_base_pct, "unidad_compra": unidad_compra,
                "contenido_compra": contenido_compra, "proveedor_principal": proveedor_principal,
                "ubicacion": ubicacion, "stock_ideal": stock_ideal, "stock_maximo": stock_maximo,
                "punto_reorden": punto_reorden, "observaciones": observaciones,
            }, usuario)
            st.success(f"Artículo #{item_id} creado.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo crear: {exc}")


def _render_editar(usuario: str) -> None:
    df = listar_inventario_unificado(activos_only=False)
    if df.empty:
        st.info("No hay artículos para editar.")
        return
    opciones = {f"#{int(r['id'])} · {r['nombre']} · {r['sku']}": r for _, r in df.iterrows()}
    seleccion = st.selectbox("Artículo a editar", list(opciones.keys()), key="editar_item_inventario")
    row = opciones[seleccion]
    with st.form("form_editar_item_unificado"):
        c1, c2, c3 = st.columns(3)
        sku_e = c1.text_input("SKU *", value=str(row["sku"] or ""))
        nombre_e = c2.text_input("Nombre *", value=str(row["nombre"] or ""))
        categoria_e = c3.text_input("Categoría", value=str(row["categoria"] or "General"))
        d1, d2, d3 = st.columns(3)
        tipo_e = d1.selectbox("Tipo de uso", TIPOS_USO, index=TIPOS_USO.index(str(row["tipo_uso"])) if str(row["tipo_uso"]) in TIPOS_USO else 2)
        unidades = list(UNIDADES_BASE)
        unidad_actual = str(row["unidad_base"] or "unidad")
        if unidad_actual not in unidades:
            unidades.insert(0, unidad_actual)
        unidad_e = d2.selectbox("Unidad base", unidades, index=unidades.index(unidad_actual))
        fracc_e = d3.checkbox("Permite fraccionamiento", value=bool(int(row["permite_fraccionamiento"] or 0)))

        a1, a2, a3, a4, a5 = st.columns(5)
        marca_e = a1.text_input("Marca", value=str(row["marca"] or ""))
        color_e = a2.text_input("Color", value=str(row["color"] or ""))
        tamano_e = a3.text_input("Nombre comercial del tamaño", value=str(row["tamano"] or ""))
        gramaje_e = a4.text_input("Gramaje / grosor", value=str(row["gramaje"] or ""))
        acabado_e = a5.text_input("Acabado", value=str(row["acabado"] or ""))

        st.markdown("#### Dimensiones y aprovechamiento")
        m1, m2, m3 = st.columns(3)
        ancho_e = m1.number_input("Ancho del material (cm)", min_value=0.0, value=float(row["ancho_cm"] or 0), step=0.01, format="%.2f")
        alto_e = m2.number_input("Alto del material (cm)", min_value=0.0, value=float(row["alto_cm"] or 0), step=0.01, format="%.2f")
        merma_base_e = m3.number_input("Merma base adicional (%)", min_value=0.0, max_value=100.0, value=float(row["merma_base_pct"] or 0), step=0.1, format="%.2f")
        n1, n2, n3, n4 = st.columns(4)
        mi_e = n1.number_input("Margen izquierdo (cm)", min_value=0.0, value=float(row["margen_izquierdo_cm"] or 0), step=0.01, format="%.2f")
        md_e = n2.number_input("Margen derecho (cm)", min_value=0.0, value=float(row["margen_derecho_cm"] or 0), step=0.01, format="%.2f")
        ms_e = n3.number_input("Margen superior (cm)", min_value=0.0, value=float(row["margen_superior_cm"] or 0), step=0.01, format="%.2f")
        minf_e = n4.number_input("Margen inferior (cm)", min_value=0.0, value=float(row["margen_inferior_cm"] or 0), step=0.01, format="%.2f")
        p1, p2 = st.columns(2)
        separacion_e = p1.number_input("Separación entre piezas (cm)", min_value=0.0, value=float(row["separacion_cm"] or 0), step=0.01, format="%.2f")
        sangrado_e = p2.number_input("Sangrado por lado (cm)", min_value=0.0, value=float(row["sangrado_cm"] or 0), step=0.01, format="%.2f")

        b1, b2, b3, b4 = st.columns(4)
        uc_actual = str(row["unidad_compra"] or "")
        uc_opts = [""] + UNIDADES_BASE
        if uc_actual not in uc_opts:
            uc_opts.insert(1, uc_actual)
        uc_e = b1.selectbox("Unidad de compra", uc_opts, index=uc_opts.index(uc_actual))
        contenido_e = b2.number_input("Contenido por unidad de compra", min_value=0.0, value=float(row["contenido_compra"] or 0), step=1.0)
        proveedor_e = b3.text_input("Proveedor principal", value=str(row["proveedor_principal"] or ""))
        ubicacion_e = b4.text_input("Ubicación", value=str(row["ubicacion"] or ""))
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Stock actual", f"{float(row['stock_actual'] or 0):g} {unidad_actual}")
        minimo_e = e2.number_input("Stock mínimo", min_value=0.0, value=float(row["stock_minimo"] or 0), step=1.0)
        reorden_e = e3.number_input("Punto de reorden", min_value=0.0, value=float(row["punto_reorden"] or 0), step=1.0)
        ideal_e = e4.number_input("Stock ideal", min_value=0.0, value=float(row["stock_ideal"] or 0), step=1.0)
        maximo_e = st.number_input("Stock máximo", min_value=0.0, value=float(row["stock_maximo"] or 0), step=1.0)
        f1, f2 = st.columns(2)
        costo_e = f1.number_input("Costo unitario USD", min_value=0.0, value=float(row["costo_unitario_usd"] or 0), step=0.01, format="%.4f")
        precio_e = f2.number_input("Precio venta USD", min_value=0.0, value=float(row["precio_venta_usd"] or 0), step=0.01, format="%.4f")
        obs_e = st.text_area("Observaciones", value=str(row["observaciones"] or ""))
        actualizar = st.form_submit_button("Guardar cambios", type="primary", use_container_width=True)

    if actualizar:
        try:
            _actualizar_articulo(int(row["id"]), {
                "sku": sku_e, "nombre": nombre_e, "categoria": categoria_e, "tipo_uso": tipo_e,
                "unidad_base": unidad_e, "fraccionable": fracc_e, "stock_minimo": minimo_e,
                "punto_reorden": reorden_e, "stock_ideal": ideal_e, "stock_maximo": maximo_e,
                "costo": costo_e, "precio": precio_e, "marca": marca_e, "color": color_e,
                "tamano": tamano_e, "gramaje": gramaje_e, "acabado": acabado_e,
                "ancho_cm": ancho_e, "alto_cm": alto_e, "margen_izquierdo_cm": mi_e,
                "margen_derecho_cm": md_e, "margen_superior_cm": ms_e,
                "margen_inferior_cm": minf_e, "separacion_cm": separacion_e,
                "sangrado_cm": sangrado_e, "merma_base_pct": merma_base_e,
                "unidad_compra": uc_e, "contenido_compra": contenido_e,
                "proveedor": proveedor_e, "ubicacion": ubicacion_e, "observaciones": obs_e,
            }, usuario)
            st.success("Artículo actualizado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar: {exc}")

    st.divider()
    estado_actual = str(row["estado"] or "activo").lower()
    st.warning("Desactivar conserva el artículo y su historial, pero evita utilizarlo como artículo activo.")
    if estado_actual == "activo":
        confirmar = st.checkbox("Confirmo que deseo desactivar este artículo", key=f"confirmar_desactivar_{int(row['id'])}")
        if st.button("Desactivar artículo", disabled=not confirmar, use_container_width=True):
            _cambiar_estado(int(row["id"]), "inactivo", usuario)
            st.success("Artículo desactivado.")
            st.rerun()
    else:
        if st.button("Reactivar artículo", use_container_width=True):
            _cambiar_estado(int(row["id"]), "activo", usuario)
            st.success("Artículo reactivado.")
            st.rerun()


def _render_clasificar() -> None:
    df = listar_inventario_unificado(activos_only=False)
    if df.empty:
        st.info("No hay artículos para clasificar.")
        return
    opciones = {f"#{int(row['id'])} - {row['nombre']} - {row['tipo_uso']}": row for _, row in df.iterrows()}
    seleccion = st.selectbox("Artículo", list(opciones.keys()))
    row = opciones[seleccion]
    tipo_actual = str(row.get("tipo_uso") or "Ambos")
    unidad_actual = str(row.get("unidad_base") or row.get("unidad") or "unidad")
    unidades = list(UNIDADES_BASE)
    if unidad_actual not in unidades:
        unidades.insert(0, unidad_actual)
    with st.form("form_clasificar_item"):
        c1, c2, c3 = st.columns(3)
        tipo_nuevo = c1.selectbox("Tipo de uso", TIPOS_USO, index=TIPOS_USO.index(tipo_actual) if tipo_actual in TIPOS_USO else 2)
        unidad_nueva = c2.selectbox("Unidad base", unidades, index=unidades.index(unidad_actual))
        fraccionable_nuevo = c3.checkbox("Permite fraccionamiento", value=bool(int(row.get("permite_fraccionamiento") or 0)))
        guardar_cambio = st.form_submit_button("Guardar clasificación", type="primary", use_container_width=True)
    if guardar_cambio:
        try:
            guardar_clasificacion_inventario(int(row["id"]), tipo_uso=tipo_nuevo, unidad_base=unidad_nueva, permite_fraccionamiento=fraccionable_nuevo)
            st.success("Clasificación actualizada.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar: {exc}")


def render_inventario_unificado(usuario: str) -> None:
    st.subheader("Inventario unificado")
    st.caption("Un mismo artículo puede ser insumo, producto de reventa o ambos.")
    tab_lista, tab_pegar, tab_crear, tab_editar, tab_clasificar = st.tabs(["Existencias", "📋 Pegar datos", "Crear artículo", "Editar / desactivar", "Clasificar"])

    with tab_lista:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("Aún no hay artículos.")
        else:
            filtro = st.multiselect("Tipo de uso", TIPOS_USO, default=TIPOS_USO)
            vista = df[df["tipo_uso"].isin(filtro)] if filtro else df.iloc[0:0]
            mostrar = vista.copy()
            mostrar["fraccionable"] = mostrar["permite_fraccionamiento"].astype(int).map({1: "Sí", 0: "No"})
            cols = ["id", "sku", "nombre", "categoria", "marca", "color", "tamano", "ancho_cm", "alto_cm", "area_total_cm2", "area_util_cm2", "merma_dimensional_pct", "merma_base_pct", "tipo_uso", "unidad_base", "unidad_compra", "fraccionable", "stock_actual", "stock_minimo", "punto_reorden", "stock_ideal", "costo_unitario_usd", "precio_venta_usd", "ubicacion", "estado"]
            st.dataframe(mostrar[cols], use_container_width=True, hide_index=True)

    with tab_pegar:
        _render_pegar_datos(usuario)

    with tab_crear:
        _render_form_crear(usuario)

    with tab_editar:
        _render_editar(usuario)

    with tab_clasificar:
        _render_clasificar()
