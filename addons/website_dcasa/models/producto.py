"""Lo que el cliente ve de un producto en el sitio: el código público, nunca la referencia del proveedor.

La referencia interna (``default_code``) es de la casa; Odoo la deja salir por varios lados sin que se vea escrita en
la ficha: el nombre del producto lleva «[XHT022-T-W] …» y de ahí salen la dirección de la ficha, el nombre de cada foto
y los datos estructurados para Google. Aquí se cierran esos lados; el cliente ve el código público (``DC-K7M4PX``,
addons/dcasa_base/models/codigo_publico.py) y la dirección de la ficha es la de siempre pero sin el código.

Las direcciones viejas (``/shop/xht022-t-w-cama-…-5``) siguen funcionando: Odoo redirige (301) a la nueva.
"""
from odoo import api, models
from odoo.addons.dcasa_base.models.codigo_publico import normalizar_codigo_publico
from odoo.addons.dcasa_base.nombres import nombre_para_cliente
from odoo.fields import Domain

PRODUCTOS = ('product.template', 'product.product')


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _slug(cls, value):
        """La dirección bonita de un producto sale de su nombre, sin el «[referencia]» con que Odoo lo antecede."""
        if getattr(value, '_name', None) in PRODUCTOS:
            value = value.with_context(display_default_code=False)
        return super()._slug(value)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _to_markup_data(self, website):
        """Datos estructurados para Google: el ``sku`` es el código público, no la referencia del proveedor."""
        datos = super()._to_markup_data(website)
        datos.pop('sku', None)
        if self.dcasa_codigo_publico:
            datos['sku'] = self.dcasa_codigo_publico
        if isinstance(datos.get('name'), str):
            datos['name'] = nombre_para_cliente(datos['name'])   # el nombre que Google enseña: formato título (F5)
        return datos


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _search_get_detail(self, website, order, options):
        """El cuadro de búsqueda de la tienda también encuentra el producto por su código público completo
        («DC-K7M4PX», «dck7m4px»). Solo el código entero: es al azar y un pedazo suyo («tv») no significa nada."""
        detalle = super()._search_get_detail(website, order, options)
        otra_busqueda = detalle.get('search_extra')

        def por_codigo_publico(env, termino):
            subdominios = [otra_busqueda(env, termino)] if otra_busqueda else []
            if codigo := normalizar_codigo_publico(termino):
                subdominios.append(Domain('dcasa_codigo_publico', '=', codigo))
            return Domain.OR(subdominios) if subdominios else Domain.FALSE

        detalle['search_extra'] = por_codigo_publico
        return detalle

    def _default_website_meta(self):
        """El título al compartir la ficha (WhatsApp, Facebook): «Cama Queen Tapizada», no en MAYÚSCULAS (F5)."""
        res = super()._default_website_meta()
        nombre = self._dcasa_nombre_cliente()
        res['default_opengraph']['og:title'] = res['default_twitter']['twitter:title'] = nombre
        return res

    @api.model
    def _search_render_results(self, fetch_fields, mapping, icon, limit):
        """El buscador del sitio muestra los nombres en formato título (F5)."""
        resultados = super()._search_render_results(fetch_fields, mapping, icon, limit)
        for datos in resultados:
            if isinstance(datos.get('name'), str):
                datos['name'] = nombre_para_cliente(datos['name'])
        return resultados
