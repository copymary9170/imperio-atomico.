from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.planeacion_financiera import (
    render_planeacion_financiera as render_planeacion_financiera_module,
)
from services.backup_service import create_backup
from views.caja import render_caja
from views.contabilidad import render_contabilidad
from views.finanzas_control import render_finanzas_control
from views.gastos import render_gastos
from views.presupuesto_mensual import render_presupuesto_mensual
from views.rentabilidad import render_rentabilidad
from views.erp_nuevos_modulos import (
    render_conciliacion_bancaria,
    render_cuentas_por_pagar,
    render_impuestos,
    render_tesoreria,
)


KONTIGO_TIPOS = [
    "Entrada desde caja",
    "Entrada depósito divisa física",
    "Entrada ajuste manual",
    "Salida nómina",
    "Salida reinversión",
    "Salida tarjeta / compra online",
    "Salida a bolívares",
    "Salida a efectivo / divisa física",
    "Comisión",
    "Ajuste manual",
]
KONTIGO_ENTRADAS = {"Entrada desde caja", "Entrada depósito divisa física", "Entrada ajuste manual", "Ajuste manual"}


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _scalar(conn, sql: str, default: float = 0.0) -> float:
    try:
        row = conn.execute(sql).fetchone()
        return float((row[0] if row else default) or default)
    except Exception:
        return float(default)


def _ensure_kontigo_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kontigo_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                tipo TEXT NOT NULL,
                concepto TEXT,
                monto_bruto_usdc REAL DEFAULT 0,
                comision_usdc REAL DEFAULT 0,
                monto_neto_usdc REAL DEFAULT 0,
                tasa_bolivares REAL DEFAULT 0,
                equivalente_bs REAL DEFAULT 0,
                destino TEXT,
                referencia TEXT,
                notas TEXT,
                usuario TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kontigo_bolsillos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                monto_objetivo_usdc REAL DEFAULT 0,
                notas TEXT
            )
            """
        )
        for nombre in ["Nómina", "Reinversión", "Disponible", "Compras online"]:
            conn.execute(
                "INSERT OR IGNORE INTO kontigo_bolsillos (nombre, monto_objetivo_usdc, notas) VALUES (?, 0, '')",
                (nombre,),
            )


def _load_kontigo_movimientos() -> pd.DataFrame:
    _ensure_kontigo_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha, tipo, concepto, monto_bruto_usdc, comision_usdc, monto_neto_usdc,
                   tasa_bolivares, equivalente_bs, destino, referencia, notas, usuario
            FROM kontigo_movimientos
            ORDER BY datetime(fecha) DESC, id DESC
            """,
            conn,
        )


def _load_kontigo_bolsillos() -> pd.DataFrame:
    _ensure_kontigo_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            "SELECT id, nombre, monto_objetivo_usdc, notas FROM kontigo_bolsillos ORDER BY nombre",
            conn,
        )


def _saldo_kontigo(df: pd.DataFrame | None = None) -> float:
    if df is None:
        df = _load_kontigo_movimientos()
    if df.empty:
        return 0.0
    return float(pd.to_numeric(df["monto_neto_usdc"], errors="coerce").fillna(0).sum())


def _render_kontigo(usuario: str) -> None:
    _ensure_kontigo_tables()
    st.subheader("💳 Kontigo / Protección de caja")
    st.caption("Cuenta interna para proteger caja en USDC, controlar saldo, pagar nómina, reinvertir y comprar online.")

    df = _load_kontigo_movimientos()
    saldo = _saldo_kontigo(df)
    entradas = 0.0 if df.empty else float(pd.to_numeric(df[df["monto_neto_usdc"] > 0]["monto_neto_usdc"], errors="coerce").fillna(0).sum())
    salidas = 0.0 if df.empty else abs(float(pd.to_numeric(df[df["monto_neto_usdc"] < 0]["monto_neto_usdc"], errors="coerce").fillna(0).sum()))
    comisiones = 0.0 if df.empty else float(pd.to_numeric(df["comision_usdc"], errors="coerce").fillna(0).sum())
    bolsillos = _load_kontigo_bolsillos()
    reservado = float(pd.to_numeric(bolsillos["monto_objetivo_usdc"], errors="coerce").fillna(0).sum()) if not bolsillos.empty else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo Kontigo", f"$ {saldo:,.2f} USDC")
    c2.metric("Disponible real", f"$ {saldo - reservado:,.2f}")
    c3.metric("Salidas", f"$ {salidas:,.2f}")
    c4.metric("Comisiones", f"$ {comisiones:,.2f}")

    if saldo - reservado < 0:
        st.warning("⚠️ Tienes más dinero reservado que saldo disponible en Kontigo.")

    tab_mov, tab_bolsillos, tab_historial, tab_calc = st.tabs(["Registrar movimiento", "Distribución", "Historial", "Calculadora"])

    with tab_mov:
        with st.form("form_kontigo_movimiento_integrado"):
            a1, a2, a3 = st.columns(3)
            fecha_mov = a1.date_input("Fecha", value=date.today())
            tipo = a2.selectbox("Tipo", KONTIGO_TIPOS)
            concepto = a3.text_input("Concepto", placeholder="Ej: Protección caja del día")

            b1, b2, b3 = st.columns(3)
            monto_bruto = b1.number_input("Monto bruto USDC", min_value=0.0, step=1.0, format="%.2f")
            comision = b2.number_input("Comisión USDC", min_value=0.0, step=0.1, format="%.2f")
            tasa_bs = b3.number_input("Tasa Bs/USDC", min_value=0.0, step=0.01, format="%.2f")

            monto_neto = max(monto_bruto - comision, 0) if tipo in KONTIGO_ENTRADAS else -abs(monto_bruto + comision)
            equivalente_bs = abs(monto_neto) * tasa_bs if tasa_bs else 0.0
            st.info(f"Movimiento neto: $ {monto_neto:,.2f} USDC · Equivalente: Bs {equivalente_bs:,.2f}")

            d1, d2 = st.columns(2)
            destino = d1.selectbox("Destino / categoría", ["Nómina", "Reinversión", "Disponible", "Compras online", "Caja", "Otro"])
            referencia = d2.text_input("Referencia")
            notas = st.text_area("Notas")

            if st.form_submit_button("💾 Guardar movimiento", type="primary", use_container_width=True):
                with db_transaction() as conn:
                    conn.execute(
                        """
                        INSERT INTO kontigo_movimientos (
                            fecha, tipo, concepto, monto_bruto_usdc, comision_usdc, monto_neto_usdc,
                            tasa_bolivares, equivalente_bs, destino, referencia, notas, usuario
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"{fecha_mov.isoformat()} {datetime.now().strftime('%H:%M:%S')}",
                            tipo,
                            concepto,
                            monto_bruto,
                            comision,
                            monto_neto,
                            tasa_bs,
                            equivalente_bs,
                            destino,
                            referencia,
                            notas,
                            usuario,
                        ),
                    )
                create_backup("kontigo_movimiento", upload_external=True)
                st.success("Movimiento Kontigo registrado y respaldo creado.")
                st.rerun()

    with tab_bolsillos:
        st.caption("Reserva parte del saldo para nómina, reinversión, compras online o disponible.")
        edited = st.data_editor(
            bolsillos,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "nombre": st.column_config.TextColumn("Bolsillo"),
                "monto_objetivo_usdc": st.column_config.NumberColumn("Monto reservado USDC", min_value=0.0, step=1.0, format="$ %.2f"),
                "notas": st.column_config.TextColumn("Notas"),
            },
            key="editor_bolsillos_kontigo_integrado",
        )
        if st.button("💾 Guardar distribución", use_container_width=True):
            with db_transaction() as conn:
                conn.execute("DELETE FROM kontigo_bolsillos")
                for _, row in edited.iterrows():
                    nombre = str(row.get("nombre", "")).strip()
                    if nombre:
                        conn.execute(
                            "INSERT INTO kontigo_bolsillos (nombre, monto_objetivo_usdc, notas) VALUES (?, ?, ?)",
                            (nombre, float(row.get("monto_objetivo_usdc") or 0), str(row.get("notas") or "")),
                        )
            create_backup("kontigo_bolsillos", upload_external=True)
            st.success("Distribución guardada.")
            st.rerun()

    with tab_historial:
        if df.empty:
            st.info("Aún no hay movimientos registrados en Kontigo.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Descargar historial CSV",
                df.to_csv(index=False).encode("utf-8-sig"),
                file_name="historial_kontigo.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_historial_kontigo_integrado",
            )

    with tab_calc:
        x1, x2, x3 = st.columns(3)
        monto = x1.number_input("Monto bruto", min_value=0.0, step=1.0, format="%.2f", key="kontigo_calc_monto_integrado")
        comision_pct = x2.number_input("Comisión %", min_value=0.0, step=0.1, format="%.2f", key="kontigo_calc_comision_integrado")
        tasa = x3.number_input("Tasa Bs/USDC", min_value=0.0, step=0.01, format="%.2f", key="kontigo_calc_tasa_integrado")
        comision_calc = monto * comision_pct / 100
        neto = max(monto - comision_calc, 0)
        st.metric("Comisión estimada", f"$ {comision_calc:,.2f}")
        st.metric("Neto estimado", f"$ {neto:,.2f} USDC")
        if tasa:
            st.metric("Equivalente Bs", f"Bs {neto * tasa:,.2f}")


def _render_alertas_financieras(usuario: str) -> None:
    st.subheader("🚨 Alertas financieras")
    st.caption("Caja, flujo, gastos, cuentas por cobrar/pagar, impuestos, conciliaciones y registros contables pendientes.")

    alertas: list[dict] = []
    detalles: dict[str, pd.DataFrame] = {}

    with db_transaction() as conn:
        caja_saldo = 0.0
        if _table_exists(conn, "movimientos_tesoreria"):
            cols = _columns(conn, "movimientos_tesoreria")
            if {"tipo", "monto_usd"}.issubset(cols):
                caja_saldo = _scalar(conn, "SELECT COALESCE(SUM(CASE WHEN lower(tipo) IN ('ingreso','entrada') THEN monto_usd ELSE -monto_usd END),0) FROM movimientos_tesoreria WHERE lower(COALESCE(estado,'')) IN ('confirmado','pagado','')")
        if caja_saldo < 0:
            alertas.append({"nivel": "Alta", "alerta": "Caja estimada negativa", "cantidad": 1, "acción": "Revisar movimientos de tesorería y cerrar caja."})

        if _table_exists(conn, "gastos"):
            cols = _columns(conn, "gastos")
            cat_col = "categoria" if "categoria" in cols else "concepto" if "concepto" in cols else None
            if cat_col:
                sin_categoria = pd.read_sql_query(f"SELECT * FROM gastos WHERE COALESCE({cat_col},'')='' LIMIT 200", conn)
                detalles["Gastos sin categoría"] = sin_categoria
                if not sin_categoria.empty:
                    alertas.append({"nivel": "Media", "alerta": "Gastos sin categoría", "cantidad": len(sin_categoria), "acción": "Clasificar gastos para mejorar reportes y presupuesto."})

        if _table_exists(conn, "cuentas_por_cobrar"):
            vencidas = pd.read_sql_query("SELECT * FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) IN ('vencida','incobrable') LIMIT 200", conn)
            detalles["CxC vencidas"] = vencidas
            if not vencidas.empty:
                alertas.append({"nivel": "Alta", "alerta": "Cuentas por cobrar vencidas", "cantidad": len(vencidas), "acción": "Priorizar cobranza y seguimiento a clientes."})

        if _table_exists(conn, "cuentas_por_pagar"):
            vencidas = pd.read_sql_query("SELECT * FROM cuentas_por_pagar WHERE lower(COALESCE(estado,''))='vencida' LIMIT 200", conn)
            detalles["CxP vencidas"] = vencidas
            if not vencidas.empty:
                alertas.append({"nivel": "Alta", "alerta": "Cuentas por pagar vencidas", "cantidad": len(vencidas), "acción": "Ordenar pagos críticos o renegociar proveedores."})

        if _table_exists(conn, "conciliaciones_bancarias"):
            pendientes = pd.read_sql_query("SELECT * FROM conciliaciones_bancarias WHERE lower(COALESCE(estado,'')) IN ('pendiente','abierta','por conciliar') LIMIT 200", conn)
            detalles["Conciliaciones pendientes"] = pendientes
            if not pendientes.empty:
                alertas.append({"nivel": "Media", "alerta": "Conciliaciones pendientes", "cantidad": len(pendientes), "acción": "Conciliar bancos contra caja/tesorería."})

        if _table_exists(conn, "impuestos"):
            pendientes = pd.read_sql_query("SELECT * FROM impuestos WHERE lower(COALESCE(estado,'')) IN ('pendiente','vencido','por pagar') LIMIT 200", conn)
            detalles["Impuestos pendientes"] = pendientes
            if not pendientes.empty:
                alertas.append({"nivel": "Alta", "alerta": "Impuestos pendientes o vencidos", "cantidad": len(pendientes), "acción": "Revisar calendario fiscal y pagos."})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Caja estimada", f"${caja_saldo:,.2f}")
    c2.metric("Alertas", len(alertas))
    c3.metric("CxC vencidas", len(detalles.get("CxC vencidas", pd.DataFrame())))
    c4.metric("CxP vencidas", len(detalles.get("CxP vencidas", pd.DataFrame())))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas financieras críticas con la información disponible.")

    if detalles:
        tabs = st.tabs(list(detalles.keys()))
        for tab, (nombre, df) in zip(tabs, detalles.items()):
            with tab:
                if df.empty:
                    st.success("Sin registros.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)


def render_planeacion_financiera(usuario: str) -> None:
    st.title("💼 Finanzas")
    st.caption("Hub financiero: resumen ejecutivo, planeación, presupuesto mensual, caja, tesorería, Kontigo, gastos, cuentas por pagar, contabilidad, conciliación, impuestos, rentabilidad y alertas.")

    secciones = {
        "📊 Resumen ejecutivo": lambda: render_finanzas_control(usuario),
        "💰 Planeación / Presupuesto": lambda: render_planeacion_financiera_module(usuario),
        "📅 Presupuesto mensual": lambda: render_presupuesto_mensual(usuario),
        "🏦 Caja": lambda: render_caja(usuario),
        "🏦 Tesorería y cobranza": lambda: render_tesoreria(usuario),
        "💳 Kontigo": lambda: _render_kontigo(usuario),
        "📉 Gastos": lambda: render_gastos(usuario),
        "💸 Cuentas por pagar": lambda: render_cuentas_por_pagar(usuario),
        "📚 Contabilidad": lambda: render_contabilidad(usuario),
        "🏛️ Conciliación bancaria": lambda: render_conciliacion_bancaria(usuario),
        "🧾 Impuestos": lambda: render_impuestos(usuario),
        "📈 Rentabilidad": lambda: render_rentabilidad(usuario),
        "🚨 Alertas financieras": lambda: _render_alertas_financieras(usuario),
    }

    seccion = st.radio(
        "Sección financiera",
        list(secciones.keys()),
        horizontal=True,
        key="finanzas_seccion_activa",
    )
    st.divider()
    secciones[seccion]()
