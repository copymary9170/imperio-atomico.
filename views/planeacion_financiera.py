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

FONDOS_DEFAULT = [
    ("Kontigo", "USD", 0.0, "Saldo protegido en Kontigo / USDC"),
    ("Menudeo", "USD", 0.0, "Compra por menudeo; mínimo operativo sugerido de $10"),
    ("Dólares físicos", "USD", 0.0, "Efectivo en divisas"),
    ("Banco USD", "USD", 0.0, "Cuenta o plataforma en dólares"),
    ("Bs Banco", "Bs", 0.0, "Bolívares en banco / pago móvil"),
    ("Bs Efectivo", "Bs", 0.0, "Bolívares en efectivo"),
]
MENUDO_MINIMO_USD = 10.0


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


def _ensure_fondos_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fondos_monetarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                tipo_moneda TEXT NOT NULL DEFAULT 'USD',
                saldo_actual REAL NOT NULL DEFAULT 0,
                tasa_referencia REAL NOT NULL DEFAULT 0,
                activo INTEGER NOT NULL DEFAULT 1,
                notas TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movimientos_fondos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fondo_id INTEGER NOT NULL,
                tipo_movimiento TEXT NOT NULL,
                monto REAL NOT NULL DEFAULT 0,
                moneda TEXT NOT NULL DEFAULT 'USD',
                tasa_cambio REAL NOT NULL DEFAULT 0,
                comision REAL NOT NULL DEFAULT 0,
                usd_equivalente REAL NOT NULL DEFAULT 0,
                descripcion TEXT,
                referencia TEXT,
                usuario TEXT,
                FOREIGN KEY (fondo_id) REFERENCES fondos_monetarios(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversiones_monetarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fondo_origen_id INTEGER NOT NULL,
                fondo_destino_id INTEGER NOT NULL,
                monto_origen REAL NOT NULL DEFAULT 0,
                monto_destino REAL NOT NULL DEFAULT 0,
                moneda_origen TEXT NOT NULL DEFAULT 'USD',
                moneda_destino TEXT NOT NULL DEFAULT 'USD',
                tasa REAL NOT NULL DEFAULT 0,
                comision REAL NOT NULL DEFAULT 0,
                usd_equivalente REAL NOT NULL DEFAULT 0,
                observacion TEXT,
                usuario TEXT,
                FOREIGN KEY (fondo_origen_id) REFERENCES fondos_monetarios(id),
                FOREIGN KEY (fondo_destino_id) REFERENCES fondos_monetarios(id)
            )
            """
        )
        for nombre, moneda, tasa, notas in FONDOS_DEFAULT:
            conn.execute(
                """
                INSERT OR IGNORE INTO fondos_monetarios (nombre, tipo_moneda, saldo_actual, tasa_referencia, activo, notas)
                VALUES (?, ?, 0, ?, 1, ?)
                """,
                (nombre, moneda, tasa, notas),
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


def _load_fondos() -> pd.DataFrame:
    _ensure_fondos_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, nombre, tipo_moneda, saldo_actual, tasa_referencia, activo, notas
            FROM fondos_monetarios
            WHERE activo = 1
            ORDER BY CASE tipo_moneda WHEN 'USD' THEN 0 ELSE 1 END, nombre
            """,
            conn,
        )


def _load_movimientos_fondos() -> pd.DataFrame:
    _ensure_fondos_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT m.id, m.fecha, f.nombre AS fondo, m.tipo_movimiento, m.monto, m.moneda,
                   m.tasa_cambio, m.comision, m.usd_equivalente, m.descripcion, m.referencia, m.usuario
            FROM movimientos_fondos m
            JOIN fondos_monetarios f ON f.id = m.fondo_id
            ORDER BY datetime(m.fecha) DESC, m.id DESC
            LIMIT 250
            """,
            conn,
        )


def _load_conversiones_fondos() -> pd.DataFrame:
    _ensure_fondos_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT c.id, c.fecha, fo.nombre AS origen, fd.nombre AS destino, c.monto_origen,
                   c.moneda_origen, c.monto_destino, c.moneda_destino, c.tasa, c.comision,
                   c.usd_equivalente, c.observacion, c.usuario
            FROM conversiones_monetarias c
            JOIN fondos_monetarios fo ON fo.id = c.fondo_origen_id
            JOIN fondos_monetarios fd ON fd.id = c.fondo_destino_id
            ORDER BY datetime(c.fecha) DESC, c.id DESC
            LIMIT 250
            """,
            conn,
        )


def _saldo_kontigo(df: pd.DataFrame | None = None) -> float:
    if df is None:
        df = _load_kontigo_movimientos()
    if df.empty:
        return 0.0
    return float(pd.to_numeric(df["monto_neto_usdc"], errors="coerce").fillna(0).sum())


def _usd_equivalente_fondo(row: pd.Series, tasa_actual_bs: float) -> float:
    saldo = float(row.get("saldo_actual") or 0)
    moneda = str(row.get("tipo_moneda") or "USD")
    tasa_fondo = float(row.get("tasa_referencia") or 0)
    if moneda.upper() == "USD":
        return saldo
    tasa = tasa_fondo or tasa_actual_bs
    return saldo / tasa if tasa else 0.0


def _render_fondo_monetario(usuario: str) -> None:
    _ensure_fondos_tables()
    st.subheader("💼 Fondo Monetario / USD equivalente")
    st.caption("Controla cuánto dinero tiene el negocio sin importar si está en Kontigo, Menudeo, dólares físicos, banco o bolívares.")

    fondos = _load_fondos()
    tasa_actual = st.number_input("Tasa actual para valorar bolívares (Bs/$)", min_value=0.0, step=0.01, format="%.2f", key="fondo_tasa_actual_usd")

    if not fondos.empty:
        fondos["usd_equivalente"] = fondos.apply(lambda row: _usd_equivalente_fondo(row, tasa_actual), axis=1)
    total_usd = 0.0 if fondos.empty else float(pd.to_numeric(fondos["usd_equivalente"], errors="coerce").fillna(0).sum())
    total_usd_liquido = 0.0 if fondos.empty else float(pd.to_numeric(fondos[fondos["tipo_moneda"] == "USD"]["saldo_actual"], errors="coerce").fillna(0).sum())
    total_bs = 0.0 if fondos.empty else float(pd.to_numeric(fondos[fondos["tipo_moneda"] == "Bs"]["saldo_actual"], errors="coerce").fillna(0).sum())
    saldo_menudeo = 0.0 if fondos.empty else float(pd.to_numeric(fondos[fondos["nombre"] == "Menudeo"]["saldo_actual"], errors="coerce").fillna(0).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Patrimonio equivalente", f"$ {total_usd:,.2f}")
    c2.metric("USD líquidos", f"$ {total_usd_liquido:,.2f}")
    c3.metric("Bolívares", f"Bs {total_bs:,.2f}")
    c4.metric("Menudeo", f"$ {saldo_menudeo:,.2f}")

    if 0 < saldo_menudeo < MENUDO_MINIMO_USD:
        st.warning(f"⚠️ Menudeo está por debajo del mínimo operativo de $ {MENUDO_MINIMO_USD:,.2f}.")

    tab_resumen, tab_mov, tab_conversion, tab_config, tab_historial = st.tabs([
        "Resumen", "Registrar movimiento", "Convertir / Menudeo", "Fondos", "Historial"
    ])

    with tab_resumen:
        if fondos.empty:
            st.info("Aún no hay fondos monetarios registrados.")
        else:
            mostrar = fondos.copy()
            mostrar["estado_menudeo"] = mostrar.apply(
                lambda row: "Mínimo alcanzado" if row["nombre"] == "Menudeo" and float(row["saldo_actual"] or 0) >= MENUDO_MINIMO_USD
                else "Falta mínimo" if row["nombre"] == "Menudeo" and float(row["saldo_actual"] or 0) > 0
                else "",
                axis=1,
            )
            st.dataframe(mostrar, use_container_width=True, hide_index=True)

    with tab_mov:
        st.info("Usa esto para registrar entradas, salidas o ajustes directos en un fondo específico.")
        with st.form("form_movimiento_fondo"):
            a1, a2, a3 = st.columns(3)
            fecha_mov = a1.date_input("Fecha", value=date.today(), key="fecha_mov_fondo")
            fondo_nombre = a2.selectbox("Fondo", fondos["nombre"].tolist() if not fondos.empty else [])
            tipo = a3.selectbox("Tipo", ["Ingreso", "Egreso", "Ajuste positivo", "Ajuste negativo"])

            b1, b2, b3 = st.columns(3)
            monto = b1.number_input("Monto real", min_value=0.0, step=1.0, format="%.2f", key="monto_mov_fondo")
            tasa = b2.number_input("Tasa Bs/$ si aplica", min_value=0.0, step=0.01, format="%.2f", key="tasa_mov_fondo")
            comision = b3.number_input("Comisión", min_value=0.0, step=0.1, format="%.2f", key="comision_mov_fondo")
            descripcion = st.text_input("Descripción", placeholder="Ej: Venta del día, compra menudeo, ajuste de caja")
            referencia = st.text_input("Referencia")

            fondo_row = fondos[fondos["nombre"] == fondo_nombre].iloc[0] if fondo_nombre and not fondos.empty else None
            moneda = str(fondo_row["tipo_moneda"]) if fondo_row is not None else "USD"
            signo = 1 if tipo in ["Ingreso", "Ajuste positivo"] else -1
            monto_neto = max(monto - comision, 0) if signo > 0 else abs(monto + comision)
            usd_equiv = monto_neto if moneda == "USD" else (monto_neto / tasa if tasa else 0.0)
            st.info(f"Impacto: {'+' if signo > 0 else '-'}{monto_neto:,.2f} {moneda} · USD equivalente: $ {usd_equiv:,.2f}")

            if st.form_submit_button("💾 Guardar movimiento", type="primary", use_container_width=True):
                if fondo_row is None:
                    st.error("No hay fondo seleccionado.")
                elif moneda == "Bs" and tasa <= 0:
                    st.error("Para fondos en bolívares debes indicar la tasa Bs/$.")
                else:
                    with db_transaction() as conn:
                        conn.execute(
                            """
                            INSERT INTO movimientos_fondos (
                                fecha, fondo_id, tipo_movimiento, monto, moneda, tasa_cambio, comision,
                                usd_equivalente, descripcion, referencia, usuario
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                f"{fecha_mov.isoformat()} {datetime.now().strftime('%H:%M:%S')}",
                                int(fondo_row["id"]),
                                tipo,
                                signo * monto_neto,
                                moneda,
                                tasa,
                                comision,
                                signo * usd_equiv,
                                descripcion,
                                referencia,
                                usuario,
                            ),
                        )
                        conn.execute(
                            "UPDATE fondos_monetarios SET saldo_actual = saldo_actual + ? WHERE id = ?",
                            (signo * monto_neto, int(fondo_row["id"])),
                        )
                    create_backup("fondo_monetario_movimiento", upload_external=True)
                    st.success("Movimiento del fondo monetario registrado.")
                    st.rerun()

    with tab_conversion:
        st.info("Para comprar por menudeo: origen normalmente será Bs Banco o Bs Efectivo, destino Menudeo. El sistema guarda comisión y USD neto.")
        with st.form("form_conversion_fondos"):
            a1, a2, a3 = st.columns(3)
            fecha_conv = a1.date_input("Fecha", value=date.today(), key="fecha_conversion_fondo")
            origen = a2.selectbox("Origen", fondos["nombre"].tolist() if not fondos.empty else [], key="origen_conversion_fondo")
            destino = a3.selectbox("Destino", fondos["nombre"].tolist() if not fondos.empty else [], index=1 if len(fondos) > 1 else 0, key="destino_conversion_fondo")

            b1, b2, b3 = st.columns(3)
            monto_origen = b1.number_input("Monto origen", min_value=0.0, step=1.0, format="%.2f", key="monto_origen_conversion")
            tasa = b2.number_input("Tasa usada", min_value=0.0, step=0.01, format="%.2f", key="tasa_conversion_fondo")
            comision = b3.number_input("Comisión en USD", min_value=0.0, step=0.1, format="%.2f", key="comision_conversion_fondo")
            observacion = st.text_area("Observación", placeholder="Ej: Compra por menudeo; mínimo $10")

            origen_row = fondos[fondos["nombre"] == origen].iloc[0] if origen and not fondos.empty else None
            destino_row = fondos[fondos["nombre"] == destino].iloc[0] if destino and not fondos.empty else None
            moneda_origen = str(origen_row["tipo_moneda"]) if origen_row is not None else "USD"
            moneda_destino = str(destino_row["tipo_moneda"]) if destino_row is not None else "USD"

            if moneda_origen == "Bs" and moneda_destino == "USD":
                monto_destino = max((monto_origen / tasa) - comision, 0) if tasa else 0.0
            elif moneda_origen == "USD" and moneda_destino == "Bs":
                monto_destino = max((monto_origen - comision) * tasa, 0) if tasa else 0.0
            else:
                monto_destino = max(monto_origen - comision, 0)
            usd_equivalente = monto_destino if moneda_destino == "USD" else (monto_destino / tasa if tasa else 0.0)
            st.info(f"Destino neto estimado: {monto_destino:,.2f} {moneda_destino} · Equivalente: $ {usd_equivalente:,.2f}")
            if destino == "Menudeo" and monto_destino < MENUDO_MINIMO_USD:
                st.warning(f"Menudeo todavía no llega al mínimo de $ {MENUDO_MINIMO_USD:,.2f}.")

            if st.form_submit_button("🔁 Guardar conversión", type="primary", use_container_width=True):
                if origen_row is None or destino_row is None:
                    st.error("Selecciona fondo origen y destino.")
                elif int(origen_row["id"]) == int(destino_row["id"]):
                    st.error("El origen y destino no pueden ser el mismo fondo.")
                elif tasa <= 0 and moneda_origen != moneda_destino:
                    st.error("Debes indicar la tasa para convertir monedas diferentes.")
                else:
                    with db_transaction() as conn:
                        conn.execute(
                            """
                            INSERT INTO conversiones_monetarias (
                                fecha, fondo_origen_id, fondo_destino_id, monto_origen, monto_destino,
                                moneda_origen, moneda_destino, tasa, comision, usd_equivalente, observacion, usuario
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                f"{fecha_conv.isoformat()} {datetime.now().strftime('%H:%M:%S')}",
                                int(origen_row["id"]),
                                int(destino_row["id"]),
                                monto_origen,
                                monto_destino,
                                moneda_origen,
                                moneda_destino,
                                tasa,
                                comision,
                                usd_equivalente,
                                observacion,
                                usuario,
                            ),
                        )
                        conn.execute("UPDATE fondos_monetarios SET saldo_actual = saldo_actual - ? WHERE id = ?", (monto_origen, int(origen_row["id"])))
                        conn.execute("UPDATE fondos_monetarios SET saldo_actual = saldo_actual + ? WHERE id = ?", (monto_destino, int(destino_row["id"])))
                    create_backup("fondo_monetario_conversion", upload_external=True)
                    st.success("Conversión registrada en el fondo monetario.")
                    st.rerun()

    with tab_config:
        st.caption("Edita saldos iniciales o agrega fondos nuevos. Úsalo con cuidado: estos saldos son la base del patrimonio equivalente.")
        edited = st.data_editor(
            fondos,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "nombre": st.column_config.TextColumn("Fondo"),
                "tipo_moneda": st.column_config.SelectboxColumn("Moneda", options=["USD", "Bs"]),
                "saldo_actual": st.column_config.NumberColumn("Saldo actual", step=1.0, format="%.2f"),
                "tasa_referencia": st.column_config.NumberColumn("Tasa referencia", step=0.01, format="%.2f"),
                "activo": st.column_config.CheckboxColumn("Activo"),
                "notas": st.column_config.TextColumn("Notas"),
                "usd_equivalente": st.column_config.NumberColumn("USD equivalente", disabled=True, format="$ %.2f"),
            },
            key="editor_fondos_monetarios",
        )
        if st.button("💾 Guardar fondos", use_container_width=True):
            with db_transaction() as conn:
                conn.execute("DELETE FROM fondos_monetarios")
                for _, row in edited.iterrows():
                    nombre = str(row.get("nombre", "")).strip()
                    if nombre:
                        conn.execute(
                            """
                            INSERT INTO fondos_monetarios (nombre, tipo_moneda, saldo_actual, tasa_referencia, activo, notas)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                nombre,
                                str(row.get("tipo_moneda") or "USD"),
                                float(row.get("saldo_actual") or 0),
                                float(row.get("tasa_referencia") or 0),
                                1 if bool(row.get("activo", True)) else 0,
                                str(row.get("notas") or ""),
                            ),
                        )
            create_backup("fondos_monetarios_config", upload_external=True)
            st.success("Fondos monetarios actualizados.")
            st.rerun()

    with tab_historial:
        movs = _load_movimientos_fondos()
        convs = _load_conversiones_fondos()
        h1, h2 = st.tabs(["Movimientos", "Conversiones"])
        with h1:
            if movs.empty:
                st.info("Aún no hay movimientos de fondos.")
            else:
                st.dataframe(movs, use_container_width=True, hide_index=True)
        with h2:
            if convs.empty:
                st.info("Aún no hay conversiones registradas.")
            else:
                st.dataframe(convs, use_container_width=True, hide_index=True)


def _render_kontigo(usuario: str) -> None:
    _ensure_kontigo_tables()
    st.subheader("💳 Kontigo / Protección de caja")
    st.caption("Primero registras el dinero que entra a Kontigo como saldo libre. Después decides si se reserva para nómina, reinversión, compras online u otro uso.")

    df = _load_kontigo_movimientos()
    saldo = _saldo_kontigo(df)
    entradas = 0.0 if df.empty else float(pd.to_numeric(df[df["monto_neto_usdc"] > 0]["monto_neto_usdc"], errors="coerce").fillna(0).sum())
    salidas = 0.0 if df.empty else abs(float(pd.to_numeric(df[df["monto_neto_usdc"] < 0]["monto_neto_usdc"], errors="coerce").fillna(0).sum()))
    comisiones = 0.0 if df.empty else float(pd.to_numeric(df["comision_usdc"], errors="coerce").fillna(0).sum())
    bolsillos = _load_kontigo_bolsillos()
    reservado = float(pd.to_numeric(bolsillos["monto_objetivo_usdc"], errors="coerce").fillna(0).sum()) if not bolsillos.empty else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo Kontigo", f"$ {saldo:,.2f} USDC")
    c2.metric("Libre / sin asignar", f"$ {saldo - reservado:,.2f}")
    c3.metric("Salidas", f"$ {salidas:,.2f}")
    c4.metric("Comisiones", f"$ {comisiones:,.2f}")

    if saldo - reservado < 0:
        st.warning("⚠️ Tienes más dinero reservado que saldo disponible en Kontigo.")

    tab_mov, tab_bolsillos, tab_historial, tab_calc = st.tabs(["Registrar movimiento", "Asignar saldo después", "Historial", "Calculadora"])

    with tab_mov:
        st.info("Las entradas a Kontigo quedarán como **Sin asignar**. La decisión de nómina, reinversión o compras se hace luego en 'Asignar saldo después'.")
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
            if tipo in KONTIGO_ENTRADAS:
                destino = "Sin asignar"
                d1.text_input("Estado del dinero", value="Sin asignar / saldo libre", disabled=True)
            else:
                destino = d1.selectbox("Uso de la salida", ["Nómina", "Reinversión", "Compras online", "Bolívares", "Efectivo", "Comisión", "Otro"])
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
        st.caption("Aquí decides después cómo quieres reservar el saldo libre. Esto no cambia el movimiento original; solo organiza el saldo disponible.")
        edited = st.data_editor(
            bolsillos,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "nombre": st.column_config.TextColumn("Destino futuro"),
                "monto_objetivo_usdc": st.column_config.NumberColumn("Monto reservado USDC", min_value=0.0, step=1.0, format="$ %.2f"),
                "notas": st.column_config.TextColumn("Notas"),
            },
            key="editor_bolsillos_kontigo_integrado",
        )
        if st.button("💾 Guardar asignación", use_container_width=True):
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
            st.success("Asignación guardada.")
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
    st.caption("Hub financiero: resumen ejecutivo, planeación, presupuesto mensual, caja, tesorería, fondo monetario, Kontigo, gastos, cuentas por pagar, contabilidad, conciliación, impuestos, rentabilidad y alertas.")

    secciones = {
        "📊 Resumen ejecutivo": lambda: render_finanzas_control(usuario),
        "💰 Planeación / Presupuesto": lambda: render_planeacion_financiera_module(usuario),
        "📅 Presupuesto mensual": lambda: render_presupuesto_mensual(usuario),
        "🏦 Caja": lambda: render_caja(usuario),
        "🏦 Tesorería y cobranza": lambda: render_tesoreria(usuario),
        "💼 Fondo Monetario": lambda: _render_fondo_monetario(usuario),
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
