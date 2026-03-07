# Propuesta de evolución arquitectónica — ERP Industrial para imprentas

## 1. Diagnóstico técnico de la arquitectura actual

La arquitectura actual ya tiene una base fuerte porque conecta costos técnicos con operación real (Inventario + Producción + Cotización + Activos). Sin embargo, para escalar a operación industrial con trazabilidad fina y márgenes robustos, conviene reforzar cuatro ejes:

1. **Modelo de dominio unificado de costos** (evitar fórmulas aisladas por módulo).
2. **Motor de eventos transaccionales** (qué cambió, cuándo, por qué y por cuál orden).
3. **Normalización de unidades y conversiones** (cm², ml, unidades, pliegos, metros lineales).
4. **Planificación industrial avanzada** (capacidad, cuellos de botella, priorización y simulación).

---

## 2. Mejoras estructurales (arquitectura de software)

## 2.1 Separación por capas de dominio

Estandarizar servicios por contexto de negocio:

- `inventory_domain/`
- `production_domain/`
- `quotation_domain/`
- `assets_domain/`
- `analytics_domain/`
- `industrial_services/` (CMYK, corte, sublimación)

Cada dominio con:
- `models.py` (entidades y value objects)
- `service.py` (reglas de negocio)
- `repository.py` (acceso SQLite)
- `events.py` (eventos de integración)

Beneficio: desacopla UI (Streamlit) de lógica crítica y evita duplicar reglas entre módulos.

## 2.2 Event sourcing ligero (híbrido)

Sin migrar todo a event sourcing puro, agregar tabla central de eventos:

### `erp_event_log`
- `id`
- `event_type` (ej: `inventario.consumido`, `orden.creada`, `cotizacion.aprobada`)
- `aggregate_type` (orden, cotizacion, inventario_item, activo)
- `aggregate_id`
- `payload_json`
- `causation_id`
- `correlation_id`
- `created_at`
- `created_by`

Uso:
- Trazabilidad industrial completa.
- Auditoría de costos.
- Reproceso de métricas sin alterar transacciones.

## 2.3 Motor unificado de costos

Crear un servicio transversal: `CostEngineService` con contratos por proceso:
- `calcular_cmyk(...)`
- `calcular_corte(...)`
- `calcular_sublimacion(...)`
- `calcular_manual(...)`

Todos devuelven una estructura homogénea:

```json
{
  "costo_material": 0,
  "costo_mano_obra": 0,
  "costo_desgaste": 0,
  "costo_energia": 0,
  "costo_indirecto": 0,
  "costo_total": 0,
  "moneda": "USD",
  "version_formula": "v1.0"
}
```

Esto permite:
- comparabilidad inter-módulo,
- histórico de cambios de fórmula,
- cotizaciones consistentes.

## 2.4 Catálogo de unidades y conversiones

Crear tablas:
- `unidad_medida` (ml, cm2, m_lineal, unidad, pliego)
- `factor_conversion` (de_uom, a_uom, factor)

Y en inventario:
- `uom_compra`
- `uom_stock`
- `uom_consumo`

Beneficio: evita errores cuando producción consume cm² pero compras llegan en rollos/pliegos.

---

## 3. Optimización de cálculos por módulo

## 3.1 Inventario

### Mejoras
1. **Costo promedio móvil + lote opcional**:
   - Modo A: promedio móvil (rápido).
   - Modo B: por lote/FEFO para materiales críticos.
2. **Merma parametrizada por proceso**:
   - `merma_pct_corte`, `merma_pct_impresion`, `merma_pct_sublimacion`.
3. **Reserva de inventario por orden**:
   - reserva al aprobar cotización,
   - descuento definitivo al iniciar/confirmar producción.

### Fórmula sugerida
`stock_disponible = stock_fisico - stock_reservado`

## 3.2 CMYK

### Mejoras
1. Perfil ICC y corrección por sustrato.
2. Factor por modo de impresión (borrador/calidad/foto).
3. Diferenciar cobertura teórica vs real (aprendizaje histórico).

### Ajuste recomendado
`ml_real_estimado = ml_teorico * factor_equipo * factor_mantenimiento * factor_sustrato`

## 3.3 Corte industrial

### Mejoras
1. Separar **tiempo de trayecto en vacío** vs **tiempo de corte efectivo**.
2. Penalización por microcontornos (incrementa tiempo y desgaste).
3. Curva de desgaste no lineal para cuchilla (fin de vida más costoso).

### Fórmula avanzada
`desgaste_cuchilla = cm_corte * k1 + (microsegmentos * k2) + (pasadas * k3)`

## 3.4 Sublimación

### Mejoras
1. Modelo térmico por ciclo: precalentamiento + prensado + enfriado.
2. Energía por equipo real (kWh medido) en vez de fijo.
3. Curva de productividad por operador (aprendizaje).

## 3.5 Activos

### Mejoras
1. Depreciación técnica por uso real, no solo por tiempo.
2. Índice de salud (`health_score`) por horas, fallas y sobrecarga.
3. Alertas predictivas de mantenimiento por patrón de producción.

---

## 4. Integración fuerte Producción ↔ Inventario

## 4.1 Flujo recomendado de estados

1. Cotización aprobada
2. Orden creada
3. **Reserva de materiales**
4. Orden liberada a producción
5. Consumo real (pick/confirm)
6. Cierre de orden
7. Ajuste de diferencias (merma real vs estándar)

## 4.2 Tablas sugeridas

### `inventario_reserva`
- `id`, `orden_id`, `item_id`, `cantidad_reservada`, `estado`, `created_at`

### `inventario_movimiento`
- agregar `orden_id`, `proceso`, `origen_evento`, `costo_unitario_aplicado`

### `produccion_consumo_real`
- `id`, `orden_id`, `item_id`, `cantidad_plan`, `cantidad_real`, `desviacion_pct`

Beneficio: elimina “consumos fantasma” y mejora exactitud de costo estándar vs real.

---

## 5. Automatización avanzada (nivel planta industrial)

## 5.1 Planificador APS básico

Motor de planificación con restricciones:
- capacidad por máquina/turno,
- prioridad cliente,
- SLA de entrega,
- setup dependiente de material/color/proceso.

Salida:
- secuencia óptima por recurso,
- fecha promesa más realista,
- alertas de sobrecarga.

## 5.2 Reglas inteligentes de ruteo

Dado un trabajo compuesto, dividir automáticamente en operaciones:
- impresión CMYK,
- laminado,
- corte,
- sublimación,
- ensamblaje.

Generar una **ruta de fabricación** (`routing`) con tiempos y costos por operación.

## 5.3 Captura de datos en piso

Añadir módulo “Shop Floor”:
- inicio/pausa/fin por orden,
- scrap/merma en tiempo real,
- causa de paro,
- productividad por operador.

## 5.4 Telemetría de equipos (cuando aplique)

Integrar lectura semiautomática (API/CSV/OCR) de:
- contadores de impresora,
- horas de plotter,
- ciclos de plancha.

Esto mejora costo real y mantenimiento predictivo.

---

## 6. Nuevos módulos industriales recomendados

## 6.1 Módulo de Planificación y Capacidad
- calendario de planta,
- asignación máquina-operador,
- simulación “what-if”.

## 6.2 Módulo de Calidad (QA/QC)
- checklist por proceso,
- no conformidades,
- reprocesos y costo de mala calidad.

## 6.3 Módulo de Mantenimiento (CMMS ligero)
- OT de mantenimiento preventivo/correctivo,
- repuestos,
- MTBF / MTTR por activo.

## 6.4 Módulo de Ingeniería de Producto
- recetas técnicas (BOM + ruta),
- versión de proceso,
- costos estándar por SKU.

## 6.5 Módulo de Compras Inteligentes
- reposición por punto de pedido dinámico,
- sugerencias por forecast de producción,
- ranking de proveedores (precio + calidad + entrega).

---

## 7. Modelo de datos mínimo adicional (prioridad alta)

## 7.1 `orden_operacion`
- `id`, `orden_id`, `operacion`, `recurso_id`, `estado`, `tiempo_est`, `tiempo_real`, `secuencia`

## 7.2 `orden_costo_detalle`
- `id`, `orden_id`, `tipo_costo`, `monto`, `fuente` (estimado/real), `version_formula`

## 7.3 `formula_version`
- `id`, `proceso`, `version`, `json_formula`, `vigente_desde`, `vigente_hasta`

## 7.4 `kpi_diario_planta`
- `fecha`, `otd`, `scrap_pct`, `utilizacion_maquina`, `margen_real_pct`, `wip_total`

---

## 8. KPIs industriales para control ejecutivo

1. **OTD** (on-time delivery)
2. **Costo estimado vs costo real** por orden
3. **Merma real %** por proceso/material
4. **Utilización de máquina** por turno
5. **Tiempo de ciclo real** vs estándar
6. **Margen bruto real** por tipo de trabajo
7. **Rotación de inventario** y días de cobertura
8. **Tasa de reproceso** y costo de no calidad

---

## 9. Roadmap de implementación recomendado

## Fase A (4–6 semanas) — Robustez base
- CostEngine unificado
- reservas de inventario por orden
- versionado de fórmulas
- tabla de eventos `erp_event_log`

## Fase B (6–8 semanas) — Industrialización
- operaciones por orden (`orden_operacion`)
- captura de tiempos reales
- desviaciones estándar vs real
- dashboard KPI planta

## Fase C (8–12 semanas) — Optimización avanzada
- planificador APS básico
- mantenimiento predictivo inicial
- sugerencias inteligentes de compras/reposición

---

## 10. Principios de diseño para no romper la lógica actual

1. **Compatibilidad hacia atrás**: no remover columnas/flujo vigente sin capa de adaptación.
2. **Feature flags** para activar mejoras por módulo.
3. **Migraciones idempotentes SQLite** con respaldo automático.
4. **Contratos estables entre módulos** (payloads versionados).
5. **Pruebas de regresión por costo**: mismo input, mismo costo esperado por versión.

---

## 11. Resultado esperado

Con esta evolución, el ERP pasa de ser un sistema funcional integrado a una plataforma industrial con:
- costos trazables y auditables,
- planificación de capacidad,
- control real de merma y desgaste,
- cotizaciones más precisas,
- mayor margen y previsibilidad operativa.
