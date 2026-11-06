"""Camila etapa 1b (decisiones de la dueña, 2026-11-06): la lista crece sola.

0. **Se activa sola al agregar el correo** («en el momento en el que se añade un correo, ya debe activarse
   automáticamente»), con el origen honesto «Se activó sola al agregar su correo», una ficha a la vez y nunca con baja,
   «no contactar», después de un «no», importando, en bloque, instalando ni por el sistema. El «no» queda anotado.
1. **Al confirmar una venta o registrar un pago desde la pantalla**, un cuadro: con correo, la casilla ya activada (si
   el cliente dijo que no, se desactiva y queda el «no»); sin correo, «Sí / No» y lo pide. Nunca traba la venta ni el
   pago, y nunca sale en lo automático (Juan, la web, Brian, crones, RPC sin la marca de la pantalla).
2. **Juan** guarda el correo que escribió el cliente (se activa sola) y honra siempre un «no». Nunca las activa por su
   cuenta.
3. La pantalla de Camila cuenta cuántos llegaron por cada camino.

Datos inventados (ZZCM, @example.com)."""
import json
import os
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.addons.dcasa_brian.models.registro import BrianError
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

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

    def sin_correo(self, nombre='Dora Zzcm', celular='6000-1040'):
        """Una ficha sin correo (la crea el sistema: así no se activa nada)."""
        return self.env['res.partner'].create({'name': nombre, 'phone': celular, 'dcasa_sin_correo': True})

    def estado(self, ficha):
        ficha.invalidate_recordset()
        return ficha.dcasa_promos_estado, ficha.dcasa_promos_origen


# ----------------------------------------------------------------------
# 0. Se activa sola al agregar el correo
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSeActivaSolaAlAgregarElCorreo(Etapa1bComun):

    def test_al_crear_una_ficha_con_correo(self):
        nueva = self.env['res.partner'].with_user(self.vendedora).create(
            {'name': 'Elena Zzcm', 'email': 'elena.zzcm@example.com', 'phone': '6000-1050'})
        self.assertEqual(self.estado(nueva), ('si', 'al_agregar_correo'), 'Nunca «tienda»: nadie le preguntó')
        self.assertEqual((nueva.dcasa_promos_usuario_id, nueva.dcasa_promos_correo),
                         (self.vendedora, 'elena.zzcm@example.com'), 'Con quién lo agregó y a qué correo')

    def test_al_agregar_o_cambiar_el_correo(self):
        dora = self.sin_correo()
        self.assertEqual(self.estado(dora), ('sin', False))
        dora.with_user(self.vendedora).write({'dcasa_sin_correo': False, 'email': 'dora.zzcm@example.com'})
        self.assertEqual(self.estado(dora), ('si', 'al_agregar_correo'))
        # Dijo que sí en la tienda con ese correo y después cambió de correo: el nuevo también se activa solo.
        dora.with_user(self.vendedora).action_dcasa_promos_confirmar()
        self.assertEqual(self.estado(dora), ('si', 'tienda'), 'Una persona lo confirmó')
        dora.with_user(self.vendedora).write({'email': 'dora.nuevo.zzcm@example.com'})
        self.assertEqual(self.estado(dora), ('si', 'al_agregar_correo'))
        self.assertEqual(dora.dcasa_promos_correo, 'dora.nuevo.zzcm@example.com')

    def test_los_clientes_de_siempre_no_se_activan_hacia_atras(self):
        self.assertEqual({self.estado(f)[0] for f in self.ana | self.beto | self.carla}, {'sin'})
        self.carla.with_user(self.vendedora).write({'phone': '6000-1033'})
        self.assertEqual(self.estado(self.carla)[0], 'sin', 'Tocar la ficha sin cambiar el correo no la activa')
        self.carla.with_user(self.vendedora).write({'email': 'CARLA.ZZCM@example.com'})
        self.assertEqual(self.estado(self.carla)[0], 'sin', 'El mismo correo con otras mayúsculas no es otro correo')

    def test_nunca_con_baja_o_no_contactar_de_ese_correo_en_cualquier_ficha(self):
        self.beto.sudo()._dcasa_promos_baja('correo')
        dora = self.sin_correo()
        dora.with_user(self.vendedora).with_context(dcasa_sin_duplicados=True).write(
            {'dcasa_sin_correo': False, 'email': 'beto.zzcm@example.com'})
        self.assertEqual(self.estado(dora)[0], 'baja')
        self.assertFalse(dora.dcasa_promos_fecha)
        self.ana.sudo().write({'dcasa_no_contactar': True})
        eva = self.sin_correo('Eva Zzcm', '6000-1051')
        eva.with_user(self.vendedora).with_context(dcasa_sin_duplicados=True).write(
            {'dcasa_sin_correo': False, 'email': 'ana.zzcm@example.com'})
        self.assertFalse(eva.dcasa_promos_fecha, '«No contactar» en otra ficha con ese correo')

    def test_desmarcar_anota_el_no_y_ya_no_se_activa_sola(self):
        dora = self.sin_correo()
        dora.with_user(self.vendedora).write({'dcasa_sin_correo': False, 'email': 'dora.zzcm@example.com'})
        dora.with_user(self.vendedora).write({'dcasa_promos': False})
        self.assertEqual(self.estado(dora)[0], 'sin')
        self.assertTrue(dora.dcasa_promos_no_fecha)
        self.assertEqual((dora.dcasa_promos_no_origen, dora.dcasa_promos_no_usuario_id), ('ficha', self.vendedora))
        self.assertFalse(dora.dcasa_promos_baja_fecha, 'El «no» no es la baja')
        dora.with_user(self.vendedora).write({'email': 'dora.otro.zzcm@example.com'})
        self.assertEqual(self.estado(dora)[0], 'sin', 'Con un «no», otro correo no la vuelve a activar')
        # Una persona sí puede volver a marcarla si el cliente cambia de idea (y el «no» se va).
        dora.with_user(self.vendedora).write({'dcasa_promos': True})
        self.assertEqual(self.estado(dora), ('si', 'tienda'))
        self.assertFalse(dora.dcasa_promos_no_fecha)

    def test_nunca_importando_en_bloque_instalando_ni_el_sistema(self):
        Partner = self.env['res.partner'].with_user(self.vendedora)
        importada = Partner.with_context(import_file=True).create(
            {'name': 'Ines Zzcm', 'email': 'ines.zzcm@example.com', 'phone': '6000-1052'})
        dos = Partner.create([{'name': 'Juana Zzcm', 'email': 'juana.zzcm@example.com', 'phone': '6000-1053'},
                              {'name': 'Kira Zzcm', 'email': 'kira.zzcm@example.com', 'phone': '6000-1054'}])
        instalando = Partner.with_context(install_mode=True).create(
            {'name': 'Lia Zzcm', 'email': 'lia.zzcm@example.com', 'phone': '6000-1055'})
        sistema = self.env['res.partner'].create({'name': 'Mia Zzcm', 'email': 'mia.zzcm@example.com',
                                                  'phone': '6000-1056'})
        sin = self.sin_correo('Nora Zzcm', '6000-1057') | self.sin_correo('Olga Zzcm', '6000-1058')
        sin.with_user(self.vendedora).with_context(dcasa_sin_duplicados=True).write(
            {'dcasa_sin_correo': False, 'email': 'varias.zzcm@example.com'})
        for ficha in importada | dos | instalando | sistema | sin:
            with self.subTest(ficha.name):
                self.assertFalse(ficha.dcasa_promos_fecha)

    def test_ni_la_ficha_de_un_usuario_nuevo_ni_la_de_una_empresa(self):
        nuevo = self.env['res.users'].with_user(self.gerencia).sudo().create({
            'name': 'Pia Zzcm', 'login': 'zzcm_pia', 'email': 'pia.zzcm@example.com'})
        self.assertFalse(nuevo.partner_id.dcasa_promos_fecha, 'Del equipo (o del portal): no')
        empresa = self.env['res.partner'].with_user(self.vendedora).create(
            {'name': 'ZZCM Muebles S.A.', 'is_company': True, 'email': 'compras.zzcm@example.com',
             'phone': '6000-1098'})
        self.assertFalse(empresa.dcasa_promos_fecha)
        dora = self.sin_correo()
        hijo = self.env['res.partner'].with_user(self.vendedora).create(
            {'name': 'Hijo de Dora', 'parent_id': dora.id, 'email': 'hijo.zzcm@example.com', 'type': 'other'})
        self.assertFalse(dora.dcasa_promos_fecha, 'El correo de un contacto hijo no es el de su ficha')
        self.assertTrue(hijo)

    def test_un_fallo_al_activar_no_traba_guardar_el_correo(self):
        from ..models.permiso import ResPartner  # aquí: sin el módulo, falla solo esta prueba

        dora = self.sin_correo()
        with patch.object(ResPartner, '_dcasa_promos_registrar', side_effect=RuntimeError('falla')):
            dora.with_user(self.vendedora).write({'dcasa_sin_correo': False, 'email': 'dora.zzcm@example.com'})
        self.assertEqual(dora.email, 'dora.zzcm@example.com')
        self.assertFalse(dora.dcasa_promos_fecha)

    def test_confirmar_solo_lo_que_se_activo_solo(self):
        self.permiso(self.ana)
        with self.assertRaisesRegex(UserError, 'no hay nada que confirmar'):
            self.ana.with_user(self.vendedora).action_dcasa_promos_confirmar()

    def test_sofia_guarda_sus_datos_y_se_activa(self):
        dani = self.env['res.partner'].create({'name': 'Dani Zzcm', 'phone': '6000-1020'})
        conv = self.env['dcasa.conversacion'].sudo().create({
            'canal': 'whatsapp_cloud', 'id_externo': '50760001020', 'partner_id': dani.id, 'estado': 'humano'})
        propuesta = self.env['dcasa.sofia.propuesta'].sudo().create({
            'clave': f'guardar_datos:partner:{dani.id}', 'tipo': 'guardar_datos', 'estado': 'pendiente',
            'partner_id': dani.id, 'conversacion_id': conv.id, 'usuario_id': self.vendedora.id,
            'titulo': 'Guarda sus datos', 'datos': {'campos': {'correo': 'dani.zzcm@example.com'}}})
        self.env['dcasa.sofia'].with_user(self.vendedora).aplicar(propuesta.id, 'guardar')
        self.assertEqual(dani.email, 'dani.zzcm@example.com')
        self.assertEqual(self.estado(dani), ('si', 'al_agregar_correo'))
        self.assertEqual(dani.dcasa_promos_usuario_id, self.vendedora)


# ----------------------------------------------------------------------
# 1. Al confirmar una venta y al pagar
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPreguntaEnLaVenta(Etapa1bComun):

    def test_con_correo_la_casilla_viene_activada_y_la_venta_queda_hecha(self):
        orden = self.orden(self.carla)
        cuadro = self.cuadro(self.confirmar(orden))
        self.assertEqual(orden.state, 'sale', 'La venta se confirma ANTES: el cuadro nunca la traba')
        self.assertEqual((cuadro.paso, cuadro.quiere, cuadro.venia_activada), ('casilla', True, True))
        self.assertEqual(cuadro.correo_actual, 'carla.zzcm@example.com')
        self.assertEqual(cuadro.action_listo(), {'type': 'ir.actions.act_window_close'})
        self.assertEqual(self.estado(self.carla), ('si', 'venta'))
        self.assertEqual(self.carla.dcasa_promos_referencia, f'Venta {orden.name} · venía activada',
                         'Lo honesto: venía activada y nadie la quitó')
        self.assertIs(self.confirmar(self.orden(self.carla)), True, 'Ya está: no vuelve a salir')

    def test_desactivarla_anota_el_no(self):
        orden = self.orden(self.carla)
        cuadro = self.cuadro(self.confirmar(orden))
        cuadro.quiere = False
        cuadro.action_listo()
        self.assertEqual(self.estado(self.carla)[0], 'sin')
        self.assertEqual((self.carla.dcasa_promos_no_origen, self.carla.dcasa_promos_no_usuario_id),
                         ('venta', self.vendedora))
        self.assertIs(self.confirmar(self.orden(self.carla)), True, 'Dijo que no hace poco: no sale')
        self.carla.with_user(self.vendedora).write({'email': 'carla.otro.zzcm@example.com'})
        self.assertEqual(self.estado(self.carla)[0], 'sin', 'Con su «no», otro correo no la activa')

    def test_si_se_activo_sola_sigue_diciendolo_y_no_vuelve_a_salir(self):
        dora = self.sin_correo()
        dora.with_user(self.vendedora).write({'dcasa_sin_correo': False, 'email': 'dora.zzcm@example.com'})
        cuadro = self.cuadro(self.confirmar(self.orden(dora)))
        self.assertTrue(cuadro.quiere)
        cuadro.action_listo()
        self.assertEqual(self.estado(dora), ('si', 'al_agregar_correo'), 'Dejarla activada no es que dijo que sí')
        self.assertIs(self.confirmar(self.orden(dora)), True, 'No sale en cada venta')

    def test_pasado_el_plazo_de_un_no_sale_desactivada(self):
        self.carla.sudo()._dcasa_promos_anotar_no('venta')
        hace_tiempo = fields.Datetime.now() - timedelta(days=181)
        self.carla.sudo().write({'dcasa_promos_no_fecha': hace_tiempo, 'dcasa_promos_pregunta_fecha': hace_tiempo})
        cuadro = self.cuadro(self.confirmar(self.orden(self.carla)))
        self.assertEqual((cuadro.quiere, cuadro.venia_activada), (False, False), 'Su «no» se respeta')
        cuadro.quiere = True
        cuadro.action_listo()
        self.assertEqual(self.estado(self.carla), ('si', 'venta'))
        self.assertIn('la activó quien atendió', self.carla.dcasa_promos_referencia)
        self.assertFalse(self.carla.dcasa_promos_no_fecha)
        self.carla.sudo()._dcasa_promos_anotar_no('venta')
        self.carla.sudo().write({'dcasa_promos_no_fecha': hace_tiempo, 'dcasa_promos_pregunta_fecha': hace_tiempo})
        self.env['ir.config_parameter'].sudo().set_param('dcasa_camila.dias_entre_preguntas', '365')
        self.assertIs(self.confirmar(self.orden(self.carla)), True, 'El plazo es un ajuste')

    def test_sin_la_marca_de_la_pantalla_no_sale(self):
        """Lo automático (Juan, la web, Brian, un RPC sin la marca) nunca ve el cuadro."""
        self.assertIs(self.confirmar(self.orden(self.carla), marca=False), True)
        self.assertIs(self.orden(self.carla).sudo().with_context(dcasa_camila_preguntar=True).action_confirm(), True)

    def test_no_sale_a_quien_no_toca(self):
        self.permiso(self.ana)
        self.assertIs(self.confirmar(self.orden(self.ana)), True, 'Ya lo confirmó con su correo de hoy')
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
        dora = self.sin_correo()
        orden = self.orden(dora, dcasa_cliente_sin_correo=True)
        cuadro = self.cuadro(self.confirmar(orden))
        self.assertEqual(cuadro.paso, 'pregunta')
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
        self.assertEqual(self.estado(dora), ('si', 'venta'), 'Dijo que sí: no queda como «se activó sola»')

    def test_sin_correo_el_no_queda_anotado(self):
        dora = self.sin_correo()
        self.cuadro(self.confirmar(self.orden(dora, dcasa_cliente_sin_correo=True))).action_no()
        self.assertEqual(dora.dcasa_promos_no_origen, 'venta')
        dora.with_user(self.vendedora).write({'dcasa_sin_correo': False, 'email': 'dora.zzcm@example.com'})
        self.assertEqual(self.estado(dora)[0], 'sin', 'Dijo que no: su correo no la activa')

    def test_dijo_que_si_pero_no_dio_su_correo(self):
        dora = self.sin_correo()
        cuadro = self.cuadro(self.confirmar(self.orden(dora, dcasa_cliente_sin_correo=True)))
        cuadro.action_si()
        cuadro.action_sin_correo()
        self.assertEqual(dora.dcasa_promos_estado, 'sin')
        self.assertFalse(dora.dcasa_promos_no_fecha, 'No es un «no»: la próxima vez se le pregunta')

    def test_un_fallo_al_armar_el_cuadro_no_traba_la_venta(self):
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
        falso = Pregunta.create({'partner_id': self.beto.id, 'orden_id': orden.id, 'referencia': 'Venta falsa',
                                 'paso': 'casilla'})
        for accion in (falso.action_listo, falso.action_si, falso.action_no):
            with self.subTest(accion.__name__), self.assertRaisesRegex(UserError, 'no corresponde'):
                accion()
        borrador = Pregunta.create({'partner_id': self.carla.id, 'orden_id': self.orden(self.carla).id})
        with self.assertRaisesRegex(UserError, 'no corresponde'):
            borrador.action_si()
        with self.assertRaisesRegex(UserError, 'no corresponde'):
            Pregunta.create({'partner_id': self.carla.id}).action_si()
        self.assertEqual(self.beto.dcasa_promos_estado, 'sin')
        self.assertFalse(self.beto.dcasa_promos_no_fecha)

    def test_al_pagar_sale_y_despues_sigue_lo_de_siempre(self):
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
        cuadro.quiere = False
        siguiente = cuadro.action_listo()
        self.assertEqual(siguiente.get('res_model'), 'dcasa.impresion.paquete', 'Después, «Imprimir documentos»')
        self.assertEqual(self.carla.dcasa_promos_no_origen, 'venta')

    def test_pagar_sin_la_marca_no_sale(self):
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
# 2. Juan: guarda el correo que escribió el cliente y honra siempre un «no»
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestJuanYLasNovedades(Etapa1bComun):

    def setUp(self):
        super().setUp()
        self.juan = self.env.ref('dcasa_conversaciones.user_juan')
        self.dora = self.sin_correo()
        # Los mensajes van en el pasado (el reloj del servidor recorta los del futuro).
        self.ahora = fields.Datetime.now() - timedelta(hours=1)
        self._n = 0
        self.conv = self.mensaje('cliente', 'Hola, me pasas la cotización de la cama')

    def mensaje(self, autor, texto, minutos=0, ficha=None, numero='50760001040'):
        self._n += 1
        conv, _m, _c = self.env['dcasa.conversacion'].sudo()._registrar_mensaje({
            'canal': 'whatsapp_qr', 'id_externo': numero, 'nombre': 'Dora Zzcm', 'celular': numero,
            'id_mensaje': f'zz-{self._n}', 'direccion': 'entrante' if autor == 'cliente' else 'saliente',
            'autor': autor, 'texto': texto, 'ts': self.ahora + timedelta(minutes=minutos)})
        ficha = ficha or self.dora
        if conv.partner_id != ficha:
            conv.sudo().write({'partner_id': ficha.id})
        return conv

    def herramientas(self, conv=None):
        return self.env['brian.herramientas'].with_user(self.juan).with_context(
            juan_conversacion_id=(conv or self.conv).id)

    def test_guarda_el_correo_que_escribio_el_cliente_y_se_activa(self):
        self.assertEqual(self.conv._estado_para_worker().get('permiso_correo'), 'sin_correo')
        self.mensaje('cliente', 'Claro, mi correo es Dora.Zzcm@example.com', minutos=2)
        respuesta = self.herramientas()._juan_guardar_correo('dora.zzcm@example.com')
        self.assertTrue(respuesta['guardado'] and respuesta['novedades'])
        self.assertIn('si no las quiere te lo diga cuando quiera', respuesta['nota'])
        self.assertEqual(self.dora.email, 'dora.zzcm@example.com')
        self.assertEqual(self.estado(self.dora), ('si', 'al_agregar_correo'))
        self.assertEqual(self.dora.dcasa_promos_usuario_id, self.juan, 'Lo agregó Juan')
        self.assertRegex(self.dora.dcasa_promos_referencia, rf'^Chat {self.conv.id} · mensaje \d+$')
        self.assertEqual(self.conv._estado_para_worker().get('permiso_correo'), 'activo')

    def test_un_correo_que_el_cliente_no_escribio_no_se_guarda(self):
        self.mensaje('cliente', 'sí, mándamela', minutos=2)
        with self.assertRaisesRegex(BrianError, 'no lo escribió el cliente'):
            self.herramientas()._juan_guardar_correo('dora.zzcm@example.com')
        with self.assertRaisesRegex(BrianError, 'no está bien escrito'):
            self.herramientas()._juan_guardar_correo('dora.zzcm@')
        self.assertFalse(self.dora.email)
        self.assertFalse(self.dora.dcasa_promos_fecha)

    def test_no_cambia_un_correo_que_ya_tiene_ni_activa_uno_viejo(self):
        conv = self.mensaje('cliente', 'mi correo es carla.zzcm@example.com', ficha=self.carla, numero='50760001003')
        respuesta = self.herramientas(conv)._juan_guardar_correo('carla.zzcm@example.com')
        self.assertFalse(respuesta['novedades'], 'Ya lo tenía: Juan nunca las activa por su cuenta')
        self.assertEqual(self.estado(self.carla)[0], 'sin')
        self.mensaje('cliente', 'mejor a carla.nuevo.zzcm@example.com', ficha=self.carla, numero='50760001003')
        with self.assertRaisesRegex(BrianError, 'ya tiene otro correo'):
            self.herramientas(conv)._juan_guardar_correo('carla.nuevo.zzcm@example.com')
        self.assertEqual(self.carla.email, 'carla.zzcm@example.com')

    def test_con_un_no_o_una_baja_guarda_el_correo_pero_no_las_activa(self):
        self.dora.sudo()._dcasa_promos_anotar_no('venta')
        self.mensaje('cliente', 'dora.zzcm@example.com', minutos=2)
        respuesta = self.herramientas()._juan_guardar_correo('dora.zzcm@example.com')
        self.assertEqual((respuesta['guardado'], respuesta['novedades']), (True, False))
        self.assertIn('no se las ofrezcas', respuesta['nota'])
        self.assertEqual(self.estado(self.dora)[0], 'sin')

    def test_honra_siempre_un_no(self):
        self.mensaje('cliente', 'mi correo es dora.zzcm@example.com', minutos=2)
        self.herramientas()._juan_guardar_correo('dora.zzcm@example.com')
        self.mensaje('cliente', 'mmm mejor no me manden nada por correo', minutos=4)
        respuesta = self.herramientas()._juan_no_quiere_novedades()
        self.assertTrue(respuesta['anotado'])
        self.assertEqual(self.estado(self.dora)[0], 'sin')
        self.assertEqual((self.dora.dcasa_promos_no_origen, self.dora.dcasa_promos_no_usuario_id),
                         ('juan_whatsapp', self.juan))
        self.assertNotIn('permiso_correo', self.conv._estado_para_worker(), 'Ya tiene correo y dijo que no: nada')
        self.dora.with_user(self.vendedora).write({'email': 'dora.otro.zzcm@example.com'})
        self.assertEqual(self.estado(self.dora)[0], 'sin', 'Su «no» se respeta aunque cambie de correo')

    def test_un_no_antes_de_dar_el_correo_tambien_queda(self):
        self.herramientas()._juan_no_quiere_novedades()
        self.assertTrue(self.dora.dcasa_promos_no_fecha)
        self.mensaje('cliente', 'te dejo mi correo: dora.zzcm@example.com', minutos=2)
        self.assertFalse(self.herramientas()._juan_guardar_correo('dora.zzcm@example.com')['novedades'])

    def test_juan_no_tiene_como_activarlas(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.juan).catalogo()}
        self.assertLessEqual({'juan_guardar_correo', 'juan_no_quiere_novedades'}, nombres)
        self.assertFalse({n for n in nombres if 'permiso' in n or 'activar' in n or 'anotar_si' in n})
        with self.assertRaises(Exception):  # noqa: B017 — cualquier rechazo sirve (acceso o casilla)
            self.dora.with_user(self.juan).write({'dcasa_promos': True})
        self.assertFalse(self.dora.dcasa_promos_fecha)


@tagged('post_install', '-at_install')
class TestJuanPorLaApi(Etapa1bComun, HttpCase):

    def test_de_punta_a_punta_como_lo_hace_juan(self):
        """Por la API, como el Worker: el mensaje con su correo, guardar_correo, el estado y el «no»."""
        cabeceras = {'Authorization': f'Bearer {TOKEN_JUAN}', 'Content-Type': 'application/json'}
        dora = self.sin_correo()
        n = iter(range(1, 10))

        def post(ruta, cuerpo):
            respuesta = self.url_open(f'/dcasa/juan/v1/{ruta}', data=json.dumps(cuerpo), headers=cabeceras)
            self.assertEqual(respuesta.status_code, 200, respuesta.text)
            return respuesta.json()

        def mensaje(texto):
            return post('mensaje', {
                'canal': 'whatsapp_qr', 'id_externo': '50760001040', 'nombre': 'Dora Zzcm', 'celular': '50760001040',
                'id_mensaje': f'zz-api-{next(n)}', 'direccion': 'entrante', 'autor': 'cliente', 'texto': texto,
                'ts': (fields.Datetime.now() - timedelta(minutes=5)).replace(microsecond=0).isoformat() + 'Z'})

        with patch.dict(os.environ, {'JUAN_ODOO_TOKEN': TOKEN_JUAN, 'JUAN_WORKER_TOKEN': '', 'JUAN_URL': ''}):
            definiciones = self.url_open('/dcasa/juan/v1/herramientas', headers=cabeceras).json()['herramientas']
            self.assertLessEqual({'guardar_correo', 'no_quiere_novedades'}, {h['nombre'] for h in definiciones})
            primero = mensaje('Hola, me pasas la cotización')
            conv = self.env['dcasa.conversacion'].sudo().browse(primero['conversacion_id'])
            conv.write({'partner_id': dora.id})
            self.assertEqual(mensaje('mi correo es dora.zzcm@example.com').get('permiso_correo'), 'sin_correo')
            guardar = post('herramienta', {'nombre': 'guardar_correo', 'conversacion_id': conv.id,
                                           'argumentos': {'correo': 'dora.zzcm@example.com'}})
            self.assertTrue(guardar['ok'] and guardar['resultado']['novedades'], guardar)
            self.assertEqual(mensaje('gracias').get('permiso_correo'), 'activo')
            no = post('herramienta', {'nombre': 'no_quiere_novedades', 'conversacion_id': conv.id, 'argumentos': {}})
            self.assertTrue(no['ok'] and no['resultado']['anotado'], no)
        self.assertEqual(self.estado(dora)[0], 'sin')
        self.assertEqual(dora.dcasa_promos_no_origen, 'juan_whatsapp')


# ----------------------------------------------------------------------
# 3. La pantalla de Camila: por dónde llegaron
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPorCamino(Etapa1bComun):

    def test_la_pantalla_cuenta_por_camino(self):
        self.permiso(self.ana)                         # la casilla (tienda)
        self.permiso(self.beto, origen='venta')
        self.permiso(self.carla, origen='juan_whatsapp')
        nueva = self.env['res.partner'].with_user(self.vendedora).create(
            {'name': 'Elena Zzcm', 'email': 'elena.zzcm@example.com', 'phone': '6000-1050'})
        self.assertEqual(nueva.dcasa_promos_origen, 'al_agregar_correo')
        caminos = {c['clave']: c['n'] for c in self.Camila.with_user(self.marketing).panel()['por_camino']}
        self.assertEqual(caminos['tienda'], 1)
        self.assertEqual(caminos['venta'], 1)
        self.assertEqual(caminos['juan_whatsapp'], 1)
        self.assertEqual(caminos['al_agregar_correo'], 1)
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
    const cuerpo = await esperar(() => document.querySelector('.o_dcasa_camila_pregunta'), 'el cuadro');
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
"""

DESACTIVAR = """
    const casilla = await esperar(() => document.querySelector('.o_camila_pregunta_casilla input[type="checkbox"]'),
                                  'la casilla');
    if (!casilla.checked) { throw new Error('La casilla tenía que venir activada'); }
    if (!cuerpo.textContent.includes('Se le enviarán novedades a carla.zzcm@example.com')) {
        throw new Error('Falta a qué correo le llegarían');
    }
    if (!cuerpo.textContent.includes('Si el cliente dijo que no, desactívala')) { throw new Error('Falta la ayuda'); }
    casilla.click();
    await esperar(() => !casilla.checked, 'que se desactive');
    document.querySelector('.o_camila_pregunta_listo').click();
"""

SI_Y_CORREO = """
    if (!cuerpo.textContent.includes('quiere recibir novedades de D')) { throw new Error('Falta la pregunta'); }
    await esperar(() => document.querySelector('.o_camila_pregunta_si'), 'el botón Sí');
    if (!document.querySelector('.o_camila_pregunta_no')) { throw new Error('Falta el botón No'); }
    document.querySelector('.o_camila_pregunta_si').click();
    const campo = await esperar(() => document.querySelector('.o_camila_pregunta_correo input'),
                                'el mismo cuadro pidiendo el correo');
    campo.value = 'elsa.zzcm@example.com';
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    campo.dispatchEvent(new Event('change', { bubbles: true }));
    document.querySelector('.o_camila_pregunta_guardar').click();
"""

CERRADO = """
    await esperar(() => !document.querySelector('.o_dcasa_camila_pregunta'), 'que se cierre el cuadro');
    sinErrores();
"""


@tagged('post_install', '-at_install')
class TestPreguntaEnElNavegador(Etapa1bComun, HttpCase):

    def correr(self, cuerpo, orden):
        from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN

        codigo = '(async () => {' + COMUN + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js(f'/odoo/sale.order/{orden.id}', codigo, ready='odoo.isReady', login='zzcm_vendedora',
                        timeout=180)

    def test_al_confirmar_la_casilla_viene_activada_y_desactivarla_anota_el_no(self):
        self.browser_size = '1366x768'
        orden = self.orden(self.carla)
        self.correr(CUADRO + DESACTIVAR + CERRADO, orden)
        self.assertEqual(orden.state, 'sale')
        self.carla.invalidate_recordset()
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_no_origen), ('sin', 'venta'))

    def test_en_el_celular_pide_el_correo_si_no_tiene(self):
        self.browser_size = '390x844'
        elsa = self.sin_correo('Elsa Zzcm', '6000-1041')
        orden = self.orden(elsa, dcasa_cliente_sin_correo=True)
        self.correr(CUADRO + SI_Y_CORREO + CERRADO, orden)
        elsa.invalidate_recordset()
        self.assertEqual((elsa.email, elsa.dcasa_promos_estado, elsa.dcasa_promos_origen),
                         ('elsa.zzcm@example.com', 'si', 'venta'))
