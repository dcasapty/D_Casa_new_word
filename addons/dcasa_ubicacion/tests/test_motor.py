"""El motor de la ubicación sin base de datos: qué punto vale, la zona con la tabla, el aviso de lo escrito contra el
punto, los botones del chofer y los enlaces de mapa (incluidos los cortos, con la red simulada)."""
import math

from odoo.tests import BaseCase, tagged

from ..motor import enlaces_mapa, geo

LUGARES = [
    {'nombre': 'Barrio Prueba', 'tipo': 'corregimiento', 'corr': 'Barrio Prueba', 'dist': 'La Chorrera',
     'prov': 'Panamá Oeste', 'lat': 8.9001, 'lon': -79.8001},
    {'nombre': 'Villa Prueba', 'tipo': 'barrio', 'corr': 'Barrio Prueba', 'dist': 'La Chorrera',
     'prov': 'Panamá Oeste', 'lat': 8.9011, 'lon': -79.8011},
    {'nombre': 'Hospital del Ejemplo', 'tipo': 'referencia', 'corr': 'Barrio Prueba', 'dist': 'La Chorrera',
     'prov': 'Panamá Oeste', 'lat': 8.9021, 'lon': -79.8021},
    {'nombre': 'Vista Inventada', 'tipo': 'corregimiento', 'corr': 'Vista Inventada', 'dist': 'Arraiján',
     'prov': 'Panamá Oeste', 'lat': 8.9304, 'lon': -79.8304},
    {'nombre': 'Sin coordenadas', 'tipo': 'barrio', 'corr': 'X', 'dist': 'Y', 'prov': 'Z', 'lat': None, 'lon': None},
]


@tagged('post_install', '-at_install')
class TestGeo(BaseCase):

    def test_un_punto_de_panama_se_redondea_y_lo_demas_no_vale(self):
        self.assertEqual(geo.punto(8.90123456789, -79.80123456789), (8.9012346, -79.8012346))
        for lat, lon in (('8.9', -79.8), (True, -79.8), (math.nan, -79.8), (20.0, -79.8), (8.9, 10.0),
                         (None, None), (10 ** 400, -79.8)):
            with self.subTest(lat=lat, lon=lon):
                self.assertIsNone(geo.punto(lat, lon))

    def test_la_precision_del_gps_y_que_tan_fiable_es(self):
        self.assertEqual(geo.precision_m(12.4), 12)
        self.assertIsNone(geo.precision_m(-1))
        self.assertIsNone(geo.precision_m('12'))
        self.assertTrue(geo.es_confiable('gps', 40))
        self.assertFalse(geo.es_confiable('gps', 350), 'GPS con más de 100 m de error: hay que mover el pin')
        self.assertTrue(geo.es_confiable('pin'))
        self.assertTrue(geo.es_confiable('whatsapp'))
        self.assertFalse(geo.es_confiable('busqueda'))
        self.assertFalse(geo.es_confiable('escrita'))
        self.assertEqual(geo.etiqueta('gps', 12), 'Ubicación del teléfono (±12 m)')
        self.assertEqual(geo.etiqueta('escrita'), 'Escrita a mano')

    def test_los_dos_botones_del_chofer(self):
        self.assertEqual(geo.enlaces(8.9, -79.8), {
            'waze': 'https://waze.com/ul?ll=8.9000000%2C-79.8000000&navigate=yes',
            'google': 'https://www.google.com/maps/dir/?api=1&destination=8.9000000%2C-79.8000000',
        })

    def test_la_zona_sale_de_la_tabla(self):
        zona = geo.deducir_zona(LUGARES, 8.9012, -79.8013)
        self.assertEqual(LUGARES[zona['precio']]['nombre'], 'Villa Prueba')
        self.assertLess(zona['precio_m'], 50)
        self.assertEqual((zona['barriada'], zona['corregimiento'], zona['distrito'], zona['provincia']),
                         ('Villa Prueba', 'Barrio Prueba', 'La Chorrera', 'Panamá Oeste'))
        self.assertEqual(geo.zona_texto(zona), 'Villa Prueba · Barrio Prueba · La Chorrera · Panamá Oeste')
        self.assertTrue(geo.en_cobertura(zona))

    def test_lejos_de_todo_no_hay_precio_ni_cobertura(self):
        # A unos 9 km de Vista Inventada: sin lugar que ponga precio (3 km), pero todavía en la cobertura (25 km).
        zona = geo.deducir_zona(LUGARES, 8.98, -79.89)
        self.assertIsNone(zona['precio'])
        self.assertEqual(zona['distrito'], 'Arraiján')
        self.assertTrue(geo.en_cobertura(zona))
        # En el Caribe, lejos de todo: con la tabla cargada, no es un punto de entrega.
        lejos = geo.deducir_zona(LUGARES, 9.6, -82.8)
        self.assertIsNone(lejos['cerca_m'])
        self.assertTrue(lejos['tabla'])
        self.assertFalse(geo.en_cobertura(lejos))
        # Sin tabla (instalación nueva) no se puede saber: vale el recuadro.
        self.assertTrue(geo.en_cobertura(geo.deducir_zona([], 9.6, -82.8)))

    def test_lo_escrito_contra_el_punto(self):
        zona = {'distrito': 'La Chorrera'}
        distritos = ['La Chorrera', 'Arraiján', 'San Miguelito']
        aviso = geo.aviso_de_cruce('Calle 5, casa 12, Arraijan', zona, distritos)
        self.assertIn('está en La Chorrera', aviso)
        self.assertIn('escribió Arraiján', aviso)
        self.assertEqual(geo.aviso_de_cruce('Calle 5, LA CHORRERA', zona, distritos), '')
        self.assertEqual(geo.aviso_de_cruce('Calle 5, casa 12', zona, distritos), '',
                         'sin distrito escrito no hay aviso')
        self.assertEqual(geo.aviso_de_cruce('Arraiján', {'distrito': ''}, distritos), '')

    def test_el_secreto_se_guarda_como_huella(self):
        token = geo.token_nuevo()
        self.assertGreaterEqual(len(token), 20)
        self.assertEqual(len(geo.huella(token)), 64)
        self.assertNotIn(token, geo.huella(token))
        self.assertNotEqual(geo.token_nuevo(), token)


@tagged('post_install', '-at_install')
class TestEnlacesDeMapa(BaseCase):

    def test_enlaces_largos(self):
        casos = {
            'https://www.google.com/maps/@8.9012345,-79.8012345,17z': (8.9012345, -79.8012345),
            'https://www.google.com/maps/place/Algo/@8.95,-79.6,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d8.9012345!4d-79.8012345':
                (8.9012345, -79.8012345),
            'https://maps.google.com/?q=8.9012345,-79.8012345': (8.9012345, -79.8012345),
            'https://www.google.com/maps/search/?api=1&query=8.9,-79.8': (8.9, -79.8),
            'https://www.google.com/maps/dir/?api=1&destination=8.9%2C-79.8': (8.9, -79.8),
            'https://www.google.com/maps/search/8.9012,+-79.8012': (8.9012, -79.8012),   # «+» es un espacio
            'https://waze.com/ul?ll=8.9012345%2C-79.8012345&navigate=yes': (8.9012345, -79.8012345),
            'https://ul.waze.com/ul?ll=8.9,-79.8': (8.9, -79.8),
            'https://maps.apple.com/?ll=8.9,-79.8&q=Casa': (8.9, -79.8),
        }
        for enlace, esperado in casos.items():
            with self.subTest(enlace=enlace):
                self.assertEqual(enlaces_mapa.coordenadas_sin_red(enlace), esperado)

    def test_lo_que_no_se_adivina(self):
        for enlace in ('https://maps.google.com/?q=Super+99+Brisas', 'https://www.google.com/maps/@40.4,-3.7,17z',
                       'https://ejemplo.com/maps/@8.9,-79.8,17z', 'ftp://maps.google.com/?q=8.9,-79.8',
                       'https://waze.com/ul?q=Super%2099', 'no es un enlace', None):
            with self.subTest(enlace=enlace):
                self.assertIsNone(enlaces_mapa.coordenadas_sin_red(enlace))

    def test_el_enlace_dentro_de_un_mensaje(self):
        texto = 'Hola, aquí estoy: https://maps.google.com/?q=8.9,-79.8. Gracias!'
        self.assertEqual(enlaces_mapa.coordenadas(texto), (8.9, -79.8))

    def test_los_enlaces_cortos_se_siguen_solo_hacia_google(self):
        saltos = {
            'https://maps.app.goo.gl/abc123': 'https://www.google.com/maps/place/X/@8.9,-79.8,17z/data=!3d8.9012!4d-79.8012',
        }
        pedidos = []

        def pedir(url, espera):
            pedidos.append(url)
            return saltos.get(url)

        self.assertEqual(enlaces_mapa.coordenadas('https://maps.app.goo.gl/abc123', resolver_cortos=True, pedir=pedir),
                         (8.9012, -79.8012))
        self.assertIsNone(enlaces_mapa.coordenadas('https://maps.app.goo.gl/abc123', pedir=pedir),
                          'sin permiso para resolver, un corto no se sigue')

        # Una redirección a otro sitio, a http o un círculo sin fin: no.
        for destino in ('https://malo.example.com/maps/@8.9,-79.8,17z', 'http://www.google.com/maps/@8.9,-79.8,17z'):
            with self.subTest(destino=destino):
                self.assertIsNone(enlaces_mapa.resolver('https://maps.app.goo.gl/x', pedir=lambda u, e, d=destino: d))
        vueltas = []
        self.assertIsNone(enlaces_mapa.resolver(
            'https://maps.app.goo.gl/x', pedir=lambda u, e: vueltas.append(u) or 'https://maps.app.goo.gl/x'))
        self.assertEqual(len(vueltas), enlaces_mapa.MAX_SALTOS)
        # Un host que no es de mapas cortos no se pide nunca.
        pedidos.clear()
        self.assertIsNone(enlaces_mapa.coordenadas('https://bit.ly/abc', resolver_cortos=True, pedir=pedir))
        self.assertEqual(pedidos, [])

    def test_un_enlace_disfrazado_no_hace_pedir_a_otra_maquina(self):
        # Auditoría 1: urlsplit veía «maps.app.goo.gl» y requests se conectaba a 127.0.0.1:9999.
        pedidos = []

        def pedir(url, espera):
            pedidos.append(url)
            return 'https://www.google.com/maps/@8.9012,-79.8012,17z'

        for disfrazado in ('http://127.0.0.1:9999\\@maps.app.goo.gl/x', 'https://usuario@maps.app.goo.gl/x',
                           'https://maps.app.goo.gl:8443/x', 'https://maps.app.goo.gl/x y', 'ftp://maps.app.goo.gl/x'):
            with self.subTest(enlace=disfrazado):
                self.assertIsNone(enlaces_mapa.resolver(disfrazado, pedir=pedir))
        self.assertEqual(pedidos, [], 'ninguno llega a pedirse')
        # Un enlace corto en http se pide en https; la «@» del camino de Google sí vale.
        self.assertEqual(enlaces_mapa.resolver('http://maps.app.goo.gl/x', pedir=pedir),
                         'https://www.google.com/maps/@8.9012,-79.8012,17z')
        self.assertEqual(pedidos, ['https://maps.app.goo.gl/x'])
