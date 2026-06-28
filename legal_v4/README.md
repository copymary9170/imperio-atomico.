# Legal V4 Enterprise

## Capas

- `domain.py`: comandos y validaciones de dominio.
- `schema.py`: migraciones SQLite idempotentes.
- `service.py`: casos de uso y migracion legacy.
- `reports.py`: reportes ejecutivos y consultas agregadas.
- `ui.py`: interfaz Streamlit sin SQL directo.

## Flujo de uso

1. Entrar al Departamento Juridico.
2. Seleccionar `Legal V4 Enterprise`.
3. Crear expedientes nuevos o ejecutar migracion desde Legal V2.
4. Revisar dashboard, documentos, calendario y auditoria.
5. Verificar la cadena de auditoria despues de operaciones sensibles.

## Migracion recomendada

1. Respaldar `data/imperio.db`.
2. Ejecutar `Migrar expedientes`.
3. Ejecutar `Migrar operaciones V2`.
4. Verificar conteos importados.
5. Verificar auditoria.
6. Revisar documentos y calendario.

## Produccion

No eliminar las tablas Legal V2 hasta confirmar que todos los registros fueron importados y que la operacion juridica diaria funciona correctamente desde Legal V4.