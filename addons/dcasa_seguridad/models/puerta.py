"""La puerta del equipo, vista desde Odoo (edge/src/puerta.ts, docs/SEGURIDAD_ACCESO.md §8).

El personal entra al panel por tres pasos: el PIN al correo (Cloudflare Access, en el borde), la clave y el
código de la app. El borde verifica el primer paso y le pasa a Odoo, en cada petición, la cabecera
``X-Dcasa-Puerta: <correo>|<vence>|<firma>`` firmada con ``DCASA_PUERTA_SECRETO`` (el mismo secreto que tiene el
Worker; solo vive en el entorno, nunca en la base). Aquí se verifica esa firma y se decide:

* ``DCASA_PUERTA_OBLIGATORIA`` = ``0`` (por defecto): no se exige nada.
* ``avisar``: quien entra sin puerta entra, pero queda en «Accesos al panel» y se avisa por Telegram. Sirve para
  comprobar, antes de cerrar, que todo el equipo ya está pasando por la puerta.
* ``1``: el personal (usuarios internos) solo inicia sesión y solo sigue dentro con la puerta abierta. Los clientes
  del portal y los socios nunca pasan por aquí.

Sin secreto de al menos 32 caracteres no se puede verificar nada: el modo se queda en ``0`` (y el arranque lo
avisa), para que un error de copiar y pegar no deje a todo el personal fuera. Rescate si la puerta no abre:
``DCASA_PUERTA_OBLIGATORIA=0`` y desplegar (docs/SEGURIDAD_ACCESO.md §4).

``DCASA_PUERTA_EXIGIR_CORREO=1``: además, el correo con el que se pasó la puerta tiene que ser el correo (o el
usuario) de la cuenta de Odoo: así la lista de Access y la de Odoo quedan amarradas.
"""
import hmac
import os
import re
import time
from hashlib import sha256

CABECERA = 'X-Dcasa-Puerta'

APAGADA = '0'
AVISAR = 'avisar'
OBLIGATORIA = '1'
MODOS = (APAGADA, AVISAR, OBLIGATORIA)

# Resultados que se anotan en «Accesos al panel»
SIN_PUERTA = 'sin_puerta'
CORREO_DISTINTO = 'puerta_correo'

LARGO_MINIMO_SECRETO = 32
_CORREO = re.compile(r'^[^\s@|\x00-\x1f]{1,64}@[^\s@|\x00-\x1f]{1,190}$')
_FIRMA = re.compile(r'^[0-9a-f]{64}$')


def _entorno(nombre):
    return (os.environ.get(nombre) or '').strip()


def secreto():
    return _entorno('DCASA_PUERTA_SECRETO')


def modo():
    """``'0'``, ``'avisar'`` o ``'1'``. Un valor raro, o sin secreto para verificar, es ``'0'``."""
    valor = _entorno('DCASA_PUERTA_OBLIGATORIA').lower() or APAGADA
    if valor not in MODOS or len(secreto()) < LARGO_MINIMO_SECRETO:
        return APAGADA
    return valor


def exigir_correo():
    return _entorno('DCASA_PUERTA_EXIGIR_CORREO') == '1'


def correo_de_la_puerta(valor, ahora=None):
    """El correo con el que se pasó la puerta, o ``None`` si la cabecera falta, está vencida o no la firmó el borde."""
    if not valor or not isinstance(valor, str):
        return None
    clave = secreto()
    if len(clave) < LARGO_MINIMO_SECRETO:
        return None
    partes = valor.split('|')
    if len(partes) != 3:
        return None
    correo, vence, firma = partes
    if not _CORREO.match(correo) or not vence.isdigit() or len(vence) > 12 or not _FIRMA.match(firma):
        return None
    if int(vence) <= int(ahora if ahora is not None else time.time()):
        return None
    esperada = hmac.new(clave.encode(), f'cabecera|{correo}|{vence}'.encode(), sha256).hexdigest()
    if not hmac.compare_digest(esperada, firma):
        return None
    return correo.lower()


def coincide(usuario, correo):
    """¿El correo de la puerta es el de esta cuenta de Odoo (su correo o su usuario)?"""
    propios = {(usuario.email or '').strip().lower(), (usuario.login or '').strip().lower()} - {''}
    return correo.lower() in propios


def problema(valor, usuario, ahora=None):
    """``None`` si la puerta está bien abierta para este usuario; si no, ``SIN_PUERTA`` o ``CORREO_DISTINTO``."""
    correo = correo_de_la_puerta(valor, ahora)
    if not correo:
        return SIN_PUERTA
    if exigir_correo() and not coincide(usuario, correo):
        return CORREO_DISTINTO
    return None
