"""rv_web, segunda vuelta (2026-11-20): ataques a la memoria de «Lo más buscado» (controllers/main.py:
``_CACHE_VITRINA``, ``_fichas_de_la_vitrina``).

Crecimiento sin límite con muchas combinaciones de idioma, tarifa, posición fiscal y sitio; objetos mutables compartidos
entre la memoria y la respuesta; dos personas con tarifa y carrito distintos; lo que pasa tras el minuto. Etiqueta
``rv_web``.
"""
from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.dcasa_brian_tienda.controllers import main as controlador
from odoo.addons.dcasa_brian_tienda.controllers.main import (
    MAX_CLAVES_CACHE_VITRINA,
    SEGUNDOS_CACHE_VITRINA,
    limpiar_cache_vitrina,
)
from odoo.tests import tagged

from .common import RAIZ, TiendaCase

VITRINA = f'{RAIZ}/vitrina'


@tagged('post_install', '-at_install')
class TestRvWeb2VitrinaCache(TiendaCase):

    def _falso(self, lang='es_419', tarifa=1, posicion=None, sitio=None):
        return SimpleNamespace(
            website=sitio or self.website, env=self.env, lang=SimpleNamespace(code=lang),
            pricelist=SimpleNamespace(id=tarifa) if tarifa is not None else None,
            fiscal_position=SimpleNamespace(id=posicion) if posicion is not None else None, cart=None)

    def test_la_memoria_nunca_pasa_del_tope_aunque_se_pidan_cientos_de_combinaciones(self):
        limpiar_cache_vitrina()
        api = controlador.DcasaBrianTiendaAPI()
        pico = 0
        for i in range(260):
            with patch.object(controlador, 'request', self._falso(lang=f'xx_{i % 7}', tarifa=i, posicion=i % 11)):
                api._fichas_de_la_vitrina()
            pico = max(pico, len(controlador._CACHE_VITRINA))
            self.assertLessEqual(len(controlador._CACHE_VITRINA), MAX_CLAVES_CACHE_VITRINA,
                                    f'tras {i + 1} combinaciones')
        self.assertGreater(pico, 10, 'la memoria sí se usó (si no, esta prueba no prueba nada)')

    def test_una_combinacion_repetida_no_vuelve_a_armar_y_dos_combinaciones_no_se_mezclan(self):
        limpiar_cache_vitrina()
        api = controlador.DcasaBrianTiendaAPI()
        with patch.object(controlador, 'request', self._falso(tarifa=1)):
            a1 = api._fichas_de_la_vitrina()
            self.env.flush_all()
            antes = self.env.cr.sql_log_count
            a2 = api._fichas_de_la_vitrina()
            self.assertEqual(self.env.cr.sql_log_count, antes, 'la segunda vez no toca la base')
            self.assertIs(a1, a2)
        with patch.object(controlador, 'request', self._falso(tarifa=2)):
            b = api._fichas_de_la_vitrina()
        with patch.object(controlador, 'request', self._falso(lang='en_US', tarifa=1)):
            c = api._fichas_de_la_vitrina()
        with patch.object(controlador, 'request', self._falso(tarifa=1, posicion=5)):
            d = api._fichas_de_la_vitrina()
        self.assertEqual(len(controlador._CACHE_VITRINA), 4, 'tarifa, idioma y posición fiscal separan las memorias')
        self.assertTrue(all(x is not a1 for x in (b, c, d)))

    def test_lo_que_se_devuelve_no_comparte_objetos_mutables_con_la_memoria(self):
        """Si un request cambia (en el lugar) algo de lo que devolvió ``_sugeridos``, la memoria no puede cambiar con
        él: los dicts de la respuesta son nuevos, pero sus listas y diccionarios internos tienen que serlo también."""
        limpiar_cache_vitrina()
        api = controlador.DcasaBrianTiendaAPI()
        with patch.object(controlador, 'request', self._falso()):
            sugeridos = api._sugeridos()
            guardado = {f['plantilla_id']: f for f in api._fichas_de_la_vitrina()}
        self.assertTrue(sugeridos)
        compartidos = []
        for ficha in sugeridos:
            original = guardado[ficha['plantilla_id']]
            for clave, valor in ficha.items():
                if isinstance(valor, (list, dict)) and valor is original.get(clave):
                    compartidos.append(clave)
        self.assertEqual(compartidos, [], 'estos valores de la respuesta SON los de la memoria')

    def test_dos_personas_con_tarifa_y_carrito_distintos_cada_una_ve_lo_suyo(self):
        """A pone el colchón en su carrito y B (otra sesión, con otra tarifa elegida) abre el chat: B no pierde el
        colchón ni ve el carrito de A, y la memoria queda con una clave por tarifa."""
        self.colchon.website_sequence = -99999
        limpiar_cache_vitrina()
        tarifa = self.env['product.pricelist'].create({
            'name': 'Tarifa rv_web2', 'selectable': True, 'website_id': self.website.id,
            'item_ids': [(0, 0, {'applied_on': '3_global', 'compute_price': 'percentage', 'percent_price': 50})]})
        a = [p['plantilla_id'] for p in self.url_open(VITRINA).json()['productos']]
        self.assertEqual(a[0], self.colchon.id)
        agregado = self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        self.assertTrue(agregado.json()['ok'], agregado.text)
        con_carrito = [p['plantilla_id'] for p in self.url_open(VITRINA).json()['productos']]
        self.assertNotIn(self.colchon.id, con_carrito)
        self.otra_sesion()
        self.url_open(f'/shop?pricelist={tarifa.id}')
        b = self.url_open(VITRINA).json()['productos']
        self.assertEqual([p['plantilla_id'] for p in b], a, 'B ve lo común, sin el carrito de A')
        claves = list(controlador._CACHE_VITRINA)
        self.assertGreaterEqual(len(claves), 1)
        # Las fichas no dependen de la tarifa (el precio de la tarjeta es el de lista, con o sin memoria): lo que ve B
        # es lo mismo que vería sin la memoria.
        limpiar_cache_vitrina()
        sin_memoria = self.url_open(VITRINA).json()['productos']
        self.assertEqual(b, sin_memoria, 'con o sin memoria, B ve lo mismo')

    def test_pasado_el_minuto_lo_despublicado_ya_no_sale(self):
        self.colchon.website_sequence = -99999
        limpiar_cache_vitrina()
        reloj = {'t': 5000.0}
        with patch.object(controlador.time, 'monotonic', side_effect=lambda: reloj['t']):
            self.assertEqual(self.url_open(VITRINA).json()['productos'][0]['plantilla_id'], self.colchon.id)
            self.colchon.is_published = False
            self.env.flush_all()
            reloj['t'] += SEGUNDOS_CACHE_VITRINA - 0.5
            self.assertEqual(self.url_open(VITRINA).json()['productos'][0]['plantilla_id'], self.colchon.id,
                             'dentro del minuto se ve la tarjeta de antes')
            reloj['t'] += 1
            self.assertNotIn(self.colchon.id, [p['plantilla_id'] for p in self.url_open(VITRINA).json()['productos']],
                             'pasado el minuto, lo despublicado sale')
