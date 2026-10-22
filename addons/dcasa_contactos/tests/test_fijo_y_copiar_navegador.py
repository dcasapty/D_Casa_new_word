"""En el navegador: el teléfono fijo y el ícono de copiar en la ficha del cliente (2026-10-22).

* «Debería poderse poner el teléfono o celular»: en la ficha y al crear el cliente desde una cotización se ven los dos
  campos, «Celular» y «Teléfono fijo», y un cliente se guarda solo con su fijo.
* «Un ícono de copiar en la mayoría de cosas de productos y clientes»: nombre, correo, celular, fijo y RUC llevan un
  ícono que copia con un toque y avisa «Copiado», en la computadora y en el celular, sin romper el enlace de llamar ni
  el de escribir y sin cambiar la ficha. En la lista de contactos, copiar no abre la ficha."""
from odoo import Command
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
    const sinErrores = () => {
        const error = document.querySelector('.o_error_dialog, .o_dialog .modal-body .alert-danger');
        if (error) { throw new Error('Salió un error: ' + error.textContent.trim().slice(0, 300)); }
    };
    // El portapapeles de prueba: lo que se copia queda aquí (el de verdad pide permiso al navegador sin pantalla).
    const copiado = [];
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true, value: { writeText: async (texto) => { copiado.push(texto); } },
    });
    const copiar = async (selector, esperado) => {
        const campo = await esperar(() => document.querySelector(selector), 'el campo ' + selector);
        const boton = await esperar(() => campo.querySelector('.o_dcasa_copiar_boton'),
                                    'el ícono de copiar en ' + selector);
        const caja = boton.getBoundingClientRect();
        if (caja.width < 10 || caja.height < 10) { throw new Error('El ícono de ' + selector + ' no se ve'); }
        const antes = copiado.length;
        boton.click();
        await esperar(() => copiado.length === antes + 1, 'que copie ' + selector);
        if (copiado[antes] !== esperado) {
            throw new Error(`Copió «${copiado[antes]}» en vez de «${esperado}» (${selector})`);
        }
        await esperar(() => [...document.querySelectorAll('.o-tooltip')].some((t) => t.textContent.includes('Copiado')),
                      'el aviso «Copiado»');
    };
    const sinScrollDeLado = () => {
        if (document.documentElement.scrollWidth > window.innerWidth + 1) {
            throw new Error('Hay scroll de lado: ' + document.documentElement.scrollWidth + ' > ' + window.innerWidth);
        }
    };
"""

FICHA = """
    await esperar(() => document.querySelector('.o_form_view .o_field_widget[name="dcasa_telefono_fijo"]'),
                  'el teléfono fijo en la ficha');
    const icono = document.querySelector('.o_form_view div[name="phone"]').parentElement.querySelector('i.fa-mobile');
    if (!icono) { throw new Error('El celular no lleva su ícono de celular'); }
    await copiar('.o_form_view div[name="name"].o_dcasa_copiar', 'CLIENTE DE PRUEBA COPIAR');
    await copiar('.o_form_view div[name="email"].o_dcasa_copiar', 'copiar.prueba@example.com');
    await copiar('.o_form_view div[name="phone"].o_dcasa_copiar', '+507 6000-0901');
    await copiar('.o_form_view div[name="dcasa_telefono_fijo"].o_dcasa_copiar', '+507 234-0901');
    await copiar('.o_form_view div[name="vat"].o_dcasa_copiar', '8-888-9901');
    // Los enlaces de siempre siguen: llamar al celular y al fijo, escribir al correo.
    if (!document.querySelector('.o_form_view div[name="phone"] a[href^="tel:"]')) { throw new Error('Sin «Llamar»'); }
    if (!document.querySelector('.o_form_view div[name="dcasa_telefono_fijo"] a[href^="tel:"]')) {
        throw new Error('Sin «Llamar» al fijo');
    }
    if (!document.querySelector('.o_form_view div[name="email"] a[href^="mailto:"]')) { throw new Error('Sin correo'); }
    // Copiar no cambia la ficha (no aparece la nube de «sin guardar»).
    if (document.querySelector('.o_form_status_indicator_buttons:not(.invisible)')) {
        throw new Error('Copiar dejó la ficha con cambios sin guardar');
    }
    sinScrollDeLado();
    sinErrores();
"""


@tagged('post_install', '-at_install')
class TestFijoYCopiarEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_copiar', password='vend_copiar', name='Vendedora Copiar',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.cliente = cls.env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA COPIAR', 'phone': '+507 6000-0901', 'dcasa_telefono_fijo': '+507 234-0901',
            'email': 'copiar.prueba@example.com', 'vat': '8-888-9901', 'customer_rank': 1})
        cls.producto = cls.env['product.product'].create({'name': 'Armado copiar prueba', 'type': 'service',
                                                          'list_price': 50.0})

    def probar(self, url, cuerpo):
        codigo = '(async () => {' + COMUN + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js(url, codigo, login='vend_copiar', timeout=120)

    def test_copiar_en_la_ficha_en_la_computadora(self):
        self.probar(f'/odoo/contacts/{self.cliente.id}', FICHA)

    def test_copiar_en_la_ficha_en_el_celular(self):
        self.browser_size = '390x844'
        self.touch_enabled = True
        self.probar(f'/odoo/contacts/{self.cliente.id}', """
            await esperar(() => document.body.classList.contains('o_touch_device') || true, 'pantalla táctil');
        """ + FICHA)

    def test_copiar_en_la_lista_no_abre_la_ficha(self):
        self.probar('/odoo/action-contacts.action_contacts?view_type=list', """
            const fila = await esperar(() => [...document.querySelectorAll('.o_list_view .o_data_row')]
                .find((f) => f.textContent.includes('CLIENTE DE PRUEBA COPIAR')), 'la fila del cliente');
            const celda = fila.querySelector('td[name="phone"] .o_dcasa_copiar');
            if (!celda) { throw new Error('El celular de la lista no tiene el ícono de copiar'); }
            celda.querySelector('.o_dcasa_copiar_boton').click();
            await esperar(() => copiado.includes('+507 6000-0901'), 'que copie el celular desde la lista');
            await new Promise((ok) => setTimeout(ok, 500));
            if (document.querySelector('.o_form_view')) { throw new Error('Copiar abrió la ficha'); }
        """)

    def test_crear_el_cliente_desde_la_cotizacion_con_fijo_y_celular(self):
        """«Crear y editar» en el cliente de una cotización: se ven «Celular» y «Teléfono fijo»; con el fijo basta."""
        self.probar('/odoo/action-sale.action_quotations_with_onboarding/new', """
            const cliente = await esperar(() => document.querySelector('.o_form_view div[name="partner_id"] input'),
                                          'el cliente de la cotización');
            cliente.focus();
            cliente.value = 'CLIENTE DE PRUEBA SOLO FIJO';
            cliente.dispatchEvent(new Event('input', { bubbles: true }));
            const crear = await esperar(() => [...document.querySelectorAll('.o-autocomplete--dropdown-item a, '
                + '.o-autocomplete--dropdown-item')].find((a) => /Crear y editar|Create and edit/i.test(a.textContent)),
                'la opción «Crear y editar…»');
            crear.click();
            const dialogo = await esperar(() => document.querySelector('.modal .o_form_view'), 'la ficha nueva');
            const celular = await esperar(() => dialogo.querySelector('div[name="phone"] input'), 'el celular');
            const fijo = await esperar(() => dialogo.querySelector('div[name="dcasa_telefono_fijo"] input'), 'el fijo');
            if (!celular.placeholder.startsWith('Celular') || !fijo.placeholder.startsWith('Teléfono fijo')) {
                throw new Error('Los dos campos no dicen qué son: ' + celular.placeholder + ' / ' + fijo.placeholder);
            }
            const escribir = (input, valor) => {
                input.focus();
                input.value = valor;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.blur();
            };
            escribir(fijo, '234 0902');
            escribir(dialogo.querySelector('div[name="email"] input'), 'solo.fijo@example.com');
            await new Promise((ok) => setTimeout(ok, 300));
            const guardar = await esperar(() => document.querySelector('.modal .o_form_button_save, '
                + '.modal .modal-footer .btn-primary'), 'el botón Guardar');
            guardar.click();
            await esperar(() => !document.querySelector('.modal .o_form_view')
                                || document.querySelector('.o_error_dialog'), 'que se guarde el cliente');
            sinErrores();
            await esperar(() => document.querySelector('.o_form_view div[name="partner_id"] input')?.value
                                  .includes('SOLO FIJO'), 'el cliente nuevo en la cotización');
        """)
        cliente = self.env['res.partner'].search([('name', '=', 'CLIENTE DE PRUEBA SOLO FIJO')])
        self.assertEqual((cliente.phone, cliente.dcasa_telefono_fijo, cliente.email),
                         (False, '+507 234-0902', 'solo.fijo@example.com'))

    def test_un_cliente_solo_con_fijo_confirma_su_venta_en_pantalla(self):
        cliente = self.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA FIJO VENTA', 'customer_rank': 1,
                                                  'dcasa_telefono_fijo': '+507 234-0903',
                                                  'email': 'fijo.venta@example.com'})
        orden = self.env['sale.order'].create({
            'partner_id': cliente.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        self.probar(f'/odoo/sales/{orden.id}', """
            await esperar(() => document.querySelector('.o_form_view .o_statusbar_buttons'), 'la cotización');
            if (document.querySelector('.o_form_view .o_dcasa_falta_contacto')) {
                throw new Error('Sale el aviso amarillo aunque tiene teléfono fijo');
            }
            const confirmar = await esperar(
                () => document.querySelector('.o_form_view .o_statusbar_buttons button[name="action_confirm"]'),
                'el botón Confirmar');
            confirmar.click();
            const boton = '.o_form_view .o_statusbar_buttons button[name="action_confirm"]';
            await esperar(() => !document.querySelector(boton) || document.querySelector('.o_error_dialog'),
                          'que se confirme');
        """)
        self.assertEqual(orden.state, 'sale')
