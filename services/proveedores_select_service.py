from __future__ import annotations

import pandas as pd

from database.connection import db_transaction


def listar_proveedores_activos() -> pd.DataFrame:
    """Devuelve proveedores activos para selectores de compras e inventario."""
    try:
        with db_transaction() as conn:
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='proveedores'"
            ).fetchone()
            if not existe:
                return pd.DataFrame(columns=["id", "nombre", "rif", "tipo_proveedor", "activo"])
            cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(proveedores)").fetchall()}
            selected = []
            for out, col, default in [
                ("id", "id", "0"),
                ("nombre", "nombre", "''"),
                ("rif", "rif", "''"),
                ("tipo_proveedor", "tipo_proveedor", "''"),
                ("activo", "activo", "1"),
            ]:
                if col in cols:
                    selected.append(f"COALESCE({col}, {default}) AS {out}")
                else:
                    selected.append(f"{default} AS {out}")
            df = pd.read_sql_query(
                f"SELECT {', '.join(selected)} FROM proveedores ORDER BY nombre COLLATE NOCASE",
                conn,
            )
    except Exception:
        return pd.DataFrame(columns=["id", "nombre", "rif", "tipo_proveedor", "activo"])

    if df.empty:
        return df
    df = df[df["nombre"].astype(str).str.strip().ne("")].copy()
    if "activo" in df.columns:
        df = df[df["activo"].astype(str).str.lower().isin(["1", "1.0", "true", "activo", "sí", "si"])]
    return df.reset_index(drop=True)


def opciones_proveedores_con_manual() -> tuple[list[str], dict[str, str]]:
    """Opciones legibles y mapa opción -> nombre de proveedor."""
    df = listar_proveedores_activos()
    opciones = ["Sin proveedor", "Escribir manualmente"]
    mapa = {"Sin proveedor": "", "Escribir manualmente": ""}
    for _, row in df.iterrows():
        nombre = str(row.get("nombre") or "").strip()
        rif = str(row.get("rif") or "").strip()
        tipo = str(row.get("tipo_proveedor") or "").strip()
        etiqueta = nombre
        detalles = [x for x in [rif, tipo] if x]
        if detalles:
            etiqueta = f"{nombre} · {' · '.join(detalles)}"
        opciones.append(etiqueta)
        mapa[etiqueta] = nombre
    return opciones, mapa
