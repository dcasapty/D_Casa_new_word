"""Etapa 3 (2026-10-16): al cotizar, una persona sale una sola vez y se avisa si parece repetida.

La dueña veía a la misma persona hasta cinco veces al elegir el cliente: su ficha, su usuario, su contacto de
empleado y sus direcciones. Los usuarios y empleados no se tocan: solo dejan de ofrecerse como cliente."""
from odoo.tests import TransactionCase, new_test_user, tagged

SIN = {'dcasa_sin_duplicados': True}


@tagged('post_install', '-at_install')
class TestCotizar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner'].with_context(**SIN)
        cls.ficha = Partner.create({'name': 'Marta Cotiza', 'phone': '6555-0201', 'email': 'marta.cotiza@x.com'})
        cls.entrega = Partner.create({'name': 'Marta Cotiza', 'parent_id': cls.ficha.id, 'type': 'delivery',
                                      'street': 'Calle 1'})
        cls.usuaria = new_test_user(cls.env, login='marta_cotiza', name='Marta Cotiza',
                                    groups='base.group_user,dcasa_base.group_vendedora')
        cls.empleada = cls.env['hr.employee'].create({'name': 'Marta Cotiza'})
        cls.portal = new_test_user(cls.env, login='cliente_portal_cotiza', name='Marta Cotiza Portal',
                                   groups='base.group_portal')
        cls.vendedora = new_test_user(cls.env, login='vend_cotiza', name='Vendedora Cotiza',
                                      groups='base.group_user,dcasa_base.group_vendedora')

    def _dominio(self, usuario=None):
        Orden = self.env['sale.order'].with_user(usuario) if usuario else self.env['sale.order']
        return Orden._fields['partner_id'].get_comodel_domain(Orden)

    def test_el_selector_de_cliente_solo_ofrece_fichas_de_clientes(self):
        todos = (self.ficha | self.entrega | self.usuaria.partner_id | self.empleada.work_contact_id
                 | self.portal.partner_id | self.env.company.partner_id)
        ofrecidos = self.env['res.partner'].search(list(self._dominio()) + [('id', 'in', todos.ids)])
        self.assertEqual(ofrecidos, self.ficha | self.portal.partner_id,
                         'Solo la ficha y quien se registró en la tienda; no el usuario, la empleada, la dirección '
                         'ni la empresa propia')

    def test_la_vendedora_busca_clientes_sin_error(self):
        """La Vendedora no ve empleados: el selector no puede depender de leerlos."""
        dominio = list(self._dominio(self.vendedora))
        encontrados = self.env['res.partner'].with_user(self.vendedora).search(
            dominio + [('name', 'ilike', 'Marta Cotiza')])
        self.assertIn(self.ficha, encontrados)
        self.assertNotIn(self.usuaria.partner_id, encontrados)
        campos = self.env['sale.order'].with_user(self.vendedora).fields_get(['partner_id'])
        self.assertIn('partner_id', campos)
        self.env['sale.order'].with_user(self.vendedora).get_views([(False, 'form')])

    def test_una_cotizacion_vieja_con_otro_contacto_se_sigue_abriendo(self):
        """El dominio es del selector: lo ya guardado (p. ej. un pedido web con una dirección) no se rompe."""
        orden = self.env['sale.order'].create({'partner_id': self.entrega.id})
        self.assertEqual(orden.partner_id, self.entrega)

    def test_avisa_si_otra_ficha_tiene_el_mismo_celular(self):
        otra = self.env['res.partner'].with_context(**SIN).create({'name': 'M. Cotiza', 'phone': '+507 6555 0201'})
        orden = self.env['sale.order'].new({'partner_id': self.ficha.id})
        aviso = orden._onchange_dcasa_cliente_duplicado()
        self.assertTrue(aviso and aviso.get('warning'))
        self.assertIn('M. Cotiza', aviso['warning']['message'])
        self.assertIn('6555-0201', aviso['warning']['message'])
        self.assertIn('Posibles duplicados', aviso['warning']['message'])
        # Elegir la dirección de entrega avisa igual: cuenta la ficha de la que cuelga.
        orden = self.env['sale.order'].new({'partner_id': self.entrega.id})
        self.assertIn(otra.name, orden._onchange_dcasa_cliente_duplicado()['warning']['message'])

    def test_sin_repetidos_no_avisa(self):
        orden = self.env['sale.order'].new({'partner_id': self.ficha.id})
        self.assertIsNone(orden._onchange_dcasa_cliente_duplicado())

    def test_el_usuario_o_la_empleada_con_el_mismo_celular_no_cuentan_como_repetidos(self):
        self.usuaria.partner_id.with_context(**SIN).phone = '6555-0201'
        self.empleada.work_contact_id.with_context(**SIN).phone = '6555-0201'
        orden = self.env['sale.order'].new({'partner_id': self.ficha.id})
        self.assertIsNone(orden._onchange_dcasa_cliente_duplicado())
