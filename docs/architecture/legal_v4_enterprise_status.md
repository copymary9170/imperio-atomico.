# Legal V4 Enterprise — Estado de implementación

## Estado del PR

Rama: `codex/legal-v4-enterprise`  
PR: Draft #30  
Base: `main`

## Implementado

- Plan de reconstrucción y auditoría de brechas.
- Paquete nuevo `legal/` separado de `legal_v4/`.
- Capas: dominio, aplicación, repositorios, seguridad, auditoría, infraestructura SQLite y UI.
- Entidades y políticas base para expedientes jurídicos.
- RBAC inicial con denegación por defecto.
- Auditoría sellada con SHA-256.
- Fachada de aplicación para que Streamlit no ejecute SQL directo.
- Repositorios SQLite para expedientes y auditoría.
- Unit of Work transaccional.
- Bootstrap de migraciones.
- Página Streamlit con feature flag: `IMPERIO_LEGAL_ENTERPRISE_UI=1`.

## Migraciones

- V100: núcleo común Enterprise.
- V101: dominios operativos.
- V102: importación idempotente desde `legal_v4_matters`.

## Tablas cubiertas

- Expedientes.
- Partes.
- Documentos.
- Comentarios.
- Timeline.
- Contratos.
- Obligaciones contractuales.
- Privacidad.
- Consentimientos.
- Litigios.
- Evidencias.
- Cumplimiento.
- Licencias.
- Riesgos.
- Gobierno corporativo.
- Tareas.
- Calendario.
- Auditoría.

## Pruebas agregadas

- Dominio jurídico.
- Segregación de funciones.
- Transiciones de estado.
- RBAC.
- Auditoría hash.
- Migraciones y bootstrap.

## Pendiente antes de fusionar

- Ejecutar pruebas en checkout real.
- Probar migración contra copia de `imperio.db`.
- Completar casos de uso específicos por dominio.
- Completar formularios operativos por dominio.
- Implementar descarga documental autorizada.
- Implementar firma digital real.

## Riesgo

Sigue siendo Draft. No debe fusionarse hasta validar pruebas, migración y seguridad.
