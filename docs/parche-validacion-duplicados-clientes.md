# Parche pendiente: validación de duplicados en `modules/clientes.py`

Ya existe `modules/clientes_mejoras.py` con la función `validar_cliente_duplicado(nombre, telefono, cliente_id=None)`.

Para activar la validación dentro del registro y edición principal del maestro de clientes, aplicar estos cambios en `modules/clientes.py`:

## 1. Importar función

```python
from modules.clientes_mejoras import validar_cliente_duplicado
```

## 2. En registro, antes de `create_cliente(...)`

```python
alertas_dup = validar_cliente_duplicado(nombre, whatsapp)
if alertas_dup:
    st.error("Posible cliente duplicado:\n" + "\n".join(f"- {a}" for a in alertas_dup))
    return
```

Esto reemplaza o complementa la validación actual que solo revisa nombre.

## 3. En edición, antes del `UPDATE clientes`

```python
alertas_dup = validar_cliente_duplicado(nombre_n, whatsapp_n, int(cliente_id))
if alertas_dup:
    st.error("Posible cliente duplicado:\n" + "\n".join(f"- {a}" for a in alertas_dup))
    return
```

## Razón empresarial
La validación solo por nombre no es suficiente. En un negocio real puede haber muchas personas con el mismo nombre, y una misma persona puede registrarse con nombres escritos distinto. El teléfono/WhatsApp es el dato más fuerte para evitar duplicados.
