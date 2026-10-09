"""URLs firmadas de vida corta para que el Worker (y el puente de WhatsApp) bajen un adjunto de Odoo.

Por qué no un enlace permanente: la foto o el PDF que una vendedora manda desde Odoo tiene que poder bajarse sin
sesión (el puente la pide desde internet), pero ese enlace no debe servir mañana ni a quien lo encuentre en un
registro. La firma amarra TRES cosas: el adjunto, la hora en que vence y el contenido (su checksum): si el archivo
cambia o pasa el tiempo, el enlace deja de valer. Funciones PURAS: la clave la pone quien llama
(``database.secret`` de Odoo, que no sale del servidor).

    /dcasa/adjunto/<id>/<vence>/<firma>/<nombre>

La ruta NO empieza por ``/dcasa/juan`` a propósito: ésa la bloquea el borde desde internet.
"""
import hashlib
import hmac
import re
import time
from urllib.parse import quote

VIDA_POR_DEFECTO = 15 * 60          # 15 minutos
VIDA_MAXIMA = 24 * 60 * 60          # ni con un ajuste raro dura más de un día
PREFIJO = '/dcasa/adjunto'
_FIRMA_VALIDA = re.compile(r'^[0-9a-f]{64}$')


def firma(secreto, adjunto_id, vence, checksum):
    """HMAC-SHA256 en hex de ``adjunto:vence:checksum`` con la clave del servidor."""
    mensaje = f'dcasa_adjunto:{int(adjunto_id)}:{int(vence)}:{checksum or ""}'.encode()
    return hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()


def ruta_firmada(secreto, adjunto_id, checksum, nombre, vida=VIDA_POR_DEFECTO, ahora=None):
    """Ruta (sin dominio) de un adjunto, firmada y con vencimiento."""
    vida = max(1, min(int(vida), VIDA_MAXIMA))
    vence = int((time.time() if ahora is None else ahora) + vida)
    archivo = quote((nombre or 'adjunto').replace('/', '_'), safe='') or 'adjunto'
    return f'{PREFIJO}/{int(adjunto_id)}/{vence}/{firma(secreto, adjunto_id, vence, checksum)}/{archivo}'


def es_valida(secreto, adjunto_id, vence, firma_recibida, checksum, ahora=None):
    """¿La firma es de este adjunto, con este contenido, y todavía no venció? (comparación en tiempo constante)"""
    ahora = time.time() if ahora is None else ahora
    if not isinstance(firma_recibida, str) or not _FIRMA_VALIDA.match(firma_recibida):
        return False
    if int(vence) < ahora or int(vence) - ahora > VIDA_MAXIMA + 60:
        return False
    return hmac.compare_digest(firma_recibida, firma(secreto, adjunto_id, vence, checksum))
