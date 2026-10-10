"""«Cargando…» y anti doble toque del carrito (pedido de la dueña: al tocar «Agregar al carrito» no pasaba nada
visible y se podía tocar varias veces; cada toque sumaba otra unidad). Se prueba en Chrome con el teléfono emulado:

* Tienda y ficha (el JS de Odoo): el botón gira y queda bloqueado desde el primer toque, tres toques seguidos
  mandan UNA sola petición y suman UNA unidad, y al terminar el botón vuelve a su estado.
* Tarjetas de la portada y de Black Weekend (formulario normal): igual, y el segundo envío se cancela.
* La barra de progreso al abrir otra página y qué enlaces la activan.
"""
from odoo.addons.website_dcasa.models.black_weekend import PARAM_ACTIVO, PARAM_FIN, PARAM_INICIO
from odoo.tests import tagged

from .chrome_movil import ChromeMovilCase

NOMBRE = 'Silla del test del carrito'

# Tres toques seguidos al primer «Agregar al carrito» de la grilla; espera a que el botón se libere.
TRES_TOQUES = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(500);
        const boton = document.querySelector('#products_grid .o_wsale_product_btn .a-submit');
        if (!boton) { return {sinBoton: true, html: document.body.innerText.slice(0, 300)}; }
        const estado = () => ({ ocupado: !!boton.dataset.dcasaOcupado, deshabilitado: boton.disabled,
                                cargador: boton.querySelectorAll('.fa-spin').length,
                                aria: boton.getAttribute('aria-busy') });
        boton.click(); boton.click(); setTimeout(() => boton.click(), 30);
        const tras = estado();
        await esperar(60);
        const aTiempo = estado();
        let final = estado();
        for (let i = 0; i < 160 && final.ocupado; i++) { await esperar(50); final = estado(); }
        await esperar(300);
        const peticiones = performance.getEntriesByType('resource')
            .filter((r) => r.name.includes('/shop/cart/add')).length;
        return { tras, aTiempo, final, peticiones,
                 anuncio: (document.getElementById('o_dcasa_estado_carrito') || {}).textContent };
    })()
"""

# El primer formulario «Agregar» de la portada: un clic, un segundo envío (cancelado) y vuelta atrás desde el caché.
FORMULARIO = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(500);
        const forma = document.querySelector('form[action="/dcasa/carrito/agregar"]');
        if (!forma) { return {sinFormulario: true}; }
        const boton = forma.querySelector('button[type=submit]');
        let enviosNoCancelados = 0;
        // Corre DESPUÉS de la interacción (burbujea hasta el documento): cuenta lo que no canceló y frena el
        // envío real.
        document.addEventListener('submit', (ev) => {
            enviosNoCancelados += ev.defaultPrevented ? 0 : 1;
            ev.preventDefault();
        });
        const estado = () => ({ ocupado: !!boton.dataset.dcasaOcupado, deshabilitado: boton.disabled,
                                cargador: boton.querySelectorAll('.fa-spin').length });
        const antes = estado();
        boton.click();
        await esperar(40);
        const tras = estado();
        const segundo = new Event('submit', { cancelable: true, bubbles: true });
        forma.dispatchEvent(segundo);
        await esperar(40);
        window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
        const alVolver = estado();
        return { antes, tras, segundoCancelado: segundo.defaultPrevented, enviosNoCancelados, alVolver };
    })()
"""

# La decisión de la barra de progreso: qué enlaces cuentan como «abrir otra página».
ENLACES = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && !odoo.loader.modules.has('@website_dcasa/js/carrito'); i++) { await esperar(50); }
        const modulo = odoo.loader.modules.get('@website_dcasa/js/carrito');
        const enlace = (atributos) => {
            const a = document.createElement('a');
            Object.entries(atributos).forEach(([k, v]) => a.setAttribute(k, v));
            return a;
        };
        const sitio = location.origin;
        const casos = {
            otraPagina: [{ href: '/socios' }, {}],
            otraPaginaAbsoluta: [{ href: sitio + '/shop?search=cama' }, {}],
            ancla: [{ href: '#arriba' }, {}],
            mismaPagina: [{ href: location.pathname + location.search }, {}],
            pestanaNueva: [{ href: '/shop', target: '_blank' }, {}],
            descarga: [{ href: '/x.pdf', download: '' }, {}],
            menuBootstrap: [{ href: '/shop', 'data-bs-toggle': 'dropdown' }, {}],
            otroSitio: [{ href: 'https://example.com/' }, {}],
            correo: [{ href: 'mailto:info@dcasapty.com' }, {}],
            telefono: [{ href: 'tel:+50760261919' }, {}],
            conCtrl: [{ href: '/socios' }, { ctrlKey: true }],
            conMeta: [{ href: '/socios' }, { metaKey: true }],
            botonDerecho: [{ href: '/socios' }, { button: 2 }],
        };
        const resultado = {};
        for (const [nombre, [atributos, evento]] of Object.entries(casos)) {
            resultado[nombre] = modulo.esNavegacionNueva(enlace(atributos), { button: 0, ...evento });
        }
        document.documentElement.classList.add('o_dcasa_navegando');
        const barra = getComputedStyle(document.documentElement, '::before');
        resultado.barra = { posicion: barra.position, alto: barra.height, fondo: barra.backgroundColor };
        document.documentElement.classList.remove('o_dcasa_navegando');
        return resultado;
    })()
"""


@tagged('post_install', '-at_install')
class TestCarritoFeedback(ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        param = cls.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_ACTIVO, '1')       # la tarjeta de Black Weekend de la portada lleva el formulario
        param.set_param(PARAM_INICIO, '')
        param.set_param(PARAM_FIN, '')
        categoria = cls.env.ref('website_dcasa.public_category_recamaras')
        # Sin control de existencias: siempre se puede agregar (la prueba no depende del inventario).
        cls.producto = cls.env['product.template'].create({
            'name': NOMBRE, 'list_price': 49.99, 'is_published': True, 'type': 'consu', 'is_storable': False,
            'sale_ok': True, 'public_categ_ids': [(6, 0, categoria.ids)], 'dcasa_black_weekend': True})

    def _unidades_en_carritos(self):
        self.env.invalidate_all()
        lineas = self.env['sale.order.line'].sudo().search([('product_id.product_tmpl_id', '=', self.producto.id)])
        return sum(lineas.mapped('product_uom_qty'))

    def test_tres_toques_en_agregar_al_carrito_de_la_tienda_suman_una_sola_unidad(self):
        with self._chrome_movil(390) as browser:
            browser.navigate_to(self.base_url() + '/shop?search=' + NOMBRE.replace(' ', '+'), wait_stop=True)
            self.assertTrue(browser._wait_ready(), 'la tienda no terminó de cargar')
            r = self._evaluar(browser, TRES_TOQUES)
        self.assertFalse(r.get('sinBoton'), f'no hay botón «Agregar al carrito» en la tienda: {r}')
        # Desde el primer toque el botón gira, está bloqueado y avisa a los lectores de pantalla.
        for momento in ('tras', 'aTiempo'):
            self.assertTrue(r[momento]['ocupado'], f'{momento}: el botón debe estar ocupado')
            self.assertTrue(r[momento]['deshabilitado'], f'{momento}: el botón debe estar deshabilitado')
            self.assertGreaterEqual(r[momento]['cargador'], 1, f'{momento}: se debe ver el cargador')
            self.assertEqual(r[momento]['aria'], 'true')
        self.assertEqual(r['anuncio'], 'Agregando al carrito…')
        # Tres toques, una petición, una unidad.
        self.assertEqual(r['peticiones'], 1, 'los toques repetidos no deben mandar más peticiones')
        self.assertEqual(self._unidades_en_carritos(), 1, 'el carrito debe tener una sola unidad')
        # Al terminar vuelve a su estado (se puede volver a agregar a propósito).
        self.assertFalse(r['final']['ocupado'])
        self.assertFalse(r['final']['deshabilitado'])
        self.assertEqual(r['final']['cargador'], 0)
        self.assertIsNone(r['final']['aria'])

    def test_agregar_de_las_tarjetas_de_la_portada_se_bloquea_y_cancela_el_segundo_envio(self):
        with self._chrome_movil(390) as browser:
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            self.assertTrue(browser._wait_ready(), 'la portada no terminó de cargar')
            r = self._evaluar(browser, FORMULARIO)
        self.assertFalse(r.get('sinFormulario'), 'la portada no trae el formulario «Agregar»')
        self.assertEqual(r['antes'], {'ocupado': False, 'deshabilitado': False, 'cargador': 0})
        self.assertTrue(r['tras']['ocupado'])
        self.assertTrue(r['tras']['deshabilitado'])
        self.assertGreaterEqual(r['tras']['cargador'], 1)
        self.assertTrue(r['segundoCancelado'], 'un segundo envío sumaría otra unidad: se cancela')
        self.assertEqual(r['enviosNoCancelados'], 1, 'solo el primer envío sale')
        self.assertEqual(r['alVolver'], {'ocupado': False, 'deshabilitado': False, 'cargador': 0},
                         'al volver atrás desde el carrito el botón no puede quedar girando')

    def test_la_barra_de_progreso_solo_sale_al_abrir_otra_pagina_del_sitio(self):
        with self._chrome_movil(390) as browser:
            browser.navigate_to(self.base_url() + '/shop', wait_stop=True)
            self.assertTrue(browser._wait_ready(), 'la tienda no terminó de cargar')
            r = self._evaluar(browser, ENLACES)
        nuevas = {'otraPagina', 'otraPaginaAbsoluta'}
        for nombre, abre in r.items():
            if nombre == 'barra':
                continue
            self.assertEqual(abre, nombre in nuevas, f'enlace «{nombre}»')
        self.assertEqual(r['barra'], {'posicion': 'fixed', 'alto': '3px', 'fondo': 'rgb(19, 64, 177)'})
