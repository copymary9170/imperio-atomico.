# Base de Operaciones - Imperio Atomico

Esta base organiza las areas principales del negocio de impresion, papeleria, sublimacion, servicios y corte de alta gama.

## Objetivo

Saber con claridad:

- Cuanto se debe pagar a trabajadores.
- Cuanto ahorrar para salidas, expos y aprendizaje.
- Que seguros, pensiones y obligaciones se deben cubrir.
- Cuando surtir material.
- Que publicar en redes y canales de venta.
- Que pedidos de clientes estan activos.
- Como calcular precios justos por servicio.

## Modulos conectados

```text
catalogo/productos.csv
servicios/lista-servicios.csv
precios/calculadora-precios.csv
inventario/stock.csv
compras/materiales.csv
pedidos/pedidos-clientes.csv
trabajadores/nomina.csv
finanzas/presupuesto-mensual.csv
calendario/recordatorios.csv
marketing/calendario-publicaciones.csv
reportes/resumen.md
```

## Areas del negocio

| Area | Archivo principal | Para que sirve |
|---|---|---|
| Catalogo | `catalogo/productos.csv` | Productos fisicos y vendibles |
| Servicios | `servicios/lista-servicios.csv` | Impresion, papeleria, sublimacion y corte |
| Precios | `precios/calculadora-precios.csv` | Calcular precios justos |
| Inventario | `inventario/stock.csv` | Saber que material hay |
| Compras | `compras/materiales.csv` | Saber que surtir y cuando |
| Pedidos | `pedidos/pedidos-clientes.csv` | Controlar entregas de clientes |
| Trabajadores | `trabajadores/nomina.csv` | Calcular pagos y responsabilidades |
| Finanzas | `finanzas/presupuesto-mensual.csv` | Separar dinero por categoria |
| Calendario | `calendario/recordatorios.csv` | Fechas de surtido, pagos, clases y expos |
| Marketing | `marketing/calendario-publicaciones.csv` | Que publicar y cuando |

## Regla de oro

Cada movimiento debe tener un ID:

- Producto: `IA-0001`
- Servicio: `SRV-0001`
- Material: `MAT-0001`
- Pedido: `PED-0001`
- Trabajador: `TRB-0001`
- Recordatorio: `REC-0001`
- Publicacion: `PUB-0001`

Esto permite conectar todo sin perder informacion.
