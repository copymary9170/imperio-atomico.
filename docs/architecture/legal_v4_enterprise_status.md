# Legal V4 Enterprise — Estado de implementación

## Estado del PR

Rama: `codex/legal-v4-enterprise`  
PR: Draft #30  
Base: `main`

## Implementado

### Arquitectura y planificación

- Auditoría de brechas de Legal V4/V4.1.
- Plan de reconstrucción empresarial.
- Criterios de aceptación antes de producción.
- Estrategia de migración paralela sin romper tablas `legal_v4_*`.

### Capas nuevas

- `legal/domain`: entidades, estados, errores y workflow.
- `legal/application`: comandos, casos de uso y bootstrap.
- `legal/repositories`: contratos de persistencia.
- `legal/security`: contexto de seguridad y RBAC inicial.
- `legal/audit`: evento auditado sellado con SHA-256.
- `legal/infrastructure/sqlite`: esquema, repositorios y Unit of Work.

### Datos y migración

Se agregó esquema paralelo `legal_*` con tablas para:

- expedientes jurídicos;
- partes y contrapartes;
- relación expediente-parte;
- documentos;
- comentarios;
- timeline;
- contratos;
- privacidad;
- consentimientos;
- litigios;
- evidencias;
- cumplimiento;
- riesgos;
- gobierno corporativo;
- auditoría inmutable;
- control de migraciones.

### Pruebas agregadas

- Pruebas de dominio jurídico.
- Pruebas de segregación de funciones.
- Pruebas de transición de estados.
- Pruebas de RBAC básico.
- Pruebas de auditoría sellada con hash.

## Pendiente

- Ejecutar suite en un checkout real.
- Corregir cualquier fallo de importación detectado por CI.
- Completar conexión UI/navegación bajo feature flag.
- Agregar migración de datos desde `legal_v4_*` hacia `legal_*`.
- Agregar repositorios y casos de uso específicos para contratos, privacidad, litigios, cumplimiento, riesgos y gobierno.
- Implementar descarga documental autorizada y auditada.
- Implementar firma digital real mediante proveedor externo.
- Ensayar migración sobre una copia de `imperio.db`.

## Riesgos abiertos

- El PR todavía es una base de reconstrucción, no un módulo productivo completo.
- No debe fusionarse hasta ejecutar pruebas y migración de ensayo.
- La coexistencia temporal de `legal_v4_*` y `legal_*` requiere feature flag y documentación de transición.
