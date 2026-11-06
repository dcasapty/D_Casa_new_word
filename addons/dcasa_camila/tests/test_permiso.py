"""El permiso del cliente: la casilla de la ficha, la baja (final), la fusión de fichas, a quién se le puede escribir
y el correo que dio cuando Sofía se lo pidió (solo si el mensaje que salió decía «promociones»)."""
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_conversaciones.models.mensaje import CLAVE_SISTEMA
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import CamilaComun


@tagged('post_install', '-at_install')
class TestPermiso(CamilaComun):

    def test_la_vendedora_marca_la_casilla_y_queda_con_quien_y_cuando(self):
        self.assertEqual(self.ana.dcasa_promos_estado, 'sin')
        self.env.invalidate_all()   # como el formulario: nada calculado de antes en la memoria
        self.ana.with_user(self.vendedora).write({'dcasa_promos': True})
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.dcasa_promos_estado, 'si')
        self.assertEqual(self.ana.dcasa_promos_origen, 'tienda')
        self.assertEqual(self.ana.dcasa_promos_usuario_id, self.vendedora)
        self.assertTrue(self.ana.dcasa_promos_fecha)
        contacto = self.env['res.partner'].create({'name': 'Persona de Ana', 'parent_id': self.ana.id,
                                                   'type': 'contact'})
        self.assertTrue(contacto.dcasa_promos, 'El permiso vive en la ficha comercial')

    def test_el_permiso_no_se_escribe_a_mano(self):
        for valores in ({'dcasa_promos_fecha': fields.Datetime.now()}, {'dcasa_promos_origen': 'web'},
                        {'dcasa_promos_baja_fecha': False}):
            with self.subTest(valores), self.assertRaises(AccessError):
                self.ana.with_user(self.gerencia).write(valores)
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.gerencia).create({
                'name': 'X', 'email': 'x.zzcm@example.com', 'dcasa_promos_origen': 'web'})

    def test_la_baja_es_final_y_la_anota_quien_edita_al_cliente(self):
        self.permiso(self.ana)
        self.ana.with_user(self.vendedora).action_dcasa_promos_baja()
        self.assertEqual(self.ana.dcasa_promos_estado, 'baja')
        self.assertEqual((self.ana.dcasa_promos_baja_origen, self.ana.dcasa_promos_baja_usuario_id),
                         ('ficha', self.vendedora))
        with self.assertRaises(UserError):
            self.ana.with_user(self.vendedora).write({'dcasa_promos': True})
        # Ni el enlace, ni Sofía, ni el sistema la vuelven a dar de alta.
        self.assertFalse(self.ana.sudo()._dcasa_promos_registrar('factura'))
        self.assertEqual(self.ana.dcasa_promos_estado, 'baja')
        self.assertNotIn(self.ana, self.env['res.partner']._dcasa_promos_con_permiso().values())

    def test_quien_no_puede_editar_al_cliente_no_anota_la_baja(self):
        self.permiso(self.ana)
        portal = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Portal Zzcm', 'login': 'zzcm_portal',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            self.ana.with_user(portal).action_dcasa_promos_baja()
        self.assertEqual(self.ana.dcasa_promos_estado, 'si')

    def test_a_quien_se_le_escribe(self):
        self.permiso(self.ana, self.beto, self.carla)
        self.beto.sudo()._dcasa_promos_baja('correo')
        self.carla.dcasa_no_contactar = True
        sin_correo = self.env['res.partner'].create({'name': 'Sin Correo Zzcm', 'phone': '6000-1009'})
        self.permiso(sin_correo)
        del_equipo = self.env['res.partner'].create({'name': 'Equipo Zzcm', 'email': self.gerencia.email,
                                                     'phone': '6000-1010'})
        self.permiso(del_equipo)
        con_permiso = self.env['res.partner']._dcasa_promos_con_permiso()
        self.assertIn('ana.zzcm@example.com', con_permiso)
        for fuera in ('beto.zzcm@example.com', 'carla.zzcm@example.com', self.gerencia.email):
            self.assertNotIn(fuera, con_permiso, 'Con baja, sin querer contacto o del equipo: nunca')
        self.assertNotIn(sin_correo, con_permiso.values())


@tagged('post_install', '-at_install')
class TestFusion(CamilaComun):

    def fusionar(self, queda, se_va):
        wizard = self.env['base.partner.merge.automatic.wizard'].with_context(active_test=False).create({})
        wizard._merge((queda | se_va).ids, queda)

    def test_se_queda_el_permiso_mas_reciente(self):
        viejo = fields.Datetime.now() - timedelta(days=90)
        self.ana.sudo()._dcasa_promos_registrar('tienda', self.vendedora, fecha=viejo)
        self.beto.sudo()._dcasa_promos_registrar('factura')
        self.beto.sudo().write({'email': 'beto.otro.zzcm@example.com'})
        self.fusionar(self.ana, self.beto)
        self.assertEqual(self.ana.dcasa_promos_origen, 'factura', 'El más reciente, entero')
        self.assertFalse(self.ana.dcasa_promos_usuario_id, 'Sin mezclar el «quién» de la otra ficha')
        self.assertGreater(self.ana.dcasa_promos_fecha, viejo)

    def test_cualquier_baja_manda(self):
        self.ana.sudo()._dcasa_promos_registrar('tienda')
        self.beto.sudo()._dcasa_promos_baja('correo')
        self.beto.sudo().write({'email': 'beto.otro.zzcm@example.com'})
        self.fusionar(self.ana, self.beto)
        self.assertEqual(self.ana.dcasa_promos_estado, 'baja')
        self.assertEqual(self.ana.dcasa_promos_baja_origen, 'correo')


@tagged('post_install', '-at_install')
class TestPermisoDeSofia(CamilaComun):
    """Gerencia puede cambiar el texto de Sofía y la vendedora puede editarlo antes de enviarlo: solo cuenta lo que
    de verdad salió por el chat (aquí, «Abrir el chat»: el primer mensaje de la vendedora; «Enviar ya» en
    test_revision)."""

    PEDIDO = ('¡Hola Ana! Soy Vendedora de D\'CASA. Para atenderte mejor, ¿me regalas tu correo? Así te avisamos de '
              'promociones, del programa Socios D\'CASA y de los beneficios de cumpleaños.')

    def setUp(self):
        super().setUp()
        self.ficha = self.env['res.partner'].create({'name': 'Dani Zzcm', 'phone': '6000-1020'})
        self.conv = self.env['dcasa.conversacion'].sudo().create({
            'canal': 'whatsapp_cloud', 'id_externo': '50760001020', 'partner_id': self.ficha.id, 'estado': 'humano'})
        self.hace_un_dia = fields.Datetime.now() - timedelta(days=1)

    def propuesta(self, accion='chat'):
        return self.env['dcasa.sofia.propuesta'].sudo().create({
            'clave': f'pedir_datos:partner:{self.ficha.id}', 'tipo': 'pedir_datos', 'estado': 'aplicada',
            'pide_datos': True, 'partner_id': self.ficha.id, 'conversacion_id': self.conv.id, 'accion': accion,
            'resuelta_por': self.vendedora.id, 'resuelta_en': self.hace_un_dia})

    def mensaje(self, autor, texto, minutos):
        Mensaje = self.env['dcasa.mensaje'].sudo().with_context(**{CLAVE_SISTEMA: True})
        return Mensaje.create({
            'conversacion_id': self.conv.id, 'id_mensaje': f'm-{autor}-{minutos}', 'tipo': 'mensaje',
            'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': texto,
            'ts': self.hace_un_dia + timedelta(minutes=minutos),
            'estado_envio': 'recibido' if autor == 'cliente' else 'enviado',
            'usuario_id': self.vendedora.id if autor == 'vendedora' else False})

    def test_cuenta_si_el_mensaje_que_salio_decia_promociones(self):
        self.propuesta()
        self.mensaje('vendedora', self.PEDIDO, 1)
        respuesta = self.mensaje('cliente', 'Claro, es dani.zzcm@example.com', 30)
        self.ficha.email = 'dani.zzcm@example.com'   # «Guarda sus datos» lo guardó en su ficha
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 1)
        self.assertEqual(self.ficha.dcasa_promos_origen, 'sofia_whatsapp')
        self.assertEqual(self.ficha.dcasa_promos_fecha, respuesta.ts, 'La fecha es la de cuando dio el correo')
        self.assertEqual(self.ficha.dcasa_promos_correo, 'dani.zzcm@example.com')
        self.assertEqual(self.ficha.dcasa_promos_usuario_id, self.vendedora)
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0, 'Una sola vez')

    def test_no_cuenta_si_el_texto_que_salio_no_lo_decia(self):
        self.propuesta(accion='chat')
        self.mensaje('vendedora', '¿Me regalas tu correo para mandarte la cotización?', 5)
        self.mensaje('cliente', 'dani.zzcm@example.com', 30)
        self.ficha.email = 'dani.zzcm@example.com'
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0)
        self.assertEqual(self.ficha.dcasa_promos_estado, 'sin')

    def test_no_cuenta_otro_correo_ni_una_baja_ni_sin_respuesta(self):
        self.propuesta()
        self.mensaje('vendedora', self.PEDIDO, 1)
        self.ficha.email = 'dani.zzcm@example.com'
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0, 'No contestó')
        self.mensaje('cliente', 'mi correo es otro.zzcm@example.com', 20)
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0, 'Su ficha tiene otro correo')
        self.mensaje('cliente', 'perdón, es dani.zzcm@example.com', 40)
        self.ficha.sudo()._dcasa_promos_baja('ficha')
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0, 'Una baja se respeta siempre')

    def test_no_cuenta_lo_que_contesto_dias_despues(self):
        self.propuesta()
        self.mensaje('vendedora', self.PEDIDO, 1)
        self.mensaje('cliente', 'dani.zzcm@example.com', 60 * 49)
        self.ficha.email = 'dani.zzcm@example.com'
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0)
