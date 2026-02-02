import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SEGURIDAD ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔐 IMPERIO ATÓMICO: Acceso")
        password = st.text_input("Clave de Acceso:", type="password")
        if st.button("Activar"):
            if password == "1234":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. CONFIGURACIÓN DE ARCHIVOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

def inicializar_archivos():
    # Estructura robusta para Multimoneda
    if not os.path.exists(CSV_VENTAS):
        pd.DataFrame(columns=["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa_Usada", "Equiv_USD", "Responsable"]).to_csv(CSV_VENTAS, index=False)
    if not os.path.exists(CSV_STOCK):
        pd.DataFrame(columns=["Material", "Cantidad", "Unidad", "Costo_Unit_USD"]).to_csv(CSV_STOCK, index=False)

inicializar_archivos()

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "💰 Ventas (Tasa en Vivo)", "📦 Inventario (Costos USD)", "🔍 Manuales"])

# --- MÓDULO: VENTAS (CON TASA DINÁMICA) ---
if menu == "💰 Ventas (Tasa en Vivo)":
    st.title("💰 Registro de Venta con Tasa del Momento")
    df_stock = pd.read_csv(CSV_STOCK)
    
    with st.form("venta_dinamica"):
        cliente = st.text_input("Cliente")
        insumo = st.selectbox("Material usado", df_stock["Material"].unique()) if not df_stock.empty else None
        cant_u = st.number_input("Cantidad usada", min_value=0.0, step=0.1)
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        tipo_pago = c1.selectbox("Moneda de Pago", ["Bolívares (Bs)", "Dólares ($)"])
        monto_pago = c2.number_input("Monto total pagado", min_value=0.0)
        
        # Aquí es donde manejamos la tasa que cambia por hora
        tasa_ahora = c3.number_input("Tasa de cambio actual (Bs/USD)", min_value=1.0, value=1.0, help="Escribe la tasa BCV o Binance de este momento exacto.")
        
        responsable = st.text_input("Atendido por:")
        
        if st.form_submit_button("FINALIZAR OPERACIÓN"):
            # Calculamos el equivalente en USD para tu Dashboard
            if tipo_pago == "Bolívares (Bs)":
                equiv_usd = monto_pago / tasa_ahora
                monto_bs = monto_pago
            else:
                equiv_usd = monto_pago
                monto_bs = monto_pago * tasa_ahora
                
            # Guardar Venta
            nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, monto_bs, tasa_ahora, equiv_usd, responsable]], 
                                   columns=["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa_Usada", "Equiv_USD", "Responsable"])
            nueva_v.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            
            # Descontar Stock
            if insumo:
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                df_stock.to_csv(CSV_STOCK, index=False)
            
            st.success(f"✅ Venta registrada. Valor real: ${equiv_usd:.2f} (Tasa: {tasa_ahora})")
            st.balloons()

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario (Costos USD)":
    st.title("📦 Gestión de Compras y Costos de Reposición")
    df_stock = pd.read_csv(CSV_STOCK)
    
    tab1, tab2 = st.tabs(["📋 Ver Existencias", "🛒 Registrar Nueva Compra"])
    
    with tab1:
        if not df_stock.empty:
            df_stock["Valor_Total_USD"] = df_stock["Cantidad"] * df_stock["Costo_Unit_USD"]
            st.dataframe(df_stock, use_container_width=True)
            st.metric("Capital en Mercancía", f"$ {df_stock['Valor_Total_USD'].sum():,.2f}")
        else:
            st.info("No hay nada en bodega.")

    with tab2:
        with st.form("nueva_compra_tasa"):
            c1, c2 = st.columns(2)
            nom = c1.text_input("Nombre del Insumo")
            uni = c2.selectbox("Unidad", ["Hojas", "Metros", "Unidades", "Rollos"])
            
            c3, c4, c5 = st.columns(3)
            pago_compra = c3.number_input("Monto pagado al proveedor", min_value=0.0)
            moneda_compra = c4.selectbox("Moneda de compra", ["Bs (BCV)", "Bs (Binance)", "USD"])
            tasa_compra = c5.number_input("Tasa del proveedor (Bs/$)", min_value=1.0, value=1.0)
            
            cantidad_c = st.number_input("Cantidad total recibida", min_value=0.1)
            
            if st.form_submit_button("INGRESAR A STOCK"):
                # Estandarizar a USD
                costo_total_usd = pago_compra if moneda_compra == "USD" else pago_compra / tasa_compra
                costo_unit_usd = costo_total_usd / cantidad_c
                
                if not df_stock.empty and nom in df_stock["Material"].values:
                    # Promediar costo o actualizar al más reciente
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cantidad_c
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_unit_usd
                    df_stock.to_csv(CSV_STOCK, index=False)
                else:
                    nueva_c = pd.DataFrame([[nom, cantidad_c, uni, costo_unit_usd]], columns=["Material", "Cantidad", "Unidad", "Costo_Unit_USD"])
                    nueva_c.to_csv(CSV_STOCK, mode='a', header=False, index=False)
                st.success(f"Ingresado. Costo unitario base: ${costo_unit_usd:.4f}")

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen Financiero Blindado")
    if os.path.exists(CSV_VENTAS):
        df_v = pd.read_csv(CSV_VENTAS)
        if not df_v.empty:
            # Forzar conversión numérica para el gráfico
            df_v["Equiv_USD"] = pd.to_numeric(df_v["Equiv_USD"], errors='coerce')
            st.metric("Ventas Totales ($ Real)", f"$ {df_v['Equiv_USD'].sum():,.2f}")
            st.subheader("Historial de Transacciones")
            st.dataframe(df_v.tail(20), use_container_width=True)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Número de Hoja")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
