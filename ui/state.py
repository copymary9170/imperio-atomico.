from __future__ import annotations

import streamlit as st


class SessionStateService:
    """
    Servicio centralizado para manejar el estado de Streamlit.
    """

    @staticmethod
    def get_current_user(default: str = "Sistema") -> str:
        return str(st.session_state.get("usuario_nombre", default))

    @staticmethod
    def get(key: str, default=None):
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value) -> None:
        st.session_state[key] = value

    @staticmethod
    def exists(key: str) -> bool:
        return key in st.session_state

    @staticmethod
    def delete(key: str) -> None:
        if key in st.session_state:
            del st.session_state[key]

    @staticmethod
    def clear() -> None:
        """Limpia toda la sesión"""
        for k in list(st.session_state.keys()):
            del st.session_state[k]
