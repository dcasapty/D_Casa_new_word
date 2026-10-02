"""Catálogo publicado, como JSON, para el generador de la tienda estática del Worker (edge/).

Todo sale de lo mismo que usan las páginas de Odoo, para que la página estática y la de Odoo
digan lo mismo:

* URL: ``website_url`` del producto y ``/shop/category/<slug>`` de la categoría (iguales a Odoo).
* Precio: ``_get_sales_prices`` (la tarifa y la posición fiscal del visitante anónimo, sin
  ITBMS: la tienda muestra el precio sin impuesto) y la leyenda «+ ITBMS» de website_dcasa.
* JSON-LD: el ``_to_markup_data`` de website_sale con las migas de website_dcasa y, mientras
  ``PUBLICAR_DISPONIBILIDAD`` sea falso, sin ``availability``.
* Existencias: solo si ``PUBLICAR_DISPONIBILIDAD`` es verdadero (si no, ``null``: no se inventan).

Solo se lee lo que un visitante anónimo puede ver: el feed corre con el usuario público del
sitio (las reglas de registro dejan fuera lo no publicado) y el dominio de la tienda.
"""
import json

from odoo import fields, models
from odoo.addons.dcasa_socios.models import reglas as reglas_socios
from odoo.addons.website_dcasa.controllers import main as website_dcasa_main

VERSION_FEED = 1
# Más variantes que esto: la ficha sigue en Odoo (el selector de Odoo es mejor para listas largas).
MAX_VARIANTES_ESTATICAS = 30
DESCRIPCION_TIENDA = (
    "Tienda en línea de D'CASA Panamá: salas, recámaras, colchones, zapateras, estantes y escritorios "
    'con precios claros. Entrega a todo Panamá desde La Chorrera.')
TAMANOS_IMAGEN = ('image_256', 'image_512', 'image_1024', 'image_1920')


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_tienda_modo_compra(self, producto):
        """Cómo se compra desde la página estática.

        * ``directa``: un botón «Agregar al carrito» (las mismas reglas que el «Agregar» de la portada).
        * ``variantes``: una lista de opciones (cada variante con su precio) y un botón, sin JavaScript.
        * ``ficha``: hay que configurar algo (atributos dinámicos o sin variante, valores a medida,
          combos, opcionales): esa ficha la sigue sirviendo Odoo.
        """
        self.ensure_one()
        if self._dcasa_compra_directa(producto):
            return 'directa'
        lineas = producto.attribute_line_ids
        if (
            1 < producto.product_variant_count <= MAX_VARIANTES_ESTATICAS
            and producto.type != 'combo'
            and not producto.optional_product_ids
            and all(linea.attribute_id.create_variant == 'always' for linea in lineas)
            and not any(lineas.product_template_value_ids.mapped('is_custom'))
        ):
            return 'variantes'
        return 'ficha'

    def _dcasa_tienda_disponibilidad(self, variante):
        """(disponible, existencias) de una variante, o (None, None) si no se publica."""
        if not website_dcasa_main.PUBLICAR_DISPONIBILIDAD:
            return None, None
        variante_sudo = variante.sudo()  # el visitante no lee stock.quant; solo se publica un número
        if not variante_sudo.is_storable:
            return True, None
        cantidad = max(0.0, self._get_product_available_qty(variante_sudo))
        return bool(cantidad > 0 or variante_sudo.allow_out_of_stock_order), int(cantidad)

    def _dcasa_tienda_feed(self):
        """Datos de la tienda estática. Necesita una petición web del sitio (tarifa del visitante)."""
        self.ensure_one()
        Producto = self.env['product.template']
        dominio = self._dcasa_dominio_publicado()
        productos = Producto.search(dominio, order=f'is_published desc, {self.shop_default_sort}, id desc')
        precios = productos._get_sales_prices(self)
        base = self._dcasa_url_publica()
        slug = self.env['ir.http']._slug
        migas = website_dcasa_main.DcasaCheckout()

        categorias = self.env['product.public.category'].search(self.website_domain(), order='sequence, id')
        datos_categorias = [{
            'id': c.id,
            'nombre': c.name,
            'padre_id': c.parent_id.id or None,
            'secuencia': c.sequence,
            'url': f'/shop/category/{slug(c)}',
            'seo': {'titulo': c.website_meta_title or '', 'descripcion': c.website_meta_description or ''},
        } for c in categorias]

        items = []
        for producto in productos:
            precio = precios.get(producto.id, {}).get('price_reduce', producto.list_price)
            categorias_producto = producto.public_categ_ids.filtered(lambda c: c in categorias)
            modo = self._dcasa_tienda_modo_compra(producto)
            json_ld = [producto._to_markup_data(self)]
            if categorias_producto:
                json_ld.append(migas._prepare_breadcrumb_markup_data(
                    self.get_base_url(), categorias_producto[:1], producto.name))
            if not website_dcasa_main.PUBLICAR_DISPONIBILIDAD:
                json_ld = website_dcasa_main._sin_disponibilidad(json_ld)
            variantes = []
            if modo == 'variantes':
                for variante in producto.product_variant_ids:
                    info = variante._get_combination_info_variant()
                    disponible, existencias = self._dcasa_tienda_disponibilidad(variante)
                    variantes.append({
                        'id': variante.id,
                        'nombre': variante.product_template_attribute_value_ids._get_combination_name(),
                        'precio': info['price'],
                        'disponible': disponible,
                        'existencias': existencias,
                    })
            disponible, existencias = self._dcasa_tienda_disponibilidad(producto.product_variant_id)
            if variantes and disponible is not None:
                disponible = any(v['disponible'] for v in variantes)
                existencias = sum(v['existencias'] or 0 for v in variantes)
            tiene_imagen = bool(producto.sudo().with_context(bin_size=True).image_1920)
            items.append({
                'id': producto.id,
                'nombre': producto.name,
                'codigo': producto.default_code or '',
                'url': producto.website_url,
                'precio': precio,
                'precio_lista': producto.list_price,
                'precio_visible': bool(precio or not self.prevent_zero_price_sale),
                'mas_itbms': self._dcasa_mas_itbms(producto),
                'moneda': self.currency_id.name,
                'categorias': categorias_producto.ids,
                'descripcion_html': str(producto.description_ecommerce or ''),
                'descripcion_corta': producto.description_sale or '',
                'imagen': {t: self.image_url(producto, t) for t in TAMANOS_IMAGEN} if tiene_imagen else None,
                'galeria': [self.image_url(img, 'image_1024') for img in producto.product_template_image_ids],
                'seo': {
                    'titulo': producto.website_meta_title or '',
                    'descripcion': producto.website_meta_description or '',
                },
                'json_ld': json_ld,
                'compra': modo,
                'variantes': variantes,
                'disponible': disponible,
                'existencias': existencias,
                'whatsapp': self._dcasa_whatsapp_producto(producto),
                'secuencia': producto.website_sequence,
            })

        reglas = reglas_socios.cargar_reglas()
        portada = self.env['website.page'].sudo().search(
            [('url', '=', '/'), ('website_id', 'in', (False, self.id))], order='website_id', limit=1)
        para_dormir = self._dcasa_productos(limit=8, categorias=['recamaras', 'colchones'])
        company = self.company_id
        paginas = {}
        for ruta, pagina in website_dcasa_main.PAGINAS_LEGALES.items():
            paginas[ruta] = {
                'titulo': pagina['titulo'],
                'descripcion': pagina['descripcion'],
                'actualizado': pagina['actualizado'],
                'html': str(self.env['ir.qweb']._render(pagina['cuerpo'], {})),
            }
        return {
            'version': VERSION_FEED,
            'generado': fields.Datetime.now().isoformat(timespec='seconds') + 'Z',
            'sitio': {
                'nombre': self.name,
                'url_base': base,
                'moneda': self.currency_id.name,
                'whatsapp': self._dcasa_whatsapp_url(),
                'publicar_disponibilidad': bool(website_dcasa_main.PUBLICAR_DISPONIBILIDAD),
                'por_pagina': self.shop_ppg or 21,
                'json_ld_tienda': json.loads(self._dcasa_json_ld()),
                'json_ld_organizacion': json.loads(self._dcasa_json_ld_organizacion()),
            },
            'empresa': {
                'nombre': company.name,
                'ruc': company.vat or '',
                'calle': ', '.join(filter(None, [company.street, company.street2])),
                'ciudad': company.city or '',
                'telefono': company.phone or '',
                'email': company.email or '',
                'latitud': website_dcasa_main.LATITUD,
                'longitud': website_dcasa_main.LONGITUD,
            },
            'socios': {
                'puntos_por_dolar': (reglas.get('acumulacion') or {}).get('puntosPorDolar'),
                'puntos_al_padrino': (reglas.get('referido') or {}).get('puntosAlPadrino'),
                'puntos_al_ahijado': (reglas.get('referido') or {}).get('puntosAlAhijado'),
            },
            'portada': {
                'seo': {
                    'titulo': (portada.website_meta_title if portada else '') or '',
                    'descripcion': (portada.website_meta_description if portada else '') or '',
                },
                'categorias': self._dcasa_categorias(),
                'mas_buscados': [i['producto'].id for i in self._dcasa_productos(limit=8)],
                'para_dormir': [i['producto'].id for i in para_dormir],
                'para_dormir_url': self._dcasa_categoria_url('recamaras'),
            },
            'tienda': {'descripcion': DESCRIPCION_TIENDA},
            'categorias': datos_categorias,
            'productos': items,
            'paginas': paginas,
        }
