# Legal V4.1 Enterprise — Consolidacion

## Objetivo

La version 4.1 consolida la base fusionada de Legal V4 y agrega capacidades empresariales que faltaban para operar el departamento juridico como un modulo ERP real.

## Capacidades agregadas

- Repositorio documental juridico con hash SHA-256.
- Control de duplicados por expediente y hash.
- Soporte para documentos firmados, proveedor y referencia de firma.
- Legal hold por documento firmado.
- Eventos de workflow normalizados.
- Politicas de transicion de estados fuera de la UI.
- Obligaciones juridicas y de cumplimiento.
- Panel de auditoria con hashes encadenados.
- Dashboard ampliado con documentos y obligaciones.
- Interfaz Streamlit con tabs funcionales para expediente, workflow, documentos, obligaciones, auditoria y migracion.

## Tablas agregadas

- `legal_v4_documents`
- `legal_v4_workflow_events`
- `legal_v4_obligations`

## Migracion

La migracion se mantiene idempotente. `legal_schema_migrations` registra:

- `1 legal_v4_initial`
- `2 legal_v4_documents_workflows`

## Controles de seguridad

- Los documentos se hashean antes de persistir metadatos.
- Los duplicados activos se bloquean por `matter_id + sha256 + active`.
- Los expedientes cerrados o archivados no aceptan documentos firmados nuevos.
- Las transiciones requieren aprobador cuando pasan a estados aprobados, firmados o vigentes.
- Cierre y archivo requieren comentario.
- Toda mutacion pasa por `LegalService` y genera auditoria.

## Pendientes posteriores

- Firma digital real con proveedor externo.
- Descarga controlada de archivos con permisos y auditoria.
- Migracion documental desde `legal_enterprise_files`.
- Pruebas de integracion contra una copia de `imperio.db`.
- Revision juridica de textos por jurisdiccion.
