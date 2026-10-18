"""Quién ve y cambia el catálogo para Meta: Gerencia y administradores sí; la Vendedora no."""
import json

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

from .common import MetaComun

MENUS = ('dcasa_meta_catalogo.menu_meta_raiz', 'dcasa_meta_catalogo.menu_meta_catalogo',
         'dcasa_meta_catalogo.menu_meta_campanas')


@tagged('post_install', '-at_install')
class TestPermisosMeta(MetaComun, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupo):
            return Usuarios.create({'name': login.title(), 'login': login, 'group_ids': [
                (6, 0, [cls.env.ref('base.group_user').id, cls.env.ref(grupo).id])]})

        cls.vendedora = usuario('vendedora_meta', 'dcasa_base.group_vendedora')
        cls.gerencia = usuario('gerencia_meta', 'dcasa_base.group_gerencia')
        cls.mesa = cls._producto('Mesa permisos prueba Meta', 75.0)
        cls.campana = cls.env['dcasa.meta.campana'].create({'name': 'Permisos'})

    def _menus(self, usuario):
        visibles = self.env['ir.ui.menu'].with_user(usuario)._visible_menu_ids()
        return {xmlid for xmlid in MENUS if self.env.ref(xmlid).id in visibles}

    def test_menus(self):
        self.assertEqual(self._menus(self.gerencia), set(MENUS))
        self.assertEqual(self._menus(self.vendedora), set())

    def test_la_vendedora_no_cambia_el_catalogo_ni_las_campanas(self):
        feed = self.feed.with_user(self.vendedora)
        with self.assertRaises(AccessError):
            feed.write({'dcasa_activo': False})
        with self.assertRaises(AccessError):
            feed.read(['url'])
        with self.assertRaises(AccessError):
            feed.action_dcasa_meta_nueva_direccion()
        with self.assertRaises(AccessError):
            feed.action_dcasa_meta_ver_fuera()
        Campana = self.env['dcasa.meta.campana'].with_user(self.vendedora)
        with self.assertRaises(AccessError):
            Campana.create({'name': 'De la vendedora'})
        with self.assertRaises(AccessError):
            self.campana.with_user(self.vendedora).write({'name': 'Otra'})
        with self.assertRaises(AccessError):
            self.campana.with_user(self.vendedora).unlink()

    def test_la_vendedora_no_marca_productos_para_meta(self):
        mesa = self.mesa.with_user(self.vendedora)
        with self.assertRaises(AccessError):
            mesa.write({'dcasa_meta_campana_id': self.campana.id})
        with self.assertRaises(AccessError):
            mesa.write({'dcasa_meta_no_anunciar': True})
        with self.assertRaises(AccessError):
            mesa.read(['dcasa_meta_no_anunciar'])
        # Su ficha y su lista de productos se abren sin esos campos.
        for tipo in ('form', 'list', 'search'):
            vistas = self.env['product.template'].with_user(self.vendedora).get_views([(False, tipo)])
            arch = vistas['views'][tipo]['arch']
            self.assertNotIn('dcasa_meta_', arch, tipo)

    def test_gerencia_si(self):
        feed = self.feed.with_user(self.gerencia)
        feed.write({'dcasa_marca': "D'CASA Panamá", 'dcasa_activo': False})
        self.assertFalse(self.feed.dcasa_activo)
        self.assertTrue(feed.url)
        feed.action_dcasa_meta_nueva_direccion()
        self.assertEqual(feed.action_dcasa_meta_ver_fuera()['res_model'], 'product.template')
        campana = self.env['dcasa.meta.campana'].with_user(self.gerencia).create({'name': 'De Gerencia'})
        self.mesa.with_user(self.gerencia).write({'dcasa_meta_campana_id': campana.id, 'dcasa_meta_no_anunciar': True})
        campana.unlink()
        # Gerencia no crea ni borra catálogos (eso es del administrador).
        with self.assertRaises(AccessError):
            self.env['product.feed'].with_user(self.gerencia).create({
                'name': 'Otro', 'target': 'meta', 'website_id': self.website.id})
        with self.assertRaises(AccessError):
            feed.unlink()
        vistas = self.env['product.template'].with_user(self.gerencia).get_views([(False, 'form')])
        form = vistas['views']['form']['arch']
        self.assertIn('name="dcasa_meta_campana_id"', form)
        self.assertIn('name="dcasa_meta_no_anunciar"', form)

    def test_la_guia_lleva_a_las_pantallas_nuevas(self):
        with file_open('dcasa_guia/data/guia.json') as archivo:
            tareas = {t['id']: t for t in json.load(archivo)['tareas']}
        self.assertEqual(tareas['meta-catalogo']['destino'], {'menu': 'dcasa_meta_catalogo.menu_meta_catalogo'})
        self.assertEqual(tareas['meta-campana']['destino'], {'menu': 'dcasa_meta_catalogo.menu_meta_campanas'})
        self.assertEqual(tareas['meta-eventos']['destino'], {'menu': 'dcasa_meta_eventos.menu_meta_eventos'})
        for clave in ('meta-catalogo', 'meta-campana'):
            menu = self.env.ref(tareas[clave]['destino']['menu'])
            self.assertTrue(menu.action, clave)
