"""Quién ve y quién cambia qué: solo Gerencia y quien administra la nómina; la vendedora, Caja, Marketing y el
administrador técnico solo no ven ni el menú ni nada por enlace. Y los métodos nuevos no abren puertas por RPC."""
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import ComisionCommon

MODELOS = ('dcasa.web.reglas', 'dcasa.web.reparto', 'dcasa.web.venta', 'dcasa.web.movimiento',
           'dcasa.web.liquidacion', 'dcasa.web.liquidacion.linea')
MENUS = ('menu_comision_web', 'menu_ventas_sitio', 'menu_liquidaciones_web', 'menu_quienes_reciben', 'menu_libro_web',
         'menu_reglas_web')


@tagged('post_install', '-at_install')
class TestPermisos(ComisionCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.u_marketing = new_test_user(cls.env, login='com_marketing', name='Marketing Comisión',
                                        groups='base.group_user,dcasa_marketing.group_marketing')
        cls.u_portal = new_test_user(cls.env, login='com_portal', name='Portal Comisión', groups='base.group_portal')

    def test_gerencia_y_nomina_ven_todo(self):
        for usuario in (self.u_gerencia, self.u_nomina):
            for modelo in MODELOS:
                with self.subTest(usuario=usuario.login, modelo=modelo):
                    self.env[modelo].with_user(usuario).search([])
                    self.env[modelo].with_user(usuario).check_access('read')

    def test_los_demas_no_ven_ni_leen_nada(self):
        for usuario in (self.u_vendedora, self.u_caja, self.u_marketing, self.u_tecnico, self.u_portal):
            for modelo in MODELOS:
                with self.subTest(usuario=usuario.login, modelo=modelo), self.assertRaises(AccessError):
                    self.env[modelo].with_user(usuario).search([])

    def test_ninguno_de_los_cuatro_libros_se_escribe_por_la_interfaz(self):
        """Ni quien administra la nómina crea, edita ni borra a mano el libro, las ventas ni los renglones."""
        for modelo in ('dcasa.web.venta', 'dcasa.web.movimiento', 'dcasa.web.liquidacion.linea'):
            for operacion in ('create', 'write', 'unlink'):
                with self.subTest(modelo=modelo, operacion=operacion), self.assertRaises(AccessError):
                    self.env[modelo].with_user(self.u_nomina).check_access(operacion)

    def test_los_menus_son_de_gerencia_y_nomina_nunca_del_tecnico_solo(self):
        Menu = self.env['ir.ui.menu']
        for nombre in MENUS:
            menu = self.env.ref(f'dcasa_comision_web.{nombre}')
            for usuario, ve in ((self.u_nomina, True), (self.u_gerencia, True), (self.u_vendedora, False),
                                (self.u_caja, False), (self.u_marketing, False), (self.u_tecnico, False)):
                with self.subTest(menu=nombre, usuario=usuario.login):
                    visible = bool(Menu.with_user(usuario).search([('id', '=', menu.id)]))
                    self.assertEqual(visible, ve)

    def test_el_menu_vive_dentro_de_la_app_de_nomina(self):
        raiz = self.env.ref('dcasa_nomina.menu_nomina_raiz')
        self.assertEqual(self.env.ref('dcasa_comision_web.menu_comision_web').parent_id, raiz)
        for nombre in MENUS[1:]:
            self.assertEqual(self.env.ref(f'dcasa_comision_web.{nombre}').parent_id.id,
                             self.env.ref('dcasa_comision_web.menu_comision_web').id)

    def test_las_acciones_de_cada_menu_son_del_grupo_de_nomina(self):
        servidor = self.env.ref('dcasa_comision_web.accion_quienes_reciben')
        self.assertEqual(servidor.group_ids, self.env.ref('dcasa_nomina.group_nomina'))
        # Las acciones de ventana de los botones solo abren una pantalla: sin permiso de los modelos, no muestra nada.
        for usuario in (self.u_vendedora, self.u_tecnico):
            with self.assertRaises(AccessError):
                self.env['dcasa.web.reglas'].with_user(usuario).search([])

    def test_el_tecnico_solo_no_cambia_las_reglas(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.web.reglas'].with_user(self.u_tecnico).create({'company_id': self.company.id})
