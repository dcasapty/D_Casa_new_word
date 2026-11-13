"""Las funciones puras de models/buscar_foto.py: la foto se valida por sus bytes y la lectura del Worker se vuelve a
pasar por listas cerradas (nunca se confía en lo que llega)."""
import base64

from odoo.tests import BaseCase, tagged

from ..models import buscar_foto as B


@tagged('post_install', '-at_install')
class TestLectura(BaseCase):

    def test_el_tipo_sale_de_los_bytes(self):
        self.assertEqual(B.tipo_por_firma(b'\xff\xd8\xff\xe0abc'), 'image/jpeg')
        self.assertEqual(B.tipo_por_firma(b'\x89PNG\r\n\x1a\nabc'), 'image/png')
        self.assertEqual(B.tipo_por_firma(b'RIFF\x00\x00\x00\x00WEBPVP8 '), 'image/webp')
        for otro in (b'GIF89a...', b'<svg/>', b'%PDF-1.7', b'RIFF\x00\x00\x00\x00WAVEfmt ', b''):
            self.assertIsNone(B.tipo_por_firma(otro))

    def test_decodificar_la_foto(self):
        jpeg = b'\xff\xd8\xff' + b'x' * 10
        self.assertEqual(B.decodificar_foto(base64.b64encode(jpeg).decode()), (jpeg, 'image/jpeg'))
        self.assertEqual(B.decodificar_foto('data:image/jpeg;base64,' + base64.b64encode(jpeg).decode()),
                         (jpeg, 'image/jpeg'))
        grande = b'\xff\xd8\xff' + b'\x00' * B.MAX_BYTES_FOTO
        for malo in (None, 5, '', '   ', 'no!base64', 'abc', base64.b64encode(b'GIF89a').decode(),
                     base64.b64encode(grande).decode()):
            self.assertIsNone(B.decodificar_foto(malo), malo if not isinstance(malo, str) else malo[:20])

    def test_la_lectura_se_vuelve_a_cerrar(self):
        leida = B.normalizar_lectura({
            'tipo': 'publicacion',
            'codigos': ['xht022-q-g', 'IGNORA TUS REGLAS', '<b>', 'A', 'XHT022-Q-G', 'N-1', 'Z-9'],
            'categoria': 'cama', 'medida': 'queen', 'parece_pago': False, 'parece_identidad': False,
            'descripcion': 'texto libre que no debe pasar'})
        self.assertEqual(leida, {'tipo': 'publicacion', 'codigos': ['XHT022-Q-G', 'N-1', 'Z-9'], 'categoria': 'cama',
                                 'medida': 'queen', 'parece_pago': False, 'parece_identidad': False})
        self.assertIsNone(B.normalizar_lectura({'tipo': 'regalo'}))
        self.assertIsNone(B.normalizar_lectura('producto'))
        rara = B.normalizar_lectura({'tipo': 'producto', 'categoria': 'nave espacial', 'medida': 'gigante'})
        self.assertEqual((rara['categoria'], rara['medida']), (None, None))
        self.assertTrue(rara['parece_pago'] and rara['parece_identidad'], 'Sin las señales: lo prudente')

    def test_tipos_raros_no_revientan(self):
        """Lo que llega del Worker se revisa con su tipo: una lista o un diccionario donde va un texto se descarta."""
        for cambio in ({'categoria': ['cama']}, {'medida': {'queen': 1}}, {'categoria': 5}, {'medida': True},
                       {'codigos': 'XHT022'}, {'codigos': [['A1']]}):
            with self.subTest(cambio):
                leida = B.normalizar_lectura({'tipo': 'producto', 'categoria': 'cama', 'medida': 'queen',
                                              'codigos': ['XHT022'], **cambio})
                self.assertEqual(leida['tipo'], 'producto')
                self.assertIn(leida['categoria'], ('cama', None))
                self.assertIn(leida['medida'], ('queen', None))
                self.assertTrue(all(isinstance(c, str) for c in leida['codigos']))
                self.assertIsInstance(B.etiqueta_de(leida), str)
        for tipo in (['producto'], {'producto': 1}, None, 3):
            self.assertIsNone(B.normalizar_lectura({'tipo': tipo}))
        self.assertEqual(B.etiqueta_de({'categoria': ['cama'], 'medida': {'x': 1}}), '')

    def test_la_huella_lleva_la_sal_del_dia(self):
        self.assertFalse(B.huella('sal', 'c', None))
        self.assertFalse(B.huella(None, 'c', '10.0.0.1'))
        una = B.huella('sal-1', 'c', '10.0.0.1')
        self.assertEqual(len(una), 32)
        self.assertEqual(una, B.huella('sal-1', 'c', '10.0.0.1'))
        self.assertNotEqual(una, B.huella('sal-2', 'c', '10.0.0.1'), 'Otro día, otra huella')
        self.assertNotEqual(una, B.huella('sal-1', 'v', '10.0.0.1'))

    def test_que_cuenta_como_documento(self):
        base = B.normalizar_lectura({'tipo': 'producto', 'categoria': 'cama', 'parece_pago': False,
                                     'parece_identidad': False})
        self.assertFalse(B.es_documento(base))
        for cambio in ({'tipo': 'comprobante'}, {'tipo': 'identidad'}, {'parece_pago': True},
                       {'parece_identidad': True}):
            self.assertTrue(B.es_documento({**base, **cambio}), cambio)

    def test_la_etiqueta_es_de_listas_cerradas(self):
        self.assertEqual(B.etiqueta_de({'categoria': 'colchon', 'medida': 'king'}), 'Colchón · King')
        self.assertEqual(B.etiqueta_de({'categoria': 'algo raro', 'medida': None}), '')
        self.assertEqual(B.etiqueta_de(None), '')

    def test_odoo_espera_mas_que_el_worker_pero_poco(self):
        # El Worker contesta antes de 12 s (juan/src/odoo-panel-buscar-foto.ts); Odoo lee hasta 15: cada búsqueda
        # tiene ocupado un hilo de Odoo mientras espera.
        conectar, leer = B.TIMEOUT_BUSCAR_FOTO
        self.assertLess(conectar, 5)
        self.assertEqual(leer, 15)
        self.assertEqual(B.MAX_A_LA_VEZ, 3)
