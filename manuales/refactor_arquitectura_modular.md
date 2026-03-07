# Plan de refactorización modular ERP (sin romper lógica)

## 1) Arquitectura objetivo propuesta

```text
app.py
modules/
  dashboard.py
  ventas.py
  gastos.py
  inventario.py
  clientes.py
  cotizaciones.py
  produccion.py
  auditoria.py
services/
  ventas_service.py
  inventario_service.py
  produccion_service.py
  cotizacion_service.py
  diagnostico_service.py
database/
  connection.py
  schema.py
utils/
  calculations.py
  currency.py
  helpers.py
```

### Criterios arquitectónicos
- `app.py` solo debe enrutar módulos y controlar sesión/roles.
- `modules/*` solo contiene Streamlit UI y validaciones mínimas de captura.
- `services/*` contiene lógica de negocio y transacciones críticas.
- `database/*` centraliza conexión, `PRAGMA`, esquema y migraciones.
- `utils/*` concentra cálculos puros (sin acceso DB ni Streamlit).

## 2) Ejemplos de refactor implementado

### Ventas atómicas
- Se creó `VentasService.registrar_venta_atomica` para: validar stock previo, crear cabecera, crear detalle, descontar inventario vía `InventoryService` y registrar cuentas por cobrar en la misma transacción.

### Producción integrada con inventario
- Se creó `ProduccionService.registrar_orden` para crear orden de producción y consumir insumos de forma atómica con validación de stock.

### Diagnóstico OCR preservado
- Se agregó `services/diagnostico_service.py` como fachada para reutilizar `DiagnosticsService` y funciones OCR existentes sin cambiar algoritmo.

## 3) Estrategia segura para dividir `app.py`

1. **Congelar comportamiento actual**
   - Ejecutar smoke tests de ventas, gastos, inventario, producción, cotizaciones, diagnóstico.
2. **Extraer funciones puras primero**
   - Mover cálculos monetarios, costos, conversiones y helpers sin tocar UI.
3. **Extraer servicios transaccionales**
   - Mover ventas, movimientos inventario y producción a `services` con rollback automático.
4. **Crear módulos UI espejo**
   - Cada menú en `app.py` pasa a `modules/*.py` conservando queries SQL y formularios.
5. **Migración por feature flags**
   - Activar módulo nuevo por opción (`st.session_state["use_new_sales"]`) para rollback rápido.
6. **Eliminar duplicidad al final**
   - Solo cuando las métricas y auditoría coincidan 1:1 con legacy.

## 4) Pasos de migración sin ruptura

1. Añadir servicios nuevos sin reemplazar rutas legacy.
2. Ejecutar operaciones dual-write (solo en entorno de staging).
3. Comparar:
   - total de venta
   - saldo de inventario
   - costo promedio
   - asientos de auditoría
4. Activar por módulo (ventas → inventario → producción → cotizaciones).
5. Mantener plan de rollback: volver a handler legacy si falla check de consistencia.

## 5) Riesgos/bugs arquitectónicos detectados en el código actual

1. **Monolito excesivo**: `app.py` supera 8k líneas y mezcla UI, SQL, reglas de negocio y utilidades, elevando riesgo de regresión por cambios locales.
2. **Duplicidad de capa de DB**: existen `db/connection.py` y `database/connection.py` con comportamientos distintos, aumentando riesgo de inconsistencias transaccionales.
3. **Servicios paralelos en inglés/español**: coexistencia de archivos (`inventory_service.py`, `inventario_service.py`, `diagnostics_service.py`, `diagnostico_service.py`) requiere control de imports para evitar bypass de lógica central.
4. **Acoplamiento UI-negocio**: módulos Streamlit antiguos registran directamente SQL; el patrón recomendado es invocar servicios para preservar atomicidad en ventas/producción.
5. **Divergencia de esquema posible**: hay dos definiciones de inventario (`cantidad` vs `stock_actual`) en distintos flujos; cualquier módulo nuevo debe normalizar lectura antes de descontar stock.
