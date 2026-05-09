# Imperio Atomico - Base de Operaciones

Menu principal para controlar impresion, papeleria, sublimacion, corte de alta gama, servicios, inventario, produccion, calidad, finanzas, pedidos y marketing.

## Menu principal

### 1. Direccion general
- [Base de operaciones](operaciones/BASE-DE-OPERACIONES.md)
- [Sistema conectado](docs/SISTEMA-CONECTADO.md)
- [Rutas de planificacion](planificacion/rutas-operativas.csv)

### 2. Catalogo, servicios y precios
- [Catalogo de productos](catalogo/productos.csv)
- [Lista de servicios](servicios/lista-servicios.csv)
- [Calculadora de precios justos](precios/calculadora-precios.csv)
- [Cotizaciones](cotizaciones/cotizaciones.csv)

### 3. Produccion
- [Produccion manual](produccion/produccion-manual.csv)
- [Procesos generales](procesos/procesos-generales.csv)
- [Sublimacion](procesos/sublimacion.csv)
- [Corte de alta gama](procesos/corte-alta-gama.csv)
- [Otros procesos](procesos/otros-procesos.csv)

### 4. Inventario, compras y materiales
- [Inventario de stock](inventario/stock.csv)
- [Materiales y reabastecimiento](compras/materiales.csv)

### 5. Calidad, mermas y desperdicio
- [Control de calidad](calidad/control-calidad.csv)
- [Mermas y desperdicio](calidad/mermas-desperdicio.csv)

### 6. Clientes, pedidos y ventas
- [Clientes](clientes/clientes.csv)
- [Pedidos de clientes](pedidos/pedidos-clientes.csv)
- [Ventas](ventas/ventas.csv)

### 7. Finanzas, trabajadores y responsabilidades
- [Presupuesto mensual](finanzas/presupuesto-mensual.csv)
- [Nomina y trabajadores](trabajadores/nomina.csv)
- [Activos del negocio](activos/activos.csv)

### 8. Calendarios y marketing
- [Calendario de recordatorios](calendario/recordatorios.csv)
- [Calendario de publicaciones](marketing/calendario-publicaciones.csv)

### 9. Reportes
- [Resumen del sistema](reportes/resumen.md)

## Como debe fluir el negocio

```text
Cotizacion -> Pedido -> Planificacion -> Inventario -> Produccion -> Calidad -> Entrega -> Venta -> Reporte
```

## Reglas clave

- Todo producto usa `producto_id`.
- Todo servicio usa `servicio_id`.
- Todo pedido usa `pedido_id`.
- Toda cotizacion usa `cotizacion_id`.
- Todo proceso usa `proceso_id`.
- Toda ruta usa `ruta_id`.
- Toda merma usa `merma_id`.
- Todo activo usa `activo_id`.

## Objetivo del sistema

Que Imperio Atomico pueda saber que vender, cuanto cobrar, que producir, que material comprar, que pedidos entregar, que revisar en calidad, cuanto se pierde en merma, cuanto pagar, cuanto ahorrar y que publicar.
