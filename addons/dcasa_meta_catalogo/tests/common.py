"""Lo común de las pruebas del catálogo para Meta: un sitio con dirección pública de prueba y productos propios.

Ninguna prueba llama a Meta. ``web.base.url`` = ``https://tienda.example`` (congelado) dentro de la prueba, y el feed
se limita a una categoría de prueba para no arrastrar el catálogo real que carga dcasa_catalogo.
"""
import base64
import csv
import io

from PIL import Image

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.fields import Command
from odoo.tools import SQL

BASE = 'https://tienda.example'


def foto(color='blue', ancho=640, alto=480):
    salida = io.BytesIO()
    Image.new('RGB', (ancho, alto), color).save(salida, format='JPEG')
    return base64.b64encode(salida.getvalue())


def leer_csv(contenido):
    """[{columna: valor}] del CSV en bytes (UTF-8 sin BOM)."""
    return list(csv.DictReader(io.StringIO(contenido.decode('utf-8'))))


class MetaComun:
    """Mezcla para TransactionCase / HttpCase."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        parametros = cls.env['ir.config_parameter'].sudo()
        parametros.set_param('web.base.url', BASE)
        parametros.set_param('web.base.url.freeze', 'True')
        cls.website = cls.env.ref('website.default_website')
        cls.website.domain = False
        cls.padre = cls.env['product.public.category'].create({'name': 'Dormitorio', 'sequence': 1})
        cls.categoria = cls.env['product.public.category'].create({
            'name': 'Habitación de Niños', 'parent_id': cls.padre.id, 'sequence': 1})
        cls.feed = cls.env.ref('dcasa_meta_catalogo.feed_meta_principal')
        cls.feed.write({'dcasa_activo': True, 'product_category_ids': [Command.set(cls.padre.ids)]})
        cls.almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)

    @classmethod
    def _producto(cls, nombre, precio=120.0, **valores):
        """Un producto publicado, a la venta, con foto y en la categoría de prueba."""
        datos = {
            'name': nombre, 'list_price': precio, 'is_published': True, 'sale_ok': True,
            'image_1920': foto(), 'public_categ_ids': [Command.set(cls.categoria.ids)],
        }
        datos.update(valores)
        return cls.env['product.template'].create(datos)

    @classmethod
    def _cama_con_tamanos(cls, nombre='Cama prueba Meta', precio=300.0, extra_king=50.0):
        """Una cama con dos tamaños (dos variantes): King cuesta ``extra_king`` más."""
        atributo = cls.env['product.attribute'].create({
            'name': 'Tamaño prueba Meta', 'create_variant': 'always',
            'value_ids': [Command.create({'name': 'Queen'}), Command.create({'name': 'King'})],
        })
        cama = cls._producto(nombre, precio, attribute_line_ids=[Command.create({
            'attribute_id': atributo.id, 'value_ids': [Command.set(atributo.value_ids.ids)]})])
        king = cama.product_variant_ids.filtered(
            lambda v: v.product_template_attribute_value_ids.name == 'King')
        king.product_template_attribute_value_ids.price_extra = extra_king
        return cama, cama.product_variant_ids - king, king

    def _existencias(self, plantilla, cantidad):
        variante = plantilla.product_variant_ids[:1]
        self.env['stock.quant']._update_available_quantity(variante, self.almacen.lot_stock_id, cantidad)

    def _csv(self, feed=None):
        feed = feed or self.feed
        with MockRequest(self.env, website=self.website):
            return feed._dcasa_meta_csv()

    def _filas(self, feed=None):
        return leer_csv(self._csv(feed))

    def _por_id(self, feed=None):
        return {fila['id']: fila for fila in self._filas(feed)}

    def _despues(self, registros):
        """Como si el cambio se hubiera hecho en otra petición, un momento después.

        En una prueba todo pasa en una sola transacción y ``write_date`` es la misma hora para todo; en producción
        cada cambio llega en su propia transacción. La huella del catálogo mira la última modificación.
        """
        self.env.flush_all()
        self.env.cr.execute(SQL(
            "UPDATE %s SET write_date = write_date + interval '1 minute' WHERE id = ANY(%s)",
            SQL.identifier(registros._table), registros.ids))
        registros.invalidate_recordset(['write_date'])
