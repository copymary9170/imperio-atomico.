from __future__ import annotations

# Python importa este archivo automaticamente cuando la raiz del proyecto esta en sys.path.
# Lo usamos como puente seguro para que el nucleo transaccional exista aunque app.py
# no haya sido actualizado directamente.


def _bootstrap_transactional_core() -> None:
    try:
        from database.transactional_core import ensure_transactional_core_schema

        ensure_transactional_core_schema()
    except Exception:
        # Nunca debe impedir que Streamlit arranque. Los errores de migracion se
        # revisan desde el propio sistema o ejecutando la funcion manualmente.
        pass


_bootstrap_transactional_core()
