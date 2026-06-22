from __future__ import annotations

import streamlit as st

from services.inventario_unificado_service import TIPOS_USO, UNIDADES_BASE, crear_item_unificado
from services.proveedores_select_service import listar_proveedores_activos, opciones_proveedores_con_manual
import views.inventario_unificado as base

TIPOS_MEDICION = [
    "Hoja / material con medidas",
    "Peso",
    "Volumen",
    "Unidad simple",
]


def _selector_proveedor_principal() -> str:
    opciones, mapa = opciones_proveedores_con_manual()
    seleccion = st.selectbox("Proveedor principal", opciones, key="iu_proveedor_principal_select")
    if seleccion == "Escribir manualmente":
        return st.text_input("Proveedor principal manual", key="iu_proveedor_principal_manual").strip()
    if seleccion == "Sin proveedor":
        st.caption("Registra proveedores en el módulo 🏢 Proveedores para seleccionarlos aquí.")
    return mapa.get(seleccion, "")


def _tipo_medicion_sugerido(categoria: str, unidad_base: str) -> str:
    texto = f"{categoria} {unidad_base}".lower()
    if any(x in texto for x in ["papel", "cartulina", "foami", "hoja", "pliego", "acetato", "opalina"]):
        return "Hoja / material con medidas"
    if any(x in texto for x in ["g", "kg", "gramo", "kilo"]):
        return "Peso"
    if any(x in texto for x in ["ml", "l", "litro", "tinta"]):
        return "Volumen"
    return "Unidad simple"


def _normalizar_proveedor_pegado(nombre: str) -> str:
    proveedor = str(nombre or "").strip()
    if not proveedor:
        return ""
    proveedores = listar_proveedores_activos()
    if proveedores.empty:
        raise ValueError(f"Proveedor '{proveedor}' no existe. Primero créalo en 🏢 Proveedores o deja Proveedor vacío.")
    mapa = {str(row.get("nombre") or "").strip().casefold(): str(row.get("nombre") or "").strip() for _, row in proveedores.iterrows()}
    encontrado = mapa.get(proveedor.casefold())
    if encontrado:
        return encontrado
    disponibles = ", ".join([v for v in mapa.values()][:8])
    raise ValueError(f"Proveedor '{proveedor}' no existe en 🏢 Proveedores. Usa el nombre exacto. Disponibles: {disponibles}")


def _data_para_crear_validando_proveedor(item: dict) -> dict:
    data = dict(item)
    data["proveedor_principal"] = _normalizar_proveedor_pegado(data.get("proveedor_principal", ""))
    return data


def _render_form_crear_con_proveedor(usuario: str) -> None:
    st.info("Si registrarás una factura de compra, deja el stock inicial y el costo en 0 para evitar duplicar existencias.")
    with st.form("form_crear_item_unificado"):
        st.markdown("#### Identificación")
        c1, c2, c3 = st.columns(3)
        sku = c1.text_input("SKU *", placeholder="Ej.: PAP-BOND-CARTA-75G")
        nombre = c2.text_input("Nombre *", placeholder="Ej.: Papel bond carta 75 g")
        categoria = c3.selectbox("Categoría", base.CATEGORIAS_SUGERIDAS, index=base.CATEGORIAS_SUGERIDAS.index("General"))
        d1, d2, d3 = st.columns(3)
        tipo_uso = d1.selectbox("Tipo de uso", TIPOS_USO, index=2)
        unidad_base = d2.selectbox("Unidad base", UNIDADES_BASE)
        fraccionable = d3.checkbox("Permite fraccionamiento", value=True)

        tipo_sugerido = _tipo_medicion_sugerido(categoria, unidad_base)
        tipo_medicion = st.selectbox(
            "Cómo se mide este artículo",
            TIPOS_MEDICION,
            index=TIPOS_MEDICION.index(tipo_sugerido),
            help="Usa medidas solo para hojas, pliegos, foami, cartulina o materiales que se cortan. Para tintas usa volumen; para polvo o material pesado usa peso.",
        )

        st.markdown("#### Características")
        a1, a2, a3, a4 = st.columns(4)
        marca = a1.text_input("Marca")
        color = a2.text_input("Color")
        tamano = a3.text_input("Presentación / tamaño comercial", placeholder="Ej.: carta, oficio, botella 70 ml, bolsa 1 kg")
        acabado = a4.text_input("Acabado / tipo", placeholder="Ej.: mate, brillante, pigmentada")
        gramaje = ""

        ancho_cm = alto_cm = margen_izquierdo_cm = margen_derecho_cm = 0.0
        margen_superior_cm = margen_inferior_cm = separacion_cm = sangrado_cm = 0.0
        merma_base_pct = 0.0

        if tipo_medicion == "Hoja / material con medidas":
            st.markdown("#### Dimensiones y aprovechamiento")
            m1, m2, m3 = st.columns(3)
            ancho_cm = m1.number_input("Ancho del material (cm)", min_value=0.0, step=0.01, format="%.2f")
            alto_cm = m2.number_input("Alto del material (cm)", min_value=0.0, step=0.01, format="%.2f")
            gramaje = m3.text_input("Gramaje / grosor", placeholder="Ej.: 75 g, 180 g, 2 mm")
            usar_margenes = st.checkbox("Usar márgenes, separación o sangrado", value=False)
            if usar_margenes:
                n1, n2, n3, n4 = st.columns(4)
                margen_izquierdo_cm = n1.number_input("Margen izquierdo (cm)", min_value=0.0, step=0.01, format="%.2f")
                margen_derecho_cm = n2.number_input("Margen derecho (cm)", min_value=0.0, step=0.01, format="%.2f")
                margen_superior_cm = n3.number_input("Margen superior (cm)", min_value=0.0, step=0.01, format="%.2f")
                margen_inferior_cm = n4.number_input("Margen inferior (cm)", min_value=0.0, step=0.01, format="%.2f")
                p1, p2 = st.columns(2)
                separacion_cm = p1.number_input("Separación entre piezas (cm)", min_value=0.0, step=0.01, format="%.2f")
                sangrado_cm = p2.number_input("Sangrado por lado (cm)", min_value=0.0, step=0.01, format="%.2f")
            merma_base_pct = st.number_input("Merma adicional opcional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
            area_total, area_util, merma_dimensional = base._calcular_areas(locals())
            q1, q2, q3 = st.columns(3)
            q1.metric("Área total", f"{area_total:.2f} cm²")
            q2.metric("Área útil", f"{area_util:.2f} cm²")
            q3.metric("Merma por márgenes", f"{merma_dimensional:.2f}%")
        elif tipo_medicion == "Peso":
            st.markdown("#### Medición por peso")
            p1, p2 = st.columns(2)
            gramaje = p1.text_input("Peso / presentación", placeholder="Ej.: 100 g, 1 kg, 25 kg")
            merma_base_pct = p2.number_input("Pérdida o desperdicio opcional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
            st.caption("No se piden centímetros, márgenes ni sangrado porque este artículo se controla por peso.")
        elif tipo_medicion == "Volumen":
            st.markdown("#### Medición por volumen")
            p1, p2 = st.columns(2)
            gramaje = p1.text_input("Volumen / presentación", placeholder="Ej.: 70 ml, 100 ml, 1 L")
            merma_base_pct = p2.number_input("Pérdida o desperdicio opcional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
            st.caption("No se piden centímetros, márgenes ni sangrado porque este artículo se controla por volumen.")
        else:
            st.markdown("#### Medición por unidad")
            gramaje = st.text_input("Presentación opcional", placeholder="Ej.: paquete de 12, caja, pieza individual")
            st.caption("No se piden medidas ni merma. Úsalo para carpetas, bolígrafos, grapadoras, equipos o artículos por unidad.")

        st.markdown("#### Compra y almacenamiento")
        b1, b2, b3, b4 = st.columns(4)
        unidad_compra = b1.selectbox("Unidad de compra", [""] + UNIDADES_BASE)
        contenido_compra = b2.number_input("Contenido por unidad de compra", min_value=0.0, step=1.0, format="%.4f")
        with b3:
            proveedor_principal = _selector_proveedor_principal()
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


def render_inventario_unificado(usuario: str) -> None:
    base._render_form_crear = _render_form_crear_con_proveedor
    base._data_para_crear = _data_para_crear_validando_proveedor
    base.render_inventario_unificado(usuario)
