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
            'dcasa_combo': 'Combo con colchón First Class $469.99',
            'public_categ_ids': [Command.set(cls.env.ref('website_dcasa.public_category_recamaras').ids)],
        })
        cls.herramientas = cls.env['brian.herramientas'].sudo()
        cls.env.ref('base.group_user').write({
            'implied_ids': [Command.link(cls.env.ref('product.group_product_pricelist').id)]})
        cls.env['dcasa.campana']._dcasa_tarifa_del_sitio()

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

    def test_cada_medida_baja_lo_mismo_en_la_ficha_completa(self):
        medida = self.env['product.attribute'].create({'name': 'Medida ficha', 'create_variant': 'always'})
        full, king = self.env['product.attribute.value'].create([
            {'name': 'Full', 'attribute_id': medida.id}, {'name': 'King', 'attribute_id': medida.id}])
        self.cama.write({'attribute_line_ids': [Command.create({
            'attribute_id': medida.id, 'value_ids': [Command.set([full.id, king.id])]})]})
        self.cama.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.product_attribute_value_id == king).price_extra = 60.0
        self.env.ref('base.group_user').write({
            'implied_ids': [Command.link(self.env.ref('product.group_product_pricelist').id)]})
        self.env['dcasa.campana']._dcasa_tarifa_del_sitio()
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        precios = sorted(v['precio'] for v in self.herramientas._j_ficha_completa(self.cama)['variantes'])
        self.assertEqual(precios, [150.0, 210.0], 'la King conserva sus 60 de diferencia')
        self.assertIsNone(self.herramientas._j_combo(self.cama), 'con precio de campaña no se dice el combo del Excel')
