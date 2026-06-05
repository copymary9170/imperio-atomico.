# Reglas de negocio Copy Mary

## Reglas obligatorias

1. Ninguna venta puede registrarse en 0.
2. Ninguna cotizacion puede tener precio final menor al costo total.
3. Ninguna impresion a color puede tener un precio menor que una impresion blanco y negro equivalente.
4. No se permite vender inventario con stock igual o menor a 0.
5. Todo pedido debe provenir de una cotizacion aprobada.
6. Toda venta debe estar asociada a un cliente.
7. Todo material debe tener stock minimo definido.
8. Cuando stock_actual <= stock_minimo se genera alerta de reabastecimiento.
9. Toda venta debe registrar utilidad.
10. Todo servicio debe tener costo_base y precio_sugerido.

## Formula financiera

Precio Final = (Costo Papel + Costo Tinta + Costos Operativos + Mano de Obra) * (1 + Margen)

## Indicadores

- Ganancia diaria
- Ganancia mensual
- Materiales criticos
- Servicios mas vendidos
- Clientes recurrentes
- Utilidad por servicio
