"""F5: los nombres se guardan en MAYÚSCULAS y el cliente los lee en formato título (``dcasa_base/nombres.py``)."""
from odoo.tests import TransactionCase, tagged

from ..models.nombres_cliente import CLAVE_CLIENTE
from ..nombres import nombre_en_mayusculas, nombre_para_cliente


@tagged('post_install', '-at_install')
class TestNombreParaCliente(TransactionCase):

    def assertNombres(self, casos):
        for guardado, para_cliente in casos:
            with self.subTest(guardado=guardado):
                self.assertEqual(nombre_para_cliente(guardado), para_cliente)

    def test_formato_titulo_con_preposiciones_en_minuscula(self):
        self.assertNombres([
            ('CAMA QUEEN TAPIZADA', 'Cama Queen Tapizada'),
            ('CAMA DE METAL CON BAÚL', 'Cama de Metal con Baúl'),
            ('MESA DE NOCHE PARA LA SALA Y EL CUARTO', 'Mesa de Noche para la Sala y el Cuarto'),
            ('DE LUJO SIN BRAZOS', 'De Lujo sin Brazos'),   # la primera palabra siempre con mayúscula
            ('Y TAMBIÉN', 'Y También'),
            ('SILLA O BANCO U OTOMANA', 'Silla o Banco u Otomana'),
        ])

    def test_tamanos(self):
        self.assertNombres([
            ('CAMA KING', 'Cama King'), ('CAMA QUEEN', 'Cama Queen'),
            ('TWIN Y FULL', 'Twin y Full'), ('CAMA TAPIZADA (King)', 'Cama Tapizada (King)'),
        ])

    def test_tildes_y_enie(self):
        self.assertNombres([
            ('SOFÁ SECCIONAL MILÁN', 'Sofá Seccional Milán'),
            ('MUÑECA ÑANDÚ PINGÜINO', 'Muñeca Ñandú Pingüino'),
            ('ÚNICO CAMIÓN ÍNTIMO', 'Único Camión Íntimo'),
        ])

    def test_codigos_y_numeros_quedan_como_estan(self):
        self.assertNombres([
            ('CAMA DR-1024', 'Cama DR-1024'),
            ('JUEGO DE SALA 4/6 Y 3/4', 'Juego de Sala 4/6 y 3/4'),
            ('[DC-K7M4PX] COLCHÓN KING', '[DC-K7M4PX] Colchón King'),
            ('[ABC] COLCHÓN', '[ABC] Colchón'),
            ('SOFÁ 3 PUESTOS 2X', 'Sofá 3 Puestos 2X'),
            ('A/C TV-LED', 'A/C TV-LED'),   # cortas con guion o barra: parecen código
            ('SOFÁ-CAMA', 'Sofá-Cama'),
        ])

    def test_medidas(self):
        self.assertNombres([
            ('BASE 160 X 200 CM', 'Base 160 x 200 cm'),
            ('CAMA QUEEN 1.5M X 2M', 'Cama Queen 1.5m x 2m'),
            ('COLCHÓN 160X200CM', 'Colchón 160x200cm'),
        ])

    def test_marca_y_siglas(self):
        self.assertNombres([
            ("COLCHÓN D'CASA KING", "Colchón D'CASA King"),
            ('COLCHÓN D’CASA', 'Colchón D’CASA'),
            ('MESA PARA TV EN MDF', 'Mesa para TV en MDF'),
            ('LÁMPARA LED USB', 'Lámpara LED USB'),
            ('SILLA PVC XL', 'Silla PVC XL'),
            ('SOFÁ EN L', 'Sofá en L'),
            ('SOFÁ EN U', 'Sofá en U'),
        ])

    def test_lineas_separadores_y_lo_que_ya_tiene_minusculas(self):
        self.assertNombres([
            ('CAMA TAPIZADA QUEEN – BLANCO', 'Cama Tapizada Queen – Blanco'),
            ('COLOR: DE LA CASA', 'Color: De la Casa'),
            ('CAMA KING\nColor: Gris\nMEDIDAS: 200 X 200 CM', 'Cama King\nColor: Gris\nMedidas: 200 x 200 cm'),
            ('Incluye luz NEÓN y control', 'Incluye luz NEÓN y control'),   # una palabra resaltada: se deja
            ('Cama SOFÁ (King)', 'Cama SOFÁ (King)'),
            ('Cama Queen Tapizada', 'Cama Queen Tapizada'),
            ("D'CASA", "D'CASA"),
        ])
        for vacio in ('', False, None):
            self.assertEqual(nombre_para_cliente(vacio), vacio)

    def test_ida_y_vuelta_con_lo_guardado(self):
        for nombre in ('Cama de Metal con Baúl', 'Sofá Seccional Milán', 'Mesa para TV en MDF'):
            self.assertEqual(nombre_para_cliente(nombre_en_mayusculas(nombre)), nombre)


@tagged('post_install', '-at_install')
class TestNombreClienteEnModelos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cama = cls.env['product.template'].create({
            'name': 'CAMA DE METAL CON BAÚL', 'default_code': 'PROV-777', 'list_price': 100})
        cls.variante = cls.cama.product_variant_id

    def test_por_dentro_mayusculas_para_el_cliente_titulo(self):
        self.assertEqual(self.cama.name, 'CAMA DE METAL CON BAÚL')
        self.assertEqual(self.variante.display_name, '[PROV-777] CAMA DE METAL CON BAÚL')
        self.assertEqual(self.cama._dcasa_nombre_cliente(), 'Cama de Metal con Baúl')
        self.assertEqual(self.variante._dcasa_nombre_cliente(), 'Cama de Metal con Baúl', 'sin la referencia')

    def test_display_name_con_la_clave_del_cliente(self):
        para_cliente = self.variante.with_context(**{CLAVE_CLIENTE: True})
        self.assertEqual(para_cliente.display_name, '[PROV-777] Cama de Metal con Baúl')
        self.assertEqual(self.variante.display_name, '[PROV-777] CAMA DE METAL CON BAÚL', 'sin la clave, igual')
        self.assertEqual(self.cama.with_context(**{CLAVE_CLIENTE: True}).display_name,
                         '[PROV-777] Cama de Metal con Baúl')

    def test_linea_de_pedido(self):
        cliente = self.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA'})
        orden = self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': [
            (0, 0, {'product_id': self.variante.id})]})
        linea = orden.order_line
        self.assertIn('CAMA DE METAL CON BAÚL', linea.name, 'lo guardado sigue en MAYÚSCULAS')
        self.assertIn('Cama de Metal con Baúl', linea._dcasa_nombre_cliente())
