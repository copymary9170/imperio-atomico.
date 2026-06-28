# Legal V4 Enterprise — Arquitectura objetivo

## Estado

Aprobada para implementación incremental en la rama `legal-v4-enterprise`.

## Diagnóstico de la implementación anterior

La versión anterior mezcla en archivos de interfaz Streamlit:

- definición y migración de tablas;
- reglas de dominio y workflows;
- acceso SQL;
- almacenamiento documental;
- auditoría;
- autorización;
- validación;
- presentación y reportes.

Este acoplamiento dificulta pruebas, migraciones seguras, reutilización, control transaccional y evolución del modelo.

## Arquitectura adoptada

```text
legal/
├── domain/          # Entidades, value objects, estados, políticas y errores
├── application/     # Casos de uso, comandos, consultas y DTO
├── infrastructure/  # SQLite, almacenamiento, hashing, firma y adaptadores
├── repositories/    # Contratos y repositorios concretos
├── services/        # Servicios de dominio y aplicación
├── security/        # RBAC, clasificación, segregación y contexto de sesión
├── audit/           # Eventos, integridad y trazabilidad
├── automation/      # Alertas, vencimientos, tareas y reglas
├── reports/         # Consultas y exportaciones
├── validators/      # Validadores reutilizables
├── ui/              # Vistas Streamlit sin SQL ni reglas de negocio
├── migrations/      # Migraciones versionadas, idempotentes y reversibles
└── legacy/          # Adaptadores temporales para Legal V2
```

## Principios obligatorios

1. La UI no ejecuta SQL ni crea tablas.
2. Toda escritura pasa por un caso de uso y una transacción.
3. Toda mutación genera un evento de auditoría inmutable.
4. Los documentos se identifican por UUID y hash SHA-256.
5. La autorización se verifica en aplicación y no solo en la interfaz.
6. Los estados se modifican únicamente mediante transiciones explícitas.
7. Los registros aprobados o firmados no se sobrescriben: generan una versión nueva.
8. La segregación creador–revisor–aprobador es una política de dominio.
9. La migración conserva datos existentes y registra su procedencia.
10. SQLite debe operar con claves foráneas, WAL, índices y restricciones.

## Agregados principales

- `LegalMatter`: expediente jurídico maestro.
- `LegalDocument`: documento controlado y sus versiones.
- `Contract`: ciclo contractual, contrapartes, obligaciones y renovaciones.
- `ClaimCase`: reclamos, garantías, devoluciones y controversias.
- `LitigationCase`: demandas, litigios, actuaciones y evidencias.
- `ComplianceObligation`: obligación normativa, control, evidencia y evaluación.
- `LegalRisk`: riesgo, impacto, probabilidad, tratamiento y aceptación.
- `ConsentRecord`: consentimiento, finalidad, base jurídica y revocación.
- `CorporateGovernanceRecord`: actas, resoluciones, poderes y órganos societarios.
- `LegalCalendarEvent`: vencimientos, audiencias, renovaciones y alertas.

## Estrategia de migración

1. Crear esquema V4 en paralelo con prefijo `legal_v4_`.
2. Registrar versión del esquema en `legal_schema_migrations`.
3. Importar datos de tablas `legal_enterprise_*` de forma idempotente.
4. Mantener Legal V2 como lectura temporal mediante adaptadores.
5. Cambiar navegación a V4 solo después de pruebas de integridad.
6. Marcar la implementación anterior como `legacy` sin eliminarla inicialmente.
7. Retirar tablas y código anterior únicamente después de respaldo y aceptación.

## Controles de producción

- RBAC granular y denegación por defecto.
- clasificación pública, interna, confidencial y restringida;
- legal hold y retención documental;
- hash encadenado de auditoría;
- control de duplicados por hash;
- metadatos de IP, dispositivo, navegador y sesión;
- límites de archivo y lista permitida de formatos;
- firma desacoplada mediante proveedor;
- exportaciones autorizadas y auditadas;
- pruebas unitarias de dominio, integración de repositorios y smoke tests de UI.

## Criterio de finalización

Legal V4 se considerará listo para producción cuando las migraciones sean repetibles, los casos de uso críticos tengan pruebas, no exista SQL en UI, las acciones sensibles estén auditadas y se haya ejecutado una migración de ensayo sobre una copia del ERP.