"""El transporte de Resend, sin base de datos (funciones y una clase puras: se prueban sin Odoo).

Odoo arma cada correo como siempre (``mail.mail`` → ``email.message.EmailMessage``) y, en vez de hablar SMTP, se lo
entrega a ``SesionResend.send_message``, que lo traduce al JSON de ``POST https://api.resend.com/emails``.

Reglas que no se rompen:

* **La clave nunca sale**: no está en el texto de ninguna excepción ni de ningún log (se tacha si Resend la repitiera),
  ni en ``repr()`` de la sesión.
* **Nunca se lanza ``smtplib.SMTPServerDisconnected``**: Odoo cortaría el lote entero (``mail_mail.py``). Cada error es
  un ``RuntimeError`` cuyo texto empieza con ``DCASA_REINTENTAR:`` (temporal: 429, 5xx, sin red) o
  ``DCASA_NO_ENVIADO:`` (la política no lo dejó salir; no se llama a Resend).
* Las direcciones de las personas no van al log: solo el Message-Id y el id que devuelve Resend.
"""
import base64
import hashlib
import logging
import re
from email.utils import getaddresses

import requests

from . import politica

_logger = logging.getLogger(__name__)

URL_RESEND = 'https://api.resend.com/emails'
TIEMPO = (5, 30)   # segundos: conectar, esperar la respuesta
PREFIJO_REINTENTAR = 'DCASA_REINTENTAR:'
PREFIJO_NO_ENVIADO = 'DCASA_NO_ENVIADO:'
# Cabeceras propias que viajan a Resend (el hilo de respuestas); las demás las pone Resend o son de Odoo.
CABECERAS_QUE_VIAJAN = ('References', 'In-Reply-To')
_CORREO_EN_TEXTO = re.compile(r'[^\s<>"\'@,;:]+@[^\s<>"\'@,;:]+')
MAX_DETALLE = 300


def _normal(direccion):
    return (direccion or '').strip().lower()


def direcciones(valores):
    """Las direcciones (sin nombre visible) de una o varias cabeceras ``To``/``Cc``."""
    textos = [str(v) for v in (valores or []) if v]
    return [correo.strip() for _nombre, correo in getaddresses(textos) if correo and '@' in correo]


def mensaje_a_resend(message, smtp_to_list, remitente, nombre, responder_a):
    """El JSON que espera Resend para este correo.

    * ``from`` y ``reply_to`` son siempre los de Ajustes (se ignora el ``From`` de Odoo, que puede ser el de la
      vendedora);
    * ``to`` y ``cc`` salen de las cabeceras, pero solo con quien de verdad recibe (``smtp_to_list``): Odoo pone en
      ``To`` a otros clientes del mismo documento para «responder a todos» y aquí no se exponen;
    * ``bcc``: el resto de ``smtp_to_list`` (Odoo ya borró la cabecera ``Bcc``);
    * los adjuntos van en base64 con su nombre; las cabeceras ``X-Dcasa-*`` no salen.
    """
    destinos = []
    for direccion in smtp_to_list or []:
        if _normal(direccion) and _normal(direccion) not in [_normal(d) for d in destinos]:
            destinos.append(direccion.strip())
    pendientes = {_normal(d): d for d in destinos}

    def tomar(cabecera):
        elegidas = []
        for direccion in direcciones(message.get_all(cabecera, [])):
            clave = _normal(direccion)
            if clave in pendientes:
                elegidas.append(pendientes.pop(clave))
        return elegidas

    para = tomar('To')
    copia = tomar('Cc')
    oculta = list(pendientes.values())
    if not para:
        if len(oculta) != 1:
            raise RuntimeError(f'{PREFIJO_NO_ENVIADO} El correo no tiene un destinatario visible.')
        para, oculta = oculta, []

    datos = {
        'from': remitente_visible(nombre, remitente),
        'to': para,
        'subject': str(message['Subject'] or ''),
    }
    opcionales = {'reply_to': [responder_a] if responder_a else None, 'cc': copia, 'bcc': oculta}
    datos.update({clave: valor for clave, valor in opcionales.items() if valor})
    datos.update(_cuerpos(message))
    adjuntos = _adjuntos(message)
    if adjuntos:
        datos['attachments'] = adjuntos
    cabeceras = {nombre_cabecera: ' '.join(str(message[nombre_cabecera]).split())
                 for nombre_cabecera in CABECERAS_QUE_VIAJAN if message[nombre_cabecera]}
    if cabeceras:
        datos['headers'] = cabeceras
    return datos


def _cuerpos(message):
    """El HTML y el texto del correo (``{'html': …, 'text': …}``, solo los que existan)."""
    cuerpos = {}
    for clave, tipo in (('html', 'html'), ('text', 'plain')):
        parte = message.get_body(preferencelist=(tipo,))
        if parte is not None:
            cuerpos[clave] = parte.get_content()
    return cuerpos


def _adjuntos(message):
    """Los adjuntos en base64 con su nombre, como los pide Resend."""
    return [{'filename': parte.get_filename() or 'adjunto',
             'content': base64.b64encode(parte.get_payload(decode=True) or b'').decode('ascii')}
            for parte in message.iter_attachments()]


def remitente_visible(nombre, correo):
    """«"D'CASA Panamá" <ventas@dcasapty.com>»: el nombre entre comillas y en UTF-8 (Resend arma la cabecera)."""
    limpio = ' '.join(str(nombre or '').replace('"', '').replace('\\', '').replace('<', '').replace('>', '').split())
    return f'"{limpio}" <{correo}>' if limpio else correo


def idempotencia(message_id, smtp_to_list):
    """La misma clave para el mismo correo a los mismos destinatarios: si Odoo reintenta, Resend no lo duplica."""
    base = '|'.join([str(message_id or '').strip()] + sorted(_normal(d) for d in smtp_to_list or []))
    return 'dcasa-' + hashlib.sha256(base.encode('utf-8')).hexdigest()[:48]


def clasificar_error(estado=None, excepcion=None):
    """``'temporal'`` (vale reintentar: 429, 5xx, sin respuesta) o ``'definitivo'`` (otro 4xx)."""
    if excepcion is not None:
        return 'temporal' if isinstance(excepcion, (requests.Timeout, requests.ConnectionError)) else 'definitivo'
    if estado == 429 or (estado or 0) >= 500:
        return 'temporal'
    return 'definitivo'


def tachar(texto, clave):
    """Sin la clave (por si Resend la repitiera) y sin direcciones de personas."""
    texto = str(texto or '')
    if clave:
        texto = texto.replace(clave, '***')
    texto = _CORREO_EN_TEXTO.sub('[correo]', texto)
    texto = ' '.join(texto.split())
    return texto[:MAX_DETALLE]


def detalle_de_respuesta(respuesta, clave=''):
    """El mensaje de error que trae Resend (``message`` o ``name``), recortado y tachado."""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = None
    if isinstance(cuerpo, dict):
        detalle = cuerpo.get('message') or cuerpo.get('name') or ''
    else:
        detalle = (getattr(respuesta, 'text', '') or '')[:MAX_DETALLE]
    return tachar(detalle, clave) or 'sin detalle'


class SesionResend:
    """Lo que Odoo espera de una conexión SMTP (``send_message`` y ``quit``), hablando con Resend.

    ``config``: ``remitente``, ``nombre``, ``responder_a``, ``a_clientes`` (interruptor ya resuelto con la clave y el
    entorno), ``entorno``. ``correos_internos``: los correos del equipo (para la prueba).
    """

    from_filter = None
    mail_server_name = 'Resend'

    def __init__(self, clave, config, correos_internos=()):
        self.__clave = clave
        self.remitente = config['remitente']
        self.nombre = config['nombre']
        self.responder_a = config['responder_a']
        self.a_clientes = bool(config['a_clientes'])
        self.entorno = config['entorno']
        self.correos_internos = {_normal(c) for c in correos_internos if c}
        self.smtp_from = self.remitente

    def __repr__(self):
        return '<SesionResend>'

    def quit(self):
        """No hay conexión que cerrar."""
        return None

    def send_message(self, message, smtp_from=None, smtp_to_list=None):
        clase = str(message[politica.CABECERA_CLASE] or politica.CLASE_ODOO).strip()
        sale, motivo = politica.puede_salir(
            clase, self.a_clientes, self.entorno, smtp_to_list or [], self.correos_internos)
        if not sale:
            raise RuntimeError(f'{PREFIJO_NO_ENVIADO} {motivo}')
        datos = mensaje_a_resend(message, smtp_to_list, self.remitente, self.nombre, self.responder_a)
        cabeceras = {
            'Authorization': f'Bearer {self.__clave}',
            'Idempotency-Key': idempotencia(message['Message-Id'], smtp_to_list),
            'User-Agent': 'dcasa-odoo',
        }
        try:
            respuesta = requests.post(URL_RESEND, json=datos, timeout=TIEMPO, headers=cabeceras)
        except (requests.Timeout, requests.ConnectionError) as error:
            raise RuntimeError(f'{PREFIJO_REINTENTAR} Resend no respondió ({type(error).__name__}).') from None
        except requests.RequestException as error:
            raise RuntimeError(f'No se pudo llamar a Resend ({type(error).__name__}).') from None
        estado = getattr(respuesta, 'status_code', 0) or 0
        if 200 <= estado < 300:
            try:
                resend_id = (respuesta.json() or {}).get('id')
            except (ValueError, AttributeError):
                resend_id = None
            _logger.info('DCASA_CORREO enviado clase=%s message_id=%s resend_id=%s',
                         clase, message['Message-Id'], resend_id)
            return {}
        detalle = detalle_de_respuesta(respuesta, self.__clave)
        if clasificar_error(estado) == 'temporal':
            raise RuntimeError(f'{PREFIJO_REINTENTAR} Resend respondió {estado}: {detalle}')
        raise RuntimeError(f'Resend no aceptó el correo ({estado}): {detalle}')
