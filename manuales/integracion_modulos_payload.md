# Contrato estándar de payload entre módulos

Este ERP ahora incluye una capa de interoperabilidad no invasiva en `modules/integration_hub.py`.

## Estructura base

Cada envío entre módulos usa este contrato:

```python
{
    "source_module": str,
    "source_action": str,
    "record_id": str | None,
    "referencia": str,
    "timestamp": str,  # ISO-8601
    "usuario": str,
    "payload_data": dict,
}
```

## Bandeja de entrada estándar

- Clave raíz: `st.session_state["module_inbox"]`
- Por módulo destino: `st.session_state["module_inbox"][target_module]`
- Registro de trazabilidad: `st.session_state["module_dispatch_log"]`

## Reglas

1. No reemplaza flujos actuales; solo agrega interoperabilidad.
2. No autoejecuta procesos críticos en destino.
3. El destino muestra la bandeja y ofrece:
   - **Usar datos recibidos**
   - **Limpiar datos recibidos**
4. `payload_data` es flexible y específico por módulo.
