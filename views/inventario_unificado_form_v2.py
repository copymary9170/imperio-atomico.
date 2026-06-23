from __future__ import annotations
import streamlit as st
from services.inventario_unificado_service import TIPOS_FISICOS, UNIDADES_POR_TIPO, crear_item_unificado
from services.proveedores_select_service import listar_proveedores_activos
import views.inventario_unificado as base

COMPRA=["","resma","paquete","caja","bolsa","botella","envase","rollo","unidad","hoja","pliego","ml","L","cm³","g","kg","cm","m","cm²","m²"]

def proveedor_id():
    df=listar_proveedores_activos(); ids=[None]+[int(x) for x in df.get("id",[])]
    etiquetas={None:"Sin proveedor"}
    for _,r in df.iterrows(): etiquetas[int(r["id"])]=str(r["nombre"])
    return st.selectbox("Proveedor principal",ids,format_func=lambda x:etiquetas[x])

def normalizar_pegado(item:dict)->dict:
    d=dict(item); nombre=str(d.get("proveedor_principal") or "").strip(); d["proveedor_principal_id"]=None
    if nombre:
        df=listar_proveedores_activos(); hit=df[df["nombre"].astype(str).str.casefold()==nombre.casefold()]
        if hit.empty: raise ValueError(f"Proveedor '{nombre}' no existe en Proveedores.")
        d["proveedor_principal_id"]=int(hit.iloc[0]["id"])
    d.setdefault("tipo_fisico","unidad"); uso=str(d.get("tipo_uso") or "Ambos").lower(); d["usos"]=[]
    if uso in {"insumo","ambos"}: d["usos"].append("servicios")
    if uso in {"reventa","ambos"}: d["usos"].append("venta_detal")
    return d

def render_form(usuario:str)->None:
    st.info("Selecciona primero la naturaleza física. Solo se muestran unidades compatibles.")
    with st.form("form_crear_item_unificado"):
        a,b,c=st.columns(3); sku=a.text_input("SKU *"); nombre=b.text_input("Nombre *"); categoria=c.selectbox("Categoría",base.CATEGORIAS_SUGERIDAS,index=base.CATEGORIAS_SUGERIDAS.index("General"))
        a,b=st.columns(2); tipo=a.selectbox("Tipo físico",list(TIPOS_FISICOS),format_func=lambda x:TIPOS_FISICOS[x]); unidad=b.selectbox("Unidad base",sorted(UNIDADES_POR_TIPO[tipo],key=str.lower))
        a,b,c,d=st.columns(4); serv=a.checkbox("Insumo para servicios",True); venta=b.checkbox("Venta al detal"); manual=c.checkbox("Manualidades"); frac=d.checkbox("Permite fraccionamiento",tipo!="unidad")
        a,b,c,d=st.columns(4); marca=a.text_input("Marca"); color=b.text_input("Color"); tamano=c.text_input("Presentación / tamaño"); acabado=d.text_input("Acabado / tipo")
        gramaje=up=""; cp=ancho=alto=merma=0.0
        if tipo=="lamina":
            a,b,c=st.columns(3); ancho=a.number_input("Ancho (cm) *",min_value=0.0); alto=b.number_input("Alto (cm) *",min_value=0.0); gramaje=c.text_input("Gramaje / grosor"); merma=st.number_input("Merma adicional (%)",0.0,100.0)
        elif tipo=="rollo":
            a,b,c=st.columns(3); ancho=a.number_input("Ancho (cm)",min_value=0.0); cp=b.number_input("Largo",min_value=0.0); up=c.selectbox("Unidad",["m","cm"])
        elif tipo=="volumen":
            a,b,c=st.columns(3); cp=a.number_input("Contenido",min_value=0.0); up=b.selectbox("Unidad",["ml","L","cm³"]); merma=c.number_input("Pérdida (%)",0.0,100.0)
        elif tipo=="peso":
            a,b,c=st.columns(3); cp=a.number_input("Peso",min_value=0.0); up=b.selectbox("Unidad",["g","kg"]); merma=c.number_input("Pérdida (%)",0.0,100.0)
        elif tipo=="unidad": cp,up=1.0,"unidad"
        a,b,c,d=st.columns(4); uc=a.selectbox("Unidad de compra",COMPRA); contenido=b.number_input("Contenido por compra",min_value=0.0,value=500.0 if uc=="resma" and unidad=="hoja" else 0.0)
        with c: prov=proveedor_id()
        ubicacion=d.text_input("Ubicación")
        a,b,c,d=st.columns(4); stock=a.number_input("Stock inicial",min_value=0.0); minimo=b.number_input("Stock mínimo",min_value=0.0); reorden=c.number_input("Punto de reorden",min_value=0.0); ideal=d.number_input("Stock ideal",min_value=0.0)
        maximo=st.number_input("Stock máximo",min_value=0.0); a,b=st.columns(2); costo=a.number_input("Costo unitario USD",min_value=0.0); precio=b.number_input("Precio venta USD",min_value=0.0); obs=st.text_area("Observaciones"); guardar=st.form_submit_button("Crear artículo",type="primary",use_container_width=True)
    if guardar:
        try:
            usos=(["servicios"] if serv else [])+(["venta_detal"] if venta else [])+(["manualidades"] if manual else [])
            item={"sku":sku,"nombre":nombre,"categoria":categoria,"tipo_fisico":tipo,"usos":usos,"unidad_base":unidad,"permite_fraccionamiento":frac,"cantidad_presentacion":cp,"unidad_presentacion":up,"stock_actual":stock,"stock_minimo":minimo,"costo_unitario_usd":costo,"precio_venta_usd":precio,"marca":marca,"color":color,"tamano":tamano,"gramaje":gramaje,"acabado":acabado,"ancho_cm":ancho,"alto_cm":alto,"merma_base_pct":merma,"unidad_compra":uc,"contenido_compra":contenido,"proveedor_principal_id":prov,"ubicacion":ubicacion,"stock_ideal":ideal,"stock_maximo":maximo,"punto_reorden":reorden,"observaciones":obs}
            st.success(f"Artículo #{crear_item_unificado(item,usuario)} creado."); st.rerun()
        except Exception as exc: st.error(f"No se pudo crear: {exc}")
