import json
import re

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.misc import file_path


@tagged('post_install', '-at_install')
class TestTablero(TransactionCase):

    def test_datos_del_tablero(self):
        datos = self.env['dcasa.tablero'].obtener_datos()
        claves = {c['clave'] for c in datos['cifras']}
        self.assertTrue({'ventas_hoy', 'cotizaciones', 'web', 'por_cobrar', 'entregas', 'socios'}
                        <= claves)
        self.assertNotIn('cobrado_hoy', claves, '«Cobrado hoy» salió: Caja de hoy ya lo dice (2026-10-16)')
        self.assertEqual(len(datos['semana']), 7)
        self.assertTrue(datos['semana'][-1]['hoy'])
        for cifra in datos['cifras']:
            self.assertIn('res_model', cifra['accion'])
        web = next(c for c in datos['cifras'] if c['clave'] == 'web')
        self.assertEqual(web['titulo'], 'Compraron en la web y aún no se entregan', 'decisión 10 de la dueña')

    def test_venta_de_hoy_suma_en_el_tablero(self):
        """Una venta suma en «Vendido hoy» cuando está facturada por completo, no antes."""
        def vendido():
            return next(c['valor'] for c in self.env['dcasa.tablero'].obtener_datos()['cifras']
                        if c['clave'] == 'ventas_hoy')
        antes = vendido()
        producto = self.env['product.product'].create({'name': 'Mesa tablero', 'list_price': 100})
        orden = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Cliente tablero'}).id,
            'order_line': [(0, 0, {'product_id': producto.id})],
        })
        self.assertAlmostEqual(vendido(), antes, places=2)   # cotización: no es una venta
        orden.action_confirm()
        self.assertAlmostEqual(vendido(), antes, places=2)   # confirmada pero por facturar: tampoco
        factura = orden._create_invoices()
        self.assertAlmostEqual(vendido(), antes, places=2)   # factura en borrador: tampoco
        factura.action_post()
        self.assertAlmostEqual(vendido() - antes, orden.amount_untaxed, places=2)

    def test_vendedora_sin_contabilidad_ve_su_tablero(self):
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora', 'login': 'vendedora_tablero',
            'group_ids': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id])],
        })
        datos = self.env['dcasa.tablero'].with_user(vendedora).obtener_datos()
        self.assertTrue(datos['cifras'])
        # UI-02: sin Facturación no cobra; el Inicio no le ofrece «Registrar cobro» ni cifras de cobros.
        self.assertFalse(datos['permisos']['cobrar'])
        self.assertFalse(datos['permisos']['ver_cobros'])
        self.assertTrue(datos['permisos']['cotizar'])
        claves = {c['clave'] for c in datos['cifras']}
        self.assertNotIn('cobrado_hoy', claves)
        self.assertNotIn('por_cobrar', claves)
        self.assertFalse(datos['cobros'])

    def test_rol_vendedora_no_ve_cobros_en_el_inicio_y_gerencia_si(self):
        """2026-10-14: la vendedora no ve lo cobrado ni lo por cobrar (ni «Registrar cobro» en el Inicio): se cobra
        desde la factura. Gerencia conserva todo."""
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora con rol', 'login': 'vendedora_rol_tablero',
            'group_ids': [(6, 0, [self.env.ref('dcasa_base.group_vendedora').id])],
        })
        datos = self.env['dcasa.tablero'].with_user(vendedora).obtener_datos()
        self.assertFalse(datos['permisos']['cobrar'])
        self.assertFalse(datos['permisos']['ver_cobros'])
        self.assertFalse(datos['permisos']['completo'])
        self.assertTrue(datos['permisos']['facturar'] and datos['permisos']['crear_cliente'])
        self.assertTrue({'cobrado_hoy', 'por_cobrar'}.isdisjoint({c['clave'] for c in datos['cifras']}))
        gerencia = self.env['res.users'].create({
            'name': 'Gerencia con rol', 'login': 'gerencia_rol_tablero',
            'group_ids': [(6, 0, [self.env.ref('dcasa_base.group_gerencia').id])],
        })
        datos = self.env['dcasa.tablero'].with_user(gerencia).obtener_datos()
        self.assertTrue(all(datos['permisos'].values()), datos['permisos'])
        self.assertIn('por_cobrar', {c['clave'] for c in datos['cifras']})
        self.assertIn('total_cobrado', datos)

    def test_inicio_condiciona_accesos_y_caja(self):
        """La plantilla solo dibuja «Registrar cobro» y «Caja de hoy» con permiso."""
        with open(file_path('dcasa_interfaz/static/src/xml/inicio.xml'), encoding='utf-8') as plantilla:
            xml = plantilla.read()
        self.assertRegex(xml, r't-if="d\.permisos\.cobrar"[^\n]*\n[^\n]*this\.nuevo\(\'account\.payment\'')
        self.assertIn('t-if="d.permisos.ver_cobros" class="o_dcasa_panel o_dcasa_caja"', xml)

    def test_atajo_a_productos_para_quien_vende(self):
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora atajos', 'login': 'vendedora_atajos',
            'group_ids': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id])]})
        atajos = {a['clave']: a for a in self.env['dcasa.tablero'].with_user(vendedora).obtener_datos()['atajos']}
        self.assertEqual(atajos['productos']['accion'], 'sale.product_template_action')
        self.assertEqual(atajos['productos']['vista'], 'list', 'los productos abren en lista, no en tarjetas')
        self.assertNotIn('stock_precios', atajos, 'el stock se ve y se ordena en Productos: una sola pantalla')
        for atajo in atajos.values():
            self.assertTrue(atajo['titulo'] and atajo['detalle'] and atajo['icono'].startswith('fa-'))
            self.assertTrue(self.env.ref(atajo['accion'], raise_if_not_found=False), atajo['accion'])

    def test_sin_permiso_de_productos_no_hay_atajos_de_catalogo(self):
        interno = self.env['res.users'].create({
            'name': 'Interno sin ventas', 'login': 'interno_atajos',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        datos = self.env['dcasa.tablero'].with_user(interno).obtener_datos()
        claves = {a['clave'] for a in datos['atajos']}
        if not datos['permisos']['catalogo']:
            self.assertNotIn('productos', claves)

    def test_el_inicio_dibuja_los_atajos_y_ya_no_el_boton_catalogo(self):
        with open(file_path('dcasa_interfaz/static/src/xml/inicio.xml'), encoding='utf-8') as plantilla:
            xml = plantilla.read()
        self.assertIn('t-foreach="d.atajos"', xml)
        self.assertIn('this.abrirAtajo(a)', xml)
        self.assertNotIn('t-on-click="catalogo"', xml)

    def test_inicio_sin_recorrido_ni_odoobot(self):
        admin = self.env.ref('base.user_admin')
        self.assertEqual(admin.action_id.id, self.env.ref('dcasa_interfaz.action_dcasa_inicio').id)
        self.assertFalse(admin.tour_enabled)
        self.assertEqual(admin.odoobot_state, 'disabled')
        nuevo = self.env['res.users'].create({'name': 'Nueva', 'login': 'nueva_tablero'})
        self.assertFalse(nuevo.tour_enabled)

    def test_apps_con_iconos_propios(self):
        for xmlid in ('sale.sale_menu_root', 'stock.menu_stock_root', 'dcasa_interfaz.menu_dcasa_inicio'):
            menu = self.env.ref(xmlid)
            self.assertTrue(menu.web_icon.startswith('dcasa_interfaz,'), xmlid)
            self.assertTrue(menu.web_icon_data, xmlid)

    def test_catalogo_de_apps_sin_modulos_de_pago(self):
        self.assertIn('to_buy', self.env.ref('base.open_module_tree').domain)


@tagged('post_install', '-at_install')
class TestInterfazWeb(HttpCase):

    def test_login_sin_odoo(self):
        html = self.url_open('/web/login').text
        self.assertNotIn('Powered by', html)
        self.assertIn("D'CASA", html.replace('&#39;', "'"))

    def test_bundle_backend_con_la_marca(self):
        self.authenticate('admin', 'admin')
        html = self.url_open('/odoo').text
        css = re.findall(r'href="([^"]*web\.assets_web[^"]*\.css)"', html)
        self.assertTrue(css, 'El backend enlaza su CSS')
        contenido = self.url_open(css[0]).text
        self.assertIn('o_dcasa_inicio', contenido)
        self.assertIn('o_dcasa_en_desarrollo', contenido)
        # Barra lateral y sistema de diseño (escala de azules, blancos fríos).
        self.assertIn('o_dcasa_barra_marca', contenido)
        self.assertIn('--dc-azul-600', contenido)
        self.assertIn('o_dcasa_grafico_barra', contenido)
        js = re.findall(r'src="([^"]*web\.assets_web[^"]*\.js)"', html)
        self.assertTrue(js, 'El backend enlaza su JavaScript')
        codigo = self.url_open(js[0]).text
        self.assertIn('DcasaBarraLateral', codigo)
        self.assertIn('DcasaVistaPrevia', codigo)
        self.assertIn('o_dcasa_ayuda', codigo)  # las ayudas propias de las listas vacías sí se muestran
        self.assertIn('o_dcasa_vp_marco', contenido)
        self.assertNotIn('css error', contenido.lower())

    def test_barra_lateral_tercer_nivel(self):
        """Facturación › Contabilidad › Transacciones › Asientos: los grupos se despliegan a cualquier nivel."""
        admin = self.env.ref('base.user_admin')
        admin.group_ids = [(4, self.env.ref('account.group_account_manager').id)]
        codigo = """(async () => {
            const esperar = async (fn, que) => {
                for (let i = 0; i < 100; i++) {
                    const r = fn();
                    if (r) { return r; }
                    await new Promise((ok) => setTimeout(ok, 100));
                }
                throw new Error('No apareció: ' + que);
            };
            // Por defecto la barra es automática: franja de íconos que no empuja el contenido.
            await esperar(() => document.body.classList.contains('o_dcasa_barra_colapsada'), 'el modo automático');
            await esperar(() => document.querySelector('nav.o_dcasa_barra.o_dcasa_barra_colapsada'), 'la franja');
            // Fijarla abierta.
            document.querySelector('.o_dcasa_barra_colapsar').click();
            await esperar(() => !document.body.classList.contains('o_dcasa_barra_colapsada'), 'la barra fija');
            (await esperar(() => [...document.querySelectorAll('.o_dcasa_barra_app')]
                .find((a) => a.textContent.trim() === __APP__), 'la app')).click();
            await esperar(() => document.querySelector('.o_dcasa_barra_secciones'), 'las secciones');
            // Acordeón: abrir un grupo recoge a sus hermanos.
            const grupos = [...document.querySelectorAll('.o_dcasa_barra_secciones > li > .o_dcasa_barra_grupo_btn')];
            grupos[0].click();
            await esperar(() => grupos[0].getAttribute('aria-expanded') === 'true', 'el primer grupo');
            grupos[1].click();
            await esperar(() => grupos[1].getAttribute('aria-expanded') === 'true'
                && grupos[0].getAttribute('aria-expanded') === 'false', 'el acordeón');
            // Buscar un grupo con tercer nivel.
            let anidado = null;
            for (const g of grupos) {
                if (g.getAttribute('aria-expanded') !== 'true') { g.click(); }
                anidado = await esperar(() => g.closest('li').querySelector('.o_dcasa_barra_hijos')
                    && (g.closest('li').querySelector('.o_dcasa_barra_hijos .o_dcasa_barra_grupo_btn') || 'no'),
                    'los hijos');
                if (anidado !== 'no') { break; }
            }
            if (anidado === 'no') { throw new Error('No apareció: un grupo de tercer nivel'); }
            anidado.click();
            const enlace = await esperar(
                () => document.querySelector('.o_dcasa_barra_hijos .o_dcasa_barra_hijos a'), 'el tercer nivel');
            enlace.click();
            await esperar(() => document.querySelector('.o_dcasa_barra_hijos .o_dcasa_barra_hijos a.o_activa'),
                          'el enlace activo');
            // Ninguna sección queda como enlace muerto (sin acción ni subsecciones).
            const muertos = [...document.querySelectorAll('a.o_dcasa_barra_seccion')]
                .filter((a) => a.getAttribute('href') === '/odoo').map((a) => a.textContent.trim());
            if (muertos.length) { throw new Error('Secciones sin destino: ' + muertos.join(', ')); }
            console.log('test successful');
        })();""".replace('__APP__', json.dumps(self.env.ref('account.menu_finance').with_context(lang=admin.lang).name))
        self.browser_js('/odoo', codigo, login='admin')

    def test_filtros_rapidos_en_productos(self):
        """Productos: botones de filtro de un clic y categorías a la izquierda."""
        codigo = """(async () => {
            const esperar = async (fn, que) => {
                for (let i = 0; i < 100; i++) {
                    const r = fn();
                    if (r) { return r; }
                    await new Promise((ok) => setTimeout(ok, 100));
                }
                throw new Error('No apareció: ' + que);
            };
            await esperar(() => document.querySelector('.o_search_panel'), 'el panel de categorías');
            const chip = await esperar(() => [...document.querySelectorAll('.o_dcasa_chip')]
                .find((b) => b.textContent.trim() === 'Disponibles'), 'el filtro Disponibles');
            chip.click();
            const activo = () => [...document.querySelectorAll('.o_dcasa_chip.o_activo')]
                .some((b) => b.textContent.includes('Disponibles'));
            await esperar(activo, 'el filtro activo');
            await esperar(() => document.querySelector('.o_searchview_facet'), 'la faceta en el buscador');
            (await esperar(() => document.querySelector('.o_dcasa_chip_limpiar'), 'quitar filtros')).click();
            await esperar(() => !document.querySelector('.o_dcasa_chip.o_activo'), 'sin filtros');
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/action-sale.product_template_action', codigo, login='admin')


@tagged('post_install', '-at_install')
class TestOrdenarProductosEnElNavegador(HttpCase):
    """Marketing en Productos: filtrar por categoría y disponibilidad y ordenar por stock y precio, con botones."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        categoria = cls.env['product.category'].create({'name': 'Zzordenes'})
        cls.ubicacion = cls.env['stock.warehouse'].search([], limit=1).lot_stock_id
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'categ_id': categoria.id}
        # nombre, precio, stock
        for nombre, precio, stock in (('Zzorden A', 300.0, 50), ('Zzorden B', 900.0, 20), ('Zzorden C', 100.0, 5),
                                      ('Zzorden D', 500.0, 0)):
            producto = cls.env['product.template'].create({**base, 'name': nombre, 'list_price': precio})
            if stock:
                cls.env['stock.quant']._update_available_quantity(producto.product_variant_id, cls.ubicacion, stock)

    def probar(self, cuerpo):
        codigo = """(async () => {
            const esperar = async (fn, que, intentos = 150) => {
                for (let i = 0; i < intentos; i++) {
                    const r = fn();
                    if (r) { return r; }
                    await new Promise((ok) => setTimeout(ok, 100));
                }
                throw new Error('No apareció: ' + que);
            };
            const pausa = (ms = 150) => new Promise((ok) => setTimeout(ok, ms));
            const nombres = () => [...document.querySelectorAll('.o_list_view .o_data_row td[name="name"]')]
                .map((td) => td.textContent.trim());
            const orden = (clave) => document.querySelector(`.o_dcasa_orden[data-orden="${clave}"]`);
            const pulsar = async (clave) => {
                (await esperar(() => orden(clave), 'el botón ' + clave)).click();
                await pausa();
            };
            const igual = (visto, esperado, que) => {
                if (JSON.stringify(visto) !== JSON.stringify(esperado)) {
                    const dos = [visto, esperado].map((x) => JSON.stringify(x));
                    throw new Error(`${que}: se vio ${dos[0]} y se esperaba ${dos[1]}`);
                }
            };
            // Solo las cuatro de la prueba: el buscador por nombre.
            await esperar(() => document.querySelector('.o_search_panel'), 'el panel de categorías');
            const buscador = await esperar(() => document.querySelector('.o_searchview_input'), 'el buscador');
            buscador.focus();
            buscador.value = 'Zzorden';
            buscador.dispatchEvent(new Event('input', { bubbles: true }));
            // La primera sugerencia es «Buscar Nombre o código: Zzorden».
            (await esperar(() => document.querySelector('.o_searchview_autocomplete .dropdown-item'),
                           'las sugerencias del buscador')).click();
            await esperar(() => nombres().length === 4 && nombres().every((n) => n.startsWith('Zzorden')),
                          'las 4 de la prueba');
            __CUERPO__
            console.log('test successful');
        })();""".replace('__CUERPO__', cuerpo)
        self.browser_js('/odoo/action-sale.product_template_action', codigo, login='admin')

    def test_ordenar_por_stock_y_por_precio_con_un_clic(self):
        self.probar("""
            // La columna de stock se ve con la cifra de cada producto.
            const filas = () => [...document.querySelectorAll('.o_list_view .o_data_row')];
            const cifras = () => Object.fromEntries(filas().map((fila) => [
                fila.querySelector('td[name="name"]').textContent.trim(),
                (fila.querySelector('td[name="dcasa_stock"]') || {}).textContent]));
            const stock = cifras();
            igual([stock['Zzorden A'], stock['Zzorden B'], stock['Zzorden C']].map((x) => (x || '').trim()),
                  ['50', '20', '5'], 'las cifras de la columna Stock');

            await pulsar('stock_desc');
            igual(nombres(), ['Zzorden A', 'Zzorden B', 'Zzorden C', 'Zzorden D'], 'mayor stock primero');
            if (!orden('stock_desc').classList.contains('o_activo')) {
                throw new Error('Mayor stock debe verse activo');
            }

            await pulsar('stock_asc');
            igual(nombres(), ['Zzorden D', 'Zzorden C', 'Zzorden B', 'Zzorden A'], 'menor stock primero');
            if (orden('stock_desc').classList.contains('o_activo')) { throw new Error('solo un orden a la vez'); }

            // El filtro «Disponibles» se suma al orden (no lo quita): el agotado sale y el menor stock queda primero.
            (await esperar(() => [...document.querySelectorAll('.o_dcasa_chip')]
                .find((b) => b.textContent.trim() === 'Disponibles'), 'el filtro Disponibles')).click();
            await esperar(() => nombres().length === 3, 'sin el agotado');
            igual(nombres(), ['Zzorden C', 'Zzorden B', 'Zzorden A'], 'menor stock con unidades');
            if (!orden('stock_asc').classList.contains('o_activo')) {
                throw new Error('el orden se mantiene al filtrar');
            }

            await pulsar('precio_desc');
            igual(nombres(), ['Zzorden B', 'Zzorden A', 'Zzorden C'], 'mayor precio primero');
            await pulsar('precio_asc');
            igual(nombres(), ['Zzorden C', 'Zzorden A', 'Zzorden B'], 'menor precio primero');

            // Otro clic en el mismo botón lo quita: vuelve al orden de siempre.
            await pulsar('precio_asc');
            if (document.querySelector('.o_dcasa_orden.o_activo')) {
                throw new Error('el segundo clic debe quitar el orden');
            }

            // Pelear con el título de la columna también se refleja en los botones.
            document.querySelector('.o_list_view th[data-name="dcasa_stock"]').click();
            await pausa(400);
            if (!orden('stock_asc').classList.contains('o_activo')) {
                throw new Error('el título de la columna también ordena');
            }
        """)

    def test_los_botones_de_orden_solo_salen_en_la_lista(self):
        self.probar("""
            await esperar(() => orden('stock_desc'), 'los botones en la lista');
            (await esperar(() => document.querySelector('.o_switch_view.o_kanban'), 'cambiar a tarjetas')).click();
            await esperar(() => document.querySelector('.o_kanban_view'), 'las tarjetas');
            await pausa(300);
            if (document.querySelector('.o_dcasa_orden')) { throw new Error('en tarjetas no hay botones de orden'); }
            // Los filtros rápidos sí siguen.
            const chips = [...document.querySelectorAll('.o_dcasa_chip')];
            if (!chips.some((b) => b.textContent.trim() === 'Disponibles')) {
                throw new Error('los filtros rápidos siguen en tarjetas');
            }
        """)
