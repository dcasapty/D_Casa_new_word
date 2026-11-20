"""El pago como un checkout moderno (rediseño visual, 2026-11-20): lo que la persona ve y lo que el JavaScript de Odoo
necesita para seguir funcionando.

Se cargan las pantallas de verdad (HTTP): el paso de pago de la tienda (``/shop/payment``), la ventana «Pagar tu pedido»
del portal (``/my/orders/<id>``), «Estado del pago» y la confirmación. Se comprueba:

* la pantalla sin distracciones (cabecera mínima: sin menú de la tienda ni barra de avisos);
* que cada método conserva lo que usa el formulario de pago de Odoo (``#o_payment_form``, ``name="o_payment_option"``,
  ``input[name=o_payment_radio]`` con sus ``data-payment-option-*``, ``.o_payment_option_label``,
  ``button[name=o_payment_submit_button]``): el JavaScript no se tocó y sus nombres siguen ahí;
* el botón «Pagar $ monto», el resumen con ITBMS y total, el resumen plegable del celular y la ayuda por WhatsApp;
* íconos propios y DISTINTOS para Yappy, transferencia y pago en la tienda (nunca el mismo ícono ni el logo de Yappy);
* el premio de Socios en el resumen y los tres estados del pago (esperando, pago recibido, no se completó).
"""
import re
from datetime import timedelta

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

CLAVE = 'Prueba-pago-visual-1'
CORREO = 'camila.pago.visual@example.com'
ICONOS = ('yappy', 'transferencia', 'tienda')


class PagoVisualDatos:
    """Un cliente del portal con dirección y un servicio de 100 dólares (sin entrega: el pago no pide transportista).
    Se mezcla con ``HttpCase`` (aquí) o con ``ChromeMovilCase`` (test_pago_celular.py)."""

    @classmethod
    def preparar_pago(cls):
        cls.website = cls.env.ref('website.default_website')
        cls.producto = cls.env['product.product'].create({
            'name': 'SERVICIO DE PRUEBA DEL PAGO', 'type': 'service', 'list_price': 100.0, 'is_published': True,
            'sale_ok': True})
        cls.usuario = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Camila Prueba Pago', 'login': CORREO, 'email': CORREO, 'password': CLAVE,
            'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        cls.cliente = cls.usuario.partner_id
        cls.cliente.write({
            'phone': '+507 6000-0505', 'street': 'Calle de prueba 5', 'city': 'La Chorrera',
            'country_id': cls.env.ref('base.pa').id})

    def entrar_y_llenar_el_carrito(self, cantidad=1):
        self.authenticate(CORREO, CLAVE)
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.producto.product_tmpl_id.id, 'product_id': self.producto.id,
            'quantity': cantidad})
        orden = self.env['sale.order'].search(
            [('partner_id', '=', self.cliente.id), ('website_id', '=', self.website.id)], order='id desc', limit=1)
        self.assertTrue(orden, 'la tienda armó el carrito')
        return orden


class PagoVisualComun(PagoVisualDatos, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_pago()

    def pagina(self, ruta):
        respuesta = self.url_open(ruta)
        self.assertEqual(respuesta.status_code, 200, ruta)
        return respuesta.url, respuesta.text, lxml_html.fromstring(respuesta.text)

    @staticmethod
    def texto(nodo):
        return re.sub(r'\s+', ' ', nodo.text_content()).strip()


@tagged('post_install', '-at_install')
class TestPaginaDePago(PagoVisualComun):

    def setUp(self):
        super().setUp()
        self.orden = self.entrar_y_llenar_el_carrito()

    def test_es_una_pantalla_sin_distracciones(self):
        url, texto, arbol = self.pagina('/shop/payment')
        self.assertIn('/shop/payment', url)
        # Cabecera mínima: logo, «Pago seguro» y volver al carrito.
        cabecera = arbol.xpath('//div[contains(@class, "o_dcasa_pago_cabecera")]')
        self.assertEqual(len(cabecera), 1)
        self.assertIn('Pago seguro', self.texto(cabecera[0]))
        volver = cabecera[0].xpath('.//a[contains(@class, "o_dcasa_pago_volver")]')
        self.assertEqual(len(volver), 1)
        self.assertEqual(volver[0].get('href'), '/shop/cart')
        self.assertIn('Volver al carrito', self.texto(volver[0]))
        self.assertTrue(cabecera[0].xpath('.//a[@href="/"]//img'), 'el logo lleva a la tienda')
        # Sin menú de la tienda, ni barra de avisos, ni botón flotante de WhatsApp.
        self.assertNotIn('o_dcasa_anuncios', texto)
        self.assertFalse(arbol.xpath('//header[@id="top"]'), 'sin la cabecera de Odoo (menú, buscador, avisos)')
        self.assertNotIn('o_dcasa_wa_float', texto)
        self.assertTrue(arbol.xpath('//body[contains(@class, "o_dcasa_pago")]'))

    def test_los_metodos_siguen_enganchados_al_javascript_de_odoo(self):
        _url, _texto, arbol = self.pagina('/shop/payment')
        self.assertEqual(len(arbol.xpath('//form[@id="o_payment_form"]')), 1)
        filas = arbol.xpath('//form[@id="o_payment_form"]//li[@name="o_payment_option"]')
        radios = arbol.xpath('//form[@id="o_payment_form"]//input[@name="o_payment_radio"]')
        self.assertGreaterEqual(len(filas), 2, 'Yappy y transferencia por lo menos')
        self.assertEqual(len(filas), len(radios), 'un radio por fila')
        for radio in radios:
            for atributo in ('data-payment-option-type', 'data-payment-option-id', 'data-provider-id',
                             'data-provider-code', 'data-payment-method-code'):
                self.assertTrue(radio.get(atributo), f'{atributo} sigue en el radio: lo lee el JavaScript de Odoo')
            self.assertEqual(radio.get('data-payment-option-type'), 'payment_method')
            etiqueta = arbol.xpath(f'//label[@for="{radio.get("id")}"][contains(@class, "o_payment_option_label")]')
            self.assertEqual(len(etiqueta), 1, 'cada radio sigue con su etiqueta .o_payment_option_label')
        # Los dos botones de pagar (el de la columna y el pegado abajo en el celular) conservan su nombre.
        botones = arbol.xpath('//button[@name="o_payment_submit_button"]')
        self.assertEqual(len(botones), 2)
        for boton in botones:
            self.assertEqual(boton.get('type'), 'submit')
            self.assertEqual(boton.get('disabled'), 'true', 'nace apagado hasta elegir un método, como siempre')
        self.assertEqual(arbol.xpath('//form[@id="o_payment_form"]')[0].get('data-transaction-route'),
                         f'/shop/payment/transaction/{self.orden.id}')

    def test_el_boton_dice_cuanto_se_paga_y_hay_ayuda_por_whatsapp(self):
        _url, _texto, arbol = self.pagina('/shop/payment')
        total = f'{self.orden.amount_total:.2f}'
        for boton in arbol.xpath('//button[@name="o_payment_submit_button"]'):
            etiqueta = self.texto(boton)
            self.assertTrue(etiqueta.startswith('Pagar'), etiqueta)
            self.assertIn(total, etiqueta, 'el botón lleva el monto: «Pagar $ …»')
        ayuda = arbol.xpath('//p[contains(@class, "o_dcasa_pago_ayuda_wa")]')
        self.assertEqual(len(ayuda), 1)
        self.assertIn('¿Dudas?', self.texto(ayuda[0]))
        enlace = ayuda[0].xpath('.//a')[0]
        self.assertTrue(enlace.get('href').startswith('https://wa.me/'), 'el número sale de la configuración del sitio')
        self.assertEqual(enlace.get('target'), '_blank')
        self.assertIn('Escríbenos por WhatsApp', self.texto(enlace))

    def test_el_resumen_trae_itbms_total_y_el_plegable_del_celular(self):
        _url, _texto, arbol = self.pagina('/shop/payment')
        total = f'{self.orden.amount_total:.2f}'
        panel = arbol.xpath('//div[contains(@class, "o_total_card")]')
        self.assertTrue(panel)
        self.assertIn('Resumen del pedido', self.texto(panel[0]))
        filas = [self.texto(fila) for fila in panel[0].xpath('.//table[contains(@class, "o_cart_products_table")]//tr')]
        self.assertTrue(any('SERVICIO DE PRUEBA DEL PAGO' in fila for fila in filas), 'la línea del pedido')
        etiquetas = [self.texto(td) for td in panel[0].xpath('.//div[contains(@class, "o_cart_total")]//tr/td[1]')]
        orden_de_filas = [e for e in etiquetas if e in ('Subtotal', 'ITBMS', 'Total')]
        self.assertEqual(orden_de_filas, ['Subtotal', 'ITBMS', 'Total'], 'el impuesto se llama ITBMS')
        self.assertNotIn('Impuestos', self.texto(panel[0]))
        self.assertIn(total, self.texto(panel[0].xpath('.//tr[@name="o_order_total"]')[0]))
        # El celular: «Ver resumen del pedido · $ 106.00», plegable, arriba (antes del contenido).
        plegable = arbol.xpath('//div[contains(@class, "o_dcasa_pago_resumen_movil")]')
        self.assertEqual(len(plegable), 1)
        boton = plegable[0].xpath('.//button[@data-bs-toggle="collapse"]')[0]
        self.assertIn('Ver resumen del pedido', self.texto(boton))
        self.assertIn(total, self.texto(boton))
        self.assertEqual(boton.get('data-bs-target'), '#o_dcasa_pago_resumen')
        self.assertTrue(plegable[0].xpath('.//div[@id="o_dcasa_pago_resumen" and contains(@class, "collapse")]'))

    def test_la_entrega_va_antes_de_elegir_como_pagar(self):
        _url, texto, _arbol = self.pagina('/shop/payment')
        self.assertLess(texto.index('id="address_on_payment"'), texto.index('id="o_payment_form"'),
                        'la dirección se ve ANTES de la lista de métodos')

    def test_cada_metodo_manual_tiene_su_icono_propio_y_distinto(self):
        _url, _texto, arbol = self.pagina('/shop/payment')
        iconos = {}
        for fila in arbol.xpath('//li[@name="o_payment_option"]'):
            nombre = self.texto(fila.xpath('.//label[contains(@class, "o_payment_option_label")]')[0])
            imagenes = fila.xpath('.//span[contains(@class, "o_dcasa_pago_iconos")]//img/@src')
            self.assertTrue(imagenes, f'«{nombre}» lleva su ícono')
            iconos[nombre] = tuple(imagenes)
        propios = {n: i for n, i in iconos.items() if n in ('Yappy', 'Transferencia bancaria', 'Pago en la tienda')}
        self.assertTrue(propios)
        self.assertEqual(len(set(propios.values())), len(propios), f'cada método con un ícono distinto: {propios}')
        for nombre, imagenes in propios.items():
            self.assertTrue(imagenes[0].startswith('/website_dcasa/static/src/img/pago/'), nombre)
            self.assertNotIn('bank.png', imagenes[0], 'ya no es el ícono naranja de Odoo')
        for icono in ICONOS:
            self.assertEqual(self.url_open(f'/website_dcasa/static/src/img/pago/{icono}.svg').status_code, 200)

    def test_tilopay_muestra_visa_y_mastercard_de_odoo(self):
        metodo = self.env.ref('dcasa_pago_tilopay.payment_method_tilopay', raise_if_not_found=False)
        if not metodo:
            self.skipTest('dcasa_pago_tilopay no está instalado')
        # El ícono sale de la plantilla del logo: se renderiza con el método de Tilopay, sin encender la pasarela.
        vista = self.env['ir.qweb']._render('payment.form_logo', {'logo_pm_sudo': metodo})
        self.assertIn('/payment/static/img/visa.png', vista)
        self.assertIn('/payment/static/img/mastercard.png', vista)
        self.assertNotIn('amex', vista, 'solo las tarjetas que propone docs/TILOPAY.md')
        for archivo in ('visa', 'mastercard'):
            self.assertEqual(self.url_open(f'/payment/static/img/{archivo}.png').status_code, 200)

    def test_el_premio_de_socios_se_ve_como_un_descuento_en_el_resumen(self):
        premio = self.env.ref('dcasa_socios.premio_desc_10')
        canje = self.env['dcasa.canje'].sudo().create({
            'codigo': 'TSTP10', 'partner_id': self.cliente.id, 'premio_id': premio.id,
            'premio_nombre': premio.name, 'puntos': premio.puntos, 'valor': premio.valor, 'costo': premio.costo,
            'origen': 'web', 'expira_en': fields.Datetime.now() + timedelta(days=3)})
        self.env['sale.order.line'].sudo().with_context(dcasa_aplicando_premio=True).create({
            'order_id': self.orden.id, 'product_id': self.env.ref('dcasa_socios.product_premio_canje').id,
            'name': f'Premio {canje.codigo}: {premio.name}', 'product_uom_qty': 1, 'price_unit': -9.35,
            'dcasa_canje_id': canje.id})
        _url, _texto, arbol = self.pagina('/shop/payment')
        filas = arbol.xpath('//div[contains(@class, "o_total_card")]//tr[contains(@class, "o_dcasa_pago_premio")]')
        self.assertEqual(len(filas), 1, 'la línea del premio lleva su clase para verse como un descuento')
        self.assertIn(f'Premio {canje.codigo}', self.texto(filas[0]))
        self.assertIn('-9.35', self.texto(filas[0]).replace(' ', '').replace('\xa0', ''))


@tagged('post_install', '-at_install')
class TestVentanaDelPortalYEstados(PagoVisualComun):

    def pedido_para_pagar(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'website_id': self.website.id, 'require_payment': True,
            'prepayment_percent': 1.0,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 2})]})
        orden.action_quotation_sent()
        return orden

    def test_la_ventana_de_pago_del_portal_es_el_mismo_componente(self):
        orden = self.pedido_para_pagar()
        _url, texto, arbol = self.pagina(orden.get_portal_url())
        ventana = arbol.xpath('//div[@id="modalaccept"]')
        self.assertEqual(len(ventana), 1)
        self.assertIn('Pagar tu pedido', self.texto(ventana[0].xpath('.//h4[contains(@class, "modal-title")]')[0]))
        total = ventana[0].xpath('.//*[contains(@class, "o_dcasa_pago_total_monto")]')
        self.assertEqual(len(total), 1)
        self.assertIn(f'{orden.amount_total:.2f}', self.texto(total[0]), 'el total, grande, arriba')
        # El mismo formulario y los mismos nombres que el de la tienda.
        self.assertEqual(len(ventana[0].xpath('.//form[@id="o_payment_form"]')), 1)
        radios = ventana[0].xpath('.//li[@name="o_payment_option"]//input[@name="o_payment_radio"]')
        self.assertGreaterEqual(len(radios), 2)
        for radio in radios:
            self.assertTrue(radio.get('data-payment-option-id'))
            self.assertTrue(radio.get('data-provider-code'))
        boton = ventana[0].xpath('.//button[@name="o_payment_submit_button"]')
        self.assertEqual(len(boton), 1)
        self.assertTrue(self.texto(boton[0]).startswith('Pagar'))
        self.assertIn(f'{orden.amount_total:.2f}', self.texto(boton[0]))
        self.assertEqual(len(ventana[0].xpath('.//p[contains(@class, "o_dcasa_pago_ayuda_wa")]')), 1)
        # Los iconos propios también aquí.
        self.assertIn('/website_dcasa/static/src/img/pago/', texto)

    def _pagar_con_yappy_en_la_tienda(self):
        orden = self.entrar_y_llenar_el_carrito()
        proveedor = self.env['payment.provider'].search([('name', '=', 'Yappy'), ('code', '=', 'custom')], limit=1)
        self.assertTrue(proveedor, 'Yappy lo deja la configuración de la tienda')
        self.make_jsonrpc_request(f'/shop/payment/transaction/{orden.id}', {
            'access_token': orden._portal_ensure_token(), 'provider_id': proveedor.id,
            'payment_method_id': proveedor.payment_method_ids[:1].id, 'token_id': None,
            'flow': 'direct', 'tokenization_requested': False, 'landing_route': '/shop/payment/validate',
            'is_validation': False})
        return orden

    def test_estado_del_pago_es_la_misma_pantalla_sin_menu_ni_pie(self):
        self._pagar_con_yappy_en_la_tienda()
        _url, texto, arbol = self.pagina('/payment/status')
        self.assertTrue(arbol.xpath('//div[contains(@class, "o_dcasa_pago_cabecera")]'))
        self.assertNotIn('o_dcasa_anuncios', texto)
        self.assertFalse(arbol.xpath('//footer'), 'sin el pie de la tienda')
        self.assertFalse(arbol.xpath('//header[@id="top"]'))
        self.assertTrue(arbol.xpath('//div[@name="o_payment_status"]'), 'el JavaScript del reloj sigue enganchado')
        self.assertIn('Estamos confirmando tu pago', texto)
        self.assertIn('Seguir sin esperar', texto)
        self.assertIn('o_dcasa_pago_ayuda_wa', texto)

    def test_la_confirmacion_dice_el_estado_del_pago_y_que_sigue(self):
        orden = self._pagar_con_yappy_en_la_tienda()
        url, texto, arbol = self.pagina('/shop/payment/validate')
        self.assertIn('/shop/confirmation', url)
        self.assertIn('¡Gracias por tu compra!', texto)
        nombre = self.texto(arbol.xpath('//div[@id="order_name"]')[0])
        self.assertIn(f'Pedido {orden.name}', nombre)
        estado = arbol.xpath('//p[contains(@class, "o_dcasa_pago_estado_titulo")]')
        self.assertEqual(len(estado), 1)
        self.assertIn('Esperando tu pago', self.texto(estado[0]))
        self.assertIn('Te escribimos por WhatsApp con el número de Yappy', texto)
        self.assertTrue(
            arbol.xpath('//a[contains(@class, "o_dcasa_pago_wa")][starts-with(@href, "https://wa.me/")]'))
        self.assertTrue(arbol.xpath('//a[@class="o_dcasa_pago_seguir"][@href="/shop"]'))
        self.assertFalse(arbol.xpath('//*[contains(@class, "o_dcasa_pago_reintentar")]'), 'no hay nada que reintentar')

    def test_si_el_pago_no_se_completo_hay_un_camino_de_vuelta(self):
        self._pagar_con_yappy_en_la_tienda()
        transaccion = self.env['payment.transaction'].search([], order='id desc', limit=1)
        transaccion._set_canceled()
        url, texto, arbol = self.pagina('/shop/payment/validate')
        self.assertIn('/shop/confirmation', url)
        estado = arbol.xpath('//p[contains(@class, "o_dcasa_pago_estado_titulo")]')
        self.assertEqual(len(estado), 1)
        self.assertIn('El pago no se completó', self.texto(estado[0]))
        reintentar = arbol.xpath('//p[contains(@class, "o_dcasa_pago_reintentar")]//a[@href="/shop/payment"]')
        self.assertEqual(len(reintentar), 1)
        self.assertIn('Intentar de nuevo', self.texto(reintentar[0]))
        self.assertTrue(
            arbol.xpath('//a[contains(@class, "btn-outline-primary")][contains(@class, "o_dcasa_pago_wa")]'),
            'con el pago sin completar, «Intentar de nuevo» es el único botón lleno')
