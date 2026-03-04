from __future__ import annotations

import streamlit as st


class SessionStateService:
    @staticmethod
    def get_current_user(default: str = "Sistema") -> str:
        return str(st.session_state.get("usuario_nombre", default))

    @staticmethod
    def get(key: str, default=None):
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value) -> None:
        st.session_state[key] = value
