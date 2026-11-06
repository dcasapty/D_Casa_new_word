"""El cliente de Resend para las CAMPAÑAS: contactos, el segmento y los *broadcasts* (sin base de datos).

Revisado en la documentación oficial el 2026-11-06 (``https://resend.com/docs/llms.txt``):

* **La clave**: ``RESEND_CAMPANAS_API_KEY``, aparte de la de los correos de factura (``RESEND_API_KEY``, «Sending
  access»). Resend solo tiene dos permisos: ``sending_access`` (solo manda correos; en contactos y broadcasts contesta
  401 ``restricted_api_key``) y ``full_access``. Para campañas hace falta **Full access**.
* **Segmento** («Audiences are now called Segments»): ``GET /segments`` y ``POST /segments {name}``;
  ``GET /segments/{id}/contacts?limit=100&after=…`` (``{data: [{id, email, unsubscribed}], has_more}``). El plan
  gratis de marketing tiene **3 segmentos** (el Pro, ilimitados; revisado el 2026-11-06): Camila usa uno solo, reusado.
* **Todos los contactos**: ``GET /contacts?limit=100&after=…`` («Show all contacts»; ``segment_id`` opcional).
* **Contactos**: ``POST /contacts {email, first_name, segments: [{id}]}``; ``POST /contacts/{email}/segments/{id}``
  (agregar uno que ya existe); ``DELETE /contacts/{id o email}/segments/{id}`` (sacarlo); ``PATCH /contacts/{id o
  email} {unsubscribed: true}`` (la baja vale para todas las campañas). «Either id or email must be provided»: Camila
  saca y da de baja **por el id** del contacto que listó el segmento (un correo con otra grafía en Resend daba 404).
* **Broadcast**: ``POST /broadcasts {segment_id, from, subject, html, reply_to, name}`` lo crea en borrador y
  ``POST /broadcasts/{id}/send`` lo manda. ``GET /broadcasts/{id}`` dice su ``status`` (draft, scheduled, queued,
  sent, canceled). ``DELETE /broadcasts/{id}`` borra uno que no ha salido (draft o scheduled). La baja va en el HTML
  con ``{{{RESEND_UNSUBSCRIBE_URL}}}``.
* **Resultados**: ``GET /broadcasts/{id}/recipients?type=delivered|opened|clicked|unsubscribed&limit=100``, filas
  ``{id (cursor), contact_id, email}`` (Resend avisa que las aperturas pueden no ser exactas).
* **Límite**: 10 peticiones por segundo por equipo (429 ``rate_limit_exceeded`` con ``retry-after``).

Reglas que no se rompen: la clave nunca sale (ni en un error ni en un log ni en ``repr``); los correos de las personas
no van al log; nada de esto toca los correos de factura.
"""
import logging
import time
from urllib.parse import quote

import requests

from odoo.addons.dcasa_correo.models import resend as R_correo

_logger = logging.getLogger(__name__)

URL = 'https://api.resend.com'
TIEMPO = (5, 30)        # segundos: conectar, esperar la respuesta
PAUSA = 0.12            # entre llamadas: 10 por segundo como mucho (el límite de Resend por equipo)
INTENTOS = 3
ESPERA_MAXIMA = 5.0
POR_PAGINA = 100
MAX_PAGINAS = 200       # 20 000 contactos: más que el plan de D'CASA; corta un bucle si Resend repitiera páginas
ESTADOS_YA_SALIO = ('scheduled', 'queued', 'sent')


class ErrorResend(Exception):
    """Un error de Resend con el mensaje en palabras sencillas (sin la clave ni correos de personas)."""

    def __init__(self, mensaje, estado=None, temporal=False):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado
        self.temporal = temporal


def correo_en_ruta(correo):
    return quote((correo or '').strip().lower(), safe='@')


def contacto_en_ruta(contacto):
    """El contacto en la ruta: su id (tal cual) o, si es un correo, el correo en minúsculas."""
    contacto = (contacto or '').strip()
    return correo_en_ruta(contacto) if '@' in contacto else quote(contacto, safe='')


class ClienteCampanas:
    """Habla con la API de Resend con la clave de campañas. ``pausa`` es 0 en las pruebas."""

    def __init__(self, clave, pausa=PAUSA):
        self.__clave = (clave or '').strip()
        self.pausa = pausa

    def __repr__(self):
        return '<ClienteCampanas>'

    # -- HTTP ---------------------------------------------------------------

    def _llamar(self, metodo, ruta, cuerpo=None, params=None):
        cabeceras = {'Authorization': f'Bearer {self.__clave}', 'User-Agent': 'dcasa-odoo-camila',
                     'Content-Type': 'application/json'}
        for intento in range(INTENTOS):
            try:
                respuesta = requests.request(metodo, URL + ruta, json=cuerpo, params=params, headers=cabeceras,
                                             timeout=TIEMPO)
            except (requests.Timeout, requests.ConnectionError) as error:
                if intento < INTENTOS - 1:
                    time.sleep(self.pausa * (intento + 1))
                    continue
                raise ErrorResend(f'Resend no respondió ({type(error).__name__}).', temporal=True) from None
            except requests.RequestException as error:
                raise ErrorResend(f'No se pudo llamar a Resend ({type(error).__name__}).') from None
            estado = getattr(respuesta, 'status_code', 0) or 0
            if 200 <= estado < 300:
                if self.pausa:
                    time.sleep(self.pausa)
                try:
                    datos = respuesta.json()
                except ValueError:
                    datos = {}
                return datos if isinstance(datos, dict) else {}
            if estado == 429 and intento < INTENTOS - 1:
                try:
                    espera = float(respuesta.headers.get('retry-after') or 1)
                except (TypeError, ValueError, AttributeError):
                    espera = 1.0
                if self.pausa:
                    time.sleep(min(max(espera, self.pausa), ESPERA_MAXIMA))
                continue
            raise self._error(respuesta, estado)
        raise ErrorResend('Resend pidió esperar demasiadas veces.', estado=429, temporal=True)

    def _error(self, respuesta, estado):
        detalle = R_correo.detalle_de_respuesta(respuesta, self.__clave)
        minusculas = detalle.lower()
        if estado in (401, 403) and ('restricted' in minusculas or 'only send' in minusculas):
            return ErrorResend('La clave de campañas solo tiene permiso de envío: en Resend tiene que ser «Full '
                               'access» (ver docs/CAMILA.md).', estado=estado)
        if estado in (400, 401, 403) and 'api key' in minusculas:
            return ErrorResend('Resend no acepta la clave de campañas (borrada, inactiva o mal copiada).',
                               estado=estado)
        return ErrorResend(f'Resend respondió {estado}: {detalle}', estado=estado,
                           temporal=estado == 429 or estado >= 500)

    def _paginas(self, ruta, params=None):
        """Todas las filas de una lista con cursor (``limit`` + ``after``)."""
        filas, despues = [], None
        for _pagina in range(MAX_PAGINAS):
            consulta = dict(params or {}, limit=POR_PAGINA)
            if despues:
                consulta['after'] = despues
            datos = self._llamar('GET', ruta, params=consulta)
            lote = datos.get('data') or []
            filas.extend(lote)
            if not datos.get('has_more') or not lote:
                return filas
            despues = lote[-1].get('id')
            if not despues:
                return filas
        raise ErrorResend('La lista de Resend no terminaba: se cortó para no quedarse dando vueltas.')

    # -- Segmento -----------------------------------------------------------

    def buscar_o_crear_segmento(self, nombre):
        for segmento in self._llamar('GET', '/segments').get('data') or []:
            if (segmento.get('name') or '').strip() == nombre and segmento.get('id'):
                return segmento['id']
        creado = self._llamar('POST', '/segments', {'name': nombre})
        if not creado.get('id'):
            raise ErrorResend('Resend no devolvió el segmento creado.')
        return creado['id']

    def contactos_del_segmento(self, segmento_id):
        """``[{id, email, unsubscribed}]`` de todo el segmento."""
        return self._paginas(f'/segments/{quote(segmento_id)}/contacts')

    def contactos(self):
        """``[{id, email, unsubscribed}]`` de TODOS los contactos de la cuenta (``GET /contacts``: «Show all
        contacts»): de aquí se leen las bajas, estén o no en el segmento de envío."""
        return self._paginas('/contacts')

    # -- Contactos ----------------------------------------------------------

    def agregar_contacto(self, correo, nombre, segmento_id):
        """Lo deja en el segmento: lo crea con su nombre de pila o, si ya existía, lo agrega. No toca su baja."""
        cuerpo = {'email': correo, 'segments': [{'id': segmento_id}]}
        if nombre:
            cuerpo['first_name'] = nombre
        try:
            return self._llamar('POST', '/contacts', cuerpo)
        except ErrorResend as error:
            if error.estado in (401, 403, 429) or (error.estado or 0) >= 500 or error.estado is None:
                raise
        # Ya existía (Resend no documenta ese error): se agrega al segmento por su correo.
        return self._llamar('POST', f'/contacts/{correo_en_ruta(correo)}/segments/{quote(segmento_id)}')

    def sacar_del_segmento(self, contacto, segmento_id):
        """``contacto``: su id (lo que lista el segmento) o su correo. Si ya no existe, no hay nada que sacar."""
        try:
            return self._llamar('DELETE', f'/contacts/{contacto_en_ruta(contacto)}/segments/{quote(segmento_id)}')
        except ErrorResend as error:
            if error.estado == 404:
                return {}
            raise

    def dar_de_baja(self, contacto):
        """La baja vale para todas las campañas (``unsubscribed: true``). ``contacto``: su id o su correo. Si el
        contacto no existe, no hay nada."""
        try:
            return self._llamar('PATCH', f'/contacts/{contacto_en_ruta(contacto)}', {'unsubscribed': True})
        except ErrorResend as error:
            if error.estado == 404:
                return {}
            raise

    # -- Broadcast ----------------------------------------------------------

    def crear_broadcast(self, segmento_id, remitente, asunto, html, responder_a=None, nombre=None):
        cuerpo = {'segment_id': segmento_id, 'from': remitente, 'subject': asunto, 'html': html}
        if responder_a:
            cuerpo['reply_to'] = responder_a
        if nombre:
            cuerpo['name'] = nombre
        creado = self._llamar('POST', '/broadcasts', cuerpo)
        if not creado.get('id'):
            raise ErrorResend('Resend no devolvió la campaña creada.')
        return creado['id']

    def estado_broadcast(self, broadcast_id):
        return (self._llamar('GET', f'/broadcasts/{quote(broadcast_id)}').get('status') or '').lower()

    def enviar_broadcast(self, broadcast_id):
        return self._llamar('POST', f'/broadcasts/{quote(broadcast_id)}/send', {})

    def borrar_broadcast(self, broadcast_id):
        """Borra en Resend una campaña que no salió (draft o scheduled). Si ya no existe, no hay nada."""
        try:
            return self._llamar('DELETE', f'/broadcasts/{quote(broadcast_id)}')
        except ErrorResend as error:
            if error.estado == 404:
                return {}
            raise

    def destinatarios(self, broadcast_id, tipo):
        """Las filas ``{id, contact_id, email}`` de quienes tuvieron ese evento (delivered, opened, clicked,
        unsubscribed)."""
        return self._paginas(f'/broadcasts/{quote(broadcast_id)}/recipients', {'type': tipo})

    def contar_destinatarios(self, broadcast_id, tipo):
        """Cuántas personas tuvieron ese evento."""
        return len(self.destinatarios(broadcast_id, tipo))
