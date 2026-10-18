"""El catálogo es público: nunca lleva la referencia del proveedor, el costo, el código de barras ni nada interno."""
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import MetaComun, leer_csv


@tagged('post_install', '-at_install')
class TestFeedPrivacidad(MetaComun, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        proveedor = cls.env['res.partner'].create({
            'name': 'Proveedor Secreto S.A.', 'email': 'compras@proveedor.example'})
        cls.producto = cls._producto(
            'Ropero prueba privacidad', 250.0,
            default_code='PROV-XYZ-123',
            standard_price=77.77,
            barcode='7701234567890',
            description='NOTA INTERNA de bodega',
            description_purchase='Texto de compra reservado',
            description_picking='Texto de entrega reservado',
            seller_ids=[Command.create({
                'partner_id': proveedor.id, 'product_code': 'SUP-CODE-999',
                'product_name': 'Nombre del proveedor reservado', 'price': 55.55,
            })],
        )

    def test_ningun_dato_interno_en_el_csv(self):
        contenido = self._csv()
        texto = contenido.decode('utf-8')
        self.assertIn(str(self.producto.product_variant_id.id), [f['id'] for f in leer_csv(contenido)])
        for secreto in ('PROV-XYZ-123', '77.77', '7701234567890', 'SUP-CODE-999', 'Nombre del proveedor reservado',
                        '55.55', 'Proveedor Secreto', 'compras@proveedor.example', 'NOTA INTERNA',
                        'Texto de compra reservado', 'Texto de entrega reservado'):
            with self.subTest(secreto):
                self.assertNotIn(secreto, texto)

    def test_sin_columnas_de_identificadores_ni_costo(self):
        cabecera = self._csv().decode('utf-8').split('\n', 1)[0].split(',')
        for columna in ('gtin', 'mpn', 'cost', 'standard_price', 'default_code', 'barcode', 'identifier_exists'):
            self.assertNotIn(columna, cabecera)

    def test_el_id_nunca_es_la_referencia_ni_el_codigo_publico(self):
        [fila] = [f for f in self._filas() if f['id'] == str(self.producto.product_variant_id.id)]
        self.assertNotEqual(fila['id'], self.producto.default_code)
        self.assertNotEqual(fila['id'], self.producto.dcasa_codigo_publico)
        self.assertEqual(fila['custom_label_4'], self.producto.dcasa_codigo_publico, 'el código público sí, a la vista')
        self.assertNotIn('PROV-XYZ-123', fila['title'])
