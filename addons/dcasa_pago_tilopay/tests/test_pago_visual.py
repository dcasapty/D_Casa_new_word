"""Lo de Tilopay en el pago rediseñado («el pago como un checkout moderno»): la fila de Tilopay en la ventana «Pagar tu
pedido» del portal con su ayuda, y la línea con candado bajo el botón que dice qué pasa con los datos de la tarjeta.
Los íconos de Visa y Mastercard y el botón «Pagar $ monto» los pone website_dcasa (si está instalado)."""
import re

from lxml import html as lxml_html

from odoo.tests import HttpCase, tagged

from .common import ComunTilopay, SimuladorTilopay

LINEA_DE_SEGURIDAD = "Pagas en la página segura de Tilopay; D'CASA nunca ve los datos de tu tarjeta."


@tagged('post_install', '-at_install')
class TestTilopayEnElPagoRedisenado(ComunTilopay, HttpCase):

    def _portal(self):
        pedido = self.pedido()
        pedido.write({'require_payment': True, 'prepayment_percent': 1.0})
        pedido.action_quotation_sent()
        respuesta = self.url_open(pedido.get_portal_url())
        self.assertEqual(respuesta.status_code, 200)
        return pedido, respuesta.text, lxml_html.fromstring(respuesta.text)

    def _con_website_dcasa(self):
        return bool(self.env['ir.module.module'].search_count(
            [('name', '=', 'website_dcasa'), ('state', '=', 'installed')]))

    @staticmethod
    def _texto(nodo):
        return re.sub(r'\s+', ' ', nodo.text_content()).strip()

    def test_la_fila_de_tilopay_conserva_lo_que_lee_el_javascript_y_lleva_su_ayuda(self):
        _pedido, _texto_html, arbol = self._portal()
        radio = arbol.xpath(
            '//form[@id="o_payment_form"]//input[@name="o_payment_radio"][@data-provider-code="tilopay"]')
        self.assertEqual(len(radio), 1, 'Tilopay sale como una sola opción')
        self.assertEqual(radio[0].get('data-payment-method-code'), 'tilopay')
        self.assertEqual(radio[0].get('data-payment-option-type'), 'payment_method')
        self.assertEqual(radio[0].get('data-payment-option-id'), str(self.metodo.id))
        fila = radio[0].xpath('ancestor::li[@name="o_payment_option"]')[0]
        etiqueta = fila.xpath('.//label[contains(@class, "o_payment_option_label")]')
        self.assertEqual(self._texto(etiqueta[0]), 'Tarjeta de crédito o débito')
        self.assertIn('Pago seguro con tarjeta', self._texto(fila), 'su ayuda vive dentro de su fila')

    def test_la_linea_de_seguridad_esta_bajo_el_boton_de_pagar(self):
        _pedido, _texto_html, arbol = self._portal()
        formulario = arbol.xpath('//form[@id="o_payment_form"]')[0]
        notas = formulario.xpath('.//p[@data-dcasa-proveedor="tilopay"]')
        self.assertEqual(len(notas), 1)
        self.assertEqual(self._texto(notas[0]), LINEA_DE_SEGURIDAD)
        self.assertIn('o_dcasa_pago_nota', notas[0].get('class'))
        anterior = notas[0].getprevious()
        self.assertEqual(anterior.get('name'), 'o_payment_submit_button', 'va justo debajo del botón')

    def test_los_estilos_solo_muestran_la_linea_con_tilopay_elegido(self):
        """Sin :has() no hay línea (la ayuda de la fila ya cuenta que se paga en la página de Tilopay); con :has(),
        solo cuando el radio de Tilopay está marcado. La prueba de Chrome (website_dcasa) lo mide en pantalla."""
        from pathlib import Path  # noqa: PLC0415
        css = (Path(__file__).resolve().parent.parent / 'static' / 'src' / 'scss' / 'tilopay.scss').read_text()
        self.assertIn('display: none', css)
        self.assertIn('[data-provider-code="tilopay"]:checked', css)
        self.assertNotIn('gradient', css)

    def test_los_mensajes_del_cliente_no_repiten_el_titulo_del_estado(self):
        proveedor = self.proveedor.with_context(lang='es_419')
        self.assertNotIn('¡Pago recibido!', str(proveedor.done_msg), 'el título «Pago recibido» lo pone la pantalla')
        self.assertNotIn('El pago no se completó', str(proveedor.cancel_msg))
        self.assertIn('Tu pedido sigue guardado', str(proveedor.cancel_msg))

    def test_con_el_sitio_de_d_casa_el_estado_del_pago_espera_con_su_titulo(self):
        if not self._con_website_dcasa():
            self.skipTest('website_dcasa no está instalado')
        pedido = self.pedido()
        self.authenticate(None, None)
        with SimuladorTilopay():
            valores = self.make_jsonrpc_request(f'/my/orders/{pedido.id}/transaction', {
                'access_token': pedido._portal_ensure_token(), 'provider_id': self.proveedor.id,
                'payment_method_id': self.metodo.id, 'token_id': None, 'amount': pedido.amount_total,
                'flow': 'redirect', 'tokenization_requested': False, 'landing_route': pedido.get_portal_url(),
                'is_validation': False})
            self.assertTrue(valores)
            respuesta = self.url_open('/payment/status')
        self.assertEqual(respuesta.status_code, 200)
        arbol = lxml_html.fromstring(respuesta.text)
        self.assertTrue(arbol.xpath('//div[contains(@class, "o_dcasa_pago_cabecera")]'))
        self.assertTrue(arbol.xpath('//div[@name="o_payment_status"]'), 'el reloj de la página sigue enganchado')
        self.assertIn('Estamos confirmando tu pago', respuesta.text)
        self.assertIn('Seguir sin esperar', respuesta.text)
