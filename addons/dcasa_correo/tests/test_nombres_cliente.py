"""F5: los correos de Odoo que listan productos (confirmación del pedido, carrito abandonado) los nombran en formato
título, como los lee el cliente; por dentro siguen en MAYÚSCULAS."""
from odoo.tests import TransactionCase, tagged

from ..nombres_correo import CAMBIOS, nombres_en_correos


@tagged('post_install', '-at_install')
class TestNombresEnLosCorreos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        producto = cls.env['product.product'].create({'name': 'CAMA DE METAL CON BAÚL', 'list_price': 100})
        cliente = cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA', 'email': 'cliente.correo@example.com'})
        # Un pedido de la tienda: el correo de confirmación lista los productos solo si viene del sitio.
        cls.orden = cls.env['sale.order'].create({
            'partner_id': cliente.id, 'website_id': cls.env.ref('website.default_website').id,
            'order_line': [(0, 0, {'product_id': producto.id})]})

    def test_las_plantillas_quedan_con_el_nombre_para_el_cliente(self):
        for xmlid, cambios in CAMBIOS.items():
            plantilla = self.env.ref(xmlid, raise_if_not_found=False)
            if not plantilla:
                continue
            cuerpo = plantilla.body_html
            for viejo, _nuevo in cambios:
                self.assertNotIn(viejo, cuerpo, xmlid)
            self.assertIn('_dcasa_nombre_cliente()', cuerpo, xmlid)
        self.assertFalse(nombres_en_correos(self.env), 'se puede repetir: la segunda vez no cambia nada')

    def test_la_confirmacion_del_pedido_nombra_en_formato_titulo(self):
        plantilla = self.env.ref('sale.mail_template_sale_confirmation')
        cuerpo = str(plantilla._render_field('body_html', self.orden.ids)[self.orden.id])
        self.assertIn('Cama de Metal con Baúl', cuerpo)
        self.assertNotIn('CAMA DE METAL CON BAÚL', cuerpo)
        self.assertIn('CAMA DE METAL CON BAÚL', self.orden.order_line.name, 'lo guardado no cambia')
