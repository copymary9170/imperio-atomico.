from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import streamlit as st


INBOX_KEY = "module_inbox"
DISPATCH_LOG_KEY = "module_dispatch_log"


def build_standard_payload(
    source_module: str,
    source_action: str,
    payload_data: dict[str, Any],
    record_id: str | int | None = None,
    referencia: str | None = None,
    usuario: str | None = None,
) -> dict[str, Any]:
    """Contrato estándar de payload entre módulos."""
    return {
        "source_module": str(source_module),
        "source_action": str(source_action),
        "record_id": str(record_id) if record_id is not None else None,
        "referencia": str(referencia or ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "usuario": str(usuario or st.session_state.get("usuario", "")),
        "payload_data": dict(payload_data or {}),
    }


def _ensure_integration_state() -> None:
    if INBOX_KEY not in st.session_state or not isinstance(st.session_state.get(INBOX_KEY), dict):
        st.session_state[INBOX_KEY] = {}
    if DISPATCH_LOG_KEY not in st.session_state or not isinstance(st.session_state.get(DISPATCH_LOG_KEY), list):
        st.session_state[DISPATCH_LOG_KEY] = []


def dispatch_to_module(
    source_module: str,
    target_module: str,
    payload: dict[str, Any],
    success_message: str | None = None,
    session_key: str | None = None,
) -> None:
    """Guarda un payload en la bandeja del módulo destino sin alterar flujos existentes."""
    _ensure_integration_state()

    normalized_target = str(target_module).strip().lower()
    st.session_state[INBOX_KEY][normalized_target] = payload

    if session_key:
        st.session_state[session_key] = payload.get("payload_data", {})

    st.session_state[DISPATCH_LOG_KEY].append(
        {
            "source_module": str(source_module),
            "target_module": normalized_target,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "record_id": payload.get("record_id"),
            "referencia": payload.get("referencia"),
        }
    )

    if success_message:
        st.success(success_message)


def get_module_inbox(target_module: str) -> dict[str, Any] | None:
    _ensure_integration_state()
    return st.session_state[INBOX_KEY].get(str(target_module).strip().lower())


def clear_module_inbox(target_module: str) -> None:
    _ensure_integration_state()
    st.session_state[INBOX_KEY].pop(str(target_module).strip().lower(), None)


def render_send_buttons(
    source_module: str,
    payload_builders: dict[str, Callable[[], tuple[str, dict[str, Any]] | None]],
    layout: str = "horizontal",
) -> None:
    """Renderiza botones reutilizables 'Enviar a ...'."""
    if not payload_builders:
        return

    targets = list(payload_builders.keys())
    if layout == "vertical":
        containers = [st.container() for _ in targets]
    else:
        containers = st.columns(len(targets))

    for container, target in zip(containers, targets):
        with container:
            label = f"📤 Enviar a {target}"
            if st.button(label, key=f"dispatch::{source_module}::{target}", use_container_width=True):
                built = payload_builders[target]()
                if not built:
                    continue
                source_action, payload_data = built
                payload = build_standard_payload(
                    source_module=source_module,
                    source_action=source_action,
                    payload_data=payload_data,
                    record_id=payload_data.get("record_id") or payload_data.get("id"),
                    referencia=payload_data.get("referencia"),
                    usuario=payload_data.get("usuario"),
                )
                dispatch_to_module(
                    source_module=source_module,
                    target_module=target,
                    payload=payload,
                    success_message=f"Datos enviados a {target}.",
                )


def render_module_inbox(
    target_module: str,
    apply_callback: Callable[[dict[str, Any]], None] | None = None,
    clear_after_apply: bool = False,
) -> dict[str, Any] | None:
    """Muestra bandeja de entrada estándar en el módulo destino."""
    inbox = get_module_inbox(target_module)
    if not inbox:
        return None

    source = inbox.get("source_module", "origen")
    reference = inbox.get("referencia") or "sin referencia"
    st.info(f"Datos recibidos desde {source} · Referencia: {reference}")
    st.caption(f"Acción: {inbox.get('source_action', 'N/D')} · Fecha: {inbox.get('timestamp', 'N/D')}")
    st.json(inbox.get("payload_data", {}))

    c1, c2 = st.columns(2)
    if c1.button("Usar datos recibidos", key=f"inbox_apply::{target_module}", use_container_width=True):
        if apply_callback:
            apply_callback(inbox)
        st.success("Datos aplicados al módulo.")
        if clear_after_apply:
            clear_module_inbox(target_module)
        st.rerun()

    if c2.button("Limpiar datos recibidos", key=f"inbox_clear::{target_module}", use_container_width=True):
        clear_module_inbox(target_module)
        st.rerun()

    return inbox
