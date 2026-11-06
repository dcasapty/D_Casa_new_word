"""El motor de envíos, sin base de datos: da lo mismo que el JavaScript del HTML de la propuesta.

Los esperados (``datos/esperados_motor.json``) salieron de correr el JavaScript del propio ``envios-dcasa.html`` en node
sobre el fixture sintético (``node scripts/envios/paridad.mjs``, ver docs/ENVIOS.md): las búsquedas (los primeros 10
lugares, el total y las sugerencias), cada tarjeta (chips, zona, precio, desglose, ruta y texto para el cliente), una
tabla de km → precio con 8 tarifas distintas, los tramos y los textos de la regla."""
import json
import math

from odoo.tests import BaseCase, tagged

from ..motor import archivo, buscador, tarifa, tarjeta, texto
from .common import DATOS, como_html, fixture


def tarjeta_como_el_html(datos):
    """La tarjeta del motor con la forma en que paridad.mjs saca la del HTML."""
    clases = {'tipo': 'cat', 'revisar': 'revisar', 'aparte': 'aparte', 'mano': 'google'}
    salida = {'chips': [[clases[c['clase']], c['texto']] for c in datos['chips']], 'zona': datos['zona'],
              'tambien': [t for t in (datos['tambien'], datos['nota']) if t], 'url': datos['url_mapa']}
    if datos['con_precio']:
        salida.update(total=datos['total_txt'], km=datos['km_txt'] + (' · Google' if datos['google'] else ''),
                      desglose=[f"{d['texto']} {d['monto']}" for d in datos['desglose']], copiar=datos['texto_cliente'])
    else:
        salida.update(total='Cotizar aparte', km=datos['km_txt'] or None, desglose=[], copiar=None)
    return salida


@tagged('post_install', '-at_install')
class TestMotorComoElHtml(BaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        datos = fixture()
        cls.lugares = datos['lugares'] + [{**lugar, 'agregado': True} for lugar in datos['agregados']]
        cls.ajustes = datos['ajustes']
        cls.consultas = json.loads((DATOS / 'consultas_motor.json').read_text(encoding='utf-8'))
        cls.esperados = json.loads((DATOS / 'esperados_motor.json').read_text(encoding='utf-8'))
        cls.indice = buscador.Indice(cls.lugares)
        cls.tarifa = tarifa.Tarifa(cls.ajustes)
        cls.variantes = {v['nombre']: v.get('cambios') or {} for v in cls.consultas['variantes']}

    def con_variante(self, nombre):
        return tarifa.Tarifa({**json.loads(json.dumps(self.ajustes)), **self.variantes[nombre]})

    def test_los_esperados_son_del_mismo_fixture(self):
        self.assertEqual(self.esperados['lugares'], len(self.lugares))
        self.assertGreaterEqual(len(self.esperados['busquedas']), 40)
        self.assertTrue(any(b['sugerencias'] for b in self.esperados['busquedas']), 'prueba «¿Quisiste decir…?»')

    def test_las_palabras_son_las_del_html(self):
        constantes = self.esperados['constantes']
        for nombre in ('ABREV', 'CAT_SIN', 'DIST_SIN', 'PROV_SIN', 'PRIORIDAD'):
            self.assertEqual(getattr(buscador, nombre), constantes[nombre], nombre)
        for nombre in ('VACIAS', 'GENERICAS'):
            self.assertEqual(sorted(getattr(buscador, nombre)), constantes[nombre], nombre)

    def test_cada_busqueda_da_lo_mismo_que_el_html(self):
        for esperado in self.esperados['busquedas']:
            with self.subTest(texto=esperado['texto'], tipo=esperado.get('tipo'), distrito=esperado.get('distrito')):
                posiciones = self.indice.buscar(esperado['texto'], esperado.get('tipo'), esperado.get('distrito'))
                self.assertEqual(posiciones[:10], esperado['top'])
                self.assertEqual(len(posiciones), esperado['total'])
                self.assertEqual([] if posiciones else self.indice.sugerir(esperado['texto']), esperado['sugerencias'])

    def test_cada_tarjeta_dice_lo_mismo_que_el_html(self):
        revisadas = 0
        for esperado in self.esperados['busquedas']:
            for posicion, del_html in zip(esperado['top'], esperado['tarjetas'], strict=True):
                with self.subTest(lugar=self.lugares[posicion]['nombre']):
                    self.assertEqual(tarjeta_como_el_html(tarjeta.tarjeta(self.lugares[posicion], self.tarifa)),
                                     del_html)
                revisadas += 1
        self.assertGreater(revisadas, 50)

    def test_cada_precio_da_lo_mismo_que_el_html(self):
        for precio in self.esperados['precios']:
            with self.subTest(variante=precio['variante'], km=precio['km'], peaje=precio['peaje']):
                cotizacion = self.con_variante(precio['variante']).cotizar(precio['km'], precio['peaje'])
                self.assertEqual(cotizacion['base'], precio['base'])
                self.assertEqual(cotizacion['extras'], precio['extras'])
                self.assertEqual(cotizacion['total'], precio['total'])
                self.assertEqual(texto.dinero(cotizacion['total']), precio['dinero'])
                self.assertEqual(texto.km_txt(precio['km']), precio['km_txt'])

    def test_los_tramos_y_la_regla_dicen_lo_mismo_que_el_html(self):
        for tramo in self.esperados['tramos']:
            with self.subTest(variante=tramo['variante']):
                t = self.con_variante(tramo['variante'])
                if tramo['tramos'] is not None:
                    self.assertEqual(t.tramos(), tramo['tramos'])
                self.assertEqual(''.join(f"{f['km_txt']}{f['precio_txt']}|" for f in t.tramos_para_mostrar()),
                                 tramo['mostrar'])
                self.assertEqual(t.nota_tramos(), tramo['nota'])
        for textos in self.esperados['textos']:
            with self.subTest(variante=textos['variante']):
                t = self.con_variante(textos['variante'])
                self.assertEqual(''.join(f'{f[1]}|' for f in t.regla()), textos['regla'])
                self.assertEqual(''.join(f"{e['texto']}|" for e in t.efecto()), textos['efecto'])
                self.assertEqual(t.formula_txt(), textos['formula'])

    def test_la_tarifa_de_prueba_en_numeros_redondos(self):
        """$10 de salida + $1 por km, mínimo $10, redondeado a $5 hacia arriba (cifras de juguete)."""
        t = self.tarifa
        self.assertEqual((t.salida(), t.por_km()), (10.0, 1.0))
        self.assertEqual([t.base(km) for km in (0, 1.2, 10, 15, 15.05, 90.7)], [10, 15, 20, 25, 30, 105])
        self.assertTrue(t.configurada)
        self.assertFalse(tarifa.Tarifa({}).configurada)


@tagged('post_install', '-at_install')
class TestMotorDetalles(BaseCase):

    def test_redondeos_de_javascript(self):
        self.assertEqual(texto.js_round(2.5), 3.0, 'Math.round: el medio va hacia arriba (round() de Python da 2)')
        self.assertEqual(texto.js_round(0.49999999999999994), 0.0)
        self.assertEqual(texto.js_round(-2.5), -2.0)
        self.assertEqual(texto.to_fixed(0.125, 2), '0.13')
        self.assertEqual(texto.to_fixed(1.005, 2), '1.00', 'toFixed mira el valor exacto (1.00499…)')
        self.assertEqual(texto.to_fixed(-0.0, 2), '0.00')
        self.assertEqual(texto.numero_js(15.0), '15')
        self.assertEqual(texto.numero_js(7.5), '7.5')
        self.assertEqual(texto.dinero(20), '$20')
        self.assertEqual(texto.dinero(20.004), '$20')
        self.assertEqual(texto.dinero(20.5), '$20.50')
        self.assertEqual(texto.dinero(1234), '$1,234')
        self.assertEqual(texto.km_txt(34.06), '34.1')
        self.assertEqual(texto.km_txt(7.0), '7')
        self.assertEqual(texto.km_txt(1234.5), '1,234.5')
        self.assertEqual(texto.encode_uri_component('Villa, Panamá (2)'), 'Villa%2C%20Panam%C3%A1%20(2)')

    def test_los_cargos_se_suman_al_total(self):
        """Se suman de izquierda a derecha, como ``reduce`` de JavaScript (no con ``sum()``, que en Python 3.12
        compensa los decimales)."""
        cargos = [{'nombre': n, 'como': 'viaje', 'monto': m, 'activo': True}
                  for n, m in (('a', 0.1), ('b', 0.2), ('c', 0.3))]
        t = tarifa.Tarifa({**fixture()['ajustes'], 'paso': 0, 'extras': cargos})
        self.assertEqual(t.cotizar(0)['total'], 10.6)

    def test_la_palabra_constructor_no_rompe_el_buscador(self):
        """En el HTML, buscar «constructor» se caía (``ABREV['constructor']`` es una función de JavaScript)."""
        indice = buscador.Indice([{'nombre': 'Constructor Prueba', 'tipo': 'referencia', 'cat': 'comercio',
                                   'dist': 'La Chorrera', 'prov': 'Panamá Oeste', 'km': 3, 'estado': 'ok'}])
        self.assertEqual(indice.buscar('constructor'), [0])

    def test_sin_tarifa_el_lugar_dice_sin_tarifa(self):
        lugar = fixture()['lugares'][14]
        datos = tarjeta.tarjeta(lugar, tarifa.Tarifa({}))
        self.assertFalse(datos['con_precio'])
        self.assertIn({'texto': 'sin tarifa', 'clase': 'aparte'}, datos['chips'])

    def test_un_nombre_con_emoji_cuenta_como_en_javascript(self):
        self.assertEqual(buscador.largo_js('Café 😀 Prueba'), 14)

    def test_la_distancia_entre_palabras(self):
        self.assertEqual(buscador.distancia('arraijan', 'arraijan', 2), 0)
        self.assertEqual(buscador.distancia('arraijan', 'arriajan', 2), 1, 'dos letras cambiadas de lugar = 1')
        self.assertEqual(buscador.distancia('golff', 'golf', 1), 1)
        self.assertEqual(buscador.distancia('chorrera', 'colon', 2), 3, 'pasado el tope dice tope + 1')

    def test_leer_el_archivo_en_html_y_en_json(self):
        datos = fixture()
        del_html = archivo.leer_archivo(como_html(datos).encode('utf-8'))
        del_json = archivo.leer_archivo(json.dumps(datos).encode('utf-8'))
        self.assertEqual(del_html, del_json)
        self.assertEqual(len(del_html[0]), 38)
        self.assertEqual(del_html[1]['minimo'], 10)
        self.assertEqual([a['nombre'] for a in del_html[2]], ['Finca Agregada'])
        solo_lista = archivo.leer_archivo(json.dumps(datos['lugares']).encode('utf-8'))
        self.assertEqual((len(solo_lista[0]), solo_lista[1], solo_lista[2]), (38, None, []))
        for malo in (b'\xff\xfe', b'<html>sin datos</html>', b'{"lugares": 3}', b'{roto',
                     b'<script id="lugares" type="application/json">[{</script>'):
            with self.subTest(malo=malo), self.assertRaises(archivo.ArchivoInvalido):
                archivo.leer_archivo(malo)

    def test_normalizar_un_lugar_del_archivo(self):
        limpio, motivo = archivo.normalizar_lugar({
            'nombre': '  Villa   Prueba ', 'tipo': 'barrio', 'dist': 'La Chorrera', 'km': 3.5, 'estado': 'ok',
            'alias': ['Otra, S. A.', 7, ' La villa '], 'lat': 8.9, 'lon': -79.8, 'peaje': True})
        self.assertIsNone(motivo)
        self.assertEqual((limpio['name'], limpio['alias'], limpio['km'], limpio['km_medido'], limpio['peaje']),
                         ('Villa Prueba', 'Otra, S. A.\nLa villa', 3.5, True, True))
        sin_km, _ = archivo.normalizar_lugar({'nombre': 'X', 'tipo': 'corregimiento', 'dist': 'D', 'km': None,
                                              'estado': 'raro', 'lat': 8.9})
        self.assertEqual((sin_km['km_medido'], sin_km['estado'], sin_km['lat'], sin_km['lon']),
                         (False, 'sin_dato', 0.0, 0.0))
        for malo, motivo in (({'tipo': 'barrio', 'dist': 'D'}, 'sin nombre'), ({'nombre': 'X', 'tipo': 'casa',
                             'dist': 'D'}, 'tipo desconocido'), ({'nombre': 'X', 'tipo': 'barrio'}, 'sin distrito'),
                             ('texto', 'no es un lugar')):
            self.assertEqual(archivo.normalizar_lugar(malo), (None, motivo))
        self.assertEqual(archivo.llave({'name': 'Villa  Prueba', 'tipo': 'barrio', 'dist': 'La Chorrera',
                                        'corr': 'Barrio Prueba'}),
                         archivo.llave({'name': 'VILLA PRUEBA', 'tipo': 'barrio', 'dist': 'la chorrera',
                                        'corr': 'barrio prueba'}))

    def test_la_tarifa_del_archivo_se_revisa(self):
        valores, cargos = archivo.normalizar_ajustes(fixture()['ajustes'])
        self.assertEqual((valores['minimo'], valores['ancla_b_km'], valores['paso'], valores['max_km']),
                         (10.0, 100.0, '5', 300.0))
        self.assertEqual([c['codigo'] for c in cargos], ['viatico', 'honorarios', 'peaje'])
        for cambio in ({'minimo': 'diez'}, {'anclaB': {'km': 5, 'precio': 110}}, {'paso': 3}, {'maxKm': 5},
                       {'extras': [{'como': 'raro'}]}, {'ajustePct': 500}):
            with self.subTest(cambio=cambio), self.assertRaises(archivo.ArchivoInvalido):
                archivo.normalizar_ajustes({**fixture()['ajustes'], **cambio})

    def test_los_numeros_raros_no_dan_precio(self):
        self.assertIsNone(archivo._numero(math.nan))
        self.assertIsNone(archivo._numero(True))
        self.assertIsNone(archivo._numero('3'))
