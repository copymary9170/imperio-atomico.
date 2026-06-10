# ⚛️ Imperio Atómico ERP

Sistema administrativo y operativo para **Copy Mary**: impresión, copias, papelería, sublimación, inventario, caja, ventas, producción, reportes y respaldos.

## Objetivo

Que todo el negocio esté conectado desde una sola app:

```text
Cotización → Venta → Caja → Inventario → Producción → Entrega → Reporte → Respaldo
```

## Módulos principales

- 🌅 **Día / Caja**: operación diaria, caja esperada, movimientos, ventas del día y alertas.
- 📊 **Panel de control**: alertas operativas, dashboard y panel ejecutivo.
- 📦 **Inventario / Almacén**: productos, stock mínimo, kardex, compras, proveedores y catálogo.
- 👥 **Clientes**: cartera, CRM, alertas comerciales y fidelización.
- 📇 **Contactos**: agenda unificada de clientes y proveedores.
- 📊 **Reportes**: caja y punto, histórico, administrativo y consolidados.
- 💾 **Respaldo**: respaldo local, respaldo externo en GitHub y restauración manual.
- 💰 **Ventas**: operaciones comerciales y punto de venta.
- 📝 **Cotizaciones**: presupuestos y seguimiento.
- 🏭 **Producción**: órdenes, diseños, CMYK, rutas, calidad, mermas y despacho.
- 💼 **Finanzas**: tesorería, gastos, CxP, contabilidad y planificación.
- 🧮 **Costeo y márgenes**: costeo simple, industrial, BOM y rentabilidad.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Secrets en Streamlit

En Streamlit Cloud:

```text
Manage app → Settings → Secrets
```

Ejemplo:

```toml
GITHUB_TOKEN = "tu_token_de_github"
GITHUB_REPO = "copymary9170/imperio-atomico."
BACKUP_PASSWORD = "tu_clave_privada_de_respaldo"
APP_SECRET_KEY = "copy_mary_erp_2026"
```

### Para qué sirve cada secret

- `GITHUB_TOKEN`: permite subir respaldos protegidos al repositorio.
- `GITHUB_REPO`: indica a qué repositorio se suben los respaldos.
- `BACKUP_PASSWORD`: protege los respaldos antes de subirlos.
- `APP_SECRET_KEY`: llave interna para futuras funciones de seguridad.

## Sistema de respaldo

El ERP tiene respaldo local y externo:

1. Crea copias locales de la base SQLite.
2. Protege el respaldo usando `BACKUP_PASSWORD`.
3. Lo sube a GitHub en la carpeta `backups/`.
4. Mantiene historial de respaldos locales.

Ruta esperada en GitHub:

```text
backups/YYYY/MM/imperio_atomico_auto_diario_YYYYMMDD_HHMMSS.protected.json
```

## Seguridad

No subir al repositorio:

- Bases `.db` sin proteger.
- `.streamlit/secrets.toml`.
- Archivos `.env`.
- Respaldos locales sin proteger.
- Credenciales, tokens o contraseñas.

## Documentación

- [Respaldos](docs/respaldo.md)
- [Secrets de Streamlit](docs/streamlit_secrets.md)
- [Módulos del ERP](docs/modulos.md)
- [Errores comunes](docs/errores_comunes.md)

## Próximas mejoras recomendadas

- Restaurar respaldos externos directamente desde GitHub.
- Cambiar protección básica por cifrado fuerte con `cryptography`.
- Conectar Supabase/PostgreSQL para persistencia real en nube.
- Crear configuración visual del sistema.
- Mejorar pruebas de conexión con GitHub y Secrets.
