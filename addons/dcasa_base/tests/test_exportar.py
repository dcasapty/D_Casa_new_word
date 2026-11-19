"""Exportar a Excel («Acción › Exportar» de las listas): solo Gerencia y los administradores (pedido del jefe,
2026-11-19: «bajar las facturas con su forma de pago»).

* El permiso es ``base.group_allow_export`` y Gerencia lo trae por su rol (``dcasa_roles.xml``); los administradores ya
  lo tenían. Caja, la Vendedora, contabilidad sola, un usuario interno cualquiera y el portal no lo tienen y reciben el
  error de siempre.
* Exportar no abre nada nuevo: el exportador lee con los permisos de quien exporta. Lo que Gerencia no puede leer (la
  clave del PIN de socios, los datos técnicos de Meta, los parámetros del sistema) sigue sin salir en un Excel, y el
  costo del producto sigue cerrado para quien no es de los que lo ven aunque alguien le diera el permiso de exportar.
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario


@tagged('post_install', '-at_install')
class TestExportar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exportar = cls.env.ref('base.group_allow_export')
        cls.gerencia = crear_usuario(cls.env, 'exp_gerencia', 'dcasa_base.group_gerencia')
        cls.admin = crear_usuario(cls.env, 'exp_admin', 'base.group_system')
        cls.caja = crear_usuario(cls.env, 'exp_caja', 'dcasa_base.group_caja')
        cls.vendedora = crear_usuario(cls.env, 'exp_vendedora', 'dcasa_base.group_vendedora')
        cls.contador = crear_usuario(cls.env, 'exp_contador', 'account.group_account_user')
        cls.interno = crear_usuario(cls.env, 'exp_interno')
        cls.portal = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Exp Portal', 'login': 'exp_portal',
            'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente para exportar', 'phone': '+507 6000-0000'})

    def test_gerencia_lo_trae_por_su_rol_y_los_demas_no(self):
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        self.assertIn(self.exportar, gerencia.implied_ids, 'viene en el rol, no puesto a mano a cada usuario')
        self.assertNotIn(self.exportar, self.gerencia.group_ids)
        for usuario in (self.gerencia, self.admin):
            with self.subTest(usuario.login):
                self.assertTrue(usuario.has_group('base.group_allow_export'))
        for usuario in (self.caja, self.vendedora, self.contador, self.interno, self.portal):
            with self.subTest(usuario.login):
                self.assertFalse(usuario.has_group('base.group_allow_export'))

    def test_nadie_mas_trae_el_permiso(self):
        """Todo el que lo tiene es de Gerencia, administrador o el sistema: ningún rol de la tienda se coló."""
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        quienes = self.env['res.users'].with_context(active_test=False).search(
            [('all_group_ids', 'in', self.exportar.ids)])
        self.assertTrue(quienes)
        for usuario in quienes:
            with self.subTest(usuario.login):
                self.assertTrue(usuario._is_superuser() or usuario.has_group('base.group_system')
                                or gerencia in usuario.all_group_ids, usuario.login)

    def test_quien_tiene_el_permiso_exporta_y_quien_no_recibe_el_error_de_siempre(self):
        for usuario in (self.gerencia, self.admin):
            with self.subTest(usuario.login):
                datos = self.cliente.with_user(usuario).export_data(['name', 'phone'])['datas']
                self.assertEqual(datos, [['Cliente para exportar', '+507 6000-0000']])
        for usuario in (self.caja, self.vendedora, self.contador, self.interno, self.portal):
            with self.subTest(usuario.login), self.assertRaisesRegex(UserError, '(?i)export'):
                self.cliente.with_user(usuario).export_data(['name'])

    def test_lo_que_gerencia_no_puede_leer_no_sale_en_un_excel(self):
        """El exportador no abre campos ni modelos cerrados: pedirlos por ``export_data`` falla igual que leerlos."""
        Partner = self.env['res.partner']
        con_gerencia = self.cliente.with_user(self.gerencia)
        cerrados = []
        if 'dcasa_pin_hash' in Partner._fields:      # la clave del PIN de Socios: solo administradores
            cerrados.append((con_gerencia, 'dcasa_pin_hash'))
        if 'dcasa_meta_fbp' in self.env['sale.order']._fields:    # datos del navegador para Meta: solo administradores
            orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
            cerrados.append((orden.with_user(self.gerencia), 'dcasa_meta_fbp'))
        self.assertTrue(cerrados, 'la prueba necesita algún campo cerrado a Gerencia')
        for registros, campo in cerrados:
            with self.subTest(campo):
                with self.assertRaises(AccessError):
                    registros.read([campo])
                with self.assertRaises(AccessError):
                    registros.export_data(['name', campo])
                self.assertNotIn(campo, registros.fields_get(), 'ni siquiera sale en la lista de campos del diálogo')

    def test_lo_que_gerencia_no_puede_leer_en_modelos_cerrados_tampoco(self):
        parametro = self.env['ir.config_parameter'].sudo().create({'key': 'dcasa.prueba.exportar', 'value': 'secreto'})
        with self.assertRaises(AccessError):
            parametro.with_user(self.gerencia).export_data(['key', 'value'])
        # El administrador sí: es suyo.
        self.assertEqual(parametro.with_user(self.admin).export_data(['key', 'value'])['datas'],
                         [['dcasa.prueba.exportar', 'secreto']])

    def test_el_costo_sigue_cerrado_aunque_alguien_pueda_exportar(self):
        """Caja con el permiso de exportar (por un descuido de configuración) no se baja el costo: el exportador lee
        con sus permisos y el costo está cerrado para ella. Gerencia, que ya lo ve, lo exporta."""
        producto = self.env['product.template'].create({'name': 'MUEBLE EXPORTAR', 'standard_price': 123.0})
        caja_con_permiso = crear_usuario(
            self.env, 'exp_caja_exporta', 'dcasa_base.group_caja', 'base.group_allow_export')
        self.assertTrue(caja_con_permiso.has_group('base.group_allow_export'))
        suyo = producto.with_user(caja_con_permiso)
        self.assertEqual(suyo.export_data(['name'])['datas'], [['MUEBLE EXPORTAR']])
        with self.assertRaises(AccessError):
            suyo.export_data(['name', 'standard_price'])
        self.assertNotIn('standard_price', suyo.fields_get())
        de_gerencia = producto.with_user(self.gerencia)
        self.assertEqual(de_gerencia.export_data(['name', 'standard_price'])['datas'], [['MUEBLE EXPORTAR', 123.0]])
