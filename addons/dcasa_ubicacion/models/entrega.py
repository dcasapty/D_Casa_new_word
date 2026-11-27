"""La entrega de una venta para el motorizado: el QR del comprobante y de la nota de entrega abre ``/entrega/<secreto>``
con «Abrir en Waze», «Abrir en Google Maps», la foto de la casa, la dirección, la referencia, quién recibe, «Avisar que
llegué» (WhatsApp con el mensaje listo), «Llamar» y el teléfono de respaldo.

A diferencia de Nébula, la página **vence** (``DIAS_VIGENCIA`` días desde que se armó o se puso al día) y **no cambia
nada** (no marca «entregado»): quien encuentre el papel no puede tocar el pedido. El secreto va en el QR, así que se
guarda en un campo que solo lee el equipo de ventas.
"""
import base64
from datetime import timedelta

import psycopg2

from odoo import api, fields, models

from ..motor import casa, geo

DIAS_VIGENCIA = 30
DIAS_TRAS_ENTREGAR = 3     # después de entregado, la página se cierra a los 3 días
DIAS_MAXIMOS = 90          # tope absoluto desde la compra, aunque la salida nunca se valide (auditoría 2)
RUTA = '/entrega/'
QR_PIXELES = 240


class UbicacionEntrega(models.Model):
    _name = 'dcasa.ubicacion.entrega'
    _description = 'Entrega para el motorizado (QR)'
    _order = 'id desc'

    token = fields.Char(required=True, readonly=True, copy=False, index=True,
                        groups='sales_team.group_sale_salesman,account.group_account_invoice')
    order_id = fields.Many2one('sale.order', 'Venta', required=True, readonly=True, ondelete='cascade', index=True)
    vence = fields.Datetime(required=True, readonly=True)

    _venta_unica = models.Constraint('UNIQUE(order_id)', 'Cada venta tiene una sola entrega.')

    @api.model
    def _de_la_venta(self, orden, crear=True):
        """La entrega de esa venta. Con ``crear`` la arma si no existe y le pone la vigencia al día; sin ``crear``
        solo la busca y no escribe nada (el PDF se arma en una transacción de solo lectura: ``/report`` de Odoo 19)."""
        orden = orden.sudo()
        entrega = self.sudo().search([('order_id', '=', orden.id)], limit=1)
        if not crear:
            return entrega
        ahora = fields.Datetime.now()
        vence = ahora + timedelta(days=DIAS_VIGENCIA)
        if entrega:
            if not entrega._abierta():
                # Cerrada (vencida o entregada hace días): el QR viejo NO revive (auditoría 1: quien guardó un papel de
                # hace meses veía la casa nueva de la clienta). Secreto nuevo; el QR nuevo sale al imprimir otra vez.
                entrega.write({'token': geo.token_nuevo(18), 'vence': vence})
            elif entrega.vence < vence - timedelta(days=1):
                entrega.write({'vence': vence})
            return entrega
        try:
            with self.env.cr.savepoint():
                return self.sudo().create({'order_id': orden.id, 'token': geo.token_nuevo(18), 'vence': vence})
        except psycopg2.IntegrityError:
            # Otra petición la armó al mismo tiempo (confirmar y publicar la factura a la vez): se usa esa. Nunca hace
            # fallar la confirmación ni la factura.
            return self.sudo().search([('order_id', '=', orden.id)], limit=1)

    @api.model
    def _del_secreto(self, token):
        """La entrega vigente de ese secreto, o un registro vacío (vencida o inexistente: lo mismo)."""
        if not isinstance(token, str) or not 16 <= len(token) <= 64:
            return self.sudo().browse()
        entrega = self.sudo().search([('token', '=', token)], limit=1)
        return entrega if entrega and entrega._abierta() else self.sudo().browse()

    def _abierta(self):
        """¿Le sirve todavía la página al motorizado? Mientras la venta tenga una salida sin entregar (un pedido que
        sale a los 40 días no puede imprimir un QR vencido: auditoría 1), pero nunca más de ``DIAS_MAXIMOS`` días
        desde la compra; entregada, hasta ``DIAS_TRAS_ENTREGAR`` días después; cancelada, nunca; sin salidas, hasta
        que vence."""
        self.ensure_one()
        orden = self.sudo().order_id
        if not orden or orden.state == 'cancel':
            return False
        # Tope absoluto: si en la tienda no se validan las salidas, la página no puede quedar abierta para siempre.
        if orden.date_order and orden.date_order < fields.Datetime.now() - timedelta(days=DIAS_MAXIMOS):
            return False
        salidas = orden.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
        if any(p.state != 'done' for p in salidas):
            return True
        if salidas:
            entregada = max((p.date_done for p in salidas if p.date_done), default=None)
            return bool(entregada) and entregada > fields.Datetime.now() - timedelta(days=DIAS_TRAS_ENTREGAR)
        return self.vence > fields.Datetime.now()

    def _url(self):
        self.ensure_one()
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        website = self.order_id.sudo().website_id or self.env['website'].sudo().search([], limit=1)
        if website and website.domain:
            dominio = website.domain if '://' in website.domain else 'https://' + website.domain
            base = dominio.rstrip('/')
        return f'{base}{RUTA}{self.sudo().token}'

    def _para_el_motorizado(self):
        """Lo que ve el motorizado: nombre de pila, teléfono, la dirección y el punto (con sus dos botones), quién
        recibe, «Avisar que llegué» (WhatsApp al celular de la clienta con el mensaje listo), el teléfono de respaldo
        (llamar y, si es celular, WhatsApp) y la foto de la casa (por su ruta con el mismo secreto). No escribe nada: lo
        lee también el PDF, que se arma en una transacción de solo lectura."""
        self.ensure_one()
        orden = self.order_id.sudo()
        destino = orden.partner_shipping_id or orden.partner_id
        resumen = destino._dcasa_ubic_resumen()
        nombre = (destino.name or orden.partner_id.name or '').strip()
        pila = nombre.split()[0] if nombre else ''
        telefono = destino.phone or orden.partner_id.phone or ''
        tienda = self._nombre_de_la_tienda()
        respaldo = casa.telefono_de_respaldo(resumen['telefono_respaldo'])
        if respaldo and casa.mismo_telefono(respaldo['guardar'], telefono):
            respaldo = None     # el mismo celular de la clienta: un botón de más que confunde
        resumen.update({
            'pedido': orden.name,
            'nombre': pila,
            'telefono': telefono,
            'telefono_tel': casa.tel(telefono),
            'nota': geo.texto_corto(orden.client_order_ref or '', 120),
            'avisar_llegue': casa.enlace_whatsapp(casa.numero_whatsapp(telefono),
                                                  self._texto_llegue(tienda, orden.name, pila)),
            'respaldo': respaldo['guardar'] if respaldo else '',
            'respaldo_tel': respaldo['tel'] if respaldo else '',
            # Al respaldo le escribe a otra persona (la abuela, el guardia): el pedido es «de Ana».
            'respaldo_whatsapp': casa.enlace_whatsapp(respaldo['wa'], self._texto_llegue(
                tienda, orden.name, de=pila)) if respaldo else '',
            'fachada_url': f'{RUTA}{self.sudo().token}/fachada' if resumen['tiene_foto_fachada'] else '',
        })
        return resumen

    def _nombre_de_la_tienda(self):
        """El nombre con que el motorizado se presenta: el del sitio de la venta (o el de la compañía)."""
        self.ensure_one()
        orden = self.order_id.sudo()
        website = orden.website_id or self.env['website'].sudo().search([('company_id', '=', orden.company_id.id)],
                                                                        limit=1)
        return (website.name if website else '') or orden.company_id.name or ''

    def _texto_llegue(self, tienda, pedido, nombre='', de=''):
        """«Hola Ana, soy el motorizado de Baby Caleb 🛵. Ya llegué con su pedido S00042 📦» (de usted, corto). Para el
        teléfono de respaldo (otra persona): «Hola, soy el motorizado de Baby Caleb 🛵. Ya llegué con el pedido S00042
        de Ana 📦»."""
        saludo = self.env._('Hola %s', nombre) if nombre else self.env._('Hola')
        if de:
            return self.env._('%(saludo)s, soy el motorizado de %(tienda)s 🛵. Ya llegué con el pedido %(pedido)s de '
                              '%(de)s 📦', saludo=saludo, tienda=tienda, pedido=pedido, de=de)
        return self.env._('%(saludo)s, soy el motorizado de %(tienda)s 🛵. Ya llegué con su pedido %(pedido)s 📦',
                          saludo=saludo, tienda=tienda, pedido=pedido)

    def _qr_src(self):
        """El QR (``data:image/png;base64,…``) con la dirección de la página, incrustado en el PDF."""
        self.ensure_one()
        png = self.env['ir.actions.report'].barcode('QR', self._url(), width=QR_PIXELES, height=QR_PIXELES,
                                                    quiet=0, barLevel='M')
        return 'data:image/png;base64,' + base64.b64encode(png).decode()

    @api.autovacuum
    def _gc_entregas_vencidas(self):
        """Las entregas vencidas hace más de 90 días se borran (la venta sigue; al confirmar o publicar otra vez, se
        arma otra)."""
        self.sudo().search([('vence', '<', fields.Datetime.now() - timedelta(days=90))]).unlink()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_zona_entrega = fields.Char('Zona de entrega', related='partner_shipping_id.dcasa_ubic_zona')
    dcasa_recibe_entrega = fields.Char('Quién recibe', related='partner_shipping_id.dcasa_recibe')
    dcasa_tel_respaldo_entrega = fields.Char('Teléfono de respaldo', related='partner_shipping_id.dcasa_tel_respaldo')

    def _dcasa_va_a_domicilio(self):
        """¿Esta venta se lleva a domicilio? (El método de entrega «a domicilio» o una línea de envío del sistema.)"""
        self.ensure_one()
        orden = self.sudo()
        if orden.carrier_id and orden.carrier_id.dcasa_por_cotizar:
            return True
        return any(linea.dcasa_envio_lugar_id for linea in orden.order_line)

    def _dcasa_ubic_url_para_marcar(self):
        """La página «¡Gracias por su compra!» (y lo que la llame): si la venta va a domicilio y su dirección de entrega
        no tiene un punto confiable o le faltan el número de casa y las indicaciones, la dirección para marcarla en el
        mapa (``/u/pedido/<id>?access_token=…``, la misma de la página del pedido); si no, ``''``."""
        self.ensure_one()
        orden = self.sudo()
        if orden.state == 'cancel' or not orden._dcasa_va_a_domicilio():
            return ''
        if not orden._dcasa_ubic_falta_la_casa():
            return ''
        return f'/u/pedido/{orden.id}?access_token={orden._portal_ensure_token()}'

    def _dcasa_ubic_falta_la_casa(self):
        """¿Le falta la casa a la dirección de entrega? Sí si no tiene un punto **confiable** (sin punto, escrita,
        buscada sin mover el pin o un GPS de más de 100 m) o le faltan el número de casa y las indicaciones. Un solo
        criterio para «¡Gracias!» y la página del pedido (auditoría 1: el pedido miraba solo «hay punto»)."""
        self.ensure_one()
        resumen = (self.sudo().partner_shipping_id or self.sudo().partner_id)._dcasa_ubic_resumen()
        return not (resumen['confiable'] and resumen['referencia'])

    def _dcasa_entrega_motorizado(self, crear=True):
        """La entrega de esta venta para el QR, o un registro vacío si no va a domicilio o no tiene a dónde. Sin
        ``crear`` no escribe nada (para el PDF)."""
        self.ensure_one()
        if self.state == 'cancel' or not self._dcasa_va_a_domicilio():
            return self.env['dcasa.ubicacion.entrega']
        destino = (self.partner_shipping_id or self.partner_id).sudo()
        if not destino._dcasa_ubic_punto() and not (destino.street or destino.dcasa_referencia):
            return self.env['dcasa.ubicacion.entrega']
        return self.env['dcasa.ubicacion.entrega']._de_la_venta(self, crear=crear)

    def action_confirm(self):
        resultado = super().action_confirm()
        for orden in self:
            orden._dcasa_entrega_motorizado()
        return resultado

    def action_dcasa_abrir_entrega(self):
        """Panel: abre la página del motorizado (la misma del QR) en otra pestaña."""
        self.ensure_one()
        self.check_access('read')
        entrega = self._dcasa_entrega_motorizado()
        if not entrega:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'warning', 'title': self.env._('Sin entrega a domicilio'),
                'message': self.env._('Esta venta no va a domicilio o la clienta todavía no tiene dirección.')}}
        return {'type': 'ir.actions.act_url', 'url': entrega._url(), 'target': 'new'}


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _dcasa_entrega_para_el_qr(self):
        """La entrega (para el QR del motorizado) de la venta de este comprobante, o un registro vacío. No escribe."""
        self.ensure_one()
        if self.move_type != 'out_invoice' or self.state != 'posted':
            return self.env['dcasa.ubicacion.entrega']
        for orden in self.sudo().invoice_line_ids.sale_line_ids.order_id:
            entrega = orden._dcasa_entrega_motorizado(crear=False)
            if entrega:
                return entrega
        return self.env['dcasa.ubicacion.entrega']

    def _post(self, soft=True):
        publicados = super()._post(soft=soft)
        for factura in publicados.filtered(lambda m: m.move_type == 'out_invoice'):
            for orden in factura.sudo().invoice_line_ids.sale_line_ids.order_id:
                orden._dcasa_entrega_motorizado()
        return publicados


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _dcasa_entrega_para_el_qr(self):
        """La entrega (para el QR del motorizado) de la venta de esta salida, o un registro vacío."""
        self.ensure_one()
        if self.picking_type_code != 'outgoing' or not self.sale_id:
            return self.env['dcasa.ubicacion.entrega']
        return self.sale_id._dcasa_entrega_motorizado(crear=False)
