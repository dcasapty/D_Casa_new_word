"""El precio del envío en el checkout sale del punto de entrega (docs/UBICACION.md).

La entrega «a domicilio» (la que se cotizaba por WhatsApp, ``dcasa_por_cotizar``) da precio cuando la dirección de
entrega tiene un punto confirmado y el lugar de la tabla más cercano tiene precio con las reglas de siempre (tarifa
aprobada, lugar revisado, no «se cotiza aparte»). Si no, sigue como hoy: «por cotizar». La línea del envío queda como
la que pone Juan (``dcasa_envio_lugar_id``) y, si la promoción de envío de hoy aplica, con su línea.
"""
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.addons.dcasa_envios.motor import choferes
from odoo.addons.dcasa_envios.motor import tarjeta as motor_tarjeta

from ..motor import geo
from .zona import UbicacionInvalida


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    def fixed_rate_shipment(self, order):
        resultado = super().fixed_rate_shipment(order)
        if resultado.get('success') and self.dcasa_por_cotizar:
            envio = order._dcasa_envio_por_ubicacion()
            if envio:
                resultado = dict(resultado, price=envio['total'])
        return resultado


SIN_PENDIENTE = {'dcasa_ubic_pend_lat': 0, 'dcasa_ubic_pend_lon': 0, 'dcasa_ubic_pend_precision': 0,
                 'dcasa_ubic_pend_referencia': False}
MISMO_SITIO_M = 30      # el punto del chat a menos de esto de la dirección de entrega: es la misma casa
MAX_LUGAR_TARJETA = 60  # lo que cabe en «No, en …» y en «En el chat nos dio: …»


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # El punto que el cliente dio en el chat de la tienda (Andrés) antes de pagar: solo para llenar el checkout, donde
    # lo confirma con «Sí, aquí es» (controllers/tienda.py).
    dcasa_ubic_pend_lat = fields.Float('Latitud (del chat)', digits=(10, 7), readonly=True, copy=False)
    dcasa_ubic_pend_lon = fields.Float('Longitud (del chat)', digits=(10, 7), readonly=True, copy=False)
    dcasa_ubic_pend_precision = fields.Integer('Precisión del GPS (del chat)', readonly=True, copy=False)
    dcasa_ubic_pend_referencia = fields.Char('Indicaciones (del chat)', readonly=True, copy=False)

    @api.autovacuum
    def _gc_puntos_pendientes(self):
        """El punto que dio en el chat de la tienda se queda en el carrito solo para llenar el checkout: en un carrito
        abandonado (sin tocar en 30 días) se borra (auditoría 2: eran coordenadas exactas sin limpieza)."""
        limite = fields.Datetime.now() - timedelta(days=30)
        self.sudo().search([('state', '=', 'draft'), ('write_date', '<', limite),
                            '|', ('dcasa_ubic_pend_lat', '!=', 0),
                            ('dcasa_ubic_pend_referencia', '!=', False)]).write(SIN_PENDIENTE)

    def _dcasa_ubic_pendiente(self):
        """``{'lat', 'lon', 'precision', 'referencia'}`` del punto que dio en el chat de la tienda, o ``None``."""
        self.ensure_one()
        orden = self.sudo()
        punto = geo.punto(orden.dcasa_ubic_pend_lat, orden.dcasa_ubic_pend_lon)
        if not punto:
            return None
        return {'lat': punto[0], 'lon': punto[1], 'precision': orden.dcasa_ubic_pend_precision or None,
                'referencia': orden.dcasa_ubic_pend_referencia or ''}

    def _dcasa_ubic_pend_casa(self):
        """La casa (número e indicaciones) que escribió en el chat de la tienda, aunque el GPS no sirviera (auditoría 2:
        con un GPS impreciso no pasaba nada al checkout), o ``''``."""
        self.ensure_one()
        return self.sudo().dcasa_ubic_pend_referencia or ''

    def _dcasa_ubic_hay_pendiente(self):
        """¿Queda algo del chat de la tienda en el carrito (el punto o solo la casa)?"""
        self.ensure_one()
        orden = self.sudo()
        return bool(orden.dcasa_ubic_pend_lat or orden.dcasa_ubic_pend_lon or orden.dcasa_ubic_pend_referencia)

    def _dcasa_ubic_chat_distinto(self):
        """Para la tarjeta de arriba de ``/shop/checkout`` (auditoría 2): alguien que ya tiene dirección no pasa por el
        formulario, así que el punto que dio en el chat de la tienda nunca llegaba aunque Andrés dijera «Listo». Si el
        carrito tiene ese punto y NO es el de la dirección de entrega elegida (a más de 30 m, o ella sin punto),
        ``{'donde': 'Barriada Nueva Ficción, Oficina 3', 'actual': 'Villa Prueba II', 'url_si': '/shop/address?…'}``;
        si no, ``None``. Sin coordenadas en lo que devuelve: ``url_si`` abre esa dirección con el punto del chat."""
        self.ensure_one()
        orden = self.sudo()
        pendiente = orden._dcasa_ubic_pendiente()
        if not pendiente or orden.state not in ('draft', 'sent') or not orden._has_deliverable_products():
            return None
        destino = orden.partner_shipping_id
        # El carrito de una visita que todavía no dio su dirección es del usuario público: ahí no hay qué preguntar.
        if not destino or destino == orden.website_id.user_id.sudo().partner_id:
            return None
        punto = destino._dcasa_ubic_punto()
        if punto and choferes.distancia_m(punto[0], punto[1], pendiente['lat'], pendiente['lon']) <= MISMO_SITIO_M:
            return None
        try:
            _lat, _lon, zona = self.env['dcasa.ubicacion']._validar(pendiente['lat'], pendiente['lon'])
        except UbicacionInvalida:
            return None
        lugar = zona.get('barriada') or zona.get('corregimiento') or zona.get('distrito') or ''
        donde = ', '.join(p for p in (lugar, pendiente['referencia']) if p)
        actual = ((destino.dcasa_ubic_zona or '').split(' · ')[0] or destino.street or destino.city or '').strip()
        return {
            'donde': geo.texto_corto(donde, MAX_LUGAR_TARJETA) or self.env._('tu ubicación'),
            'actual': geo.texto_corto(actual, MAX_LUGAR_TARJETA),
            'url_si': f'/shop/address?partner_id={destino.id}&address_type=delivery&dcasa_chat=1',
        }

    def _dcasa_envio_por_ubicacion(self):
        """``{'lugar', 'total', 'total_txt'}`` si la dirección de entrega tiene un punto confirmado con precio; si no,
        ``None`` (sin punto, escrita a mano, sin lugar a 3 km, tarifa en revisión, lugar sin revisar o aparte)."""
        self.ensure_one()
        destino = (self.partner_shipping_id or self.partner_id).sudo()
        if not destino or not destino.dcasa_ubic_confirmada or not destino._dcasa_ubic_punto():
            return None
        precio = self.env['dcasa.ubicacion']._precio(destino.dcasa_ubic_lugar_id)
        return precio if precio['con_precio'] else None

    def _dcasa_ubic_no_recalcular(self):
        """Por qué NO se recalcula solo el envío de este pedido al marcar el punto (``''`` si se puede): con un pago en
        curso o hecho (cambiar el total hace que el pago ya no confirme la venta) o con un envío que puso una persona
        (dcasa_envios: esos no se reemplazan solos)."""
        self.ensure_one()
        orden = self.sudo()
        # También un pago recién abierto que la pasarela todavía tiene en borrador (Tilopay no pasa a «pendiente»
        # mientras el cliente está en su página): si el total cambia, paga el viejo y la venta no se confirma
        # (auditoría 2). Uno de hace más de 2 horas ya no cuenta.
        reciente = fields.Datetime.now() - timedelta(hours=2)
        if orden.transaction_ids.filtered(lambda t: t.state in ('pending', 'authorized', 'done')
                                          or (t.state == 'draft' and t.create_date and t.create_date > reciente)):
            return 'pago'
        # El «por cotizar» en $0 que pone la web sin punto no es de una persona: ese sí se reemplaza.
        if any(linea._dcasa_envio_ajeno() and linea.price_unit > 0 for linea in orden.order_line):
            return 'ajeno'
        return ''

    def _dcasa_ubic_nota_sin_recalcular(self, zona, motivo):
        """La nota al equipo cuando el envío no se recalculó (sin coordenadas)."""
        self.ensure_one()
        precio = self.env['dcasa.ubicacion']._precio(zona.get('lugar'))
        donde = (zona.get('texto') or '').replace(' · ', ', ') or self.env._('sin zona de la tabla')
        porque = (self.env._('ya tiene un pago en curso') if motivo == 'pago'
                  else self.env._('el envío lo puso una persona'))
        tabla = (self.env._('con la tabla sería %s', precio['total_txt']) if precio['con_precio']
                 else self.env._('la tabla no da precio para esa zona'))
        self.sudo().message_post(body=Markup('<p>%s</p>') % escape(self.env._(
            '📍 El cliente marcó su casa: %(zona)s. 🚚 El envío no se cambió porque %(porque)s (%(tabla)s): decidan '
            'si se ajusta.', zona=donde, porque=porque, tabla=tabla)), subtype_xmlid='mail.mt_note')

    def _dcasa_ubic_elegir_domicilio(self):
        """El cliente marcó su casa en el mapa: la entrega pasa a «a domicilio» si estaba en «Retiro en tienda» (o sin
        elegir). Solo en el carrito (borrador o enviada), con algo que entregar y sin un pago en curso (cambiar el
        método cambia el total y el pago ya abierto no confirmaría la venta). Devuelve ``True`` si la cambió."""
        self.ensure_one()
        orden = self.sudo()
        if orden.state not in ('draft', 'sent') or orden.locked or not orden._has_deliverable_products():
            return False
        if orden.carrier_id.dcasa_por_cotizar or orden._dcasa_ubic_no_recalcular() == 'pago':
            return False
        domicilio = self.env['delivery.carrier'].sudo().search(
            [('dcasa_por_cotizar', '=', True), ('is_published', '=', True)], order='sequence, id', limit=1)
        if not domicilio:
            return False
        orden._set_delivery_method(domicilio)
        return True

    def set_delivery_line(self, carrier, amount):
        # «Agregar envío» / «Actualizar costo» del panel: con el precio del punto, la línea queda como la del sistema
        # (con su lugar y la promoción de hoy), igual que en la web (auditoría 1: quedaba sin promoción y «de persona»).
        resultado = super().set_delivery_line(carrier, amount)
        if carrier and carrier.dcasa_por_cotizar:
            for orden in self:
                orden._dcasa_marcar_envio_por_ubicacion()
        return resultado

    def _set_delivery_method(self, delivery_method, rate=None):
        resultado = super()._set_delivery_method(delivery_method, rate=rate)
        if delivery_method and delivery_method.dcasa_por_cotizar:
            for orden in self:
                orden._dcasa_marcar_envio_por_ubicacion()
        return resultado

    def _dcasa_marcar_envio_por_ubicacion(self):
        """La línea del envío que acaba de poner Odoo (con el precio del punto) queda como la del sistema: con su
        lugar y su nombre, y con la promoción de envío si aplica hoy. Solo en el carrito (borrador o enviada)."""
        self.ensure_one()
        if self.state not in ('draft', 'sent') or self.locked:
            return
        envio = self._dcasa_envio_por_ubicacion()
        if not envio:
            return
        orden = self.sudo()
        linea = orden.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)[-1:]
        if not linea or linea.dcasa_envio_lugar_id == envio['lugar']:
            return
        lugar = envio['lugar']
        linea.write({'name': self.env._('Envío a domicilio: %s', motor_tarjeta.lugar_con_zona(lugar._como_motor())),
                     'dcasa_envio_lugar_id': lugar.id})
        resultado, terminos = orden._dcasa_promocion_calcular(linea)
        if terminos:
            orden._dcasa_promocion_crear(linea, resultado, terminos)
