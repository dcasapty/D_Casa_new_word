"""La cotización en el celular: la barra de estado y los botones bajo las líneas (auditoría visual del 2026-11-11).

* La barra de estado: «Enviar por WhatsApp», los tres puntos y el estado no caben en un renglón de 360 px. El botón se
  partía en dos líneas, los tres puntos caían debajo y la flecha del estado se montaba sobre el botón.
* Debajo de las líneas, a la vendedora le salen tres botones («Descuento», «Agregar envío», «Pedir descuento a
  Gerencia») y Odoo los apretaba en una fila: cajas de tres renglones."""
import os

from odoo.tests import HttpCase, tagged

from .test_inicio_por_rol import ESPERAR_JS


@tagged('post_install', '-at_install')
class TestCotizacionEnElCelular(HttpCase):

    def test_la_barra_de_estado_y_los_botones_no_se_desarman(self):
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        cliente = self.env['res.partner'].create({'name': 'Cliente Barra de Estado', 'phone': '+507 6000-0000'})
        producto = self.env['product.product'].create({'name': 'ZZ MESA DE PRUEBA', 'list_price': 100.0})
        orden = self.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [(0, 0, {'product_id': producto.id, 'product_uom_qty': 1, 'price_unit': 100.0})]})
        orden.state = 'sent'     # «Cotización enviada»: el estado de nombre más largo de los que se usan a diario
        codigo = '(async () => {' + ESPERAR_JS + """
            const barra = await esperar(() => document.querySelector('.o_form_view .o_form_statusbar'), 'la barra');
            const visibles = (lista) => [...lista].filter((e) => e.getBoundingClientRect().width > 0);
            const botones = visibles(barra.querySelectorAll('.o_statusbar_buttons > .btn'));
            const estado = visibles(barra.querySelectorAll('.o_field_statusbar .btn'));
            if (!botones.length || !estado.length) { throw new Error('faltan los botones o el estado de la barra'); }
            const cajas = botones.map((b) => b.getBoundingClientRect());
            for (const [i, caja] of cajas.entries()) {
                if (caja.height > 46) {
                    throw new Error('«' + botones[i].textContent.trim() + '» se parte en dos renglones');
                }
                if (Math.abs(caja.top - cajas[0].top) > 4) {
                    throw new Error('los botones de la barra deben ir juntos: uno cayó a otra fila');
                }
            }
            for (const e of estado) {
                const c = e.getBoundingClientRect();
                for (const caja of cajas) {
                    const seMontan = c.left < caja.right - 1 && c.right > caja.left + 1
                        && c.top < caja.bottom - 1 && c.bottom > caja.top + 1;
                    if (seMontan) { throw new Error('«' + e.textContent.trim() + '» se monta sobre un botón'); }
                }
                if (c.left < 0 || c.right > window.innerWidth + 1) {
                    throw new Error('el estado se sale de la pantalla');
                }
            }
            // Bajo las líneas: con tres botones (el tercero, el más largo) ninguno se parte y nada se sale.
            const fila = await esperar(() => document.querySelector('div[name="so_button_below_order_lines"]'),
                                       'los botones bajo las líneas');
            let deAbajo = visibles(fila.querySelectorAll(':scope > .btn'));
            if (!deAbajo.length) { throw new Error('no hay botones bajo las líneas'); }
            while (deAbajo.length < 3) {
                const copia = deAbajo[0].cloneNode(true);
                copia.textContent = 'Pedir descuento a Gerencia';
                fila.appendChild(copia);
                deAbajo = visibles(fila.querySelectorAll(':scope > .btn'));
            }
            for (const b of deAbajo) {
                const c = b.getBoundingClientRect();
                if (c.height > 46) { throw new Error('«' + b.textContent.trim() + '» se parte en varios renglones'); }
                if (c.left < 0 || c.right > window.innerWidth + 1) {
                    throw new Error('«' + b.textContent.trim() + '» se sale de la pantalla');
                }
            }
            if (document.documentElement.scrollWidth > window.innerWidth + 1) {
                throw new Error('la página se sale de lado');
            }
            console.log('test successful');
        })();"""
        for tamano in ('360x740', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js(f'/odoo/action-sale.action_quotations_with_onboarding/{orden.id}', codigo,
                                login='admin')
