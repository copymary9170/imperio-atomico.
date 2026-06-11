# Módulos de Imperio Atómico ERP

Este ERP está diseñado para administrar Copy Mary sin convertir la aplicación en un almacén de archivos pesados.

## Principio general

El sistema debe guardar información administrativa, operativa y financiera:

- Ventas.
- Caja.
- Inventario.
- Clientes.
- Cotizaciones.
- Producción.
- Costos.
- Reportes.
- Respaldos.

No debe guardar por defecto documentos personales o archivos enviados por clientes para imprimir.

## Manejo de archivos de clientes

Los archivos de clientes se consideran temporales salvo que exista una razón clara para conservarlos.

Opciones recomendadas para registrar el estado del archivo:

- No guardado.
- Guardado externamente.
- Temporal.
- Eliminado después de imprimir.

Ejemplos de observación:

```text
Archivo recibido por WhatsApp. No se conserva.
```

```text
Archivo guardado externamente por solicitud del cliente.
```

```text
Diseño reutilizable guardado fuera del ERP.
```

## Módulos principales

### Día / Caja
Control diario de apertura, movimientos, ventas, gastos, cierre y diferencias de caja.

### Panel de control
Resumen operativo, alertas, métricas y visión general del negocio.

### Inventario / Almacén
Productos, stock, movimientos, kardex, compras, proveedores, catálogo y unidades fraccionadas.

### Clientes y contactos
Datos básicos de clientes, historial comercial y notas importantes.

### Ventas
Registro de operaciones comerciales, métodos de pago, descuentos, costos y utilidad.

### Cotizaciones
Presupuestos para trabajos de impresión, papelería, sublimación, diseño y otros servicios.

### Producción
Seguimiento de trabajos, diseños, CMYK, rutas, control de calidad, mermas y despacho.

### Costeo y márgenes
Cálculo de costos, precios mínimos, margen, rentabilidad, materiales y mano de obra.

### Finanzas
Tesorería, gastos, cuentas por pagar, presupuesto, conciliación, impuestos y contabilidad.

### Reportes
Reportes diarios, semanales y mensuales sobre ventas, caja, inventario y rentabilidad.

### Respaldo
Copia de seguridad local y externa de la información administrativa del ERP.

## Qué no debe guardarse en el repositorio

- Archivos de clientes.
- PDFs de impresión de uso único.
- Fotos personales.
- Cédulas o documentos privados.
- Bases de datos locales sin protección.
- Secrets, tokens o contraseñas.
- Respaldos sin cifrado.
