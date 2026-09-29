import json
import math
import re
from urllib.parse import quote

from markupsafe import Markup

from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import reglas as reglas_socios
from odoo.fields import Domain
from odoo.http import request
from odoo.tools.misc import file_open

DEFAULT_WHATSAPP_MESSAGE = "Hola D'CASA, quiero información"

# Categorías de la portada: (xmlid, nombre, imagen, texto alternativo de la foto).
CATEGORIAS_PORTADA = [
    ('salas', 'Salas', 'cat-salas', 'Sala con sofá turquesa y mesa de centro de madera'),
    ('comedores', 'Comedores', 'cat-comedores', 'Mesa de comedor redonda de madera con silla'),
    ('recamaras', 'Recámaras', 'cat-recamaras', 'Recámara con cama de madera y ropa de cama terracota'),
    ('colchones', 'Colchones', 'cat-colchones', 'Recámara luminosa con cama y colchón'),
    ('decoracion', 'Decoración', 'cat-decoracion', 'Lámparas colgantes y sillas junto a una cortina'),
    ('exteriores', 'Exteriores', 'cat-exteriores', 'Terraza con muebles de exterior y plantas'),
]


class Website(models.Model):
    _inherit = 'website'

    dcasa_whatsapp_number = fields.Char(
        string='WhatsApp de ventas',
        help='Número con código de país, p. ej. +507 6026-1919. Lo usan los botones de WhatsApp del sitio. '
             'Si está vacío se usa el teléfono de la empresa.',
    )

    # ------------------------------------------------------------------
    # WhatsApp
    # ------------------------------------------------------------------

    def _dcasa_whatsapp_digits(self):
        self.ensure_one()
        number = self.dcasa_whatsapp_number or self.company_id.phone or ''
        return re.sub(r'\D', '', number)

    def _dcasa_whatsapp_url(self, message=None):
        """Link wa.me con mensaje precargado; '/contactus' si no hay número."""
        self.ensure_one()
        digits = self._dcasa_whatsapp_digits()
        if not digits:
            return '/contactus'
        return f'https://wa.me/{digits}?text={quote(message or DEFAULT_WHATSAPP_MESSAGE)}'

    def _dcasa_whatsapp_producto(self, product):
        """Mensaje de WhatsApp con el nombre del mueble ya escrito."""
        return self._dcasa_whatsapp_url(f"Hola D'CASA, me interesa: {product.display_name}")

    # ------------------------------------------------------------------
    # Menú
    # ------------------------------------------------------------------

    MENU_PRINCIPAL = [
        ('Catálogo', '/shop'),
        ("Socios D'CASA", '/socios'),
        ('Visítanos', '/#visitanos'),
    ]

    @api.model
    def _dcasa_armar_menu_principal(self):
        """Deja el menú de cada sitio con tres opciones (en vez de una por categoría).

        Las categorías siguen a mano en el catálogo (/shop) y en «Compra por espacio».
        """
        Menu = self.env['website.menu']
        for website in self.search([]):
            raiz = website.menu_id
            if not raiz:
                continue
            raiz.child_id.unlink()
            for orden, (nombre, url) in enumerate(self.MENU_PRINCIPAL, start=1):
                Menu.create({
                    'name': nombre, 'url': url, 'parent_id': raiz.id,
                    'website_id': website.id, 'sequence': orden * 10,
                })

    # ------------------------------------------------------------------
    # Portada
    # ------------------------------------------------------------------

    def _dcasa_categoria_url(self, clave):
        """URL canónica (con slug) de una categoría de la tienda; '/shop' si ya no existe.

        En sudo: el visitante no puede leer una categoría aún sin productos, y el enlace igual sirve.
        """
        categoria = self.env.ref(f'website_dcasa.public_category_{clave}', raise_if_not_found=False)
        return f"/shop/category/{self.env['ir.http']._slug(categoria.sudo())}" if categoria else '/shop'

    def _dcasa_categorias(self):
        """Tarjetas de «Compra por espacio»: la URL sale de la categoría real de la tienda."""
        self.ensure_one()
        tarjetas = []
        for clave, nombre, imagen, alt in CATEGORIAS_PORTADA:
            tarjetas.append({
                'nombre': nombre,
                'url': self._dcasa_categoria_url(clave),
                'imagen': f'/website_dcasa/static/src/img/{imagen}.webp',
                'alt': alt,
            })
        return tarjetas

    def _dcasa_productos(self, limit=8, categorias=None):
        """Productos publicados para los carruseles de la portada, con el mismo precio que la tienda.

        :param categorias: claves de categoría pública (p. ej. ``['colchones', 'recamaras']``).
        """
        self.ensure_one()
        # Solo publicados, también para quien edita: la portada muestra lo que ve el cliente.
        dominio = [self.sale_product_domain(), [('is_published', '=', True)]]
        if categorias:
            ids = [
                categoria.id for clave in categorias
                if (categoria := self.env.ref(f'website_dcasa.public_category_{clave}', raise_if_not_found=False))
            ]
            dominio.append([('public_categ_ids', 'child_of', ids)])
        productos = self.env['product.template'].search(Domain.AND(dominio), limit=limit,
                                                       order='website_sequence asc, id desc')
        # El precio de la tarifa del visitante necesita la petición web; sin ella, el de lista.
        con_tarifa = productos and request and hasattr(request, 'pricelist')
        precios = productos._get_sales_prices(self) if con_tarifa else {}
        return [{
            'producto': p,
            'precio': precios.get(p.id, {}).get('price_reduce', p.list_price),
            'directo': bool(con_tarifa) and self._dcasa_compra_directa(p),
        } for p in productos]

    def _dcasa_compra_directa(self, producto):
        """¿Se puede agregar al carrito sin pasar por la ficha?

        No, si hay que elegir algo (variantes, atributos configurables, combos) o si la tienda
        no permite comprarlo (precio cero bloqueado, tienda solo para usuarios registrados...).
        Mismas reglas que el botón «Agregar al carrito» de Odoo.
        """
        return bool(
            producto.product_variant_count == 1
            and not producto.has_configurable_attributes
            and producto.type != 'combo'
            and producto.product_variant_id._is_add_to_cart_allowed()
        )

    def _dcasa_resenas(self):
        """Opiniones reales de la ficha de Google (copia literal en data/resenas.json).

        La cinta necesita repetir la lista para cerrar el bucle sin salto: ``copias`` dice
        cuántas veces se imprime (par, y cada mitad con al menos 8 tarjetas para cubrir
        pantallas anchas). Solo la primera copia la leen los lectores de pantalla.
        """
        with file_open('website_dcasa/data/resenas.json') as archivo:
            datos = json.load(archivo)
        opiniones = [o for o in datos.get('opiniones', []) if (o.get('texto') or '').strip()]
        en_movimiento = len(opiniones) >= 3
        copias = 2 * max(1, math.ceil(8 / len(opiniones))) if en_movimiento else 1
        return {
            'ficha': datos['ficha'],
            'puntuacion': datos.get('puntuacion'),
            'total': datos.get('total'),
            'opiniones': opiniones,
            'en_movimiento': en_movimiento,
            'copias': copias,
            'duracion': f'{max(30, round(len(opiniones) * copias * 5.5))}s',
        }

    def _dcasa_reglas_socios(self):
        """Cifras del programa de socios, leídas de puntos.json (nunca escritas a mano)."""
        return reglas_socios.cargar_reglas()

    # ------------------------------------------------------------------
    # SEO
    # ------------------------------------------------------------------

    def _dcasa_json_ld(self):
        """Datos estructurados FurnitureStore para Google (tienda local)."""
        self.ensure_one()
        company = self.company_id
        base = self.get_base_url()
        datos = {
            '@context': 'https://schema.org',
            '@type': 'FurnitureStore',
            '@id': f'{base}/#tienda',
            'name': company.name,
            'url': base,
            'logo': f'{base}/web/image/website/{self.id}/logo',
            'image': f'{base}/website_dcasa/static/src/img/hero.webp',
            'telephone': company.phone,
            'email': company.email,
            'currenciesAccepted': company.currency_id.name,
            'address': {
                '@type': 'PostalAddress',
                'streetAddress': ', '.join(filter(None, [company.street, company.street2])),
                'addressLocality': company.city,
                'addressRegion': company.state_id.name or 'Panamá Oeste',  # La Chorrera
                'addressCountry': company.country_id.code or 'PA',
            },
            'sameAs': [url for url in (self.social_instagram, self.social_tiktok, self.social_facebook) if url],
        }
        # Sin campos vacíos (Google los marca como error). Nada de cifras inventadas (rango de precios).
        datos = {k: v for k, v in datos.items() if v}
        datos['address'] = {k: v for k, v in datos['address'].items() if v}
        # Dentro de <script>: «<», «>» y «&» como escapes JSON, así ningún texto cierra la etiqueta.
        texto = json.dumps(datos, ensure_ascii=False)
        texto = texto.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return Markup(texto)
