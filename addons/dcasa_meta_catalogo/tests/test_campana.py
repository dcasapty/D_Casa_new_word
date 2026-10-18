"""Campañas para anuncios: el código para Meta y marcar varios productos a la vez."""
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import MetaComun


@tagged('post_install', '-at_install')
class TestCampana(MetaComun, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Campana = cls.env['dcasa.meta.campana']
        cls.gerencia = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gerencia campañas', 'login': 'gerencia_campanas_meta',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref('dcasa_base.group_gerencia').id])],
        })

    def test_el_codigo_se_normaliza(self):
        self.assertEqual(self.Campana.create({'name': 'Navidad'}).codigo, 'navidad')
        campana = self.Campana.create({'name': 'Día de la Madre ñandú 2026'})
        self.assertEqual(campana.codigo, 'dia_de_la_madre_nandu_2026')

    def test_el_codigo_es_unico(self):
        self.Campana.create({'name': 'Black Weekend'})
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Campana.create({'name': 'black  weekend!'})
            self.env.flush_all()

    def test_el_codigo_no_cambia_al_renombrar(self):
        campana = self.Campana.create({'name': 'Navidad'})
        campana.name = 'Navidad y Año Nuevo'
        self.env.flush_all()
        campana.invalidate_recordset()
        self.assertEqual(campana.codigo, 'navidad', 'el conjunto de productos de Meta no se rompe')

    def test_sin_letras_ni_numeros_no_hay_codigo(self):
        with self.assertRaises(ValidationError):
            self.Campana.create({'name': '¡¡!!'})

    def test_borrar_la_campana_deja_al_producto_sin_campana(self):
        campana = self.Campana.create({'name': 'Liquidación'})
        mesa = self._producto('Mesa campaña prueba', 90.0, dcasa_meta_campana_id=campana.id)
        self.assertEqual(campana.producto_count, 1)
        campana.unlink()
        self.assertTrue(mesa.exists())
        self.assertFalse(mesa.dcasa_meta_campana_id)

    def test_gerencia_marca_varios_productos_a_la_vez(self):
        campana = self.Campana.create({'name': 'Verano'})
        productos = self._producto('Silla verano 1', 40.0) | self._producto('Silla verano 2', 45.0) \
            | self._producto('Silla verano 3', 50.0)
        # «Productos para campañas»: la lista de Productos (edita varios a la vez) trae la columna de la campaña.
        accion = self.env.ref('sale.product_template_action')
        vista_id = accion.view_ids.filtered(lambda v: v.view_mode == 'list').view_id.id
        vistas = self.env['product.template'].with_user(self.gerencia).get_views([(vista_id, 'list')])
        arch = vistas['views']['list']['arch']
        self.assertIn('name="dcasa_meta_campana_id"', arch)
        self.assertIn('multi_edit="1"', arch)
        # Lo que hace la lista al editar varios a la vez: un solo write sobre todos.
        productos.with_user(self.gerencia).write({'dcasa_meta_campana_id': campana.id})
        self.assertEqual(productos.mapped('dcasa_meta_campana_id'), campana)
        self.assertEqual(campana.producto_count, 3)
        filas = self._por_id()
        for producto in productos:
            self.assertEqual(filas[str(producto.product_variant_id.id)]['custom_label_1'], 'verano')
