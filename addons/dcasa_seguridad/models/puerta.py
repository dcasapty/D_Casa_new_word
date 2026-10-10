"""La puerta del equipo, vista desde Odoo (edge/src/puerta.ts, docs/SEGURIDAD_ACCESO.md §8).

El personal entra al panel por tres pasos: el PIN al correo (Cloudflare Access, en el borde), la clave y el
código de la app. El borde verifica el primer paso y le pasa a Odoo, en cada petición, DOS cabeceras firmadas con
``DCASA_PUERTA_SECRETO`` (el mismo secreto que tiene el Worker; solo vive en el entorno, nunca en la base):

* ``X-Dcasa-Puerta: <correo>|<vence>|<firma>``: quién pasó la puerta (solo si la pasó).
* ``X-Dcasa-Puerta-Modo: <modo>|<exigir correo 0/1>|<vence>|<firma>``: qué se exige en ESTA petición. Lo decide el
  Worker con su variable ``DCASA_PUERTA_OBLIGATORIA`` (por eso cambiarla y desplegar surte efecto al instante, sin
  reiniciar el contenedor: es el rescate). Los modos:

  * ``0``: no se exige nada.
  * ``avisar``: quien entra sin puerta entra, pero queda en «Accesos al panel» y se avisa por Telegram. Sirve para
    comprobar, antes de cerrar, que todo el equipo ya está pasando por la puerta.
  * ``1``: el personal (usuarios internos) solo inicia sesión y solo sigue dentro con la puerta abierta. Los
    clientes del portal y los socios nunca pasan por aquí.

Una petición SIN la cabecera del modo (o con una que no se pueda verificar) no exige nada: así lo que nace dentro
del contenedor y no pasa por el borde (el PDF de una factura, por ejemplo, que llama a Odoo con la sesión de quien
lo pidió) sigue funcionando, y un error de copiar y pegar el secreto nunca deja a todo el personal fuera.
Rescate si la puerta no abre: ``DCASA_PUERTA_OBLIGATORIA=0`` en el Worker y desplegar.

``exigir correo``: además, el correo con el que se pasó la puerta tiene que ser el correo (o el usuario) de la
cuenta de Odoo: así la lista de Access y la de Odoo quedan amarradas.
"""
import hmac
import os
import re
import time
from hashlib import sha256

CABECERA = 'X-Dcasa-Puerta'
CABECERA_MODO = 'X-Dcasa-Puerta-Modo'

APAGADA = '0'
AVISAR = 'avisar'
OBLIGATORIA = '1'
MODOS = (APAGADA, AVISAR, OBLIGATORIA)

# Resultados que se anotan en «Accesos al panel»
SIN_PUERTA = 'sin_puerta'
CORREO_DISTINTO = 'puerta_correo'

LARGO_MINIMO_SECRETO = 32
# ASCII imprimible, sin «|» ni un segundo «@» (igual que el borde): lo demás haría fallar las cabeceras HTTP.
_CORREO = re.compile(r'[\x21-\x3f\x41-\x7b\x7d-\x7e]{1,64}@[\x21-\x3f\x41-\x7b\x7d-\x7e]{1,190}')
_FIRMA = re.compile(r'[0-9a-f]{64}')
_NUMERO = re.compile(r'[0-9]{1,12}')


def secreto():
    return (os.environ.get('DCASA_PUERTA_SECRETO') or '').strip()


def _firma_valida(clave, mensaje, firma):
    esperada = hmac.new(clave.encode(), mensaje.encode(), sha256).hexdigest()
    return hmac.compare_digest(esperada, firma)


def ajustes_de_la_peticion(valor, ahora=None):
    """``(modo, exigir_correo)`` que el borde firmó para esta petición; ``('0', False)`` si falta o no se verifica."""
    sin_exigencia = (APAGADA, False)
    clave = secreto()
    if not valor or not isinstance(valor, str) or len(clave) < LARGO_MINIMO_SECRETO:
        return sin_exigencia
    partes = valor.split('|')
    if len(partes) != 4:
        return sin_exigencia
    modo, exigir, vence, firma = partes
    if modo not in MODOS or exigir not in ('0', '1') or not _NUMERO.fullmatch(vence) or not _FIRMA.fullmatch(firma):
        return sin_exigencia
    if int(vence) <= int(ahora if ahora is not None else time.time()):
        return sin_exigencia
    if not _firma_valida(clave, f'modo|{modo}|{exigir}|{vence}', firma):
        return sin_exigencia
    return modo, exigir == '1'


def correo_de_la_puerta(valor, ahora=None):
    """El correo con el que se pasó la puerta, o ``None`` si la cabecera falta, está vencida o no la firmó el borde."""
    clave = secreto()
    if not valor or not isinstance(valor, str) or len(clave) < LARGO_MINIMO_SECRETO:
        return None
    partes = valor.split('|')
    if len(partes) != 3:
        return None
    correo, vence, firma = partes
    if not _CORREO.fullmatch(correo) or not _NUMERO.fullmatch(vence) or not _FIRMA.fullmatch(firma):
        return None
    if int(vence) <= int(ahora if ahora is not None else time.time()):
        return None
    if not _firma_valida(clave, f'cabecera|{correo}|{vence}', firma):
        return None
    return correo.lower()


def coincide(usuario, correo):
    """¿El correo de la puerta es el de esta cuenta de Odoo (su correo o su usuario)?"""
    propios = {(usuario.email or '').strip().lower(), (usuario.login or '').strip().lower()} - {''}
    return correo.lower() in propios


def problema(valor, usuario, exigir_correo=False, ahora=None):
    """``None`` si la puerta está bien abierta para este usuario; si no, ``SIN_PUERTA`` o ``CORREO_DISTINTO``."""
    correo = correo_de_la_puerta(valor, ahora)
    if not correo:
        return SIN_PUERTA
    if exigir_correo and not coincide(usuario, correo):
        return CORREO_DISTINTO
    return None
