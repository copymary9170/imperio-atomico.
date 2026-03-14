from PIL import Image


# ==========================================================
# CONFIGURACIÓN GLOBAL
# ==========================================================

MAX_IMAGE_SIZE = 1500  # tamaño máximo de análisis en px


# ==========================================================
# OPTIMIZAR IMAGEN PARA ANÁLISIS
# ==========================================================

def optimize_image(img_obj: Image.Image, max_size: int = MAX_IMAGE_SIZE) -> Image.Image:
    """
    Reduce el tamaño de una imagen si es demasiado grande.

    Esto evita:
    - alto consumo de RAM
    - análisis lento con numpy
    - bloqueos en PDFs grandes

    Parámetros
    ----------
    img_obj : PIL.Image
        Imagen a optimizar.

    max_size : int
        Tamaño máximo permitido por lado.

    Retorna
    -------
    PIL.Image
        Imagen optimizada.
    """

    if img_obj.width > max_size or img_obj.height > max_size:

        # copiar para no modificar la original
        img_obj = img_obj.copy()

        # reducir manteniendo proporción
        img_obj.thumbnail((max_size, max_size), Image.LANCZOS)

    return img_obj
