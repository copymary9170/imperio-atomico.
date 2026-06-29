# Legal V4 Enterprise — Auditoría de brechas y plan de reconstrucción

## 1. Propósito

Este documento establece el alcance de reconstrucción del Departamento Jurídico del ERP y evita considerar como terminado un módulo que todavía no satisface los requisitos de arquitectura, seguridad, gobierno, cumplimiento, gestión documental y operación empresarial.

La reconstrucción parte del estado actual de `main`, conserva compatibilidad con los datos existentes y reemplaza gradualmente las implementaciones Legal V2/V4 mediante migraciones idempotentes y adaptadores de legado.

## 2. Diagnóstico del estado actual

La versión actual aporta una base funcional útil: expedientes, versiones, documentos, eventos de workflow, obligaciones, tareas y auditoría encadenada. Sin embargo, el diseño todavía está concentrado principalmente en:

- `legal_v4/domain.py`
- `legal_v4/schema.py`
- `legal_v4/service.py`
- `legal_v4/ui.py`

Esto no implementa todavía la arquitectura limpia declarada en la documentación. Persisten las siguientes brechas críticas:

1. No existe separación efectiva entre dominio, aplicación, infraestructura, repositorios, seguridad, automatización, reportes y UI.
2. El esquema actual modela expedientes genéricos, pero no agregados empresariales completos para contratos, litigios, privacidad, propiedad intelectual, reclamos, garantías, licencias, gobierno corporativo y cumplimiento.
3. La autorización no está centralizada como política de aplicación con denegación por defecto y permisos por recurso/acción.
4. No existe un modelo completo de partes, organizaciones, contactos, jurisdicciones, autoridades, asesores externos y relaciones entre expedientes.
5. La gestión documental no contiene clasificación documental completa, metadatos normalizados, check-in/check-out, restauración, comparación, disposición, retención y cadena de custodia.
6. La firma digital es solo una preparación de metadatos; no existe proveedor, verificación, sellado de tiempo ni validación de integridad firmada.
7. Faltan comentarios, menciones, adjuntos por entidad, timeline unificado y notificaciones persistentes.
8. La auditoría no incluye todavía de forma garantizada IP, navegador, dispositivo, sesión, correlación, motivo, resultado y política aplicada en cada acción sensible.
9. No existe motor de automatización jurídicamente configurable para alertas, renovaciones, SLA, escalamiento y obligaciones periódicas.
10. No hay pruebas de integración suficientes sobre SQLite, migración de datos reales, permisos, almacenamiento documental y smoke tests de Streamlit.
11. La navegación mantiene coexistencia de Legal V2 y Legal V4 sin una estrategia de retiro completamente ejecutada.
12. No se ha demostrado preparación para producción mediante ensayo de migración sobre una copia de `imperio.db`, verificación de rollback, pruebas de carga y revisión de seguridad.

## 3. Arquitectura objetivo

```text
legal/
├── domain/
│   ├── common/
│   ├── matters/
│   ├── contracts/
│   ├── documents/
│   ├── privacy/
│   ├── intellectual_property/
│   ├── claims/
│   ├── litigation/
│   ├── compliance/
│   ├── risks/
│   ├── licenses/
│   └── governance/
├── application/
│   ├── commands/
│   ├── queries/
│   ├── dto/
│   ├── policies/
│   └── use_cases/
├── infrastructure/
│   ├── sqlite/
│   ├── storage/
│   ├── signatures/
│   ├── hashing/
│   ├── notifications/
│   └── clock/
├── repositories/
├── services/
├── security/
├── audit/
├── automation/
├── reports/
├── validators/
├── migrations/
├── ui/
│   ├── pages/
│   ├── components/
│   ├── forms/
│   └── presenters/
└── legacy/
```

### Reglas arquitectónicas obligatorias

- La UI no ejecuta SQL, no crea tablas y no decide permisos.
- Los casos de uso controlan transacciones y autorización.
- El dominio no depende de Streamlit, pandas, SQLite ni rutas de archivos.
- Los repositorios se consumen mediante interfaces explícitas.
- Toda mutación sensible genera auditoría inmutable.
- Las migraciones son versionadas, idempotentes y verificables.
- Los registros aprobados, publicados o firmados nunca se sobrescriben.
- La denegación de acceso es el comportamiento predeterminado.

## 4. Modelo funcional requerido

### 4.1 Núcleo común

- Expedientes jurídicos.
- Partes y contrapartes.
- Personas, organizaciones y contactos.
- Responsables, revisores y aprobadores.
- Jurisdicciones, autoridades y asesores externos.
- Relaciones entre expedientes.
- Etiquetas, comentarios, menciones, adjuntos y timeline.
- Calendario, tareas, SLA, alertas y escalamiento.

### 4.2 Gestión contractual

- Contratos con clientes, proveedores, trabajadores y terceros.
- Plantillas, cláusulas, anexos, adendas y versiones.
- Solicitud, redacción, revisión, aprobación, firma, vigencia, renovación, terminación y archivo.
- Obligaciones contractuales, hitos, montos, monedas, garantías y penalidades.
- Matriz de riesgos y desviaciones de cláusulas.

### 4.3 Privacidad y documentos públicos

- Aviso legal.
- Términos y condiciones.
- Política de privacidad.
- Política de cookies.
- Consentimientos y revocaciones.
- Finalidades, bases jurídicas, categorías de datos, encargados y transferencias.
- Registro de versiones publicadas y evidencia de aceptación.

### 4.4 Propiedad intelectual

- Marcas, nombres comerciales, dominios, diseños y derechos de autor.
- Solicitudes, registros, renovaciones, oposiciones y licencias.
- Titulares, territorios, clases y evidencias.

### 4.5 Reclamos, garantías y devoluciones

- Recepción, clasificación, SLA, investigación, decisión, compensación y cierre.
- Relación con clientes, ventas, productos, servicios y documentos.
- Evidencias, comunicaciones y aprobación de excepciones.

### 4.6 Litigios y controversias

- Demandas, arbitrajes, mediaciones y procedimientos administrativos.
- Partes, pretensiones, cuantías, tribunales, abogados, actuaciones, audiencias y plazos.
- Evidencias, cadena de custodia, reservas y estrategia.

### 4.7 Cumplimiento, riesgos y licencias

- Obligaciones normativas.
- Controles, pruebas, hallazgos, planes de acción y evidencias.
- Riesgos inherentes y residuales.
- Licencias, permisos, renovaciones y autoridades.
- Matrices de cumplimiento y reportes ejecutivos.

### 4.8 Gobierno corporativo

- Órganos, cargos, accionistas y poderes.
- Actas, resoluciones, decisiones y libros corporativos.
- Convocatorias, quórum, votaciones, firmas y seguimiento de acuerdos.

## 5. Esquema de datos objetivo

El esquema deberá dividirse por agregados y evitar una tabla genérica como único contenedor. Como mínimo:

- `legal_matters`
- `legal_matter_links`
- `legal_parties`
- `legal_party_contacts`
- `legal_matter_parties`
- `legal_documents`
- `legal_document_versions`
- `legal_document_signatures`
- `legal_document_access_log`
- `legal_comments`
- `legal_timeline_events`
- `legal_tasks`
- `legal_calendar_events`
- `legal_notifications`
- `legal_contracts`
- `legal_contract_parties`
- `legal_contract_clauses`
- `legal_contract_obligations`
- `legal_contract_renewals`
- `legal_privacy_notices`
- `legal_consents`
- `legal_cookie_records`
- `legal_ip_assets`
- `legal_claims`
- `legal_warranties`
- `legal_returns`
- `legal_litigation_cases`
- `legal_litigation_actions`
- `legal_evidence`
- `legal_compliance_obligations`
- `legal_controls`
- `legal_findings`
- `legal_action_plans`
- `legal_risks`
- `legal_licenses`
- `legal_governance_bodies`
- `legal_governance_meetings`
- `legal_governance_resolutions`
- `legal_audit_events`
- `legal_schema_migrations`

Todas las tablas deben incluir restricciones, índices, claves foráneas y campos de trazabilidad coherentes. Las fechas se almacenarán en formato ISO 8601. Los borrados de registros jurídicos deben ser lógicos salvo una política explícita y auditada.

## 6. Seguridad y auditoría

### RBAC mínimo

- `legal.view`
- `legal.create`
- `legal.update`
- `legal.delete`
- `legal.review`
- `legal.approve`
- `legal.sign`
- `legal.publish`
- `legal.export`
- `legal.audit.view`
- `legal.admin`
- permisos específicos por contratos, privacidad, litigios, cumplimiento, propiedad intelectual y gobierno corporativo.

### Contexto de auditoría

Cada evento sensible deberá guardar:

- usuario y rol efectivo;
- acción y recurso;
- entidad e identificador;
- fecha/hora;
- IP;
- navegador;
- dispositivo;
- sesión;
- correlación de solicitud;
- valores anteriores y posteriores;
- política de autorización aplicada;
- resultado;
- motivo o comentario;
- hash anterior y hash del evento.

## 7. Estrategia de migración

1. Inventariar tablas y registros Legal V2/V4 existentes.
2. Crear esquema nuevo en paralelo.
3. Incorporar tabla de correspondencias de IDs de legado.
4. Migrar catálogos y expedientes de forma idempotente.
5. Migrar metadatos documentales y verificar archivos/hash.
6. Validar conteos, relaciones, estados y registros huérfanos.
7. Ejecutar reconciliación automática y generar informe.
8. Mantener adaptadores de lectura para datos no migrados.
9. Activar la nueva navegación mediante feature flag.
10. Retirar el legado solo después de respaldo, aceptación y periodo de estabilización.

## 8. Fases de implementación

### Fase 0 — Baseline y protección

- Congelar inventario de arquitectura y esquema.
- Añadir pruebas de caracterización del comportamiento existente.
- Definir feature flag y estrategia de rollback.

### Fase 1 — Fundación técnica

- Crear estructura limpia de paquetes.
- Introducir entidades, errores, DTO, interfaces de repositorio y unidad de trabajo.
- Implementar migrador versionado.
- Centralizar contexto de seguridad y auditoría.

### Fase 2 — Núcleo jurídico y documentos

- Expedientes, partes, relaciones, comentarios, timeline y tareas.
- Repositorio documental, versiones, retención, legal hold y cadena de custodia.
- Descarga y exportación autorizadas y auditadas.

### Fase 3 — Contratos y privacidad

- Ciclo contractual completo.
- Aviso legal, términos, privacidad, cookies y consentimientos.
- Evidencia de publicación y aceptación.

### Fase 4 — Reclamos, litigios e IP

- Garantías, devoluciones y reclamos.
- Litigios, actuaciones, evidencias y calendario procesal.
- Propiedad intelectual y renovaciones.

### Fase 5 — Cumplimiento, riesgos y gobierno

- Obligaciones, controles, hallazgos y planes.
- Riesgos jurídicos y cumplimiento.
- Licencias, permisos y gobierno corporativo.

### Fase 6 — Automatización, reportes y producción

- Motor de reglas y alertas.
- Dashboard ejecutivo y reportes.
- Pruebas de integración, seguridad, migración y recuperación.
- Documentación operativa y técnica.

## 9. Criterios de aceptación

La reconstrucción no se considerará completa hasta cumplir todos estos criterios:

- No existe SQL ni lógica de autorización en la UI.
- Los agregados críticos tienen pruebas unitarias y de integración.
- Las migraciones se ejecutan dos veces sin duplicar ni corromper datos.
- La reconciliación de migración reporta cero pérdidas no justificadas.
- Toda acción sensible queda auditada con contexto completo.
- La descarga, exportación, firma y publicación exigen permisos explícitos.
- Los documentos firmados conservan integridad verificable.
- Los workflows rechazan transiciones inválidas.
- La segregación de funciones se aplica en dominio/aplicación.
- La navegación anterior puede desactivarse sin pérdida de acceso a datos.
- Se ejecutó un ensayo sobre una copia de la base real.
- Existe rollback documentado y probado.
- El módulo supera revisión jurídica por jurisdicción antes de publicar textos legales.

## 10. Riesgos inmediatos

- Duplicidad de ramas y PR jurídicos previos con alcances superpuestos.
- Divergencia entre documentación de arquitectura y código real.
- Coexistencia prolongada de V2/V4 que puede fragmentar datos.
- Falta de pruebas contra una copia de la base productiva.
- Almacenamiento local de documentos sin abstracción completa ni controles operativos.
- Posible falsa percepción de cumplimiento por disponer de pantallas sin controles jurídicos y técnicos completos.

## 11. Política de trabajo para este PR

- Rama: `codex/legal-v4-enterprise`.
- Base: `main`.
- PR siempre en estado Draft durante la reconstrucción.
- Commits pequeños y descriptivos.
- No fusionar hasta completar criterios de aceptación.
- Cada fase debe actualizar este documento, la matriz de trazabilidad y el informe de migración.
