"""Qué cambios ensucian una página de la tienda del borde.

Solo se anota el id del producto (``dcasa.tienda.pendiente._dcasa_marcar``); nada se calcula aquí.
Las sobrescrituras de ``create``/``write``/``unlink`` no usan ``sudo()`` sobre el registro del
usuario: la marca se escribe aparte, en la tabla interna, al confirmar la transacción.
"""
from odoo import api, models

# Parámetros cuyo cambio se ve en el sitio: la ventana de Black Weekend (website_dcasa).
PREFIJO_PARAMETROS_SITIO = 'dcasa_black_weekend.'

# Campos de product.template que se ven en el sitio (ficha, tarjetas, JSON-LD, SEO).
CAMPOS_PLANTILLA = frozenset({
    'name', 'list_price', 'compare_list_price', 'is_published', 'website_published', 'website_id',
    'sale_ok', 'active', 'type', 'is_storable', 'allow_out_of_stock_order', 'image_1920',
    'description_ecommerce', 'description_sale', 'public_categ_ids', 'website_sequence',
    'website_meta_title', 'website_meta_description', 'website_meta_keywords', 'seo_name',
    'taxes_id', 'default_code', 'product_template_image_ids', 'attribute_line_ids',
    'optional_product_ids', 'website_ribbon_id', 'combo_ids',
    # Black Weekend (website_dcasa) y el combo del catálogo (dcasa_catalogo), que sale en su tarjeta.
    'dcasa_black_weekend', 'dcasa_bw_orden', 'dcasa_bw_variante_id', 'dcasa_combo',
})
CAMPOS_VARIANTE = frozenset({
    'active', 'default_code', 'image_variant_1920', 'product_template_attribute_value_ids', 'lst_price',
    'website_published', 'is_published',
})
CAMPOS_CATEGORIA = frozenset({'name', 'parent_id', 'sequence', 'website_id', 'seo_name', 'image_1920'})
# Vistas QWeb (plantillas del sitio, ediciones con el constructor de sitios) y páginas/menús: el
# borde guarda el HTML entero de Odoo, cabecera y pie incluidos.
CAMPOS_VISTA = frozenset({'arch', 'arch_db', 'arch_fs', 'active', 'inherit_id', 'mode', 'priority', 'key'})
CAMPOS_SITIO = frozenset({
    'dcasa_whatsapp_number', 'shop_ppg', 'shop_default_sort', 'prevent_zero_price_sale',
    'show_line_subtotals_tax_selection', 'domain', 'name', 'company_id', 'social_instagram',
    'social_tiktok', 'social_facebook', 'homepage_url',
})


def _marcar(env, plantilla_ids, motivo):
    env['dcasa.tienda.pendiente']._dcasa_marcar(plantilla_ids, motivo)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        productos = super().create(vals_list)
        _marcar(self.env, productos.ids, 'producto nuevo')
        return productos

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_PLANTILLA.intersection(vals):
            _marcar(self.env, self.ids, 'producto')
        return resultado

    def unlink(self):
        ids = self.ids
        resultado = super().unlink()
        _marcar(self.env, ids, 'producto borrado')
        return resultado


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_VARIANTE.intersection(vals):
            _marcar(self.env, self.product_tmpl_id.ids, 'variante')
        return resultado


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def write(self, vals):
        resultado = super().write(vals)
        if {'price_extra', 'ptav_active'}.intersection(vals):
            _marcar(self.env, self.product_tmpl_id.ids, 'precio de variante')
        return resultado


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    @api.model_create_multi
    def create(self, vals_list):
        categorias = super().create(vals_list)
        _marcar(self.env, [0], 'categoría')
        return categorias

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_CATEGORIA.intersection(vals):
            _marcar(self.env, [0], 'categoría')
        return resultado

    def unlink(self):
        resultado = super().unlink()
        _marcar(self.env, [0], 'categoría')
        return resultado


class Website(models.Model):
    _inherit = 'website'

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_SITIO.intersection(vals):
            _marcar(self.env, [0], 'ajustes del sitio')
        return resultado


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    def _dcasa_toca_el_sitio(self, claves):
        return any((clave or '').startswith(PREFIJO_PARAMETROS_SITIO) for clave in claves)

    @api.model_create_multi
    def create(self, vals_list):
        parametros = super().create(vals_list)
        if self._dcasa_toca_el_sitio(parametros.mapped('key')):
            _marcar(self.env, [0], 'black weekend')
        return parametros

    def write(self, vals):
        claves = self.mapped('key') + [vals.get('key')]
        resultado = super().write(vals)
        if self._dcasa_toca_el_sitio(claves):
            _marcar(self.env, [0], 'black weekend')
        return resultado

    def unlink(self):
        toca = self._dcasa_toca_el_sitio(self.mapped('key'))
        resultado = super().unlink()
        if toca:
            _marcar(self.env, [0], 'black weekend')
        return resultado


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # Todo movimiento validado (recepción, entrega, ajuste de inventario) y toda reserva pasan
    # por estos dos métodos privados: la disponibilidad pública sale de ahí.
    @api.model
    def _update_available_quantity(self, product_id, location_id, *args, **kwargs):
        resultado = super()._update_available_quantity(product_id, location_id, *args, **kwargs)
        _marcar(self.env, product_id.product_tmpl_id.ids, 'existencias')
        return resultado

    @api.model
    def _update_reserved_quantity(self, product_id, location_id, *args, **kwargs):
        resultado = super()._update_reserved_quantity(product_id, location_id, *args, **kwargs)
        _marcar(self.env, product_id.product_tmpl_id.ids, 'reserva')
        return resultado


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_confirm(self):
        resultado = super()._action_confirm()
        _marcar(self.env, self.order_line.product_id.product_tmpl_id.ids, 'venta confirmada')
        return resultado

    def _action_cancel(self):
        resultado = super()._action_cancel()
        _marcar(self.env, self.order_line.product_id.product_tmpl_id.ids, 'venta cancelada')
        return resultado


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        publicados = super()._post(soft=soft)
        plantillas = publicados.filtered(lambda m: m.is_invoice(include_receipts=True)) \
            .invoice_line_ids.product_id.product_tmpl_id
        _marcar(self.env, plantillas.ids, 'factura')
        return publicados


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    @api.model_create_multi
    def create(self, vals_list):
        vistas = super().create(vals_list)
        if vistas.filtered(lambda v: v.type == 'qweb'):
            _marcar(self.env, [0], 'plantilla')
        return vistas

    def write(self, vals):
        qweb = bool(self.filtered(lambda v: v.type == 'qweb'))
        resultado = super().write(vals)
        if qweb and CAMPOS_VISTA.intersection(vals):
            _marcar(self.env, [0], 'plantilla')
        return resultado

    def unlink(self):
        qweb = bool(self.filtered(lambda v: v.type == 'qweb'))
        resultado = super().unlink()
        if qweb:
            _marcar(self.env, [0], 'plantilla')
        return resultado


# Menú, páginas y tarifas: cualquier cambio puede verse en todo el sitio (cabecera, precios).
class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    @api.model_create_multi
    def create(self, vals_list):
        registros = super().create(vals_list)
        _marcar(self.env, [0], 'menú')
        return registros

    def write(self, vals):
        resultado = super().write(vals)
        _marcar(self.env, [0], 'menú')
        return resultado

    def unlink(self):
        resultado = super().unlink()
        _marcar(self.env, [0], 'menú')
        return resultado


class WebsitePage(models.Model):
    _inherit = 'website.page'

    @api.model_create_multi
    def create(self, vals_list):
        registros = super().create(vals_list)
        _marcar(self.env, [0], 'página')
        return registros

    def write(self, vals):
        resultado = super().write(vals)
        _marcar(self.env, [0], 'página')
        return resultado

    def unlink(self):
        resultado = super().unlink()
        _marcar(self.env, [0], 'página')
        return resultado


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    @api.model_create_multi
    def create(self, vals_list):
        registros = super().create(vals_list)
        _marcar(self.env, [0], 'tarifa')
        return registros

    def write(self, vals):
        resultado = super().write(vals)
        _marcar(self.env, [0], 'tarifa')
        return resultado

    def unlink(self):
        resultado = super().unlink()
        _marcar(self.env, [0], 'tarifa')
        return resultado
