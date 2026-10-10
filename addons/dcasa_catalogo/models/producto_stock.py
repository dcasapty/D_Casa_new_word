"""«Stock y precios»: una sola lista para elegir qué empujar en una campaña.

Pedido de la dueña: cuando se hace una campaña (esta semana, las camas) hay que ver el stock de una categoría, de
una línea o de todo, y ordenar por mayor o menor stock y por mayor o menor precio según la campaña. En la lista de
productos de Odoo el stock («A la mano») no se puede ordenar ni agrupar porque se calcula al vuelo; esta es una
vista de SOLO LECTURA hecha en la base de datos (una fila por variante) donde todo se ordena, se filtra y se agrupa.

Qué NO muestra: costos ni márgenes (los ve quien tiene permiso en Contabilidad), ni cambia nada: es solo para mirar.
El estado del stock usa la misma regla que Juan y la tienda (``publico.etiqueta_existencias``): agotado si no hay
unidades libres, «pocas» hasta el umbral de la ficha (5 por defecto) y disponible si hay más. Un producto que no
controla inventario no tiene cifra (queda en 0 para que «mayor stock primero» lo deje al final) y se ve «Sin
control».
"""
from odoo import fields, models
from odoo.tools import SQL

ESTADOS = [
    ('agotado', 'Agotado'),
    ('pocas', 'Pocas unidades'),
    ('disponible', 'Disponible'),
    ('sin_control', 'Sin control de stock'),
]


class DcasaProductoStock(models.Model):
    _name = 'dcasa.producto.stock'
    _description = 'Stock y precio de cada producto (para elegir qué empujar en una campaña)'
    _auto = False
    _order = 'categ_id, product_id'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.product', 'Producto', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', 'Ficha', readonly=True)
    default_code = fields.Char('Código', readonly=True)
    categ_id = fields.Many2one('product.category', 'Categoría', readonly=True)
    categoria_web_id = fields.Many2one('product.public.category', 'Categoría de la tienda', readonly=True,
                                       help='La primera categoría de la tienda en línea de la ficha.')
    currency_id = fields.Many2one('res.currency', 'Moneda', readonly=True)
    precio = fields.Monetary('Precio (sin ITBMS)', currency_field='currency_id', readonly=True, aggregator='avg')
    stock = fields.Float('En existencia', readonly=True, aggregator='sum', digits=(16, 0),
                         help='Unidades que hay en las ubicaciones internas (bodega y tienda).')
    reservado = fields.Float('Reservado', readonly=True, aggregator='sum', digits=(16, 0),
                             help='Unidades ya comprometidas con una venta o un traslado.')
    disponible = fields.Float('Libre', readonly=True, aggregator='sum', digits=(16, 0),
                              help='Existencia menos lo reservado: lo que de verdad se puede ofrecer.')
    estado_stock = fields.Selection(ESTADOS, 'Estado del stock', readonly=True)
    valor_a_precio = fields.Monetary('Valor a precio de venta', currency_field='currency_id', readonly=True,
                                     aggregator='sum',
                                     help='Existencia por precio de venta, sin ITBMS. No es el costo.')
    vendidas_30d = fields.Float('Vendidas en 30 días', readonly=True, aggregator='sum', digits=(16, 0),
                                help='Unidades de ventas confirmadas en los últimos 30 días.')
    publicado = fields.Boolean('En la tienda en línea', readonly=True)
    en_black_weekend = fields.Boolean('Black Weekend', readonly=True)
    controla_stock = fields.Boolean('Controla inventario', readonly=True)
    public_categ_ids = fields.Many2many('product.public.category', string='Categorías de la tienda',
                                        related='product_tmpl_id.public_categ_ids', readonly=True)
    image_128 = fields.Image('Foto', related='product_tmpl_id.image_128', readonly=True)
    # El cliente web la pide para las fotos (widget image) y así una foto nueva no se ve con la vieja en la memoria.
    write_date = fields.Datetime('Última modificación', readonly=True)

    @property
    def _table_query(self):
        return SQL("""
            SELECT pp.id AS id,
                   pp.id AS product_id,
                   pt.id AS product_tmpl_id,
                   pp.default_code AS default_code,
                   pt.categ_id AS categ_id,
                   (SELECT rel.product_public_category_id
                      FROM product_public_category_product_template_rel rel
                     WHERE rel.product_template_id = pt.id
                  ORDER BY rel.product_public_category_id LIMIT 1) AS categoria_web_id,
                   (SELECT c.currency_id FROM res_company c ORDER BY c.id LIMIT 1) AS currency_id,
                   (pt.list_price + COALESCE(extra.precio_extra, 0)) AS precio,
                   CASE WHEN pt.is_storable THEN COALESCE(q.existencia, 0) ELSE 0 END AS stock,
                   CASE WHEN pt.is_storable THEN COALESCE(q.reservado, 0) ELSE 0 END AS reservado,
                   CASE WHEN pt.is_storable THEN COALESCE(q.existencia, 0) - COALESCE(q.reservado, 0)
                        ELSE 0 END AS disponible,
                   CASE WHEN NOT pt.is_storable THEN 'sin_control'
                        WHEN COALESCE(q.existencia, 0) - COALESCE(q.reservado, 0) <= 0 THEN 'agotado'
                        WHEN COALESCE(q.existencia, 0) - COALESCE(q.reservado, 0)
                             <= COALESCE(pt.available_threshold, 5) THEN 'pocas'
                        ELSE 'disponible' END AS estado_stock,
                   CASE WHEN pt.is_storable
                        THEN GREATEST(COALESCE(q.existencia, 0), 0) * (pt.list_price + COALESCE(extra.precio_extra, 0))
                        ELSE 0 END AS valor_a_precio,
                   COALESCE(v.unidades, 0) AS vendidas_30d,
                   COALESCE(pt.is_published, FALSE) AS publicado,
                   COALESCE(pt.dcasa_black_weekend, FALSE) AS en_black_weekend,
                   pt.is_storable AS controla_stock,
                   GREATEST(pt.write_date, pp.write_date) AS write_date
              FROM product_product pp
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
         LEFT JOIN (SELECT pvc.product_product_id AS producto, SUM(ptav.price_extra) AS precio_extra
                      FROM product_variant_combination pvc
                      JOIN product_template_attribute_value ptav
                        ON ptav.id = pvc.product_template_attribute_value_id
                  GROUP BY pvc.product_product_id) extra ON extra.producto = pp.id
         LEFT JOIN (SELECT sq.product_id AS producto, SUM(sq.quantity) AS existencia,
                           SUM(sq.reserved_quantity) AS reservado
                      FROM stock_quant sq
                      JOIN stock_location sl ON sl.id = sq.location_id AND sl.usage = 'internal'
                  GROUP BY sq.product_id) q ON q.producto = pp.id
         LEFT JOIN (SELECT sol.product_id AS producto, SUM(sol.product_uom_qty) AS unidades
                      FROM sale_order_line sol
                      JOIN sale_order so ON so.id = sol.order_id
                     WHERE so.state = 'sale' AND sol.display_type IS NULL
                       AND so.date_order >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '30 days'
                  GROUP BY sol.product_id) v ON v.producto = pp.id
             WHERE pp.active AND pt.active AND pt.sale_ok AND pt.type = 'consu'
        """)
