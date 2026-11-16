"""Las reglas de la tarifa del catálogo, buscadas una sola vez para todo el lote.

El precio de cada fila sale de la ficha (``_get_additionnal_combination_info``), que busca las reglas de la tarifa
producto por producto: con una tarifa ofrecida al sitio (en producción, la general desde la campaña del sitio) eran una
consulta por producto (``tests/test_rendimiento.py``). Aquí se buscan una vez para todas las variantes del catálogo (sin
fechas) y cada producto toma las suyas en Python, con las mismas condiciones del dominio de Odoo
(``product.pricelist._get_applicable_rules_domain``): tarifa, categoría (o una madre), plantilla, variante y fechas, en
el mismo orden. El precio sigue siendo el mismo cálculo de la ficha.

Solo vale dentro del catálogo (``REGLAS_DEL_LOTE`` lleva un objeto de Python en el contexto, que una llamada por RPC no
puede fabricar), para esa tarifa y esos productos y sin argumentos extra; si no, la búsqueda de siempre.
"""
from odoo import fields, models
from odoo.addons.website_dcasa.models.campana import COMBO_SIN_CAMPANA, es_interno

REGLAS_DEL_LOTE = 'dcasa_meta_reglas_del_lote'


class ReglasDelLote:
    """Las reglas de una tarifa que pueden tocar a alguna variante del lote (sin mirar fechas)."""

    def __init__(self, tarifa, variantes):
        self.tarifa_id = tarifa.id
        self.variantes = frozenset(variantes.ids)
        self.plantillas = frozenset(variantes.product_tmpl_id.ids)
        self.reglas = tarifa.env['product.pricelist.item'].search([
            ('pricelist_id', '=', tarifa.id),
            '|', ('categ_id', '=', False), ('categ_id', 'parent_of', variantes.categ_id.ids),
            '|', ('product_tmpl_id', '=', False), ('product_tmpl_id', 'in', list(self.plantillas)),
            '|', ('product_id', '=', False), ('product_id', 'in', list(self.variantes)),
        ])

    def sirve(self, tarifa, productos):
        if len(tarifa) != 1 or tarifa.id != self.tarifa_id or not productos:
            return False
        if productos._name == 'product.product':
            return set(productos.ids) <= self.variantes
        return productos._name == 'product.template' and set(productos.ids) <= self.plantillas

    def de(self, tarifa, productos, fecha):
        """Las reglas que daría ``_get_applicable_rules(productos, fecha)``, en su orden."""
        momento = fields.Datetime.to_datetime(fecha)
        if productos._name == 'product.template':
            plantillas, variantes = set(productos.ids), None
        else:
            plantillas, variantes = set(productos.product_tmpl_id.ids), set(productos.ids)
        rutas = [categoria.parent_path for categoria in productos.categ_id if categoria.parent_path]

        def aplica(regla):
            if regla.categ_id and not any(ruta.startswith(regla.categ_id.parent_path) for ruta in rutas):
                return False
            if regla.product_tmpl_id and regla.product_tmpl_id.id not in plantillas:
                return False
            if regla.product_id:
                if variantes is None and regla.product_id.product_tmpl_id.id not in plantillas:
                    return False
                if variantes is not None and regla.product_id.id not in variantes:
                    return False
            if regla.date_start and regla.date_start > momento:
                return False
            return not (regla.date_end and regla.date_end < momento)

        return self.reglas.filtered(aplica).with_env(tarifa.env)


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _get_applicable_rules(self, products, date, **kwargs):
        lote = self.env.context.get(REGLAS_DEL_LOTE)
        # La bandera de los combos (website_dcasa) cambia el dominio: con ella, la búsqueda de siempre.
        if isinstance(lote, ReglasDelLote) and not kwargs and lote.sirve(self, products) \
                and not es_interno(self.env, COMBO_SIN_CAMPANA):
            return lote.de(self, products, date)
        return super()._get_applicable_rules(products, date, **kwargs)
