"""Íconos de la pantalla de inicio y favicon, hechos del logo de la marca: python scripts/iconos_de_la_marca.py

Pedido de la dueña (2026-10-22): «el ícono que se crea cuando se guarda la página o panel administrativo en los
celulares en pantallas de inicio debe ser estrictamente el logo». Todos salen de
``addons/dcasa_base/static/img/logo.png`` (el de la empresa, el sitio y los correos), tal cual: centrado, entero (sin
recortar) y del mismo tamaño en proporción.

* ``logo-192.png`` y ``logo-512.png``: solo el logo, con fondo transparente (manifiesto «any», favicon).
* ``logo-maskable-192.png`` y ``logo-maskable-512.png``: sobre blanco y dentro de la zona segura (el círculo del 80 %),
  para que Android lo recorte en círculo o en gota sin cortarle nada.
* ``apple-touch-icon.png`` (180 × 180): sobre blanco, sin transparencia (el iPhone pinta de negro lo transparente) y
  con margen para las esquinas redondas del iPhone.
* ``addons/website_dcasa/static/src/img/favicon.png``: el mismo de 512 transparente, del que Odoo saca el favicon del
  sitio.

Si cambia el logo, se vuelve a correr y se suben las imágenes nuevas.
"""
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
LOGO = RAIZ / 'addons/dcasa_base/static/img/logo.png'
CARPETA = RAIZ / 'addons/dcasa_base/static/img/icono'
FAVICON_DEL_SITIO = RAIZ / 'addons/website_dcasa/static/src/img/favicon.png'
BLANCO = (255, 255, 255, 255)

# (archivo, lado en píxeles, ancho del logo sobre el lado, fondo o None si es transparente)
ICONOS = (
    ('logo-192.png', 192, 0.94, None),
    ('logo-512.png', 512, 0.94, None),
    # Zona segura de un ícono «maskable»: un círculo de radio 40 %. El logo mide 892 × 405, así que su esquina queda a
    # 0,55 × su ancho del centro: con 0,72 del lado cae dentro del círculo.
    ('logo-maskable-192.png', 192, 0.72, BLANCO),
    ('logo-maskable-512.png', 512, 0.72, BLANCO),
    ('apple-touch-icon.png', 180, 0.86, BLANCO),
)


def componer(logo, lado, ancho_relativo, fondo):
    """El logo, entero y centrado, en un cuadrado de ``lado`` píxeles."""
    ancho = round(lado * ancho_relativo)
    alto = round(ancho * logo.height / logo.width)
    reducido = logo.resize((ancho, alto), Image.LANCZOS)
    lienzo = Image.new('RGBA', (lado, lado), fondo or (0, 0, 0, 0))
    lienzo.alpha_composite(reducido, ((lado - ancho) // 2, (lado - alto) // 2))
    return lienzo.convert('RGB') if fondo else lienzo


def main():
    logo = Image.open(LOGO).convert('RGBA')
    CARPETA.mkdir(exist_ok=True)
    for archivo, lado, ancho, fondo in ICONOS:
        componer(logo, lado, ancho, fondo).save(CARPETA / archivo, optimize=True)
        print(f'{CARPETA.relative_to(RAIZ) / archivo}')
    componer(logo, 512, 0.94, None).save(FAVICON_DEL_SITIO, optimize=True)
    print(FAVICON_DEL_SITIO.relative_to(RAIZ))


if __name__ == '__main__':
    main()
