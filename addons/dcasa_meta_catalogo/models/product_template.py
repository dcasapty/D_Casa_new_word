from odoo import fields, models

GERENCIA = 'sales_team.group_sale_manager,base.group_system'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Los dos campos son de Gerencia y administradores (``groups``): la Vendedora no los ve ni los escribe, tampoco
    # por RPC. El catálogo los lee con sudo.
    dcasa_meta_no_anunciar = fields.Boolean(
        'No anunciar en Facebook e Instagram', default=False, copy=False, groups=GERENCIA,
        help='Si lo marcas, este producto sigue en la tienda en línea pero no sale en el catálogo que lee Meta, así '
             'que no aparece en los anuncios.')
    dcasa_meta_campana_id = fields.Many2one(
        'dcasa.meta.campana', string='Campaña (Meta)', ondelete='set null', index='btree_not_null', copy=False,
        groups=GERENCIA,
        help='Campaña de anuncios de este producto. En Meta se usa como «Etiqueta personalizada 1» para armar un '
             'conjunto de productos.')
