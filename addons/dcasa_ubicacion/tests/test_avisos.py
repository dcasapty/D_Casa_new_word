"""Los avisos de la entrega (models/avisos.py; el dueño, 2026-11-25: «el dolor número uno son los pedidos devueltos»).

A. Al confirmar una venta a domicilio sin la casa en el mapa: el asistente le pide el punto por el chat si puede
   escribirle ya (WhatsApp por QR y Telegram siempre; la API oficial, Instagram y Messenger solo dentro de las 24
   horas); si no, un pendiente para la vendedora y el botón «📲 Pedir ubicación por WhatsApp». Una vez por venta, sin
   tumbar la confirmación (ni con el Worker caído ni con un error).
B. «🚚 Sale hoy: avisarle»: una vez por venta y por día, por el chat o abriendo WhatsApp; desde la venta, la entrega, la
   lista y Brian.

Nada de coordenadas en los textos, las notas, las actividades ni el registro."""
import json
import os
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import unquote

import requests

from odoo import fields
from odoo.addons.dcasa_conversaciones.models.sale_origen import hoy_en_panama
from odoo.addons.dcasa_conversaciones.tests.common import TOKEN_WORKER, URL_WORKER
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import CERCA, UbicacionCase

LATITUD = str(CERCA[0])


class AvisosCase(UbicacionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Caja de avisos', 'list_price': 20, 'type': 'consu',
                                                          'sale_ok': True})
        cls.vendedora_avisos = new_test_user(cls.env, login='vend_avisos', name='Vendedora Avisos',
                                             groups='base.group_user,sales_team.group_sale_salesman')
        cls.Enlace = cls.env['dcasa.ubicacion.enlace'].sudo()
        cls.tipo = cls.env.ref('dcasa_ubicacion.actividad_pedir_ubicacion')

    def venta(self, partner, con_envio=True):
        orden = self.env['sale.order'].create({
            'partner_id': partner.id, 'user_id': self.vendedora_avisos.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})]})
        if con_envio:
            orden.carrier_id = self.domicilio
        return orden

    def del_bot(self, conv):
        return self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conv.id), ('tipo', '=', 'mensaje'), ('origen', '=', 'odoo')], order='id')

    def pendientes(self, orden):
        return self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'sale.order'), ('res_id', '=', orden.id), ('activity_type_id', '=', self.tipo.id)])

    def worker_caido(self):
        entorno = patch.dict(os.environ, {'JUAN_URL': URL_WORKER, 'JUAN_WORKER_TOKEN': TOKEN_WORKER})
        entorno.start()
        self.addCleanup(entorno.stop)
        parche = patch('requests.request', side_effect=requests.ConnectionError('sin red'))
        parche.start()
        self.addCleanup(parche.stop)

    def triggers(self):
        cron = self.env.ref('dcasa_conversaciones.ir_cron_mantenimiento')
        return self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)])

    def notas(self, orden):
        return ' '.join(orden.sudo().message_ids.mapped(lambda m: str(m.body or '')))


@tagged('post_install', '-at_install')
class TestPedirUbicacionAlComprar(AvisosCase):

    def test_sin_chat_queda_un_pendiente_y_el_boton_abre_whatsapp(self):
        cliente = self.env['res.partner'].create({'name': 'Rosa Sinchat', 'phone': '+507 6123-9001'})
        orden = self.venta(cliente)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')
        self.assertTrue(orden.dcasa_ubic_pedida_el)
        self.assertTrue(orden.dcasa_falta_punto)
        pendiente = self.pendientes(orden)
        self.assertEqual(len(pendiente), 1)
        self.assertEqual(pendiente.user_id, self.vendedora_avisos)
        self.assertEqual(pendiente.summary, '📍 Pedirle la ubicación de entrega')
        self.assertIn('Pedir ubicación por WhatsApp', str(pendiente.note))
        self.assertIn('no tiene un chat con la tienda', str(pendiente.note))
        # El botón: WhatsApp con el mismo texto y un enlace nuevo de un solo uso, ligado a la venta.
        accion = orden.with_user(self.vendedora_avisos).action_dcasa_pedir_ubicacion_whatsapp()
        self.assertEqual(accion['type'], 'ir.actions.act_url')
        self.assertTrue(accion['url'].startswith('https://api.whatsapp.com/send?phone=50761239001&text='),
                        accion['url'])
        texto = unquote(accion['url'].split('text=', 1)[1])
        self.assertTrue(texto.startswith('🛍️ ¡Gracias por tu compra!\n📍 Para que el chofer llegue directo a tu '
                                         'casa, márquela aquí: '), texto)
        enlace = self.Enlace.search([('orden_id', '=', orden.id)])
        self.assertEqual((len(enlace), enlace.creado_por, enlace.partner_id), (1, 'aviso', orden.partner_shipping_id))
        self.assertIn('/u/', texto)
        # Cuando el cliente marca su casa, el pendiente se da por hecho y el botón ya no hace falta.
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 7')
        self.assertFalse(self.pendientes(orden))
        orden.invalidate_recordset(['dcasa_falta_punto'])
        self.assertFalse(orden.dcasa_falta_punto)

    def test_con_whatsapp_qr_le_escribe_el_asistente_y_sale_despues_de_confirmar(self):
        conv = self.conversacion(id_externo='50761231001')
        simulado = self.configurar_worker()
        orden = self.venta(conv.partner_id)
        antes = self.triggers()
        orden.action_confirm()
        mensaje = self.del_bot(conv)
        self.assertEqual(len(mensaje), 1)
        self.assertEqual((mensaje.autor, mensaje.direccion, mensaje.estado_envio), ('bot', 'saliente', 'por_enviar'))
        self.assertTrue(mensaje.texto.startswith('🛍️ ¡Gracias por tu compra!\n📍 Para que el chofer llegue directo'))
        enlace = self.Enlace.search([('orden_id', '=', orden.id)])
        self.assertEqual((enlace.creado_por, enlace.conversacion_id), ('aviso', conv))
        self.assertIn('/u/', mensaje.texto)
        self.assertFalse(self.pendientes(orden), 'se lo pidió el asistente: no hay nada que hacer a mano')
        self.assertEqual(conv.estado, 'bot', 'a nombre del asistente: Juan sigue atendiendo')
        simulado.assert_not_called()
        self.assertGreater(self.triggers(), antes, 'se adelanta el cron que manda lo pendiente')
        aviso = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('tipo', '=', 'aviso')],
                                                         order='id desc', limit=1)
        self.assertIn(orden.name, aviso.texto)
        self.Mensaje._cron_reintentar_envios()
        self.assertEqual(mensaje.estado_envio, 'enviado')
        cuerpo = simulado.call_args.kwargs['json']
        self.assertEqual((cuerpo['autor'], cuerpo['canal']), ('bot', 'whatsapp_qr'))
        # Una sola vez por venta.
        orden._dcasa_pedir_ubicacion_al_confirmar()
        self.assertEqual(len(self.del_bot(conv)), 1)

    def test_whatsapp_oficial_solo_dentro_de_las_24_horas(self):
        self.ajustes.canal_whatsapp_cloud = True
        ahora = fields.Datetime.now()
        conv = self.conversacion(canal='whatsapp_cloud', id_externo='50761231002', ts=ahora - timedelta(hours=30))
        self.configurar_worker()
        vieja = self.venta(conv.partner_id)
        vieja.action_confirm()
        self.assertFalse(self.del_bot(conv), 'Meta pediría una plantilla aprobada (131047)')
        self.assertIn('24 horas', str(self.pendientes(vieja).note))
        self.registrar('¿Ya salió mi pedido?', canal='whatsapp_cloud', id_externo='50761231002',
                       ts=ahora - timedelta(hours=1))
        nueva = self.venta(conv.partner_id)
        nueva.action_confirm()
        self.assertEqual(len(self.del_bot(conv)), 1)
        self.assertFalse(self.pendientes(nueva))

    def test_quien_puede_escribir_sola_por_canal(self):
        ahora = fields.Datetime.now()
        self.ajustes.write({'canal_whatsapp_cloud': True, 'canal_instagram': True, 'canal_messenger': True,
                            'canal_telegram': True})
        casos = [('whatsapp_qr', 100, True), ('telegram', 100, True), ('whatsapp_cloud', 22, True),
                 ('whatsapp_cloud', 23.5, False), ('instagram', 2, True), ('instagram', 30, False),
                 ('messenger', 25, False)]
        for numero, (canal, horas, puede) in enumerate(casos):
            with self.subTest(canal=canal, horas=horas):
                conv = self.conversacion(canal=canal, id_externo=f'5076124{numero:04d}',
                                         ts=ahora - timedelta(hours=horas))
                self.assertEqual(conv._dcasa_puede_escribir_ya(), puede)
        self.ajustes.canal_whatsapp_qr = False
        apagado = self.conversacion(id_externo='50761249999')
        self.assertFalse(apagado._dcasa_puede_escribir_ya(), 'con el canal apagado, no')

    def test_sin_worker_o_con_no_contactar_queda_para_una_persona(self):
        conv = self.conversacion(id_externo='50761231006')
        orden = self.venta(conv.partner_id)
        orden.action_confirm()
        self.assertFalse(self.del_bot(conv), 'sin el Worker configurado no se escribe')
        self.assertIn('no está conectado', str(self.pendientes(orden).note))
        self.configurar_worker()
        conv.partner_id.dcasa_no_contactar = True
        otra = self.venta(conv.partner_id)
        otra.action_confirm()
        self.assertFalse(self.del_bot(conv), 'pidió que no le escribamos')
        self.assertTrue(self.pendientes(otra))

    def test_con_el_worker_caido_la_venta_se_confirma_y_el_mensaje_espera(self):
        conv = self.conversacion(id_externo='50761231003')
        self.worker_caido()
        orden = self.venta(conv.partner_id)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')
        mensaje = self.del_bot(conv)
        self.assertEqual(mensaje.estado_envio, 'por_enviar')
        self.Mensaje._cron_reintentar_envios()
        self.assertEqual(mensaje.estado_envio, 'por_enviar', 'nada se pierde: se reintenta')
        self.assertTrue(mensaje.error_envio)

    def test_un_error_al_pedirla_no_tumba_la_venta_ni_deja_coordenadas_en_el_registro(self):
        cliente = self.env['res.partner'].create({'name': 'Eva Error', 'phone': '6123-9003'})
        cliente._dcasa_poner_ubicacion(*CERCA, 'gps', precision=500, referencia='Casa 2')
        orden = self.venta(cliente)
        with patch.object(type(self.env['sale.order']), '_dcasa_pedir_ubicacion', side_effect=RuntimeError('falla')), \
                self.assertLogs('odoo.addons.dcasa_ubicacion.models.avisos', 'ERROR') as registro:
            orden.action_confirm()
        self.assertEqual(orden.state, 'sale')
        self.assertFalse(orden.dcasa_ubic_pedida_el, 'no quedó como pedida: se puede pedir después')
        self.assertNotIn(LATITUD, '\n'.join(registro.output))

    def test_no_se_pide_si_ya_tiene_su_casa_o_no_va_a_domicilio(self):
        con_casa = self.env['res.partner'].create({'name': 'Lía Casa', 'phone': '6123-9004'})
        con_casa._dcasa_poner_ubicacion(*CERCA, 'whatsapp', referencia='Casa 4')
        orden = self.venta(con_casa)
        orden.action_confirm()
        self.assertFalse(orden.dcasa_ubic_pedida_el)
        self.assertFalse(self.pendientes(orden))
        retiro = self.venta(self.env['res.partner'].create({'name': 'Ana Retira'}), con_envio=False)
        retiro.action_confirm()
        self.assertFalse(retiro.dcasa_ubic_pedida_el or self.pendientes(retiro))
        # Un GPS de 500 m o una dirección escrita a mano no son confiables: se pide.
        impreciso = self.env['res.partner'].create({'name': 'Ivo Impreciso', 'phone': '6123-9005'})
        impreciso._dcasa_poner_ubicacion(*CERCA, 'gps', precision=500)
        otra = self.venta(impreciso)
        otra.action_confirm()
        self.assertTrue(self.pendientes(otra))

    def test_al_marcar_su_casa_con_la_venta_confirmada_no_se_habla_de_precio(self):
        conv = self.conversacion(id_externo='50761231004')
        self.configurar_worker()
        orden = self.venta(conv.partner_id)
        orden.action_confirm()
        enlace = self.Enlace.search([('orden_id', '=', orden.id)])
        enlace._confirmar(*CERCA, 'gps', precision=8, referencia='Casa 24')
        listo = self.del_bot(conv)[-1]
        self.assertEqual(listo.texto, '✅ ¡Listo! Ya tenemos tu casa: Villa Prueba II, La Chorrera. 🏠 Casa 24. '
                                      f'Tu pedido {orden.name} irá a esa dirección.')
        self.assertEqual(listo.autor, 'bot')
        # Lo cobrado no se toca; el equipo ve en la venta el envío de la tabla.
        self.assertFalse(orden.order_line.filtered('is_delivery'), 'la venta confirmada no se recalcula')
        notas = self.notas(orden)
        self.assertIn(f'Con la tabla, el envío a esa zona es {self.precio_de(self.villa)} y en la venta quedó en $0',
                      notas)
        for texto in (listo.texto, notas):
            self.assertNotIn(LATITUD, texto, 'nunca las coordenadas')


@tagged('post_install', '-at_install')
class TestSaleHoy(AvisosCase):

    def test_por_el_chat_una_vez_por_dia(self):
        conv = self.conversacion(id_externo='50761231005')
        conv.partner_id._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 3')
        self.configurar_worker()
        orden = self.venta(conv.partner_id)
        orden.action_confirm()
        self.assertFalse(self.del_bot(conv), 'con su casa en el mapa no se le pide')
        venta = orden.with_user(self.vendedora_avisos)
        self.assertEqual(venta.action_dcasa_avisar_sale_hoy()['params']['type'], 'success')
        mensaje = self.del_bot(conv)
        self.assertEqual(mensaje.texto, f'🚚 ¡Hoy te llega tu pedido {orden.name} a Villa Prueba II!\n'
                                        '¿Habrá alguien en casa para recibirlo?\n✅ Sí / 📍 Cambiar')
        self.assertEqual((mensaje.autor, mensaje.estado_envio), ('bot', 'por_enviar'))
        self.assertEqual((orden.dcasa_aviso_sale_hoy_el, orden.dcasa_aviso_sale_hoy_por), (hoy_en_panama(), 'chat'))
        self.assertEqual(venta.action_dcasa_avisar_sale_hoy()['params']['type'], 'info', 'ya avisada hoy')
        salida = orden.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        self.assertTrue(salida)
        self.assertEqual(salida.with_user(self.vendedora_avisos).action_dcasa_avisar_sale_hoy()['params']['type'],
                         'info', 'desde la entrega, lo mismo: no se repite')
        self.assertEqual(len(self.del_bot(conv)), 1)
        self.assertNotIn(LATITUD, mensaje.texto)

    def test_sin_su_casa_lleva_el_enlace_y_si_cambia_el_lugar_el_equipo_lo_ve(self):
        conv = self.conversacion(id_externo='50761231007')
        self.configurar_worker()
        orden = self.venta(conv.partner_id)
        orden.action_confirm()                       # A: le pide su casa (1)
        orden.with_user(self.vendedora_avisos).action_dcasa_avisar_sale_hoy()
        aviso = self.del_bot(conv)[-1]
        lineas = aviso.texto.split('\n')
        self.assertEqual(lineas[0], f'🚚 ¡Hoy te llega tu pedido {orden.name}!')
        self.assertTrue(lineas[1].startswith('📍 Para que el chofer llegue directo, marca tu casa aquí: '))
        self.assertIn('/u/', lineas[1])
        # Juan: si quiere cambiar el lugar, su enlace va ligado a esa venta.
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        Herramientas._juan_enlace_de_ubicacion()
        enlace = self.Enlace.search([('conversacion_id', '=', conv.id), ('creado_por', '=', 'juan')])
        self.assertEqual(enlace.orden_id, orden)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        pendiente = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'sale.order'), ('res_id', '=', orden.id),
            ('summary', '=', '📍 Marcó su casa el día de la entrega')])
        self.assertEqual(pendiente.user_id, self.vendedora_avisos)
        self.assertNotIn(LATITUD, str(pendiente.note))
        self.assertFalse(self.pendientes(orden), 'ya marcó su casa')

    def test_sin_chat_abre_whatsapp_y_sin_confirmar_no(self):
        cliente = self.env['res.partner'].create({'name': 'Luz Sinchat', 'phone': '6123-9002'})
        cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        orden = self.venta(cliente)
        venta = orden.with_user(self.vendedora_avisos)
        self.assertEqual(venta.action_dcasa_avisar_sale_hoy()['params']['type'], 'warning', 'sin confirmar')
        orden.action_confirm()
        accion = venta.action_dcasa_avisar_sale_hoy()
        self.assertEqual(accion['type'], 'ir.actions.act_url')
        self.assertTrue(accion['url'].startswith('https://api.whatsapp.com/send?phone=50761239002&text='))
        self.assertIn('¿Habrá alguien en casa para recibirlo?', unquote(accion['url']))
        self.assertEqual(orden.dcasa_aviso_sale_hoy_por, 'whatsapp')

    def test_varias_desde_la_lista_y_solo_ventas(self):
        conv = self.conversacion(id_externo='50761231008')
        self.configurar_worker()
        por_chat = self.venta(conv.partner_id)
        sin_chat = self.venta(self.env['res.partner'].create({'name': 'Nora Sinchat', 'phone': '6123-9006'}))
        sin_confirmar = self.venta(conv.partner_id)
        (por_chat | sin_chat).action_confirm()
        accion = self.env.ref('dcasa_ubicacion.accion_avisar_sale_hoy').with_user(self.vendedora_avisos)
        resultado = accion.with_context(active_model='sale.order',
                                        active_ids=(por_chat | sin_chat | sin_confirmar).ids).run()
        mensaje = resultado['params']['message']
        self.assertIn(f'📲 Avisadas por el chat: {por_chat.name}.', mensaje)
        self.assertIn(sin_chat.name, mensaje.split('Sin chat abierto')[1])
        self.assertIn(f'Sin confirmar: {sin_confirmar.name}.', mensaje)
        self.assertFalse(sin_chat.dcasa_aviso_sale_hoy_el, 'sin chat, la lista no arma nada: se manda una por una')
        with self.assertRaises(AccessError):
            por_chat.with_user(self.interno).action_dcasa_avisar_sale_hoy()


@tagged('post_install', '-at_install')
class TestBrianAvisos(AvisosCase):

    def test_brian_pide_la_ubicacion_y_avisa_que_sale_hoy_sin_coordenadas(self):
        Brian = self.env['brian.herramientas'].with_user(self.vendedora_avisos)
        nombres = {h['name'] for h in Brian.catalogo()}
        self.assertTrue({'pedir_ubicacion_al_cliente', 'avisar_que_sale_hoy'} <= nombres)
        self.assertFalse({'pedir_ubicacion_al_cliente', 'avisar_que_sale_hoy'}
                         & {h['name'] for h in self.env['brian.herramientas'].with_user(self.interno).catalogo()})
        conv = self.conversacion(id_externo='50761231009')
        self.configurar_worker()
        orden = self.venta(conv.partner_id)
        orden.action_confirm()
        pedido = Brian.ejecutar('pedir_ubicacion_al_cliente', {'venta': orden.name})
        self.assertTrue(pedido['ok'], pedido)
        self.assertEqual(pedido['datos']['hecho'], 'enviado_por_el_chat')
        avisado = Brian.ejecutar('avisar_que_sale_hoy', {'venta': orden.name})
        self.assertEqual(avisado['datos']['hecho'], 'enviado_por_el_chat')
        otra_vez = Brian.ejecutar('avisar_que_sale_hoy', {'venta': orden.name})
        self.assertEqual(otra_vez['datos']['hecho'], 'ya_avisada')
        self.assertEqual(len(self.del_bot(conv)), 3, 'al comprar, lo que pidió Brian y un solo «sale hoy»')
        # Sin chat: el enlace de WhatsApp para abrir. Con su casa en el mapa: no hace falta.
        sin_chat = self.venta(self.env['res.partner'].create({'name': 'Sol Sinchat', 'phone': '6123-9007'}))
        sin_chat.action_confirm()
        datos = Brian.ejecutar('pedir_ubicacion_al_cliente', {'venta': sin_chat.name})['datos']
        self.assertEqual(datos['hecho'], 'enlace_whatsapp')
        self.assertTrue(datos['abrir']['url'].startswith('https://api.whatsapp.com/send?phone=50761239007&text='))
        sin_chat.partner_id._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 5')
        datos = Brian.ejecutar('pedir_ubicacion_al_cliente', {'venta': sin_chat.name})['datos']
        self.assertEqual(datos['hecho'], 'no_hace_falta')
        datos = Brian.ejecutar('avisar_que_sale_hoy', {'venta': sin_chat.name})['datos']
        self.assertEqual(datos['hecho'], 'enlace_whatsapp')
        self.assertNotIn('/u/', unquote(datos['enlace']), 'con su casa en el mapa, el aviso no lleva el enlace')
        retiro = self.venta(conv.partner_id, con_envio=False)
        retiro.action_confirm()
        self.assertIn('no va a domicilio', Brian.ejecutar('avisar_que_sale_hoy', {'venta': retiro.name})['error'])
        auditoria = self.env['brian.accion'].sudo().search([
            ('herramienta', 'in', ('pedir_ubicacion_al_cliente', 'avisar_que_sale_hoy'))])
        self.assertTrue(auditoria)
        self.assertNotIn(LATITUD, json.dumps(auditoria.mapped('resultado')), 'nunca las coordenadas en la auditoría')
