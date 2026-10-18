"""Ajustes › Meta: apagado de fábrica, compuertas al encender, el token que nunca se ve y el botón de
prueba. Ninguna prueba llama a Meta."""
import json

from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import tagged

from .common import CODIGO, PIXEL, TOKEN, MetaCase, publicar_privacidad, respuesta


@tagged('post_install', '-at_install')
class TestAjustes(MetaCase):

    def ajustes(self, **valores):
        # Las compuertas son del negocio, no de permisos: se prueban como superusuario (los permisos van aparte).
        return self.env['res.config.settings'].create(valores)

    def test_el_administrador_ve_la_seccion_de_meta_en_ajustes(self):
        """En D'CASA nadie tiene «Editor y diseñador»: la sección «Sitio web» de Ajustes no se ve. La de Meta va
        aparte y la ve un administrador; también desde Sitio web › Configuración."""
        vista = self.env['res.config.settings'].with_user(self.admin).get_views([(False, 'form')])['views']['form']
        self.assertIn('name="dcasa_meta_pixel_id"', vista['arch'])
        self.assertIn('name="action_dcasa_meta_enviar_prueba"', vista['arch'])
        with self.assertRaises(AccessError, msg='Ajustes es solo de administradores'):
            self.env['res.config.settings'].with_user(self.gerencia).get_views([(False, 'form')])
        menu = self.env.ref('dcasa_meta_eventos.menu_dcasa_meta_ajustes')
        self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(self.admin)._visible_menu_ids())
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.gerencia)._visible_menu_ids())

    def test_todo_viene_apagado_y_vacio(self):
        # Lo que dejó la instalación (setUp no tocó los interruptores de verdad: los borra, igual que de fábrica).
        ajustes = self.ajustes()
        self.assertFalse(ajustes.dcasa_meta_pixel_id)
        self.assertFalse(ajustes.dcasa_meta_pixel_activo)
        self.assertFalse(ajustes.dcasa_meta_capi_web)
        self.assertFalse(ajustes.dcasa_meta_capi_tienda)
        self.assertFalse(ajustes.dcasa_meta_test_event_code)
        self.assertEqual(ajustes.dcasa_meta_graph_version, 'v26.0')
        self.assertIn('falta', ajustes.dcasa_meta_token_estado)
        self.assertFalse(self.website.cookies_bar, 'El aviso de cookies tampoco se enciende solo')

    def test_el_pixel_no_se_enciende_sin_id_ni_sin_la_seccion_de_privacidad(self):
        with self.assertRaisesRegex(UserError, 'ID del píxel'):
            self.ajustes(dcasa_meta_pixel_activo=True).execute()
        with self.assertRaisesRegex(UserError, 'solo números'):
            self.ajustes(dcasa_meta_pixel_id='abc').execute()
        with self.assertRaisesRegex(UserError, 'política de privacidad'):
            self.ajustes(dcasa_meta_pixel_id=PIXEL, dcasa_meta_pixel_activo=True).execute()
        self.assertFalse(self.ICP.get_param('dcasa_meta.pixel_activo'))

    def test_con_la_seccion_publicada_se_enciende_con_el_aviso_de_cookies(self):
        publicar_privacidad(self.env)
        self.website.cookies_bar = False
        self.env.cr.precommit.data.pop('dcasa_tienda_borde.pendientes', None)
        self.ajustes(dcasa_meta_pixel_id=PIXEL, dcasa_meta_pixel_activo=True).execute()
        self.assertTrue(self.ICP.get_param('dcasa_meta.pixel_activo'))
        self.assertTrue(self.website.cookies_bar, 'Sin aceptar las cookies el píxel no carga: el aviso se enciende')
        self.assertIn(0, self.env.cr.precommit.data.get('dcasa_tienda_borde.pendientes', {}),
                      'Las páginas guardadas en el borde se vuelven a armar')

    def test_las_ventas_no_se_encienden_sin_token(self):
        publicar_privacidad(self.env)
        for campo in ('dcasa_meta_capi_web', 'dcasa_meta_capi_tienda'):
            with self.subTest(campo=campo), self.assertRaisesRegex(UserError, 'token'):
                self.ajustes(dcasa_meta_pixel_id=PIXEL, **{campo: True}).execute()
        self.con_token()
        self.ajustes(dcasa_meta_pixel_id=PIXEL, dcasa_meta_capi_web=True, dcasa_meta_capi_tienda=True).execute()
        self.assertTrue(self.ICP.get_param('dcasa_meta.capi_web'))
        self.assertTrue(self.ICP.get_param('dcasa_meta.capi_tienda'))

    def test_las_ventas_tampoco_sin_la_seccion_de_privacidad(self):
        self.con_token()
        with self.assertRaisesRegex(UserError, 'política de privacidad'):
            self.ajustes(dcasa_meta_pixel_id=PIXEL, dcasa_meta_capi_tienda=True).execute()

    def test_el_token_nunca_se_ve_ni_se_guarda(self):
        self.con_token()
        ajustes = self.ajustes()
        self.assertEqual(ajustes.dcasa_meta_token_estado, 'Token de Meta: cargado')
        leido = json.dumps(ajustes.read()[0], default=str)
        self.assertNotIn(TOKEN, leido)
        publicar_privacidad(self.env)
        self.ajustes(dcasa_meta_pixel_id=PIXEL, dcasa_meta_capi_web=True, dcasa_meta_test_event_code=CODIGO).execute()
        self.assertFalse(self.env['ir.config_parameter'].sudo().search([('value', 'ilike', TOKEN[:20])]))
        self.env.cr.execute("SELECT count(*) FROM ir_config_parameter WHERE value LIKE %s", [f'%{TOKEN}%'])
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_en_staging_lo_dice(self):
        self.en_staging()
        self.assertIn('no es el de producción', self.ajustes().dcasa_meta_estado)


@tagged('post_install', '-at_install')
class TestEventoDePrueba(MetaCase):

    def boton(self, **valores):
        return self.env['res.config.settings'].create(valores).action_dcasa_meta_enviar_prueba()

    def test_exige_codigo_de_prueba_y_token(self):
        with self.assertRaisesRegex(UserError, 'código de prueba'):
            self.boton(dcasa_meta_pixel_id=PIXEL)
        with self.assertRaisesRegex(UserError, 'token'):
            self.boton(dcasa_meta_pixel_id=PIXEL, dcasa_meta_test_event_code=CODIGO)
        self.post.assert_not_called()

    def test_manda_un_solo_evento_de_prueba_sin_datos_de_personas(self):
        self.con_token()
        self.responder()
        accion = self.boton(dcasa_meta_pixel_id=PIXEL, dcasa_meta_test_event_code=CODIGO)
        self.post.assert_called_once()
        cuerpo = self.post.call_args.kwargs['data']
        self.assertEqual(cuerpo['test_event_code'], CODIGO)
        self.assertNotIn(TOKEN, self.post.call_args.args[0])
        eventos = json.loads(cuerpo['data'])
        self.assertEqual(len(eventos), 1)
        evento = eventos[0]
        self.assertEqual(evento['event_name'], 'PageView')
        self.assertEqual(evento['action_source'], 'website')
        self.assertRegex(evento['event_id'], r'^prueba-[0-9a-f-]{36}$')
        self.assertTrue(evento['event_source_url'].endswith('/'))
        self.assertEqual(set(evento['user_data']), {'client_user_agent', 'external_id'})
        self.assertEqual(evento['user_data']['client_user_agent'], 'DCASA-prueba')
        self.assertNotIn('custom_data', evento)
        # Muestra el resultado y el rastreo de Meta, sin el token.
        mensaje = accion['params']['message']
        self.assertIn('AbCdEfTrace', mensaje)
        self.assertNotIn(TOKEN, mensaje)
        fila = self.Evento.search([('event_id', '=', evento['event_id'])])
        self.assertEqual((fila.estado, fila.es_prueba, fila.origen), ('enviado', True, 'prueba'))

    def test_si_meta_lo_rechaza_lo_dice_sin_filtrar_el_token(self):
        self.con_token()
        self.responder(respuesta(400, {'error': {'code': 100, 'message': f'malo {TOKEN}', 'fbtrace_id': 'Zz9'}}))
        accion = self.boton(dcasa_meta_pixel_id=PIXEL, dcasa_meta_test_event_code=CODIGO)
        self.assertEqual(accion['params']['type'], 'danger')
        self.assertIn('Zz9', accion['params']['message'])
        self.assertNotIn(TOKEN, accion['params']['message'])

    def test_solo_un_administrador_lo_manda(self):
        self.con_token()
        self.ICP.set_param('dcasa_meta.pixel_id', PIXEL)
        self.ICP.set_param('dcasa_meta.test_event_code', CODIGO)
        for usuario in (self.vendedora, self.gerencia):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                # Como lo llamaría la interfaz o alguien por RPC (con ids vacíos).
                call_kw(self.env(user=usuario)['res.config.settings'], 'action_dcasa_meta_enviar_prueba', [[]], {})
        self.post.assert_not_called()
