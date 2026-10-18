"""La caché: el CSV se arma una vez y solo se vuelve a armar si algo cambió (o pasó un día)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.exceptions import LockError
from odoo.tests import TransactionCase, tagged

from .common import MetaComun, leer_csv


@tagged('post_install', '-at_install')
class TestFeedCache(MetaComun, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mesa = cls._producto('Mesa caché prueba Meta', 120.0)
        cls.silla = cls._producto('Silla caché prueba Meta', 45.0)

    def setUp(self):
        super().setUp()
        self.armados = 0
        Feed = type(self.env['product.feed'])
        original = Feed._dcasa_meta_csv

        def contar(feed):
            self.armados += 1
            return original(feed)

        patcher = patch.object(Feed, '_dcasa_meta_csv', contar)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _servir(self):
        with MockRequest(self.env, website=self.website):
            return leer_csv(self.feed.sudo()._dcasa_meta_servir())

    def _fila(self, filas, plantilla):
        return next((f for f in filas if f['id'] == str(plantilla.product_variant_id.id)), None)

    def test_la_segunda_peticion_no_vuelve_a_armar(self):
        primera = self._servir()
        self.assertEqual(self.armados, 1)
        self.assertTrue(self.feed.feed_cache)
        segunda = self._servir()
        self.assertEqual(self.armados, 1, 'nada cambió: se sirve el guardado')
        self.assertEqual(primera, segunda)

    def test_cambiar_un_precio_vuelve_a_armar(self):
        self._servir()
        self.mesa.list_price = 130.0
        self._despues(self.mesa)
        filas = self._servir()
        self.assertEqual(self.armados, 2)
        self.assertEqual(self._fila(filas, self.mesa)['price'], '130.00 USD')

    def test_despublicar_vuelve_a_armar(self):
        self._servir()
        self.silla.is_published = False
        self._despues(self.silla)
        filas = self._servir()
        self.assertEqual(self.armados, 2)
        self.assertIsNone(self._fila(filas, self.silla))

    def test_marcar_una_campana_vuelve_a_armar(self):
        self._servir()
        campana = self.env['dcasa.meta.campana'].create({'name': 'Regreso a clases'})
        self.mesa.dcasa_meta_campana_id = campana
        self._despues(self.mesa)
        filas = self._servir()
        self.assertEqual(self.armados, 2)
        self.assertEqual(self._fila(filas, self.mesa)['custom_label_1'], 'regreso_a_clases')
        # Archivar la campaña (otra tabla) también se nota.
        campana.active = False
        self._despues(campana)
        filas = self._servir()
        self.assertEqual(self.armados, 3)
        self.assertEqual(self._fila(filas, self.mesa)['custom_label_1'], '')

    def test_no_anunciar_vuelve_a_armar(self):
        self._servir()
        self.silla.dcasa_meta_no_anunciar = True
        self._despues(self.silla)
        self.assertIsNone(self._fila(self._servir(), self.silla))
        self.assertEqual(self.armados, 2)

    def test_cambiar_el_feed_vuelve_a_armar(self):
        self._servir()
        self.feed.dcasa_marca = 'Otra marca'
        self.assertEqual(self._fila(self._servir(), self.mesa)['brand'], 'Otra marca')
        self.assertEqual(self.armados, 2)

    def test_a_un_dia_o_con_regenerar_ahora(self):
        self._servir()
        self.feed.cache_expiry = fields.Datetime.now() - timedelta(minutes=1)
        self._servir()
        self.assertEqual(self.armados, 2, 'vencido: se vuelve a armar')
        self.feed.action_invalidate_cache()
        self._servir()
        self.assertEqual(self.armados, 3, '«Regenerar ahora»')
        self._servir()
        self.assertEqual(self.armados, 3)

    def test_mientras_otra_peticion_lo_arma_se_sirve_el_anterior(self):
        anterior = self._servir()
        self.feed.action_invalidate_cache()
        with patch.object(type(self.feed), 'lock_for_update', side_effect=LockError('ocupado')):
            self.assertEqual(self._servir(), anterior)
            self.assertEqual(self.armados, 1)
            # Sin ninguno guardado, LockError: la ruta responde 503 con Retry-After.
            self.feed.feed_cache = False
            with self.assertRaises(LockError):
                self._servir()
