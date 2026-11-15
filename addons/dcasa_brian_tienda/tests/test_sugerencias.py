"""Sugerencias del saludo con el catálogo (pedido de la dueña, 2026-11-15, «opción 2»): las dos categorías de la portada
con más productos publicados, con la palabra que escribiría un cliente («Camas», «Escritorios»), en la respuesta del
pase. Con empate, el orden de la portada; sin nada publicado, ninguna (la página usa las de fábrica)."""
from odoo import Command
from odoo.tests import tagged

from .common import TiendaCase


@tagged('post_install', '-at_install')
class TestSugerenciasDelSaludo(TiendaCase):

    def _publicar(self, clave, cuantos):
        categoria = self.env.ref(f'website_dcasa.public_category_{clave}')
        for i in range(cuantos):
            self.env['product.template'].create({
                'name': f'ZZSUG {clave} {i}', 'list_price': 10.0, 'sale_ok': True, 'is_published': True,
                'public_categ_ids': [Command.set(categoria.ids)]})

    def _sugerencias(self):
        respuesta = self.post('pase').json()
        self.assertTrue(respuesta['ok'], respuesta)
        return respuesta['sugerencias']

    def test_las_dos_categorias_con_mas_productos_con_palabras_de_cliente(self):
        Plantilla = self.env['product.template']
        Plantilla.search([('is_published', '=', True)]).write({'is_published': False})
        self._publicar('oficina', 3)
        self._publicar('recamaras', 2)
        self._publicar('salas', 1)
        self.assertEqual(self._sugerencias(), ['Escritorios', 'Camas'], 'Oficina y Recámaras, como las dice un cliente')
        self._publicar('salas', 3)
        self.assertEqual(self._sugerencias(), ['Salas', 'Escritorios'], 'cambia sola al publicar más')
        self._publicar('oficina', 1)
        self.assertEqual(self._sugerencias(), ['Salas', 'Escritorios'], 'con empate, el orden de la portada')
        colchones = self.env.ref('website_dcasa.public_category_colchones')
        Plantilla.create({'name': 'ZZSUG oculto', 'list_price': 10.0, 'sale_ok': True, 'is_published': False,
                          'public_categ_ids': [Command.set(colchones.ids)]})
        self.assertNotIn('Colchones', self._sugerencias(), 'lo no publicado no cuenta')
        Plantilla.search([('is_published', '=', True)]).write({'is_published': False})
        self.assertEqual(self._sugerencias(), [], 'sin nada publicado, ninguna: la página usa las de fábrica')
