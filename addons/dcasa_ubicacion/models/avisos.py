"""Los avisos de la entrega a la clienta (pedido del dueño, 2026-11-25: «el dolor número uno son los pedidos devueltos»;
«la gente no lee: íconos y pocas palabras»; «lo que priorizamos es lo más fácil para el cliente»).

A. **Al comprar, pedirle su punto en el mapa.** Al confirmar una venta que va a domicilio y cuya dirección de entrega
   no tiene un punto confiable (escrita a mano, buscada sin mover el pin, GPS impreciso o sin punto), UNA vez por venta
   (``dcasa_ubic_pedida_el``): si el asistente puede escribirle ya, le escribe a nombre del asistente con el enlace de
   un solo uso ligado a la venta; si no, una actividad para la vendedora y el botón «📲 Pedir ubicación por WhatsApp»
   (abre WhatsApp con el mismo texto y un enlace nuevo).
B. **El día de la entrega: «¿hay alguien en casa?».** En el sistema no hay un despacho fiable (la fecha programada de la
   entrega no dice que sale hoy): lo dispara una persona con «🚚 Sale hoy: avisarle» (la venta, la entrega, la acción de
   la lista para varias o Brian). Una vez por venta y por día. Sin punto confiable, el mensaje lleva el enlace del mapa.
   Juan entiende la respuesta (juan/src/dcasa/prompt.ts).

¿Cuándo puede escribirle sola? (``dcasa.conversacion._dcasa_puede_escribir_ya``)

* WhatsApp por QR y Telegram: siempre (no tienen ventana).
* WhatsApp de la API oficial, Instagram y Messenger: solo dentro de las 24 horas desde su último mensaje (fuera de eso
  Meta pide una plantilla aprobada, que este sistema no tiene: el error 131047). Se deja una hora de margen.
* Siempre: el canal y el asistente encendidos en Ajustes de Juan, el Worker configurado y la clienta sin «No contactar».

El mensaje se escribe a nombre del asistente (``autor='bot'``): una vendedora callaría a Juan
(docs/CONTEXTO_AGENTICO.md). Y no sale en esta transacción: queda «por enviar» y se adelanta el cron que manda lo
pendiente. Llamar al Worker confirma la transacción (``transaccion.confirmar``) y aquí se corre dentro de la
confirmación de una venta o de una herramienta de Brian, en un savepoint; además, si la venta no llega a confirmarse,
el mensaje tampoco sale.

Nada de esto hace fallar una venta ni un pago (va en un savepoint; el error queda en el registro, solo con el id de la
venta). Las coordenadas no salen nunca: ni en los textos, ni en las notas, ni en las actividades, ni en el registro.
"""
import logging
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.addons.dcasa_base import whatsapp
from odoo.addons.dcasa_conversaciones.models.ajustes import CANALES, CANALES_CON_CELULAR
from odoo.addons.dcasa_conversaciones.models.sale_origen import hoy_en_panama
from odoo.addons.dcasa_envios.motor.texto import dinero
from odoo.addons.dcasa_socios.models import reglas
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

from ..motor import geo

_logger = logging.getLogger(__name__)

# Los canales que solo dejan escribir dentro de las 24 h desde el último mensaje de la clienta (juan/src/canales: la
# capacidad ``ventana24h``). Telegram y WhatsApp por QR no tienen ventana.
CANALES_CON_VENTANA = ('whatsapp_cloud', 'instagram', 'messenger')
# Una hora de margen: el mensaje sale con el cron (segundos o minutos después) y puede reintentarse.
VENTANA_SEGURA = timedelta(hours=23)
CRON_DE_ENVIOS = 'dcasa_conversaciones.ir_cron_mantenimiento'
TIPO_PEDIR_UBICACION = 'dcasa_ubicacion.actividad_pedir_ubicacion'
GRUPO_VENTAS = 'sales_team.group_sale_salesman'
ETIQUETA_CANAL = dict(CANALES)
MAX_ZONA = 60


def url_whatsapp(numero, texto):
    """El enlace de WhatsApp con el mensaje ya escrito (``api.whatsapp.com/send``: con ``wa.me`` los emojis llegaban
    como «�» en WhatsApp Web y en Instagram; dcasa_base/whatsapp.py)."""
    return whatsapp.enlace(numero, texto)


class DcasaConversacionAvisos(models.Model):
    _inherit = 'dcasa.conversacion'

    def _dcasa_puede_escribir_ya(self, ajustes=None, ahora=None):
        """¿El asistente puede escribirle ahora por esta conversación, sin una plantilla de Meta?"""
        self.ensure_one()
        conv = self.sudo()
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        ahora = ahora or fields.Datetime.now()
        if not conv.id_externo or not ajustes.canal_activo(conv.canal):
            return False
        if conv.canal in CANALES_CON_VENTANA:
            return bool(conv.ultimo_mensaje_cliente) and conv.ultimo_mensaje_cliente >= ahora - VENTANA_SEGURA
        return True

    def _dcasa_escribir_como_asistente(self, texto):
        """El mensaje queda «por enviar» a nombre del asistente (Juan sigue atendiendo y lo ve en su historia) y se
        adelanta el cron que manda lo pendiente: sale en cuanto se confirme esta transacción. Si el Worker no responde,
        se reintenta como cualquier otro (nada se pierde: al agotarse queda «No se pudo enviar» a la vista)."""
        self.ensure_one()
        conv = self.sudo()
        Mensaje = self.env['dcasa.mensaje']
        mensaje, _creado = Mensaje._crear_si_no_existe({
            'conversacion_id': conv.id, 'id_mensaje': Mensaje._id_local(), 'direccion': 'saliente', 'autor': 'bot',
            'texto': texto, 'ts': fields.Datetime.now(), 'origen': 'odoo', 'estado_envio': 'por_enviar'})
        conv._notificar_panel('mensaje', mensaje)
        cron = self.env.ref(CRON_DE_ENVIOS, raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return mensaje


class ResPartnerAvisos(models.Model):
    _inherit = 'res.partner'

    def _dcasa_ubic_confiable(self):
        """¿El motorizado puede ir con este punto sin llamar antes? Confirmado por la clienta y de un origen confiable
        (GPS de 100 m o menos, el pin, el chat o un enlace de mapa): no escrito a mano ni buscado sin mover el pin."""
        self.ensure_one()
        partner = self.sudo()
        return bool(partner.dcasa_ubic_confirmada) and partner._dcasa_ubic_punto() is not None \
            and geo.es_confiable(partner.dcasa_ubic_origen, partner.dcasa_ubic_precision_m or None)

    def _dcasa_ubic_al_dia_en_ventas(self):
        resultado = super()._dcasa_ubic_al_dia_en_ventas()
        try:
            with self.env.cr.savepoint():
                self._dcasa_cerrar_pedidos_de_ubicacion()
        except Exception:   # noqa: BLE001 — el punto ya quedó; cerrar el pendiente es un extra
            _logger.exception('Avisos: no se pudo cerrar el pendiente de la ubicación de la ficha %s.', self.id)
        return resultado

    def _dcasa_cerrar_pedidos_de_ubicacion(self):
        """La clienta ya marcó un punto confiable: el pendiente «📍 Pedirle la ubicación de entrega» de sus ventas se da
        por hecho (la vendedora no la persigue por algo que ya hizo)."""
        self.ensure_one()
        tipo = self.env.ref(TIPO_PEDIR_UBICACION, raise_if_not_found=False)
        if not tipo or not self._dcasa_ubic_confiable():
            return
        ordenes = self.env['sale.order'].sudo().search([('partner_shipping_id', '=', self.id)], limit=50)
        pendientes = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'sale.order'), ('res_id', 'in', ordenes.ids), ('activity_type_id', '=', tipo.id)])
        if pendientes:
            pendientes.action_feedback(feedback=self.env._('La clienta marcó su casa en el mapa.'))


class UbicacionEnlaceAvisos(models.Model):
    _inherit = 'dcasa.ubicacion.enlace'

    def _confirmar(self, lat, lon, origen, **opciones):
        # Las opciones (precisión, referencia, quién recibe, teléfono…) pasan tal cual: así otra herencia de
        # ``_confirmar`` puede sumar las suyas sin romper esta (la unión de C/D/E con los avisos lo rompió una vez).
        zona = super()._confirmar(lat, lon, origen, **opciones)
        orden = self.sudo().orden_id
        if orden and orden.state == 'sale':
            try:
                with self.env.cr.savepoint():
                    orden._dcasa_nota_del_punto_nuevo(zona)
            except Exception:   # noqa: BLE001 — el punto ya quedó; la nota al equipo es un extra
                _logger.exception('Avisos: no se pudo dejar la nota del punto nuevo en la venta %s.', orden.id)
        return zona


class SaleOrderAvisos(models.Model):
    _inherit = 'sale.order'

    dcasa_ubic_pedida_el = fields.Datetime(
        'Ubicación pedida el', readonly=True, copy=False,
        help='Cuándo se le pidió a la clienta que marque su casa en el mapa (una sola vez por venta, al confirmarla).')
    dcasa_aviso_sale_hoy_el = fields.Date(
        'Aviso «sale hoy»', readonly=True, copy=False,
        help='El día (en Panamá) en que se le avisó que su pedido sale hoy. Por el chat, una sola vez por día.')
    dcasa_aviso_sale_hoy_por = fields.Selection(
        [('chat', 'Por el chat (el asistente)'), ('whatsapp', 'Por WhatsApp (una persona)')], 'Aviso por',
        readonly=True, copy=False)
    dcasa_aviso_sale_hoy_mensaje_id = fields.Many2one(
        'dcasa.mensaje', 'Mensaje del aviso «sale hoy»', readonly=True, copy=False, ondelete='set null',
        help='El mensaje que escribió el asistente: si no se pudo enviar, se puede volver a avisar ese mismo día.')
    dcasa_va_a_domicilio = fields.Boolean('Va a domicilio', compute='_compute_dcasa_avisos')
    dcasa_falta_punto = fields.Boolean(
        'Falta su casa en el mapa', compute='_compute_dcasa_avisos',
        help='Va a domicilio y la dirección de entrega no tiene un punto confiable: el motorizado tendría que llamar.')

    @api.depends('state', 'carrier_id', 'order_line', 'partner_id', 'partner_shipping_id',
                 'partner_shipping_id.dcasa_ubic_origen', 'partner_shipping_id.dcasa_ubic_confirmada',
                 'partner_shipping_id.partner_latitude', 'partner_shipping_id.partner_longitude')
    def _compute_dcasa_avisos(self):
        for orden in self:
            domicilio = orden.state != 'cancel' and orden._dcasa_va_a_domicilio()
            destino = orden.partner_shipping_id or orden.partner_id
            orden.dcasa_va_a_domicilio = domicilio
            orden.dcasa_falta_punto = domicilio and bool(destino) and not destino._dcasa_ubic_confiable()

    # ------------------------------------------------------------------
    # A quién y por dónde
    # ------------------------------------------------------------------

    def _dcasa_destino(self):
        self.ensure_one()
        return (self.partner_shipping_id or self.partner_id).sudo()

    def _dcasa_personas_de_la_compra(self):
        """A quién le escriben los avisos: la clienta que compró (y su empresa) y la dirección de entrega solo si es
        suya (una dirección hija). Si es un regalo para otra persona, a ella no: «¡Gracias por su compra!» le contaría
        la sorpresa (auditoría 1)."""
        self.ensure_one()
        orden = self.sudo()
        personas = orden.partner_id | orden.partner_id.commercial_partner_id
        entrega = orden.partner_shipping_id
        if entrega and entrega.commercial_partner_id == orden.partner_id.commercial_partner_id:
            personas |= entrega
        return personas.exists()

    def _dcasa_conversacion_para_avisar(self):
        """``(conversación, motivo)``: la conversación de la clienta por donde el asistente puede escribirle ya (la de
        su último mensaje) o una vacía con el porqué, en palabras sencillas, para quien lo tenga que mandar a mano."""
        self.ensure_one()
        vacia = self.env['dcasa.conversacion']
        orden = self.sudo()
        personas = orden._dcasa_personas_de_la_compra()
        if any(persona.dcasa_no_contactar for persona in personas):
            return vacia, self.env._('pidió que no le escribamos por el chat')
        conversaciones = vacia.sudo().search([('partner_id', 'in', personas.ids)],
                                             order='ultimo_mensaje_cliente desc nulls last, id desc', limit=20)
        if not conversaciones:
            return vacia, self.env._('no tiene un chat con la tienda')
        if not self.env['dcasa.juan.cliente'].configurado():
            return vacia, self.env._('el asistente no está conectado')
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        for conv in conversaciones:
            if conv._dcasa_puede_escribir_ya(ajustes, ahora):
                return conv, ''
        return vacia, self.env._('su chat no deja escribirle ahora (en WhatsApp oficial, Instagram y Messenger solo '
                                 'dentro de las 24 horas desde su último mensaje, o el asistente está apagado)')

    def _dcasa_celular_para_whatsapp(self):
        """El número de WhatsApp (507 y el celular), o ``''``: el celular de Panamá de la ficha o, si no, el de su chat
        de WhatsApp. Solo de Panamá, como «Enviar por WhatsApp» de la venta: un id del chat que no es un celular (los
        de WhatsApp por QR pueden serlo) mandaría el mensaje a otra persona."""
        self.ensure_one()
        orden = self.sudo()
        for persona in orden._dcasa_personas_de_la_compra():
            for valor in (persona.phone, persona.dcasa_celular):
                numero = reglas.celular_normal(valor)
                if reglas.celular_valido(numero):
                    return f'507{numero}'
        conversaciones = self.env['dcasa.conversacion'].sudo().search([
            ('partner_id', 'in', orden._dcasa_personas_de_la_compra().ids),
            ('canal', 'in', tuple(CANALES_CON_CELULAR))], order='ultimo_mensaje_cliente desc nulls last', limit=5)
        for conversacion in conversaciones:
            digitos = reglas.solo_digitos(conversacion.id_externo)
            if len(digitos) == 11 and digitos.startswith('507') and reglas.celular_valido(digitos[3:]):
                return digitos
        return ''

    def _dcasa_responsable_de_avisos(self):
        """La vendedora de la venta; si no tiene (o es el usuario técnico de Juan), la persona responsable por defecto
        de Ajustes de Juan; si no, el administrador."""
        self.ensure_one()
        juan = self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False)
        vendedora = self.sudo().user_id
        if vendedora and vendedora.active and not vendedora.share and vendedora != juan:
            return vendedora
        responsable = self.env['dcasa.juan.ajustes'].obtener().responsable_id
        if responsable and responsable.active:
            return responsable
        return self.env.ref('base.user_admin', raise_if_not_found=False) or self.env['res.users']

    # ------------------------------------------------------------------
    # Textos para la clienta: de usted, cortos y con ícono
    # ------------------------------------------------------------------

    def _dcasa_texto_pedir_ubicacion(self, url):
        self.ensure_one()
        return self.env._('🛍️ ¡Gracias por su compra!\n📍 Para que el motorizado llegue directo a su casa, márquela '
                          'aquí: %s', url)

    def _dcasa_zona_corta(self):
        """«Villa Lucre»: la barriada, o el corregimiento, el distrito o la ciudad (lo primero que haya)."""
        destino = self._dcasa_destino()
        return geo.texto_corto(destino.dcasa_barriada or destino.dcasa_corregimiento or destino.dcasa_distrito
                               or destino.city or '', MAX_ZONA)

    def _dcasa_texto_sale_hoy(self, url=None):
        self.ensure_one()
        zona = self._dcasa_zona_corta()
        lineas = [self.env._('🚚 ¡Hoy le llega su pedido %(pedido)s a %(zona)s!', pedido=self.name, zona=zona)
                  if zona else self.env._('🚚 ¡Hoy le llega su pedido %s!', self.name)]
        if url:
            lineas.append(self.env._('📍 Para que el motorizado llegue directo, marque su casa aquí: %s', url))
        lineas.append(self.env._('¿Habrá alguien en casa para recibirlo?'))
        lineas.append(self.env._('✅ Sí / 📍 Cambiar'))
        return '\n'.join(lineas)

    def _dcasa_avisos_nota(self, texto):
        self.sudo().message_post(body=Markup('<p>%s</p>') % escape(texto), subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # A. Pedirle su punto en el mapa
    # ------------------------------------------------------------------

    def action_confirm(self):
        resultado = super().action_confirm()
        for orden in self:
            orden._dcasa_pedir_ubicacion_al_confirmar()
        return resultado

    def _action_cancel(self):
        resultado = super()._action_cancel()
        # La página del motorizado se cierra con un secreto nuevo: si la venta vuelve a borrador, el papel viejo no
        # revive (auditoría 2).
        entregas = self.env['dcasa.ubicacion.entrega'].sudo().search([('order_id', 'in', self.ids)])
        for entrega in entregas:
            entrega.write({'token': geo.token_nuevo(18), 'vence': fields.Datetime.now()})
        # Una venta cancelada ya no se entrega: el pendiente «📍 Pedirle la ubicación» se cierra (auditoría 1).
        tipo = self.env.ref(TIPO_PEDIR_UBICACION, raise_if_not_found=False)
        if tipo:
            self.env['mail.activity'].sudo().search([
                ('res_model', '=', 'sale.order'), ('res_id', 'in', self.ids),
                ('activity_type_id', '=', tipo.id)]).action_feedback(feedback=self.env._('La venta se canceló.'))
        return resultado

    def _dcasa_pedir_ubicacion_al_confirmar(self):
        """Una vez por venta. Nunca hace fallar la confirmación: el error queda en el registro y la venta sigue."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                orden = self.sudo()
                if orden.state != 'sale' or orden.dcasa_ubic_pedida_el or not orden._dcasa_va_a_domicilio():
                    return
                destino = orden._dcasa_destino()
                if not destino or destino._dcasa_ubic_confiable():
                    return
                orden._dcasa_pedir_ubicacion(automatico=True)
        except Exception:   # noqa: BLE001 — la venta ya se confirmó; pedir la ubicación es un extra
            _logger.exception('Avisos: no se pudo pedir la ubicación de la venta %s.', self.id)

    def _dcasa_pedir_ubicacion(self, automatico=False):
        """Le pide a la clienta que marque su casa. Devuelve ``{'como', 'canal', 'motivo', 'url_whatsapp'}``:

        * ``chat``: el asistente se lo escribe (con el enlace de un solo uso ligado a esta venta y a su chat).
        * ``persona`` (``automatico``): sin un chat donde escribirle, una actividad para la vendedora.
        * ``whatsapp``: sin chat, el enlace de WhatsApp para que una persona lo mande (Brian).
        * ``sin_celular``: sin chat ni celular."""
        self.ensure_one()
        orden = self.sudo()
        destino = orden._dcasa_destino()
        Enlace = self.env['dcasa.ubicacion.enlace']
        conv, motivo = orden._dcasa_conversacion_para_avisar()
        if conv:
            _enlace, url = Enlace._crear(destino, conversacion=conv, creado_por='aviso', orden=orden)
            conv._dcasa_escribir_como_asistente(orden._dcasa_texto_pedir_ubicacion(url))
            orden.write({'dcasa_ubic_pedida_el': fields.Datetime.now()})
            canal = ETIQUETA_CANAL.get(conv.canal, conv.canal)
            conv._aviso(self.env._(
                '📍 Se le pidió que marque su casa en el mapa para la venta %s: va a domicilio y la dirección no '
                'tiene un punto confiable.', orden.name))
            orden._dcasa_avisos_nota(self.env._(
                '📲 Se le pidió a la clienta que marque su casa en el mapa, por el chat (%s).', canal))
            return {'como': 'chat', 'canal': canal, 'motivo': ''}
        if automatico:
            orden.write({'dcasa_ubic_pedida_el': fields.Datetime.now()})
            orden._dcasa_actividad_pedir_ubicacion(motivo)
            return {'como': 'persona', 'motivo': motivo}
        numero = orden._dcasa_celular_para_whatsapp()
        if not numero:
            return {'como': 'sin_celular', 'motivo': motivo}
        _enlace, url = Enlace._crear(destino, creado_por='aviso', orden=orden)
        orden.write({'dcasa_ubic_pedida_el': fields.Datetime.now()})
        return {'como': 'whatsapp', 'motivo': motivo,
                'url_whatsapp': url_whatsapp(numero, orden._dcasa_texto_pedir_ubicacion(url))}

    def _dcasa_actividad_pedir_ubicacion(self, motivo=''):
        """«📍 Pedirle la ubicación de entrega» para la vendedora (una sola abierta por venta)."""
        self.ensure_one()
        orden = self.sudo()
        tipo = self.env.ref(TIPO_PEDIR_UBICACION, raise_if_not_found=False)
        responsable = orden._dcasa_responsable_de_avisos()
        if not tipo or not responsable:
            return
        if self.env['mail.activity'].sudo().search_count([
                ('res_model', '=', 'sale.order'), ('res_id', '=', orden.id), ('activity_type_id', '=', tipo.id)],
                limit=1):
            return
        nota = self.env._('Va a domicilio y la dirección no tiene su casa marcada en el mapa: el motorizado tendría '
                          'que llamar. Toca «📲 Pedir ubicación por WhatsApp» en la venta y mándale el mensaje.')
        if motivo:
            nota += ' ' + self.env._('El asistente no se lo pudo escribir: %s.', motivo)
        orden.activity_schedule(TIPO_PEDIR_UBICACION, summary=self.env._('📍 Pedirle la ubicación de entrega'),
                                note=Markup('<p>%s</p>') % escape(nota), user_id=responsable.id)

    def _dcasa_nota_del_punto_nuevo(self, zona):
        """La clienta marcó su casa con la venta ya confirmada: lo cobrado no se toca (ya se cobró), pero si el envío de
        la tabla para esa zona es otro, el equipo lo ve en la venta. Y si era el día de la entrega, una actividad para
        que el motorizado abra otra vez la ruta. Sin coordenadas."""
        self.ensure_one()
        orden = self.sudo()
        precio = self.env['dcasa.ubicacion']._precio(zona.get('lugar'))
        envio = orden.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)
        cobrado = sum(envio.mapped('price_unit'))
        donde = (zona.get('texto') or '').replace(' · ', ', ') or self.env._('sin zona de la tabla')
        if not precio['con_precio']:
            orden._dcasa_avisos_nota(self.env._(
                '📍 La clienta marcó su casa con la venta ya confirmada: %(zona)s. 🚚 La tabla no da precio para esa '
                'zona (en la venta, el envío quedó en %(cobrado)s): confírmenlo con ella.', zona=donde,
                cobrado=dinero(cobrado)))
        elif float_compare(cobrado, precio['total'], precision_rounding=orden.currency_id.rounding or 0.01):
            orden._dcasa_avisos_nota(self.env._(
                '📍 La clienta marcó su casa con la venta ya confirmada: %(zona)s. 🚚 Con la tabla, el envío a esa '
                'zona es %(tabla)s y en la venta quedó en %(cobrado)s. La venta no se cambió: decidan si se ajusta.',
                zona=donde, tabla=precio['total_txt'], cobrado=dinero(cobrado)))
        if orden.dcasa_aviso_sale_hoy_el == hoy_en_panama():
            responsable = orden._dcasa_responsable_de_avisos()
            if responsable:
                orden.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=responsable.id,
                    summary=self.env._('📍 Marcó su casa el día de la entrega'),
                    note=Markup('<p>%s</p>') % escape(self.env._(
                        'La clienta marcó su casa hoy: %s. Que el motorizado abra otra vez «Ruta del motorizado» (o el '
                        'QR) antes de salir.', donde)))

    def action_dcasa_pedir_ubicacion_whatsapp(self):
        """Botón «📲 Pedir ubicación por WhatsApp»: abre WhatsApp con el mensaje y un enlace nuevo de un solo uso."""
        self.ensure_one()
        self._dcasa_exigir_ventas()
        self.check_access('write')
        orden = self.sudo()
        if orden.state == 'cancel' or not orden._dcasa_va_a_domicilio():
            raise UserError(self.env._('Esta venta no va a domicilio: no hace falta su casa en el mapa.'))
        numero = orden._dcasa_celular_para_whatsapp()
        if not numero:
            raise UserError(self.env._(
                '%s no tiene un celular anotado. Escríbelo en el contacto (8 números, como 6123-4567).',
                orden.partner_id.display_name))
        conv, _motivo = orden._dcasa_conversacion_para_avisar()
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(
            orden._dcasa_destino(), conversacion=conv or None, creado_por='aviso', orden=orden)
        if not orden.dcasa_ubic_pedida_el:
            orden.write({'dcasa_ubic_pedida_el': fields.Datetime.now()})
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': url_whatsapp(numero, orden._dcasa_texto_pedir_ubicacion(url))}

    # ------------------------------------------------------------------
    # B. «Sale hoy: ¿hay alguien en casa?»
    # ------------------------------------------------------------------

    def _dcasa_avisar_sale_hoy(self, solo_chat=False):
        """Le avisa que su pedido sale hoy. Devuelve ``{'estado', 'canal', 'motivo', 'url_whatsapp'}`` con estado:

        * ``chat``: el asistente se lo escribe; ``ya_avisada``: ya se le escribió hoy (no se repite);
        * ``whatsapp``: sin chat, el enlace de WhatsApp para una persona (``a_mano`` con ``solo_chat``: no arma nada);
        * ``sin_celular``, ``no_confirmada``, ``no_va`` (no va a domicilio)."""
        self.ensure_one()
        orden = self.sudo()
        if orden.state != 'sale':
            return {'estado': 'no_confirmada'}
        if not orden._dcasa_va_a_domicilio():
            return {'estado': 'no_va'}
        hoy = hoy_en_panama()
        if orden.dcasa_aviso_sale_hoy_el == hoy and orden.dcasa_aviso_sale_hoy_por == 'chat' \
                and orden.dcasa_aviso_sale_hoy_mensaje_id.estado_envio != 'fallido':
            return {'estado': 'ya_avisada'}     # si no se pudo enviar (Worker caído), se puede volver a avisar
        destino = orden._dcasa_destino()
        sin_punto = not destino._dcasa_ubic_confiable()
        Enlace = self.env['dcasa.ubicacion.enlace']
        conv, motivo = orden._dcasa_conversacion_para_avisar()
        if conv:
            url = Enlace._crear(destino, conversacion=conv, creado_por='aviso', orden=orden)[1] if sin_punto else None
            mensaje = conv._dcasa_escribir_como_asistente(orden._dcasa_texto_sale_hoy(url))
            valores = {'dcasa_aviso_sale_hoy_el': hoy, 'dcasa_aviso_sale_hoy_por': 'chat',
                       'dcasa_aviso_sale_hoy_mensaje_id': mensaje.id}
            if sin_punto and not orden.dcasa_ubic_pedida_el:
                valores['dcasa_ubic_pedida_el'] = fields.Datetime.now()
            orden.write(valores)
            canal = ETIQUETA_CANAL.get(conv.canal, conv.canal)
            conv._aviso(self.env._(
                '🚚 Se le avisó que hoy sale su pedido %s. Si dice que no habrá nadie o quiere cambiar el día o la '
                'hora, el asistente la pasa a una vendedora.', orden.name))
            orden._dcasa_avisos_nota(self.env._(
                '🚚 Se le avisó a la clienta por el chat (%s) que hoy sale su pedido.', canal))
            return {'estado': 'chat', 'canal': canal, 'motivo': ''}
        if solo_chat:
            return {'estado': 'a_mano', 'motivo': motivo}
        numero = orden._dcasa_celular_para_whatsapp()
        if not numero:
            return {'estado': 'sin_celular', 'motivo': motivo}
        url = Enlace._crear(destino, creado_por='aviso', orden=orden)[1] if sin_punto else None
        orden.write({'dcasa_aviso_sale_hoy_el': hoy, 'dcasa_aviso_sale_hoy_por': 'whatsapp'})
        return {'estado': 'whatsapp', 'motivo': motivo,
                'url_whatsapp': url_whatsapp(numero, orden._dcasa_texto_sale_hoy(url))}

    def _dcasa_avisar_sale_hoy_seguro(self, solo_chat=False):
        """Lo mismo, en su savepoint: un error en una venta no tumba las demás de la lista."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                return self._dcasa_avisar_sale_hoy(solo_chat=solo_chat)
        except Exception:   # noqa: BLE001
            _logger.exception('Avisos: no se pudo avisar que sale hoy la venta %s.', self.id)
            return {'estado': 'error'}

    def _dcasa_exigir_ventas(self):
        if not self.env.user.has_group(GRUPO_VENTAS):
            raise AccessError(self.env._('Solo el equipo de ventas le escribe a la clienta.'))

    def action_dcasa_avisar_sale_hoy(self):
        """Botón «🚚 Sale hoy: avisarle» (una venta: si no hay chat, abre WhatsApp) y la acción de la lista (varias:
        solo por el chat; las demás se dicen para mandarlas una por una)."""
        self._dcasa_exigir_ventas()
        self.check_access('write')
        if len(self) == 1:
            resultado = self._dcasa_avisar_sale_hoy_seguro()
            if resultado['estado'] == 'whatsapp':
                return {'type': 'ir.actions.act_url', 'url': resultado['url_whatsapp'], 'target': 'new'}
            return self._dcasa_notificacion_sale_hoy(resultado)
        por_estado = {}
        for orden in self:
            por_estado.setdefault(orden._dcasa_avisar_sale_hoy_seguro(solo_chat=True)['estado'], []).append(orden.name)
        return self._dcasa_notificacion_varias(por_estado)

    def _dcasa_notificacion_sale_hoy(self, resultado):
        estado = resultado['estado']
        textos = {
            'chat': ('success', self.env._('📲 El asistente le escribe por el chat (%s): sale en un momento.',
                                           resultado.get('canal', ''))),
            'ya_avisada': ('info', self.env._('Ya se le avisó hoy por el chat: no se le manda otra vez.')),
            'no_confirmada': ('warning', self.env._('La venta todavía no está confirmada.')),
            'no_va': ('warning', self.env._('Esta venta no va a domicilio.')),
            'sin_celular': ('warning', self.env._(
                'No se le puede escribir por el chat (%s) y no tiene un celular anotado: escríbelo en el contacto.',
                resultado.get('motivo') or '—')),
            'error': ('danger', self.env._('No se pudo avisar: quedó en el registro del sistema.')),
        }
        tipo, mensaje = textos.get(estado, textos['error'])
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': tipo, 'title': self.env._('🚚 Sale hoy'), 'message': mensaje, 'sticky': tipo != 'success'}}

    def _dcasa_notificacion_varias(self, por_estado):
        etiquetas = {
            'chat': self.env._('📲 Avisadas por el chat'),
            'a_mano': self.env._('Sin chat abierto (ábrelas una por una y toca «🚚 Sale hoy: avisarle»)'),
            'ya_avisada': self.env._('Ya avisadas hoy'),
            'no_confirmada': self.env._('Sin confirmar'),
            'no_va': self.env._('No van a domicilio'),
            'error': self.env._('No se pudo (quedó en el registro)'),
        }
        partes = [f'{etiquetas.get(estado, estado)}: {", ".join(nombres)}.' for estado, nombres in por_estado.items()]
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'info', 'sticky': True, 'title': self.env._('🚚 Sale hoy'),
            'message': ' '.join(partes) or self.env._('Marca las ventas que salen hoy.')}}


class StockPickingAvisos(models.Model):
    _inherit = 'stock.picking'

    def action_dcasa_avisar_sale_hoy(self):
        """Botón «🚚 Sale hoy: avisarle» en la entrega: lo mismo que en su venta."""
        self.ensure_one()
        self.check_access('read')
        if self.picking_type_code != 'outgoing' or not self.sale_id:
            raise UserError(self.env._('Esta entrega no es de una venta a una clienta.'))
        return self.sale_id.action_dcasa_avisar_sale_hoy()
