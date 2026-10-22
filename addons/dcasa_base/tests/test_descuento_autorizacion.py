"""D1: un descuento mayor al tope se aplica solo con la clave de Gerencia (una vez, para esa cotización y ese monto,
con vencimiento) o con la aprobación de Gerencia desde su usuario; todo queda registrado."""
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models import descuento_autorizacion as D
from .test_roles import crear_usuario

CLASE = 'odoo.addons.dcasa_base.models.descuento_autorizacion.DcasaDescuentoAutorizacion'


@tagged('post_install', '-at_install')
class TestDescuentoConClave(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        cls.vendedora = crear_usuario(env, 'desc_vendedora', 'dcasa_base.group_vendedora')
        cls.otra = crear_usuario(env, 'desc_otra', 'dcasa_base.group_vendedora')
        cls.gerente = crear_usuario(env, 'desc_gerente', 'dcasa_base.group_gerencia')
        cls.cliente = env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA DESCUENTO', 'phone': '6000-0041', 'email': 'cliente.descuento@example.com'})
        cls.producto = env['product.product'].create({'name': 'Comedor descuento', 'list_price': 1000.0,
                                                      'taxes_id': [Command.clear()]})

    def setUp(self):
        super().setUp()
        self.claves = {}
        self.sin_telegram = False
        prueba = self

        def _enviar(solicitud, claves):
            prueba.claves.update({usuario.login: codigo for usuario, codigo in claves.items()})
            if prueba.sin_telegram:
                return solicitud.env['res.users']
            return solicitud.env['res.users'].browse([u.id for u in claves])

        parche = patch(f'{CLASE}._dcasa_enviar_claves', autospec=True, side_effect=_enviar)
        parche.start()
        self.addCleanup(parche.stop)
        self.orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})

    def _pedir(self, usuario=None, **valores):
        asistente = self.env['dcasa.descuento.pedir'].with_user(usuario or self.vendedora).create({
            'order_id': self.orden.id, 'tipo': 'porcentaje', 'porcentaje': 15, 'motivo': 'Lleva el juego completo',
            **valores})
        asistente.action_pedir()
        return asistente

    def test_sin_clave_el_tope_sigue(self):
        with self.assertRaises(ValidationError):
            self.orden.order_line.with_user(self.vendedora).write({'discount': 15})

    def test_la_clave_correcta_aplica_el_descuento_y_queda_registrado(self):
        asistente = self._pedir()
        solicitud = asistente.autorizacion_id
        self.assertEqual(solicitud.estado, 'pendiente')
        self.assertEqual(solicitud.rebaja_estimada, 150.0)
        self.assertIn('desc_gerente', self.claves)
        self.assertNotIn('desc_vendedora', self.claves, 'quien pide no recibe clave')
        asistente.clave = self.claves['desc_gerente']
        asistente.action_aplicar()
        self.assertEqual(solicitud.estado, 'usada')
        self.assertEqual(solicitud.aprobador_id, self.gerente)
        self.assertEqual(solicitud.canal, 'telegram')
        self.assertAlmostEqual(self.orden.amount_total, 850.0, places=2)
        self.assertIn('Descuento autorizado', self.orden.message_ids[0].body)
        # La clave ya se usó: no se vuelve a aplicar.
        listo, motivo = solicitud.with_user(self.vendedora)._dcasa_usar_clave(self.claves['desc_gerente'])
        self.assertFalse(listo)
        self.assertAlmostEqual(self.orden.amount_total, 850.0, places=2)

    def test_despues_no_se_puede_empeorar_el_descuento_autorizado(self):
        asistente = self._pedir()
        asistente.clave = self.claves['desc_gerente']
        asistente.action_aplicar()
        rebaja = self.orden.order_line.filtered(lambda linea: linea.price_unit < 0)
        with self.assertRaises(ValidationError):
            rebaja.with_user(self.vendedora).write({'price_unit': rebaja.price_unit * 2})
        with self.assertRaises(ValidationError):
            self.orden.order_line.filtered(lambda linea: linea.price_unit > 0).with_user(self.vendedora).write(
                {'discount': 20})

    def test_clave_equivocada_cuenta_y_bloquea(self):
        asistente = self._pedir()
        solicitud = asistente.autorizacion_id
        malo = '000000' if self.claves['desc_gerente'] != '000000' else '111111'
        for _ in range(D.MAX_INTENTOS - 1):
            asistente.clave = malo
            asistente.action_aplicar()
            self.assertTrue(asistente.aviso)
        self.assertEqual(solicitud.intentos, D.MAX_INTENTOS - 1)
        asistente.clave = malo
        asistente.action_aplicar()
        self.assertEqual(solicitud.estado, 'bloqueada')
        asistente.clave = self.claves['desc_gerente']
        asistente.action_aplicar()
        self.assertEqual(solicitud.estado, 'bloqueada')
        self.assertAlmostEqual(self.orden.amount_total, 1000.0, places=2)

    def test_la_clave_vence(self):
        asistente = self._pedir()
        solicitud = asistente.autorizacion_id
        solicitud.sudo().vence = fields.Datetime.now() - timedelta(minutes=1)
        asistente.clave = self.claves['desc_gerente']
        asistente.action_aplicar()
        self.assertEqual(solicitud.estado, 'vencida')
        self.assertAlmostEqual(self.orden.amount_total, 1000.0, places=2)

    def test_si_la_cotizacion_cambia_la_clave_no_sirve(self):
        asistente = self._pedir()
        self.orden.with_user(self.vendedora).write({'order_line': [Command.create(
            {'product_id': self.producto.id, 'product_uom_qty': 1})]})
        asistente.clave = self.claves['desc_gerente']
        with self.assertRaises(UserError):
            asistente.action_aplicar()

    def test_la_clave_es_solo_de_quien_pidio(self):
        asistente = self._pedir()
        with self.assertRaises(AccessError):
            asistente.autorizacion_id.with_user(self.otra)._dcasa_usar_clave(self.claves['desc_gerente'])

    def test_dentro_del_tope_no_hace_falta_clave(self):
        with self.assertRaises(UserError):
            self._pedir(porcentaje=8)
        with self.assertRaises(UserError):
            self._pedir(tipo='monto', monto=50)

    def test_sin_telegram_lo_aprueba_gerencia_en_persona(self):
        self.sin_telegram = True
        asistente = self._pedir(tipo='monto', monto=200)
        solicitud = asistente.autorizacion_id
        self.assertFalse(solicitud.enviada_a)
        with self.assertRaises(AccessError):
            solicitud.with_user(self.vendedora).action_aprobar()
        solicitud.with_user(self.gerente).action_aprobar()
        self.assertEqual(solicitud.estado, 'usada')
        self.assertEqual(solicitud.canal, 'persona')
        self.assertEqual(solicitud.aprobador_id, self.gerente)
        self.assertAlmostEqual(self.orden.amount_total, 800.0, places=2)

    def test_gerencia_rechaza(self):
        solicitud = self._pedir().autorizacion_id
        solicitud.with_user(self.gerente).action_rechazar()
        self.assertEqual(solicitud.estado, 'rechazada')
        listo, _motivo = solicitud.with_user(self.vendedora)._dcasa_usar_clave(self.claves['desc_gerente'])
        self.assertFalse(listo)

    def test_cada_quien_ve_lo_suyo_y_la_clave_no_se_lee(self):
        solicitud = self._pedir().autorizacion_id
        Solicitudes = self.env['dcasa.descuento.autorizacion']
        self.assertIn(solicitud, Solicitudes.with_user(self.vendedora).search([]))
        self.assertNotIn(solicitud, Solicitudes.with_user(self.otra).search([]))
        self.assertIn(solicitud, Solicitudes.with_user(self.gerente).search([]))
        with self.assertRaises(AccessError):
            solicitud.with_user(self.vendedora).write({'estado': 'usada'})
        with self.assertRaises(AccessError):
            self.env['dcasa.descuento.clave'].with_user(self.gerente).search([])
        huellas = self.env['dcasa.descuento.clave'].search([('autorizacion_id', '=', solicitud.id)])
        self.assertTrue(huellas)
        self.assertNotIn(self.claves['desc_gerente'], huellas.mapped('clave_hash'))

    def test_otra_vendedora_no_pide_por_una_cotizacion_ajena(self):
        with self.assertRaises(AccessError):
            self._pedir(usuario=self.otra)
