"""«Más datos» en la cotización: los productos más arriba (decisión del 2026-11-11).

En el celular había que bajar dos pantallas para llegar a los productos: antes de las líneas iban trece datos. Los que
casi nunca se tocan al cotizar (teléfono fijo, direcciones de factura y de entrega, vencimiento, lista de precios y
términos de pago) quedan plegados detrás del botón «Más datos», justo antes de las pestañas.

* Cerrado al abrir; se abre y se cierra con el botón (un ``<button>`` con ``aria-expanded``) y ese aparato lo recuerda.
* Se abre solo si la entrega o la factura van a otra dirección, o si ahí dentro hay un dato obligatorio sin llenar o
  con error: nunca queda escondido un campo que impide guardar.
* Ningún campo cambia de sitio en la vista (otros módulos los buscan ahí): solo llevan una clase.
* Las facturas y los demás formularios no cambian.
"""
import json
import os
import re
from pathlib import Path

from lxml import etree

from odoo import Command
from odoo.tests import HttpCase, TransactionCase, tagged

from .test_inicio_por_rol import ESPERAR_JS, crear_usuario

FUENTES = Path(__file__).resolve().parents[1] / 'static' / 'src'
MARCA = 'o_dcasa_mas_dato'
# Los datos de Odoo que se pliegan (el teléfono fijo lo marca dcasa_contactos, si está instalado).
DE_ODOO = ['partner_invoice_id', 'partner_shipping_id', 'validity_date', 'pricelist_id', 'payment_term_id']

COMUN_JS = ESPERAR_JS + r"""
    const CLAVE = 'dcasa.cotizacion.mas_datos';
    const D = __DATOS__;
    const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const boton = () => document.querySelector('.o_form_view .o_dcasa_mas_datos_boton');
    const abierto = () => boton().getAttribute('aria-expanded') === 'true';
    const marcados = () => [...document.querySelectorAll('.o_form_view .o_field_widget.o_dcasa_mas_dato')];
    const nombres = () => marcados().map((campo) => campo.getAttribute('name'));
    const seVe = (el) => Boolean(el) && el.getBoundingClientRect().height > 0;
    const rotulo = (campo) => {
        const id = campo.querySelector('[id]')?.id;
        return id && document.querySelector(`.o_form_view label.o_form_label[for="${id}"]`);
    };
    const sinErrores = () => {
        const error = document.querySelector('.o_error_dialog, .o_notification.border-danger');
        if (error) { throw new Error('salió un error: ' + error.textContent.trim().slice(0, 300)); }
    };
    // La cotización, ya pintada: con su botón y con los productos.
    const listo = async () => {
        await esperar(() => boton() && document.querySelector('.o_form_view .o_notebook'), 'la cotización');
        await pausa(300);
        sinErrores();
    };
    // Desde el tope de la pantalla, sin haber bajado.
    const arriba = () => {
        for (let el = document.querySelector('.o_form_view .o_form_sheet'); el; el = el.parentElement) {
            el.scrollTop = 0;
        }
    };
    const tope = (selector) => {
        arriba();
        const el = [...document.querySelectorAll(selector)].find(seVe);
        return el ? Math.round(el.getBoundingClientRect().top) : null;
    };
    const medidas = () => ({
        pestanas: tope('.o_form_view .o_form_sheet .o_notebook'),
        producto: tope('.o_form_view [name="order_line"] .o_data_row, '
                       + '.o_form_view [name="order_line"] .o_kanban_record'),
    });
    // Cerrado: ni el campo ni su rótulo ocupan sitio. Abierto: los dos se ven.
    const revisar = (debeVerse, que) => {
        if (!marcados().length) { throw new Error(que + ': no hay ningún dato marcado'); }
        for (const campo of marcados()) {
            const nombre = campo.getAttribute('name');
            if (seVe(campo) !== debeVerse) {
                throw new Error(`${que}: «${nombre}» ${debeVerse ? 'no se ve' : 'se ve'}`);
            }
            if (!rotulo(campo)) { throw new Error(`${que}: «${nombre}» no tiene su rótulo`); }
            if (seVe(rotulo(campo)) !== debeVerse) {
                throw new Error(`${que}: el rótulo de «${nombre}» ${debeVerse ? 'no se ve' : 'se ve'}`);
            }
        }
        igual(abierto(), debeVerse, que + ': lo que dice el botón (aria-expanded)');
    };
    const nadaSeSale = (que) => {
        if (document.documentElement.scrollWidth > window.innerWidth + 1) {
            throw new Error(que + ': la página se sale de lado');
        }
        const hoja = document.querySelector('.o_form_view .o_form_sheet').getBoundingClientRect();
        const cajas = [boton(), ...marcados().filter(seVe),
                       ...document.querySelectorAll('.o_form_view .o_inner_group')];
        for (const el of cajas) {
            const caja = el.getBoundingClientRect();
            if (caja.width > 1 && (caja.left < hoja.left - 1 || caja.right > hoja.right + 1
                                   || caja.right > window.innerWidth + 1)) {
                throw new Error(`${que}: se sale de la hoja «${el.textContent.trim().slice(0, 30)}» `
                                + `${Math.round(caja.left)}–${Math.round(caja.right)}`);
            }
        }
    };
    // Vuelve a abrir la misma cotización desde cero (una pantalla nueva, como al volver a entrar).
    const reabrir = async (id) => {
        document.querySelector('.o_form_view').dataset.vieja = '1';
        await odoo.__WOWL_DEBUG__.root.env.services.action.doAction({
            type: 'ir.actions.act_window', res_model: 'sale.order', res_id: id, views: [[false, 'form']],
        }, { clearBreadcrumbs: true });
        await esperar(() => !document.querySelector('.o_form_view[data-vieja]') && boton(), 'la cotización otra vez');
        await pausa(300);
    };
    const escribir = (input, valor) => {
        input.focus();
        input.value = valor;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.blur();
    };
    // Elige una opción de un campo de «buscar y elegir». En la computadora se escribe y sale una lista debajo; en el
    // celular el campo abre un buscador a pantalla completa con las fichas.
    const elegir = async (campo, texto) => {
        const entrada = () => document.querySelector(`.o_form_view div[name="${campo}"] input`);
        if (!seVe(entrada())) { throw new Error('no se puede escribir en «' + campo + '»'); }
        if (entrada().readOnly) {
            entrada().click();
            const ficha = await esperar(() => [...document.querySelectorAll('.modal .o_kanban_record')]
                .find((f) => f.textContent.includes(texto)), `la ficha «${texto}» de ${campo}`);
            ficha.click();
            await esperar(() => !document.querySelector('.modal'), 'que cierre el buscador de ' + campo);
        } else {
            entrada().focus();
            entrada().value = texto;
            entrada().dispatchEvent(new Event('input', { bubbles: true }));
            const opcion = await esperar(() => [...document.querySelectorAll('.o-autocomplete--dropdown-item')]
                .find((o) => o.textContent.includes(texto)), `la opción «${texto}» de ${campo}`);
            (opcion.querySelector('a') || opcion).click();
            await esperar(() => !document.querySelector('.o-autocomplete--dropdown-menu'),
                          'que cierre la lista de ' + campo);
        }
        await esperar(() => entrada().value.includes(texto), `«${texto}» elegido en ${campo}`);
        await pausa(500);       // el cambio va y vuelve del servidor antes de tocar el dato siguiente
    };
    const guardar = async () => {
        document.querySelector('.o_form_status_indicator .o_form_button_save').click();
        await esperar(() => document.querySelector('.o_form_status_indicator_buttons.invisible')
                            || document.querySelector('.o_error_dialog'), 'que se guarde');
        sinErrores();
    };
"""


@tagged('post_install', '-at_install')
class TestMasDatosVistaYCodigo(TransactionCase):
    """Sin navegador: los campos siguen en su sitio, solo con la marca; y las reglas de la casa en la hoja."""

    def arbol(self, xmlid):
        return etree.fromstring(self.env.ref(xmlid).get_combined_arch())

    def test_los_datos_llevan_la_marca_y_siguen_en_su_sitio(self):
        arbol = self.arbol('sale.view_order_form')
        clientes = arbol.xpath("//group[@name='sale_header']/group[@name='partner_details']")[0]
        pedido = arbol.xpath("//group[@name='sale_header']/group[@name='order_details']")[0]
        sitios = {
            'partner_invoice_id': clientes.xpath("./field[@name='partner_invoice_id']"),
            'partner_shipping_id': clientes.xpath("./field[@name='partner_shipping_id']"),
            'validity_date': pedido.xpath("./field[@name='validity_date']"),
            'pricelist_id': pedido.xpath("./div[contains(@class, 'o_row')]/field[@name='pricelist_id']"),
            'payment_term_id': pedido.xpath("./field[@name='payment_term_id']"),
        }
        for nombre in DE_ODOO:
            with self.subTest(nombre):
                self.assertEqual(len(sitios[nombre]), 1, 'sigue en su grupo de siempre')
                self.assertIn(MARCA, (sitios[nombre][0].get('class') or '').split())
        # En el mismo orden de siempre dentro de cada grupo (nadie se movió).
        orden = [campo.get('name') for campo in clientes.xpath("./field")]
        self.assertLess(orden.index('partner_id'), orden.index('partner_invoice_id'))
        self.assertLess(orden.index('partner_invoice_id'), orden.index('partner_shipping_id'))
        orden = [campo.get('name') for campo in pedido.xpath(".//field")]
        self.assertLess(orden.index('validity_date'), orden.index('pricelist_id'))
        self.assertLess(orden.index('pricelist_id'), orden.index('payment_term_id'))
        # Lo que se queda a la vista no lleva la marca.
        for nombre in ('partner_id', 'dcasa_cliente_nombre', 'dcasa_cliente_celular', 'dcasa_cliente_correo',
                       'dcasa_cliente_cedula', 'dcasa_vendedor_id', 'dcasa_referido_por_id', 'date_order'):
            for campo in arbol.xpath(f"//group[@name='sale_header']//field[@name='{nombre}']"):
                self.assertNotIn(MARCA, (campo.get('class') or '').split(), nombre)
        # El teléfono fijo (dcasa_contactos), si está: marcado y en «Sus datos», donde siempre.
        fijo = arbol.xpath("//field[@name='dcasa_cliente_fijo']")
        if fijo:
            self.assertEqual(fijo[0].getparent(), clientes)
            self.assertIn(MARCA, fijo[0].get('class').split())
        # El botón va justo antes de las pestañas.
        boton = arbol.xpath("//sheet/widget[@name='dcasa_mas_datos']")
        self.assertEqual(len(boton), 1)
        self.assertEqual(boton[0].getnext().tag, 'notebook')
        self.assertEqual(len(arbol.xpath(f"//*[contains(@class, '{MARCA}')]")), len(DE_ODOO) + len(fijo))

    def test_las_facturas_no_cambian(self):
        arch = self.env.ref('account.view_move_form').get_combined_arch()
        self.assertNotIn(MARCA, arch)
        self.assertNotIn('dcasa_mas_datos', arch)

    def test_la_hoja_y_el_boton_respetan_las_reglas_de_la_casa(self):
        scss = (FUENTES / 'scss' / 'mas_datos.scss').read_text(encoding='utf-8')
        sin_comentarios = re.sub(r'//[^\n]*', '', scss)
        self.assertNotRegex(sin_comentarios, r'#[0-9a-fA-F]{3,8}\b', 'colores sueltos: van con las variables --dc-*')
        self.assertNotRegex(sin_comentarios, r'\brgba?\(', 'colores sueltos: van con las variables --dc-*')
        self.assertNotIn('gradient', sin_comentarios, 'sistema plano: sin degradados')
        self.assertNotIn('shadow: 0', sin_comentarios, 'sistema plano: sin sombras propias')
        self.assertNotIn('--dc-amarillo', sin_comentarios, 'el botón va sobre blanco: nada de amarillo')
        tokens = (FUENTES / 'scss' / 'tokens.scss').read_text(encoding='utf-8')
        for variable in set(re.findall(r'var\((--dc-[a-z0-9-]+)', sin_comentarios)):
            self.assertIn(variable + ':', tokens, variable)
        # El compilador de hojas de Odoo no entiende «@supports selector(…)»: el respaldo va con una regla que usa
        # :has() (un navegador que no lo conoce la descarta y el botón no sale).
        self.assertNotIn('@supports', sin_comentarios)
        self.assertIn('.o_form_sheet:has(> .o_widget_dcasa_mas_datos) > .o_widget_dcasa_mas_datos', sin_comentarios)
        self.assertIn('[aria-expanded="false"]', sin_comentarios)
        # El movimiento, solo para quien no pidió menos.
        fuera = sin_comentarios[:sin_comentarios.index('@media (prefers-reduced-motion: no-preference)')]
        self.assertNotIn('transition', fuera)
        xml = (FUENTES / 'xml' / 'mas_datos.xml').read_text(encoding='utf-8')
        for trozo in ('<button type="button" class="o_dcasa_mas_datos_boton"', 't-att-aria-expanded=',
                      't-att-aria-controls=', '<strong>Más datos</strong>', 'aria-hidden="true"'):
            self.assertIn(trozo, xml)
        js = (FUENTES / 'js' / 'mas_datos.js').read_text(encoding='utf-8')
        self.assertIn('export const CLAVE_MAS_DATOS = "dcasa.cotizacion.mas_datos";', js)
        self.assertEqual(len(re.findall(r'try \{\s+(?:return )?browser\.localStorage\.', js)), 2,
                         'leer y guardar la preferencia, las dos veces dentro de un try')


@tagged('post_install', '-at_install')
class TestMasDatosEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'vendedora_mas_datos', 'dcasa_base.group_vendedora')
        cls.admin = cls.env.ref('base.user_admin')
        # Las direcciones y la lista de precios son dos ajustes de Odoo (grupos): aquí, encendidos para las dos
        # personas de la prueba, con una lista de precios activa.
        ajustes = [Command.link(cls.env.ref('account.group_delivery_invoice_address').id),
                   Command.link(cls.env.ref('product.group_product_pricelist').id)]
        (cls.vendedora | cls.admin).write({'group_ids': ajustes})
        cls.lista = cls.env['product.pricelist'].create({'name': 'AAA LISTA MAS DATOS'})
        cls.plazo = cls.env['account.payment.term'].create({'name': 'AAA PLAZO MAS DATOS'})
        # Los nombres empiezan por «AAA» para salir en la primera página de los buscadores del celular (van por orden
        # alfabético) aunque la base tenga miles de fichas.
        Partner = cls.env['res.partner']
        cls.cliente = Partner.create({
            'name': 'AAA CLIENTE DE PRUEBA MAS DATOS', 'phone': '+507 6990-7711', 'email': 'zz.mas.datos@example.com',
            'street': 'Calle de prueba 1', 'city': 'La Chorrera'})
        # Otra persona con otra dirección de entrega: sus cotizaciones nacen con la entrega en esa dirección.
        cls.cliente_dos = Partner.create({
            'name': 'AAA CLIENTE DE PRUEBA DOS DIRECCIONES', 'phone': '+507 6990-7712',
            'email': 'zz.mas.datos.dos@example.com'})
        cls.entrega = Partner.create({
            'name': 'AAA CASA DE ENTREGA', 'type': 'delivery', 'parent_id': cls.cliente_dos.id,
            'street': 'Calle de prueba 2', 'city': 'Arraiján'})
        cls.otra_entrega = Partner.create({'name': 'AAA ENTREGA MAS DATOS', 'street': 'Calle de prueba 3'})
        cls.producto = cls.env['product.product'].create({'name': 'ZZ MESA MAS DATOS', 'list_price': 100.0})

    def setUp(self):
        super().setUp()
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')

    def cotizacion(self, cliente=None, usuario=None, lineas=3):
        return self.env['sale.order'].create({
            'partner_id': (cliente or self.cliente).id, 'user_id': (usuario or self.vendedora).id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': n + 1})
                           for n in range(lineas)]})

    def probar(self, ruta, cuerpo, login, tamano, datos=None):
        codigo = ('(async () => {' + COMUN_JS.replace('__DATOS__', json.dumps(datos or {})) + cuerpo
                  + "console.log('test successful'); })();")
        self.browser_size = tamano
        self.browser_js(ruta, codigo, login=login, timeout=120)

    def ruta(self, orden):
        return f'/odoo/action-sale.action_quotations_with_onboarding/{orden.id}'

    def en_cada_pantalla(self):
        """Celular y computadora, con el administrador y con una vendedora."""
        for tamano in ('390x844', '1366x768'):
            for login in ('admin', 'vendedora_mas_datos'):
                yield tamano, login

    def test_cerrado_al_abrir_los_productos_quedan_arriba_y_se_recuerda(self):
        orden = self.cotizacion()
        self.assertEqual(orden.partner_shipping_id, orden.partner_id)
        cuerpo = r"""
            await listo();
            const celular = window.innerWidth < 768;
            // Los cinco datos de Odoo (y el teléfono fijo, si está ese módulo) existen y están marcados.
            for (const nombre of D.de_odoo) {
                if (!nombres().includes(nombre)) { throw new Error('falta el dato «' + nombre + '»'); }
            }
            // Cerrado al abrir: no ocupan sitio; lo de siempre sigue a la vista.
            revisar(false, 'al abrir');
            for (const nombre of ['partner_id']) {
                if (!seVe(document.querySelector(`.o_form_view div[name="${nombre}"]`))) {
                    throw new Error('«' + nombre + '» tiene que seguir a la vista');
                }
            }
            const cerrado = medidas();
            nadaSeSale('cerrado');
            // El botón: un botón de verdad, antes de las pestañas, que dice qué guarda.
            const b = boton();
            igual([b.tagName, b.type, b.tabIndex], ['BUTTON', 'button', 0], 'un botón, para teclado y lector');
            const texto = b.textContent.trim().replace(/\s+/g, ' ');
            if (!/^Más datos: direcciones, vencimiento, lista de precios(,| y) pago/.test(texto)) {
                throw new Error('el botón dice qué guarda: ' + texto);
            }
            const controla = (b.getAttribute('aria-controls') || '').split(' ').filter(Boolean);
            igual(controla.length, marcados().length, 'aria-controls nombra cada dato');
            for (const id of controla) {
                if (!document.getElementById(id)) { throw new Error('aria-controls apunta a nada: ' + id); }
            }
            const caja = b.getBoundingClientRect();
            const pestanas = document.querySelector('.o_form_view .o_notebook').getBoundingClientRect();
            if (caja.bottom > pestanas.top + 1) { throw new Error('el botón va antes de las pestañas'); }
            if (celular && caja.height < 44) { throw new Error('en el celular el botón mide al menos 44 px de alto'); }
            igual(getComputedStyle(b).boxShadow, 'none', 'sistema plano: sin sombra');

            // Se abre: los datos vuelven a su sitio de siempre, con su rótulo, y los productos bajan.
            b.click();
            await esperar(() => abierto(), 'que abra');
            revisar(true, 'abierto');
            igual(localStorage.getItem(CLAVE), '1', 'lo recuerda el aparato');
            const abiertos = medidas();
            nadaSeSale('abierto');
            console.log('MEDIDAS ' + JSON.stringify({ ancho: window.innerWidth, cerrado, abiertos }));
            if (!(cerrado.pestanas < abiertos.pestanas) || !(cerrado.producto < abiertos.producto)) {
                throw new Error('cerrado, los productos van más arriba: ' + JSON.stringify([cerrado, abiertos]));
            }
            if (celular) {
                // En el celular: los productos suben más de 250 px y las pestañas quedan a poco más de una pantalla.
                if (abiertos.producto - cerrado.producto < 250) {
                    throw new Error('los productos suben muy poco: ' + (abiertos.producto - cerrado.producto));
                }
                if (cerrado.pestanas > __TOPE_PESTANAS__ || cerrado.producto > __TOPE_PRODUCTO__) {
                    throw new Error('los productos quedan muy abajo: ' + JSON.stringify(cerrado));
                }
            }

            // Se recuerda: al volver a entrar abre como quedó (abierto); se cierra y también se recuerda.
            await reabrir(D.id);
            revisar(true, 'recordado abierto');
            boton().click();
            await esperar(() => !abierto(), 'que cierre');
            revisar(false, 'cerrado otra vez');
            igual(localStorage.getItem(CLAVE), '0', 'recuerda que quedó cerrado');
            await reabrir(D.id);
            revisar(false, 'recordado cerrado');

            // Sin almacenamiento (ventana privada, bloqueado) funciona igual: abre y cierra, y nace cerrado.
            // (Solo falla esta preferencia: otras piezas de Odoo también leen el almacenamiento al abrir.)
            const poner = Storage.prototype.setItem;
            const leer = Storage.prototype.getItem;
            Storage.prototype.setItem = function (clave, valor) {
                if (clave === CLAVE) { throw new Error('bloqueado'); }
                return poner.call(this, clave, valor);
            };
            boton().click();
            await esperar(() => abierto(), 'que abra sin poder guardar');
            revisar(true, 'sin poder guardar');
            igual(leer.call(localStorage, CLAVE), '0', 'no se pudo guardar');
            Storage.prototype.getItem = function (clave) {
                if (clave === CLAVE) { throw new Error('bloqueado'); }
                return leer.call(this, clave);
            };
            await reabrir(D.id);
            revisar(false, 'sin poder leer');
            Storage.prototype.setItem = poner;
            Storage.prototype.getItem = leer;
            sinErrores();
        """
        # Topes del celular (390 px de ancho): antes del cambio las pestañas quedaban a 1251 px del tope y el primer
        # producto a 1454 (con todos los módulos); ahora, a unos 900 y 1100.
        cuerpo = cuerpo.replace('__TOPE_PESTANAS__', '960').replace('__TOPE_PRODUCTO__', '1170')
        for tamano, login in self.en_cada_pantalla():
            with self.subTest(tamano=tamano, login=login):
                self.probar(self.ruta(orden), cuerpo, login, tamano, {'id': orden.id, 'de_odoo': DE_ODOO})

    def test_con_otra_direccion_de_entrega_abre_solo(self):
        orden = self.cotizacion(cliente=self.cliente_dos)
        self.assertEqual(orden.partner_shipping_id, self.entrega, 'la entrega va a la otra dirección')
        cuerpo = r"""
            // Aunque el aparato recuerde «cerrado».
            await listo();
            localStorage.setItem(CLAVE, '0');
            await reabrir(D.id);
            revisar(true, 'con la entrega en otra dirección');
            const entrega = document.querySelector('.o_form_view div[name="partner_shipping_id"] input');
            if (!entrega.value.includes('AAA CASA DE ENTREGA')) { throw new Error('la entrega: ' + entrega.value); }
            igual(boton().getAttribute('aria-disabled'), null, 'se puede cerrar: no falta ningún dato');
            // El botón dice por qué se abrió (en el celular el nombre de la dirección sale cortado).
            const aviso = () => boton().querySelector('.o_dcasa_mas_datos_aviso')?.textContent.trim();
            igual(aviso(), 'La entrega va a otra dirección.', 'el aviso del botón');
            nadaSeSale('abierto solo');
            // La persona lo puede cerrar (el aviso sigue a la vista); al volver a entrar abre solo otra vez.
            boton().click();
            await esperar(() => !abierto(), 'que cierre');
            revisar(false, 'cerrado a mano');
            igual(aviso(), 'La entrega va a otra dirección.', 'el aviso, también cerrado');
            await reabrir(D.id);
            revisar(true, 'otra vez abierto solo');
            // Una cotización con la entrega en la dirección del cliente sigue cerrada.
            await reabrir(D.normal);
            revisar(false, 'la de siempre');
            igual(aviso(), undefined, 'sin aviso cuando todo va a la dirección del cliente');
            sinErrores();
        """
        normal = self.cotizacion()
        for tamano, login in self.en_cada_pantalla():
            with self.subTest(tamano=tamano, login=login):
                self.probar(self.ruta(orden), cuerpo, login, tamano, {'id': orden.id, 'normal': normal.id})

    def test_los_datos_se_editan_y_se_guardan(self):
        hay_fijo = 'dcasa_cliente_fijo' in self.env['sale.order']._fields
        cuerpo = r"""
            await listo();
            boton().click();
            await esperar(() => abierto(), 'que abra');
            revisar(true, 'abierto para editar');
            // Ninguno quedó de solo lectura.
            for (const campo of marcados()) {
                if (campo.classList.contains('o_readonly_modifier')) {
                    throw new Error('«' + campo.getAttribute('name') + '» quedó de solo lectura');
                }
            }
            await elegir('payment_term_id', 'AAA PLAZO MAS DATOS');
            await elegir('pricelist_id', 'AAA LISTA MAS DATOS');
            await elegir('partner_invoice_id', 'AAA ENTREGA MAS DATOS');
            await elegir('partner_shipping_id', 'AAA ENTREGA MAS DATOS');
            if (D.hay_fijo) {
                escribir(document.querySelector('.o_form_view div[name="dcasa_cliente_fijo"] input'), '234-5678');
            }
            // El vencimiento: se toca y se escribe otra fecha.
            const fecha = document.querySelector('.o_form_view div[name="validity_date"] .o_input');
            fecha.click();
            const entrada = await esperar(
                () => document.querySelector('.o_form_view div[name="validity_date"] input.o_input'), 'la fecha');
            entrada.focus();
            entrada.value = '31/12/2030';
            entrada.dispatchEvent(new Event('input', { bubbles: true }));
            entrada.dispatchEvent(new Event('change', { bubbles: true }));
            entrada.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
            await pausa(300);
            document.querySelector('.o_form_view .oe_title').click();
            await pausa(300);
            await guardar();
            // Guardado: los datos siguen ahí al volver a entrar (la entrega ya no es la del cliente: abre solo).
            await reabrir(D.id);
            revisar(true, 'después de guardar');
            sinErrores();
        """
        for tamano, login in self.en_cada_pantalla():
            with self.subTest(tamano=tamano, login=login):
                orden = self.cotizacion(usuario=self.admin if login == 'admin' else self.vendedora)
                self.probar(self.ruta(orden), cuerpo, login, tamano, {'id': orden.id, 'hay_fijo': hay_fijo})
                orden.invalidate_recordset()
                self.cliente.invalidate_recordset()
                self.assertEqual(orden.payment_term_id, self.plazo)
                self.assertEqual(orden.pricelist_id, self.lista)
                self.assertEqual(orden.partner_invoice_id, self.otra_entrega)
                self.assertEqual(orden.partner_shipping_id, self.otra_entrega)
                self.assertEqual(str(orden.validity_date), '2030-12-31')
                if hay_fijo:
                    self.assertTrue((self.cliente.dcasa_telefono_fijo or '').replace(' ', '').endswith('234-5678'),
                                    self.cliente.dcasa_telefono_fijo)
                    self.cliente.dcasa_telefono_fijo = False

    def test_un_dato_obligatorio_sin_llenar_no_queda_escondido(self):
        cuerpo = r"""
            localStorage.setItem(CLAVE, '0');
            await esperar(() => boton(), 'la cotización nueva');
            await pausa(300);
            // Sin cliente todavía: cerrado (las direcciones salen del cliente; lo que falta es el cliente, que se ve).
            igual(abierto(), false, 'nueva, sin cliente');
            igual(boton().getAttribute('aria-disabled'), null, 'nueva, sin cliente');
            // Se intenta guardar sin cliente: Odoo marca el cliente y las direcciones, y el bloque se abre solo.
            document.querySelector('.o_form_status_indicator .o_form_button_save').click();
            await esperar(() => document.querySelector('.o_form_view div[name="partner_invoice_id"].o_field_invalid'),
                          'la dirección de factura marcada');
            await esperar(() => abierto(), 'que se abra solo');
            for (const nombre of ['partner_invoice_id', 'partner_shipping_id']) {
                const campo = document.querySelector(`.o_form_view div[name="${nombre}"]`);
                if (!seVe(campo) || !campo.classList.contains('o_field_invalid')) {
                    throw new Error('«' + nombre + '» tiene que verse, marcado');
                }
            }
            igual(boton().getAttribute('aria-disabled'), 'true', 'mientras falte un dato no se cierra');
            if (!boton().textContent.includes('Falta llenar un dato de aquí.')) {
                throw new Error('el botón avisa que falta un dato: ' + boton().textContent);
            }
            boton().click();
            await pausa(300);
            igual(abierto(), true, 'no se cierra aunque lo toquen');
            igual(localStorage.getItem(CLAVE), '0', 'ni cambia lo que recuerda el aparato');
            nadaSeSale('con un dato sin llenar');
            // Con el cliente elegido ya no falta nada: se puede cerrar.
            await elegir('partner_id', 'AAA CLIENTE DE PRUEBA MAS DATOS');
            await esperar(() => boton().getAttribute('aria-disabled') === null, 'que deje cerrar');
            igual(abierto(), true, 'se queda abierto hasta que la persona lo cierre');
            boton().click();
            await esperar(() => !abierto(), 'que cierre');
            revisar(false, 'cerrado con todo lleno');
            // La cotización de prueba no se guarda.
            document.querySelector('.o_form_status_indicator .o_form_button_cancel').click();
            await pausa(300);
        """
        for tamano, login in self.en_cada_pantalla():
            with self.subTest(tamano=tamano, login=login):
                self.probar('/odoo/action-sale.action_quotations_with_onboarding/new', cuerpo, login, tamano)
