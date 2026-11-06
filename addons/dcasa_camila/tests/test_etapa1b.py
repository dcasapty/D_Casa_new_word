"""Camila etapa 1b (decisiones de la dueña, 2026-11-06): la lista de quienes reciben las novedades crece sola.

1. **Al confirmar una venta o registrar un pago desde la pantalla**, Odoo le pregunta a la persona del equipo si el
   cliente quiere recibir novedades por correo (Sí / No; sin correo lo pide). Nunca traba la venta ni el pago, y nunca
   sale en lo automático (Juan, la web, Brian, crones, RPC sin la marca de la pantalla).
2. **Juan lo pregunta por WhatsApp** con candados contra un «sí» inventado por la IA: la marca de SU pregunta, el último
   mensaje del cliente después de ella, en pocas horas, con un sí claro; el correo, escrito por el cliente.
3. La pantalla de Camila cuenta cuántos llegaron por cada camino.

Datos inventados (ZZCM, @example.com)."""
import json
import os
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.addons.dcasa_brian.models.registro import BrianError
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from ..models import reglas as R
from .comun import CamilaComun

TOKEN_JUAN = 'token-juan-zzcm-de-prueba-0123456789abcdef'


class Etapa1bComun(CamilaComun):

    def orden(self, partner, **extra):
        variante = self.productos[0].product_variant_id
        return self.env['sale.order'].create(dict({
            'partner_id': partner.id, 'user_id': self.vendedora.id,   # la venta es de la vendedora (ve solo las suyas)
            'order_line': [Command.create({'product_id': variante.id})]}, **extra))

    def confirmar(self, orden, usuario=None, marca=True):
        orden = orden.with_user(usuario or self.vendedora)
        if marca:
            orden = orden.with_context(dcasa_camila_preguntar=True)
        return orden.action_confirm()

    def cuadro(self, accion, usuario=None):
        self.assertIsInstance(accion, dict)
        self.assertEqual(accion['res_model'], 'dcasa.camila.pregunta')
        return self.env['dcasa.camila.pregunta'].with_user(usuario or self.vendedora).browse(accion['res_id'])


# ----------------------------------------------------------------------
# 1. Preguntar en cada venta y en cada pago
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPreguntaEnLaVenta(Etapa1bComun):

    def test_al_confirmar_desde_la_pantalla_pregunta_y_la_venta_queda_hecha(self):
        orden = self.orden(self.carla)
        cuadro = self.cuadro(self.confirmar(orden))
        self.assertEqual(orden.state, 'sale', 'La venta se confirma ANTES: la pregunta nunca la traba')
        self.assertEqual(cuadro.partner_id, self.carla)
        self.assertIn(orden.name, cuadro.referencia)
        self.assertEqual(cuadro.correo_actual, 'carla.zzcm@example.com')

    def test_sin_la_marca_de_la_pantalla_no_pregunta(self):
        """Lo automático (Juan, la web, Brian, un RPC sin la marca) nunca ve la pregunta."""
        self.assertIs(self.confirmar(self.orden(self.carla), marca=False), True)
        self.assertIs(self.orden(self.carla).sudo().with_context(dcasa_camila_preguntar=True).action_confirm(), True)

    def test_si_anota_en_la_venta_con_quien_y_donde(self):
        orden = self.orden(self.carla)
        cuadro = self.cuadro(self.confirmar(orden))
        self.assertEqual(cuadro.action_si(), {'type': 'ir.actions.act_window_close'})
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_origen,
                          self.carla.dcasa_promos_usuario_id, self.carla.dcasa_promos_correo),
                         ('si', 'venta', self.vendedora, 'carla.zzcm@example.com'))
        self.assertEqual(self.carla.dcasa_promos_referencia, f'Venta {orden.name}')

    def test_no_queda_con_su_fecha_y_no_se_vuelve_a_preguntar_en_el_plazo(self):
        self.cuadro(self.confirmar(self.orden(self.carla))).action_no()
        self.assertTrue(self.carla.dcasa_promos_no_fecha)
        self.assertEqual(self.carla.dcasa_promos_estado, 'sin')
        self.assertIs(self.confirmar(self.orden(self.carla)), True, 'Dijo que no hace poco: no se le pregunta')
        self.carla.sudo().write({'dcasa_promos_no_fecha': fields.Datetime.now() - timedelta(days=181)})
        self.assertIsInstance(self.confirmar(self.orden(self.carla)), dict, 'Pasados los 180 días, se pregunta')
        self.env['ir.config_parameter'].sudo().set_param('dcasa_camila.dias_entre_preguntas', '365')
        self.assertIs(self.confirmar(self.orden(self.carla)), True, 'Es un ajuste')

    def test_no_pregunta_a_quien_no_toca(self):
        self.permiso(self.ana)
        self.assertIs(self.confirmar(self.orden(self.ana)), True, 'Ya tiene permiso con su correo de hoy')
        self.beto.sudo()._dcasa_promos_baja('ficha')
        self.assertIs(self.confirmar(self.orden(self.beto)), True, 'Se dio de baja')
        otra = self.env['res.partner'].with_context(dcasa_sin_duplicados=True).create(
            {'name': 'Carla otra ficha', 'email': 'carla.zzcm@example.com', 'phone': '6000-1099'})
        otra.sudo().write({'dcasa_no_contactar': True})
        self.assertIs(self.confirmar(self.orden(self.carla)), True, '«No contactar» en otra ficha con su correo')
        empresa = self.env['res.partner'].create({'name': 'ZZCM Muebles S.A.', 'is_company': True,
                                                  'email': 'compras.zzcm@example.com', 'phone': '6000-1098'})
        self.assertIs(self.confirmar(self.orden(empresa)), True, 'Una empresa sin persona')
        self.marketing.partner_id.sudo().phone = '6000-1097'
        self.assertIs(self.confirmar(self.orden(self.marketing.partner_id), usuario=self.gerencia), True,
                      'Una ficha del equipo')

    def test_sin_correo_lo_pide_lo_revisa_y_lo_guarda(self):
        dora = self.env['res.partner'].create({'name': 'Dora Zzcm', 'phone': '6000-1040', 'dcasa_sin_correo': True})
        orden = self.orden(dora, dcasa_cliente_sin_correo=True)
        cuadro = self.cuadro(self.confirmar(orden))
        self.assertFalse(cuadro.correo_actual)
        accion = cuadro.action_si()
        self.assertEqual((accion['res_model'], accion['res_id'], cuadro.paso),
                         ('dcasa.camila.pregunta', cuadro.id, 'correo'), 'El mismo cuadro pide el correo')
        self.assertEqual(dora.dcasa_promos_estado, 'sin', 'Sin correo no hay sí')
        cuadro.correo = 'dora.zzcm@'
        with self.assertRaisesRegex(UserError, 'Escribe su correo bien escrito'):
            cuadro.action_si()
        cuadro.correo = 'Dora.Zzcm@Example.com '
        cuadro.action_si()
        self.assertEqual(dora.email, 'dora.zzcm@example.com', 'Se guarda en la ficha, limpio')
        self.assertEqual((dora.dcasa_promos_estado, dora.dcasa_promos_origen), ('si', 'venta'))

    def test_dijo_que_si_pero_no_dio_su_correo(self):
        dora = self.env['res.partner'].create({'name': 'Dora Zzcm', 'phone': '6000-1040', 'dcasa_sin_correo': True})
        cuadro = self.cuadro(self.confirmar(self.orden(dora, dcasa_cliente_sin_correo=True)))
        cuadro.action_si()
        cuadro.action_sin_correo()
        self.assertEqual(dora.dcasa_promos_estado, 'sin')
        self.assertFalse(dora.dcasa_promos_no_fecha, 'No es un «no»: la próxima vez se le pregunta')

    def test_un_fallo_al_armar_la_pregunta_no_traba_la_venta(self):
        from ..models import pregunta as PREGUNTA  # aquí: sin el módulo, falla solo esta prueba

        orden = self.orden(self.carla)
        with patch.object(PREGUNTA.CamilaPregunta, '_accion_para', side_effect=RuntimeError('falla')):
            self.assertIs(self.confirmar(orden), True)
        self.assertEqual(orden.state, 'sale')

    def test_el_cuadro_no_sirve_para_otro_cliente_ni_sin_venta(self):
        """El cuadro se podría crear por RPC con cualquier ficha: el servidor revisa la venta y el cliente."""
        orden = self.orden(self.carla)
        self.confirmar(orden, marca=False)
        Pregunta = self.env['dcasa.camila.pregunta'].with_user(self.vendedora)
        falso = Pregunta.create({'partner_id': self.beto.id, 'orden_id': orden.id, 'referencia': 'Venta falsa'})
        with self.assertRaisesRegex(UserError, 'no corresponde'):
            falso.action_si()
        borrador = Pregunta.create({'partner_id': self.carla.id, 'orden_id': self.orden(self.carla).id})
        with self.assertRaisesRegex(UserError, 'no corresponde'):
            borrador.action_si()
        with self.assertRaisesRegex(UserError, 'no corresponde'):
            Pregunta.create({'partner_id': self.carla.id}).action_si()
        self.assertEqual(self.beto.dcasa_promos_estado, 'sin')

    def test_al_pagar_pregunta_y_despues_sigue_lo_de_siempre(self):
        self.env.company.dcasa_ofrecer_impresion_pago = True
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.carla.id,
            'invoice_line_ids': [Command.create({'product_id': self.productos[0].product_variant_id.id,
                                                 'quantity': 1, 'price_unit': 100.0, 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        asistente = self.env['account.payment.register'].with_user(self.gerencia).with_context(
            active_model='account.move', active_ids=factura.ids).create({})
        cuadro = self.cuadro(asistente.with_context(dcasa_camila_preguntar=True).action_create_payments(),
                             usuario=self.gerencia)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'), 'El pago ya quedó hecho')
        self.assertIn(factura.name, cuadro.referencia)
        siguiente = cuadro.action_no()
        self.assertEqual(siguiente.get('res_model'), 'dcasa.impresion.paquete', 'Después, «Imprimir documentos»')
        self.assertTrue(self.carla.dcasa_promos_no_fecha)

    def test_pagar_sin_la_marca_no_pregunta(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.carla.id,
            'invoice_line_ids': [Command.create({'product_id': self.productos[0].product_variant_id.id,
                                                 'quantity': 1, 'price_unit': 100.0, 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        asistente = self.env['account.payment.register'].with_user(self.gerencia).with_context(
            active_model='account.move', active_ids=factura.ids).create({})
        resultado = asistente.action_create_payments()
        self.assertNotEqual(isinstance(resultado, dict) and resultado.get('res_model'), 'dcasa.camila.pregunta')


# ----------------------------------------------------------------------
# 2. Juan pregunta por WhatsApp
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestJuanPreguntaPorWhatsapp(Etapa1bComun):

    def setUp(self):
        super().setUp()
        # Los mensajes van en el pasado (el reloj del servidor recorta los del futuro): «minutos» cuenta desde aquí.
        self.ahora = fields.Datetime.now() - timedelta(hours=12)
        self._n = 0
        self.conv = self.mensaje('cliente', 'Hola, me pasas la cotización de la cama', minutos=0)

    def mensaje(self, autor, texto, minutos=0, canal='whatsapp_qr', numero='50760003003'):
        self._n += 1
        conv, _m, _c = self.env['dcasa.conversacion'].sudo()._registrar_mensaje({
            'canal': canal, 'id_externo': numero, 'nombre': 'Carla Zzcm', 'celular': numero,
            'id_mensaje': f'zz-{self._n}', 'direccion': 'entrante' if autor == 'cliente' else 'saliente',
            'autor': autor, 'texto': texto, 'ts': self.ahora + timedelta(minutes=minutos)})
        if conv.partner_id != self.carla:
            conv.sudo().write({'partner_id': self.carla.id})
        return conv

    def herramienta(self, accion, conv=None, **kw):
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=(conv or self.conv).id)
        return Herramientas._juan_permiso_correo(accion, **kw)

    def preguntar(self, minutos=10):
        """Juan llama a la herramienta y, enseguida, su respuesta (con la pregunta) se registra en Odoo."""
        respuesta = self.herramienta('preguntar')
        self.assertTrue(respuesta['puedes_preguntar'], respuesta)
        self.conv.sudo().write({'dcasa_camila_permiso_pedido_en': self.ahora + timedelta(minutes=minutos - 1)})
        self.mensaje('bot', 'Te mando la cotización. ' + respuesta['texto_sugerido'], minutos=minutos)
        return respuesta

    def test_pregunta_y_el_cliente_dice_que_si(self):
        self.assertEqual(self.conv._estado_para_worker().get('permiso_correo'), 'puedes_preguntar')
        self.preguntar()
        pregunta = self.conv.dcasa_camila_permiso_msg_id
        self.assertEqual(pregunta.autor, 'bot', 'Se guarda el id del mensaje del bot que preguntó')
        self.assertEqual(self.conv._estado_para_worker().get('permiso_correo'), 'esperando_respuesta')
        self.mensaje('cliente', '¡Sí, dale! 👍', minutos=15)
        si = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', self.conv.id)], order='id desc', limit=1)
        self.assertTrue(self.herramienta('anotar')['anotado'])
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_origen), ('si', 'juan_whatsapp'))
        self.assertEqual(self.carla.dcasa_promos_referencia, f'Chat {self.conv.id} · mensaje {si.id}',
                         'La prueba: el id del mensaje del cliente')
        self.assertFalse(self.conv.dcasa_camila_permiso_msg_id)
        self.assertNotIn('permiso_correo', self.conv._estado_para_worker())

    def test_sin_su_pregunta_no_se_anota(self):
        self.mensaje('cliente', 'sí', minutos=15)
        with self.assertRaisesRegex(BrianError, 'No hay una pregunta tuya abierta'):
            self.herramienta('anotar')
        self.herramienta('preguntar')   # la marca, pero el bot todavía no mandó la pregunta
        with self.assertRaisesRegex(BrianError, 'No hay una pregunta tuya abierta'):
            self.herramienta('anotar')
        self.assertEqual(self.carla.dcasa_promos_estado, 'sin')

    def test_solo_cuenta_lo_que_el_cliente_contesta_despues(self):
        self.mensaje('cliente', 'sí', minutos=5)
        self.preguntar(minutos=10)
        with self.assertRaisesRegex(BrianError, 'todavía no contestó'):
            self.herramienta('anotar')

    def test_un_si_que_no_es_claro_no_se_anota(self):
        self.preguntar()
        for texto in ('si tienen en gris me interesa', 'Sí, pero no tan seguido', 'mmm', 'ok no'):
            self.mensaje('cliente', texto, minutos=15)
            with self.assertRaisesRegex(BrianError, 'no es un sí claro'):
                self.herramienta('anotar')
        self.assertEqual(self.carla.dcasa_promos_estado, 'sin')

    def test_un_si_horas_despues_no_cuenta(self):
        self.preguntar(minutos=10)
        self.mensaje('cliente', 'sí', minutos=10 + 60 * 7)
        with self.assertRaisesRegex(BrianError, 'no es un sí claro'):
            self.herramienta('anotar')

    def test_sin_correo_lo_pide_y_tiene_que_escribirlo_el_cliente(self):
        self.carla.sudo().write({'email': False})
        self.assertFalse(self.preguntar()['tiene_correo'])
        self.mensaje('cliente', 'Claro que sí', minutos=15)
        self.assertTrue(self.herramienta('anotar')['necesita_correo'])
        self.mensaje('cliente', 'carla.nueva.zzcm@example.com', minutos=18)
        with self.assertRaisesRegex(BrianError, 'no lo escribió el cliente'):
            self.herramienta('anotar', correo='otra.zzcm@example.com')
        self.assertEqual(self.carla.dcasa_promos_estado, 'sin')
        self.assertTrue(self.herramienta('anotar', correo='carla.nueva.zzcm@example.com')['anotado'])
        self.assertEqual(self.carla.email, 'carla.nueva.zzcm@example.com')
        self.assertEqual(self.carla.dcasa_promos_origen, 'juan_whatsapp')

    def test_no_cambia_el_correo_de_la_ficha(self):
        self.preguntar()
        self.mensaje('cliente', 'sí, a otro.zzcm@example.com', minutos=15)
        with self.assertRaisesRegex(BrianError, 'ya tiene otro correo'):
            self.herramienta('anotar', correo='otro.zzcm@example.com')
        self.assertEqual(self.carla.email, 'carla.zzcm@example.com')

    def test_pregunta_una_vez_cada_180_dias(self):
        self.preguntar()
        self.mensaje('cliente', 'no gracias', minutos=15)
        self.assertTrue(self.herramienta('no')['anotado'])
        self.assertTrue(self.carla.dcasa_promos_no_fecha)
        respuesta = self.herramienta('preguntar')
        self.assertFalse(respuesta['puedes_preguntar'])
        self.assertNotIn('permiso_correo', self.conv._estado_para_worker())
        self.carla.sudo().write({'dcasa_promos_no_fecha': False})
        self.assertFalse(self.herramienta('preguntar')['puedes_preguntar'], 'Ya se le preguntó: una vez cada 180 días')

    def test_nunca_a_quien_tiene_permiso_baja_o_no_contactar(self):
        self.permiso(self.carla)
        self.assertFalse(self.herramienta('preguntar')['puedes_preguntar'])
        self.carla.sudo()._dcasa_promos_quitar()
        self.carla.sudo().write({'dcasa_no_contactar': True})
        self.assertFalse(self.herramienta('preguntar')['puedes_preguntar'])
        self.assertNotIn('permiso_correo', self.conv._estado_para_worker())

    def test_solo_por_whatsapp(self):
        telegram = self.mensaje('cliente', 'hola', canal='telegram', numero='777001')
        self.assertFalse(self.herramienta('preguntar', conv=telegram)['puedes_preguntar'])

    def test_la_marca_no_se_escribe_a_mano(self):
        bot = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', self.conv.id)], limit=1)
        with self.assertRaises(AccessError):
            self.conv.with_user(self.vendedora).write({'dcasa_camila_permiso_msg_id': bot.id})

    def test_reglas_del_si_claro(self):
        for texto in ('sí', 'Si', 'dale', 'Claro que sí', 'ok, gracias', 'Sí por favor', 'me interesa',
                      'sí, mi correo es ana@example.com', 'Sííí 🙌', 'de una'):
            self.assertTrue(R.es_un_si_claro(texto), texto)
        for texto in ('no', 'si tienen en gris', 'sí pero no tan seguido', '', 'ana@example.com', 'mejor no',
                      'Sí, ¿y cuánto cuesta el sofá?', 'nunca'):
            self.assertFalse(R.es_un_si_claro(texto), texto)
        self.assertTrue(R.es_un_no('No gracias'))
        self.assertFalse(R.es_un_no('sí'))


@tagged('post_install', '-at_install')
class TestJuanPermisoPorLaApi(Etapa1bComun, HttpCase):

    def test_juan_tiene_la_herramienta_con_su_nombre_publico(self):
        with patch.dict(os.environ, {'JUAN_ODOO_TOKEN': TOKEN_JUAN, 'JUAN_WORKER_TOKEN': '', 'JUAN_URL': ''}):
            respuesta = self.url_open('/dcasa/juan/v1/herramientas',
                                      headers={'Authorization': f'Bearer {TOKEN_JUAN}'})
            self.assertEqual(respuesta.status_code, 200, respuesta.text)
            nombres = {h['nombre'] for h in respuesta.json()['herramientas']}
            self.assertIn('permiso_correo', nombres)
            definicion = next(h for h in respuesta.json()['herramientas'] if h['nombre'] == 'permiso_correo')
            self.assertEqual(definicion['parametros']['properties']['accion']['enum'], ['preguntar', 'anotar', 'no'])

    def test_de_punta_a_punta_como_lo_hace_juan(self):
        """Por la API, como el Worker: el mensaje, la herramienta, la pregunta del bot, el «sí» y el anotado."""
        cabeceras = {'Authorization': f'Bearer {TOKEN_JUAN}', 'Content-Type': 'application/json'}
        n = iter(range(1, 10))

        def post(ruta, cuerpo):
            respuesta = self.url_open(f'/dcasa/juan/v1/{ruta}', data=json.dumps(cuerpo), headers=cabeceras)
            self.assertEqual(respuesta.status_code, 200, respuesta.text)
            return respuesta.json()

        def mensaje(autor, texto, ts):
            return post('mensaje', {
                'canal': 'whatsapp_qr', 'id_externo': '50760003003', 'nombre': 'Carla Zzcm', 'celular': '50760003003',
                'id_mensaje': f'zz-api-{next(n)}', 'direccion': 'entrante' if autor == 'cliente' else 'saliente',
                'autor': autor, 'texto': texto, 'ts': ts.replace(microsecond=0).isoformat() + 'Z'})

        with patch.dict(os.environ, {'JUAN_ODOO_TOKEN': TOKEN_JUAN, 'JUAN_WORKER_TOKEN': '', 'JUAN_URL': ''}):
            primero = mensaje('cliente', 'Hola, me pasas la cotización', fields.Datetime.now() - timedelta(hours=1))
            conv = self.env['dcasa.conversacion'].sudo().browse(primero['conversacion_id'])
            conv.write({'partner_id': self.carla.id})
            herramienta = {'nombre': 'permiso_correo', 'conversacion_id': conv.id}
            preguntar = post('herramienta', dict(herramienta, argumentos={'accion': 'preguntar'}))
            self.assertTrue(preguntar['ok'], preguntar)
            self.assertTrue(preguntar['resultado']['puedes_preguntar'])
            ahora = fields.Datetime.now()
            respuesta_del_bot = mensaje('bot', 'Te la mandé. ' + preguntar['resultado']['texto_sugerido'], ahora)
            self.assertEqual(respuesta_del_bot.get('permiso_correo'), 'esperando_respuesta')
            mensaje('cliente', 'Sí, por favor', ahora)
            anotar = post('herramienta', dict(herramienta, argumentos={'accion': 'anotar'}))
            self.assertTrue(anotar['ok'] and anotar['resultado']['anotado'], anotar)
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_origen), ('si', 'juan_whatsapp'))


# ----------------------------------------------------------------------
# 3. La pantalla de Camila: por dónde llegaron
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPorCamino(Etapa1bComun):

    def test_la_pantalla_cuenta_por_camino(self):
        self.permiso(self.ana)                         # la casilla (tienda)
        self.permiso(self.beto, origen='venta')
        self.permiso(self.carla, origen='juan_whatsapp')
        caminos = {c['clave']: c['n'] for c in self.Camila.with_user(self.marketing).panel()['por_camino']}
        self.assertEqual(caminos['tienda'], 1)
        self.assertEqual(caminos['venta'], 1)
        self.assertEqual(caminos['juan_whatsapp'], 1)
        self.assertEqual(caminos['factura'], 0)
        self.assertNotIn('web', caminos, '«Sitio web» solo si hay alguno')
        self.assertEqual(json.loads(json.dumps(caminos)), caminos, 'Solo cuántos (nada de nombres)')


# ----------------------------------------------------------------------
# 4. En el navegador: el cuadro al confirmar (con la regla del scroll y sin la X)
# ----------------------------------------------------------------------

CUADRO = """
    await esperar(() => document.querySelector('.o_form_statusbar'), 'la venta');
    await new Promise((ok) => setTimeout(ok, 300));
    let confirmar = document.querySelector('.o_form_statusbar button[name="action_confirm"]');
    if (!confirmar) {
        // En el celular, los botones de la venta van en el menú de la barra («⋮»).
        const menu = await esperar(() => document.querySelector('.o_statusbar_buttons .dropdown-toggle'),
                                   'el menú de los botones');
        menu.click();
        confirmar = await esperar(() => document.querySelector('.dropdown-menu button[name="action_confirm"], '
                                                               + '.o-dropdown--menu button[name="action_confirm"]'),
                                  'el botón Confirmar en el menú');
    }
    confirmar.click();
    const cuerpo = await esperar(() => document.querySelector('.o_dcasa_camila_pregunta'), 'la pregunta');
    const contenido = cuerpo.closest('.modal-content');
    const cerrar = contenido.querySelector('.modal-header .btn-close, .modal-header .oi-arrow-left');
    if (cerrar && getComputedStyle(cerrar).display !== 'none') {
        throw new Error('El cuadro se puede cerrar sin contestar');
    }
    const desborde = getComputedStyle(contenido.querySelector('.modal-body')).overflowY;
    if (!['auto', 'scroll'].includes(desborde)) {
        throw new Error('El cuadro no baja con su propio scroll (overflow-y: ' + desborde + ')');
    }
    if (contenido.getBoundingClientRect().bottom > window.innerHeight + 2) {
        throw new Error('El cuadro se sale de la pantalla');
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) {
        throw new Error('Hay scroll de lado');
    }
    if (!cuerpo.textContent.includes('quiere recibir novedades de D')) { throw new Error('Falta la pregunta'); }
    await esperar(() => document.querySelector('.o_camila_pregunta_si'), 'el botón Sí');
    if (!document.querySelector('.o_camila_pregunta_no')) { throw new Error('Falta el botón No'); }
    document.querySelector('.o_camila_pregunta_si').click();
"""

CERRADO = """
    await esperar(() => !document.querySelector('.o_dcasa_camila_pregunta'), 'que se cierre la pregunta');
    sinErrores();
"""

PIDE_CORREO = """
    const campo = await esperar(() => document.querySelector('.o_camila_pregunta_correo input'),
                                'el mismo cuadro pidiendo el correo');
    campo.value = 'elsa.zzcm@example.com';
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    campo.dispatchEvent(new Event('change', { bubbles: true }));
    document.querySelector('.o_camila_pregunta_guardar').click();
"""


@tagged('post_install', '-at_install')
class TestPreguntaEnElNavegador(Etapa1bComun, HttpCase):

    def correr(self, cuerpo, orden):
        from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN

        codigo = '(async () => {' + COMUN + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js(f'/odoo/sale.order/{orden.id}', codigo, ready='odoo.isReady', login='zzcm_vendedora',
                        timeout=180)

    def test_al_confirmar_sale_la_pregunta_y_anota_el_si(self):
        self.browser_size = '1366x768'
        orden = self.orden(self.carla)
        self.correr(CUADRO + CERRADO, orden)
        self.assertEqual(orden.state, 'sale')
        self.carla.invalidate_recordset()
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_origen), ('si', 'venta'))

    def test_en_el_celular_pide_el_correo_si_no_tiene(self):
        self.browser_size = '390x844'
        elsa = self.env['res.partner'].create({'name': 'Elsa Zzcm', 'phone': '6000-1041', 'dcasa_sin_correo': True})
        orden = self.orden(elsa, dcasa_cliente_sin_correo=True)
        self.correr(CUADRO + PIDE_CORREO + CERRADO, orden)
        elsa.invalidate_recordset()
        self.assertEqual((elsa.email, elsa.dcasa_promos_estado, elsa.dcasa_promos_origen),
                         ('elsa.zzcm@example.com', 'si', 'venta'))
