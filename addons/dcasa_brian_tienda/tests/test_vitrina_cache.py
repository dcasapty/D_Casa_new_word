"""«Lo más buscado» (``GET /dcasa/brian/v1/vitrina``, pública) con el chat ampliado de fábrica en la computadora.

La pide cada visita que abre el chat, no solo quien pulsa «ampliar» (revisión independiente, 2026-11-19: 91
consultas por llamada). Lo común (las fichas de los productos más buscados) se guarda un minuto en el proceso; lo de
cada persona (lo que ya tiene en su carrito) se aplica después y nunca entra a esa memoria. El carrito usa siempre lo
vivo.
"""
import logging
from unittest.mock import patch

import requests

from odoo.addons.dcasa_brian_tienda.controllers import main as controlador
from odoo.addons.dcasa_brian_tienda.controllers.main import SEGUNDOS_CACHE_VITRINA, limpiar_cache_vitrina
from odoo.tests import tagged

from .common import RAIZ, TiendaCase

_logger = logging.getLogger(__name__)
VITRINA = f'{RAIZ}/vitrina'


@tagged('post_install', '-at_install')
class TestVitrinaPublicaPocasConsultas(TiendaCase):

    def _consultas(self, ruta=VITRINA):
        self.env.flush_all()
        antes = self.env.cr.sql_log_count
        respuesta = self.url_open(ruta)
        return respuesta, self.env.cr.sql_log_count - antes

    def _plantillas(self, respuesta):
        return [p['plantilla_id'] for p in respuesta.json()['productos']]

    def test_la_vitrina_publica_cuesta_pocas_consultas_y_la_segunda_mucho_menos(self):
        self.url_open(VITRINA)            # calienta rutas y cachés de Odoo
        limpiar_cache_vitrina()
        primera, sin_memoria = self._consultas()
        segunda, con_memoria = self._consultas()
        self.assertEqual(primera.status_code, 200)
        self.assertTrue(primera.json()['ok'])
        self.assertEqual(primera.json(), segunda.json(), 'lo que se guarda es lo mismo que se armó')
        _logger.info('VITRINA consultas sin memoria=%s con memoria=%s productos=%s', sin_memoria, con_memoria,
                     len(primera.json()['productos']))
        self.assertLessEqual(sin_memoria, 120, f'armarla cuesta {sin_memoria} consultas')
        self.assertLessEqual(con_memoria * 2, sin_memoria,
                             f'la segunda llamada ({con_memoria}) tiene que costar menos de la mitad ({sin_memoria})')
        self.assertLessEqual(con_memoria, 40, f'la llamada con la memoria llena cuesta {con_memoria} consultas')
        # Un visitante no puede pedirla con otro método ni con basura en la ruta: no hay nada más que abrir.
        self.assertIn(self.url_open(VITRINA, data='{}').status_code, (404, 405))

    def test_lo_de_cada_persona_no_se_mezcla(self):
        """El carrito de una persona no le quita productos a otra ni queda guardado en la memoria."""
        self.colchon.website_sequence = -99999   # primero en «Lo más buscado»
        limpiar_cache_vitrina()
        anonima = self._plantillas(self.url_open(VITRINA))
        self.assertEqual(anonima[0], self.colchon.id)
        guardadas = sum(len(valor[1]) for valor in controlador._CACHE_VITRINA.values())
        # Esta persona pone el colchón en su carrito: a ella ya no se le sugiere…
        agregado = self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        self.assertTrue(agregado.json()['ok'], agregado.text)
        con_carrito = self._plantillas(self.url_open(VITRINA))
        self.assertNotIn(self.colchon.id, con_carrito)
        # …y a otra persona, que llega después y toma lo guardado, sí.
        self.opener = requests.Session()
        otra = self._plantillas(self.url_open(VITRINA))
        self.assertEqual(otra, anonima, 'la otra persona ve lo común, sin lo del carrito ajeno')
        self.assertEqual(sum(len(valor[1]) for valor in controlador._CACHE_VITRINA.values()), guardadas,
                         'lo guardado no cambió con el carrito de nadie')
        # Y una persona que llegó con el carrito vacío puede llenarlo y vaciarlo sin que la memoria se entere.
        for valor in controlador._CACHE_VITRINA.values():
            self.assertIn(self.colchon.id, [ficha['plantilla_id'] for ficha in valor[1]])

    def test_lo_guardado_dura_un_minuto_y_se_renueva(self):
        self.colchon.website_sequence = -99999
        limpiar_cache_vitrina()
        reloj = {'t': 1000.0}
        with patch.object(controlador.time, 'monotonic', side_effect=lambda: reloj['t']):
            primera = self.url_open(VITRINA).json()['productos']
            self.colchon.name = 'ZZBT COLCHÓN QUEEN RENOMBRADO'
            self.env.flush_all()
            reloj['t'] += SEGUNDOS_CACHE_VITRINA - 1
            todavia = self.url_open(VITRINA).json()['productos']
            self.assertEqual(todavia[0]['nombre'], primera[0]['nombre'], 'dentro del minuto se ve lo guardado')
            reloj['t'] += 2
            despues = self.url_open(VITRINA).json()['productos']
            self.assertEqual(despues[0]['nombre'], 'Zzbt Colchón Queen Renombrado',
                             'pasado el minuto se arma de nuevo con lo vivo')

    def test_lo_viejo_de_la_tarjeta_nunca_llega_al_carrito(self):
        """Un producto que dejó de venderse o cambió de precio puede verse viejo en la tarjeta hasta un minuto; pero
        agregar siempre revisa lo vivo (publicado, precio y existencia) y el carrito cobra lo de ahora."""
        self.colchon.website_sequence = -99999
        limpiar_cache_vitrina()
        antes = self.url_open(VITRINA).json()['productos'][0]
        self.assertEqual(antes['plantilla_id'], self.colchon.id)
        self.assertTrue(antes['agregable'])
        # El precio cambia y el producto se despublica: la tarjeta guardada sigue como estaba…
        self.colchon.list_price = 400.0
        self.colchon.is_published = False
        self.env.flush_all()
        guardada = self.url_open(VITRINA).json()['productos'][0]
        self.assertEqual(guardada['plantilla_id'], self.colchon.id, 'dentro del minuto la tarjeta se ve como estaba')
        # …pero «Agregar» no deja comprar lo que ya no se vende,
        agregado = self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        self.assertEqual(agregado.json(), {'ok': False, 'motivo': 'no_disponible'}, 'lo despublicado no se agrega')
        # y, vuelto a publicar, el carrito cobra el precio de AHORA, no el de la tarjeta guardada.
        self.colchon.is_published = True
        self.env.flush_all()
        agregado = self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        self.assertTrue(agregado.json()['ok'], agregado.text)
        linea = agregado.json()['carrito']['lineas'][0]
        self.assertEqual(linea['producto_id'], self.colchon.product_variant_id.id)
        total = agregado.json()['carrito']['total_texto']
        self.assertNotIn('278', total, 'el carrito no cobra el precio viejo de la tarjeta')
        self.assertIn('400', total, 'sino el vivo')
