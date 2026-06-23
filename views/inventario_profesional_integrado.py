from __future__ import annotations

import streamlit as st

from services.capacidad_profesional import listar_capacidad
from services.inventario_maestro_profesional_service import guardar_ficha, listar_maestro, registrar_compra, resumen_alertas
from views.inventario_operativo_copy_mary import render_inventario_operativo_copy_mary
from views.inventario_unificado_v2 import render_inventario_unificado
from views.kardex import render_kardex
from views.pedidos_inventario import render_pedidos_inventario


def _selector(df, key: str):
    ids=[int(x) for x in df['id'].tolist()]
    etiquetas={int(r['id']):f"{r['sku']} · {r['nombre']}" for _,r in df.iterrows()}
    return st.selectbox('Artículo',ids,format_func=lambda x:etiquetas[x],key=key)


def render_inventario_profesional_integrado(usuario: str) -> None:
    st.title('📦 Inventario profesional')
    st.caption('Una sola operación para controlar materiales, compras, producción, reservas, pérdidas y reposición.')
    tabs=st.tabs(['📊 Resumen','🗂️ Maestro','🧾 Compras','🧪 Recetas y producción','📋 Pedidos','🧾 Kardex','⚖️ Conteos y mermas'])

    with tabs[0]:
        df=resumen_alertas()
        if df.empty:
            st.info('No hay artículos activos.')
        else:
            c1,c2,c3,c4=st.columns(4)
            c1.metric('Artículos',len(df))
            c2.metric('Críticos',int(df['estado'].isin(['CRITICO','AGOTADO']).sum()))
            c3.metric('Reorden',int((df['estado']=='REORDEN').sum()))
            c4.metric('Comprometidos',int((df['estado']=='COMPROMETIDO').sum()))
            vista=df[['sku','nombre','unidad_base','stock_actual','reservado','disponible','minimo_operativo','punto_reorden','compra_sugerida','estado']].copy()
            st.dataframe(vista,use_container_width=True,hide_index=True)
            cap=listar_capacidad()
            if not cap.empty:
                st.markdown('#### Capacidad real de producción')
                st.dataframe(cap,use_container_width=True,hide_index=True)

    with tabs[1]:
        st.markdown('### Catálogo maestro y ficha de control')
        st.info('Aquí se define cómo se compra, cómo se controla y cuál es el mínimo que no debe cruzarse.')
        render_inventario_unificado(usuario)
        df=listar_maestro()
        if not df.empty:
            st.divider()
            item_id=_selector(df,'maestro_item')
            row=df[df['id']==item_id].iloc[0]
            with st.form('ficha_profesional'):
                c1,c2,c3=st.columns(3)
                unidad_control=c1.text_input('Unidad de control',value=str(row['unidad_control']))
                unidad_compra=c2.text_input('Unidad de compra',value=str(row['unidad_compra']))
                factor=c3.number_input('Contenido por compra',min_value=0.0001,value=float(row['factor_compra_base'] or 1),step=1.0)
                c4,c5,c6=st.columns(3)
                minimo=c4.number_input('Mínimo operativo',min_value=0.0,value=float(row['minimo_operativo'] or 0))
                seguridad=c5.number_input('Stock de seguridad',min_value=0.0,value=float(row['stock_seguridad'] or 0))
                consumo=c6.number_input('Consumo diario',min_value=0.0,value=float(row['consumo_diario'] or 0))
                c7,c8,c9=st.columns(3)
                reposicion=c7.number_input('Días de reposición',min_value=0.0,value=float(row['dias_reposicion'] or 0))
                ideal=c8.number_input('Stock ideal',min_value=0.0,value=float(row['stock_ideal'] or 0))
                maximo=c9.number_input('Stock máximo',min_value=0.0,value=float(row['stock_maximo'] or 0))
                bloquear=st.checkbox('Bloquear producción si queda por debajo del mínimo',value=bool(row['bloquear_si_critico']))
                ok=st.form_submit_button('Guardar ficha profesional',type='primary')
            if ok:
                try:
                    guardar_ficha(item_id,unidad_control=unidad_control,unidad_compra=unidad_compra,factor_compra_base=factor,minimo_operativo=minimo,stock_seguridad=seguridad,consumo_diario=consumo,dias_reposicion=reposicion,stock_ideal=ideal,stock_maximo=maximo,bloquear_si_critico=bloquear)
                    st.success('Ficha actualizada.'); st.rerun()
                except Exception as exc: st.error(str(exc))

    with tabs[2]:
        st.markdown('### Recepción de compras con conversión automática')
        df=listar_maestro()
        if df.empty: st.info('Primero crea artículos en el Maestro.')
        else:
            item_id=_selector(df,'compra_item')
            row=df[df['id']==item_id].iloc[0]
            st.caption(f"1 {row['unidad_compra']} = {row['factor_compra_base']} {row['unidad_base']}")
            with st.form('compra_profesional'):
                c1,c2=st.columns(2)
                cantidad=c1.number_input(f"Cantidad comprada ({row['unidad_compra']})",min_value=0.0001,step=1.0)
                costo=c2.number_input('Costo total USD',min_value=0.0,step=0.01)
                referencia=st.text_input('Factura o referencia')
                ok=st.form_submit_button('Registrar compra',type='primary')
            if ok:
                try:
                    base,costo_u=registrar_compra(item_id,cantidad_comprada=cantidad,costo_total_usd=costo,referencia=referencia,usuario=usuario)
                    st.success(f"Entrada: {base:,.4f} {row['unidad_base']} · costo unitario ${costo_u:,.6f}"); st.rerun()
                except Exception as exc: st.error(str(exc))

    with tabs[3]:
        render_inventario_operativo_copy_mary(usuario)
    with tabs[4]:
        render_pedidos_inventario(usuario)
    with tabs[5]:
        render_kardex(usuario)
    with tabs[6]:
        st.info('Usa las pestañas Mermas y Conteo físico del control operativo para ajustar existencias con trazabilidad.')
        render_inventario_operativo_copy_mary(usuario)
