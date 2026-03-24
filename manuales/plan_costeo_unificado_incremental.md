# Plan incremental de costeo unificado (Imperio Atómico)

## 1) Diagnóstico técnico breve (sobre el estado actual)

Imperio Atómico ya tiene las bases correctas para no rehacer nada:

- Inventario con costo unitario en tabla `inventario` y movimientos en `movimientos_inventario` (flujo apto para costo promedio). 
- Producción con `ordenes_produccion` + `ordenes_produccion_detalle` y consumo de insumos desde `ProduccionService`. 
- Cotizaciones ya operativas en `cotizaciones` (hoy centradas en costo estimado manual + margen). 
- Tesorería integrada por origen (`venta`, `gasto`, `pago_proveedor`, etc.) en `movimientos_tesoreria`, lo que permite cruzar caja con rentabilidad.

**Conclusión:** conviene montar una **capa de costeo transversal** encima, sin romper módulos actuales.

---

## 2) Arquitectura propuesta de costeo

### 2.1 Decisión técnica

Implementar un servicio nuevo:

- `services/costeo_service.py` como **motor único**.

Con persistencia mínima en 4 tablas nuevas:

- `parametros_costeo` (reglas globales de costo)
- `plantillas_costeo` (config por tipo de trabajo)
- `costeo_ordenes` (cabecera por cálculo/orden)
- `costeo_detalle` (componentes del costo)

### 2.2 Por qué esta decisión

- No duplica inventario, compras, tesorería ni CxP.
- Permite cálculo on-demand (simulación) y cálculo persistido (trazabilidad).
- Encaja con flujo actual de cotizaciones (manual + calculada).
- Abre puerta a margen estimado vs margen real sin rediseñar ventas.

### 2.3 Patrón de integración

- **Lectura:** inventario, órdenes, cotizaciones, tesorería.
- **Escritura:** solo nuevas tablas de costeo.
- **No invasivo:** cambios en módulos existentes sólo para “invocar” el motor.

---

## 3) SQL exacto de tablas nuevas (SQLite)

```sql
CREATE TABLE IF NOT EXISTS parametros_costeo (
    parametro TEXT PRIMARY KEY,
    valor_num REAL,
    valor_texto TEXT,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plantillas_costeo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    tipo_proceso TEXT NOT NULL CHECK (tipo_proceso IN ('impresion','sublimacion','corte','manual','servicio')),
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo')),
    version INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_plantillas_costeo_nombre_tipo
ON plantillas_costeo(nombre, tipo_proceso);

CREATE TABLE IF NOT EXISTS costeo_ordenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador','estimado','cerrado','anulado')),

    origen_tipo TEXT NOT NULL CHECK (origen_tipo IN ('cotizacion','produccion','venta','servicio','manual')),
    origen_id INTEGER,

    tipo_proceso TEXT NOT NULL CHECK (tipo_proceso IN ('impresion','sublimacion','corte','manual','servicio')),
    descripcion TEXT,
    cantidad REAL NOT NULL DEFAULT 1,

    costo_materiales_usd REAL NOT NULL DEFAULT 0,
    costo_mano_obra_usd REAL NOT NULL DEFAULT 0,
    costo_indirecto_usd REAL NOT NULL DEFAULT 0,
    costo_total_usd REAL NOT NULL DEFAULT 0,

    ingreso_estimado_usd REAL NOT NULL DEFAULT 0,
    ingreso_real_usd REAL NOT NULL DEFAULT 0,

    margen_estimado_usd REAL NOT NULL DEFAULT 0,
    margen_real_usd REAL NOT NULL DEFAULT 0,
    margen_estimado_pct REAL NOT NULL DEFAULT 0,
    margen_real_pct REAL NOT NULL DEFAULT 0,

    moneda TEXT NOT NULL DEFAULT 'USD',
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_fecha ON costeo_ordenes(fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_origen ON costeo_ordenes(origen_tipo, origen_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_tipo ON costeo_ordenes(tipo_proceso, estado);

CREATE TABLE IF NOT EXISTS costeo_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    costeo_orden_id INTEGER NOT NULL,

    categoria TEXT NOT NULL CHECK (categoria IN (
        'materia_prima',
        'merma',
        'tinta_cmyk',
        'mano_obra',
        'energia',
        'desgaste_equipo',
        'indirecto',
        'servicio_tercero',
        'ajuste'
    )),

    componente TEXT NOT NULL,
    referencia TEXT,

    tipo_costo TEXT NOT NULL DEFAULT 'variable' CHECK (tipo_costo IN ('variable','fijo_prorrateado','fijo_directo')),

    cantidad REAL NOT NULL DEFAULT 0,
    unidad TEXT,
    costo_unitario_usd REAL NOT NULL DEFAULT 0,
    factor_merma REAL NOT NULL DEFAULT 0,
    costo_total_usd REAL NOT NULL DEFAULT 0,

    source_table TEXT,
    source_id INTEGER,
    metadata TEXT,

    FOREIGN KEY (costeo_orden_id) REFERENCES costeo_ordenes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden ON costeo_detalle(costeo_orden_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_categoria ON costeo_detalle(categoria);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_source ON costeo_detalle(source_table, source_id);
```

---

## 4) Migración segura para SQLite

### 4.1 Estrategia

1. Crear tablas con `CREATE TABLE IF NOT EXISTS`.
2. Insertar parámetros por defecto con `INSERT OR IGNORE`.
3. Si se agregan columnas futuras: `PRAGMA table_info(...)` + `ALTER TABLE ... ADD COLUMN`.
4. No tocar tablas core existentes.

### 4.2 Script incremental sugerido (en `database/schema.py`)

```python
def _ensure_costeo_migration(conn) -> None:
    conn.executescript(COSTEO_SCHEMA_SQL)

    defaults = [
        ("costeo_merma_default_pct", 3.0, None),
        ("costeo_mano_obra_usd_hora", 4.5, None),
        ("costeo_energia_usd_hora", 0.8, None),
        ("costeo_desgaste_pct_material", 2.0, None),
        ("costeo_indirecto_pct_base", 7.5, None),
    ]

    for p, num, txt in defaults:
        conn.execute(
            """
            INSERT OR IGNORE INTO parametros_costeo(parametro, valor_num, valor_texto)
            VALUES (?, ?, ?)
            """,
            (p, num, txt),
        )
```

---

## 5) Reglas de negocio del costeo (motor real)

## 5.1 Fórmula base

`costo_total = materiales + merma + tinta_cmyk + mano_obra + energia + desgaste + indirectos + ajustes`

## 5.2 Reglas por componente

- **Materia prima:** tomar `costo_unitario_usd` vigente del inventario (costo promedio activo).
- **Merma:** `% merma` configurable por proceso/plantilla sobre materiales.
- **Tinta CMYK:** costo por ml (o por cobertura) x consumo estimado/real.
- **Electricidad:** `horas_maquina * tarifa_energia_usd_hora`.
- **Desgaste equipo:** `%` sobre base material o costo-hora por máquina.
- **Mano de obra:** `horas_operario * tarifa_hora`.
- **Indirectos:** porcentaje configurable sobre subtotal directo.
- **Proceso:**
  - `impresion`: peso alto en tinta + energía + setup.
  - `sublimacion`: papel transfer + tinta + calor (energía).
  - `corte`: tiempo máquina + desgaste cuchilla + mermas.
  - `manual`: mano de obra + indirectos.
  - `servicio`: principalmente mano de obra + terceros.

## 5.3 Margen

- `margen_usd = ingreso - costo_total`
- `margen_pct = (margen_usd / ingreso) * 100` (si ingreso > 0)

**Estimado:** usando precio cotizado/propuesto.  
**Real:** usando ingreso efectivo (venta/cobro validado).

---

## 6) Diseño del motor (`services/costeo_service.py`)

## 6.1 Firmas sugeridas

```python
calcular_costo_producto(
    usuario: str,
    inventario_id: int,
    cantidad: float,
    tipo_proceso: str,
    merma_pct: float | None = None,
    horas_mano_obra: float = 0,
    horas_maquina: float = 0,
    persistir: bool = False,
    origen_tipo: str = "manual",
    origen_id: int | None = None,
) -> dict

calcular_costo_servicio(
    usuario: str,
    descripcion: str,
    tipo_proceso: str,
    horas_mano_obra: float,
    costo_terceros_usd: float = 0,
    otros_directos_usd: float = 0,
    persistir: bool = False,
    origen_tipo: str = "servicio",
    origen_id: int | None = None,
) -> dict

calcular_costo_orden(
    usuario: str,
    orden_produccion_id: int,
    tipo_proceso: str,
    persistir: bool = True,
) -> dict

calcular_margen_estimado(
    costo_total_usd: float,
    precio_estimado_usd: float,
) -> dict

calcular_margen_real(
    costeo_orden_id: int,
    ingreso_real_usd: float,
    usuario: str,
) -> dict

resumen_rentabilidad(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    agrupar_por: str = "tipo_proceso",
) -> list[dict]
```

## 6.2 Validaciones mínimas

- IDs existentes en inventario/orden.
- Cantidades > 0.
- Tipo proceso válido.
- No persistir si costo_total <= 0 salvo casos manuales autorizados.

## 6.3 Datos que toma del sistema actual

- `inventario.costo_unitario_usd`
- `ordenes_produccion` + `ordenes_produccion_detalle`
- `cotizaciones.precio_final_usd`
- `movimientos_tesoreria` para contraste ingreso real
- `configuracion` + `parametros_costeo`

---

## 7) Cambios mínimos por módulo (exactamente qué tocar)

## 7.1 `modules/inventario.py`

- **No alterar flujo de compras**.
- Solo agregar helper opcional para costeo:
  - botón “Simular costo unitario aplicado a proceso”.
  - no persistir por defecto.

## 7.2 `modules/cotizaciones.py`

- Agregar modo de cálculo:
  - `Manual` (actual, intacto).
  - `Calculado por motor` (nuevo, opcional).
- Si modo calculado:
  - invocar `calcular_costo_producto` o `calcular_costo_servicio`.
  - llenar `costo_estimado_usd` automáticamente.
- Mantener posibilidad de override manual.

## 7.3 Producción (`modules/produccion.py`, `services/produccion_service.py`)

- Al cerrar orden, invocar `calcular_costo_orden(..., persistir=True)`.
- Guardar relación con `origen_tipo='produccion'` y `origen_id=orden_id`.

## 7.4 CMYK / motor industrial

- Exponer consumo de tinta (ml o cobertura) como entrada del motor.
- No mover lógica de análisis PDF; sólo leer su salida y convertir a componente `tinta_cmyk`.

## 7.5 Tesorería

- Sin cambios estructurales.
- Solo consulta para alimentar `ingreso_real_usd` por origen.

## 7.6 Configuración (`modules/configuracion.py`)

- Agregar sección “Parámetros de costeo” que persista en `parametros_costeo`.

---

## 8) Conexión cotizaciones ↔ costeo sin romper flujo

- Default: **sigue Manual** (cero ruptura).
- Nuevo switch:
  - `Modo: Manual / Motor de costeo`.
- En modo Motor:
  1. Usuario define tipo de proceso y entradas mínimas.
  2. Se calcula costo sugerido.
  3. Se permite editar antes de guardar.
  4. Se muestra margen sugerido dinámico.

Esto conserva operación comercial actual y añade inteligencia financiera progresiva.

---

## 9) UI mínima en Streamlit (`modules/costeo.py`)

### 9.1 Pantallas operativas

1. **Simulador de costo**
   - entradas por proceso
   - botón calcular
2. **Detalle por componentes**
   - tabla: categoría, cantidad, costo unit, total
3. **Margen estimado vs real**
   - métricas y alertas
4. **Rentabilidad**
   - ranking por proceso/producto/servicio
5. **Exportación CSV**

### 9.2 Campos críticos del simulador

- Tipo de proceso
- Cantidad/unidad
- Consumos (material, tinta, horas, merma)
- Precio de venta estimado

---

## 10) Ejemplo aterrizado de implementación (servicio)

```python
# services/costeo_service.py (resumen)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from database.connection import db_transaction


@dataclass
class CosteoResultado:
    costo_materiales_usd: float
    costo_mano_obra_usd: float
    costo_indirecto_usd: float
    costo_total_usd: float
    detalle: list[dict[str, Any]]


class CosteoService:
    TIPOS_PROCESO = {"impresion", "sublimacion", "corte", "manual", "servicio"}

    def calcular_margen_estimado(self, costo_total_usd: float, precio_estimado_usd: float) -> dict[str, float]:
        costo = float(costo_total_usd or 0)
        ingreso = float(precio_estimado_usd or 0)
        margen = ingreso - costo
        margen_pct = (margen / ingreso * 100.0) if ingreso > 0 else 0.0
        return {
            "costo_total_usd": round(costo, 4),
            "ingreso_estimado_usd": round(ingreso, 4),
            "margen_estimado_usd": round(margen, 4),
            "margen_estimado_pct": round(margen_pct, 2),
        }

    def resumen_rentabilidad(self, fecha_desde: str | None = None, fecha_hasta: str | None = None) -> list[dict[str, Any]]:
        filtros, params = ["estado != 'anulado'"], []
        if fecha_desde:
            filtros.append("date(fecha) >= date(?)")
            params.append(fecha_desde)
        if fecha_hasta:
            filtros.append("date(fecha) <= date(?)")
            params.append(fecha_hasta)

        where_sql = " AND ".join(filtros)
        query = f"""
            SELECT
                tipo_proceso,
                COUNT(*) AS total_operaciones,
                ROUND(SUM(costo_total_usd), 2) AS costo_total_usd,
                ROUND(SUM(ingreso_real_usd), 2) AS ingreso_real_usd,
                ROUND(SUM(margen_real_usd), 2) AS margen_real_usd
            FROM costeo_ordenes
            WHERE {where_sql}
            GROUP BY tipo_proceso
            ORDER BY margen_real_usd DESC
        """

        with db_transaction() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
```

---

## 11) Flujo de negocio actualizado (end-to-end)

1. Compras actualizan costo promedio inventario (igual que hoy).
2. Producción consume inventario (igual que hoy).
3. Costeo toma consumos + parámetros + proceso y calcula costo real.
4. Cotización puede usar costo manual o calculado.
5. Venta/tesorería aportan ingreso real.
6. Costeo actualiza margen real y rentabilidad por línea.
7. Dashboard de costeo muestra ranking rentable/no rentable.

---

## 12) Recomendaciones para no romper el sistema actual

- Activar costeo por feature flag (`costeo_habilitado=1` en `configuracion`).
- Mantener modo manual por defecto en cotizaciones.
- Nunca actualizar tablas core desde costeo salvo lectura.
- Persistir costeo en tablas nuevas únicamente.
- Añadir pruebas SQL básicas de migración en entorno local antes de producción.
- Validar primero en lote pequeño (últimos 30 días) y comparar contra tesorería.

---

## 13) Orden de implementación sugerido (2 fases)

### Fase 1 (rápida, segura)

- Crear tablas nuevas + parámetros base.
- Implementar `CosteoService` (simulación + margen + resumen).
- Integrar opción en cotizaciones (`Manual / Motor`).

### Fase 2 (costo real completo)

- Integrar cierre de orden de producción con persistencia de costeo.
- Cruce con ingresos reales de tesorería.
- Dashboard/ranking de rentabilidad con export CSV.
