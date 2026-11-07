"""El remitente de las campañas y lo que Resend dice de su dominio (2026-11-07, docs/CAMILA.md §1d).

La tabla de campañas decía 0 «Abrieron» y 0 «Tocaron»: Resend trae el conteo de aperturas y clics **apagado por
dominio**, y Camila salía del remitente de las facturas (``dcasa_correo.remitente``, ``ventas@dcasapty.com``).
Encenderlo en ``dcasapty.com`` pondría el píxel y cambiaría los enlaces también en las facturas; Resend recomienda
contar solo en el dominio de las campañas. Decisión: un subdominio de marketing con el conteo encendido
(``novedades.dcasapty.com``, subdominio de seguimiento ``links``) y las facturas, limpias.

* **«Remitente de las campañas»** (``dcasa_camila.remitente``; lo cambian Gerencia y los administradores, como el resto
  de los ajustes de Camila): vacío, las campañas salen del de las facturas, como antes. Con un correo, el *broadcast* y
  «Enviarme una prueba» salen de ahí, con **el mismo nombre** («D'CASA Panamá») y **la misma dirección de respuesta**
  (``info@dcasapty.com``) de siempre. El remitente de las facturas no se toca.
* **La revisión en Resend** (``_revisar_remitente``): con la clave de campañas y en producción se leen los dominios
  (``GET /domains`` y, para el subdominio de seguimiento y sus registros, ``GET /domains/{id}``) y se guarda lo que
  importa (``dcasa_camila.remitente_revision``): si está verificado y si cuenta aperturas y clics. Se pregunta con el
  cron de cada hora (cada 6 horas; si falló, a la hora), al cambiar el remitente, con «Revisar ahora» y al tocar
  «Enviar» si lo guardado no deja enviar. **La pantalla solo lee lo guardado**: nunca llama a Resend ni falla por él.
* **El aviso** (``_aviso_remitente``): sin verificar o sin estar en Resend, lo dice y **no deja enviar** (un
  *broadcast* desde un dominio sin verificar falla en Resend); con el conteo apagado, lo dice con los tres pasos para
  encenderlo. Si Resend falla, solo una nota suave: lo que no se sabe no bloquea.
* La clave nunca sale (``ErrorResend`` ya la tacha) y los registros no llevan correos de personas.
"""
import json
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_correo.models.correo import correo_valido
from odoo.exceptions import AccessError, UserError

from . import resend_campanas as RC

_logger = logging.getLogger(__name__)

P_REMITENTE = 'dcasa_camila.remitente'
P_REVISION = 'dcasa_camila.remitente_revision'
HORAS_REVISION = 6              # el cron vuelve a preguntar cada 6 horas como mucho
HORAS_REINTENTO = 1             # si la última vez Resend falló, con el cron siguiente
SEGUNDOS_ENTRE_REVISIONES = 15  # «Revisar ahora» dos veces seguidas no pregunta dos veces
MAX_CORREO = 254
# Lo que dice Resend del dominio (docs: «Understand a domain status»). «partially_verified» envía normal.
VERIFICADOS = ('verified', 'partially_verified')
NO_VERIFICADOS = ('not_started', 'pending', 'failed')
BLOQUEAN = ('no_esta', 'no_verificado')
CAMPOS_DETALLE = ('open_tracking', 'click_tracking', 'tracking_subdomain', 'records')
ESTADOS_LEGIBLES = {
    'not_started': '«sin empezar» (nadie tocó «Verify DNS Records»)',
    'pending': '«verificándose» (todavía no encuentra sus registros)',
    'failed': '«falló» (no encontró sus registros en 72 horas)',
    'temporary_failure': '«con una falla temporal» (dejó de encontrar uno de sus registros)',
    'partially_failed': '«con una parte sin verificar»',
}
# La marca del contexto con que «Enviarme una prueba» sale del remitente de las campañas (``RemitentePrueba``).
MARCA_PRUEBA = 'dcasa_camila_remitente_prueba'


class RemitentePrueba:
    """El remitente de la prueba, en el contexto de ``mail.send``. Es un objeto de Python: por RPC solo llegan textos,
    números y listas, así que nadie puede cambiar desde afuera el remitente de un correo (una factura, por ejemplo)."""

    __slots__ = ('correo',)

    def __init__(self, correo):
        self.correo = correo

    def __repr__(self):
        return '<RemitentePrueba>'


def dominio_de(correo):
    return (correo or '').rpartition('@')[2].strip().lower()


def _si_no(valor):
    """``True``/``False`` si Resend lo dijo; ``None`` si no (lo que no se sabe no se adivina)."""
    return valor if isinstance(valor, bool) else None


def _texto(valor):
    return str(valor or '').strip().lower()


def clasificar_dominio(datos):
    """Lo que le importa a Camila de un dominio de Resend (sin base de datos):

    * ``resultado``: ``ok`` (sale), ``no_verificado`` (no sale: sin empezar, verificándose, falló o con el envío
      apagado) u ``otro`` (una falla temporal o un estado nuevo: se avisa sin bloquear);
    * ``aperturas`` y ``clics``: si el conteo está encendido (``None`` si Resend no lo dijo);
    * ``subdominio`` y ``seguimiento_verificado``: el subdominio de seguimiento y si su registro está verificado
      (Resend solo cuenta con él configurado y verificado; con varios, cuenta el del subdominio de ahora)."""
    estado = _texto(datos.get('status'))
    capacidades = datos.get('capabilities') if isinstance(datos.get('capabilities'), dict) else {}
    if estado in NO_VERIFICADOS or _texto(capacidades.get('sending')) == 'disabled':
        resultado = 'no_verificado'
    elif estado in VERIFICADOS:
        resultado = 'ok'
    else:
        resultado = 'otro'
    subdominio = _texto(datos.get('tracking_subdomain')) or None
    seguimiento = None
    registros = [r for r in datos.get('records') or []
                 if isinstance(r, dict) and _texto(r.get('record')) == 'tracking']
    if subdominio and registros:
        propios = [r for r in registros
                   if _texto(r.get('name')) == subdominio or _texto(r.get('name')).startswith(f'{subdominio}.')]
        seguimiento = any(_texto(r.get('status')) == 'verified' for r in propios or registros)
    return {'resultado': resultado, 'estado': estado or None, 'aperturas': _si_no(datos.get('open_tracking')),
            'clics': _si_no(datos.get('click_tracking')), 'subdominio': subdominio,
            'seguimiento_verificado': seguimiento}


class DcasaCamila(models.AbstractModel):
    _inherit = 'dcasa.camila'

    # ------------------------------------------------------------------
    # El remitente
    # ------------------------------------------------------------------

    @api.model
    def _remitente_propio(self):
        """El remitente de las campañas que puso Gerencia (``''`` si no puso ninguno o no sirve)."""
        return correo_valido(self.env['ir.config_parameter'].sudo().get_param(P_REMITENTE) or '') or ''

    @api.model
    def _remitente_campanas(self):
        """De qué correo salen las campañas: el propio o, si no hay, el de las facturas (como antes)."""
        return self._remitente_propio() or self.env['dcasa.correo'].sudo()._config()['remitente']

    @api.model
    def _remitente_texto(self):
        """«D'CASA Panamá <correo>»: el nombre de siempre con el correo de las campañas (para la pantalla)."""
        return f"{self.env['dcasa.correo'].sudo()._config()['nombre']} <{self._remitente_campanas()}>"

    @api.model
    def _ajustar_remitente(self, correo):
        """Guarda el remitente de las campañas (Gerencia o administradores). Un solo correo bien escrito, sin nombre
        (el nombre es el de siempre); vacío = el de las facturas. Después lo revisa en Resend (si se puede)."""
        if not self._ve_dinero():
            raise AccessError(self.env._('El remitente de las campañas lo cambian Gerencia o un administrador.'))
        if not isinstance(correo, str) or len(correo.strip()) > MAX_CORREO:
            raise UserError(self._mensaje_correo_invalido())
        texto = correo.strip()
        normal = correo_valido(texto) if texto else ''
        if texto and (not normal or normal != texto.lower()):
            raise UserError(self._mensaje_correo_invalido())
        self.env['ir.config_parameter'].sudo().set_param(P_REMITENTE, normal or False)
        _logger.info('DCASA_CAMILA remitente de las campañas: %s (uid %s)', dominio_de(normal) or 'el de las facturas',
                     self.env.uid)
        self._revisar_remitente_sin_fallar('ahora')

    @api.model
    def _mensaje_correo_invalido(self):
        return self.env._('Escribe un solo correo, sin nombre, por ejemplo novedades@novedades.dcasapty.com (o déjalo '
                          'vacío para que salgan del correo de las facturas).')

    # ------------------------------------------------------------------
    # Lo que dice Resend del dominio
    # ------------------------------------------------------------------

    @api.model
    def _puede_revisar_remitente(self):
        """Solo en producción y con la clave de campañas (staging nunca habla con Resend por las campañas)."""
        return bool(self._clave()) and self._entorno() == 'produccion'

    @api.model
    def _revision_remitente(self):
        """Lo último que se revisó en Resend del dominio del remitente de HOY (``None`` si es de otro dominio, si nunca
        se revisó o si no es producción con la clave). Solo lee lo guardado: nunca llama a Resend."""
        if not self._puede_revisar_remitente():
            return None
        try:
            revision = json.loads(self.env['ir.config_parameter'].sudo().get_param(P_REVISION) or 'null')
        except ValueError:
            return None
        if not isinstance(revision, dict) or not revision.get('en') \
                or revision.get('dominio') != dominio_de(self._remitente_campanas()):
            return None
        return revision

    @api.model
    def _edad_revision(self, revision):
        try:
            return fields.Datetime.now() - fields.Datetime.to_datetime(revision['en'])
        except (KeyError, TypeError, ValueError):
            return timedelta(days=3650)

    @api.model
    def _revisar_remitente(self, cuando='cron'):
        """Pregunta a Resend por el dominio del remitente de las campañas y lo guarda, solo si hace falta:

        * ``cron`` (cada hora): si no hay nada de ESTE dominio, si pasaron 6 horas o, si la última vez falló, 1 hora;
        * ``enviar`` (al tocar «Enviar»): además si lo guardado no deja enviar (lo pudieron verificar recién) o falló;
        * ``ahora`` («Revisar ahora» o al cambiar el remitente): siempre, salvo que se revisó hace unos segundos.

        Devuelve lo guardado (``None`` fuera de producción o sin la clave). Un error de Resend queda guardado como
        «error» (no bloquea nada) y no sube."""
        if not self._puede_revisar_remitente():
            return None
        anterior = self._revision_remitente()
        if anterior:
            edad = self._edad_revision(anterior)
            fallo = anterior.get('resultado') == 'error'
            if cuando == 'ahora':
                fresca = edad < timedelta(seconds=SEGUNDOS_ENTRE_REVISIONES)
            elif cuando == 'enviar':
                fresca = edad < timedelta(hours=HORAS_REVISION) and not fallo \
                    and anterior.get('resultado') not in BLOQUEAN
            else:
                fresca = edad < timedelta(hours=HORAS_REINTENTO if fallo else HORAS_REVISION)
            if fresca:
                return anterior
        revision = self._consultar_dominio(dominio_de(self._remitente_campanas()))
        self.env['ir.config_parameter'].sudo().set_param(P_REVISION, json.dumps(revision))
        _logger.info('DCASA_CAMILA remitente revisado en Resend (%s): %s', revision['dominio'], revision['resultado'])
        return revision

    @api.model
    def _revisar_remitente_sin_fallar(self, cuando):
        """``_revisar_remitente`` que nunca hace fallar a quien la llama (guardar el remitente, «Revisar ahora»,
        «Enviar»): un error inesperado queda en el registro y no se sabe nada nuevo (lo que no se sabe no bloquea)."""
        self.env.cr.flush()   # lo pendiente de quien llama, AFUERA del try: un error suyo no se traga
        try:
            with self.env.cr.savepoint():
                return self._revisar_remitente(cuando)
        except Exception:   # noqa: BLE001
            _logger.warning('DCASA_CAMILA no se pudo revisar el remitente en Resend', exc_info=True)
            return None

    @api.model
    def _consultar_dominio(self, dominio):
        """Lo que dice Resend de ``dominio`` hoy: la lista (``GET /domains``) y, si a la fila le falta el conteo, el
        subdominio de seguimiento o los registros, el detalle (``GET /domains/{id}``)."""
        revision = {'dominio': dominio, 'en': fields.Datetime.to_string(fields.Datetime.now())}
        try:
            cliente = self._cliente()
            fila = next((d for d in cliente.dominios() if isinstance(d, dict) and _texto(d.get('name')) == dominio),
                        None)
            if not fila:
                return dict(revision, resultado='no_esta', estado=None, aperturas=None, clics=None, subdominio=None,
                            seguimiento_verificado=None)
            datos = dict(fila)
            if fila.get('id') and any(campo not in fila for campo in CAMPOS_DETALLE):
                try:
                    datos.update(cliente.dominio(str(fila['id'])))
                except RC.ErrorResend as error:   # con lo de la lista basta para saber si está verificado
                    _logger.info('DCASA_CAMILA sin el detalle del dominio en Resend: %s', error.mensaje)
            return dict(revision, **clasificar_dominio(datos))
        except RC.ErrorResend as error:
            return dict(revision, resultado='error', error=(error.mensaje or '')[:200])

    @api.model
    def _remitente_no_verificado(self):
        """¿Se SABE que el dominio del remitente no está verificado en Resend (o no está)? Solo lo guardado."""
        revision = self._revision_remitente()
        return bool(revision and revision.get('resultado') in BLOQUEAN)

    @api.model
    def _mensaje_remitente_no_verificado(self):
        return self.env._('No se puede enviar: el remitente de las campañas (%s) todavía no está verificado en Resend. '
                          'Cuando Resend lo marque «Verified», toca «Revisar ahora».', self._remitente_campanas())

    # ------------------------------------------------------------------
    # El aviso de la pantalla
    # ------------------------------------------------------------------

    @api.model
    def _aviso_remitente(self, revision):
        """El aviso en palabras sencillas (``{tipo, titulo, detalle, pasos_titulo, pasos}``) o ``None``."""
        if not revision:
            return None
        resultado = revision.get('resultado')
        if resultado in BLOQUEAN:
            return self._aviso_no_verificado(revision)
        if resultado == 'otro':
            return self._aviso_otro_estado(revision)
        if resultado == 'ok':
            return self._aviso_sin_seguimiento(revision)
        return None   # «error»: solo la nota suave de la sección del remitente

    @api.model
    def _estado_legible(self, revision):
        estado = revision.get('estado') or ''
        if revision.get('resultado') == 'no_verificado' and estado in VERIFICADOS:
            return self.env._('con el envío apagado (Sending: disabled)')
        return ESTADOS_LEGIBLES.get(estado) or f'«{estado or "?"}»'

    @api.model
    def _aviso_no_verificado(self, revision):
        correo, dominio = self._remitente_campanas(), revision['dominio']
        if revision.get('resultado') == 'no_esta':
            detalle = self.env._('Las campañas saldrían de %(correo)s, pero %(dominio)s no está en Resend.',
                                 correo=correo, dominio=dominio)
            primero = self.env._('En Resend › Domains, toca «Add domain» y agrega %s.', dominio)
        else:
            detalle = self.env._('Las campañas saldrían de %(correo)s y Resend dice que %(dominio)s está %(estado)s.',
                                 correo=correo, dominio=dominio, estado=self._estado_legible(revision))
            primero = self.env._('En Resend › Domains, abre %s.', dominio)
        ultimo = self.env._('Cuando Resend diga «Verified», toca «Revisar ahora».')
        if self._remitente_propio():
            ultimo += ' ' + self.env._('Mientras tanto, si dejas vacío «Remitente de las campañas», salen del correo '
                                       'de las facturas.')
        return {
            'tipo': 'no_verificado',
            'titulo': self.env._('El remitente de las campañas todavía no está verificado en Resend: las campañas no '
                                 'saldrán desde ahí.'),
            'detalle': detalle,
            'pasos_titulo': self.env._('Cómo arreglarlo:'),
            'pasos': [primero,
                      self.env._('Copia sus registros (Records) en Cloudflare › DNS, con la nube gris («DNS only»), y '
                                 'toca «Verify DNS Records».'),
                      ultimo],
        }

    @api.model
    def _aviso_otro_estado(self, revision):
        dominio = revision['dominio']
        return {
            'tipo': 'otro',
            'titulo': self.env._('Resend dice que el dominio del remitente de las campañas tiene un problema: puede '
                                 'que las campañas no salgan.'),
            'detalle': self.env._('Remitente: %(correo)s. Resend dice que %(dominio)s está %(estado)s.',
                                  correo=self._remitente_campanas(), dominio=dominio,
                                  estado=self._estado_legible(revision)),
            'pasos_titulo': self.env._('Cómo arreglarlo:'),
            'pasos': [self.env._('En Resend › Domains, abre %s y mira sus registros (Records).', dominio),
                      self.env._('Corrige en Cloudflare › DNS el que no esté verificado (con la nube gris, «DNS '
                                 'only»).'),
                      self.env._('Cuando Resend diga «Verified», toca «Revisar ahora».')],
        }

    @api.model
    def _aviso_sin_seguimiento(self, revision):
        """Resend no cuenta aperturas o clics (apagados, o encendidos con el subdominio de seguimiento sin verificar).
        Si las campañas salen del correo de las facturas, los pasos llevan a un subdominio aparte (encenderlo ahí
        cambiaría las facturas)."""
        sin_aperturas, sin_clics = revision.get('aperturas') is False, revision.get('clics') is False
        subdominio = revision.get('subdominio')
        cname_pendiente = bool(subdominio) and revision.get('seguimiento_verificado') is False
        if not (sin_aperturas or sin_clics or cname_pendiente):
            return None
        if cname_pendiente or (sin_aperturas and sin_clics):
            que, consecuencia = self.env._('aperturas ni clics'), self.env._('Abrieron y Tocaron saldrán en 0.')
        elif sin_aperturas:
            que, consecuencia = self.env._('aperturas'), self.env._('Abrieron saldrá en 0.')
        else:
            que, consecuencia = self.env._('clics'), self.env._('Tocaron saldrá en 0.')
        correo, dominio = self._remitente_campanas(), revision['dominio']
        if not self._remitente_propio():
            detalle = self.env._(
                'Las campañas salen de %(correo)s, el mismo correo de las facturas. No lo enciendas en %(dominio)s: '
                'las facturas también llevarían el píxel y sus enlaces cambiarían. Lo recomendado es un subdominio '
                'solo para las campañas.', correo=correo, dominio=dominio)
            pasos = [
                self.env._('En Resend › Domains, agrega un subdominio solo para las campañas (por ejemplo '
                           'novedades.%s) y verifícalo: sus registros van en Cloudflare › DNS con la nube gris («DNS '
                           'only»).', dominio),
                self.env._('En ese subdominio: Configuration › Enable tracking metrics, con el subdominio «links» y '
                           'aperturas y clics encendidos; el CNAME que te da Resend también va en Cloudflare con la '
                           'nube gris.'),
                self.env._('Cuando Resend lo marque verificado, escribe un correo de ese subdominio aquí abajo, en '
                           '«Remitente de las campañas» (lo cambian Gerencia o un administrador), y toca «Guardar».'),
            ]
        elif cname_pendiente:
            registro = f'{subdominio}.{dominio}'
            detalle = self.env._('Ya está encendido en Resend, pero falta verificar el registro de seguimiento '
                                 '%(registro)s. Las campañas salen de %(correo)s.', registro=registro, correo=correo)
            pasos = [
                self.env._('En Cloudflare › DNS, agrega el CNAME %(registro)s con el valor que te da Resend (Domains › '
                           '%(dominio)s › Records).', registro=registro, dominio=dominio),
                self.env._('Déjalo con la nube gris («DNS only»): con la nube naranja Resend no lo puede verificar.'),
                self.env._('En Resend toca «Verify DNS Records» y, cuando lo marque verificado, toca aquí «Revisar '
                           'ahora».'),
            ]
        else:
            detalle = self.env._('Las campañas salen de %s.', correo)
            pasos = [
                self.env._('En Resend › Domains, abre %s › Configuration › Enable tracking metrics.', dominio),
                self.env._('Escribe «links» como subdominio, enciende aperturas y clics y guárdalo.'),
                self.env._('Copia el CNAME que te da Resend en Cloudflare › DNS con la nube gris («DNS only») y, '
                           'cuando Resend lo marque verificado, toca «Revisar ahora».'),
            ]
        return {
            'tipo': 'sin_seguimiento',
            'titulo': self.env._('Resend no está contando %(que)s de este remitente: %(consecuencia)s', que=que,
                                 consecuencia=consecuencia),
            'detalle': detalle,
            'pasos_titulo': self.env._('Cómo encenderlo:'),
            'pasos': pasos,
        }

    @api.model
    def _hace_rato(self, momento):
        segundos = (fields.Datetime.now() - momento).total_seconds()
        if segundos < 90:
            return self.env._('hace un momento')
        if segundos < 3600:
            return self.env._('hace %s min', int(segundos // 60))
        if segundos < 86400:
            return self.env._('hace %s h', int(segundos // 3600))
        return self.env._('el %s', self._fecha_texto(self._dia_panama(momento)))

    @api.model
    def _remitente_para_pantalla(self):
        """El remitente, quién lo cambia, lo último que dijo Resend y el aviso. Solo lee lo guardado (nunca llama a
        Resend) y nunca falla por el aviso."""
        config = self.env['dcasa.correo'].sudo()._config()
        puede_revisar = self._puede_revisar_remitente()
        revision = self._revision_remitente() if puede_revisar else None
        aviso, nota, texto = None, '', ''
        try:
            aviso = self._aviso_remitente(revision)
        except Exception:   # noqa: BLE001 — un error del aviso nunca tumba la pantalla
            _logger.warning('DCASA_CAMILA no se pudo armar el aviso del remitente', exc_info=True)
        if puede_revisar:
            if not revision:
                texto = self.env._('Todavía no se ha revisado en Resend.')
            else:
                momento = fields.Datetime.to_datetime(revision['en'])
                texto = self.env._('Revisado en Resend %s.', self._hace_rato(momento))
                if revision.get('resultado') == 'error':
                    nota = self.env._('No se pudo revisar el remitente en Resend (%s). Se vuelve a intentar sola cada '
                                      'hora.', revision.get('error') or self.env._('sin detalle'))
        correo = self._remitente_campanas()
        return {
            'correo': correo,
            'visible': f"{config['nombre']} <{correo}>",
            'propio': self._remitente_propio(),
            'transaccional': config['remitente'],
            'responder_a': config['responder_a'],
            'puede_cambiar': self._ve_dinero(),
            'puede_revisar': puede_revisar,
            'revision': texto,
            'nota': nota,
            'aviso': aviso,
        }


class DcasaCorreo(models.AbstractModel):
    _inherit = 'dcasa.correo'

    @api.model
    def _sesion(self):
        """«Enviarme una prueba» sale del remitente de las campañas: solo con la marca de Camila en el contexto (un
        objeto de Python, ver ``RemitentePrueba``). Cualquier otro correo sale del remitente de siempre."""
        sesion = super()._sesion()
        marca = self.env.context.get(MARCA_PRUEBA)
        correo = correo_valido(marca.correo) if isinstance(marca, RemitentePrueba) else None
        if correo:
            sesion.remitente = sesion.smtp_from = correo
        return sesion
