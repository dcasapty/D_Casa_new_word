"""Lo que ayuda al chofer a dar con la casa y con quien recibe (el dueño, 2026-11-25: «el dolor número uno son los
pedidos devueltos»), en puro Python (sin base de datos):

* **Quién recibe** (si no es el cliente) y un **teléfono de respaldo** de Panamá, por si no contesta.
* **«Avisar que llegué»**: el número de WhatsApp del celular del cliente.
* **La foto de la fachada**: se abre con PIL, se endereza, se le quitan TODOS sus datos ocultos (EXIF, XMP, perfiles:
  la foto de un teléfono lleva el GPS de donde se tomó) y se guarda como un JPEG nuevo de hasta ``LADO_FOTO`` px.

Los celulares se leen con las reglas que ya usa el sistema: ``dcasa_socios`` (``bien_escrito``: celular y fijo de
Panamá, como en la ficha) y ``dcasa_conversaciones`` (``celulares.interpretar``: el número de WhatsApp de un cliente).
"""
import io

from PIL import Image, ImageOps

from odoo.addons.dcasa_base import whatsapp
from odoo.addons.dcasa_conversaciones.models import celulares
from odoo.addons.dcasa_socios.models import bien_escrito
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.exceptions import UserError
from odoo.tools.image import IMAGE_MAX_RESOLUTION

from .geo import texto_corto

MAX_RECIBE = 60                     # «Rosa, mi mamá» cabe; un párrafo no
MAX_TELEFONO = 30                   # lo que se acepta escrito («+507 6123-4567» con espacios de más)
MAX_FOTO_BYTES = 8 * 1024 * 1024    # lo que llega (la página la achica antes: casi siempre llega con menos de 1 MB)
LADO_FOTO = 1280                    # el lado mayor de la foto que se guarda
# Lo que se llega a decodificar (después del achique de JPEG). Un PNG de 50 MP en ceros pesa 190 KB y abierto ocupa
# cientos de MB: tumbaba Odoo (auditoría 1). Una foto de teléfono (12 MP) ya llega achicada por la página.
MAX_PIXELES_FOTO = 12_600_000
CALIDAD_FOTO = 82
FORMATOS_FOTO = ('JPEG', 'MPO', 'PNG', 'WEBP', 'HEIF', 'HEIC')   # MPO: el JPEG de varias fotos de algunos teléfonos

MENSAJE_TELEFONO = 'Ese teléfono no parece de Panamá. Escríbelo así: 6123-4567.'
MENSAJES_FOTO = {
    'vacia': 'No nos llegó la foto. Tómala otra vez 📷',
    'pesada': 'La foto pesa mucho. Tómala otra vez 📷',
    'formato': 'No pudimos abrir esa foto. Tómala otra vez 📷',
    'muchas': 'Ya recibimos varias fotos de tu casa hoy. Si quieres cambiarla, escríbenos 💬',
}
MAX_FOTOS_POR_DIA = 10      # por ficha: cambiar de foto unas veces sí; llenar R2 acuñando enlaces nuevos, no


class TelefonoInvalido(UserError):
    """El teléfono de respaldo no es un celular ni un fijo de Panamá."""


class FotoInvalida(UserError):
    """La foto no sirve. ``motivo``: ``vacia``, ``pesada`` (o demasiados píxeles) o ``formato`` (no es una imagen que
    se pueda abrir)."""

    def __init__(self, motivo):
        super().__init__(MENSAJES_FOTO.get(motivo, MENSAJES_FOTO['formato']))
        self.motivo = motivo


# ---------------------------------------------------------------------------
# Quién recibe y el teléfono de respaldo
# ---------------------------------------------------------------------------

def recibe_limpio(texto):
    """El nombre de quien recibe, en una línea y de a lo sumo ``MAX_RECIBE`` letras (o ``''``)."""
    return texto_corto(texto, MAX_RECIBE)


def telefono_de_respaldo(texto):
    """El teléfono de respaldo si es de Panamá, o ``None``:

    * un celular: ``{'guardar': '+507 6123-4567', 'tel': '+50761234567', 'wa': '50761234567', 'nacional': '61234567'}``;
    * un fijo: ``{'guardar': '+507 234-5678', 'tel': '+5072345678', 'wa': '', 'nacional': '2345678'}`` (un fijo no
      tiene WhatsApp).

    Uno de otro país, dos números juntos, letras o un número corto: ``None`` (el chofer llama desde Panamá)."""
    texto = texto_corto(texto, MAX_TELEFONO)
    if not texto:
        return None
    for guardar, es_celular in ((bien_escrito.telefono_para_guardar(texto), True),
                                (bien_escrito.fijo_para_guardar(texto), False)):
        if guardar and guardar.startswith(f'+{bien_escrito.PANAMA} '):
            nacional = R.solo_digitos(guardar)[len(bien_escrito.PANAMA):]
            return {'guardar': guardar, 'tel': f'+{bien_escrito.PANAMA}{nacional}',
                    'wa': f'{bien_escrito.PANAMA}{nacional}' if es_celular else '', 'nacional': nacional}
    return None


def mismo_telefono(uno, otro):
    """¿Es el mismo número? (Para no mostrarle al chofer el respaldo si es el mismo celular del cliente.)"""
    a = telefono_de_respaldo(uno)
    b = telefono_de_respaldo(otro)
    return bool(a and b) and a['nacional'] == b['nacional']


def numero_whatsapp(telefono):
    """El número de WhatsApp de un celular (Panamá con su 507; otro país, completo) o ``''`` (un fijo, letras…). Es
    la misma lectura con que Juan reconoce el celular de un cliente (``celulares.interpretar``)."""
    tipo, valor = celulares.interpretar(telefono or '')
    if tipo == 'pa':
        return celulares.PREFIJO_PANAMA + valor
    return valor if tipo == 'intl' else ''


def enlace_whatsapp(numero, texto):
    """``https://api.whatsapp.com/send?phone=<número>&text=<mensaje>`` (el mensaje listo para mandar) o ``''`` sin
    número. No ``wa.me``: cambia los emojis por «�» en WhatsApp Web (dcasa_base/whatsapp.py)."""
    return whatsapp.enlace(numero, texto) if numero else ''


def tel(telefono):
    """Lo que va en ``tel:`` (dígitos y el «+»), o ``''``."""
    return ''.join(c for c in (telefono or '') if c.isdigit() or c == '+')


# ---------------------------------------------------------------------------
# La foto de la fachada
# ---------------------------------------------------------------------------

def procesar_foto(datos):
    """Los bytes de un JPEG limpio (enderezado, sin EXIF ni ningún dato oculto, de hasta ``LADO_FOTO`` px de lado) a
    partir de la foto que mandó el cliente, o ``FotoInvalida``.

    Se acepta lo que PIL abra de verdad como JPEG, PNG, WebP (o HEIC, si el servidor tiene con qué abrirlo); el nombre
    y el tipo que diga el navegador no cuentan. La imagen que se guarda es NUEVA (se pinta sobre un lienzo blanco): no
    hereda nada del archivo original, ni el GPS del EXIF, ni el XMP, ni comentarios."""
    if not isinstance(datos, (bytes, bytearray)) or not datos:
        raise FotoInvalida('vacia')
    if len(datos) > MAX_FOTO_BYTES:
        raise FotoInvalida('pesada')
    try:
        with Image.open(io.BytesIO(bytes(datos))) as original:
            if (original.format or '').upper() not in FORMATOS_FOTO:
                raise FotoInvalida('formato')
            if original.width * original.height > IMAGE_MAX_RESOLUTION:
                raise FotoInvalida('pesada')
            if original.format in ('JPEG', 'MPO'):
                # Un JPEG de 12 MP se decodifica ya achicado (1/2, 1/4…), sin bajar del tamaño que se guarda.
                original.draft('RGB', (LADO_FOTO, LADO_FOTO))
            if original.width * original.height > MAX_PIXELES_FOTO:
                raise FotoInvalida('pesada')      # antes de decodificar nada
            # Primero se achica (en su lugar) y después se endereza: enderezar la grande la copiaba entera.
            original.thumbnail((LADO_FOTO, LADO_FOTO), Image.Resampling.LANCZOS)
            derecha = ImageOps.exif_transpose(original)
            con_alfa = derecha.convert('RGBA')
    except FotoInvalida:
        raise
    except (OSError, ValueError, SyntaxError, TypeError, EOFError, MemoryError, Image.DecompressionBombError):
        raise FotoInvalida('formato') from None
    limpia = Image.new('RGB', con_alfa.size, (255, 255, 255))
    limpia.paste(con_alfa, mask=con_alfa.getchannel('A'))
    salida = io.BytesIO()
    limpia.save(salida, 'JPEG', quality=CALIDAD_FOTO, optimize=True, progressive=True)
    return salida.getvalue()
