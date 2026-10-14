from odoo import models
from odoo.exceptions import AccessError

# Lo que mueve el dinero de la tienda: precio de venta y costo. La vendedora edita el producto (nombre, descripción,
# fotos, medidas, publicarlo u ocultarlo) pero estas cifras solo las cambia quien controla la tienda.
CAMPOS_SOLO_GERENCIA = frozenset({'list_price', 'lst_price', 'standard_price'})
GRUPOS_QUE_CAMBIAN_PRECIOS = ('product.group_product_manager', 'base.group_system')


def _puede_cambiar_precios(env):
    return env.su or any(env.user.has_group(grupo) for grupo in GRUPOS_QUE_CAMBIAN_PRECIOS)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        if CAMPOS_SOLO_GERENCIA.intersection(vals) and not _puede_cambiar_precios(self.env):
            raise AccessError(self.env._('Solo Gerencia cambia los precios y los costos de los productos.'))
        return super().write(vals)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        if CAMPOS_SOLO_GERENCIA.intersection(vals) and not _puede_cambiar_precios(self.env):
            raise AccessError(self.env._('Solo Gerencia cambia los precios y los costos de los productos.'))
        return super().write(vals)
