# Nota tecnica: inventario e indentacion

## Contexto

Al agregar mejoras al modulo de inventario, el archivo `modules/inventario.py` puede romperse si se inserta codigo fuera del bloque correcto.

El error observado fue:

```text
IndentationError: expected an indented block after 'with' statement
```

## Problema exacto

El error ocurre cuando se deja algo asi:

```python
def _ensure_inventory_support_tables() -> None:
    with db_transaction() as conn:

conn.execute(...)
```

Despues de:

```python
with db_transaction() as conn:
```

Python espera codigo con sangria. Por eso `conn.execute(...)` debe estar dentro del `with`.

## Forma correcta

```python
def _ensure_inventory_support_tables() -> None:
    with db_transaction() as conn:
        conn.execute(...)
        conn.execute(...)
```

## Mejora pendiente para inventario

La mejora debe agregarse dentro de `_ensure_inventory_support_tables()` y todo debe quedar con sangria dentro del `with`.

Bloque sugerido:

```python
def _ensure_inventory_support_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recetas_consumo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                insumo_id INTEGER NOT NULL,
                cantidad_insumo REAL NOT NULL DEFAULT 0,
                unidad TEXT,
                merma_pct REAL DEFAULT 0,
                activo INTEGER DEFAULT 1,
                observaciones TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (producto_id) REFERENCES inventario(id),
                FOREIGN KEY (insumo_id) REFERENCES inventario(id)
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recetas_producto
            ON recetas_consumo(producto_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recetas_insumo
            ON recetas_consumo(insumo_id)
            """
        )

        inv_cols = {r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}

        extra_inventory_columns = {
            "tipo_item": "TEXT DEFAULT 'producto_venta'",
            "unidad_base": "TEXT",
            "unidad_compra": "TEXT",
            "factor_conversion_compra": "REAL DEFAULT 1",
            "stock_ideal": "REAL DEFAULT 0",
            "punto_reorden": "REAL DEFAULT 0",
            "lead_time_dias": "INTEGER DEFAULT 0",
            "margen_objetivo_pct": "REAL DEFAULT 0.40",
            "merma_estimada_pct": "REAL DEFAULT 0",
            "permite_stock_negativo": "INTEGER DEFAULT 0",
            "control_lote": "INTEGER DEFAULT 0",
            "ubicacion": "TEXT",
            "proveedor_preferido_id": "INTEGER",
        }

        for col_name, ddl in extra_inventory_columns.items():
            if col_name not in inv_cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {col_name} {ddl}")
                inv_cols.add(col_name)
```

## Advertencia importante

No se debe meter el bloque de proveedores dentro de este `for`:

```python
for col_name, ddl in extra_inventory_columns.items():
```

Debe quedar fuera del `for`, pero dentro del `with`.

Correcto:

```python
        for col_name, ddl in extra_inventory_columns.items():
            if col_name not in inv_cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {col_name} {ddl}")
                inv_cols.add(col_name)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedores (
                ...
            )
            """
        )
```

## Regla simple

Dentro de:

```python
def _ensure_inventory_support_tables() -> None:
    with db_transaction() as conn:
```

Todo `conn.execute(...)` debe tener 8 espacios antes.

## Estado recomendado

1. Mantener `modules/inventario.py` estable.
2. Probar primero los cambios en una rama aparte.
3. Agregar columnas y tablas en una fase.
4. Luego agregar pantallas nuevas.
5. No mezclar cambios de schema con cambios de interfaz en el mismo paso.
