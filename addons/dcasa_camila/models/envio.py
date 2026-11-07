"""Camila: la sincronización con Resend, el envío, la prueba, los resultados, el enlace «Sí, quiero» y los crones.

* **Varias campañas, un tope por cliente** (etapa 2, decisión de la dueña, 2026-11-06): cada campaña tiene su público
  (``publico.py``) y a un mismo correo le llega como mucho un correo de campaña cada 15 días. El servidor lo cumple al
  enviar (también por RPC) con el registro ``dcasa.camila.destinatario``, que se escribe ANTES de mandar (y se borra si
  Resend no llegó a mandarlo).
* **Un solo segmento de envío, reusado** (el plan gratis de Resend tiene 3 segmentos): antes de mandar una campaña el
  segmento queda EXACTAMENTE con sus destinatarios: sale por el id del contacto todo el que no va (también correos que
  Odoo no sabe leer) y entran los que faltan; justo antes de mandar se vuelve a listar y, si queda alguien suscrito que
  no va, no sale. Se envía de una campaña a la vez: un candado de SESIÓN de la base (``pg_try_advisory_lock``, que
  aguanta los COMMIT a mitad de la petición y se suelta al terminar) más «otra aprobada enviándose» y, si el
  *broadcast* de cualquier otra campaña todavía está saliendo en Resend, se espera.
* **Las bajas** (cada hora y antes de cada envío, ``_sincronizar``): se leen TODOS los contactos de Resend; los dados de
  baja quedan con baja en todas las fichas con ese correo, y las bajas de Odoo suben a Resend (por id).
* **Al enviar, el servidor revisa todo** aunque llegue por RPC: el grupo, producción (``DCASA_ENTORNO=produccion``;
  staging nunca envía), la clave, los productos y precios de ahora (si cambió algo desde que la persona lo vio, no sale
  y se le muestra otra vez), el público con el permiso, la baja y el tope por cliente, y que las bajas se trajeron
  recién. Se confirma la base a mitad de la petición (como Sofía): un doble clic o dos personas a la vez no la mandan
  dos veces. Ningún error deja la campaña a medias; una «aprobada» que quedó trabada (Resend la canceló, quedó en
  borrador allá o nunca llegó) la descartan Gerencia o un administrador.
* **Un error de Camila o de Resend nunca hace fallar una venta, un pago ni el correo de una factura**: nada de esto
  corre dentro de esos flujos (el enlace del pie se arma en un savepoint y, si falla, el correo sale sin la línea).
"""
import hmac as hmac_py
import logging
import re
import time
from datetime import timedelta
from email.utils import formataddr

import psycopg2
from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models import transaccion
from odoo.addons.dcasa_correo.models.correo import correo_valido, motivo_legible
from odoo.addons.dcasa_correo.models.resend import remitente_visible
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL, email_normalize
from odoo.tools.misc import hmac as hmac_odoo

from . import reglas as R
from . import remitente as REM
from . import resend_campanas as RC
from .campana import ABIERTAS

_logger = logging.getLogger(__name__)

P_SEGMENTO = 'dcasa_camila.segmento_id'
NOMBRE_SEGMENTO = "D'CASA: campaña que sale (Odoo)"
MAX_SUBIR_AL_ENVIAR = 300      # contactos que entran al segmento en un clic «Enviar» (el resto, al reintentar)
MAX_SACAR_AL_ENVIAR = 300      # y los que salen: una vuelta corta no pasa la ventana de «enviándose»
MINUTOS_ENVIANDO = 10          # «ya se está enviando» (otra persona o un doble clic)
LLAVE_ENVIO = 7_412_043_115    # candado de SESIÓN de la base: una campaña a la vez toca el segmento de envío
DIAS_SALIENDO = 3              # cuánto se mira atrás por si el broadcast anterior todavía está saliendo en Resend
ESTADOS_SALIENDO = ('scheduled', 'queued')
HORAS_RESULTADOS = 6
DIAS_RESULTADOS = 30
TIPOS_RESEND = (('entregados', 'delivered'), ('abiertos', 'opened'), ('clics', 'clicked'), ('bajas', 'unsubscribed'))
# El enlace «Sí, quiero» del pie de la factura y de la bienvenida: firmado con el secreto de la base (HMAC).
ALCANCE_FIRMA = 'dcasa_camila_novedades'
ORIGEN_DEL_CODIGO = {'f': 'factura', 'b': 'bienvenida'}
CODIGO_DEL_ORIGEN = {origen: codigo for codigo, origen in ORIGEN_DEL_CODIGO.items()}
VIGENCIA_ENLACE = timedelta(days=400)
# ficha.origen.momento.firma, solo ASCII (``[0-9]``, no ``\d``: «²» o «１» no son dígitos aquí). La ficha cabe en un
# entero de PostgreSQL y el momento son 10 cifras de segundos.
TOKEN = re.compile(r'([1-9][0-9]{0,8})\.([fb])\.([0-9]{10})\.([0-9a-f]{40})')
# El interruptor de Gerencia de la línea del pie (encendido de fábrica: la dueña la quiere).
P_ENLACE_PIE = 'dcasa_camila.enlace_pie'
# «Enviarme una prueba» sale por los correos de siempre (el mismo cupo diario que las facturas): con tope.
MINUTOS_ENTRE_PRUEBAS = 2
MAX_PRUEBAS_24H = 10
# Cuántos días Juan sabe que el cliente llegó por una campaña (después ya es una conversación como cualquier otra).
DIAS_CONTEXTO_JUAN = 3


class DcasaCamila(models.AbstractModel):
    _inherit = 'dcasa.camila'

    # ------------------------------------------------------------------
    # Resend: las bajas y el segmento de envío
    # ------------------------------------------------------------------

    @api.model
    def _cliente(self):
        return RC.ClienteCampanas(self._clave(), pausa=RC.PAUSA)

    @api.model
    def _segmento(self, cliente):
        """El segmento de envío (uno solo, reusado: ver el docstring del módulo)."""
        ICP = self.env['ir.config_parameter'].sudo()
        segmento = (ICP.get_param(P_SEGMENTO) or '').strip()
        if not segmento:
            segmento = cliente.buscar_o_crear_segmento(NOMBRE_SEGMENTO)
            ICP.set_param(P_SEGMENTO, segmento)
        return segmento

    @api.model
    def _claves_correo(self, texto):
        """Las formas de un correo con las que Odoo lo busca (la estricta de Camila y la ``email_normalized``)."""
        return {clave for clave in (correo_valido(texto), email_normalize(texto or '')) if clave}

    @api.model
    def _anotar_bajas_de_resend(self, correos):
        """Las bajas que dio Resend quedan en TODAS las fichas con esos correos (la baja es final)."""
        claves = sorted({clave for correo in correos for clave in self._claves_correo(correo)})
        if not claves:
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        return Partner.search([('email_normalized', 'in', claves)]).commercial_partner_id._dcasa_promos_baja('correo')

    @api.model
    def _sincronizar(self, cliente=None):
        """Las bajas, en los dos sentidos (cada hora y antes de cada envío). Devuelve ``{bajas, subidas}``.

        1. Lee TODOS los contactos de Resend (``GET /contacts``): cada uno dado de baja queda con baja en las fichas con
           ese correo (final).
        2. Un contacto suscrito cuyo correo se dio de baja en CUALQUIER ficha de Odoo queda dado de baja en Resend, por
           su id (por el correo, otra grafía en Resend daba 404 y la baja se perdía)."""
        cliente = cliente or self._cliente()
        contactos = cliente.contactos()
        bajas = self._anotar_bajas_de_resend(c.get('email') for c in contactos if c.get('unsubscribed'))
        bloqueos = self.env['res.partner'].sudo()._dcasa_promos_bloqueos_por_correo()
        subidas = 0
        for contacto in contactos:
            if not contacto.get('unsubscribed') and any(
                    bloqueos.get(clave) == 'baja' for clave in self._claves_correo(contacto.get('email'))):
                cliente.dar_de_baja(contacto.get('id') or contacto.get('email'))
                subidas += 1
        _logger.info('DCASA_CAMILA bajas: %s nuevas desde Resend, %s subidas a Resend', len(bajas), subidas)
        return {'bajas': len(bajas), 'subidas': subidas}

    @api.model
    def _preparar_segmento(self, cliente, segmento, destinatarios):
        """Deja el segmento de envío con los destinatarios de ESTA campaña: saca por su id a todo el que no va (también
        correos que Odoo no sabe leer y los dados de baja) y agrega a los que faltan (solo el correo: nada más de la
        persona). Por tandas (``MAX_SACAR_AL_ENVIAR`` salidas y ``MAX_SUBIR_AL_ENVIAR`` entradas por vuelta), para que
        una vuelta no pase la ventana de «enviándose». Devuelve ``(por_sacar, por_agregar)``."""
        presentes, sobran = set(), []
        for contacto in cliente.contactos_del_segmento(segmento):
            correo = correo_valido(contacto.get('email'))
            if correo in destinatarios and not contacto.get('unsubscribed') and correo not in presentes:
                presentes.add(correo)
                continue
            sobran.append(contacto.get('id') or contacto.get('email'))
        for contacto in sobran[:MAX_SACAR_AL_ENVIAR]:
            cliente.sacar_del_segmento(contacto, segmento)
        faltan = [correo for correo in destinatarios if correo not in presentes]
        if len(sobran) > MAX_SACAR_AL_ENVIAR:
            return len(sobran) - MAX_SACAR_AL_ENVIAR, len(faltan)
        for correo in faltan[:MAX_SUBIR_AL_ENVIAR]:
            cliente.agregar_contacto(correo, None, segmento)
        return 0, max(0, len(faltan) - MAX_SUBIR_AL_ENVIAR)

    @api.model
    def _revisar_segmento(self, cliente, segmento, destinatarios):
        """``(presentes, sobran)``: los destinatarios que están suscritos en el segmento y cuántos suscritos sobran."""
        presentes, sobran = set(), 0
        for contacto in cliente.contactos_del_segmento(segmento):
            if contacto.get('unsubscribed'):
                continue
            correo = correo_valido(contacto.get('email'))
            if correo in destinatarios:
                presentes.add(correo)
            else:
                sobran += 1
        return presentes, sobran

    @api.model
    def _campana_saliendo(self, campana, cliente):
        """Otra campaña cuyo *broadcast* todavía está saliendo en Resend (el segmento no se toca hasta que termine).
        Se miran TODAS las que tienen broadcast en la ventana (no solo las de id más alto: una que se aprobó antes pudo
        salir después), las más recientes primero. Un broadcast que ya no existe en Resend no está saliendo."""
        desde = fields.Datetime.now() - timedelta(days=DIAS_SALIENDO)
        otras = self.env['dcasa.camila.campana'].sudo().search([
            ('id', '!=', campana.id), ('resend_broadcast_id', '!=', False), ('estado', 'in', ('aprobada', 'enviada')),
            '|', ('enviada_en', '=', False), ('enviada_en', '>=', desde)],
            order='enviada_en desc, aprobada_en desc, id desc')
        for otra in otras:
            if cliente.estado_broadcast(otra.resend_broadcast_id) in ESTADOS_SALIENDO:
                return otra
        return otras.browse()

    @api.model
    def _registrar_destinatarios(self, campana, destinatarios):
        """El registro del tope por cliente: a quién le sale esta campaña (se escribe ANTES de mandar, con TODOS los
        que se dejaron en el segmento). Si ya se llamó a «send» en otra vuelta, lo de entonces se queda y solo se suma
        lo nuevo (a alguno ya le pudo llegar)."""
        Destinatario = self.env['dcasa.camila.destinatario'].sudo()
        anteriores = Destinatario.search([('campana_id', '=', campana.id)])
        if campana.envio_intentado:
            ya_estan = set(anteriores.mapped('correo'))
            destinatarios = {c: f for c, f in destinatarios.items() if c not in ya_estan}
        else:
            anteriores.unlink()
        ahora = fields.Datetime.now()
        Destinatario.create([{'campana_id': campana.id, 'correo': correo, 'partner_id': ficha.id if ficha else False,
                              'enviada_en': ahora} for correo, ficha in destinatarios.items()])

    @api.model
    def _soltar_destinatarios(self, campana):
        """El registro se borra SOLO si nunca se llamó a «send» (``envio_intentado``): si se llamó, pudo salir aunque
        Resend contestara un error o su estado todavía diga «draft», y un «canceled» puede llegar a mitad del envío.
        Mejor no mandarles otra que mandarles dos."""
        if campana.envio_intentado:
            return
        self.env['dcasa.camila.destinatario'].sudo().search([('campana_id', '=', campana.id)]).unlink()

    @api.model
    def _registrar_lo_que_hay_en_el_segmento(self, campana, cliente, segmento):
        """Una campaña que ya salió en Resend y no tiene registro (p. ej. aprobada antes de este arreglo): cuenta para
        el tope todo el que está suscrito en el segmento de envío (lo conservador)."""
        permitidos = self.env['res.partner'].sudo()._dcasa_promos_con_permiso()
        correos = {correo_valido(c.get('email')) for c in cliente.contactos_del_segmento(segmento)
                   if not c.get('unsubscribed')}
        self._registrar_destinatarios(campana, {c: permitidos.get(c) for c in correos if c})

    # ------------------------------------------------------------------
    # Enviar (al tocar «Enviar a N clientes»)
    # ------------------------------------------------------------------

    @api.model
    def _bloquear(self, campana_id):
        """La campaña pedida, BLOQUEADA para que nadie la envíe ni la edite a la vez."""
        if isinstance(campana_id, bool) or not isinstance(campana_id, int) or campana_id < 1:
            raise UserError(self.env._('Esa campaña no es válida.'))
        campana = self.env['dcasa.camila.campana'].sudo().browse(campana_id).exists()
        if not campana:
            raise UserError(self.env._('Esa campaña ya no existe.'))
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(SQL('SELECT id FROM dcasa_camila_campana WHERE id = %s FOR UPDATE NOWAIT',
                                        campana.id))
        except LockNotAvailable:
            raise UserError(self.env._('Alguien más está trabajando en esta campaña en este momento.')) from None
        campana.invalidate_recordset()
        return campana

    @api.model
    def _tomar_turno_de_envio(self, campana):
        """Una campaña a la vez toca el segmento de envío. El candado es de SESIÓN (``pg_try_advisory_lock``): aguanta
        los COMMIT a mitad de la petición (el de transacción se soltaba con el primero) y lo suelta
        ``_soltar_turno_de_envio`` al terminar; si el trabajador muere, PostgreSQL lo suelta al cerrar la conexión.
        Además, ninguna otra «aprobada» enviándose en los últimos minutos (se vuelve a mirar después de confirmar
        «aprobada», con la foto nueva de la base: ``_otra_enviandose``)."""
        self.env.cr.execute(SQL('SELECT pg_try_advisory_lock(%s)', LLAVE_ENVIO))
        if not self.env.cr.fetchone()[0]:
            raise UserError(self._mensaje_otra_enviandose())
        try:
            if self._otra_enviandose(campana):
                raise UserError(self._mensaje_otra_enviandose())
        except Exception:
            self._soltar_turno_de_envio()
            raise

    @api.model
    def _mensaje_otra_enviandose(self):
        return self.env._('Otra campaña se está enviando en este momento: espera un minuto y vuelve a tocar «Enviar».')

    @api.model
    def _otra_enviandose(self, campana):
        return bool(self.env['dcasa.camila.campana'].sudo().search([
            ('id', '!=', campana.id), ('estado', '=', 'aprobada'),
            ('enviando_desde', '>=', fields.Datetime.now() - timedelta(minutes=MINUTOS_ENVIANDO))], limit=1))

    @api.model
    def _soltar_turno_de_envio(self):
        """Suelta el candado de sesión (siempre, en un ``finally``: si no, la conexión vuelve al grupo de Odoo con el
        candado tomado y ninguna campaña podría salir). El candado de sesión no se deshace con un ROLLBACK."""
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(SQL('SELECT pg_advisory_unlock(%s)', LLAVE_ENVIO))
        except psycopg2.Error:
            # La transacción quedó con error: se deshace (Odoo la iba a deshacer igual) y se suelta.
            self.env.cr.rollback()
            self.env.cr.execute(SQL('SELECT pg_advisory_unlock(%s)', LLAVE_ENVIO))

    @api.model
    def _enviar(self, campana_id, huella):
        campana = self._bloquear(campana_id)
        if campana.estado == 'enviada':
            fecha = self._fecha_texto(self._dia_panama(campana.enviada_en))
            return {'ok': True, 'ya_estaba': True, 'mensaje': self.env._('Esa campaña ya salió el %s.', fecha)}
        self._tomar_turno_de_envio(campana)
        try:
            return self._enviar_con_turno(campana, huella)
        finally:
            self._soltar_turno_de_envio()

    @api.model
    def _enviar_con_turno(self, campana, huella):
        cambio = self._revisar_antes_de_enviar(campana, huella)
        if cambio:
            return cambio
        ahora = fields.Datetime.now()
        campana.write({'estado': 'aprobada', 'aprobada_por': self.env.uid, 'aprobada_en': ahora,
                       'enviando_desde': ahora, 'error': False})
        transaccion.confirmar(self.env)   # aprobada y «enviándose» para todos antes de hablar con Resend
        try:
            destinatarios = self._mandar_a_resend(campana)
        except Exception as error:   # noqa: BLE001 — ningún error deja la campaña «enviándose» a medias
            if isinstance(error, RC.ErrorResend):
                mensaje = error.mensaje
                _logger.warning('DCASA_CAMILA no se pudo enviar la campaña %s: %s', campana.id, mensaje)
            else:
                transaccion.deshacer(self.env)   # lo de esta vuelta; lo ya confirmado (el broadcast creado) queda
                self.env.invalidate_all()
                mensaje = self.env._('algo falló al hablar con Resend (%s). Avísale a quien administra el sistema.',
                                     type(error).__name__)
                _logger.exception('DCASA_CAMILA error inesperado al enviar la campaña %s', campana.id)
            self._soltar_destinatarios(campana)
            valores = {'error': mensaje[:300], 'enviando_desde': False}
            if not campana.resend_broadcast_id:
                valores['estado'] = 'borrador'   # nada quedó en Resend: se puede editar y volver a intentar
            campana.write(valores)
            transaccion.confirmar(self.env)
            return {'ok': False, 'mensaje': self.env._('No salió: %s', mensaje)}
        campana.write({'estado': 'enviada', 'enviada_en': fields.Datetime.now(), 'destinatarios': destinatarios,
                       'enviando_desde': False, 'error': False})
        transaccion.confirmar(self.env)   # «enviada» para todos ANTES de soltar el turno
        _logger.info('DCASA_CAMILA campaña %s enviada a %s contactos', campana.id, destinatarios)
        return {'ok': True, 'mensaje': self.env._('Listo: la campaña salió a %s clientes.', destinatarios)}

    @api.model
    def _revisar_antes_de_enviar(self, campana, huella):
        """Todo lo que el servidor revisa antes de aprobar (falla con el motivo en palabras sencillas). Devuelve un
        resultado «cambió algo» si los precios o los productos de ahora no son los que vio la persona."""
        if campana.estado not in ABIERTAS:
            raise UserError(self.env._('Esa campaña se descartó: arma otra.'))
        if campana.estado == 'aprobada' and campana.enviando_desde \
                and fields.Datetime.now() - campana.enviando_desde < timedelta(minutes=MINUTOS_ENVIANDO):
            raise UserError(self.env._('Esta campaña ya se está enviando: espera un momento y vuelve a mirar.'))
        # El dominio del remitente en Resend (``remitente.py``): si lo guardado no deja enviar o nunca se revisó, se
        # mira otra vez (lo pudieron verificar recién). Si se SABE que no está verificado, no sale: se devuelve el
        # motivo (sin excepción, para que quede guardado lo que dijo Resend y la pantalla muestre el aviso). Con un
        # broadcast ya creado (un reintento), el remitente ya quedó en Resend (``_revisar_broadcast_anterior``).
        if not campana.resend_broadcast_id:
            self._revisar_remitente_sin_fallar('enviar')
            if self._remitente_no_verificado():
                return {'ok': False, 'mensaje': self._mensaje_remitente_no_verificado()}
        bloqueos = self._bloqueos(campana)
        if bloqueos:
            raise UserError(bloqueos[0])
        if campana.resend_broadcast_id and self._revisar_broadcast_anterior(campana) in RC.ESTADOS_YA_SALIO:
            return None   # ya salió en Resend: solo falta anotarla (``_mandar_a_resend``)
        if not campana.resend_broadcast_id:
            # Lo de ahora: precios, fotos y existencias. Si cambió algo desde que la persona lo vio, no sale.
            quitados = self._poner_al_dia(campana)
            self._guardar_html(campana)
            if not campana.linea_ids:
                raise UserError(self.env._('Ya no queda ningún producto que se pueda ofrecer (agotados o sin '
                                           'publicar): vuelve a armarla.'))
            if campana.huella != (huella or ''):
                mensaje = self.env._('Cambió algo desde que la viste (un precio, una foto o un producto agotado): '
                                     'revisa la vista previa otra vez antes de enviar.')
                if quitados:
                    mensaje += ' ' + self.env._('Salió de la campaña: %s.', ', '.join(quitados))
                return {'ok': False, 'cambio': True, 'mensaje': mensaje}
        Partner = self.env['res.partner'].sudo()
        Partner._dcasa_promos_de_sofia()
        if not Partner._dcasa_promos_con_permiso():
            raise UserError(self._bloqueos(campana, con_permiso=0)[-1])
        publico = self._publico(campana.publico, campana=campana)
        if not publico['total']:
            raise UserError(self._bloqueos(campana, publico=publico)[-1])
        return None

    @api.model
    def _revisar_broadcast_anterior(self, campana):
        """El broadcast que quedó de una vuelta anterior («Reintentar el envío»). Devuelve su estado en Resend.

        * No existe (lo borraron en Resend): se olvida y se arma otro; el registro del tope NO se suelta.
        * En borrador: si los precios, fotos o existencias de hoy cambian el correo (o los precios no son de hoy), se
          borra allá y se olvida: la campaña vuelve a pasar por la huella y nunca sale con el HTML viejo.
        En los dos casos vuelve a borrador (se puede revisar y editar otra vez)."""
        cliente = self._cliente()
        try:
            estado = cliente.estado_broadcast(campana.resend_broadcast_id)
            if estado == RC.NO_EXISTE:
                campana.write({'resend_broadcast_id': False, 'estado': 'borrador'})
            elif estado == 'draft':
                antes = campana.huella
                self._poner_al_dia(campana)
                self._guardar_html(campana)
                if campana.huella != antes:
                    cliente.borrar_broadcast(campana.resend_broadcast_id)
                    campana.write({'resend_broadcast_id': False, 'estado': 'borrador'})
        except RC.ErrorResend as error:
            raise UserError(self.env._('No se pudo revisar la campaña en Resend: %s', error.mensaje)) from None
        return estado

    @api.model
    def _mandar_a_resend(self, campana):
        """Trae las bajas, deja el segmento de envío con los destinatarios de esta campaña (y lo revisa otra vez),
        registra a quién le sale, crea el broadcast (una sola vez) y lo manda si sigue en borrador. Devuelve a cuántos
        clientes salió."""
        cliente = self._cliente()
        segmento = self._segmento(cliente)
        estado = cliente.estado_broadcast(campana.resend_broadcast_id) if campana.resend_broadcast_id else None
        if estado == RC.NO_EXISTE:   # lo borraron en Resend: se arma otro (el registro del tope se queda)
            campana.write({'resend_broadcast_id': False})
            estado = None
        if estado in RC.ESTADOS_YA_SALIO:   # ya salió (p. ej. un reintento): que quede en el registro del tope
            if not campana.destinatario_ids:
                self._registrar_lo_que_hay_en_el_segmento(campana, cliente, segmento)
            return len(campana.destinatario_ids) or campana.destinatarios
        if estado not in (None, 'draft'):
            raise RC.ErrorResend(self.env._('En Resend la campaña quedó «%s»: revísala allá antes de reintentar.',
                                            estado))
        if self._otra_enviandose(campana):   # con la foto nueva de la base (después de confirmar «aprobada»)
            raise RC.ErrorResend(self._mensaje_otra_enviandose(), temporal=True)
        saliendo = self._campana_saliendo(campana, cliente)
        if saliendo:
            raise RC.ErrorResend(self.env._('La campaña «%s» todavía está saliendo en Resend: prueba otra vez en unos '
                                            'minutos.', saliendo.name), temporal=True)
        self._sincronizar(cliente)
        destinatarios = self._publico(campana.publico, campana=campana)['incluidos']
        if not destinatarios:
            raise RC.ErrorResend(self.env._('Después de traer las bajas, nadie de este público puede recibirla: no '
                                            'salió nada.'))
        por_sacar, faltan = self._preparar_segmento(cliente, segmento, destinatarios)
        if por_sacar:
            raise RC.ErrorResend(self.env._('Todavía quedan %s contactos por sacar del segmento de Resend: toca '
                                            '«Enviar» otra vez en un minuto (se siguen sacando).', por_sacar),
                                 temporal=True)
        if faltan:
            raise RC.ErrorResend(self.env._('Todavía faltan %s clientes por subir a Resend: toca «Enviar» otra vez en '
                                            'un minuto (se siguen subiendo).', faltan), temporal=True)
        campana.write({'enviando_desde': fields.Datetime.now()})   # la vuelta sigue viva
        transaccion.confirmar(self.env)
        # La última revisión: si en el segmento queda alguien suscrito que no va en esta campaña, no sale.
        presentes, sobran = self._revisar_segmento(cliente, segmento, destinatarios)
        if sobran:
            raise RC.ErrorResend(self.env._(
                'En el segmento de Resend quedan %s contactos que no van en esta campaña: no salió. Prueba otra vez en '
                'unos minutos; si sigue, revisa el segmento en Resend.', sobran))
        if not presentes:
            raise RC.ErrorResend(self.env._('Resend no tiene a ninguno de los destinatarios en el segmento: no salió.'))
        if not campana.resend_broadcast_id:
            # El remitente de las campañas (``remitente.py``; vacío = el de las facturas) con el nombre y la dirección
            # de respuesta de siempre: las respuestas de los clientes llegan a donde llegaban.
            config = self.env['dcasa.correo'].sudo()._config()
            broadcast = cliente.crear_broadcast(
                segmento, remitente_visible(config['nombre'], self._remitente_campanas()), campana.asunto,
                self._html(campana, para_resend=True), responder_a=config['responder_a'],
                nombre=f'{campana.name} ({campana.marca})')
            campana.write({'resend_broadcast_id': broadcast})
            transaccion.confirmar(self.env)
        # El tope por cliente queda escrito ANTES de mandar, con TODOS los que se dejaron en el segmento (un listado
        # de Resend que tarda no deja a nadie sin registro), y «se llamó a send» también: desde ahí el registro ya no
        # se suelta (pudo salir aunque Resend conteste un error).
        self._registrar_destinatarios(campana, destinatarios)
        campana.write({'envio_intentado': fields.Datetime.now()})
        transaccion.confirmar(self.env)
        cliente.enviar_broadcast(campana.resend_broadcast_id)
        return len(destinatarios)

    # ------------------------------------------------------------------
    # Descartar (también una «aprobada» que quedó trabada)
    # ------------------------------------------------------------------

    @api.model
    def _descartar(self, campana):
        """Descarta la campaña: queda en el historial como cancelada y ya se puede armar otra.

        * Un borrador (nada en Resend): cualquiera del equipo de marketing.
        * Una «aprobada» que quedó trabada (no puede salir y bloquea a las demás por la regla de una abierta): solo
          Gerencia o un administrador, y solo si no salió ni va a salir: sin broadcast y pasada la ventana de envío,
          o con el broadcast «canceled» o «draft» en Resend (el borrador se borra allá para que nadie lo mande)."""
        if campana.estado not in ABIERTAS:
            raise UserError(self.env._('Esa campaña ya no se puede descartar (ya salió o ya se descartó).'))
        if campana.estado == 'aprobada' and not campana.resend_broadcast_id and campana.enviando_desde \
                and fields.Datetime.now() - campana.enviando_desde < timedelta(minutes=MINUTOS_ENVIANDO):
            raise UserError(self.env._('Esta campaña se está enviando en este momento: espera unos minutos y vuelve '
                                       'a mirar.'))
        if campana.estado == 'borrador' and not campana.resend_broadcast_id:
            return self._cancelar(campana)
        if not self._ve_dinero():
            raise UserError(self.env._('Esta campaña ya se aprobó para salir: solo Gerencia o un administrador la '
                                       'pueden descartar.'))
        if campana.resend_broadcast_id:
            try:
                cliente = self._cliente()
                estado = cliente.estado_broadcast(campana.resend_broadcast_id)
                if estado == 'draft':
                    cliente.borrar_broadcast(campana.resend_broadcast_id)
            except RC.ErrorResend as error:
                raise UserError(self.env._('No se pudo revisar la campaña en Resend: %s', error.mensaje)) from None
            if estado not in ('draft', 'canceled', RC.NO_EXISTE):
                raise UserError(self.env._('En Resend esta campaña está «%s»: ya salió o va a salir, no se descarta.',
                                           estado))
        return self._cancelar(campana)

    @api.model
    def _cancelar(self, campana):
        campana.write({'estado': 'cancelada', 'cancelada_por': self.env.uid, 'enviando_desde': False})
        return campana

    # ------------------------------------------------------------------
    # La prueba (solo al correo de quien aprueba, por el camino de siempre)
    # ------------------------------------------------------------------

    @api.model
    def _enviar_prueba(self, campana_id):
        """Manda la campaña al correo de quien la pide, ahora, por los correos de siempre (clase «prueba» de
        ``politica.py``: solo sale a correos del equipo). Sin el enlace de baja de Resend (va solo en la real).

        Con tope: sale por la misma clave y el mismo cupo diario que las facturas, así que una prueba cada
        ``MINUTOS_ENTRE_PRUEBAS`` minutos por persona y ``MAX_PRUEBAS_24H`` en 24 horas."""
        from odoo.addons.base.models.ir_mail_server import MailDeliveryException

        campana = self._bloquear(campana_id)
        correo = self.env['dcasa.correo'].sudo()
        if not correo._hay_clave():
            raise UserError(self.env._(
                'Todavía no hay clave de Resend para los correos (RESEND_API_KEY): la prueba sale por ese camino. '
                'Mira docs/CORREO.md.'))
        usuario = self.env.user
        destino = correo_valido(usuario.email)
        if not destino:
            raise UserError(self.env._('Tu usuario no tiene un correo bien escrito: escríbelo en tu perfil (Mis '
                                       'preferencias) y vuelve a probar.'))
        Prueba = self.env['dcasa.camila.prueba'].sudo()
        ahora = fields.Datetime.now()
        ultima = Prueba.search([('usuario_id', '=', usuario.id)], order='enviada_en desc, id desc', limit=1)
        if ultima and ahora - ultima.enviada_en < timedelta(minutes=MINUTOS_ENTRE_PRUEBAS):
            raise UserError(self.env._('Te mandé una prueba hace un momento: espera %s minutos para la siguiente.',
                                       MINUTOS_ENTRE_PRUEBAS))
        if Prueba.search_count([('usuario_id', '=', usuario.id),
                                ('enviada_en', '>=', ahora - timedelta(hours=24))]) >= MAX_PRUEBAS_24H:
            raise UserError(self.env._('Ya te mandé %s pruebas en las últimas 24 horas: es el máximo (salen por el '
                                       'mismo cupo que los correos de las facturas).', MAX_PRUEBAS_24H))
        # Sale del remitente de las campañas (``remitente.py``), como la de verdad, con el nombre y la dirección de
        # respuesta de siempre. La marca va en el contexto de ESTE envío (un objeto de Python: no viaja por RPC).
        remitente = self._remitente_campanas()
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.env._('[Prueba] %s', campana.asunto or ''),
            'body_html': self._html(campana, prueba=True),
            'email_to': destino,
            'email_from': formataddr((correo._config()['nombre'], remitente)),
            'headers': repr({'X-Dcasa-Correo': 'prueba'}),
            'model': 'res.users',
            'res_id': usuario.id,
            'auto_delete': True,
        })
        try:
            mail.with_context(**{REM.MARCA_PRUEBA: REM.RemitentePrueba(remitente)}).send(raise_exception=True)
        except MailDeliveryException as error:
            raise UserError(self.env._('No salió la prueba: %s', motivo_legible(error, correo._clave()))) from None
        Prueba.create({'usuario_id': usuario.id, 'campana_id': campana.id, 'enviada_en': ahora})
        campana.write({'prueba_a': destino, 'prueba_en': fields.Datetime.now()})
        return destino

    # ------------------------------------------------------------------
    # Resultados por campaña
    # ------------------------------------------------------------------

    @api.model
    def _ventas(self, campana):
        """``(facturas, monto sin ITBMS)``: facturas PAGADAS de los clientes que llegaron con la marca de la campaña,
        con la misma ventana que las ventas atribuidas de Conversaciones (el chat en los 30 días antes de la factura,
        días de Panamá)."""
        from odoo.addons.dcasa_conversaciones.models.panel_calculos import VENTANA_DE_ATRIBUCION_DIAS

        self.env.cr.execute(SQL("""
            WITH x AS (
                SELECT p.commercial_partner_id AS cliente, MIN(l.ts) AS llego
                  FROM dcasa_camila_llegada l
                  JOIN res_partner p ON p.id = l.partner_id
                 WHERE l.campana_id = %(campana)s
              GROUP BY p.commercial_partner_id)
            SELECT COUNT(DISTINCT m.id), COALESCE(SUM(m.amount_untaxed_signed), 0)
              FROM account_move m
              JOIN x ON x.cliente = m.commercial_partner_id
             WHERE m.move_type = 'out_invoice' AND m.state = 'posted' AND m.payment_state IN ('paid', 'in_payment')
               AND m.company_id = %(compania)s
               AND x.llego >= (m.invoice_date - %(ventana)s)::timestamp + interval '5 hours'
               AND x.llego < (m.invoice_date + 1)::timestamp + interval '5 hours'""",
                                campana=campana.id, compania=self.env.company.id,
                                ventana=VENTANA_DE_ATRIBUCION_DIAS))
        facturas, monto = self.env.cr.fetchone()
        return int(facturas or 0), round(float(monto or 0.0), 2)

    @api.model
    def _ventas_web(self, campana):
        """``(pedidos, monto sin ITBMS)``: pedidos confirmados de la tienda en línea que llegaron con el UTM de la
        campaña (``utm_campaign=DCN-0007``: Odoo lo guarda en ``campaign_id`` del pedido)."""
        pedidos = self.env['sale.order'].sudo().search([
            ('campaign_id.name', '=ilike', R.marca(campana.id)), ('state', '=', 'sale')])
        return len(pedidos), round(sum(pedidos.mapped('amount_untaxed')), 2)

    @api.model
    def _resultados(self, campana):
        facturas, monto = self._ventas(campana)
        pedidos_web, monto_web = self._ventas_web(campana)
        moneda = self.env.company.currency_id
        return {
            'enviados': campana.destinatarios,
            'chats': len(campana.llegada_ids),
            'ventas': facturas,
            'monto': self.env['dcasa.correo']._monto(monto, moneda) if self._ve_dinero() else None,
            'web': pedidos_web,
            'monto_web': self.env['dcasa.correo']._monto(monto_web, moneda) if self._ve_dinero() else None,
            'resend': {'entregados': campana.entregados, 'abiertos': campana.abiertos, 'clics': campana.clics,
                       'bajas': campana.bajas, 'al': self._fecha_texto(self._dia_panama(campana.resultados_en))}
            if campana.resultados_en else None,
        }

    @api.model
    def _actualizar_resultados(self, campana):
        """Entregados, aperturas, clics y bajas de Resend (``GET /broadcasts/{id}/recipients``). Los que se dieron de
        baja con el enlace de esta campaña quedan también con la baja en Odoo (por si el segmento ya no los lista)."""
        if not (campana.resend_broadcast_id and self._clave() and self._entorno() == 'produccion'):
            return False
        cliente = self._cliente()
        valores = {}
        for campo, tipo in TIPOS_RESEND:
            filas = cliente.destinatarios(campana.resend_broadcast_id, tipo)
            valores[campo] = len(filas)
            if tipo == 'unsubscribed':
                self._anotar_bajas_de_resend(fila.get('email') for fila in filas)
        campana.sudo().write(dict(valores, resultados_en=fields.Datetime.now()))
        return True

    # ------------------------------------------------------------------
    # Los chats que llegaron con la marca de la campaña
    # ------------------------------------------------------------------

    @api.model
    def _anotar_llegada(self, conversacion, mensaje):
        """Si el PRIMER mensaje del cliente desde que salió la campaña trae su marca («Ref. DCN-0007»), cuenta ese chat
        una vez. La conversación de un cliente es una sola, de siempre: un cliente de antes que vuelve por el correo
        cuenta; una marca escrita después de otros mensajes, no."""
        numero = R.campana_de_la_marca(mensaje.texto)
        if not numero:
            return False
        campana = self.env['dcasa.camila.campana'].sudo().browse(numero).exists()
        desde = campana.enviada_en - timedelta(minutes=5) if campana and campana.enviada_en else None
        if not campana or campana.estado != 'enviada' or not desde or mensaje.ts < desde:
            return False
        antes = self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conversacion.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje'),
            ('id', '!=', mensaje.id), ('ts', '>=', desde), ('ts', '<=', mensaje.ts)])
        if antes.filtered(lambda m: m.ts < mensaje.ts or m.id < mensaje.id):
            return False
        Llegada = self.env['dcasa.camila.llegada'].sudo()
        if Llegada.search_count([('campana_id', '=', campana.id), ('conversacion_id', '=', conversacion.id)], limit=1):
            return False
        Llegada.create({'campana_id': campana.id, 'conversacion_id': conversacion.id,
                        'partner_id': conversacion.partner_id.commercial_partner_id.id or False,
                        'mensaje_id': mensaje.id, 'ts': mensaje.ts})
        # El origen «Correo» queda a la vista en la bandeja: la etiqueta «Vino del correo» en la conversación.
        etiqueta = self.env.ref('dcasa_camila.etiqueta_vino_del_correo', raise_if_not_found=False)
        if etiqueta and etiqueta not in conversacion.etiqueta_ids:
            conversacion.sudo().write({'etiqueta_ids': [(4, etiqueta.id)]})
        return True

    @api.model
    def _contexto_para_juan(self, conversacion):
        """Lo que Juan sabe de la campaña por la que llegó el cliente (decisión de la dueña, etapa 2): el asunto, cuándo
        salió y con qué productos, para atenderlo con eso («¡Qué bueno que viste nuestro correo!») sin repetirle el
        código. Solo los primeros días desde que llegó; ``None`` si no llegó por una campaña. Sin precios: si los
        pregunta, Juan los consulta con sus herramientas (los de hoy)."""
        desde = fields.Datetime.now() - timedelta(days=DIAS_CONTEXTO_JUAN)
        llegada = self.env['dcasa.camila.llegada'].sudo().search([
            ('conversacion_id', '=', conversacion.id), ('ts', '>=', desde)], order='ts desc, id desc', limit=1)
        if not llegada or not llegada.campana_id:
            return None
        campana = llegada.campana_id
        productos = ', '.join(R.limpiar(nombre, 80) for nombre in campana.linea_ids.mapped('nombre')[:R.MAX_PRODUCTOS]
                              if nombre)
        texto = self.env._('Llegó por el correo de novedades de D\'CASA «%(asunto)s», que le salió el %(fecha)s.',
                           asunto=R.limpiar(campana.asunto, R.MAX_ASUNTO),
                           fecha=self._fecha_texto(self._dia_panama(campana.enviada_en)))
        if productos:
            texto += ' ' + self.env._('En ese correo iban: %s.', productos)
        return texto[:600]

    # ------------------------------------------------------------------
    # El enlace «¿Te avisamos de lo nuevo? Sí, quiero» (firmado)
    # ------------------------------------------------------------------

    @api.model
    def _firma(self, ficha_id, origen, correo, momento):
        return hmac_odoo(self.env(su=True), ALCANCE_FIRMA, f'{ficha_id}:{origen}:{correo}:{momento}')[:40]

    @api.model
    def _enlace_pie_encendido(self):
        """El interruptor de Gerencia (encendido de fábrica). Apagado, la línea no va y los enlaces no anotan nada."""
        return (self.env['ir.config_parameter'].sudo().get_param(P_ENLACE_PIE) or 'encendido') != 'apagado'

    @api.model
    def _enlace_si(self, registro, destino):
        """El enlace firmado del pie, o ``None`` si no va.

        Solo en la factura de cliente y en la bienvenida, cuando el correo va a UNA sola persona y esa persona ES la
        ficha comercial firmada (no un contacto hijo, ni varios destinatarios: el «sí» lo da quien recibe el correo),
        con su correo bien escrito, que no es del equipo, que no dijo ya que sí con ese correo y sin baja ni «no
        contactar» en ninguna ficha con ese correo. Con el interruptor apagado, nunca."""
        if not self._enlace_pie_encendido() or registro is None or not getattr(registro, '_name', None) \
                or not registro or not destino or len(destino) != 1:
            return None
        registro, destino = registro[:1].sudo(), destino.sudo()
        if registro._name == 'account.move' and registro.move_type == 'out_invoice':
            origen, ficha = 'factura', registro.commercial_partner_id
        elif registro._name == 'res.partner':
            origen, ficha = 'bienvenida', registro.commercial_partner_id
        else:
            return None
        if not ficha or destino != ficha or ficha.dcasa_promos_baja_fecha or ficha.dcasa_no_contactar:
            return None
        correo = correo_valido(ficha.email)
        if not correo or correo != correo_valido(destino.email) \
                or (ficha.dcasa_promos_fecha and ficha.dcasa_promos_correo == correo):
            return None
        Partner = self.env['res.partner']
        if correo in Partner._dcasa_correos_del_equipo() or Partner._dcasa_promos_bloqueos_por_correo([correo]):
            return None
        momento = int(time.time())
        token = f'{ficha.id}.{CODIGO_DEL_ORIGEN[origen]}.{momento}.{self._firma(ficha.id, origen, correo, momento)}'
        return f"{self.env['dcasa.correo']._base()}/novedades/si?t={token}"

    @api.model
    def _enlace_leer(self, token):
        """``(estado, ficha, origen)`` del enlace: «confirmar», «ya» (ya tenía permiso con ese correo), «baja» (ese
        correo se dio de baja en alguna ficha: no se vuelve a dar de alta) o «invalido» (mal formado, firma mala,
        vencido, la ficha ya no tiene ese correo o el interruptor está apagado).

        Primero la forma exacta (solo ASCII); la firma se calcula siempre y se compara en bytes, exista o no la ficha:
        la respuesta es la misma."""
        Partner = self.env['res.partner']
        encontrado = TOKEN.fullmatch(token) if isinstance(token, str) else None
        if not encontrado or not self._enlace_pie_encendido():
            return 'invalido', Partner, None
        ficha_id, codigo, momento, firma = encontrado.groups()
        ficha_id, momento, origen = int(ficha_id), int(momento), ORIGEN_DEL_CODIGO[codigo]
        ficha = Partner.sudo().browse(ficha_id).exists()
        correo = correo_valido(ficha.email) if ficha else None
        esperada = self._firma(ficha_id, origen, correo or '', momento)
        firma_buena = hmac_py.compare_digest(esperada.encode('ascii'), firma.encode('ascii'))
        if not (firma_buena and ficha and correo and ficha == ficha.commercial_partner_id):
            return 'invalido', Partner, None
        if not 0 <= time.time() - momento <= VIGENCIA_ENLACE.total_seconds():
            return 'invalido', Partner, None
        if ficha.dcasa_promos_baja_fecha or Partner._dcasa_promos_bloqueos_por_correo([correo]).get(correo) == 'baja':
            return 'baja', ficha, origen
        if ficha.dcasa_promos_fecha and ficha.dcasa_promos_correo == correo:
            return 'ya', ficha, origen
        return 'confirmar', ficha, origen

    @api.model
    def _enlace_ajustar(self, encendido):
        """Prende o apaga la línea del pie (Gerencia o administradores)."""
        if not self._ve_dinero():
            raise AccessError(self.env._('La línea «Sí, quiero» del pie la prenden o apagan Gerencia o un '
                                         'administrador.'))
        self.env['ir.config_parameter'].sudo().set_param(P_ENLACE_PIE, 'encendido' if encendido else 'apagado')

    @api.model
    def _enlace_confirmar(self, token):
        """Anota el «sí» del enlace (después de que la persona tocó «Sí, quiero» en la página). Devuelve el estado."""
        estado, ficha, origen = self._enlace_leer(token)
        if estado != 'confirmar':
            return estado
        # El cliente mismo toca «Sí, quiero» dos veces: es un acto explícito y borra un «no» viejo (CAMILA.md §1c).
        ficha.sudo()._dcasa_promos_registrar(origen, explicito=True)
        return 'gracias'

    # ------------------------------------------------------------------
    # Crones (nunca envían)
    # ------------------------------------------------------------------

    @api.model
    def _cron_preparar(self):
        """Cada día: si pasaron 15 días desde la última campaña (o nunca salió ninguna) y no hay ninguna abierta, deja
        un borrador armado (lo nuevo, lo más vendido y lo quieto) para que alguien de marketing lo revise. Nunca
        envía."""
        if self._abiertas():
            return False
        _ultima, _proxima, puede = self._proxima()
        if not puede:
            return False
        try:
            with self.env.cr.savepoint():
                self.sudo()._armar(automatica=True)
        except UserError as error:
            _logger.info('DCASA_CAMILA no se pudo armar el borrador automático: %s', error)
            return False
        return True

    @api.model
    def _cron_sincronizar(self):
        """Cada hora: anota los permisos de Sofía y, en producción con la clave, las bajas en los dos sentidos; cada 6
        horas, los resultados de las campañas de los últimos 30 días. Los contactos ya no se suben aquí: cada campaña
        sube los suyos al enviar."""
        self.env['res.partner'].sudo()._dcasa_promos_de_sofia()
        if not (self._clave() and self._entorno() == 'produccion'):
            return False
        try:
            self.sudo()._sincronizar()
        except RC.ErrorResend as error:
            _logger.warning('DCASA_CAMILA no se pudo sincronizar con Resend: %s', error.mensaje)
            return False
        # El dominio del remitente de las campañas (verificado y con el conteo de aperturas y clics): cada 6 horas.
        # Nunca frena el cron ni lo que sigue.
        self.env.cr.flush()
        try:
            with self.env.cr.savepoint():
                self.sudo()._revisar_remitente('cron')
        except Exception:   # noqa: BLE001
            _logger.warning('DCASA_CAMILA no se pudo revisar el remitente de las campañas en Resend', exc_info=True)
        ahora = fields.Datetime.now()
        for campana in self.env['dcasa.camila.campana'].sudo().search([
                ('estado', '=', 'enviada'), ('enviada_en', '>=', ahora - timedelta(days=DIAS_RESULTADOS)),
                ('resend_broadcast_id', '!=', False), '|', ('resultados_en', '=', False),
                ('resultados_en', '<', ahora - timedelta(hours=HORAS_RESULTADOS))]):
            try:
                self._actualizar_resultados(campana)
            except RC.ErrorResend as error:
                _logger.info('DCASA_CAMILA sin resultados de Resend para la campaña %s: %s', campana.id, error.mensaje)
        return True
