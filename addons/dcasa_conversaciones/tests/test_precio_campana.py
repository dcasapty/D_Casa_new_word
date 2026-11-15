"""Juan y Andrés (el chat de la tienda) dicen el precio que cobra el carrito: durante una campaña del sitio con
precio de campaña (website_dcasa, models/campana.py), ese, con el normal de referencia (pedido de la dueña, 2026-11-15).
"""
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPrecioDeCampanaEnLaFicha(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        param = cls.env['ir.config_parameter'].sudo()
        param.set_param('dcasa_black_weekend.activo', '0')
        cls.campana = cls.env['dcasa.campana'].search([('website_id', '=', cls.website.id)]) \
            or cls.env['dcasa.campana'].create({'website_id': cls.website.id})
        cls.campana.write({'name': 'Black Friday', 'fecha_inicio': False, 'fecha_fin': False})
        cls.cama = cls.env['product.template'].create({
            'name': 'CAMA FICHA CAMPAÑA', 'list_price': 200.0, 'is_published': True, 'sale_ok': True,
            'public_categ_ids': [Command.set(cls.env.ref('website_dcasa.public_category_recamaras').ids)],
        })
        cls.herramientas = cls.env['brian.herramientas'].sudo()

    def test_sin_campana_el_precio_de_siempre(self):
        ficha = self.herramientas._j_ficha_corta(self.cama, '')
        self.assertEqual(ficha['precio'], 200.0)
        self.assertNotIn('precio de', ficha['precio_texto'])

    def test_en_campana_el_de_campana_con_el_normal(self):
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        ficha = self.herramientas._j_ficha_corta(self.cama, '')
        self.assertEqual(ficha['precio'], 150.0)
        self.assertIn('$150.00', ficha['precio_texto'])
        self.assertIn('precio de Black Friday', ficha['precio_texto'])
        self.assertIn('$200.00', ficha['precio_texto'])

    def test_campana_programada_todavia_no(self):
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy + timedelta(days=5), 'fecha_fin': hoy + timedelta(days=8)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        self.assertEqual(self.herramientas._j_ficha_corta(self.cama, '')['precio'], 200.0)
