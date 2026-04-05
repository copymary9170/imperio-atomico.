from __future__ import annotations

import streamlit as st

from modules.integration_hub import render_module_inbox
from modules.operacion_industrial import render_operacion_industrial


def render_mantenimiento_activos(usuario: str) -> None:
    def _apply_inbox(inbox: dict) -> None:
        st.session_state["mantenimiento_prefill"] = dict(inbox.get("payload_data", {}))

    render_module_inbox("mantenimiento", apply_callback=_apply_inbox, clear_after_apply=False)
    render_operacion_industrial(usuario)
