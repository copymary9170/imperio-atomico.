# Sistema conectado de Imperio Atómico

Este documento define cómo se conectan las partes principales del negocio: catálogo, inventario, clientes, ventas y reportes.

## Regla principal

Todo producto debe tener un `producto_id` único. Ese mismo ID se usa en catálogo, inventario, ventas y reportes.

Ejemplo:

```text
producto_id: IA-0001
nombre: Producto inicial
```

## Módulos conectados

```text
catalogo/productos.csv
        │ usa producto_id
        ▼
inventario/stock.csv
        │ actualiza existencias
        ▼
ventas/ventas.csv
        │ registra producto_id vendido
        ▼
reportes/resumen.md
```

## Flujo de trabajo

1. Crear o actualizar el producto en `catalogo/productos.csv`.
2. Registrar existencias en `inventario/stock.csv` usando el mismo `producto_id`.
3. Cuando haya una venta, registrarla en `ventas/ventas.csv` usando el mismo `producto_id`.
4. Consultar `reportes/resumen.md` para revisar qué se vende, qué falta y qué productos están activos.

## Archivos principales

| Archivo | Función | Se conecta con |
|---|---|---|
| `catalogo/productos.csv` | Lista maestra de productos | Inventario, ventas, reportes |
| `inventario/stock.csv` | Cantidad disponible por producto | Catálogo, ventas |
| `clientes/clientes.csv` | Registro de clientes | Ventas |
| `ventas/ventas.csv` | Registro de ventas | Catálogo, inventario, clientes |
| `reportes/resumen.md` | Vista general del negocio | Todos los módulos |

## Campos clave

### Producto

- `producto_id`: identificador único del producto.
- `nombre`: nombre del producto.
- `categoria`: familia o tipo.
- `precio`: precio público.
- `estado`: activo, pausado o agotado.

### Inventario

- `producto_id`: conecta con catálogo.
- `stock_actual`: unidades disponibles.
- `stock_minimo`: punto de alerta.
- `ubicacion`: dónde está guardado.

### Venta

- `venta_id`: identificador de la venta.
- `fecha`: fecha de la venta.
- `producto_id`: conecta con catálogo e inventario.
- `cliente_id`: conecta con clientes.
- `cantidad`: unidades vendidas.
- `total`: monto total.

## Reglas para mantener todo conectado

- Nunca cambies un `producto_id` después de crearlo.
- No registres inventario sin que el producto exista en catálogo.
- No registres ventas con productos inexistentes.
- Usa siempre el mismo formato de IDs:
  - Productos: `IA-0001`, `IA-0002`, `IA-0003`
  - Clientes: `CL-0001`, `CL-0002`, `CL-0003`
  - Ventas: `VT-0001`, `VT-0002`, `VT-0003`

## Próxima mejora técnica

Crear un script que valide automáticamente que:

- Todos los productos del inventario existan en el catálogo.
- Todas las ventas usen productos existentes.
- Todas las ventas usen clientes existentes.
- Ningún producto tenga stock negativo.
