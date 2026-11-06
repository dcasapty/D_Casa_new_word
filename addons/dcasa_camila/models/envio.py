"""Camila: la sincronización con Resend, el envío, la prueba, los resultados, el enlace «Sí, quiero» y los crones.

* **Antes de cada envío** (y cada hora con el cron) el segmento de Resend queda igual a lo que dice Odoo: las bajas de
  Resend pasan a la ficha, sale del segmento quien ya no tiene permiso (y si se dio de baja en Odoo, la baja sube a
  Resend) y entra quien dijo que sí. Resend es la lista de contactos del segmento: no hay otra copia que se desfase.
* **Al enviar, el servidor revisa todo** aunque llegue por RPC: el grupo, producción (``DCASA_ENTORNO=produccion``;
  staging nunca envía), la clave, los 15 días, los productos y precios de ahora (si cambió algo desde que la persona
  lo vio, no sale y se le muestra otra vez), al menos un cliente con permiso y que las bajas se trajeron recién. Se
  confirma la base a mitad de la petición (como Sofía): un doble clic o dos personas a la vez no la mandan dos veces.
* **Un error de Camila o de Resend nunca hace fallar una venta, un pago ni el correo de una factura**: nada de esto
  corre dentro de esos flujos (el enlace del pie se arma en un savepoint y, si falla, el correo sale sin la línea).
"""
import hmac as hmac_py
import logging
import time
from datetime import timedelta

from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models import transaccion
from odoo.addons.dcasa_correo.models.correo import correo_valido, motivo_legible
from odoo.addons.dcasa_correo.models.resend import remitente_visible
from odoo.exceptions import UserError
from odoo.tools import SQL
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
    def _sincronizar(self, limite=None, cliente=None):
        """Deja el segmento de Resend igual a Odoo. Devuelve ``{bajas, sacados, subidos, faltan, en_segmento}``.

        1. Cada contacto del segmento dado de baja en Resend queda con baja en su ficha (la baja es final).
        2. Sale del segmento todo correo que no tiene permiso en Odoo; si su ficha se dio de baja en Odoo, la baja
           también se anota en Resend (vale para todas las campañas).
        3. Entra quien tiene permiso y no está (hasta ``limite``; el resto en la siguiente vuelta)."""
        cliente = cliente or self._cliente()
        segmento = self._segmento(cliente)
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        en_resend = {}
        for contacto in cliente.contactos_del_segmento(segmento):
            correo = correo_valido(contacto.get('email'))
            if correo:
                en_resend[correo] = bool(contacto.get('unsubscribed')) or en_resend.get(correo, False)
        dados_de_baja = [correo for correo, baja in en_resend.items() if baja]
        bajas = Partner.browse()
        if dados_de_baja:
            fichas = Partner.search([('email_normalized', 'in', dados_de_baja)]).commercial_partner_id
            bajas = fichas._dcasa_promos_baja('correo')
        permitidos = self.env['res.partner'].sudo()._dcasa_promos_con_permiso()
        sacados = 0
        for correo, baja in en_resend.items():
            if correo in permitidos or baja:
                continue
            if Partner.search_count([('email_normalized', '=', correo),
                                     ('commercial_partner_id.dcasa_promos_baja_fecha', '!=', False)], limit=1):
                cliente.dar_de_baja(correo)
            cliente.sacar_del_segmento(correo, segmento)
            sacados += 1
        faltan = [correo for correo in permitidos if correo not in en_resend]
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
        except RC.ErrorResend as error:
            valores = {'error': error.mensaje[:300], 'enviando_desde': False}
            if not campana.resend_broadcast_id:
                valores['estado'] = 'borrador'   # nada quedó en Resend: se puede editar y volver a intentar
            campana.write(valores)
            transaccion.confirmar(self.env)
            _logger.warning('DCASA_CAMILA no se pudo enviar la campaña %s: %s', campana.id, error.mensaje)
            return {'ok': False, 'mensaje': self.env._('No salió: %s', error.mensaje)}
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
            cliente.enviar_broadcast(campana.resend_broadcast_id)
        elif estado not in RC.ESTADOS_YA_SALIO:
            raise RC.ErrorResend(self.env._('En Resend la campaña quedó «%s»: revísala allá antes de reintentar.',
                                            estado))
        return destinatarios

    # ------------------------------------------------------------------
    # La prueba (solo al correo de quien aprueba, por el camino de siempre)
    # ------------------------------------------------------------------

    @api.model
    def _enviar_prueba(self, campana_id):
        """Manda la campaña al correo de quien la pide, ahora, por los correos de siempre (clase «prueba» de
        ``politica.py``: solo sale a correos del equipo). Sin el enlace de baja de Resend (va solo en la real)."""
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
        """Entregados, aperturas, clics y bajas de Resend (``GET /broadcasts/{id}/recipients``)."""
        if not (campana.resend_broadcast_id and self._clave() and self._entorno() == 'produccion'):
            return False
        cliente = self._cliente()
        valores = {campo: cliente.contar_destinatarios(campana.resend_broadcast_id, tipo)
                   for campo, tipo in TIPOS_RESEND}
        campana.sudo().write(dict(valores, resultados_en=fields.Datetime.now()))
        return True

    # ------------------------------------------------------------------
    # Los chats que llegaron con la marca de la campaña
    # ------------------------------------------------------------------

    @api.model
    def _anotar_llegada(self, conversacion, mensaje):
        """Si el mensaje del cliente trae la marca de una campaña enviada («Ref. DCN-0007»), cuenta ese chat una vez."""
        numero = R.campana_de_la_marca(mensaje.texto)
        if not numero:
            return False
        campana = self.env['dcasa.camila.campana'].sudo().browse(numero).exists()
        if not campana or campana.estado != 'enviada' or not campana.enviada_en \
                or mensaje.ts < campana.enviada_en - timedelta(minutes=5):
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
    def _enlace_si(self, registro):
        """El enlace firmado del pie, o ``None`` si no va: solo en la factura de cliente y en la bienvenida, a una ficha
        con correo, que no es del equipo, que todavía no dijo que sí y que no se dio de baja."""
        if registro is None or not getattr(registro, '_name', None) or not registro:
            return None
        registro = registro[:1].sudo()
        if registro._name == 'account.move' and registro.move_type == 'out_invoice':
            origen, ficha = 'factura', registro.commercial_partner_id
        elif registro._name == 'res.partner':
            origen, ficha = 'bienvenida', registro.commercial_partner_id
        else:
            return None
        if not ficha or ficha.dcasa_promos_fecha or ficha.dcasa_promos_baja_fecha or ficha.dcasa_no_contactar:
            return None
        correo = correo_valido(ficha.email)
        if not correo or correo in self.env['res.partner']._dcasa_correos_del_equipo():
            return None
        momento = int(time.time())
        token = f'{ficha.id}.{CODIGO_DEL_ORIGEN[origen]}.{momento}.{self._firma(ficha.id, origen, correo, momento)}'
        return f"{self.env['dcasa.correo']._base()}/novedades/si?t={token}"

    @api.model
    def _enlace_leer(self, token):
        """``(estado, ficha, origen)`` del enlace: «confirmar», «ya» (ya tenía permiso), «baja» (se dio de baja: no se
        vuelve a dar de alta) o «invalido» (firma mala, vencido, o la ficha ya no tiene ese correo)."""
        Partner = self.env['res.partner']
        partes = str(token or '').strip().split('.')
        if len(partes) != 4 or not partes[0].isdigit() or partes[1] not in ORIGEN_DEL_CODIGO or not partes[2].isdigit():
            return 'invalido', Partner, None
        ficha = Partner.sudo().browse(int(partes[0])).exists()
        origen, momento = ORIGEN_DEL_CODIGO[partes[1]], int(partes[2])
        correo = correo_valido(ficha.email) if ficha else None
        if not ficha or not correo or ficha != ficha.commercial_partner_id:
            return 'invalido', Partner, None
        esperada = self._firma(ficha.id, origen, correo, momento)
        if not hmac_py.compare_digest(esperada, partes[3]):
            return 'invalido', Partner, None
        if time.time() - momento > VIGENCIA_ENLACE.total_seconds():
            return 'invalido', Partner, None
        if ficha.dcasa_promos_baja_fecha:
            return 'baja', ficha, origen
        if ficha.dcasa_promos_fecha:
            return 'ya', ficha, origen
        return 'confirmar', ficha, origen

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
