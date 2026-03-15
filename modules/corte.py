from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _registrar_orden_produccion(
    usuario: str,
    tipo: str,
    referencia: str,
    costo_estimado: float,
    estado: str = "Pendiente",
) -> int:
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ordenes_produccion (usuario, tipo, referencia, costo_estimado, estado)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(usuario), str(tipo), str(referencia), float(costo_estimado), str(estado)),
        )
        return int(cur.lastrowid)


def render_corte(usuario: str):
    st.title("✂️ Corte Industrial – Cameo")
    st.caption("Carga, análisis técnico y acciones de producción para corte industrial.")

    if "datos_corte_desde_cmyk" in st.session_state:
        cmyk_data = st.session_state.get("datos_corte_desde_cmyk", {})
        st.success(
            f"Trabajo recibido desde CMYK: {cmyk_data.get('trabajo', 'N/D')} ({cmyk_data.get('cantidad', 0)} uds)"
        )
        st.caption(f"Costo base de impresión recibido: $ {float(cmyk_data.get('costo_base', 0.0)):.2f}")
        if st.button("Limpiar envío CMYK (Corte)", key="btn_clear_cmyk_corte"):
            st.session_state.pop("datos_corte_desde_cmyk", None)
            st.rerun()

    with st.container(border=True):
        archivo = st.file_uploader("Archivo de diseño", type=["svg", "dxf", "png", "jpg", "jpeg", "pdf"])

        try:
            with db_transaction() as conn:
                df_inv = pd.read_sql_query(
                    """
                    SELECT id, item, cantidad, unidad, precio_usd
                    FROM inventario
                    WHERE COALESCE(activo,1)=1
                    ORDER BY item
                    """,
                    conn,
                )

                df_act = pd.read_sql_query(
                    """
                    SELECT id, equipo, categoria,
                           COALESCE(desgaste_por_cm, desgaste_por_uso, 0) AS desgaste_por_cm,
                           COALESCE(desgaste, 0) AS desgaste_actual
                    FROM activos
                    WHERE COALESCE(activo,1)=1
                    ORDER BY equipo
                    """,
                    conn,
                )
        except Exception:
            df_inv = pd.DataFrame(columns=["id", "item", "cantidad", "unidad", "precio_usd"])
            df_act = pd.DataFrame(columns=["id", "equipo", "categoria", "desgaste_por_cm", "desgaste_actual"])

        if not df_inv.empty:
            mat_idx = st.selectbox(
                "Material (Inventario)",
                df_inv.index,
                format_func=lambda i: f"{df_inv.loc[i, 'item']} | Stock: {float(df_inv.loc[i, 'cantidad'] or 0):,.2f} {df_inv.loc[i, 'unidad']}",
                key="corte_material_idx",
            )
            material_row = df_inv.loc[mat_idx]
        else:
            material_row = None
            st.warning("No hay materiales activos en inventario.")

        if not df_act.empty:
            df_act_corte = df_act[df_act["categoria"].astype(str).str.contains("Corte|Plotter|Cameo", case=False, na=False)]
            if df_act_corte.empty:
                df_act_corte = df_act.copy()

            equipo_idx = st.selectbox(
                "Equipo (Activos)",
                df_act_corte.index,
                format_func=lambda i: f"{df_act_corte.loc[i, 'equipo']} | desgaste/cm: {float(df_act_corte.loc[i, 'desgaste_por_cm'] or 0):.6f}",
                key="corte_equipo_idx",
            )
            equipo_row = df_act_corte.loc[equipo_idx]
        else:
            equipo_row = None
            st.warning("No hay equipos activos en tabla activos.")

        c1, c2, c3 = st.columns(3)
        profundidad_cuchilla = c1.number_input("Profundidad cuchilla", min_value=0.0, value=3.0, step=0.1)
        velocidad = c2.number_input("Velocidad", min_value=0.1, value=8.0, step=0.1)
        presion = c3.number_input("Presión", min_value=1.0, value=12.0, step=0.5)

    if "corte_resultado" not in st.session_state:
        st.session_state["corte_resultado"] = {}

    st.divider()
    col_btn_1, col_btn_2, col_btn_3, col_btn_4 = st.columns(4)

    if col_btn_1.button("🔍 Analizar diseño", use_container_width=True):
        if archivo is None:
            st.error("Debes subir un archivo para analizar.")
        elif material_row is None:
            st.error("Debes seleccionar un material válido de inventario.")
        elif equipo_row is None:
            st.error("Debes seleccionar un equipo válido de activos.")
        else:
            size_kb = max(len(archivo.getvalue()) / 1024.0, 1.0)
            area_cm2 = round(size_kb * 6.2 * (1 + (presion / 100.0)), 2)
            cm_corte = round((area_cm2 ** 0.5) * (2.0 + (profundidad_cuchilla / 10.0)) * 1.8, 2)
            complejidad = 1.0 + (presion / 80.0) + (profundidad_cuchilla / 20.0)
            tiempo_estimado_min = round((cm_corte / max(velocidad, 0.1)) * complejidad / 60.0, 2)

            costo_material_cm2 = float(material_row.get("precio_usd") or 0.0) / 100.0
            costo_material = area_cm2 * costo_material_cm2
            desgaste_por_cm = float(equipo_row.get("desgaste_por_cm") or 0.0)
            costo_desgaste = cm_corte * desgaste_por_cm
            mano_obra = tiempo_estimado_min * 0.35
            costo_estimado = round(costo_material + costo_desgaste + mano_obra, 2)

            st.session_state["corte_resultado"] = {
                "archivo": archivo.name,
                "material": str(material_row.get("item")),
                "material_id": int(material_row.get("id")),
                "equipo_id": int(equipo_row.get("id")),
                "equipo": str(equipo_row.get("equipo")),
                "profundidad": float(profundidad_cuchilla),
                "velocidad": float(velocidad),
                "presion": float(presion),
                "area_cm2": float(area_cm2),
                "cm_corte": float(cm_corte),
                "tiempo_estimado_min": float(tiempo_estimado_min),
                "costo_estimado": float(costo_estimado),
                "desgaste_por_cm": float(desgaste_por_cm),
                "cantidad_descuento_estimada": float(max(area_cm2 / 100.0, 0.01)),
            }
            st.success("Análisis completado. No se descontó inventario.")

    r = st.session_state.get("corte_resultado", {})
    if r:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("CM de corte", f"{r.get('cm_corte', 0):,.2f}")
        m2.metric("Área del diseño", f"{r.get('area_cm2', 0):,.2f} cm²")
        m3.metric("Tiempo estimado", f"{r.get('tiempo_estimado_min', 0):,.2f} min")
        m4.metric("Costo estimado", f"$ {r.get('costo_estimado', 0):,.2f}")

    if col_btn_2.button("📤 Enviar a Cotización", use_container_width=True):
        if not r:
            st.error("Primero debes analizar el diseño.")
        else:
            payload = {
                "tipo_produccion": "corte",
                "archivo": r.get("archivo"),
                "material": r.get("material"),
                "cm_corte": r.get("cm_corte"),
                "tiempo_estimado": r.get("tiempo_estimado_min"),
                "costo_base": r.get("costo_estimado"),
                "costo_estimado": r.get("costo_estimado"),
            }
            st.session_state["datos_pre_cotizacion"] = payload
            st.success("Datos enviados al módulo de cotización")

    if col_btn_3.button("🧾 Crear Orden de Producción", use_container_width=True):
        if not r:
            st.error("Primero debes analizar el diseño.")
        else:
            try:
                oid = _registrar_orden_produccion(
                    usuario=usuario,
                    tipo="corte",
                    referencia=f"Corte industrial {r.get('archivo', 'Trabajo corte')}",
                    costo_estimado=float(r.get("costo_estimado", 0.0)),
                )
                st.session_state["corte_resultado"]["orden_id"] = int(oid)
                st.success(f"Orden de producción creada #{oid}")
            except Exception as e:
                st.error(f"No se pudo crear la orden: {e}")

    if col_btn_4.button("📦 Descontar Material", use_container_width=True):
        if not r:
            st.error("Primero debes analizar el diseño.")
        else:
            try:
                with db_transaction() as conn:
                    row = conn.execute(
                        "SELECT cantidad, unidad, item FROM inventario WHERE id=?",
                        (int(r["material_id"]),),
                    ).fetchone()
                    if not row:
                        st.error("Material no encontrado en inventario.")
                    else:
                        stock_actual = float(row[0] or 0.0)
                        cantidad_desc = float(r.get("cantidad_descuento_estimada", 0.0))
                        if stock_actual < cantidad_desc:
                            st.warning("Inventario insuficiente para descontar material.")
                        else:
                            conn.execute(
                                "UPDATE inventario SET cantidad = COALESCE(cantidad,0) - ? WHERE id=?",
                                (cantidad_desc, int(r["material_id"])),
                            )
                            st.success(f"Material descontado: {cantidad_desc:,.3f} {row[1]} de {row[2]}")
            except Exception as e:
                st.error(f"Error al descontar material: {e}")

    st.divider()
    if st.button("🛠️ Registrar Desgaste Equipo", use_container_width=True):
        if not r:
            st.error("Primero debes analizar el diseño.")
        else:
            try:
                desgaste_inc = float(r.get("cm_corte", 0.0)) * float(r.get("desgaste_por_cm", 0.0))
                with db_transaction() as conn:
                    cols = [x[1] for x in conn.execute("PRAGMA table_info(activos)").fetchall()]
                    if "desgaste" in cols:
                        conn.execute(
                            "UPDATE activos SET desgaste = COALESCE(desgaste,0) + ? WHERE id=?",
                            (desgaste_inc, int(r["equipo_id"])),
                        )
                    elif "desgaste_por_uso" in cols:
                        conn.execute(
                            "UPDATE activos SET desgaste_por_uso = COALESCE(desgaste_por_uso,0) + ? WHERE id=?",
                            (desgaste_inc, int(r["equipo_id"])),
                        )
                st.success(f"Desgaste registrado: +{desgaste_inc:,.6f}")
            except Exception as e:
                st.error(f"No se pudo registrar desgaste: {e}")

    st.subheader("Panel de resultados")
    if r:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "archivo": r.get("archivo"),
                        "material": r.get("material"),
                        "cm_corte": r.get("cm_corte"),
                        "tiempo_estimado": r.get("tiempo_estimado_min"),
                        "costo_estimado": r.get("costo_estimado"),
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin resultados aún. Usa el botón 'Analizar diseño'.")
