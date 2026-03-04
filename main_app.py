import streamlit as st
import pandas as pd
from funciones_db import init_db, get_conn
from inventario_core import registrar_movimiento_inventario, aplicar_ajuste, alertas_minimos
from produccion_core import analizar_cmyk, ejecutar_produccion
from diagnostico_core import registrar_diagnostico_impresora
from activos_core import obtener_activo_seleccionado


st.set_page_config(page_title='Imperio Atómico', layout='wide', page_icon='⚛️')
init_db()


MENU = [
    '📦 Inventario',
    '🎨 Análisis CMYK',
    '🖨️ Diagnóstico Impresora IA',
    '🔥 Sublimación Industrial',
    '✂️ Corte Industrial (Cameo)',
    '🛠️ Otros Procesos',
    '🏗️ Activos',
    '🔧 Ajustes de Inventario',
]

st.sidebar.title('Imperio Atómico')
menu = st.sidebar.selectbox('Módulo', MENU)
usuario = st.sidebar.text_input('Usuario', value='Sistema')

if menu == '📦 Inventario':
    st.header('Inventario')
    with get_conn() as conn:
        inv = pd.read_sql_query('SELECT id, item, categoria, unidad, cantidad, minimo, precio_usd FROM inventario WHERE activo=1 ORDER BY item', conn)
    st.dataframe(inv, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    item_id = col1.number_input('Item ID', min_value=1, step=1)
    tipo = col2.selectbox('Movimiento', ['ENTRADA', 'SALIDA', 'MERMA'])
    cantidad = col3.number_input('Cantidad', min_value=0.01, value=1.0)
    motivo = st.text_input('Motivo', value='Operación manual')

    if st.button('Registrar movimiento'):
        try:
            registrar_movimiento_inventario(int(item_id), tipo, float(cantidad), motivo=motivo, referencia='UI', usuario=usuario)
            st.success('Movimiento registrado y sincronizado con kardex/auditoría.')
        except Exception as e:
            st.error(str(e))

elif menu == '🎨 Análisis CMYK':
    st.header('Análisis CMYK')
    calidad = st.selectbox('Calidad de impresión', ['borrador', 'normal', 'alta'])
    tipo_papel = st.selectbox('Tipo de papel lógico', ['fotográfico', 'bond', 'adhesivo'])

    with get_conn() as conn:
        ids = [r['id'] for r in conn.execute('SELECT id FROM inventario WHERE activo=1 AND imprimible_cmyk=1').fetchall()]

    if st.button('Analizar consumo CMYK'):
        resultado = analizar_cmyk(ids, calidad=calidad, tipo_papel=tipo_papel)
        st.dataframe(pd.DataFrame(resultado), use_container_width=True)

elif menu == '🖨️ Diagnóstico Impresora IA':
    st.header('Diagnóstico Impresora IA')
    activo = obtener_activo_seleccionado('impresora')
    if not activo:
        st.warning('No hay impresora seleccionada en activos (seleccionada=1).')
    else:
        st.info(f"Impresora activa: {activo['equipo']} - {activo['modelo']}")

    hoja = st.text_area('Texto hoja de diagnóstico (OCR o manual)')
    foto = st.text_area('Texto foto de tanques (OCR o manual)')

    with get_conn() as conn:
        tintas = conn.execute(
            "SELECT id, item FROM inventario WHERE activo=1 AND (lower(item) LIKE '%cyan%' OR lower(item) LIKE '%magenta%' OR lower(item) LIKE '%amarillo%' OR lower(item) LIKE '%negro%' OR lower(item) LIKE '%black%')"
        ).fetchall()
    opciones = {f"{r['id']} - {r['item']}": r['id'] for r in tintas}
    map_ids = {}
    for canal in ['C', 'M', 'Y', 'K']:
        selected = st.selectbox(f'Insumo inventario para tinta {canal}', list(opciones.keys()), key=f'tinta_{canal}') if opciones else None
        if selected:
            map_ids[canal] = opciones[selected]

    if st.button('Procesar diagnóstico IA'):
        try:
            niveles = registrar_diagnostico_impresora(int(activo['id']), hoja, foto, map_ids, usuario=usuario)
            st.success(f'Diagnóstico aplicado: {niveles}')
        except Exception as e:
            st.error(str(e))

elif menu == '🔥 Sublimación Industrial':
    st.header('Sublimación Industrial')
    with get_conn() as conn:
        productos = [r['producto'] for r in conn.execute("SELECT DISTINCT producto FROM recetas_produccion WHERE activo=1 AND proceso='Sublimación'")]
    producto = st.selectbox('Producto', productos if productos else [''])
    cantidad = st.number_input('Cantidad a producir', min_value=1.0, value=1.0)
    minutos = st.number_input('Tiempo real (min)', min_value=0.0, value=0.0)

    if st.button('Lanzar orden Sublimación'):
        try:
            orden_id = ejecutar_produccion('Sublimación', producto, cantidad, usuario=usuario, minutos_reales=minutos)
            st.success(f'Orden creada OP-{orden_id}')
        except Exception as e:
            st.error(str(e))

elif menu == '✂️ Corte Industrial (Cameo)':
    st.header('Corte Industrial (Cameo)')
    with get_conn() as conn:
        productos = [r['producto'] for r in conn.execute("SELECT DISTINCT producto FROM recetas_produccion WHERE activo=1 AND proceso='Corte Cameo'")]
    producto = st.selectbox('Material / Producto', productos if productos else [''])
    cantidad = st.number_input('Cantidad', min_value=1.0, value=1.0)
    area = st.number_input('Área (m²)', min_value=0.1, value=1.0)

    if st.button('Lanzar orden Cameo'):
        try:
            orden_id = ejecutar_produccion('Corte Cameo', producto, cantidad, usuario=usuario, area=area)
            st.success(f'Orden de corte OP-{orden_id} registrada.')
        except Exception as e:
            st.error(str(e))

elif menu == '🛠️ Otros Procesos':
    st.header('Otros Procesos por receta')
    proceso = st.text_input('Nombre del proceso', value='Laminado')
    producto = st.text_input('Producto')
    cantidad = st.number_input('Cantidad', min_value=1.0, value=1.0)

    if st.button('Ejecutar proceso personalizado'):
        try:
            orden_id = ejecutar_produccion(proceso, producto, cantidad, usuario=usuario)
            st.success(f'Proceso ejecutado OP-{orden_id}')
        except Exception as e:
            st.error(str(e))

elif menu == '🏗️ Activos':
    st.header('Activos')
    with get_conn() as conn:
        act = pd.read_sql_query(
            'SELECT id, equipo, modelo, tipo, vida_total, uso_actual, vida_restante, desgaste, vida_cabezal, seleccionada FROM activos WHERE activo=1',
            conn,
        )
    st.dataframe(act, use_container_width=True)
    if not act.empty:
        alertas = act[act['vida_total'].fillna(0) < act['uso_actual'].fillna(0)]
        if not alertas.empty:
            st.error('ALERTA: hay activos con vida útil excedida.')
            st.dataframe(alertas, use_container_width=True)

elif menu == '🔧 Ajustes de Inventario':
    st.header('Ajustes de Inventario')
    item_id = st.number_input('Item ID ajuste', min_value=1, step=1)
    nuevo_stock = st.number_input('Nuevo stock', min_value=0.0, value=0.0)
    motivo = st.text_input('Motivo ajuste', value='Ajuste físico')

    if st.button('Aplicar ajuste'):
        try:
            aplicar_ajuste(int(item_id), float(nuevo_stock), motivo=motivo, usuario=usuario)
            st.success('Ajuste aplicado vía movimientos (kardex consistente).')
        except Exception as e:
            st.error(str(e))

    st.subheader('Alertas de mínimos')
    alertas = alertas_minimos()
    if alertas:
        st.dataframe(pd.DataFrame([dict(r) for r in alertas]), use_container_width=True)
    else:
        st.info('Sin alertas de stock mínimo.')
