# Sistema de respaldo

El respaldo de Imperio Atómico ERP debe proteger la información administrativa de Copy Mary sin guardar archivos privados de clientes dentro del repositorio.

## Qué se respalda

Se respalda la información necesaria para operar el negocio:

- Inventario.
- Ventas.
- Caja.
- Clientes.
- Cotizaciones.
- Producción.
- Costos y márgenes.
- Configuración del sistema.
- Reportes administrativos.

## Qué no se respalda dentro del ERP

No se deben incluir por defecto:

- PDFs de clientes.
- Fotos personales.
- Cédulas o documentos legales de clientes.
- Archivos de impresión de uso único.
- Diseños pesados.
- Archivos recibidos por WhatsApp que no necesitan conservarse.

Si un archivo debe conservarse por solicitud del cliente o por uso futuro, debe guardarse externamente y solo registrar una nota dentro del ERP.

Ejemplo:

```text
Archivo guardado externamente por solicitud del cliente.
```

## Respaldo local

El sistema puede crear copias locales de la base de datos administrativa.

Estas copias no deben subirse al repositorio sin protección.

## Respaldo externo en GitHub

Los respaldos externos deben subirse protegidos en la carpeta:

```text
backups/YYYY/MM/
```

Formato recomendado:

```text
imperio_atomico_auto_diario_YYYYMMDD_HHMMSS.protected.json
```

## Archivos sensibles prohibidos

Nunca subir al repositorio:

- `.streamlit/secrets.toml`
- `.env`
- Bases `.db`, `.sqlite` o `.sqlite3`
- Respaldos sin protección
- Tokens
- Contraseñas
- Archivos privados de clientes

## Restauración

La restauración debe hacerse con cuidado:

1. Crear un respaldo del estado actual antes de restaurar.
2. Seleccionar el respaldo protegido.
3. Verificar la contraseña de respaldo.
4. Restaurar la base administrativa.
5. Revisar inventario, caja, ventas y clientes después de restaurar.

## Mejora futura recomendada

Cambiar la protección básica por cifrado fuerte usando `cryptography` antes de manejar respaldos externos importantes.
