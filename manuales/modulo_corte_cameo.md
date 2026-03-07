# Módulo Industrial de Corte (Silhouette Cameo) — Arquitectura ERP

## 1) Objetivo
Diseñar un módulo de **pre-análisis, cotización y ejecución** de trabajos de corte para imprentas/talleres gráficos, integrando Inventario, Activos, Herramientas, Producción y Cotizaciones.

El módulo debe:
- Analizar archivos de corte sin consumir inventario (Fase 1).
- Enviar datos técnicos/costos al módulo de cotizaciones (Fase 2).
- Consumir inventario y registrar desgaste **solo tras confirmación** del cliente (Fase 3).

---

## 2) Flujo funcional por fases

## Fase 1 — Pre-análisis (NO consume inventario)
Entrada permitida:
- SVG, PNG, JPG, PDF, DXF, imagen escaneada.

Salida del análisis:
- `area_cm2`
- `cm_corte`
- `complejidad` (nodos/contornos)
- `numero_piezas`
- `tiempo_estimado_seg`
- `desgaste_cuchilla_estimado`
- `desgaste_maquina_estimado`
- `costo_estimado_total`

Reglas:
- No crea movimientos de inventario.
- No registra desgaste contable definitivo.
- Solo crea un **registro técnico estimado** reutilizable por cotización.

## Fase 2 — Cotización
Acción UI:
- Botón: **"Enviar a Cotización"**

Payload al módulo de cotizaciones:
- `tipo_produccion = "corte"`
- `archivo`
- `cm_corte`
- `material`
- `tiempo_estimado`
- `costo_base`

Resultado:
- Se crea ítem cotizable con trazabilidad al pre-análisis.

## Fase 3 — Confirmación del cliente
Cuando cotización pasa a aprobada:
1. Crear orden de producción (`orden_produccion_corte`).
2. Verificar disponibilidad de material.
3. Descontar inventario (excepto `material_cliente = true`).
4. Registrar desgaste real de máquina.
5. Registrar desgaste real de cuchilla/tapete.
6. Enviar al tablero de producción.

---

## 3) Arquitectura lógica recomendada

## 3.1 Capas
1. **UI/Workflow** (Streamlit u otra interfaz): carga archivo, visualización de métricas, envío a cotización.
2. **Servicios de Dominio**:
   - `CorteAnalisisService`
   - `CorteCosteoService`
   - `CorteProduccionService`
   - `CorteIntegracionCotizacionesService`
3. **Adaptadores de archivo**:
   - Parser SVG/DXF/PDF vectorial.
   - Raster pipeline (PNG/JPG/escaneo) con vectorización asistida.
4. **Persistencia**: tablas técnicas + tablas transaccionales.
5. **Integración ERP**: inventario, activos, herramientas, producción, cotizaciones.

## 3.2 Componentes clave
- **File Intake**: valida formato, tamaño, DPI, dimensiones.
- **Geometry Engine**: obtiene contornos, nodos, perímetros, área.
- **Estimator Engine**: estima tiempo según material, velocidad/presión y complejidad.
- **Cost Engine**: aplica fórmula de costo total.
- **Quotation Bridge**: publica ítems al módulo de cotizaciones.
- **Production Bridge**: materializa orden y movimientos reales tras aprobación.

---

## 4) Modelo de datos (tablas sugeridas)

> Nota: nombres en snake_case para consistencia SQL.

## 4.1 Catálogos y configuración

### `corte_maquina_perfil`
- `id` (PK)
- `activo_id` (FK -> activos)
- `nombre_perfil`
- `ancho_max_cm`
- `largo_max_cm`
- `velocidad_max_cm_s`
- `precision_mm`
- `estado` (activo/inactivo)
- `created_at`, `updated_at`

### `corte_herramienta_perfil`
- `id` (PK)
- `herramienta_id` (FK -> herramientas)
- `tipo` (cuchilla/tapete)
- `vida_util_cm_corte`
- `costo_reposicion`
- `desgaste_actual_cm`
- `estado`
- `created_at`, `updated_at`

### `corte_material_config`
- `id` (PK)
- `inventario_item_id` (FK -> inventario)
- `material_nombre`
- `dureza` (escala 1–10)
- `presion_recomendada`
- `velocidad_recomendada_cm_s`
- `pasadas_recomendadas`
- `factor_complejidad` (ej. 1.00, 1.15, 1.30)
- `costo_cm2`
- `merma_pct`
- `estado`
- `created_at`, `updated_at`

### `corte_parametros_costeo`
- `id` (PK)
- `sede_id` / `unidad_negocio_id` (nullable)
- `salario_operador_por_seg`
- `factor_setup_seg` (tiempo fijo preparación)
- `factor_calibracion_seg`
- `factor_riesgo`
- `vigente_desde`
- `vigente_hasta`

## 4.2 Transaccionales de análisis y cotización

### `corte_preanalisis`
- `id` (PK)
- `cliente_id` (FK)
- `archivo_path`
- `archivo_hash`
- `archivo_tipo` (svg/png/jpg/pdf/dxf/scan)
- `material_sugerido_id` (FK -> corte_material_config, nullable)
- `material_cliente` (bool)
- `estado` (borrador/analizado/enviado_cotizacion/cancelado)
- `created_by`, `created_at`, `updated_at`

### `corte_preanalisis_resultado`
- `id` (PK)
- `preanalisis_id` (FK -> corte_preanalisis)
- `area_cm2`
- `cm_corte`
- `complejidad_nodos`
- `complejidad_contornos`
- `numero_piezas`
- `tiempo_estimado_seg`
- `desgaste_maquina_estimado`
- `desgaste_cuchilla_estimado`
- `costo_material_estimado`
- `costo_mano_obra_estimado`
- `costo_total_estimado`
- `json_metricas` (detalles del motor)
- `version_modelo_estimacion`
- `created_at`

### `corte_cotizacion_link`
- `id` (PK)
- `preanalisis_id` (FK)
- `cotizacion_id` (FK -> cotizaciones)
- `cotizacion_item_id` (FK -> cotizaciones_detalle)
- `payload_enviado_json`
- `estado` (pendiente/enviado/error)
- `created_at`

## 4.3 Transaccionales de producción

### `corte_orden_produccion`
- `id` (PK)
- `preanalisis_id` (FK)
- `cotizacion_id` (FK)
- `cliente_id` (FK)
- `maquina_perfil_id` (FK)
- `herramienta_perfil_id` (FK)
- `material_config_id` (FK, nullable)
- `material_cliente` (bool)
- `estado` (creada/planificada/en_proceso/completada/cancelada)
- `fecha_programada`
- `tiempo_estimado_seg`
- `tiempo_real_seg` (nullable)
- `created_at`, `updated_at`

### `corte_consumo_material`
- `id` (PK)
- `orden_id` (FK -> corte_orden_produccion)
- `inventario_item_id` (FK)
- `cantidad_cm2`
- `cantidad_unidad_inventario`
- `costo_unitario`
- `costo_total`
- `movimiento_inventario_id` (FK)
- `created_at`

### `corte_desgaste_registro`
- `id` (PK)
- `orden_id` (FK)
- `tipo` (maquina/cuchilla/tapete)
- `referencia_id` (activo_id o herramienta_id)
- `cm_corte_aplicados`
- `desgaste_monetario`
- `vida_util_restante_cm` (nullable)
- `created_at`

### `corte_evento_produccion`
- `id` (PK)
- `orden_id` (FK)
- `evento` (inicio/pausa/reanudar/finalizar/error)
- `timestamp`
- `usuario_id`
- `meta_json`

---

## 5) Lógica de cálculo recomendada

## 5.1 Fórmula base
`costo_total = desgaste_maquina + desgaste_cuchilla + material + mano_obra`

Donde:
- `desgaste_maquina = cm_corte * desgaste_por_cm_equipo`
- `desgaste_cuchilla = cm_corte * desgaste_por_cm_cuchilla`
- `material = area_cm2 * costo_material_cm2` (si `material_cliente = false`, si no = 0)
- `mano_obra = tiempo_estimado_seg * salario_operador_por_seg`

## 5.2 Estimación de tiempo sugerida
`tiempo_estimado_seg = ((cm_corte / velocidad_efectiva_cm_s) * factor_complejidad * pasadas) + setup_seg + calibracion_seg`

Con:
- `velocidad_efectiva_cm_s = velocidad_recomendada_cm_s * factor_estado_maquina * factor_dureza_material`
- `factor_complejidad` puede basarse en nodos/contornos por pieza.

## 5.3 Cálculo de complejidad
Métrica compuesta sugerida:
- `score_complejidad = (nodos * 0.6) + (contornos * 0.3) + (piezas * 0.1)`

Normalización a categorías:
- Baja, Media, Alta, Muy alta (por umbrales configurables).

---

## 6) Pipeline técnico por tipo de archivo

## 6.1 Vectoriales (SVG, DXF, PDF vectorial)
1. Parsear paths/polilíneas.
2. Convertir a geometría unificada (segmentos/curvas discretizadas).
3. Calcular:
   - Perímetro total (cm corte)
   - Área cerrada
   - Nodos y contornos
4. Detectar piezas por componentes conectados.

## 6.2 Raster (PNG, JPG, escaneado)
1. Preprocesado (escala de grises, binarización, limpieza ruido).
2. Detección de bordes y contornos.
3. Vectorización asistida.
4. Calcular métricas geométricas sobre el vector resultante.
5. Marcar `confidence_score` del análisis; si bajo, pedir validación manual.

---

## 7) Integraciones con módulos existentes

## 7.1 Activos
- Obtener `desgaste_por_cm_equipo` desde perfil de activo o derivarlo de:
  - inversión,
  - vida útil,
  - uso acumulado.

## 7.2 Herramientas
- Cuchilla/tapete con vida útil en cm y costo reposición.
- Actualizar desgaste acumulado solo en ejecución real (Fase 3).

## 7.3 Inventario
- Validar stock antes de lanzar producción.
- Si `material_cliente = true`, no generar movimiento de salida.

## 7.4 Cotizaciones
- Endpoint interno/evento: `corte.preanalisis.enviado_a_cotizacion`.
- Guardar vínculo para trazabilidad y recotización.

## 7.5 Producción
- Crear orden en tablero con estado inicial `creada`.
- Permitir captura de tiempos reales para retroalimentar estimador.

---

## 8) Reglas de negocio críticas
1. **No descontar inventario en Fase 1 ni Fase 2.**
2. Toda orden de corte debe provenir de una cotización aprobada (o excepción autorizada).
3. Si `material_cliente = true`, costo de material = 0 y sin salida de inventario.
4. Si no hay stock y `material_cliente = false`, bloquear paso a producción.
5. Registrar diferencias entre estimado y real para mejora continua.

---

## 9) API interna sugerida

## 9.1 Pre-análisis
- `POST /api/corte/preanalisis`
- `POST /api/corte/preanalisis/{id}/analizar`
- `GET /api/corte/preanalisis/{id}`

## 9.2 Cotización
- `POST /api/corte/preanalisis/{id}/enviar-cotizacion`

## 9.3 Producción
- `POST /api/corte/ordenes` (desde cotización aprobada)
- `POST /api/corte/ordenes/{id}/iniciar`
- `POST /api/corte/ordenes/{id}/finalizar`

---

## 10) Roadmap de optimizaciones futuras
1. Optimización de nesting/tapete (minimizar merma).
2. Cálculo automático de trayectorias óptimas (orden de corte).
3. Simulación de carga de máquina por turno.
4. Telemetría de tiempo real y desgaste real por job.
5. Motor de estimación híbrido (reglas + ML) calibrado con históricos.

---

## 11) Plan de implementación incremental

## Sprint 1 (MVP técnico)
- Tablas de `preanalisis` + `resultado` + `material_config`.
- Parser SVG básico y cálculo de cm/área/contornos.
- Cálculo de costo estimado.
- Botón "Enviar a Cotización".

## Sprint 2 (ejecución real)
- Orden de producción de corte.
- Integración inventario, activos y herramientas en Fase 3.
- Registro de desgaste real.

## Sprint 3 (calidad industrial)
- Raster/vectorización.
- Captura de tiempos reales y desviación estimado vs real.
- Reglas avanzadas por material/dureza.

## Sprint 4 (optimización)
- Nesting en tapete.
- Simulación y analítica predictiva.
