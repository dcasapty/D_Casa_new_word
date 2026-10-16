"""El ícono de Empleados es de la marca; nadie se da de alta pegando texto; el módulo no trae datos de personas; y la
Vendedora no ve el menú «Empleados» (el Directorio de compañeros), sin perder nada de lo demás."""
import os
import re

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import convert_file


def crear_usuario(env, login, *grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login,
        'group_ids': [Command.set([env.ref(g).id for g in ('base.group_user', *grupos)])]})


def menus_a_la_vista(env, usuario):
    """Ids externos de los menús que la persona ve de verdad: el menú y todos sus padres a la vista."""
    visibles = env['ir.ui.menu'].with_user(usuario)._visible_menu_ids()
    resultado = set()
    for menu in env['ir.ui.menu'].sudo().browse(sorted(visibles)):
        padre = menu
        while padre and padre.id in visibles:
            padre = padre.parent_id
        if not padre:
            xmlid = menu.get_external_id().get(menu.id)
            if xmlid:
                resultado.add(xmlid)
    return resultado


@tagged('post_install', '-at_install')
class TestEquipo(TransactionCase):

    def test_el_menu_empleados_tiene_el_icono_de_la_marca(self):
        menu = self.env.ref('hr.menu_hr_root')
        self.assertEqual(menu.web_icon, 'dcasa_equipo,static/src/img/empleados.svg')
        self.assertTrue(menu.web_icon_data)
        ruta = os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'img', 'empleados.svg')
        with open(ruta, encoding='utf-8') as f:
            svg = f.read()
        # Índigo: el color de la familia «Socios y equipo» del menú (decisión de la dueña, 2026-10-16); el amarillo
        # de la marca queda de acento, nunca de fondo (tocaría el blanco de la barra).
        self.assertIn('#4B3FA8', svg)
        self.assertIn('#FED00F', svg)
        self.assertRegex(svg, r'<rect[^>]*fill="#4B3FA8"')
        self.assertNotIn('gradient', svg.lower())

    def test_no_hay_alta_de_personas_por_texto(self):
        """La dueña pidió que las personas no se creen pegando una lista (2026-10-11); se retiró la pantalla."""
        self.assertNotIn('dcasa.equipo.alta', self.env)
        self.assertNotIn('dcasa.equipo.alta.linea', self.env)
        self.assertFalse(self.env['ir.ui.menu'].search([('name', '=', 'Alta del equipo')]))
        self.assertFalse(self.env['ir.actions.act_window'].search([('res_model', '=', 'dcasa.equipo.alta')]))

    def test_el_modulo_no_trae_datos_de_personas(self):
        """Los nombres y correos del equipo viven solo en la base de datos de Odoo, nunca en el repositorio."""
        raiz = os.path.join(os.path.dirname(__file__), '..')
        permitidos = {'equipo-prueba.test', 'ejemplo.com'}
        encontrados = set()
        for carpeta, _dirs, archivos in os.walk(raiz):
            for archivo in archivos:
                if not archivo.endswith(('.py', '.xml', '.csv', '.json', '.md', '.svg')):
                    continue
                with open(os.path.join(carpeta, archivo), encoding='utf-8') as f:
                    for dominio in re.findall(r'[\w.+-]+@([\w-]+(?:\.[\w-]+)+)', f.read()):
                        if dominio.lower() not in permitidos:
                            encontrados.add((archivo, dominio))
        self.assertFalse(encontrados, "Hay correos reales dentro del módulo")


@tagged('post_install', '-at_install')
class TestMenuEmpleadosPorRol(TransactionCase):
    """«Empleados» (el Directorio) lo ven Gerencia, administradores, contabilidad y quien administra al personal."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'equipo_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'equipo_gerencia', 'dcasa_base.group_gerencia')
        cls.contador = crear_usuario(cls.env, 'equipo_contador', 'account.group_account_user')
        cls.personal = crear_usuario(cls.env, 'equipo_personal', 'hr.group_hr_user')
        cls.tecnico = crear_usuario(cls.env, 'equipo_tecnico', 'base.group_system')
        cls.interno = crear_usuario(cls.env, 'equipo_interno')   # un usuario interno sin ningún rol

    def test_la_vendedora_no_ve_empleados_ni_el_directorio(self):
        visibles = menus_a_la_vista(self.env, self.vendedora)
        self.assertNotIn('hr.menu_hr_root', visibles, '«Empleados» no debe salir como app')
        self.assertNotIn('hr.menu_hr_employee', visibles, 'ni el Directorio')
        self.assertFalse({x for x in visibles if x.startswith('hr.')}, 'ninguna pantalla de Empleados')
        # Lo que sí es de ella sigue ahí.
        self.assertIn('sale.menu_sale_quotations', visibles)

    def test_un_usuario_interno_sin_rol_tampoco(self):
        self.assertNotIn('hr.menu_hr_root', menus_a_la_vista(self.env, self.interno))

    def test_gerencia_administradores_contabilidad_y_personal_lo_siguen_viendo(self):
        admin = self.env.ref('base.user_admin')
        for usuario in (self.gerencia, admin, self.tecnico, self.contador, self.personal):
            visibles = menus_a_la_vista(self.env, usuario)
            self.assertIn('hr.menu_hr_root', visibles, usuario.login)
            self.assertIn('hr.menu_hr_employee', visibles, f'{usuario.login}: el Directorio')

    def test_es_solo_de_menu_los_permisos_de_datos_no_cambian(self):
        """La vendedora sigue leyendo lo público de sus compañeros (nombres en chats y menciones) y sigue sin leer
        fichas completas ni sueldos."""
        publico = self.env['hr.employee.public'].with_user(self.vendedora)
        self.assertTrue(publico.has_access('read'))
        self.assertFalse(self.env['hr.employee'].with_user(self.vendedora).has_access('read'))
        ficha = self.env['hr.employee'].create({'name': 'Ficha del equipo prueba'})
        with self.assertRaises(AccessError):
            ficha.with_user(self.vendedora).read(['wage'])
        self.assertEqual(publico.browse(ficha.id).name, 'Ficha del equipo prueba')

    def test_una_actualizacion_deja_el_mismo_resultado(self):
        """Odoo (o ``-u hr``) lo deja para todo usuario interno: al actualizar este módulo vuelve a quedar restringido,
        las veces que sea."""
        menu = self.env.ref('hr.menu_hr_root')
        for _ in range(2):
            menu.group_ids = [Command.set([self.env.ref(g).id for g in (
                'base.group_user', 'hr.group_hr_user', 'hr.group_hr_manager')])]
            self.assertIn('hr.menu_hr_root', menus_a_la_vista(self.env, self.vendedora))
            convert_file(self.env, 'dcasa_equipo', 'data/menu_empleados_data.xml', {}, mode='update', noupdate=False)
            self.env.registry.clear_cache()
            self.assertNotIn('hr.menu_hr_root', menus_a_la_vista(self.env, self.vendedora))
            self.assertIn('hr.menu_hr_root', menus_a_la_vista(self.env, self.gerencia))
        self.assertNotIn(self.env.ref('base.group_user'), menu.group_ids)
