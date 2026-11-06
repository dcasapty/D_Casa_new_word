"""Camila: la sincronización con Resend, el envío, la prueba, los resultados, el enlace «Sí, quiero» y los crones.

* **Antes de cada envío** (y cada hora con el cron) el segmento de Resend queda igual a lo que dice Odoo: las bajas de
  Resend pasan a las fichas con ese correo, sale del segmento (por el id del contacto) todo el que no está en la lista
  de Odoo, aunque Odoo no sepa leer su correo, y si ese correo se dio de baja en cualquier ficha la baja sube a Resend;
  entra quien dijo que sí. Justo antes de mandar se vuelve a listar el segmento: si queda alguien suscrito que no está
  en la lista de Odoo, no sale. Resend es la lista de contactos del segmento: no hay otra copia que se desfase.
* **Al enviar, el servidor revisa todo** aunque llegue por RPC: el grupo, producción (``DCASA_ENTORNO=produccion``;
  staging nunca envía), la clave, los 15 días, los productos y precios de ahora (si cambió algo desde que la persona
  lo vio, no sale y se le muestra otra vez), al menos un cliente con permiso y que las bajas se trajeron recién. Se
  confirma la base a mitad de la petición (como Sofía): un doble clic o dos personas a la vez no la mandan dos veces.
  Ningún error deja la campaña a medias; una «aprobada» que quedó trabada (Resend la canceló, quedó en borrador allá o
  nunca llegó) la descartan Gerencia o un administrador.
* **Un error de Camila o de Resend nunca hace fallar una venta, un pago ni el correo de una factura**: nada de esto
  corre dentro de esos flujos (el enlace del pie se arma en un savepoint y, si falla, el correo sale sin la línea).
"""
import hmac as hmac_py
import logging
import re
import time
from datetime import timedelta

from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models import transaccion
from odoo.addons.dcasa_correo.models.correo import correo_valido, motivo_legible
from odoo.addons.dcasa_correo.models.resend import remitente_visible
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL, email_normalize
from odoo.tools.misc import hmac as hmac_odoo

from . import reglas as R
from . import resend_campanas as RC
from .campana import ABIERTAS

_logger = logging.getLogger(__name__)

P_SEGMENTO = 'dcasa_camila.segmento_id'
NOMBRE_SEGMENTO = "D'CASA: clientes con permiso (Odoo)"
MAX_SUBIR_AL_ENVIAR = 300      # contactos nuevos que se suben dentro del clic «Enviar» (el resto, el cron)
MAX_SUBIR_POR_VUELTA = 500     # por vuelta del cron (cada hora)
MINUTOS_ENVIANDO = 10          # «ya se está enviando» (otra persona o un doble clic)
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


class DcasaCamila(models.AbstractModel):
    _inherit = 'dcasa.camila'

    # ------------------------------------------------------------------
    # Resend: el segmento igual a Odoo
    # ------------------------------------------------------------------

    @api.model
    def _cliente(self):
        return RC.ClienteCampanas(self._clave(), pausa=RC.PAUSA)

    @api.model
    def _segmento(self, cliente):
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
    def _sobran_en_el_segmento(self, cliente, segmento, permitidos):
        """Los contactos SUSCRITOS del segmento que no están en la lista de Odoo (ni uno debe quedar al enviar)."""
        return [contacto for contacto in cliente.contactos_del_segmento(segmento)
                if not contacto.get('unsubscribed') and correo_valido(contacto.get('email')) not in permitidos]

    @api.model
    def _sincronizar(self, limite=None, cliente=None):
        """Deja el segmento de Resend igual a Odoo. Devuelve ``{bajas, sacados, subidos, faltan, en_segmento}``.

        1. Cada contacto del segmento dado de baja en Resend queda con baja en las fichas con ese correo (final).
        2. Sale del segmento, POR SU ID, todo contacto suscrito que no está en la lista de Odoo: también los correos
           que Odoo no sabe leer («o'brien@…», «José@…») y lo que hubiera en un segmento reusado. Si ese correo tiene
           baja en CUALQUIER ficha, la baja se anota también en Resend, por su id (vale para todas las campañas; por
           el correo, otra grafía en Resend daba 404 y la baja se perdía).
        3. Entra quien tiene permiso y no está (hasta ``limite``; el resto en la siguiente vuelta)."""
        cliente = cliente or self._cliente()
        segmento = self._segmento(cliente)
        contactos = cliente.contactos_del_segmento(segmento)
        bajas = self._anotar_bajas_de_resend(c.get('email') for c in contactos if c.get('unsubscribed'))
        Partner = self.env['res.partner'].sudo()
        permitidos = Partner._dcasa_promos_con_permiso()
        bloqueos = Partner._dcasa_promos_bloqueos_por_correo()
        presentes = set()
        sacados = 0
        for contacto in contactos:
            correo = correo_valido(contacto.get('email'))
            if contacto.get('unsubscribed') or correo in permitidos:
                if correo:
                    presentes.add(correo)   # con su baja no recibe nada y no se vuelve a subir
                continue
            referencia = contacto.get('id') or contacto.get('email')
            if any(bloqueos.get(clave) == 'baja' for clave in self._claves_correo(contacto.get('email'))):
                cliente.dar_de_baja(referencia)
            cliente.sacar_del_segmento(referencia, segmento)
            sacados += 1
        faltan = [correo for correo in permitidos if correo not in presentes]
        subidos = 0
        for correo in faltan[:limite] if limite else faltan:
            cliente.agregar_contacto(correo, None, segmento)   # solo el correo: nada más de la persona
            subidos += 1
        resumen = {'bajas': len(bajas), 'sacados': sacados, 'subidos': subidos, 'faltan': len(faltan) - subidos,
                   'en_segmento': len(permitidos) - (len(faltan) - subidos), 'segmento': segmento}
        _logger.info('DCASA_CAMILA sincronizado: %s bajas nuevas, %s fuera del segmento, %s subidos, %s por subir',
                     resumen['bajas'], sacados, subidos, resumen['faltan'])
        return resumen

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
    def _enviar(self, campana_id, huella):
        campana = self._bloquear(campana_id)
        if campana.estado == 'enviada':
            fecha = self._fecha_texto(self._dia_panama(campana.enviada_en))
            return {'ok': True, 'ya_estaba': True, 'mensaje': self.env._('Esa campaña ya salió el %s.', fecha)}
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
            valores = {'error': mensaje[:300], 'enviando_desde': False}
            if not campana.resend_broadcast_id:
                valores['estado'] = 'borrador'   # nada quedó en Resend: se puede editar y volver a intentar
            campana.write(valores)
            transaccion.confirmar(self.env)
            return {'ok': False, 'mensaje': self.env._('No salió: %s', mensaje)}
        campana.write({'estado': 'enviada', 'enviada_en': fields.Datetime.now(), 'destinatarios': destinatarios,
                       'enviando_desde': False, 'error': False})
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
        bloqueos = self._bloqueos(campana)
        if bloqueos:
            raise UserError(bloqueos[0])
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
        return None

    @api.model
    def _mandar_a_resend(self, campana):
        """Trae las bajas y deja el segmento igual a Odoo; crea el broadcast (una sola vez) y lo manda si sigue en
        borrador. Devuelve a cuántos clientes salió."""
        cliente = self._cliente()
        resumen = self._sincronizar(limite=MAX_SUBIR_AL_ENVIAR, cliente=cliente)
        if resumen['faltan']:
            raise RC.ErrorResend(self.env._('Todavía faltan %s clientes por subir a Resend: prueba otra vez en unos '
                                            'minutos.', resumen['faltan']), temporal=True)
        destinatarios = len(self.env['res.partner'].sudo()._dcasa_promos_con_permiso())
        if not destinatarios:
            raise RC.ErrorResend(self.env._('Después de traer las bajas, ya nadie tiene permiso: no salió nada.'))
        if not campana.resend_broadcast_id:
            config = self.env['dcasa.correo'].sudo()._config()
            broadcast = cliente.crear_broadcast(
                resumen['segmento'], remitente_visible(config['nombre'], config['remitente']), campana.asunto,
                self._html(campana, para_resend=True), responder_a=config['responder_a'],
                nombre=f'{campana.name} ({campana.marca})')
            campana.write({'resend_broadcast_id': broadcast})
            transaccion.confirmar(self.env)
        estado = cliente.estado_broadcast(campana.resend_broadcast_id)
        if estado == 'draft':
            # La última revisión: si en el segmento queda alguien suscrito que no está en la lista de Odoo, no sale.
            permitidos = self.env['res.partner'].sudo()._dcasa_promos_con_permiso()
            sobran = self._sobran_en_el_segmento(cliente, resumen['segmento'], permitidos)
            if sobran:
                raise RC.ErrorResend(self.env._(
                    'En el segmento de Resend quedan %s contactos sin permiso en Odoo: no salió. Prueba otra vez en '
                    'unos minutos; si sigue, revisa el segmento en Resend.', len(sobran)))
            cliente.enviar_broadcast(campana.resend_broadcast_id)
        elif estado not in RC.ESTADOS_YA_SALIO:
            raise RC.ErrorResend(self.env._('En Resend la campaña quedó «%s»: revísala allá antes de reintentar.',
                                            estado))
        return destinatarios

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
            if estado not in ('draft', 'canceled'):
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
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.env._('[Prueba] %s', campana.asunto or ''),
            'body_html': self._html(campana, prueba=True),
            'email_to': destino,
            'email_from': correo._remitente_formateado(),
            'headers': repr({'X-Dcasa-Correo': 'prueba'}),
            'model': 'res.users',
            'res_id': usuario.id,
            'auto_delete': True,
        })
        try:
            mail.send(raise_exception=True)
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
    def _resultados(self, campana):
        facturas, monto = self._ventas(campana)
        return {
            'enviados': campana.destinatarios,
            'chats': len(campana.llegada_ids),
            'ventas': facturas,
            'monto': self.env['dcasa.correo']._monto(monto, self.env.company.currency_id) if self._ve_dinero()
            else None,
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
        return True

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
        ficha.sudo()._dcasa_promos_registrar(origen)
        return 'gracias'

    # ------------------------------------------------------------------
    # Crones (nunca envían)
    # ------------------------------------------------------------------

    @api.model
    def _cron_preparar(self):
        """Cada día: si pasaron 15 días desde la última campaña (o nunca salió ninguna) y no hay una abierta, deja un
        borrador armado para que alguien de marketing lo revise. Nunca envía."""
        if self._abierta():
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
        """Cada hora: anota los permisos de Sofía y, en producción con la clave, trae las bajas de Resend y sube los
        contactos; cada 6 horas, los resultados de las campañas de los últimos 30 días."""
        self.env['res.partner'].sudo()._dcasa_promos_de_sofia()
        if not (self._clave() and self._entorno() == 'produccion'):
            return False
        try:
            self.sudo()._sincronizar(limite=MAX_SUBIR_POR_VUELTA)
        except RC.ErrorResend as error:
            _logger.warning('DCASA_CAMILA no se pudo sincronizar con Resend: %s', error.mensaje)
            return False
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
