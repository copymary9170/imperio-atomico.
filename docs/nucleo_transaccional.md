# Fase: Nucleo transaccional y reglas de negocio

Esta fase convierte Imperio Atomico ERP en un sistema conectado por eventos reales, no solo por pantallas separadas.

## Objetivo

Unificar el flujo principal del negocio:

```text
Cotizacion -> Venta -> Caja/Tesoreria -> Inventario -> Produccion -> Entrega -> Reporte -> Dashboard
```

## Tablas base ya usadas por el ERP

- `clientes`
- `inventario`
- `movimientos_inventario`
- `ventas`
- `ventas_detalle`
- `gastos`
- `cuentas_por_cobrar`
- `pagos_clientes`
- `cuentas_por_pagar_proveedores`
- `pagos_proveedores`
- `movimientos_tesoreria`
- `cotizaciones`
- `ordenes_produccion`
- `ordenes_produccion_detalle`
- `control_calidad_registros`
- `mermas_desperdicio`

## Nuevas tablas de la fase

### `eventos_transaccionales`

Registra los hechos importantes del negocio:

- `venta_registrada`
- `pago_recibido`
- `gasto_registrado`
- `stock_descontado`
- `cotizacion_aprobada`
- `orden_produccion_creada`
- `orden_produccion_completada`
- `entrega_completada`
- `diferencia_caja_detectada`

### `reglas_negocio_transaccionales`

Catálogo de reglas que deben cumplir los servicios de dominio.

Reglas iniciales:

1. Toda venta pagada mueve caja/tesoreria.
2. Toda venta con productos inventariables descuenta stock.
3. Toda venta a credito genera cuenta por cobrar.
4. Toda cotizacion aprobada se convierte en venta u orden de produccion.
5. Toda produccion cerrada registra costo real, merma y calidad.

### `metricas_dashboard_snapshot`

Guarda cortes de metricas para panel ejecutivo:

- ventas
- utilidad estimada
- gastos
- cuentas por cobrar
- cuentas por pagar
- stock critico
- trabajos pendientes
- alertas criticas

## Servicios agregados

### `database.transactional_core`

Crea el nucleo transaccional y carga reglas de negocio base.

Funcion principal:

```python
ensure_transactional_core_schema()
```

### `services.domain_events`

Permite registrar, consultar y marcar eventos del negocio.

Funciones principales:

```python
record_domain_event(...)
fetch_pending_domain_events(...)
mark_domain_event_processed(...)
mark_domain_event_failed(...)
```

### `services.transactional_sales_service`

Registra una venta con efectos conectados:

- inserta `ventas`
- inserta `ventas_detalle`
- descuenta inventario si aplica
- crea movimiento de tesoreria si es contado
- crea cuenta por cobrar si es credito
- registra evento `venta_registrada`

Funcion principal:

```python
registrar_venta_transaccional(...)
```

### `services.dashboard_metrics_service`

Calcula y guarda metricas ejecutivas.

Funciones principales:

```python
calcular_metricas_ejecutivas(periodo="diario")
guardar_snapshot_metricas(periodo="diario")
```

## Prioridad tecnica siguiente

1. Conectar el formulario real de ventas a `registrar_venta_transaccional`.
2. Conectar el dashboard ejecutivo a `calcular_metricas_ejecutivas`.
3. Crear servicio equivalente para gastos.
4. Crear servicio equivalente para pagos de clientes.
5. Crear servicio equivalente para aprobacion de cotizaciones.
6. Crear servicio equivalente para cierre de produccion.
7. Agregar pruebas de flujo completo: venta contado, venta credito, venta con inventario y venta sin inventario.

## Criterio de aceptacion

La fase se considera funcional cuando una venta registrada desde la interfaz pueda:

1. aparecer en ventas;
2. mover caja/tesoreria;
3. afectar inventario;
4. generar cuenta por cobrar si aplica;
5. crear evento transaccional;
6. reflejarse en el dashboard ejecutivo.
