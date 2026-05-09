# Imperio Atomico - Menu Maestro

Base de operaciones para impresion, papeleria, sublimacion, corte de alta gama, servicios, inventario, produccion, calidad, finanzas, pedidos, calendarios y marketing.

## 1. Direccion general

- [Base de operaciones](operaciones/BASE-DE-OPERACIONES.md)
- [Sistema conectado](docs/SISTEMA-CONECTADO.md)
- [Rutas de planificacion](planificacion/rutas-operativas.csv)
- [Reportes](reportes/resumen.md)

## 2. Finanzas y administracion

### Nomina y trabajadores
Archivo: [trabajadores/nomina.csv](trabajadores/nomina.csv)

Sirve para controlar:

- Bienestar del trabajador
- Pago base
- Seguro
- Pension
- Extras
- Total mensual
- Estado del trabajador

### Presupuesto mensual
Archivo: [finanzas/presupuesto-mensual.csv](finanzas/presupuesto-mensual.csv)

Sirve para controlar:

- Nomina
- Materiales
- Exposiciones y salidas
- Clases y aprendizaje
- Marketing
- Seguros
- Pensiones
- Ahorro objetivo
- Dinero gastado
- Dinero disponible

## 3. Servicios y precios justos

### Catalogo de servicios
Archivo: [servicios/lista-servicios.csv](servicios/lista-servicios.csv)

Debe incluir y mejorar:

- Impresion
- Papeleria
- Sublimacion
- Corte de alta gama
- Otros servicios
- Estado del servicio
- Precio sugerido

### Calculadora de precios
Archivo: [precios/calculadora-precios.csv](precios/calculadora-precios.csv)

Formula base:

```text
Costo material
+ Tiempo
+ Operacion
+ Margen justo
= Precio final
```

Esto ayuda a evitar:

- Perder dinero
- Cobrar menos de lo real
- Cobrar de mas
- Desorden financiero
- No saber la utilidad real

### Cotizaciones
Archivo: [cotizaciones/cotizaciones.csv](cotizaciones/cotizaciones.csv)

Sirve para convertir una consulta en precio, pedido y venta.

## 4. Inventario y compras

### Control de materiales
Archivo: [compras/materiales.csv](compras/materiales.csv)

Incluye:

- Existencias reales
- Stock minimo
- Proveedor
- Fecha de reabastecimiento
- Material critico
- Material disponible

### Inventario general
Archivo: [inventario/stock.csv](inventario/stock.csv)

Sirve para conectar productos, materiales y produccion.

## 5. Pedidos y clientes

### Gestion de pedidos
Archivo: [pedidos/pedidos-clientes.csv](pedidos/pedidos-clientes.csv)

Ahora puedes saber:

- Que pedidos estan pendientes
- Fechas de entrega
- Estado del pedido
- Total
- Cliente relacionado
- Servicio o producto solicitado

### Clientes
Archivo: [clientes/clientes.csv](clientes/clientes.csv)

Sirve para conectar pedidos, ventas y cotizaciones.

### Ventas
Archivo: [ventas/ventas.csv](ventas/ventas.csv)

Sirve para registrar lo que ya se vendio y conectar con reportes.

## 6. Produccion y procesos

### Produccion manual
Archivo: [produccion/produccion-manual.csv](produccion/produccion-manual.csv)

Sirve para controlar trabajos hechos a mano o por operador.

### Sublimacion
Archivo: [procesos/sublimacion.csv](procesos/sublimacion.csv)

Controla:

- Producto
- Temperatura
- Tiempo
- Material
- Estado

### Corte de alta gama
Archivo: [procesos/corte-alta-gama.csv](procesos/corte-alta-gama.csv)

Controla:

- Material
- Configuracion
- Precision
- Responsable
- Estado

### Otros procesos
Archivo: [procesos/otros-procesos.csv](procesos/otros-procesos.csv)

Para laminado, armado, empaque, acabados, mantenimiento y procesos nuevos.

## 7. Calidad, mermas y desperdicio

### Control de calidad
Archivo: [calidad/control-calidad.csv](calidad/control-calidad.csv)

Sirve para revisar si un trabajo sale aprobado, rechazado o necesita correccion.

### Mermas y desperdicio
Archivo: [calidad/mermas-desperdicio.csv](calidad/mermas-desperdicio.csv)

Sirve para medir:

- Material desperdiciado
- Cantidad perdida
- Motivo
- Costo estimado
- Accion correctiva

## 8. Calendarios operativos

### Recordatorios internos
Archivo: [calendario/recordatorios.csv](calendario/recordatorios.csv)

Para recordar:

- Surtir material
- Pagos
- Seguro
- Pension
- Exposiciones
- Ahorro
- Mantenimiento
- Clases
- Entregas importantes

## 9. Publicaciones y marketing

### Calendario de publicaciones
Archivo: [marketing/calendario-publicaciones.csv](marketing/calendario-publicaciones.csv)

Para planificar:

- Instagram
- Facebook
- Promociones
- Campanas
- Publicaciones pendientes
- Fechas de publicacion
- Contenido por servicio

## 10. Activos del negocio

Archivo: [activos/activos.csv](activos/activos.csv)

Sirve para controlar:

- Maquinas
- Impresoras
- Herramientas
- Equipos
- Valor
- Estado
- Ubicacion

## Flujo completo del negocio

```text
Cotizacion -> Pedido -> Planificacion -> Inventario -> Produccion -> Calidad -> Entrega -> Venta -> Reporte
```

## Objetivo

Que todo este visible desde este menu y conectado por archivos, IDs y procesos para que Imperio Atomico pueda operar como una base empresarial completa.
