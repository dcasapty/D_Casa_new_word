"""Copiar con un toque en el producto (pedido de la dueña, 2026-10-22: «un ícono de copiar en la mayoría de cosas de
productos y clientes: nombre, correo, teléfono, códigos, nombres de productos»).

En la ficha del producto: nombre, referencia, código de barras y código público; en la lista: nombre, referencia y
código público. Copia el dato tal cual y avisa «Copiado», en la computadora y en el celular."""
from odoo.tests import HttpCase, new_test_user, tagged

COMUN = """
    const esperar = async (fn, que, intentos = 150) => {
        for (let i = 0; i < intentos; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    const copiado = [];
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true, value: { writeText: async (texto) => { copiado.push(texto); } },
    });
    const copiar = async (selector, esperado) => {
        const campo = await esperar(() => document.querySelector(selector), 'el campo ' + selector);
        const boton = await esperar(() => campo.querySelector('.o_dcasa_copiar_boton'),
                                    'el ícono de copiar en ' + selector);
        const antes = copiado.length;
        boton.click();
        await esperar(() => copiado.length === antes + 1, 'que copie ' + selector);
        if (copiado[antes] !== esperado) {
            throw new Error(`Copió «${copiado[antes]}» en vez de «${esperado}» (${selector})`);
        }
        await esperar(() => [...document.querySelectorAll('.o-tooltip')].some((t) => t.textContent.includes('Copiado')),
                      'el aviso «Copiado»');
    };
"""

FICHA = """
    await copiar('.o_form_view div[name="name"].o_dcasa_copiar', 'SOFÁ DE PRUEBA COPIAR');
    await copiar('.o_form_view div[name="default_code"].o_dcasa_copiar', 'COPIA-001');
    await copiar('.o_form_view div[name="barcode"].o_dcasa_copiar', '7700000000017');
    await copiar('.o_form_view div[name="dcasa_codigo_publico"].o_dcasa_copiar', CODIGO_PUBLICO);
    if (document.querySelector('.o_form_status_indicator_buttons:not(.invisible)')) {
        throw new Error('Copiar dejó el producto con cambios sin guardar');
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error('Hay scroll de lado'); }
"""


@tagged('post_install', '-at_install')
class TestCopiarEnElProducto(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(cls.env, login='vend_copiar_prod', password='vend_copiar_prod', name='Vendedora Copiar Producto',
                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.producto = cls.env['product.template'].create({
            'name': 'SOFÁ DE PRUEBA COPIAR', 'default_code': 'COPIA-001', 'barcode': '7700000000017',
            'type': 'consu', 'list_price': 10.0})

    def probar(self, url, cuerpo):
        codigo = ('(async () => {' + COMUN + cuerpo.replace('CODIGO_PUBLICO', repr(self.producto.dcasa_codigo_publico))
                  + "console.log('test successful'); })();")
        self.browser_js(url, codigo, login='vend_copiar_prod', timeout=120)

    def test_copiar_en_la_ficha_en_la_computadora(self):
        self.assertTrue(self.producto.dcasa_codigo_publico)
        self.probar(f'/odoo/action-product.product_template_action/{self.producto.id}', FICHA)

    def test_copiar_en_la_ficha_en_el_celular(self):
        self.browser_size = '390x844'
        self.touch_enabled = True
        self.probar(f'/odoo/action-product.product_template_action/{self.producto.id}', FICHA)

    def test_copiar_en_la_lista(self):
        self.probar('/odoo/action-product.product_template_action?view_type=list', """
            const fila = await esperar(() => [...document.querySelectorAll('.o_list_view .o_data_row')]
                .find((f) => f.textContent.includes('COPIA-001')), 'la fila del producto');
            for (const [nombre, esperado] of [['name', 'SOFÁ DE PRUEBA COPIAR'], ['default_code', 'COPIA-001'],
                                              ['dcasa_codigo_publico', CODIGO_PUBLICO]]) {
                const boton = fila.querySelector(`td[name="${nombre}"] .o_dcasa_copiar_boton`);
                if (!boton) { throw new Error('Sin ícono de copiar en la columna ' + nombre); }
                boton.click();
                await esperar(() => copiado.includes(esperado), 'que copie ' + nombre + ' desde la lista');
            }
            await new Promise((ok) => setTimeout(ok, 500));
            if (document.querySelector('.o_form_view')) { throw new Error('Copiar abrió el producto'); }
        """)
