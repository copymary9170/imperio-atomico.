# Módulo funcional: Gestión del Negocio (ERP papelería + sublimación + impresiones + copias + servicios)

## 1) KPIs exactos del dashboard
1. Ingresos (USD)
2. Costo de ventas (USD)
3. Gastos operativos (USD)
4. Utilidad bruta (USD)
5. Utilidad neta (USD)
6. Margen bruto (%)
7. Margen neto (%)
8. Total de ventas (transacciones)
9. Ticket promedio (USD)
10. Saldo CxC (USD)
11. Saldo CxP (USD)
12. Pedidos pendientes (cantidad)

## 2) Fórmula de cálculo de cada KPI
- **Ingresos** = `SUM(ventas.total_usd)`
- **Costo de ventas** = `SUM(ventas_detalle.cantidad * ventas_detalle.costo_unitario_usd)`
- **Gastos operativos** = `SUM(gastos.monto_usd)`
- **Utilidad bruta** = `Ingresos - Costo de ventas`
- **Utilidad neta** = `Utilidad bruta - Gastos operativos`
- **Margen bruto %** = `(Utilidad bruta / Ingresos) * 100`
- **Margen neto %** = `(Utilidad neta / Ingresos) * 100`
- **Total ventas** = `COUNT(ventas.id)`
- **Ticket promedio** = `AVG(ventas.total_usd)`
- **Saldo CxC** = `SUM(cuentas_por_cobrar.saldo_usd)`
- **Saldo CxP** = `SUM(cuentas_por_pagar_proveedores.saldo_usd)`
- **Pedidos pendientes** = `COUNT(pedidos_negocio.id WHERE estado IN ('pendiente','en_proceso'))`

## 3) Query SQL por KPI
```sql
-- KPI 1, 8, 9
SELECT
  COUNT(*) AS total_ventas,
  SUM(total_usd) AS ingresos_usd,
  AVG(total_usd) AS ticket_promedio_usd
FROM ventas
WHERE date(fecha) BETWEEN date(:desde) AND date(:hasta);

-- KPI 2
SELECT SUM(vd.cantidad * vd.costo_unitario_usd) AS costo_ventas_usd
FROM ventas_detalle vd
JOIN ventas v ON v.id = vd.venta_id
WHERE date(v.fecha) BETWEEN date(:desde) AND date(:hasta);

-- KPI 3
SELECT SUM(monto_usd) AS gastos_operativos_usd
FROM gastos
WHERE date(fecha) BETWEEN date(:desde) AND date(:hasta);

-- KPI 10
SELECT SUM(saldo_usd) AS cxc_saldo_usd
FROM cuentas_por_cobrar
WHERE estado IN ('pendiente','parcial','vencida')
  AND date(fecha) BETWEEN date(:desde) AND date(:hasta);

-- KPI 11
SELECT SUM(saldo_usd) AS cxp_saldo_usd
FROM cuentas_por_pagar_proveedores
WHERE estado IN ('pendiente','parcial','vencida')
  AND date(fecha) BETWEEN date(:desde) AND date(:hasta);

-- KPI 12
SELECT COUNT(*) AS pedidos_pendientes
FROM pedidos_negocio
WHERE estado IN ('pendiente','en_proceso')
  AND date(fecha) BETWEEN date(:desde) AND date(:hasta);
```

## 4) Tablas fuente requeridas
- `ventas`
- `ventas_detalle`
- `gastos`
- `cuentas_por_cobrar`
- `cuentas_por_pagar_proveedores`
- `costeo_ordenes`
- `pedidos_negocio`
- `clientes` (enriquecimiento CxC)

## 5) Vista consolidada por sucursal
```sql
SELECT
  COALESCE(v.sucursal, 'Matriz') AS sucursal,
  SUM(v.total_usd) AS ingresos_usd,
  SUM(vd.cantidad * vd.costo_unitario_usd) AS costo_ventas_usd,
  SUM(v.total_usd) - SUM(vd.cantidad * vd.costo_unitario_usd) AS utilidad_bruta_usd,
  COUNT(DISTINCT v.id) AS ventas
FROM ventas v
LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
WHERE date(v.fecha) BETWEEN date(:desde) AND date(:hasta)
GROUP BY 1
ORDER BY ingresos_usd DESC;
```

## 6) Vista de rentabilidad por línea de negocio
```sql
SELECT
  COALESCE(v.tipo_negocio, 'General') AS tipo_negocio,
  SUM(v.total_usd) AS ingresos_usd,
  SUM(vd.cantidad * vd.costo_unitario_usd) AS costo_ventas_usd,
  SUM(v.total_usd) - SUM(vd.cantidad * vd.costo_unitario_usd) AS utilidad_bruta_usd,
  CASE WHEN SUM(v.total_usd) > 0
       THEN ((SUM(v.total_usd) - SUM(vd.cantidad * vd.costo_unitario_usd))/SUM(v.total_usd))*100
       ELSE 0 END AS margen_bruto_pct
FROM ventas v
LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
WHERE date(v.fecha) BETWEEN date(:desde) AND date(:hasta)
GROUP BY 1
ORDER BY utilidad_bruta_usd DESC;
```

## 7) Vista de ventas por día, semana y mes
```sql
-- Día
SELECT date(fecha) AS periodo, SUM(total_usd) AS ventas_usd, COUNT(*) AS transacciones
FROM ventas
WHERE date(fecha) BETWEEN date(:desde) AND date(:hasta)
GROUP BY date(fecha)
ORDER BY periodo;

-- Semana
SELECT strftime('%Y-W%W', fecha) AS periodo, SUM(total_usd) AS ventas_usd, COUNT(*) AS transacciones
FROM ventas
WHERE date(fecha) BETWEEN date(:desde) AND date(:hasta)
GROUP BY strftime('%Y-W%W', fecha)
ORDER BY periodo;

-- Mes
SELECT strftime('%Y-%m', fecha) AS periodo, SUM(total_usd) AS ventas_usd, COUNT(*) AS transacciones
FROM ventas
WHERE date(fecha) BETWEEN date(:desde) AND date(:hasta)
GROUP BY strftime('%Y-%m', fecha)
ORDER BY periodo;
```

## 8) Vista de productos más vendidos
```sql
SELECT
  vd.descripcion AS producto,
  SUM(vd.cantidad) AS cantidad,
  SUM(vd.subtotal_usd) AS venta_usd
FROM ventas_detalle vd
JOIN ventas v ON v.id = vd.venta_id
WHERE date(v.fecha) BETWEEN date(:desde) AND date(:hasta)
GROUP BY vd.descripcion
ORDER BY cantidad DESC, venta_usd DESC
LIMIT :top;
```

## 9) Vista de servicios más rentables
```sql
SELECT
  COALESCE(o.tipo_negocio, o.tipo_proceso, 'Servicio general') AS servicio,
  COUNT(*) AS ordenes,
  SUM(o.precio_vendido_usd) AS ingresos_usd,
  SUM(o.costo_real_usd) AS costo_real_usd,
  SUM(o.precio_vendido_usd - o.costo_real_usd) AS utilidad_usd,
  CASE WHEN SUM(o.precio_vendido_usd) > 0
       THEN (SUM(o.precio_vendido_usd - o.costo_real_usd) / SUM(o.precio_vendido_usd))*100
       ELSE 0 END AS margen_pct
FROM costeo_ordenes o
WHERE date(o.fecha) BETWEEN date(:desde) AND date(:hasta)
  AND o.estado IN ('ejecutado', 'cerrado')
GROUP BY 1
ORDER BY utilidad_usd DESC
LIMIT :top;
```

## 10) Vista de pedidos pendientes
```sql
SELECT
  id, fecha, sucursal, usuario, tipo_negocio, cliente,
  descripcion, fecha_entrega, total_usd, estado,
  CAST(julianday(fecha_entrega) - julianday(date('now')) AS INTEGER) AS dias_para_entrega
FROM pedidos_negocio
WHERE estado IN ('pendiente','en_proceso')
ORDER BY date(fecha_entrega) ASC, id DESC;
```

## 11) Vista de cuentas por cobrar
```sql
SELECT
  c.id, c.fecha, cl.nombre AS cliente, c.sucursal, c.tipo_negocio,
  c.saldo_usd, c.fecha_vencimiento,
  MAX(CAST(julianday(date('now')) - julianday(date(c.fecha_vencimiento)) AS INTEGER), 0) AS dias_vencido,
  c.estado
FROM cuentas_por_cobrar c
LEFT JOIN clientes cl ON cl.id = c.cliente_id
WHERE c.estado IN ('pendiente','parcial','vencida')
ORDER BY dias_vencido DESC, c.saldo_usd DESC;
```

## 12) Vista de cuentas por pagar
```sql
SELECT
  id, fecha, sucursal, tipo_negocio, saldo_usd, fecha_vencimiento,
  MAX(CAST(julianday(date('now')) - julianday(date(fecha_vencimiento)) AS INTEGER), 0) AS dias_vencido,
  estado
FROM cuentas_por_pagar_proveedores
WHERE estado IN ('pendiente','parcial','vencida')
ORDER BY dias_vencido DESC, saldo_usd DESC;
```

## 13) Alertas automáticas del negocio
- `margen_bajo`: margen neto < 15%
- `cxc_vencida`: saldo vencido CxC > 0
- `cxp_vencida`: saldo vencido CxP > 0
- `pedidos_atrasados`: pedidos con `dias_para_entrega < 0`

## 14) Estructura del dashboard principal
1. Encabezado + filtros
2. Banda de KPI cards (12 KPIs)
3. Gráficas de ventas (día/semana/mes)
4. Consolidado por sucursal
5. Rentabilidad por línea de negocio
6. Top productos y servicios
7. Operación: pedidos pendientes + CxC + CxP
8. Panel de alertas

## 15) Widgets necesarios
- DateRangePicker (desde/hasta)
- Select sucursal
- Select usuario
- Select tipo de negocio
- KPI cards
- Line chart ventas
- Bar chart rentabilidad línea
- Table top productos
- Table servicios rentables
- Table pedidos pendientes
- Table CxC
- Table CxP
- Alert list / toast

## 16) Endpoints REST del dashboard
- `GET /api/v1/dashboard/gestion-negocio`
- `GET /api/v1/dashboard/gestion-negocio/kpis`
- `GET /api/v1/dashboard/gestion-negocio/consolidado-sucursal`
- `GET /api/v1/dashboard/gestion-negocio/rentabilidad-linea`
- `GET /api/v1/dashboard/gestion-negocio/ventas?grano=dia|semana|mes`
- `GET /api/v1/dashboard/gestion-negocio/productos-top?limit=10`
- `GET /api/v1/dashboard/gestion-negocio/servicios-rentables?limit=10`
- `GET /api/v1/dashboard/gestion-negocio/pedidos-pendientes`
- `GET /api/v1/dashboard/gestion-negocio/cxc`
- `GET /api/v1/dashboard/gestion-negocio/cxp`
- `GET /api/v1/dashboard/gestion-negocio/alertas`

Todos aceptan filtros por query params:
- `fecha_desde` (YYYY-MM-DD)
- `fecha_hasta` (YYYY-MM-DD)
- `sucursal`
- `usuario`
- `tipo_negocio`

## 17) JSON de salida para frontend (ejemplo)
```json
{
  "generated_at": "2026-03-26T14:20:00Z",
  "filters": {
    "fecha_desde": "2026-03-01",
    "fecha_hasta": "2026-03-26",
    "sucursal": "Matriz",
    "usuario": "ALL",
    "tipo_negocio": "ALL"
  },
  "dashboard": {
    "resumen": { "kpis": { "ingresos_usd": 12500.0, "margen_neto_pct": 21.4 } },
    "consolidado_sucursal": { "items": [] },
    "rentabilidad_linea": { "items": [] },
    "ventas_dia": { "grano": "dia", "series": [] },
    "ventas_semana": { "grano": "semana", "series": [] },
    "ventas_mes": { "grano": "mes", "series": [] },
    "productos_top": { "items": [] },
    "servicios_rentables": { "items": [] },
    "pedidos_pendientes": { "items": [] },
    "cuentas_por_cobrar": { "totales": { "saldo_total_usd": 0, "saldo_vencido_usd": 0 }, "items": [] },
    "cuentas_por_pagar": { "totales": { "saldo_total_usd": 0, "saldo_vencido_usd": 0 }, "items": [] },
    "alertas": { "items": [] }
  }
}
```

## 18) Filtros por fecha/sucursal/usuario/tipo negocio
Aplicación uniforme en todas las consultas:
- `date(fecha) BETWEEN date(:fecha_desde) AND date(:fecha_hasta)`
- `(:sucursal='ALL' OR sucursal=:sucursal)`
- `(:usuario='ALL' OR usuario=:usuario)`
- `(:tipo_negocio='ALL' OR tipo_negocio=:tipo_negocio)`

## 19) Reglas de actualización
- KPIs y tablas se recalculan en cada request (near-real-time).
- Cache frontend sugerido: 60 segundos.
- Eventos que invalidan cache inmediatamente: nueva venta, pago de cliente, gasto, pago a proveedor, actualización de pedido, cierre de orden de costeo.

## 20) Ejemplo funcional de pantalla
Layout sugerido para frontend web:
- Fila 1: 12 KPI cards (scroll horizontal en móvil)
- Fila 2: Gráfico línea ventas (tabs Día/Semana/Mes) + alertas
- Fila 3: Consolidado por sucursal + rentabilidad por línea
- Fila 4: Top productos + servicios rentables
- Fila 5: Pedidos pendientes
- Fila 6: CxC y CxP

Referencia funcional implementada en API local:
```bash
python -m api.gestion_negocio_http
# luego consumir: http://localhost:8091/api/v1/dashboard/gestion-negocio
```
