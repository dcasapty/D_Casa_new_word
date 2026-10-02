"""El sitio se edita por código (models/sitio.py; docs/auditoria/ronda7/constructor-web.md)."""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

GRUPOS_EDITOR = ('website.group_website_designer', 'website.group_website_restricted_editor')


def crear_usuario(env, login, grupo):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login,
        'group_ids': [Command.set([env.ref('base.group_user').id, env.ref(grupo).id])],
    })


@tagged('post_install', '-at_install')
class TestSitioPorCodigo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.sitio = cls.env.ref('website.default_website')
        cls.gerencia = crear_usuario(cls.env, 'gerencia_sitio', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(cls.env, 'vendedora_sitio', 'dcasa_base.group_vendedora')

    def _grupos(self):
        return self.env['dcasa.sitio']._grupos_de_editor()

    def _menus(self, usuario):
        menus = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
        return {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}

    # --- Grupos -------------------------------------------------------------------------------

    def test_nadie_queda_con_grupos_de_editor(self):
        grupos = self._grupos()
        internos = self.env['res.users'].with_context(active_test=False).search([('share', '=', False)])
        con_grupo = internos.filtered(lambda u: u.all_group_ids & grupos)
        self.assertFalse(con_grupo, con_grupo.mapped('login'))
        # Ni Ajustes (Odoo se lo cuelga a base.group_system) ni los roles de la tienda los implican.
        for xmlid in ('base.group_system', 'dcasa_base.group_gerencia', 'dcasa_base.group_vendedora'):
            self.assertFalse(self.env.ref(xmlid).all_implied_ids & grupos, xmlid)
        for xmlid in GRUPOS_EDITOR:
            self.assertFalse(self.admin.has_group(xmlid), xmlid)
            self.assertFalse(self.gerencia.has_group(xmlid), xmlid)
        # Lo de Odoo entre sus propios grupos no se toca: diseñador sigue implicando editor.
        self.assertIn(self.env.ref('website.group_website_restricted_editor'),
                      self.env.ref('website.group_website_designer').implied_ids)

    def test_la_actualizacion_los_vuelve_a_retirar(self):
        """Lo que hacen website (admin diseñador; Ajustes implica diseñador) y website_dcasa (Gerencia)."""
        disenador = self.env.ref('website.group_website_designer')
        self.admin.write({'group_ids': [Command.link(disenador.id)]})
        self.env.ref('base.group_system').write({'implied_ids': [Command.link(disenador.id)]})
        self.env.ref('dcasa_base.group_gerencia').write({'implied_ids': [Command.link(disenador.id)]})
        self.assertIn(disenador, self.admin.all_group_ids)
        self.assertIn(disenador, self.gerencia.all_group_ids)

        self.assertTrue(self.env['dcasa.sitio']._sitio_por_codigo())
        for usuario in (self.admin, self.gerencia):
            self.assertFalse(usuario.all_group_ids & self._grupos(), usuario.login)
        # Idempotente: la segunda vez no hay nada que hacer.
        self.assertFalse(self.env['dcasa.sitio']._sitio_por_codigo())

    # --- Menús --------------------------------------------------------------------------------

    def test_sitio_web_para_gerencia_sin_constructor(self):
        de_gerencia = self._menus(self.gerencia)
        for xmlid in ('website.menu_website_configuration', 'dcasa_interfaz.menu_dcasa_vista_previa',
                      'website.menu_website_pages_list', 'website_sale.menu_product_pages',
                      'website_sale.menu_catalog_products', 'website_sale.menu_orders_orders',
                      'website_sale.menu_report_sales'):
            self.assertIn(xmlid, de_gerencia, xmlid)
        for xmlid in ('website.menu_website_preview', 'website.menu_edit_menu', 'website.menu_current_page',
                      'website.menu_page_properties', 'website.menu_optimize_seo', 'website.menu_ace_editor',
                      'website.custom_menu_edit_menu', 'website.menu_website_technical_pages',
                      'website.menu_website_analytics', 'website.website_visitor_menu',
                      'website.menu_visitor_view_menu'):
            self.assertNotIn(xmlid, de_gerencia, xmlid)
        self.assertNotIn('website.menu_website_configuration', self._menus(self.vendedora))

    # --- Guarda: ninguna copia por sitio ni edición desde el panel -----------------------------

    def _copias(self, clave):
        return self.env['ir.ui.view'].with_context(active_test=False).search_count(
            [('key', '=', clave), ('website_id', '!=', False)])

    def test_guarda_bloquea_la_copia_por_sitio_de_website_dcasa(self):
        vista = self.env.ref('website_dcasa.tarjeta_producto')
        antes = self._copias(vista.key)
        # Lo que hace el constructor al guardar: write con website_id en el contexto (COW).
        with self.assertRaisesRegex(UserError, 'se mantiene desde el código'):
            vista.with_user(self.admin).with_context(website_id=self.sitio.id).write({'arch': vista.arch})
        self.assertEqual(self._copias(vista.key), antes)
        # Ni la copia a mano, ni editar la vista genérica desde Ajustes técnicos.
        with self.assertRaises(UserError):
            self.env['ir.ui.view'].with_user(self.admin).create({
                'name': 'Copia', 'type': 'qweb', 'key': vista.key, 'website_id': self.sitio.id,
                'arch': '<t t-name="website_dcasa.tarjeta_producto"><div/></t>'})
        with self.assertRaises(UserError):
            vista.with_user(self.admin).write({'priority': 99})
        with self.assertRaises(UserError):
            vista.with_user(self.admin).unlink()
        # Una copia que ya exista (Odoo las crea al instalar bajo una vista ya copiada) tampoco se edita.
        copia = self.env['ir.ui.view'].sudo().create({
            'name': 'Copia previa', 'type': 'qweb', 'key': 'website_dcasa.prueba_guarda', 'website_id': self.sitio.id,
            'arch': '<t t-name="website_dcasa.prueba_guarda"><div>uno</div></t>'})
        with self.assertRaises(UserError):
            copia.with_user(self.admin).write({'arch': '<t t-name="website_dcasa.prueba_guarda"><div>dos</div></t>'})
        with self.assertRaises(UserError):
            copia.with_user(self.admin).unlink()
        # La portada de Odoo la llena website_dcasa por herencia: también se protege.
        portada = self.env.ref('website.homepage')
        with self.assertRaisesRegex(UserError, 'se mantiene desde el código'):
            portada.with_user(self.admin).with_context(website_id=self.sitio.id).write({'arch': portada.arch})

    def test_guarda_deja_pasar_lo_de_odoo(self):
        # Opciones de la tienda: website_sale crea copias por sitio de SUS vistas; se permiten.
        terminos = self.env.ref('website_sale.product_terms_and_conditions')
        terminos.with_user(self.admin).with_context(website_id=self.sitio.id).write({'active': True})
        self.assertEqual(self._copias(terminos.key), 1)
        # Lo que hace Odoo por dentro (sudo, instalación) y el escape documentado, sobre vistas nuestras.
        vista = self.env.ref('website_dcasa.tarjeta_producto')
        vista.sudo().write({'name': vista.name})
        vista.with_user(self.admin).with_context(install_mode=True).write({'name': vista.name})
        self.env['ir.config_parameter'].sudo().set_param('dcasa_interfaz.sitio_editable', '1')
        vista.with_user(self.admin).write({'name': vista.name})
        self.env['ir.config_parameter'].sudo().set_param('dcasa_interfaz.sitio_editable', '0')
        with self.assertRaises(UserError):
            vista.with_user(self.admin).write({'name': vista.name})

    def test_pagina_de_la_portada_solo_se_publica_y_su_seo(self):
        portada = self.env['website.page'].search([('url', '=', '/')], limit=1)
        self.assertTrue(portada)
        como_gerencia = portada.with_user(self.gerencia)
        self.assertTrue(como_gerencia.can_publish)
        como_gerencia.write({'is_published': True})
        como_gerencia.write({'website_indexed': False})
        with self.assertRaisesRegex(UserError, 'se mantiene desde el código'):
            como_gerencia.write({'name': 'Otra portada'})
        # El SEO de la página vive en su vista (ir.ui.view): solo administradores lo escriben, y la
        # guarda lo deja pasar porque no toca la plantilla.
        with self.assertRaises(AccessError):
            como_gerencia.write({'website_meta_description': 'Muebles en La Chorrera.'})
        portada.with_user(self.admin).write({'website_meta_description': 'Muebles en La Chorrera.'})
        self.assertEqual(portada.view_id.website_meta_description, 'Muebles en La Chorrera.')
        with self.assertRaises(UserError):
            portada.with_user(self.admin).write({'url': '/otra'})
        with self.assertRaises(UserError):
            portada.with_user(self.admin).write({'arch': portada.arch})
        # Gerencia no crea ni borra páginas (ACL): las páginas nacen en el código.
        self.assertFalse(self.env['website.page'].with_user(self.gerencia).has_access('create'))
        self.assertFalse(self.env['website.page'].with_user(self.gerencia).has_access('unlink'))
        self.assertFalse(self.env['website.page'].with_user(self.vendedora).has_access('read'))

    # --- Vista previa móvil ---------------------------------------------------------------------

    def test_vista_previa_apunta_al_sitio_canonico(self):
        accion = self.env.ref('dcasa_interfaz.action_dcasa_vista_previa')
        self.assertEqual(accion.tag, 'dcasa_vista_previa')
        menu = self.env.ref('dcasa_interfaz.menu_dcasa_vista_previa')
        self.assertEqual(menu.parent_id, self.env.ref('website.menu_website_configuration'))
        self.assertEqual(menu.action, accion)

        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://dcasapty.com')
        self.sitio.domain = False
        datos = self.env['dcasa.sitio'].with_user(self.gerencia).vista_previa()
        self.assertEqual(datos['url'], 'https://dcasapty.com')
        self.assertEqual(datos['nombre'], self.sitio.name)
        self.assertEqual(datos['paginas'][0], {'nombre': 'Inicio', 'ruta': '/'})
        self.assertIn('/shop', [p['ruta'] for p in datos['paginas']])
        # Si el sitio tiene dominio propio, manda el dominio (con la barra final fuera).
        self.sitio.domain = 'https://staging.dcasapty.com/'
        self.assertEqual(self.env['dcasa.sitio'].with_user(self.vendedora).vista_previa()['url'],
                         'https://staging.dcasapty.com')
        # La fila de «Páginas» abre esta misma pantalla en la página elegida, no la vista previa de Odoo
        # (que precarga el constructor).
        portada = self.env['website.page'].search([('url', '=', '/')], limit=1)
        apertura = portada.with_user(self.gerencia).open_website_url()
        self.assertEqual((apertura['type'], apertura['tag']), ('ir.actions.client', 'dcasa_vista_previa'))
        self.assertEqual(apertura['params'], {'ruta': '/'})
        # Sin modo edición: la pantalla no manda enable_editor ni usa el constructor.
        with open(file_path('dcasa_interfaz/static/src/js/vista_previa.js'), encoding='utf-8') as archivo:
            codigo = archivo.read()
        self.assertNotIn('enable_editor', codigo)
        self.assertNotIn('website_builder', codigo)
