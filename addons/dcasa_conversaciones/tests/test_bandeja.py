"""La bandeja en el panel: atender, devolver al asistente, escribir desde Odoo (con reintentos) y ver el chat."""
import base64
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import URL_WORKER, JuanCase, respuesta_http


class BandejaCase(JuanCase):

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Karen')
        self.como_vendedora = self.conv.with_user(self.vendedora)

    def llamadas(self, ruta):
        return [c for c in self.worker.call_args_list if c.args[1] == f'{URL_WORKER}{ruta}']

    def worker_caido(self):
        self.worker.side_effect = requests.ConnectionError('sin red')

    def worker_ok(self, id_mensaje='wamid.worker.1'):
        self.worker.side_effect = None
        self.worker.return_value = respuesta_http({'ok': True, 'id_mensaje': id_mensaje})

    def envejecer(self, mensajes, minutos=10):
        mensajes.with_context(dcasa_mensaje_sistema=True).sudo().write(
            {'ultimo_intento': fields.Datetime.now() - timedelta(minutes=minutos)})


@tagged('post_install', '-at_install')
class TestAtenderYDevolver(BandejaCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()

    def test_atender_pausa_al_bot_y_avisa_al_worker(self):
        self.como_vendedora.action_atender()
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('humano', self.vendedora))
        self.assertFalse(self.conv._estado_para_worker()['bot_activo'])
        espera = (self.conv.pausada_hasta - fields.Datetime.now()).total_seconds()
        self.assertAlmostEqual(espera, 120 * 60, delta=60)
        (llamada,) = self.llamadas('/odoo/estado')
        self.assertEqual(llamada.args[0], 'POST')
        cuerpo = llamada.kwargs['json']
        self.assertEqual((cuerpo['canal'], cuerpo['id_externo'], cuerpo['estado']),
                         ('whatsapp_qr', '50761234567', 'humano'))
        self.assertRegex(cuerpo['pausada_hasta'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual(llamada.kwargs['headers']['Authorization'].split()[0], 'Bearer')
        self.assertFalse(self.conv.estado_pendiente_de_avisar)

    def test_la_pausa_es_la_de_los_ajustes_y_cero_es_hasta_que_la_devuelvan(self):
        self.ajustes.pausa_por_defecto_minutos = 0
        self.como_vendedora.action_atender()
        self.assertFalse(self.conv.pausada_hasta)
        self.assertFalse(self.conv._controla_bot())
        self.assertNotIn('pausada_hasta', self.llamadas('/odoo/estado')[0].kwargs['json'])

    def test_devolver_al_asistente(self):
        self.como_vendedora.action_atender()
        self.como_vendedora.action_devolver_al_bot()
        self.assertEqual(self.conv.estado, 'bot')
        self.assertFalse(self.conv.pausada_hasta)
        self.assertTrue(self.conv._estado_para_worker()['bot_activo'])
        ultimo = self.llamadas('/odoo/estado')[-1].kwargs['json']
        self.assertEqual(ultimo['estado'], 'bot')
        self.assertNotIn('pausada_hasta', ultimo)

    def test_si_el_worker_no_responde_atender_igual_funciona_y_se_reintenta(self):
        self.worker_caido()
        self.como_vendedora.action_atender()
        self.assertEqual(self.conv.estado, 'humano', 'Odoo manda: el Worker pregunta GET /estado antes de enviar')
        self.assertTrue(self.conv.estado_pendiente_de_avisar)
        self.worker_ok()
        self.Conversacion._reintentar_avisos_de_estado()
        self.assertFalse(self.conv.estado_pendiente_de_avisar)
        self.assertEqual(self.llamadas('/odoo/estado')[-1].kwargs['json']['estado'], 'humano')

    def test_sin_worker_configurado_no_acumula_pendientes(self):
        with patch.dict('os.environ', {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            self.como_vendedora.action_atender()
        self.assertFalse(self.conv.estado_pendiente_de_avisar)
        self.assertEqual(self.conv.estado, 'humano')

    def test_la_pausa_vencida_se_devuelve_sola_y_se_avisa(self):
        self.como_vendedora.action_atender()
        self.conv.pausada_hasta = fields.Datetime.now() - timedelta(minutes=1)
        self.Conversacion._cron_mantenimiento()
        self.assertEqual(self.conv.estado, 'bot')
        self.assertEqual(self.llamadas('/odoo/estado')[-1].kwargs['json']['estado'], 'bot')

    def test_cerrar(self):
        self.como_vendedora.action_cerrar()
        self.assertEqual(self.conv.estado, 'cerrada')
        self.assertFalse(self.conv._estado_para_worker()['bot_activo'])

    def test_el_cambio_de_estado_queda_en_el_historial_de_la_conversacion(self):
        self.como_vendedora.action_atender()
        self.env.cr.precommit.run()
        campos = self.conv.message_ids.tracking_value_ids.field_id.mapped('name')
        self.assertIn('estado', campos)


@tagged('post_install', '-at_install')
class TestPermisos(BandejaCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()

    def test_solo_ventas_atiende(self):
        for usuario in (self.interno, self.portal):
            for metodo in ('action_atender', 'action_devolver_al_bot', 'action_cerrar', 'action_enviar',
                           'action_crear_oportunidad', 'action_reintentar_envios'):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    getattr(self.conv.with_user(usuario), metodo)()
        self.assertEqual(self.conv.estado, 'bot')
        self.assertFalse(self.worker.called)

    def test_ventas_y_gerencia_si(self):
        self.conv.with_user(self.vendedora).action_atender()
        self.conv.with_user(self.gerente).action_devolver_al_bot()
        self.assertEqual(self.conv.estado, 'bot')

    def test_el_canal_y_la_persona_de_una_conversacion_no_se_cambian(self):
        for valores in ({'canal': 'telegram'}, {'id_externo': '50760000000'}):
            with self.assertRaises(AccessError):
                self.conv.with_user(self.gerente).write(valores)

    def test_solo_gerencia_borra_una_conversacion(self):
        with self.assertRaises(AccessError):
            self.conv.with_user(self.vendedora).unlink()
        mensaje = self.conv.mensaje_ids
        self.conv.with_user(self.gerente).unlink()
        self.assertFalse(self.conv.exists())
        self.assertFalse(mensaje.exists(), 'Derecho de borrado: se van los mensajes')

    def test_borrar_la_conversacion_borra_sus_adjuntos(self):
        _, mensaje, _ = self.registrar('Mira', adjuntos=[
            {'tipo': 'documento', 'nombre': 'a.pdf', 'mime': 'application/pdf', 'url': None,
             'base64': base64.b64encode(b'%PDF-1.4 x').decode(), 'sensible': False}])
        adjunto = mensaje.adjunto_ids
        self.assertTrue(adjunto)
        mensaje.conversacion_id.with_user(self.gerente).unlink()
        self.assertFalse(adjunto.exists())


@tagged('post_install', '-at_install')
class TestEscribirDesdeOdoo(BandejaCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()

    def escribir(self, texto='Hola Karen, soy Marta. Sí tenemos queen.', adjuntos=None, usuario=None):
        conv = self.conv.with_user(usuario or self.vendedora)
        conv.write({'borrador': texto, 'borrador_adjunto_ids': [(6, 0, (adjuntos or self.env['ir.attachment']).ids)]})
        return conv.action_enviar()

    def mensaje_de_odoo(self):
        return self.conv.mensaje_ids.filtered(lambda m: m.origen == 'odoo' and m.tipo == 'mensaje')

    def test_sale_por_el_worker_con_el_contrato(self):
        self.escribir()
        (llamada,) = self.llamadas('/odoo/enviar')
        self.assertEqual(llamada.args[0], 'POST')
        enviado = dict(llamada.kwargs['json'])
        # La llave de idempotencia: el id del mensaje en Odoo (`odoo-<uuid>`), que no cambia entre reintentos.
        self.assertRegex(enviado.pop('id_envio'), r'^odoo-[0-9a-f]{32}$')
        self.assertEqual(enviado, {'canal': 'whatsapp_qr', 'id_externo': '50761234567', 'autor': 'vendedora',
                                   'texto': 'Hola Karen, soy Marta. Sí tenemos queen.'})
        mensaje = self.mensaje_de_odoo()
        self.assertEqual((mensaje.estado_envio, mensaje.id_mensaje), ('enviado', 'wamid.worker.1'))
        self.assertEqual((mensaje.autor, mensaje.direccion, mensaje.usuario_id),
                         ('vendedora', 'saliente', self.vendedora))
        self.assertFalse(self.conv.borrador)
        self.assertIn('Hola Karen', self.conv.ultimo_mensaje_texto)

    def test_el_mensaje_se_confirma_en_la_base_antes_de_llamar_al_worker(self):
        """El Worker (y el puente, que baja el adjunto con su URL firmada) llaman DE VUELTA a Odoo mientras Odoo
        espera, en otra transacción: si el mensaje y su adjunto no están confirmados, el puente recibe un 404 y el
        envío falla la primera vez (hallado con Odoo y Worker reales). Además, así el mensaje no se pierde si la
        petición se cae."""
        orden = []

        def worker_que_anota(*_args, **_kwargs):
            orden.append('worker')
            return respuesta_http({'ok': True, 'id_mensaje': 'x'})

        self.worker.side_effect = worker_que_anota
        with patch('odoo.addons.dcasa_conversaciones.models.mensaje.transaccion.confirmar',
                   side_effect=lambda env: orden.append('commit')):
            self.escribir()
        self.assertEqual(orden, ['commit', 'worker'])

    def test_al_escribir_la_vendedora_toma_la_conversacion(self):
        self.escribir()
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('humano', self.vendedora))
        self.assertFalse(self.conv._estado_para_worker()['bot_activo'])
        self.assertFalse(self.conv.seguimiento_proximo)

    def test_queda_tambien_en_el_chatter_del_cliente(self):
        self.escribir('Te confirmo el precio hoy')
        notas = self.conv.partner_id.message_ids.filtered(lambda m: 'Te confirmo el precio hoy' in (m.body or ''))
        self.assertEqual(len(notas), 1)
        self.assertIn('Vendedora Vendedora Prueba', notas.body)
        self.assertEqual(notas.author_id, self.vendedora.partner_id)

    def test_sin_texto_ni_adjunto_no_envia(self):
        with self.assertRaises(UserError):
            self.escribir('   ')
        self.assertFalse(self.llamadas('/odoo/enviar'))

    def test_si_el_worker_no_responde_el_mensaje_queda_por_enviar(self):
        self.worker_caido()
        resultado = self.escribir('No te pierdas este mensaje')
        self.assertEqual(resultado['params']['title'], 'Quedó por enviar')
        mensaje = self.mensaje_de_odoo()
        self.assertEqual(mensaje.estado_envio, 'por_enviar')
        self.assertTrue(mensaje.id_mensaje.startswith('odoo-'))
        self.assertEqual(mensaje.texto, 'No te pierdas este mensaje')
        self.assertEqual(mensaje.intentos, 1)
        self.assertIn('no responde', mensaje.error_envio)
        self.assertEqual(self.conv.por_enviar_count, 1)
        self.assertIn('Por enviar', self.conv.chat_html)

    def test_el_cron_lo_reintenta_hasta_que_sale(self):
        self.worker_caido()
        self.escribir('Reintenta esto')
        mensaje = self.mensaje_de_odoo()
        self.envejecer(mensaje)
        self.Mensaje._cron_reintentar_envios()
        self.assertEqual((mensaje.estado_envio, mensaje.intentos), ('por_enviar', 2))
        self.worker_ok('wamid.worker.9')
        self.envejecer(mensaje)
        self.assertEqual(self.Mensaje._cron_reintentar_envios(), 1)
        self.assertEqual((mensaje.estado_envio, mensaje.id_mensaje), ('enviado', 'wamid.worker.9'))
        self.assertFalse(mensaje.error_envio)
        self.assertEqual(self.conv.por_enviar_count, 0)

    def test_el_reintento_usa_la_misma_llave_de_idempotencia(self):
        """Si Odoo no oyó la respuesta (se cayó la red, el Worker tardó más de 25 s) y reintenta, el Worker reconoce el
        `id_envio` y no vuelve a escribirle al cliente lo que ya salió."""
        self.worker_caido()
        self.escribir('Una sola vez, por favor')
        mensaje = self.mensaje_de_odoo()
        llave = mensaje.id_mensaje
        self.envejecer(mensaje)
        self.Mensaje._cron_reintentar_envios()
        self.worker_ok('wamid.worker.3')
        self.envejecer(mensaje)
        self.Mensaje._cron_reintentar_envios()
        llaves = [llamada.kwargs['json']['id_envio'] for llamada in self.llamadas('/odoo/enviar')]
        self.assertEqual(llaves, [llave, llave, llave])
        # Al confirmar, el mensaje toma el id del canal, pero la llave ya cumplió.
        self.assertEqual(mensaje.id_mensaje, 'wamid.worker.3')

    def test_el_cron_no_reintenta_demasiado_pronto(self):
        self.worker_caido()
        self.escribir('Espera')
        mensaje = self.mensaje_de_odoo()
        antes = len(self.llamadas('/odoo/enviar'))
        self.Mensaje._cron_reintentar_envios()      # el último intento fue hace segundos
        self.assertEqual(len(self.llamadas('/odoo/enviar')), antes)
        self.assertEqual(mensaje.estado_envio, 'por_enviar')

    def test_tras_muchos_intentos_queda_fallido_a_la_vista_y_se_puede_reintentar(self):
        self.worker_caido()
        self.escribir('No sale')
        mensaje = self.mensaje_de_odoo()
        mensaje.with_context(dcasa_mensaje_sistema=True).sudo().intentos = 11
        self.envejecer(mensaje)
        self.Mensaje._cron_reintentar_envios()
        self.assertEqual(mensaje.estado_envio, 'fallido')
        self.assertEqual(self.conv.por_enviar_count, 1, 'Un fallido sigue contando: nunca desaparece')
        self.assertIn('No se pudo enviar', self.conv.chat_html)
        self.assertEqual(self.Mensaje._cron_reintentar_envios(), 0, 'El cron ya no insiste')
        self.worker_ok('wamid.worker.7')
        mensaje.with_user(self.vendedora).action_reintentar()
        self.assertEqual((mensaje.estado_envio, mensaje.id_mensaje), ('enviado', 'wamid.worker.7'))

    def test_error_de_validacion_del_worker_no_se_reintenta_a_ciegas(self):
        self.worker.return_value = respuesta_http({'ok': False, 'error': 'canal sin sesión'}, 422)
        self.escribir('x')
        mensaje = self.mensaje_de_odoo()
        self.assertEqual(mensaje.estado_envio, 'fallido')
        self.assertIn('canal sin sesión', mensaje.error_envio)

    def test_sin_worker_configurado_queda_por_enviar_sin_gastar_intentos(self):
        with patch.dict('os.environ', {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            self.escribir('Antes de configurar')
        mensaje = self.mensaje_de_odoo()
        self.assertEqual((mensaje.estado_envio, mensaje.intentos), ('por_enviar', 0))
        self.assertIn('Falta configurar', mensaje.error_envio)

    def test_adjuntos_salen_con_url_firmada_de_vida_corta(self):
        adjunto = self.env['ir.attachment'].create({
            'name': 'cotizacion.pdf', 'raw': b'%PDF-1.4 cotizacion', 'mimetype': 'application/pdf',
            'res_model': 'dcasa.conversacion', 'res_id': self.conv.id})
        self.escribir('Te mando la cotización', adjuntos=adjunto)
        (llamada,) = self.llamadas('/odoo/enviar')
        (enviado,) = llamada.kwargs['json']['adjuntos']
        self.assertEqual((enviado['tipo'], enviado['nombre'], enviado['mime']),
                         ('documento', 'cotizacion.pdf', 'application/pdf'))
        self.assertRegex(enviado['url'], rf'/dcasa/adjunto/{adjunto.id}/\d+/[0-9a-f]{{64}}/cotizacion.pdf$')
        mensaje = self.mensaje_de_odoo()
        self.assertEqual(mensaje.adjunto_ids, adjunto)
        self.assertEqual(adjunto.res_model, 'dcasa.mensaje')
        self.assertFalse(adjunto.public)
        self.assertFalse(self.conv.borrador_adjunto_ids)

    def test_solo_un_adjunto_sin_texto(self):
        adjunto = self.env['ir.attachment'].create({
            'name': 'foto.jpg', 'raw': b'\xff\xd8\xff\xe0', 'mimetype': 'image/jpeg',
            'res_model': 'dcasa.conversacion', 'res_id': self.conv.id})
        self.escribir('', adjuntos=adjunto)
        (llamada,) = self.llamadas('/odoo/enviar')
        self.assertNotIn('texto', llamada.kwargs['json'])
        self.assertEqual(llamada.kwargs['json']['adjuntos'][0]['tipo'], 'imagen')

    def test_el_eco_del_worker_no_duplica_el_mensaje(self):
        """El Worker puede devolver lo que envió a POST /mensaje: queda UN mensaje."""
        self.worker_caido()
        self.escribir('Hola, soy Marta')
        mensaje = self.mensaje_de_odoo()
        # El Worker alcanzó a enviarlo y registra su propio eco con su id (el id local aún no se sustituyó).
        _, eco, creado = self.registrar('Hola, soy Marta', autor='vendedora')
        self.assertFalse(creado)
        self.assertEqual(eco, mensaje, 'Se adopta el mensaje escrito en Odoo en vez de duplicarlo')
        self.assertEqual(mensaje.estado_envio, 'enviado')
        self.assertTrue(mensaje.id_mensaje.startswith('wamid.'))
        self.assertEqual(self.conv.mensaje_ids.filtered(lambda m: m.texto == 'Hola, soy Marta'), mensaje)

    def test_si_el_eco_llega_antes_que_la_confirmacion_se_fusionan(self):
        self.worker_ok('wamid.eco.1')
        original = type(self.Mensaje)._enviar

        def con_eco(mensajes):
            # Mientras Odoo espera la respuesta del Worker, éste ya registró su eco.
            self.registrar('Mensaje con carrera', autor='vendedora', id_mensaje='wamid.eco.1')
            return original(mensajes)

        with patch.object(type(self.Mensaje), '_enviar', con_eco):
            self.escribir('Mensaje con carrera')
        mensajes = self.conv.mensaje_ids.filtered(lambda m: m.texto == 'Mensaje con carrera')
        self.assertEqual(len(mensajes), 1)
        self.assertEqual((mensajes.id_mensaje, mensajes.estado_envio, mensajes.usuario_id, mensajes.origen),
                         ('wamid.eco.1', 'enviado', self.vendedora, 'odoo'))

    def test_un_mensaje_enviado_mas_de_una_vez_por_el_worker_se_registra_una_vez(self):
        self.escribir('Hola')
        datos = self.datos('Respuesta distinta', autor='vendedora', id_mensaje='wamid.x.1')
        self.assertTrue(self.Conversacion._registrar_mensaje(datos)[2])
        self.assertFalse(self.Conversacion._registrar_mensaje(dict(datos))[2])


@tagged('post_install', '-at_install')
class TestElChat(BandejaCase):

    def test_se_ve_como_un_chat_en_orden(self):
        self.registrar('Quiero una cama queen', ts=self.datos()['ts'])
        self.registrar('Claro, tengo varias.', autor='bot', ts=self.datos()['ts'] + timedelta(minutes=1))
        self.registrar('Te paso con Marta', autor='vendedora', ts=self.datos()['ts'] + timedelta(minutes=2))
        html = self.conv.chat_html
        self.assertLess(html.index('Quiero una cama queen'), html.index('Claro, tengo varias.'))
        self.assertLess(html.index('Claro, tengo varias.'), html.index('Te paso con Marta'))
        for clase in ('o_dcasa_burbuja_cliente', 'o_dcasa_burbuja_bot', 'o_dcasa_burbuja_vendedora'):
            self.assertIn(clase, html)
        self.assertIn('Karen', html)
        self.assertIn('Asistente', html)

    def test_las_horas_son_de_panama(self):
        self.assertIn('09/10 10:00', self.conv.chat_html)   # 15:00 UTC = 10:00 en Panamá

    def test_el_texto_del_cliente_va_escapado_en_el_chat(self):
        conv = self.conversacion('<img src=x onerror=alert(1)> & "comillas" <script>x</script>',
                                 id_externo='50761230001')
        html = conv.chat_html
        self.assertNotIn('<img', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;img', html)
        self.assertIn('&amp;', html)

    def test_saltos_de_linea(self):
        conv = self.conversacion('Línea uno\nLínea dos', id_externo='50761230002')
        self.assertIn('Línea uno<br/>Línea dos', conv.chat_html)

    def test_adjuntos_en_el_chat(self):
        conv, mensaje, _ = self.registrar('Mira', id_externo='50761230003', adjuntos=[
            {'tipo': 'documento', 'nombre': 'orden.pdf', 'mime': 'application/pdf', 'url': None,
             'base64': base64.b64encode(b'%PDF-1.4 x').decode(), 'sensible': False},
            {'tipo': 'imagen', 'nombre': 'yappy.jpg', 'mime': 'image/jpeg', 'url': None,
             'base64': base64.b64encode(b'\xff\xd8\xff\xe0jpeg').decode(), 'sensible': True}])
        html = conv.chat_html
        self.assertIn('orden.pdf', html)
        self.assertIn('o_dcasa_sensible', html)
        self.assertIn(f'/web/content/{mensaje.adjunto_ids[0].id}?download=true', html)

    def test_conversacion_vacia(self):
        vacia = self.Conversacion.sudo().create({'canal': 'telegram', 'id_externo': '1'})
        self.assertIn('Todavía no hay mensajes', vacia.chat_html)

    def test_solo_las_ultimas_200_burbujas(self):
        conv = self.conversacion('primero', id_externo='50761230004')
        for i in range(205):
            self.registrar(f'mensaje {i}', id_externo='50761230004')
        self.assertEqual(conv.chat_html.count('o_dcasa_burbuja_texto'), 200)
        self.assertNotIn('>primero<', conv.chat_html)


@tagged('post_install', '-at_install')
class TestOportunidadDesdeLaBandeja(BandejaCase):

    def test_crear_oportunidad_no_duplica(self):
        accion = self.como_vendedora.action_crear_oportunidad()
        self.assertEqual(accion['res_model'], 'crm.lead')
        lead = self.env['crm.lead'].browse(accion['res_id'])
        self.assertEqual(lead.partner_id, self.conv.partner_id)
        self.assertEqual(lead.user_id, self.vendedora)
        self.assertEqual(self.conv.oportunidad_id, lead)
        otra = self.como_vendedora.action_crear_oportunidad()
        self.assertEqual(otra['res_id'], lead.id)
        self.assertEqual(self.env['crm.lead'].search_count([('partner_id', '=', self.conv.partner_id.id)]), 1)
        self.assertEqual(self.como_vendedora.action_ver_oportunidad()['res_id'], lead.id)


@tagged('post_install', '-at_install')
class TestVistas(BandejaCase):

    def test_todas_las_vistas_cargan(self):
        for modelo, tipos in (('dcasa.conversacion', ('kanban', 'list', 'form', 'search')),
                              ('dcasa.mensaje', ('list', 'form', 'search')),
                              ('dcasa.juan.ajustes', ('form',)),
                              ('res.partner', ('form',))):
            for tipo in tipos:
                with self.subTest(modelo=modelo, tipo=tipo):
                    vista = self.env[modelo].with_user(self.vendedora).get_view(view_type=tipo)
                    self.assertTrue(vista['arch'])

    def test_la_bandeja_usa_las_vistas_de_odoo_19(self):
        arch = self.env['dcasa.conversacion'].get_view(view_type='list')['arch']
        self.assertNotIn('<tree', arch)
        form = self.env['dcasa.conversacion'].get_view(view_type='form')['arch']
        self.assertIn('<chatter', form)

    def test_los_menus_estan_en_espanol_y_solo_para_ventas(self):
        raiz = self.env.ref('dcasa_conversaciones.menu_dcasa_conversaciones_root')
        self.assertEqual(raiz.name, 'Conversaciones')
        visibles = self.env['ir.ui.menu'].with_user(self.vendedora)._visible_menu_ids()
        self.assertIn(raiz.id, visibles)
        self.assertNotIn(raiz.id, self.env['ir.ui.menu'].with_user(self.interno)._visible_menu_ids())
        ajustes = self.env.ref('dcasa_conversaciones.menu_dcasa_juan_ajustes')
        self.assertNotIn(ajustes.id, visibles, 'Los ajustes son de Gerencia')
        self.assertIn(ajustes.id, self.env['ir.ui.menu'].with_user(self.gerente)._visible_menu_ids())

    def test_ajustes_abre_el_registro_unico(self):
        accion = self.env['dcasa.juan.ajustes'].with_user(self.gerente).action_abrir()
        self.assertEqual((accion['res_model'], accion['res_id']), ('dcasa.juan.ajustes', self.ajustes.id))
        with self.assertRaises(AccessError):
            self.env['dcasa.juan.ajustes'].with_user(self.portal).action_abrir()

    def test_el_cliente_ve_su_historial_de_conversaciones(self):
        partner = self.conv.partner_id.with_user(self.vendedora)
        self.assertEqual(partner.dcasa_conversaciones_count, 1)
        accion = partner.action_dcasa_ver_conversaciones()
        self.assertEqual(self.env['dcasa.conversacion'].search(accion['domain']), self.conv)
