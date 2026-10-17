"""«Cliente no tiene correo electrónico» en el navegador, con el guardado automático (la nube) de Odoo 19.

La dueña (2026-10-17): «esto no debería afectar el guardado en la nube. Hay que ver que aquí no vaya a haber un bug.»
Aquí la vendedora marca la casilla y sale de la pantalla sin tocar «Guardar» (el formulario se guarda solo), o la marca
y confirma la venta, o la marca en la ficha y después escribe un correo. En ningún caso sale un error."""
from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

ESPERAR_JS = """
    const esperar = async (fn, que, intentos = 150) => {
        for (let i = 0; i < intentos; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    const sinErrores = () => {
        const error = document.querySelector('.o_error_dialog, .o_dialog .modal-body .alert-danger');
        if (error) { throw new Error('Salió un error: ' + error.textContent.trim().slice(0, 300)); }
    };
    const escribir = (input, valor) => {
        input.focus();
        input.value = valor;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.blur();
    };
    // Con cambios sin guardar, Odoo muestra la nube (guardar) y la equis (descartar) junto al título.
    const sucia = () => document.querySelector('.o_form_status_indicator_buttons:not(.invisible)');
    // Sale por la miga de pan, sin tocar «Guardar»: el formulario se guarda solo (la nube).
    const salirPorLaMiga = async () => {
        const miga = await esperar(() => document.querySelector('.o_breadcrumb .breadcrumb-item:not(.active) a'),
                                   'la miga de pan');
        miga.click();
        await esperar(() => !document.querySelector('.o_form_view')
                            || document.querySelector('.o_error_dialog, .o_form_status_indicator .text-danger'),
                      'salir del formulario');
        sinErrores();
        if (document.querySelector('.o_form_status_indicator .text-danger')) {
            throw new Error('El formulario no se pudo guardar');
        }
    };
"""


@tagged('post_install', '-at_install')
class TestSinCorreoEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_nube', password='vend_nube', name='Vendedora Nube',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.producto = cls.env['product.product'].create({'name': 'Armado nube prueba', 'type': 'service',
                                                          'list_price': 80.0})

    def _cliente(self, nombre, celular):
        return self.env['res.partner'].create({'name': nombre, 'phone': celular, 'customer_rank': 1})

    def _cotizacion(self, cliente):
        return self.env['sale.order'].create({
            'partner_id': cliente.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
        })

    def probar(self, url, cuerpo):
        codigo = '(async () => {' + ESPERAR_JS + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js(url, codigo, login='vend_nube', timeout=120)

    def test_marcar_en_la_cotizacion_y_salir_guarda_solo(self):
        cliente = self._cliente('Cliente Nube Uno', '6000-0101')
        orden = self._cotizacion(cliente)
        self.probar(f'/odoo/sales/{orden.id}', """
            await esperar(() => document.querySelector('.o_form_view .o_dcasa_falta_contacto'), 'el aviso amarillo');
            const casilla = await esperar(
                () => document.querySelector('div[name="dcasa_cliente_sin_correo"] input[type="checkbox"]'),
                'la casilla junto al cliente');
            casilla.click();
            await esperar(() => !document.querySelector('.o_form_view .o_dcasa_falta_contacto'),
                          'que el aviso se vaya al marcar la casilla');
            await esperar(sucia, 'la nube: hay un cambio sin guardar');
            sinErrores();
            await salirPorLaMiga();
        """)
        self.assertTrue(cliente.dcasa_sin_correo, 'la casilla quedó guardada en la ficha del cliente')
        self.assertEqual(orden.state, 'draft')
        self.assertEqual(orden.order_line.product_id, self.producto)

    def test_marcar_en_la_cotizacion_y_confirmar(self):
        cliente = self._cliente('Cliente Nube Dos', '6000-0102')
        orden = self._cotizacion(cliente)
        self.probar(f'/odoo/sales/{orden.id}', """
            const casilla = await esperar(
                () => document.querySelector('div[name="dcasa_cliente_sin_correo"] input[type="checkbox"]'),
                'la casilla junto al cliente');
            casilla.click();
            await esperar(() => !document.querySelector('.o_form_view .o_dcasa_falta_contacto'), 'sin aviso');
            const confirmar = await esperar(
                () => document.querySelector('.o_form_view .o_statusbar_buttons button[name="action_confirm"]'),
                'el botón Confirmar');
            confirmar.click();
            const boton = '.o_form_view .o_statusbar_buttons button[name="action_confirm"]';
            await esperar(() => !document.querySelector(boton) || document.querySelector('.o_error_dialog'),
                          'que se confirme');
        """)
        self.assertTrue(cliente.dcasa_sin_correo)
        self.assertEqual(orden.state, 'sale')

    def test_sin_marcar_la_cotizacion_a_medias_se_guarda_igual(self):
        """Un borrador a medias se guarda con la nube aunque al cliente le falte el correo (lo que no se puede es
        confirmar): se escribe la referencia del cliente y se sale sin tocar «Guardar»."""
        cliente = self._cliente('Cliente Nube Tres', '6000-0103')
        orden = self._cotizacion(cliente)
        self.probar(f'/odoo/sales/{orden.id}', """
            await esperar(() => document.querySelector('.o_form_view .o_dcasa_falta_contacto'), 'el aviso amarillo');
            const pestana = await esperar(() => document.querySelector('.o_notebook a[name="other_information"]'),
                                          'la pestaña de otra información');
            pestana.click();
            const referencia = await esperar(() => document.querySelector('div[name="client_order_ref"] input'),
                                             'la referencia del cliente');
            escribir(referencia, 'Pedido a medias');
            await esperar(sucia, 'la nube: hay un cambio sin guardar');
            await salirPorLaMiga();
        """)
        self.assertEqual(orden.client_order_ref, 'Pedido a medias', 'el borrador se guardó solo')
        self.assertEqual(orden.state, 'draft')
        self.assertFalse(cliente.dcasa_sin_correo)

    def test_en_la_ficha_marcar_y_despues_escribir_el_correo(self):
        cliente = self._cliente('Cliente Nube Cuatro', '6000-0104')
        self.probar(f'/odoo/contacts/{cliente.id}', """
            const casilla = await esperar(
                () => document.querySelector('div[name="dcasa_sin_correo"] input[type="checkbox"]'),
                'la casilla debajo del correo');
            casilla.click();
            await esperar(sucia, 'la nube: hay un cambio sin guardar');
            // Esta vez con la nube (guardar a mano).
            document.querySelector('.o_form_status_indicator .o_form_button_save').click();
            await esperar(() => !sucia(), 'que se guarde');
            sinErrores();
            const correo = await esperar(() => document.querySelector('div[name="email"] input'), 'el correo');
            escribir(correo, 'Nube.Cuatro@Example.com');
            await esperar(() => !document.querySelector('div[name="dcasa_sin_correo"]'),
                          'que la casilla se desmarque y se esconda al escribir el correo');
            await salirPorLaMiga();
        """)
        self.assertFalse(cliente.dcasa_sin_correo, 'al escribir el correo, la casilla se desmarcó sola')
        self.assertEqual(cliente.email, 'nube.cuatro@example.com')

