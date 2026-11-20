# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""Permisos del carrusel de la portada y el valor de los segundos del hero (models/portada.py).

Los segundos de cada foto viven en ``dcasa.portada.ajustes`` (uno por sitio), no en ``website``: la revisión
independiente (2026-11-19) mostró que darle a Gerencia escritura sobre ``website`` le abría, como superusuario, las
acciones de servidor del sitio que Odoo deja sin grupo (por ejemplo «eCommerce: send email to customers about their
abandoned cart»). Gerencia puede cambiar los ajustes del carrusel y su lista, y NADA del sitio mismo.

Cada prueba intenta ROMPER esa frontera: escribir otro campo del sitio por cualquier camino (``write``, mezclado,
contextos, traducciones, ``web_save``), correr acciones de servidor del sitio, valores raros en los segundos (NaN,
infinito, texto, ``None``), y la pantalla de punta a punta en Chrome.
"""
import math

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


def _usuario(env, login, *grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login, 'password': login,
        'group_ids': [Command.set([env.ref('base.group_user').id, *(env.ref(g).id for g in grupos)])],
    })


@tagged('post_install', '-at_install')
class TestGerenciaNoEscribeElSitio(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sitio = cls.env.ref('website.default_website')
        cls.gerente = _usuario(cls.env, 'ppo_gerente', 'dcasa_base.group_gerencia')
        cls.vendedora = _usuario(cls.env, 'ppo_vendedora', 'dcasa_base.group_vendedora')
        cls.interno = _usuario(cls.env, 'ppo_interno')
        cls.portal = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Rvw Portal', 'login': 'ppo_portal', 'password': 'ppo_portal',
            'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        cls.publico = cls.env.ref('base.public_user')

    # ------------------------------------------------------------------ Gerencia no escribe el sitio

    def test_ningun_otro_campo_del_sitio_por_write_ni_mezclado(self):
        """Gerencia ya no escribe NINGÚN campo del sitio: solo o mezclado, o en varios sitios a la vez, falla."""
        otro = self.env['website'].create({'name': 'Sitio de prueba portada'})
        for vals in (
            {'name': 'x'}, {'domain': 'https://x.example'}, {'social_facebook': 'x'}, {'cookies_bar': True},
            {'name': 'x', 'domain': 'x'}, {'homepage_url': '/x', 'social_twitter': 'x'},
            {'company_id': self.env.company.id}, {'user_id': self.gerente.id},
            {'logo': False}, {'favicon': False}, {'shop_ppg': 99}, {'dcasa_whatsapp_number': '123'},
        ):
            for sitios in (self.sitio, self.sitio | otro):
                with self.subTest(vals=sorted(vals), sitios=len(sitios)), self.assertRaises(AccessError), \
                        self.cr.savepoint():
                    sitios.with_user(self.gerente).write(vals)
        self.assertEqual(self.sitio._dcasa_hero_segundos(), 3.0, 'y los segundos siguen como estaban')

    def test_gerencia_no_crea_ni_copia_ni_borra_sitios(self):
        Sitio = self.env['website'].with_user(self.gerente)
        with self.assertRaises(AccessError), self.cr.savepoint():
            Sitio.create({'name': 'Otro'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.sitio.with_user(self.gerente).copy()
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.sitio.with_user(self.gerente).unlink()
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.sitio.with_user(self.gerente).web_save({'name': 'x'}, {'name': {}})

    def test_con_contexto_no_se_salta_la_guarda(self):
        """Ningún contexto de los que miran Odoo o los módulos de D'CASA apaga la guarda."""
        for contexto in ({'active_test': False}, {'tracking_disable': True}, {'no_reset_password': True},
                         {'prefetch_fields': False}, {'bin_size': True}, {'lang': 'en_US'},
                         {'install_mode': True}, {'module': 'website'}, {'website_id': self.sitio.id},
                         {'force_company': self.env.company.id}, {'mail_notrack': True}):
            with self.subTest(contexto=contexto), self.assertRaises(AccessError), self.cr.savepoint():
                self.sitio.with_user(self.gerente).with_context(**contexto).write({'name': 'contexto'})

    def test_traducciones_de_campos_del_sitio_no_son_otra_puerta(self):
        """``update_field_translations`` escribe un campo traducible del sitio (en website_sale,
        ``contact_us_button_url``): Odoo lo cierra con un ``write`` al final, y la guarda lo rechaza. Si un día Odoo
        dejara de pasar por ``write``, esta prueba avisa (el cambio no puede quedar escrito)."""
        traducibles = [c for c in self.sitio._fields.values() if c.translate and c.store and not c.related]
        self.assertTrue(traducibles, 'el sitio tiene campos traducibles (si no, esta prueba no prueba nada)')
        sitio = self.sitio.with_user(self.gerente)
        for campo in traducibles:
            with self.subTest(campo=campo.name):
                antes = {lang: self.sitio.with_context(lang=lang)[campo.name] for lang in ('en_US', 'es_419')}
                with self.assertRaises(AccessError), self.cr.savepoint():
                    sitio.update_field_translations(campo.name, {'en_US': '/rv-web-puerta-trasera',
                                                                 'es_419': '/rv-web-puerta-trasera'})
                self.sitio.invalidate_recordset()
                despues = {lang: self.sitio.with_context(lang=lang)[campo.name] for lang in ('en_US', 'es_419')}
                self.assertEqual(despues, antes, f'«{campo.name}» cambió')

    def test_quien_no_es_gerencia_tampoco_por_traducciones(self):
        for usuario in (self.vendedora, self.interno, self.portal, self.publico):
            sitio = self.sitio.with_user(usuario)
            for campo in [c for c in self.sitio._fields.values() if c.translate and c.store and not c.related]:
                with self.subTest(usuario=usuario.login, campo=campo.name), self.assertRaises(AccessError), \
                        self.cr.savepoint():
                    sitio.update_field_translations(campo.name, {'en_US': '/rv-web'})

    def test_quien_no_es_gerencia_no_llega_a_los_segundos_por_ningun_camino(self):
        ajustes = self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio, crear=True)
        for usuario in (self.vendedora, self.interno, self.portal, self.publico):
            propios = ajustes.with_user(usuario)
            for vals in ({'segundos': 2}, {'diapositiva_ids': []}):
                with self.subTest(usuario=usuario.login, vals=sorted(vals)), self.assertRaises(AccessError), \
                        self.cr.savepoint():
                    propios.write(vals)
            with self.assertRaises(AccessError), self.cr.savepoint():
                propios.web_save({'segundos': 2}, {'segundos': {}})
            with self.assertRaises(AccessError), self.cr.savepoint():
                self.env['dcasa.portada.ajustes'].with_user(usuario).create({'website_id': self.sitio.id, 'segundos': 2})
            with self.assertRaises(AccessError), self.cr.savepoint():
                propios.read(['segundos'])
        self.assertEqual(ajustes.segundos, 3.0)

    def test_el_acl_de_gerencia_sobre_el_sitio_es_solo_leer(self):
        sitio = self.env['website'].with_user(self.gerente)
        self.assertEqual([sitio.has_access(op) for op in ('read', 'write', 'create', 'unlink')],
                         [True, False, False, False], 'Gerencia lee el sitio y no escribe nada en él')
        for usuario in (self.vendedora, self.interno, self.portal, self.publico):
            sitio = self.env['website'].with_user(usuario)
            self.assertEqual([sitio.has_access(op) for op in ('write', 'create', 'unlink')], [False] * 3, usuario.login)
        ajustes = self.env['dcasa.portada.ajustes']
        self.assertEqual([ajustes.with_user(self.gerente).has_access(op) for op in ('read', 'write', 'create', 'unlink')],
                         [True, True, True, False], 'Gerencia cambia los ajustes del carrusel (no los borra)')
        admin = ajustes.with_user(self.env.ref('base.user_admin'))
        self.assertEqual([admin.has_access(op) for op in ('read', 'write', 'create', 'unlink')], [True] * 4)

    def test_el_acl_de_escritura_no_abre_las_acciones_de_servidor_sin_grupo_del_sitio(self):
        """Una acción de servidor SIN grupos la puede correr quien tenga permiso de ESCRIBIR en su modelo
        (``ir.actions.server._can_execute_action_on_records``), y corre como superusuario. Al darle a Gerencia
        escritura sobre ``website`` se le abren las acciones de servidor del sitio que Odoo deja sin grupo, por ejemplo
        «eCommerce: send email to customers about their abandoned cart» (``model._send_abandoned_cart_email()``). Por eso
        Gerencia NO tiene escritura sobre ``website`` (sus segundos viven en ``dcasa.portada.ajustes``): ninguna de esas
        acciones le sale; la vendedora, tampoco."""
        acciones = self.env['ir.actions.server'].sudo().search([
            ('model_id.model', '=', 'website'), ('group_ids', '=', False)])
        self.assertTrue(acciones, 'el sitio trae acciones de servidor sin grupo (si no, esta prueba no prueba nada)')
        contexto = {'active_model': 'website', 'active_id': self.sitio.id, 'active_ids': self.sitio.ids}
        for usuario in (self.vendedora, self.gerente):
            for accion in acciones:
                with self.subTest(usuario=usuario.login, accion=accion.name), self.assertRaises(AccessError), \
                        self.cr.savepoint():
                    accion.with_user(usuario).with_context(**contexto).run()

    def test_la_accion_del_menu_solo_abre_la_pantalla(self):
        """La acción de servidor del menú: la corre Gerencia, devuelve una ventana de los ajustes y no cambia nada del
        sitio; la vendedora no puede correrla ni llamando al servidor a mano."""
        accion = self.env.ref('website_dcasa.action_dcasa_portada_carrusel')
        self.assertEqual(accion.code.strip(), 'action = model.action_abrir()')
        self.assertEqual(accion.model_id.model, 'dcasa.portada.ajustes')
        self.sitio.flush_recordset()
        antes = (self.sitio.write_date, self.sitio.name, self.sitio._dcasa_hero_segundos())
        contexto = {'active_model': 'dcasa.portada.ajustes'}
        resultado = accion.with_user(self.gerente).with_context(**contexto).run()
        ajustes = self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio)
        self.assertEqual(resultado['type'], 'ir.actions.act_window')
        self.assertEqual((resultado['res_model'], resultado['res_id']), ('dcasa.portada.ajustes', ajustes.id))
        self.sitio.invalidate_recordset()
        self.assertEqual((self.sitio.write_date, self.sitio.name, self.sitio._dcasa_hero_segundos()), antes)
        for usuario in (self.vendedora, self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                accion.with_user(usuario).with_context(**contexto).run()

    def test_gerencia_en_varios_sitios_a_la_vez_y_en_otro_sitio(self):
        """Los segundos se pueden cambiar en varios sitios con un solo write (mismos permisos), y cada sitio tiene sus
        propios ajustes y su propia firma de caché: el de otro sitio no pisa al de este."""
        Ajustes = self.env['dcasa.portada.ajustes']
        otro = self.env['website'].create({'name': 'Sitio de prueba del carrusel'})
        este = Ajustes._dcasa_del_sitio(self.sitio, crear=True)
        del_otro = Ajustes._dcasa_del_sitio(otro, crear=True)
        self.assertNotEqual(este, del_otro)
        (este | del_otro).with_user(self.gerente).write({'segundos': 5})
        self.assertEqual((este.segundos, del_otro.segundos), (5.0, 5.0))
        del_otro.with_user(self.gerente).write({'segundos': 9})
        self.assertNotEqual(self.sitio._dcasa_hero_firma(), otro._dcasa_hero_firma())
        self.assertEqual((self.sitio._dcasa_hero_tiempo(), otro._dcasa_hero_tiempo()), ('5s', '9s'))
        # Sin ajustes, un sitio trae los 3 segundos de fábrica.
        sin_ajustes = self.env['website'].create({'name': 'Sitio de prueba sin ajustes'})
        self.assertEqual(sin_ajustes._dcasa_hero_tiempo(), '3s')

    def test_el_disenador_del_sitio_sigue_escribiendo_todo(self):
        disenador = _usuario(self.env, 'ppo_disenador', 'website.group_website_designer')
        self.sitio.with_user(disenador).write({'name': self.sitio.name})

    # ------------------------------------------------------------------ el valor de los segundos

    def _intentar(self, valor):
        """Lo que pasa al escribir ``valor`` como Gerencia: ``('ok', guardado)`` o ``('error', clase)``."""
        ajustes = self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio, crear=True)
        try:
            with self.cr.savepoint():
                ajustes.with_user(self.gerente).write({'segundos': valor})
                ajustes.flush_recordset()
        except (ValidationError, AccessError, ValueError, TypeError, OverflowError) as error:
            return 'error', type(error).__name__
        ajustes.invalidate_recordset()
        return 'ok', ajustes.segundos

    def test_cualquier_valor_que_se_guarda_cae_en_el_rango_y_nunca_rompe_la_plantilla(self):
        """Por el ORM (lo que hace el RPC) entra de todo: texto, NaN, infinito, redondeos del límite. Lo que se acepta
        tiene que estar entre 2 y 15 y salir como «Ns» (nada de «nans», «infs» ni otro texto en el estilo)."""
        valores = [0, 1, 1.9, 1.94, 1.95, 1.99, 2, 2.04, 2.05, 15, 15.01, 15.04, 15.05, 15.1, -2, -0.0, 1e9, 1e400,
                   float('nan'), float('inf'), float('-inf'), '2.5', ' 3 ', '3,5', '1e1', 'abc', '', None, False,
                   True, [3], {'a': 1}, '3; background:red', '3s}</style>']
        aceptados = {}
        for valor in valores:
            veredicto = self._intentar(valor)
            with self.subTest(valor=repr(valor), veredicto=veredicto):
                self.assertNotIn(veredicto[1], ('ValueError', 'TypeError', 'OverflowError'),
                                 f'{valor!r}: por RPC solo se acepta o da un ValidationError claro')
                if veredicto[0] == 'ok':
                    aceptados[repr(valor)] = veredicto[1]
                    self.assertTrue(2.0 <= veredicto[1] <= 15.0, f'se aceptó {valor!r} y quedó {veredicto[1]!r}')
                    self.assertTrue(math.isfinite(veredicto[1]))
                    tiempo = self.sitio._dcasa_hero_tiempo()
                    self.assertRegex(tiempo, r'^\d{1,2}(\.\d)?s$', f'tiempo con {valor!r}')
                else:
                    self.assertEqual(veredicto, ('error', 'ValidationError'), f'{valor!r}: error claro, no un traspié')
        # La frontera: lo que el redondeo a un decimal deja pasar queda dicho (documenta el comportamiento).
        self.assertEqual(aceptados.get('1.99'), 2.0, 'el redondeo a un decimal deja pasar 1.99 como 2')
        self.assertEqual(aceptados.get('15.01'), 15.0, 'y 15.01 como 15')

    def test_el_estilo_de_la_portada_no_puede_llevar_nada_distinto_de_un_numero(self):
        """Aunque la base trajera basura (SQL a mano), la plantilla escribe solo «--vitrina-tiempo: Ns;»: lo que no
        sirve (fuera de rango, NaN, infinito) se vuelve los 3 segundos de fábrica."""
        ajustes = self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio, crear=True)
        for suelto in (0.0, 0.2, 1.0, 2.0, 2.5, 7.0, 15.0, 15.4, 99.0, 1e6, 123456789.0):
            self.cr.execute('UPDATE dcasa_portada_ajustes SET segundos = %s WHERE id = %s', (suelto, ajustes.id))
            ajustes.invalidate_recordset()
            with self.subTest(suelto=suelto):
                tiempo = self.sitio._dcasa_hero_tiempo()
                self.assertRegex(tiempo, r'^\d{1,2}(\.\d)?s$')
                self.assertTrue(2 <= float(tiempo[:-1]) <= 15)
                if not 2 <= suelto <= 15:
                    self.assertEqual(tiempo, '3s', 'fuera de rango: los 3 segundos de fábrica')
        # NaN y el infinito solo caben por SQL: la plantilla igual tiene que dar un número.
        for texto in ("'NaN'::numeric", "'Infinity'::float8", "'-Infinity'::float8"):
            try:
                with self.cr.savepoint():
                    self.cr.execute(f'UPDATE dcasa_portada_ajustes SET segundos = {texto} WHERE id = %s', (ajustes.id,))
            except Exception:  # noqa: BLE001 — la columna no admite ese valor: nada que probar
                continue
            ajustes.invalidate_recordset()
            with self.subTest(texto=texto):
                self.assertEqual(self.sitio._dcasa_hero_tiempo(), '3s', 'NaN o infinito en la base no llegan al CSS')

    def test_cambiar_los_segundos_marca_todo_para_regenerar_el_borde(self):
        """El borde se entera: escribir los segundos deja la marca «regenerar todo» (0), también si la deja Gerencia."""
        Pendiente = self.env['dcasa.tienda.pendiente']
        Pendiente.search([]).unlink()
        self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio, crear=True).with_user(self.gerente).write(
            {'segundos': 6})
        self.env.flush_all()
        self.env.cr.flush()
        self.assertIn(0, Pendiente.sudo().search([]).mapped('producto_id'))


@tagged('post_install', '-at_install')
class TestTraduccionesNoLlegaAlVisitante(HttpCase):
    """Si Gerencia logra cambiar un campo traducible del sitio por ``update_field_translations``, ¿llega a la página
    pública? (``contact_us_button_url`` sale como ``href`` del botón «Contact Us» de la ficha de producto)."""

    def test_el_url_del_boton_de_contacto_no_lo_cambia_gerencia(self):
        sitio = self.env.ref('website.default_website')
        gerente = _usuario(self.env, 'ppo_gerente_http', 'dcasa_base.group_gerencia')
        producto = self.env['product.template'].create({
            'name': 'ZZRVW PRODUCTO', 'is_published': True, 'sale_ok': True, 'list_price': 10.0})
        malo = 'javascript:alert(document.domain)'
        with self.assertRaises(AccessError), self.cr.savepoint():
            sitio.with_user(gerente).update_field_translations(
                'contact_us_button_url', {'en_US': malo, 'es_419': malo})
        sitio.invalidate_recordset()
        self.cr.flush()
        pagina = self.url_open(producto.website_url).text
        self.assertNotIn(malo, pagina, 'Gerencia puso un javascript: en el botón «Contact Us» de la ficha pública')


@tagged('post_install', '-at_install')
class TestPantallaDelCarruselEnChrome(HttpCase):
    """De punta a punta: Gerencia abre «Carrusel de la portada» por su acción de servidor, cambia los segundos y guarda
    (``web_save`` de verdad, con la guarda de ``Website.write``); la vendedora no puede abrirla."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sitio = cls.env.ref('website.default_website')
        cls.gerente = _usuario(cls.env, 'ppo_gerente_nav', 'dcasa_base.group_gerencia')
        cls.vendedora = _usuario(cls.env, 'ppo_vendedora_nav', 'dcasa_base.group_vendedora')

    def test_gerencia_guarda_los_segundos_desde_su_pantalla(self):
        self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio, crear=True).segundos = 3
        codigo = r"""(async () => {
            const esperar = async (fn, que, intentos = 150) => {
                for (let i = 0; i < intentos; i++) { const r = fn(); if (r) { return r; }
                    await new Promise((ok) => setTimeout(ok, 100)); }
                throw new Error('No apareció: ' + que);
            };
            const campo = await esperar(() => document.querySelector('.o_dcasa_hero_segundos input'), 'el campo de los segundos');
            if (campo.value !== '3.0' && campo.value !== '3') { throw new Error('de fábrica 3: ' + campo.value); }
            campo.value = '4.5';
            campo.dispatchEvent(new Event('input', { bubbles: true }));
            campo.dispatchEvent(new Event('change', { bubbles: true }));
            const guardar = await esperar(() => document.querySelector('.o_form_button_save'), 'el botón de guardar');
            guardar.click();
            await new Promise((ok) => setTimeout(ok, 2000));   // el botón de guardar no siempre desaparece: se mira el valor
            const campoDespues = document.querySelector('.o_dcasa_hero_segundos input');
            if (!['4.5', '4.50'].includes(campoDespues.value)) { throw new Error('quedó en ' + campoDespues.value); }
            // La pantalla es solo esto: ni nombre, ni dominio, ni nada más del sitio.
            const etiquetas = [...document.querySelectorAll('.o_form_view .o_field_widget')].map((f) => f.getAttribute('name'));
            if (etiquetas.some((n) => !['segundos', 'diapositiva_ids'].includes(n))) {
                throw new Error('la pantalla trae otros campos del sitio: ' + etiquetas.join(','));
            }
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/action-website_dcasa.action_dcasa_portada_carrusel', codigo, login='ppo_gerente_nav',
                        timeout=120)
        self.assertEqual(self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self.sitio).segundos, 4.5)

    def test_la_vendedora_no_abre_la_pantalla(self):
        accion = self.env.ref('website_dcasa.action_dcasa_portada_carrusel')
        with self.assertRaises(AccessError):
            accion.with_user(self.vendedora).with_context(active_model='website', active_id=self.sitio.id).run()
        with self.assertRaises(AccessError):
            self.env['dcasa.portada.ajustes'].with_user(self.vendedora).action_abrir()
