from modules.cmyk import render_cmyk as render_cmyk_modulo


def render_cmyk(usuario: str) -> None:
    """Vista CMYK principal (wrapper explícito para evitar rutas ambiguas)."""
    render_cmyk_modulo(usuario)
