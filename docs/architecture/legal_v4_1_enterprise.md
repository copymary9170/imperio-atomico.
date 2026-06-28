# Legal V4.1 Enterprise Consolidation

## Objetivo

Legal V4.1 consolida la primera version de Legal V4 despues de fusionarla en `main`. Esta fase no reemplaza abruptamente la operacion existente: completa las piezas empresariales necesarias para que el modulo juridico pueda crecer sin depender del archivo legacy `views/legal_enterprise_core.py`.

## Alcance implementado

- Esquema `legal_v4` ampliado a documentos, firmas, comentarios, calendario, controles y riesgos.
- Migracion versionada `legal_v4_enterprise_operations`.
- Migracion idempotente de datos operativos desde Legal V2:
  - versiones;
  - archivos/documentos;
  - tareas;
  - calendario.
- Verificacion de integridad de la cadena de auditoria.
- Reporte ejecutivo reutilizable por UI y futuras exportaciones.
- Interfaz Legal V4.1 con pestanas de dashboard, expedientes, documentos, calendario, migracion, auditoria y arquitectura.

## Tablas nuevas o ampliadas

- `legal_v4_documents`
- `legal_v4_signatures`
- `legal_v4_comments`
- `legal_v4_calendar`
- `legal_v4_controls`
- `legal_v4_risk_assessments`
- `legal_v4_tasks.legacy_task_id`
- `legal_v4_versions.legacy_version_id`

## Reglas de compatibilidad

1. La migracion no elimina Legal V2.
2. Cada tabla migrada usa una columna `legacy_*` para evitar duplicados.
3. La UI conserva la entrada anterior de operacion juridica.
4. El esquema se crea de forma idempotente.
5. La auditoria registra la migracion operativa si hubo cambios.

## Riesgos pendientes

- Ejecutar pruebas reales en un checkout con dependencias instaladas.
- Probar la migracion contra una copia de `imperio.db` antes de usar datos productivos.
- Implementar almacenamiento documental externo si Streamlit Cloud no garantiza persistencia local.
- Definir proveedor real de firma digital si la empresa lo requiere legalmente.
- Completar formularios especificos por area juridica.

## Criterio para fusionar

Fusionar solo si el PR no entra en conflicto con `main`, la aplicacion arranca y la migracion se ejecuta sobre respaldo. Si no hay entorno local disponible, mantener como Draft hasta validacion manual.