from __future__ import annotations

import streamlit as st

from services.inventario_unificado_service import TIPOS_USO, UNIDADES_BASE, crear_item_unificado
from services.proveedores_select_service import listar_proveedores_activos, opciones_proveedores_con_manual
import views.inventario_unificado as base

TIPOS_FISICOS = [
    "Lámina / hoja / pliego (cm y cm²)",
    "Volumen (ml, L, cm³)",
    "Peso (g, kg)",
    "Unidad / pieza",
    "Paquete / caja",
]

UNIDADES_BASE_UI = [
    "unidad", "hoja", "pliego", "resma", "paquete", "caja", "rollo",
    "ml", "L", "cm³", "m³",
    "g", "kg", "mg",
    "cm", "m", "cm²", "m²",
]
for _u in UNIDADES_BASE:
    if _u not in UNIDADES_BASE_UI:
        UNIDADES_BASE_UI.append(_u)

UNIDADES_LAMINA = {"hoja", "pliego", "rollo", "cm", "m", "cm²", "cm2", "m²", "m2"}
UNIDADES_VOLUMEN = {"ml", "l", "litro", "litros", "cm³", "cm3", "m³", "m3"}
UNIDADES_PESO = {"g", "kg", "mg", "gramo", "gramos", "kilogramo", "kilogramos"}
UNIDADES_PAQUETE = {"resma", "paquete", "caja"}
UNIDADES_COMPRA = ["", "resma", "paquete", "caja", "bolsa", "botella", "envase", "rollo"] + [u for u in UNIDADES_BASE_UI if u not in {"resma", "paquete", "caja", "rollo"}]


def _selector_proveedor_principal() -> str:
    opciones, mapa = opciones_proveedores_con_manual()
    seleccion = st.selectbox("Proveedor principal", opciones, key="iu_proveedor_principal_select")
    if seleccion == "Escribir manualmente":
        return st.text_input("Proveedor principal manual", key="iu_proveedor_principal_manual").strip()
    if seleccion == "Sin proveedor":
        st.caption("Registra proveedores en el módulo 🏢 Proveedores para seleccionarlos aquí.")
    return mapa.get(seleccion, "")


def _tipo_fisico_sugerido(unidad_base: str, categoria: str) -> str:
    unidad = str(unidad_base or "").strip().lower()
    categoria_txt = str(categoria or "").strip().lower()
    if unidad in UNIDADES_VOLUMEN:
        return "Volumen (ml, L, cm³)"
    if unidad in UNIDADES_PESO:
        return "Peso (g, kg)"
    if unidad in UNIDADES_LAMINA:
        return "Lámina / hoja / pliego (cm y cm²)"
    if unidad in UNIDADES_PAQUETE:
        return "Paquete / caja"
    if any(x in categoria_txt for x in ["papel", "cartulina", "foami", "acetato", "opalina", "vinil", "adhesivo"]):
        return "Lámina / hoja / pliego (cm y cm²)"
    if any(x in categoria_txt for x in ["tinta", "pega", "silic"]):
        return "Volumen (ml, L, cm³)"
    return "Unidad / pieza"


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


def _tipo_uso_desde_checks(usa_servicios: bool, usa_reventa: bool, usa_manualidades: bool) -> str:
    if usa_servicios and usa_reventa:
        return "Ambos"
    if usa_reventa and not usa_servicios:
        return "Reventa"
    return "Insumo"


def _render_form_crear_con_proveedor(usuario: str) -> None:
    st.info("Primero define cómo se cuenta el artículo. Después eliges si se usa para impresión, venta al detal o manualidades.")
    with st.form("form_crear_item_unificado"):
        st.markdown("#### 1. Identificación")
        c1, c2, c3 = st.columns(3)
        sku = c1.text_input("SKU *", placeholder="Ej.: PAP-BOND-CARTA-75G")
        nombre = c2.text_input("Nombre *", placeholder="Ej.: Papel bond carta 75 g")
        categoria = c3.selectbox("Categoría", base.CATEGORIAS_SUGERIDAS, index=base.CATEGORIAS_SUGERIDAS.index("General"))

        st.markdown("#### 2. Uso comercial")
        u1, u2, u3, u4 = st.columns(4)
        usa_servicios = u1.checkbox("Insumo para servicios", value=True, help="Impresiones, toppers, sublimación, producción, etc.")
        usa_reventa = u2.checkbox("Venta al detal", value=False, help="Se puede vender tal cual al cliente.")
        usa_manualidades = u3.checkbox("Manualidades", value=False)
        fraccionable = u4.checkbox("Permite fraccionamiento", value=True)
        tipo_uso = _tipo_uso_desde_checks(usa_servicios, usa_reventa, usa_manualidades)

        st.markdown("#### 3. Unidad y tipo físico")
        d1, d2 = st.columns(2)
        unidad_base = d1.selectbox(
            "Unidad base / cómo descuenta stock",
            UNIDADES_BASE_UI,
            help="Ej.: hoja, pliego, cm, cm², ml, L, cm³, g, kg, unidad. Para papel comprado por resma, usa hoja como unidad base.",
        )
        tipo_sugerido = _tipo_fisico_sugerido(unidad_base, categoria)
        tipo_fisico = d2.selectbox("Tipo físico del artículo", TIPOS_FISICOS, index=TIPOS_FISICOS.index(tipo_sugerido))

        st.markdown("#### 4. Características generales")
        a1, a2, a3, a4 = st.columns(4)
        marca = a1.text_input("Marca")
        color = a2.text_input("Color")
        tamano = a3.text_input("Presentación / tamaño comercial", placeholder="Carta, oficio, botella 70 ml, caja 12 und")
        acabado = a4.text_input("Acabado / tipo", placeholder="Mate, brillante, pigmentada, transparente")

        gramaje = ""
        ancho_cm = alto_cm = margen_izquierdo_cm = margen_derecho_cm = 0.0
        margen_superior_cm = margen_inferior_cm = separacion_cm = sangrado_cm = 0.0
        merma_base_pct = 0.0

        if tipo_fisico == "Lámina / hoja / pliego (cm y cm²)":
            st.markdown("#### 5. Medidas de lámina")
            m1, m2, m3 = st.columns(3)
            ancho_cm = m1.number_input("Ancho (cm)", min_value=0.0, step=0.01, format="%.2f")
            alto_cm = m2.number_input("Alto (cm)", min_value=0.0, step=0.01, format="%.2f")
            gramaje = m3.text_input("Gramaje / grosor", placeholder="75 g, 180 g, 2 mm")
            usar_margenes = st.checkbox("Usar márgenes, separación o sangrado para cálculo de área útil", value=False)
            if usar_margenes:
                n1, n2, n3, n4 = st.columns(4)
                margen_izquierdo_cm = n1.number_input("Margen izquierdo (cm)", min_value=0.0, step=0.01, format="%.2f")
                margen_derecho_cm = n2.number_input("Margen derecho (cm)", min_value=0.0, step=0.01, format="%.2f")
                margen_superior_cm = n3.number_input("Margen superior (cm)", min_value=0.0, step=0.01, format="%.2f")
                margen_inferior_cm = n4.number_input("Margen inferior (cm)", min_value=0.0, step=0.01, format="%.2f")
                s1, s2 = st.columns(2)
                separacion_cm = s1.number_input("Separación entre piezas (cm)", min_value=0.0, step=0.01, format="%.2f")
                sangrado_cm = s2.number_input("Sangrado por lado (cm)", min_value=0.0, step=0.01, format="%.2f")
            merma_base_pct = st.number_input("Merma adicional opcional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
            area_total, area_util, merma_dimensional = base._calcular_areas(locals())
            q1, q2, q3 = st.columns(3)
            q1.metric("Área por unidad", f"{area_total:.2f} cm²")
            q2.metric("Área útil", f"{area_util:.2f} cm²")
            q3.metric("Merma por márgenes", f"{merma_dimensional:.2f}%")
        elif tipo_fisico == "Volumen (ml, L, cm³)":
            st.markdown("#### 5. Medición por volumen")
            v1, v2, v3 = st.columns(3)
            cantidad_vol = v1.number_input("Contenido del envase", min_value=0.0, step=1.0, format="%.4f")
            unidad_vol = v2.selectbox("Unidad de volumen", ["ml", "L", "cm³", "m³"])
            merma_base_pct = v3.number_input("Pérdida opcional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
            gramaje = f"{cantidad_vol:g} {unidad_vol}" if cantidad_vol else unidad_vol
            st.caption("Para tintas, pega, silicón, resina o líquidos. Aquí sí puedes usar cm³.")
        elif tipo_fisico == "Peso (g, kg)":
            st.markdown("#### 5. Medición por peso")
            p1, p2, p3 = st.columns(3)
            cantidad_peso = p1.number_input("Peso de presentación", min_value=0.0, step=1.0, format="%.4f")
            unidad_peso = p2.selectbox("Unidad de peso", ["g", "kg", "mg"])
            merma_base_pct = p3.number_input("Pérdida opcional (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f")
            gramaje = f"{cantidad_peso:g} {unidad_peso}" if cantidad_peso else unidad_peso
            st.caption("Para escarcha, polvos, pigmentos o materiales vendidos por peso.")
        elif tipo_fisico == "Paquete / caja":
            st.markdown("#### 5. Contenido del paquete")
            pc1, pc2, pc3 = st.columns(3)
            contenido_pack = pc1.number_input("Cantidad contenida", min_value=0.0, step=1.0, format="%.4f")
            unidad_contenida = pc2.selectbox("Unidad contenida", ["unidad", "hoja", "pliego", "ml", "L", "cm³", "g", "kg", "cm", "cm²", "otro"])
            gramaje = pc3.text_input("Descripción del contenido", placeholder="Ej.: caja de 12 bolígrafos")
            if not gramaje and contenido_pack:
                gramaje = f"{contenido_pack:g} {unidad_contenida}"
            st.caption("Para cajas, paquetes, bolsas y agrupaciones. Si es resma de papel, lo ideal es unidad base hoja y unidad compra resma.")
        else:
            st.markdown("#### 5. Pieza individual")
            gramaje = st.text_input("Presentación opcional", placeholder="Ej.: unidad, pieza, equipo, accesorio")
            st.caption("Para carpetas, bolígrafos, borras, sacapuntas, equipos o artículos que se cuentan por pieza.")

        st.markdown("#### 6. Compra y almacenamiento")
        b1, b2, b3, b4 = st.columns(4)
        unidad_compra = b1.selectbox("Unidad de compra", UNIDADES_COMPRA, help="Ej.: resma, caja, paquete, botella, envase.")
        default_contenido = 500.0 if unidad_compra == "resma" and unidad_base == "hoja" else 0.0
        contenido_compra = b2.number_input("Contenido por unidad compra", min_value=0.0, value=default_contenido, step=1.0, format="%.4f")
        with b3:
            proveedor_principal = _selector_proveedor_principal()
        ubicacion = b4.text_input("Ubicación")
        if unidad_compra == "resma" and unidad_base == "hoja":
            st.caption("Resma = paquete de hojas. El inventario descuenta hojas, pero conserva ancho/alto para área, merma y costeo.")

        st.markdown("#### 7. Control de existencias")
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
            usos = []
            if usa_servicios: usos.append("servicios")
            if usa_reventa: usos.append("venta al detal")
            if usa_manualidades: usos.append("manualidades")
            obs_final = f"Tipo físico: {tipo_fisico}. Usos: {', '.join(usos) or 'sin definir'}. {observaciones}".strip()
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
                "punto_reorden": punto_reorden, "observaciones": obs_final,
            }, usuario)
            st.success(f"Artículo #{item_id} creado.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo crear: {exc}")


def render_inventario_unificado(usuario: str) -> None:
    base._render_form_crear = _render_form_crear_con_proveedor
    base._data_para_crear = _data_para_crear_validando_proveedor
    base.render_inventario_unificado(usuario)
