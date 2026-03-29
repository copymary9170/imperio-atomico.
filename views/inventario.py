import streamlit as st
from modules.inventario import render_inventario as inventario_module


def render_inventario(usuario: str) -> None:
    inventario_module(usuario)
