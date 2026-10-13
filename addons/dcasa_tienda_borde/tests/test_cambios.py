import os
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

TOKEN = 'y' * 40
ENTORNO = {'TIENDA_FEED_TOKEN': TOKEN, 'CANONICAL_HOST': 'staging.dcasapty.com'}


@tagged('post_install', '-at_install')
class TestMarcasDeCambio(TransactionCase):
    """Precio, existencias, ventas y facturas dejan la página «pendiente» para el Worker."""

    def setUp(self):
        super().setUp()
        self.Pendiente = self.env['dcasa.tienda.pendiente'].sudo()
        self.Pendiente.search([]).unlink()
        self.producto = self.env['product.template'].create({
            'name': 'Silla marcas prueba', 'list_price': 25, 'is_published': True, 'is_storable': True,
        })
        self.variante = self.producto.product_variant_id
        self._confirmar()
        self.Pendiente.search([]).unlink()
        self.cliente = self.env['res.partner'].create({'name': 'Cliente marcas prueba'})

    def _confirmar(self):
        """Lo que pasa al confirmar la transacción (precommit)."""
        self.env.flush_all()
        self.env.cr.flush()

    def _marcados(self):
        self._confirmar()
        return set(self.Pendiente.search([]).mapped('producto_id'))

    def test_precio_y_nombre(self):
        self.producto.list_price = 30
        self.assertIn(self.producto.id, self._marcados())

    def test_campo_que_no_se_ve_no_marca(self):
        self.producto.write({'description_purchase': 'nota interna'})
        self.assertNotIn(self.producto.id, self._marcados())

    def test_varios_cambios_una_marca(self):
        self.producto.list_price = 31
        self.producto.name = 'Silla marcas prueba 2'
        self._confirmar()
        self.assertEqual(self.Pendiente.search_count([('producto_id', '=', self.producto.id)]), 1)

    def test_categoria_regenera_todo(self):
        self.env['product.public.category'].create({'name': 'Categoría marcas'})
        self.assertIn(0, self._marcados())

    def test_plantilla_menu_pagina_y_tarifa_regeneran_todo(self):
        """El borde guarda el HTML entero (cabecera, pie, menú): editar el sitio lo invalida."""
        vista = self.env['ir.ui.view'].create({
            'name': 'Vista marcas prueba', 'type': 'qweb', 'key': 'dcasa_tienda_borde.vista_marcas_prueba',
            'arch': '<t t-name="dcasa_tienda_borde.vista_marcas_prueba"><p>uno</p></t>'})
        self.assertIn(0, self._marcados())
        self.Pendiente.search([]).unlink()
        vista.arch = '<t t-name="dcasa_tienda_borde.vista_marcas_prueba"><p>dos</p></t>'
        self.assertIn(0, self._marcados())
        self.Pendiente.search([]).unlink()
        sitio = self.env['website'].search([], limit=1)
        self.env['website.menu'].create({'name': 'Menú marcas', 'url': '/shop', 'website_id': sitio.id})
        self.assertIn(0, self._marcados())
        self.Pendiente.search([]).unlink()
        tarifa = self.env['product.pricelist'].create({'name': 'Tarifa marcas'})
        self.env['product.pricelist.item'].create({
            'pricelist_id': tarifa.id, 'compute_price': 'percentage', 'percent_price': 10})
        self.assertIn(0, self._marcados())

    def test_vista_que_no_es_del_sitio_no_marca(self):
        vista = self.env['ir.ui.view'].create({
            'name': 'Vista formulario marcas', 'type': 'form', 'model': 'res.partner',
            'arch': '<form><field name="name"/></form>'})
        self._marcados()
        self.Pendiente.search([]).unlink()
        vista.arch = '<form><field name="name"/><field name="email"/></form>'
        self.assertNotIn(0, self._marcados())

    def test_existencias(self):
        bodega = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        self.env['stock.quant']._update_available_quantity(self.variante, bodega.lot_stock_id, 5)
        self.assertIn(self.producto.id, self._marcados())

    def test_venta_confirmada(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.variante.id, 'product_uom_qty': 1})],
        })
        self._confirmar()
        self.Pendiente.search([]).unlink()
        orden.action_confirm()
        self._confirmar()
        motivos = self.Pendiente.search([('producto_id', '=', self.producto.id)]).mapped('motivo')
        self.assertTrue(motivos)

    def test_factura_publicada(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.variante.id, 'quantity': 1, 'price_unit': 25})],
        })
        self._confirmar()
        self.Pendiente.search([]).unlink()
        factura.action_post()
        self.assertIn(self.producto.id, self._marcados())

    def test_aviso_al_worker(self):
        self.producto.list_price = 32
        self._confirmar()
        respuesta = MagicMock(status_code=200)
        with patch.dict(os.environ, ENTORNO), \
                patch('odoo.addons.dcasa_tienda_borde.models.pendiente.requests.post', return_value=respuesta) as post:
            self.assertTrue(self.env['dcasa.tienda.pendiente']._dcasa_avisar_borde())
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://staging.dcasapty.com/__edge/tienda/regenerar')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], f'Bearer {TOKEN}')
        self.assertIn(self.producto.id, post.call_args.kwargs['json']['productos'])
        # La ficha del producto va en «rutas»: el borde la vuelve a pedir enseguida.
        self.assertIn(self.producto.website_url, post.call_args.kwargs['json']['rutas'])
        self.assertFalse(self.Pendiente.search_count([]), 'Entregado: se borran las marcas')

    def test_worker_caido_reintenta(self):
        self.producto.list_price = 33
        self._confirmar()
        with patch.dict(os.environ, ENTORNO), \
                patch('odoo.addons.dcasa_tienda_borde.models.pendiente.requests.post',
                      return_value=MagicMock(status_code=503)):
            self.assertFalse(self.env['dcasa.tienda.pendiente']._dcasa_avisar_borde())
        with patch.dict(os.environ, ENTORNO), \
                patch('odoo.addons.dcasa_tienda_borde.models.pendiente.requests.post',
                      side_effect=requests.ConnectionError('sin red')):
            self.assertFalse(self.env['dcasa.tienda.pendiente']._dcasa_avisar_borde())
        self.assertTrue(self.Pendiente.search_count([('producto_id', '=', self.producto.id)]))

    def test_sin_configurar_descarta(self):
        self.producto.list_price = 34
        self._confirmar()
        with patch.dict(os.environ, {'TIENDA_FEED_TOKEN': '', 'TIENDA_AVISO_URL': '', 'CANONICAL_HOST': ''}), \
                patch('odoo.addons.dcasa_tienda_borde.models.pendiente.requests.post') as post:
            self.env['dcasa.tienda.pendiente']._dcasa_avisar_borde()
        post.assert_not_called()
        self.assertFalse(self.Pendiente.search_count([]))

    def test_despliegue_nuevo_regenera_todo(self):
        """Una versión nueva (APP_VERSION) cambia plantillas y estilos sin pasar por el ORM: se avisa
        «todo» una sola vez por versión, aunque no haya ningún otro cambio pendiente."""
        Pendiente = self.env['dcasa.tienda.pendiente']
        respuesta = MagicMock(status_code=200)
        ruta_post = 'odoo.addons.dcasa_tienda_borde.models.pendiente.requests.post'
        with patch.dict(os.environ, dict(ENTORNO, APP_VERSION='v-auditoria-1')), \
                patch(ruta_post, return_value=respuesta) as post:
            self.assertTrue(Pendiente._dcasa_avisar_borde())
            self.assertTrue(post.call_args.kwargs['json']['todo'])
            self.assertIn('despliegue', post.call_args.kwargs['json']['motivos'])
            post.reset_mock()
            self.assertFalse(Pendiente._dcasa_avisar_borde(), 'Misma versión: nada que avisar')
            post.assert_not_called()
        with patch.dict(os.environ, dict(ENTORNO, APP_VERSION='v-auditoria-2')), \
                patch(ruta_post, return_value=respuesta):
            self.assertTrue(Pendiente._dcasa_avisar_borde())
        with patch.dict(os.environ, dict(ENTORNO, APP_VERSION='')), patch(ruta_post) as post:
            self.assertFalse(Pendiente._dcasa_avisar_borde(), 'Sin versión (desarrollo): no marca')
            post.assert_not_called()

    def test_cambio_dispara_el_cron(self):
        cron = self.env.ref('dcasa_tienda_borde.cron_avisar_borde')
        antes = self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)])
        self.producto.list_price = 35
        self._confirmar()
        self.assertGreater(self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)]), antes)

    def test_usuario_sin_acceso_no_lee_marcas(self):
        vendedor = self.env['res.users'].create({
            'name': 'Vendedor marcas', 'login': 'vendedor_marcas_prueba',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        # Una marca hecha con el entorno de un usuario sin acceso a la tabla se escribe igual (sistema)…
        self.env['dcasa.tienda.pendiente'].with_user(vendedor)._dcasa_marcar([self.producto.id], 'prueba')
        self.assertIn(self.producto.id, self._marcados())
        # …pero ese usuario no puede leer ni tocar la tabla interna.
        with self.assertRaises(AccessError):
            self.env['dcasa.tienda.pendiente'].with_user(vendedor).search([])
