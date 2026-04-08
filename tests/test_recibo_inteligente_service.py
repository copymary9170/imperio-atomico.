from services.recibo_inteligente_service import allocate_delivery, normalizar_texto_producto, parse_receipt_text


def test_normalizar_texto_producto_remueve_acentos_y_unidades():
    assert normalizar_texto_producto("Ázucar 1KG x2") == "azucar 1 2"


def test_parse_receipt_text_extrae_header_y_items():
    sample = """
    Comercial ABC C.A.
    Factura: A-12345
    07/04/2026
    Arroz Premium    2  3.50  7.00
    Azucar Morena    1  2.00  2.00
    Subtotal: 9.00
    Total: 9.00
    """
    header, items = parse_receipt_text(sample)
    assert header.proveedor == "Comercial ABC C.A."
    assert header.numero_factura == "A-12345"
    assert header.fecha == "2026-04-07"
    assert len(items) == 2
    assert items[0]["descripcion_detectada"].lower().startswith("arroz")


def test_allocate_delivery_proporcional_costo():
    import pandas as pd

    df = pd.DataFrame(
        [
            {"cantidad": 1, "precio_linea_detectado": 10, "delivery_manual_usd": 0},
            {"cantidad": 1, "precio_linea_detectado": 30, "delivery_manual_usd": 0},
        ]
    )
    out = allocate_delivery(df, delivery_usd=8, metodo="proporcional_costo")
    assert round(float(out.iloc[0]["delivery_asignado_usd"]), 2) == 2.00
    assert round(float(out.iloc[1]["delivery_asignado_usd"]), 2) == 6.00
