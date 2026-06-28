from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.configuracion import DEFAULT_CONFIG, get_current_config
from services.analisis_archivo_impresion import analyze_uploaded_file, estimate_ink_ml
from services.costeo_integral_service import ensure_integrated_costing_schema, price_from_margin, save_integrated_quote

UPLOAD_DIR = Path("uploads/clientes")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _rates() -> tuple[float, str]:
    try:
        cfg = get_current_config()
    except Exception:
        cfg = DEFAULT_CONFIG
    return float(cfg.get("tasa_bcv", 0) or 0), datetime.now().isoformat(timespec="seconds")


def _inventory_by_unit(unit: str | None = None) -> pd.DataFrame:
    sql = "SELECT id, sku, nombre, COALESCE(unidad,'unidad') unidad, COALESCE(costo,0) costo, COALESCE(cantidad,0) cantidad FROM inventario WHERE COALESCE(estado,'activo')='activo'"
    params: tuple = ()
    if unit:
        sql += " AND lower(COALESCE(unidad,'unidad'))=lower(?)"
        params = (unit,)
    sql += " ORDER BY nombre"
    return _df(sql, params)


def _clients() -> pd.DataFrame:
    try:
        return _df("SELECT id,nombre,COALESCE(telefono,'') telefono FROM clientes WHERE COALESCE(estado,'activo')='activo' ORDER BY nombre")
    except Exception:
        return pd.DataFrame(columns=["id", "nombre", "telefono"])


def _assets(kind: str | None = None) -> pd.DataFrame:
    sql = "SELECT *, CASE WHEN vida_util_total>0 THEN (costo_adquisicion_usd-valor_residual_usd+mantenimiento_acumulado_usd)/vida_util_total ELSE 0 END costo_por_uso_usd FROM activos_productivos_costeo WHERE estado='activo'"
    params: tuple = ()
    if kind:
        sql += " AND lower(tipo)=lower(?)"
        params = (kind,)
    sql += " ORDER BY nombre"
    return _df(sql, params)


def _pick_product(label: str, data: pd.DataFrame, key: str) -> int:
    options = [0] + data.id.tolist()
    return int(st.selectbox(label, options, format_func=lambda x: "No configurado" if x == 0 else f"{data.loc[data.id.eq(x),'nombre'].iloc[0]} · {data.loc[data.id.eq(x),'unidad'].iloc[0]} · ${data.loc[data.id.eq(x),'costo'].iloc[0]:,.6f}", key=key))


def _row(data: pd.DataFrame, item_id: int) -> pd.Series | None:
    found = data[data.id.eq(item_id)]
    return None if found.empty else found.iloc[0]


def render_cotizador_archivo(usuario: str) -> None:
    ensure_integrated_costing_schema()
    st.subheader("📄 Cotizar desde el archivo")
    st.caption("Primero se analiza el PDF o la imagen; después se calculan papel, tinta, impresora, plastificado, mano de obra y margen.")

    clients = _clients()
    c1, c2 = st.columns([2, 1])
    client_id = c1.selectbox("Cliente", [0] + clients.id.tolist(), format_func=lambda x: "Cliente General" if x == 0 else clients.loc[clients.id.eq(x), "nombre"].iloc[0], key="file_quote_client")
    copies = c2.number_input("Cantidad de copias", min_value=1, value=1, step=1, key="file_quote_copies")

    uploaded = st.file_uploader("Sube la licencia o documento", type=["pdf", "png", "jpg", "jpeg"], key="file_quote_upload")
    confidential = st.checkbox("Documento confidencial: eliminar después de la entrega", value=True, key="file_quote_confidential")
    if uploaded is None:
        st.info("La cotización comienza cuando subes el archivo. Sin archivo no se calcula la tinta ni la impresión.")
        return

    try:
        analysis = analyze_uploaded_file(uploaded)
    except Exception as exc:
        st.error(f"No se pudo analizar el archivo: {exc}")
        return

    st.markdown("#### Resultado del análisis")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Páginas", analysis.pages)
    a2.metric("Modo detectado", "Color" if analysis.has_color else "Negro / gris")
    a3.metric("Cobertura CMYK", f"{analysis.avg_total_pct:,.2f}%")
    a4.metric("Área impresa estimada", f"{analysis.total_inked_area_cm2:,.2f} cm²")
    st.dataframe(pd.DataFrame(analysis.page_details), use_container_width=True, hide_index=True)

    inventory = _inventory_by_unit()
    paper_candidates = inventory[inventory.unidad.str.lower().isin(["hoja", "unidad", "pliego"])]
    ink_candidates = inventory[inventory.unidad.str.lower().eq("ml")]
    laminate_candidates = inventory[inventory.unidad.str.lower().isin(["unidad", "cm2", "m2", "hoja", "pliego"])]
    printers = _assets("Impresora")
    laminators = _assets("Laminadora")

    st.markdown("#### Configuración de impresión")
    p1, p2, p3 = st.columns(3)
    paper_id = _pick_product("Papel", paper_candidates, "file_quote_paper")
    printer_id = int(p2.selectbox("Impresora", [0] + printers.id.tolist(), format_func=lambda x: "No configurada" if x == 0 else printers.loc[printers.id.eq(x), "nombre"].iloc[0], key="file_quote_printer"))
    duplex = p3.checkbox("Doble cara", value=False, key="file_quote_duplex")

    pages_per_sheet = st.number_input("Páginas o piezas aprovechadas por hoja", min_value=1, value=1, step=1, key="file_quote_imposition")
    printed_sides = analysis.pages * copies
    sheets = int((printed_sides + pages_per_sheet - 1) // pages_per_sheet)
    if duplex:
        sheets = int((sheets + 1) // 2)

    st.markdown("#### Tintas y calibración de la impresora")
    st.caption("La cobertura viene del archivo. Solo debes indicar cuánto consume tu impresora en una página al 100% de cobertura por canal; este dato se calibra una vez por impresora.")
    cols = st.columns(4)
    ink_ids: dict[str, int] = {}
    full_ml: dict[str, float] = {}
    labels = {"C": "Cian", "M": "Magenta", "Y": "Amarillo", "K": "Negro"}
    for idx, channel in enumerate(["C", "M", "Y", "K"]):
        with cols[idx]:
            ink_ids[channel] = _pick_product(f"Tinta {labels[channel]}", ink_candidates, f"file_quote_ink_{channel}")
            full_ml[channel] = st.number_input(f"ml a 100% {channel}", min_value=0.0, value=0.0, step=0.001, format="%.6f", key=f"file_quote_full_ml_{channel}")

    ink_ml = estimate_ink_ml(analysis, full_ml, copies)
    ink_costs: dict[str, float] = {}
    ink_rows: list[dict] = []
    for channel in ["C", "M", "Y", "K"]:
        product = _row(ink_candidates, ink_ids[channel]) if ink_ids[channel] else None
        unit_cost = float(product.costo or 0) if product is not None else 0.0
        cost = ink_ml[channel] * unit_cost
        ink_costs[channel] = cost
        ink_rows.append({"Canal": channel, "Cobertura %": getattr(analysis, f"avg_{channel.lower()}_pct"), "Consumo ml": ink_ml[channel], "Costo por ml": unit_cost, "Costo": cost})
    st.dataframe(pd.DataFrame(ink_rows), use_container_width=True, hide_index=True)

    st.markdown("#### Plastificado y acabados")
    l1, l2, l3 = st.columns(3)
    laminate_id = _pick_product("Material de plastificado", laminate_candidates, "file_quote_laminate")
    laminator_id = int(l2.selectbox("Laminadora", [0] + laminators.id.tolist(), format_func=lambda x: "No configurada" if x == 0 else laminators.loc[laminators.id.eq(x), "nombre"].iloc[0], key="file_quote_laminator"))
    laminate_qty = l3.number_input("Cantidad de material", min_value=0.0, value=1.0, step=0.01, key="file_quote_laminate_qty")

    m1, m2, m3, m4 = st.columns(4)
    labor_minutes = m1.number_input("Minutos de mano de obra", min_value=0.0, value=0.0, key="file_quote_labor_min")
    labor_rate = m2.number_input("Costo USD por minuto", min_value=0.0, value=0.0, key="file_quote_labor_rate")
    indirect_pct = m3.number_input("Costos indirectos (%)", min_value=0.0, value=0.0, key="file_quote_indirect")
    margin_pct = m4.number_input("Margen sobre venta (%)", min_value=0.0, max_value=99.0, value=40.0, key="file_quote_margin")

    paper = _row(paper_candidates, paper_id) if paper_id else None
    paper_cost = sheets * (float(paper.costo or 0) if paper is not None else 0.0)
    printer = _row(printers, printer_id) if printer_id else None
    printer_cost = printed_sides * (float(printer.costo_por_uso_usd or 0) if printer is not None else 0.0)
    laminate = _row(laminate_candidates, laminate_id) if laminate_id else None
    laminate_cost = laminate_qty * (float(laminate.costo or 0) if laminate is not None else 0.0)
    laminator = _row(laminators, laminator_id) if laminator_id else None
    laminator_cost = copies * (float(laminator.costo_por_uso_usd or 0) if laminator is not None else 0.0)
    total_ink_cost = sum(ink_costs.values())
    labor_cost = labor_minutes * labor_rate
    direct_cost = paper_cost + total_ink_cost + printer_cost + laminate_cost + laminator_cost + labor_cost
    indirect_cost = direct_cost * indirect_pct / 100.0
    total_cost = direct_cost + indirect_cost
    price_usd = price_from_margin(total_cost, margin_pct)
    bcv, rate_date = _rates()
    price_bs = price_usd * bcv

    st.markdown("#### Costo calculado desde el archivo")
    breakdown = pd.DataFrame([
        {"Concepto": f"Papel ({sheets} hojas)", "Costo USD": paper_cost},
        {"Concepto": f"Tintas ({ink_ml['TOTAL']:.6f} ml)", "Costo USD": total_ink_cost},
        {"Concepto": f"Uso impresora ({printed_sides} caras)", "Costo USD": printer_cost},
        {"Concepto": "Material plastificado", "Costo USD": laminate_cost},
        {"Concepto": "Uso laminadora", "Costo USD": laminator_cost},
        {"Concepto": f"Mano de obra ({labor_minutes:.2f} min)", "Costo USD": labor_cost},
        {"Concepto": "Indirectos", "Costo USD": indirect_cost},
    ])
    st.dataframe(breakdown, use_container_width=True, hide_index=True)
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Costo total", f"${total_cost:,.4f}")
    r2.metric("Precio USD", f"${price_usd:,.2f}")
    r3.metric("BCV activa", f"{bcv:,.2f} Bs/USD")
    r4.metric("Precio Bs", f"Bs {price_bs:,.2f}")

    missing = []
    if paper_id == 0:
        missing.append("papel")
    if printer_id == 0:
        missing.append("impresora")
    for channel in ["C", "M", "Y", "K"]:
        if getattr(analysis, f"avg_{channel.lower()}_pct") > 0.001 and (ink_ids[channel] == 0 or full_ml[channel] <= 0):
            missing.append(f"tinta/calibración {channel}")
    if bcv <= 0:
        missing.append("tasa BCV")
    if missing:
        st.warning("Falta configurar: " + ", ".join(missing))

    description = st.text_area("Descripción", value="Licencia o documento impreso y plastificado", key="file_quote_description")
    if st.button("Guardar cotización calculada desde el archivo", type="primary", use_container_width=True, disabled=bool(missing)):
        safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded.name.replace('/', '_')}"
        file_path = UPLOAD_DIR / safe_name
        file_path.write_bytes(uploaded.getvalue())
        client_name = "Cliente General" if not client_id else clients.loc[clients.id.eq(client_id), "nombre"].iloc[0]
        phone = "" if not client_id else clients.loc[clients.id.eq(client_id), "telefono"].iloc[0]
        detail = {
            "analisis_archivo": analysis.to_dict(),
            "consumo_tinta_ml": ink_ml,
            "costos_tinta_usd": ink_costs,
            "hojas": sheets,
            "caras_impresas": printed_sides,
            "desglose": breakdown.to_dict(orient="records"),
        }
        quote_id = save_integrated_quote({
            "usuario": usuario,
            "cliente_id": int(client_id) or None,
            "cliente": client_name,
            "telefono": phone,
            "descripcion": description,
            "cantidad": copies,
            "archivo_nombre": uploaded.name,
            "archivo_ruta": str(file_path),
            "confidencial": confidential,
            "materiales_usd": paper_cost + total_ink_cost + laminate_cost,
            "merma_usd": 0.0,
            "activos_usd": printer_cost + laminator_cost,
            "mano_obra_usd": labor_cost,
            "indirectos_usd": indirect_cost,
            "costo_total_usd": total_cost,
            "margen_pct": margin_pct,
            "precio_usd": price_usd,
            "tasa_bcv": bcv,
            "fecha_tasa": rate_date,
            "precio_bs": price_bs,
            "detalle": detail,
        })
        st.success(f"Cotización #{quote_id} guardada. El costo de impresión se calculó desde la cobertura del archivo.")
