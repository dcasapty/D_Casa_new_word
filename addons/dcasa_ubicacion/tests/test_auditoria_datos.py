"""Lo que encontró la auditoría 1 de corrección y datos (2026-11-25), ya arreglado: cada prueba fallaba antes del
arreglo (el auditor las escribió para reproducir el fallo; aquí van al revés)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_envios.motor import choferes
from odoo.tests import tagged

from .common import CERCA, UbicacionCase


@tagged('post_install', '-at_install')
class TestAuditoriaDatos(UbicacionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Cuna auditoría', 'list_price': 250, 'type': 'consu',
                                                          'sale_ok': True, 'is_published': True})
        cls.barato = cls.env['product.product'].create({'name': 'Chupón auditoría', 'list_price': 20, 'type': 'consu',
                                                        'sale_ok': True})
        cls.Enlace = cls.env['dcasa.ubicacion.enlace'].sudo()
        # Otro lugar con coordenadas, a más de 5 km de CERCA (la casa de la mamá).
        cls.OTRA = None
        for lugar in cls.env['dcasa.envio.lugar'].search([('lat', '!=', False), ('lon', '!=', False)]):
            if lugar.lat and lugar.lon and choferes.distancia_m(CERCA[0], CERCA[1], lugar.lat, lugar.lon) > 5000:
                cls.OTRA = (lugar.lat, lugar.lon)
                break

    def venta(self, partner, producto=None, envio=None, shipping=None):
        valores = {'partner_id': partner.id, 'order_line': [(0, 0, {'product_id': (producto or self.producto).id})]}
        if shipping:
            valores['partner_shipping_id'] = shipping.id
        orden = self.env['sale.order'].create(valores)
        if envio is None:
            orden.carrier_id = self.domicilio
        else:
            orden.set_delivery_line(self.domicilio, envio)
        return orden

    def precio_tabla(self):
        return self.env['dcasa.envio.tarifa'].sudo().cotizar_lugar(self.villa)['total']

    # 1. «Para otra casa»

    def test_para_otra_casa_no_pisa_la_casa_de_la_cliente_ni_la_ruta_de_su_venta(self):
        if not self.OTRA:
            self.skipTest('la tabla de prueba no tiene un segundo lugar lejos')
        conv = self.conversacion(id_externo='50761239901')
        cliente = conv.partner_id
        cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1, la mía')
        orden = self.venta(cliente)
        orden.action_confirm()
        entrega = orden._dcasa_entrega_chofer()
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        Herramientas._juan_enlace_de_ubicacion(para_otra_casa=True)
        enlace = self.Enlace.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        self.assertNotEqual(enlace.partner_id, cliente)
        self.assertEqual((enlace.partner_id.parent_id, enlace.partner_id.type), (cliente, 'other'))
        enlace._confirmar(*self.OTRA, 'pin', referencia='Casa de mamá')
        self.assertEqual(cliente.dcasa_referencia, 'Casa 1, la mía', 'su casa no se toca')
        self.assertIn(f'{CERCA[0]:.7f}', entrega._para_el_chofer()['enlaces']['google'],
                      'la venta ya confirmada sigue yendo a SU casa')
        self.assertEqual(enlace.partner_id.dcasa_referencia, 'Casa de mamá')
        # Lo que Juan cotiza y guarda después en esta conversación es de la otra casa.
        self.assertEqual(conv._dcasa_ubic_destino(), enlace.partner_id)
        Herramientas._juan_guardar_indicaciones(texto='Portón verde')
        self.assertEqual(enlace.partner_id.dcasa_referencia, 'Portón verde')
        self.assertEqual(cliente.dcasa_referencia, 'Casa 1, la mía')

    # 2. El link de pago no cambia lo que ya se está pagando ni el envío de una persona

    def test_el_link_de_pago_no_reemplaza_el_envio_que_puso_la_vendedora(self):
        orden = self.venta(self.cliente, producto=self.barato, envio=37.0)
        orden.action_quotation_sent()
        total_antes = orden.amount_total
        enlace, _url = self.Enlace._crear(self.cliente, orden=orden)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        self.assertEqual(orden.amount_total, total_antes)
        self.assertEqual(orden.order_line.filtered('is_delivery').mapped('price_unit'), [37.0])
        self.assertIn('el envío lo puso una persona', ' '.join(orden.message_ids.mapped('body')))

    def test_el_link_de_pago_con_un_pago_pendiente_no_cambia_lo_que_se_debe(self):
        orden = self.venta(self.cliente, producto=self.barato)
        orden._set_delivery_method(self.domicilio)
        self.cliente._dcasa_poner_escrita(referencia='Casa 9')
        orden.action_quotation_sent()
        proveedor = self.env.ref('payment.payment_provider_transfer').sudo()
        proveedor.state = 'test'
        metodo = proveedor.payment_method_ids[:1] or self.env.ref('payment_custom.payment_method_wire_transfer')
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': proveedor.id, 'payment_method_id': metodo.id, 'reference': f'AUD-{orden.id}',
            'amount': orden.amount_total, 'currency_id': orden.currency_id.id, 'partner_id': self.cliente.id,
            'sale_order_ids': [(6, 0, orden.ids)], 'operation': 'online_redirect'})
        tx._set_pending()
        debia = orden.amount_total
        enlace, _url = self.Enlace._crear(self.cliente, orden=orden)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        self.assertEqual(orden.amount_total, debia, 'con la transferencia en curso, el total no se toca')
        self.assertIn('ya tiene un pago en curso', ' '.join(orden.message_ids.mapped('body')))

    def test_sin_pago_ni_envio_de_persona_el_link_de_pago_si_pone_el_precio_del_punto(self):
        orden = self.venta(self.cliente, producto=self.barato)
        orden._set_delivery_method(self.domicilio)
        orden.action_quotation_sent()
        enlace, _url = self.Enlace._crear(self.cliente, orden=orden)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        envio = orden.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)
        self.assertEqual((envio.price_unit, envio.dcasa_envio_lugar_id), (self.precio_tabla(), self.villa))

    # 4. «Agregar envío» del panel

    def test_agregar_envio_del_panel_queda_como_el_del_sistema_con_su_promocion(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        web = self.venta(self.cliente)
        web._set_delivery_method(self.domicilio)
        con_promocion_en_la_web = bool(web.order_line.filtered('dcasa_promocion_envio_id'))
        panel = self.env['sale.order'].create({'partner_id': self.cliente.id,
                                               'order_line': [(0, 0, {'product_id': self.producto.id})]})
        asistente = self.env['choose.delivery.carrier'].create({'order_id': panel.id, 'carrier_id': self.domicilio.id})
        asistente._onchange_carrier_id()
        asistente.button_confirm()
        linea = panel.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)
        self.assertEqual(linea.dcasa_envio_lugar_id, self.villa, 'la línea queda como la del sistema')
        self.assertFalse(linea._dcasa_envio_ajeno())
        self.assertEqual(bool(panel.order_line.filtered('dcasa_promocion_envio_id')), con_promocion_en_la_web,
                         'con la misma promoción que en la web')

    # 6. La ubicación del clip va a la dirección de entrega de la venta avisada

    def test_la_ubicacion_del_chat_llega_a_la_direccion_de_entrega_de_la_venta_avisada(self):
        conv = self.conversacion(id_externo='50761239902')
        cliente = conv.partner_id
        casa = self.env['res.partner'].create({'name': 'Casa de Ana', 'type': 'delivery', 'parent_id': cliente.id,
                                               'street': 'Calle 1'})
        orden = self.venta(cliente, shipping=casa)
        orden.action_confirm()
        # El aviso al comprar (o «Sale hoy») le pidió el punto de ESA dirección por este chat.
        self.Enlace._crear(casa, conversacion=conv, creado_por='aviso', orden=orden)
        self.assertEqual(conv._dcasa_ubic_destino(para_punto=True), casa)
        conv._dcasa_ubic_destino(para_punto=True)._dcasa_poner_ubicacion(*CERCA, 'whatsapp', confirmada=True)
        orden.invalidate_recordset(['dcasa_falta_punto'])
        self.assertFalse(orden.dcasa_falta_punto)
        self.assertFalse(cliente._dcasa_ubic_punto(), 'su propia ficha no se toca')

    # 9 y la revisión de seguridad: el QR del chofer

    def test_el_qr_sirve_mientras_no_se_entregue_y_se_cierra_despues(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        orden = self.venta(self.cliente)
        orden.action_confirm()
        entrega = orden._dcasa_entrega_chofer()
        token = entrega.sudo().token
        entrega.sudo().vence = fields.Datetime.now() - timedelta(days=1)   # un apartado que sale a los 31 días
        Entrega = self.env['dcasa.ubicacion.entrega']
        self.assertEqual(Entrega._del_secreto(token), entrega, 'sin entregar, el QR impreso sigue abriendo')
        salida = orden.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        salida.sudo().write({'state': 'done', 'date_done': fields.Datetime.now() - timedelta(days=4)})
        self.assertFalse(Entrega._del_secreto(token), 'entregada hace 4 días: cerrada')
        # El cliente se muda: la página vieja NO revive con su casa nueva (secreto nuevo).
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa nueva')
        orden._dcasa_entrega_chofer()
        self.assertFalse(Entrega._del_secreto(token))

    def test_cancelada_la_pagina_del_chofer_se_cierra(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        orden = self.venta(self.cliente)
        orden.action_confirm()
        token = orden._dcasa_entrega_chofer().sudo().token
        orden._action_cancel()
        self.assertFalse(self.env['dcasa.ubicacion.entrega']._del_secreto(token))

    # 10. El «¡Listo!» no dice un precio sin la promoción

    def test_el_listo_no_dice_un_precio_que_contradiga_la_promocion(self):
        conv = self.conversacion(id_externo='50761239903')
        enlace, _url = self.Enlace._crear(conv.partner_id, conversacion=conv, creado_por='juan')
        with patch.object(type(enlace), '_promocion_de_envio', return_value='aplica'):
            enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        mensaje = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('origen', '=', 'odoo'),
                                                           ('tipo', '=', 'mensaje')], order='id desc', limit=1)
        self.assertIn('tiene promoción', mensaje.texto)
        self.assertNotIn('$', mensaje.texto)
        self.assertEqual(mensaje.estado_envio, 'por_enviar', 'sale por la cola: nada de commit a mitad de la página')

    # 12 y 13. Los avisos

    def test_cancelar_la_venta_cierra_el_pendiente_de_pedir_la_ubicacion(self):
        cliente = self.env['res.partner'].create({'name': 'Rosa Cancela', 'phone': '+507 6123-9771'})
        orden = self.venta(cliente)
        orden.action_confirm()
        tipo = self.env.ref('dcasa_ubicacion.actividad_pedir_ubicacion')
        self.assertEqual(len(orden.activity_ids.filtered(lambda a: a.activity_type_id == tipo)), 1)
        orden._action_cancel()
        self.assertFalse(orden.activity_ids.filtered(lambda a: a.activity_type_id == tipo))

    def test_un_sale_hoy_que_no_salio_se_puede_volver_a_mandar(self):
        conv = self.conversacion(id_externo='50761239904')
        conv.partner_id._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        orden = self.venta(conv.partner_id)
        orden.action_confirm()
        with patch.dict('os.environ', {'JUAN_URL': 'https://juan.prueba.example.com', 'JUAN_WORKER_TOKEN': 'w' * 40}):
            self.assertEqual(orden._dcasa_avisar_sale_hoy()['estado'], 'chat')
            self.assertEqual(orden._dcasa_avisar_sale_hoy()['estado'], 'ya_avisada', 'dos toques: uno solo')
            orden.dcasa_aviso_sale_hoy_mensaje_id.with_context(dcasa_mensaje_sistema=True).write(
                {'estado_envio': 'fallido'})
            self.assertEqual(orden._dcasa_avisar_sale_hoy()['estado'], 'chat', 'no salió: se puede volver a avisar')

    def test_el_aviso_no_le_cuenta_el_regalo_a_quien_lo_recibe(self):
        compradora = self.conversacion(id_externo='50761239905').partner_id
        mama = self.conversacion(id_externo='50761239906').partner_id     # otra persona, con su propio chat
        orden = self.venta(compradora, shipping=mama)
        self.assertNotIn(mama, orden._dcasa_personas_de_la_compra())
        self.assertIn(compradora, orden._dcasa_personas_de_la_compra())
