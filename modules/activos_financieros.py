from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


ESTADOS_PATRIMONIALES = [
    "disponible",
    "en_uso",
    "en_mantenimiento",
    "fuera_de_servicio",
    "prestado",
    "en_garantia",
    "pendiente_repuesto",
    "retirado",
    "vendido",
    "dado_de_baja",
]

MOTIVOS_BAJA = [
    "Vendido",
    "Dañado sin reparación conveniente",
    "Reemplazado",
    "Perdido",
    "Donado",
    "Desechado",
    "Otro",
]

METODOS_DEPRECIACION = {
    "lineal": "Línea recta",
}


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_column(conn, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _columns(conn, table_name):
        conn.execute(ddl)


def _ensure_schema() -> None:
    with db_transaction() as conn:
        if not _table_exists(conn, "activos"):
            return

        additions = {
            "codigo_interno": "ALTER TABLE activos ADD COLUMN codigo_interno TEXT",
            "marca": "ALTER TABLE activos ADD COLUMN marca TEXT",
            "numero_serie": "ALTER TABLE activos ADD COLUMN numero_serie TEXT",
            "proveedor": "ALTER TABLE activos ADD COLUMN proveedor TEXT",
            "factura_referencia": "ALTER TABLE activos ADD COLUMN factura_referencia TEXT",
            "moneda_compra": "ALTER TABLE activos ADD COLUMN moneda_compra TEXT NOT NULL DEFAULT 'USD'",
            "tasa_compra": "ALTER TABLE activos ADD COLUMN tasa_compra REAL NOT NULL DEFAULT 1",
            "valor_residual": "ALTER TABLE activos ADD COLUMN valor_residual REAL NOT NULL DEFAULT 0",
            "vida_contable_meses": "ALTER TABLE activos ADD COLUMN vida_contable_meses INTEGER NOT NULL DEFAULT 36",
            "metodo_depreciacion": "ALTER TABLE activos ADD COLUMN metodo_depreciacion TEXT NOT NULL DEFAULT 'lineal'",
            "fecha_compra": "ALTER TABLE activos ADD COLUMN fecha_compra TEXT",
            "garantia_hasta": "ALTER TABLE activos ADD COLUMN garantia_hasta TEXT",
            "ubicacion": "ALTER TABLE activos ADD COLUMN ubicacion TEXT",
            "custodio": "ALTER TABLE activos ADD COLUMN custodio TEXT",
            "estado_patrimonial": "ALTER TABLE activos ADD COLUMN estado_patrimonial TEXT NOT NULL DEFAULT 'en_uso'",
            "foto_url": "ALTER TABLE activos ADD COLUMN foto_url TEXT",
            "documento_url": "ALTER TABLE activos ADD COLUMN documento_url TEXT",
        }
        for name, ddl in additions.items():
            _ensure_column(conn, "activos", name, ddl)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activos_bajas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activo_id INTEGER NOT NULL,
                fecha_baja TEXT NOT NULL,
                motivo TEXT NOT NULL,
                detalle TEXT,
                valor_recuperado REAL NOT NULL DEFAULT 0,
                autorizado_por TEXT,
                evidencia_url TEXT,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activo_id) REFERENCES activos(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activos_reemplazos_componentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activo_padre_id INTEGER NOT NULL,
                componente_anterior_id INTEGER,
                componente_nuevo_id INTEGER,
                fecha_reemplazo TEXT NOT NULL,
                motivo TEXT NOT NULL,
                costo REAL NOT NULL DEFAULT 0,
                notas TEXT,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activo_padre_id) REFERENCES activos(id),
                FOREIGN KEY (componente_anterior_id) REFERENCES activos(id),
                FOREIGN KEY (componente_nuevo_id) REFERENCES activos(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activos_ingresos_atribuidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activo_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                referencia TEXT,
                ingreso REAL NOT NULL DEFAULT 0,
                costo_variable REAL NOT NULL DEFAULT 0,
                detalle TEXT,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activo_id) REFERENCES activos(id)
            )
            """
        )


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _asset_label(row: dict[str, Any]) -> str:
    model = str(row.get("modelo") or "").strip()
    suffix = f" ({model})" if model else ""
    return f"#{int(row['id'])} · {row.get('equipo') or 'Activo'}{suffix}"


def _load_assets(include_inactive: bool = True) -> pd.DataFrame:
    _ensure_schema()
    with db_transaction() as conn:
        if not _table_exists(conn, "activos"):
            return pd.DataFrame()
        where = "" if include_inactive else "WHERE COALESCE(activo, 1) = 1"
        rows = conn.execute(
            f"""
            SELECT
                id, equipo, modelo, unidad, clase_registro, activo_padre_id,
                COALESCE(inversion, 0) AS inversion,
                COALESCE(activo, 1) AS activo,
                COALESCE(estado, 'activo') AS estado,
                codigo_interno, marca, numero_serie, proveedor, factura_referencia,
                COALESCE(moneda_compra, 'USD') AS moneda_compra,
                COALESCE(tasa_compra, 1) AS tasa_compra,
                COALESCE(valor_residual, 0) AS valor_residual,
                COALESCE(vida_contable_meses, 36) AS vida_contable_meses,
                COALESCE(metodo_depreciacion, 'lineal') AS metodo_depreciacion,
                COALESCE(fecha_compra, fecha_instalacion, substr(fecha, 1, 10)) AS fecha_compra,
                garantia_hasta, ubicacion, custodio,
                COALESCE(estado_patrimonial, CASE WHEN COALESCE(activo, 1) = 1 THEN 'en_uso' ELSE 'dado_de_baja' END) AS estado_patrimonial,
                foto_url, documento_url
            FROM activos
            {where}
            ORDER BY id DESC
            """
        ).fetchall()
    df = pd.DataFrame([dict(row) for row in rows])
    if df.empty:
        return df
    today = date.today()
    financial_rows = []
    for _, row in df.iterrows():
        purchase_date = _parse_date(row.get("fecha_compra")) or today
        elapsed = max(0, (today.year - purchase_date.year) * 12 + today.month - purchase_date.month)
        useful_months = max(1, int(row.get("vida_contable_meses") or 36))
        cost = max(0.0, float(row.get("inversion") or 0.0))
        residual = min(cost, max(0.0, float(row.get("valor_residual") or 0.0)))
        depreciable = max(0.0, cost - residual)
        monthly = depreciable / useful_months
        accumulated = min(depreciable, monthly * min(elapsed, useful_months))
        book_value = max(residual, cost - accumulated) if cost else 0.0
        financial_rows.append((monthly, accumulated, book_value, elapsed))
    df[["depreciacion_mensual", "depreciacion_acumulada", "valor_en_libros", "meses_transcurridos"]] = pd.DataFrame(
        financial_rows, index=df.index
    )
    return df


def _save_financial_profile(asset_id: int, values: dict[str, Any], usuario: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE activos
            SET codigo_interno = ?, marca = ?, numero_serie = ?, proveedor = ?,
                factura_referencia = ?, moneda_compra = ?, tasa_compra = ?,
                valor_residual = ?, vida_contable_meses = ?, metodo_depreciacion = ?,
                fecha_compra = ?, garantia_hasta = ?, ubicacion = ?, custodio = ?,
                estado_patrimonial = ?, foto_url = ?, documento_url = ?
            WHERE id = ?
            """,
            (
                values["codigo_interno"], values["marca"], values["numero_serie"], values["proveedor"],
                values["factura_referencia"], values["moneda_compra"], values["tasa_compra"],
                values["valor_residual"], values["vida_contable_meses"], values["metodo_depreciacion"],
                values["fecha_compra"], values["garantia_hasta"], values["ubicacion"], values["custodio"],
                values["estado_patrimonial"], values["foto_url"], values["documento_url"], asset_id,
            ),
        )
        if _table_exists(conn, "activos_historial"):
            conn.execute(
                """
                INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
                SELECT equipo, 'actualizacion_patrimonial', ?, 0, ? FROM activos WHERE id = ?
                """,
                ("Se actualizaron datos financieros y patrimoniales.", usuario, asset_id),
            )


def _register_income(asset_id: int, fecha: date, referencia: str, ingreso: float, costo: float, detalle: str, usuario: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO activos_ingresos_atribuidos
                (activo_id, fecha, referencia, ingreso, costo_variable, detalle, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, fecha.isoformat(), referencia.strip(), max(0.0, ingreso), max(0.0, costo), detalle.strip(), usuario),
        )


def _register_retirement(asset_id: int, fecha_baja: date, motivo: str, detalle: str, valor: float, autorizado: str, evidencia: str, usuario: str) -> None:
    with db_transaction() as conn:
        row = conn.execute("SELECT equipo FROM activos WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            raise ValueError("El activo seleccionado ya no existe.")
        conn.execute(
            """
            INSERT INTO activos_bajas
                (activo_id, fecha_baja, motivo, detalle, valor_recuperado, autorizado_por, evidencia_url, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, fecha_baja.isoformat(), motivo, detalle.strip(), max(0.0, valor), autorizado.strip(), evidencia.strip(), usuario),
        )
        state = "vendido" if motivo == "Vendido" else "dado_de_baja"
        conn.execute(
            "UPDATE activos SET activo = 0, estado = ?, estado_patrimonial = ? WHERE id = ?",
            (state, state, asset_id),
        )
        if _table_exists(conn, "activos_historial"):
            conn.execute(
                """
                INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
                VALUES (?, 'baja_patrimonial', ?, ?, ?)
                """,
                (row["equipo"], f"{motivo}: {detalle.strip()}", max(0.0, valor), usuario),
            )


def _register_replacement(parent_id: int, old_id: int | None, new_id: int, fecha_reemplazo: date, motivo: str, costo: float, notas: str, usuario: str) -> None:
    with db_transaction() as conn:
        new_row = conn.execute("SELECT id, equipo FROM activos WHERE id = ?", (new_id,)).fetchone()
        if not new_row:
            raise ValueError("El componente nuevo no existe.")
        conn.execute(
            "UPDATE activos SET activo_padre_id = ?, activo = 1, estado = 'activo', estado_patrimonial = 'en_uso' WHERE id = ?",
            (parent_id, new_id),
        )
        if old_id:
            conn.execute(
                "UPDATE activos SET activo = 0, estado = 'reemplazado', estado_patrimonial = 'retirado' WHERE id = ?",
                (old_id,),
            )
        conn.execute(
            """
            INSERT INTO activos_reemplazos_componentes
                (activo_padre_id, componente_anterior_id, componente_nuevo_id, fecha_reemplazo, motivo, costo, notas, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (parent_id, old_id, new_id, fecha_reemplazo.isoformat(), motivo.strip(), max(0.0, costo), notas.strip(), usuario),
        )


def _load_profitability() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "activos_ingresos_atribuidos"):
            return pd.DataFrame()
        rows = conn.execute(
            """
            SELECT
                a.id, a.equipo, a.modelo,
                COALESCE(SUM(i.ingreso), 0) AS ingresos,
                COALESCE(SUM(i.costo_variable), 0) AS costos_variables,
                COUNT(i.id) AS movimientos
            FROM activos a
            LEFT JOIN activos_ingresos_atribuidos i ON i.activo_id = a.id
            GROUP BY a.id, a.equipo, a.modelo
            ORDER BY ingresos DESC, a.id DESC
            """
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def render_activos_financieros(usuario: str) -> None:
    _ensure_schema()
    st.divider()
    st.header("💼 Gestión financiera y patrimonial")
    st.caption("Depreciación, rentabilidad, documentación, bajas y reemplazo de componentes sin borrar la trazabilidad.")

    assets = _load_assets(include_inactive=True)
    if assets.empty:
        st.info("Registra primero un activo en la sección principal.")
        return

    active = assets[assets["activo"] == 1].copy()
    total_cost = float(active["inversion"].sum()) if not active.empty else 0.0
    total_book = float(active["valor_en_libros"].sum()) if not active.empty else 0.0
    total_dep = float(active["depreciacion_acumulada"].sum()) if not active.empty else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Costo histórico activo", f"$ {total_cost:,.2f}")
    c2.metric("Valor en libros", f"$ {total_book:,.2f}")
    c3.metric("Depreciación acumulada", f"$ {total_dep:,.2f}")
    c4.metric("Activos vigentes", int(len(active)))

    tabs = st.tabs(["📋 Ficha patrimonial", "📉 Depreciación", "💵 Rentabilidad", "🔄 Reemplazos", "🗃️ Bajas"])

    labels_all = {_asset_label(row): int(row["id"]) for _, row in assets.iterrows()}
    labels_active = {_asset_label(row): int(row["id"]) for _, row in active.iterrows()}

    with tabs[0]:
        selected_label = st.selectbox("Activo", list(labels_all.keys()), key="patrimonial_asset")
        asset_id = labels_all[selected_label]
        row = assets[assets["id"] == asset_id].iloc[0]
        with st.form(f"patrimonial_form_{asset_id}"):
            a1, a2, a3 = st.columns(3)
            codigo = a1.text_input("Código interno", value=str(row.get("codigo_interno") or ""))
            marca = a2.text_input("Marca", value=str(row.get("marca") or ""))
            serie = a3.text_input("Número de serie", value=str(row.get("numero_serie") or ""))
            b1, b2, b3 = st.columns(3)
            proveedor = b1.text_input("Proveedor", value=str(row.get("proveedor") or ""))
            factura = b2.text_input("Factura / referencia", value=str(row.get("factura_referencia") or ""))
            moneda = b3.selectbox("Moneda de compra", ["USD", "Bs", "EUR"], index=["USD", "Bs", "EUR"].index(str(row.get("moneda_compra") or "USD")) if str(row.get("moneda_compra") or "USD") in ["USD", "Bs", "EUR"] else 0)
            c1f, c2f, c3f = st.columns(3)
            tasa = c1f.number_input("Tasa al comprar", min_value=0.0001, value=float(row.get("tasa_compra") or 1.0), step=0.1)
            residual = c2f.number_input("Valor residual ($)", min_value=0.0, value=float(row.get("valor_residual") or 0.0), step=1.0)
            vida_meses = c3f.number_input("Vida contable (meses)", min_value=1, value=int(row.get("vida_contable_meses") or 36), step=1)
            d1, d2, d3 = st.columns(3)
            compra_default = _parse_date(row.get("fecha_compra")) or date.today()
            fecha_compra = d1.date_input("Fecha de compra", value=compra_default)
            garantia_default = _parse_date(row.get("garantia_hasta"))
            garantia = d2.date_input("Garantía hasta", value=garantia_default, format="YYYY-MM-DD")
            estado_actual = str(row.get("estado_patrimonial") or "en_uso")
            estado_idx = ESTADOS_PATRIMONIALES.index(estado_actual) if estado_actual in ESTADOS_PATRIMONIALES else 1
            estado = d3.selectbox("Estado patrimonial", ESTADOS_PATRIMONIALES, index=estado_idx)
            e1, e2 = st.columns(2)
            ubicacion = e1.text_input("Ubicación", value=str(row.get("ubicacion") or ""))
            custodio = e2.text_input("Responsable / custodio", value=str(row.get("custodio") or ""))
            foto = st.text_input("Foto o evidencia (URL/referencia)", value=str(row.get("foto_url") or ""))
            documento = st.text_input("Factura, garantía o manual (URL/referencia)", value=str(row.get("documento_url") or ""))
            submitted = st.form_submit_button("Guardar ficha patrimonial", type="primary")
        if submitted:
            _save_financial_profile(
                asset_id,
                {
                    "codigo_interno": codigo.strip(), "marca": marca.strip(), "numero_serie": serie.strip(),
                    "proveedor": proveedor.strip(), "factura_referencia": factura.strip(), "moneda_compra": moneda,
                    "tasa_compra": float(tasa), "valor_residual": float(residual), "vida_contable_meses": int(vida_meses),
                    "metodo_depreciacion": "lineal", "fecha_compra": fecha_compra.isoformat(),
                    "garantia_hasta": garantia.isoformat() if garantia else None, "ubicacion": ubicacion.strip(),
                    "custodio": custodio.strip(), "estado_patrimonial": estado, "foto_url": foto.strip(),
                    "documento_url": documento.strip(),
                },
                usuario,
            )
            st.success("Ficha patrimonial actualizada.")
            st.rerun()

    with tabs[1]:
        view = assets[[
            "id", "equipo", "modelo", "fecha_compra", "inversion", "valor_residual", "vida_contable_meses",
            "depreciacion_mensual", "depreciacion_acumulada", "valor_en_libros", "estado_patrimonial",
        ]].copy()
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.info("La depreciación usa línea recta y nunca reduce el activo por debajo de su valor residual.")

    with tabs[2]:
        profitability = _load_profitability()
        if not profitability.empty:
            merged = profitability.merge(assets[["id", "inversion", "depreciacion_acumulada", "valor_en_libros"]], on="id", how="left")
            merged["margen_contribucion"] = merged["ingresos"] - merged["costos_variables"]
            merged["resultado_tras_depreciacion"] = merged["margen_contribucion"] - merged["depreciacion_acumulada"]
            merged["recuperacion_inversion_pct"] = merged.apply(lambda r: (r["margen_contribucion"] / r["inversion"] * 100) if r["inversion"] else 0.0, axis=1)
            st.dataframe(merged, use_container_width=True, hide_index=True)
        with st.form("asset_income_form", clear_on_submit=True):
            asset_label = st.selectbox("Activo productor", list(labels_active.keys()) if labels_active else list(labels_all.keys()))
            f1, f2, f3 = st.columns(3)
            movement_date = f1.date_input("Fecha", value=date.today())
            income = f2.number_input("Ingreso atribuido ($)", min_value=0.0, step=1.0)
            variable_cost = f3.number_input("Costo variable ($)", min_value=0.0, step=1.0)
            reference = st.text_input("Referencia de venta, pedido o trabajo")
            detail = st.text_area("Detalle")
            add_income = st.form_submit_button("Registrar resultado del activo", type="primary")
        if add_income:
            chosen = (labels_active or labels_all)[asset_label]
            _register_income(chosen, movement_date, reference, income, variable_cost, detail, usuario)
            st.success("Movimiento atribuido al activo.")
            st.rerun()

    with tabs[3]:
        principals = active[active["clase_registro"].fillna("equipo_principal") == "equipo_principal"].copy()
        components = active[active["clase_registro"].fillna("equipo_principal") != "equipo_principal"].copy()
        if principals.empty or components.empty:
            st.info("Necesitas al menos un equipo principal y un componente/herramienta registrados.")
        else:
            principal_labels = {_asset_label(row): int(row["id"]) for _, row in principals.iterrows()}
            component_labels = {_asset_label(row): int(row["id"]) for _, row in components.iterrows()}
            with st.form("component_replacement_form", clear_on_submit=True):
                parent_label = st.selectbox("Equipo principal", list(principal_labels.keys()))
                parent_id = principal_labels[parent_label]
                old_options = {"Sin componente anterior": None}
                linked = components[components["activo_padre_id"] == parent_id]
                old_options.update({_asset_label(row): int(row["id"]) for _, row in linked.iterrows()})
                old_label = st.selectbox("Componente retirado", list(old_options.keys()))
                new_label = st.selectbox("Componente nuevo", list(component_labels.keys()))
                r1, r2 = st.columns(2)
                replacement_date = r1.date_input("Fecha de reemplazo", value=date.today())
                replacement_cost = r2.number_input("Costo del reemplazo ($)", min_value=0.0, step=1.0)
                reason = st.text_input("Motivo")
                notes = st.text_area("Notas")
                replace = st.form_submit_button("Registrar reemplazo", type="primary")
            if replace:
                new_id = component_labels[new_label]
                old_id = old_options[old_label]
                if old_id and old_id == new_id:
                    st.error("El componente anterior y el nuevo no pueden ser el mismo.")
                elif not reason.strip():
                    st.error("Indica el motivo del reemplazo.")
                else:
                    _register_replacement(parent_id, old_id, new_id, replacement_date, reason, replacement_cost, notes, usuario)
                    st.success("Reemplazo registrado sin perder el historial del componente anterior.")
                    st.rerun()

    with tabs[4]:
        if not labels_active:
            st.info("No hay activos vigentes para dar de baja.")
        else:
            with st.form("asset_retirement_form", clear_on_submit=True):
                retirement_label = st.selectbox("Activo", list(labels_active.keys()))
                b1, b2 = st.columns(2)
                retirement_date = b1.date_input("Fecha de baja", value=date.today())
                reason = b2.selectbox("Motivo", MOTIVOS_BAJA)
                recovered = st.number_input("Valor recuperado o de venta ($)", min_value=0.0, step=1.0)
                authorized = st.text_input("Autorizado por", value=usuario)
                detail = st.text_area("Detalle obligatorio")
                evidence = st.text_input("Evidencia (URL/referencia)")
                confirm = st.checkbox("Confirmo que el activo saldrá de operación y conservará su historial")
                retire = st.form_submit_button("Registrar baja", type="primary")
            if retire:
                if not confirm:
                    st.error("Debes confirmar la baja.")
                elif not detail.strip():
                    st.error("La baja requiere una explicación.")
                else:
                    _register_retirement(labels_active[retirement_label], retirement_date, reason, detail, recovered, authorized, evidence, usuario)
                    st.success("Baja registrada. El activo permanece en el historial y ya no aparece como operativo.")
                    st.rerun()

        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT b.fecha_baja, a.equipo, a.modelo, b.motivo, b.detalle,
                       b.valor_recuperado, b.autorizado_por, b.usuario
                FROM activos_bajas b
                LEFT JOIN activos a ON a.id = b.activo_id
                ORDER BY b.fecha_baja DESC, b.id DESC
                """
            ).fetchall()
        history = pd.DataFrame([dict(row) for row in rows])
        if not history.empty:
            st.markdown("#### Historial de bajas")
            st.dataframe(history, use_container_width=True, hide_index=True)
