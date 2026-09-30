import json
import math
import os
from urllib.parse import quote

from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import reglas as reglas_socios
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools.json import scriptsafe as json_scriptsafe
from odoo.tools.misc import file_path

# La tienda en Google Maps (ficha «D'CASA», La Chorrera): la usan la página «Visítanos» y el JSON-LD.
LATITUD, LONGITUD = 8.8765881, -79.7867962

DEFAULT_WHATSAPP_MESSAGE = "Hola D'CASA, quiero información"

# Categorías de la portada: (xmlid, nombre, texto alternativo). La foto es static/src/img/cat-<xmlid>.webp.
CATEGORIAS_PORTADA = [
    ('salas', 'Salas', 'Sala con sofá turquesa y mesa de centro de madera'),
    ('recamaras', 'Recámaras', 'Cama king con cabecero tapizado'),
    ('colchones', 'Colchones', 'Recámara luminosa con cama y colchón'),
    ('zapateras', 'Zapateras', 'Mueble zapatera con puertas abatibles'),
    ('organizacion', 'Estantes', 'Estante de cocina con repisas de madera'),
    ('oficina', 'Oficina', 'Escritorio negro con repisa superior'),
]

# Menú principal: tres opciones. Las categorías viven dentro del catálogo (/shop).
MENU_PRINCIPAL = [
    ('Catálogo', '/shop'),
    ("Socios D'CASA", '/socios'),
    ('Visítanos', '/visitanos'),
]


def _es_menu_viejo(url):
    """Menús que el menú corto reemplaza: los de Odoo por defecto y los de una categoría."""
    url = url or ''
    return url in ('/', '/shop', '/contactus', '/socios', '/#visitanos') or url.startswith('/shop/category/')


_RESENAS = {'mtime': None, 'datos': None}


def _leer_resenas():
    """data/resenas.json, leído una vez y releído solo si el archivo cambia."""
    ruta = file_path('website_dcasa/data/resenas.json')
    mtime = os.path.getmtime(ruta)
    if _RESENAS['mtime'] != mtime:
        with open(ruta, encoding='utf-8') as archivo:
            _RESENAS['datos'] = json.load(archivo)
        _RESENAS['mtime'] = mtime
    return _RESENAS['datos']


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

    @api.constrains('dcasa_whatsapp_number')
    def _check_dcasa_whatsapp_number(self):
        """Un número inválido borraría en silencio todos los botones de WhatsApp del sitio."""
        for website in self.filtered('dcasa_whatsapp_number'):
            digitos = reglas_socios.solo_digitos(website.dcasa_whatsapp_number)
            if not (len(digitos) == 8 or 10 <= len(digitos) <= 15):
                raise ValidationError(self.env._(
                    'El WhatsApp de ventas debe ser un número, como +507 6026-1919 o 6026-1919.'))

    def _dcasa_whatsapp_url(self, message=None):
        """Link wa.me con mensaje precargado; '/contactus' si no hay número."""
        self.ensure_one()
        digits = reglas_socios.solo_digitos(self.dcasa_whatsapp_number or self.company_id.phone)
        if not digits:
            return '/contactus'
        if len(digits) == 8:  # número de Panamá sin el código de país
            digits = f'507{digits}'
        return f'https://wa.me/{digits}?text={quote(message or DEFAULT_WHATSAPP_MESSAGE)}'

    def _dcasa_whatsapp_producto(self, product):
        """Mensaje de WhatsApp con el nombre del mueble ya escrito."""
        return self._dcasa_whatsapp_url(f"Hola D'CASA, me interesa: {product.display_name}")

    # ------------------------------------------------------------------
    # Menú
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_armar_menu_principal(self):
        """Deja el menú de cada sitio en Catálogo · Socios D'CASA · Visítanos.

        Solo quita los menús que reemplaza (Inicio, Tienda, Contáctanos, uno por categoría) y
        no duplica: se puede volver a correr sin perder lo que la dueña agregó desde el editor.
        """
        Menu = self.env['website.menu']
        idiomas = [codigo for codigo, _nombre in self.env['res.lang'].get_installed()]
        nuestros = {url for _nombre, url in MENU_PRINCIPAL}
        for website in self.search([]):
            raiz = website.menu_id
            if not raiz:
                continue
            raiz.child_id.filtered(lambda m: _es_menu_viejo(m.url) and m.url not in nuestros).unlink()
            for orden, (nombre, url) in enumerate(MENU_PRINCIPAL, start=1):
                valores = {'name': nombre, 'sequence': orden * 10}
                menu = raiz.child_id.filtered(lambda m, url=url: m.url == url)[:1]
                if menu:
                    menu.write(valores)  # p. ej. «Shop» de Odoo pasa a «Catálogo»
                else:
                    menu = Menu.create(dict(valores, url=url, parent_id=raiz.id, website_id=website.id))
                # El nombre es traducible: el mismo en todos los idiomas (si no, en español
                # seguiría la traducción de Odoo, «Tienda»).
                menu.update_field_translations('name', dict.fromkeys(idiomas, nombre))

    # ------------------------------------------------------------------
    # Portada
    # ------------------------------------------------------------------

    def _dcasa_categoria(self, clave):
        return self.env.ref(f'website_dcasa.public_category_{clave}', raise_if_not_found=False)

    def _dcasa_categoria_url(self, clave):
        """URL canónica (con slug) de una categoría de la tienda; '/shop' si ya no existe.

        En sudo: el visitante no puede leer una categoría aún sin productos, y el enlace igual sirve.
        """
        categoria = self._dcasa_categoria(clave)
        return f"/shop/category/{self.env['ir.http']._slug(categoria.sudo())}" if categoria else '/shop'

    def _dcasa_categorias(self):
        """Tarjetas de «Compra por espacio»: la URL sale de la categoría real de la tienda."""
        self.ensure_one()
        return [{
            'nombre': nombre,
            'url': self._dcasa_categoria_url(clave),
            'imagen': f'/website_dcasa/static/src/img/cat-{clave}.webp',
            'alt': alt,
        } for clave, nombre, alt in CATEGORIAS_PORTADA]

    def _dcasa_dominio_publicado(self):
        """Lo que un visitante puede comprar: se vende en este sitio y está publicado.

        Lo usan los carruseles y el «Agregar» de un clic: los dos tienen que coincidir.
        """
        return Domain.AND([self.sale_product_domain(), [('is_published', '=', True)]])

    def _dcasa_productos(self, limit=8, categorias=None):
        """Productos publicados para los carruseles de la portada, con el mismo precio que la tienda.

        :param categorias: claves de categoría pública (p. ej. ``['colchones', 'recamaras']``).
        """
        self.ensure_one()
        dominio = self._dcasa_dominio_publicado()
        if categorias:
            ids = [c.id for clave in categorias if (c := self._dcasa_categoria(clave))]
            dominio = Domain.AND([dominio, [('public_categ_ids', 'child_of', ids)]])
        productos = self.env['product.template'].search(dominio, limit=limit, order='website_sequence asc, id desc')
        # El precio y la moneda de la tarifa del visitante necesitan la petición web; sin ella, los de lista.
        con_tarifa = bool(productos) and bool(request) and hasattr(request, 'pricelist')
        precios = productos._get_sales_prices(self) if con_tarifa else {}
        moneda = (request.pricelist.currency_id if con_tarifa else None) or self.currency_id
        # Sin petición no hay visitante ni carrito: nada se compra en un clic.
        acceso = con_tarifa and self.has_ecommerce_access()
        items = []
        for p in productos:
            precio = precios.get(p.id, {}).get('price_reduce', p.list_price)
            items.append({
                'producto': p,
                'precio': precio,
                'moneda': moneda,
                'directo': acceso and self._dcasa_compra_directa(p, precio),
            })
        return items

    def _dcasa_compra_directa(self, producto, precio=None):
        """¿Se puede agregar al carrito sin pasar por la ficha?

        No, si hay que elegir algo (variantes, atributos configurables, combos, opcionales) o si
        la tienda no deja comprarlo así (precio cero bloqueado). Son las reglas del botón de Odoo.
        Los carruseles pasan el ``precio`` ya calculado para no volver a pasar por la tarifa
        producto por producto; sin precio, esa regla la revisa quien llama.
        """
        return bool(
            producto.product_variant_count == 1
            and not producto.has_configurable_attributes
            and producto.type != 'combo'
            and not producto.optional_product_ids
            and (precio is None or precio or not self.prevent_zero_price_sale)
        )

    def _dcasa_resenas(self):
        """Opiniones reales de la ficha de Google (copia literal en data/resenas.json).

        La cinta necesita repetir la lista para cerrar el bucle sin salto: ``copias`` dice
        cuántas veces se imprime (par, y cada mitad con al menos 8 tarjetas para cubrir
        pantallas anchas). Solo la primera copia la leen los lectores de pantalla.
        Un archivo incompleto no tumba la portada: la sección simplemente no sale.
        """
        try:
            datos = _leer_resenas()
        except (OSError, ValueError):
            return {'opiniones': []}
        opiniones = [
            o for o in datos.get('opiniones', [])
            if (o.get('texto') or '').strip() and o.get('autor') and o.get('estrellas')
        ]
        if not opiniones or not datos.get('ficha'):
            return {'opiniones': []}
        copias = 2 * math.ceil(8 / len(opiniones)) if len(opiniones) >= 3 else 1
        return {
            'ficha': datos['ficha'],
            'puntuacion': datos.get('puntuacion'),
            'total': datos.get('total'),
            'opiniones': opiniones,
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
        """Datos estructurados FurnitureStore para Google (tienda local).

        JSON seguro dentro de <script> (escapa <, >, & y U+2028/9) con el helper de Odoo.
        """
        self.ensure_one()
        company = self.company_id
        base = self.get_base_url()
        datos = {
            '@context': 'https://schema.org',
            '@type': 'FurnitureStore',
            '@id': f'{base}/#tienda',
            'name': company.name,
            'url': base,
            'logo': base + self.image_url(self, 'logo'),
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
            'geo': {'@type': 'GeoCoordinates', 'latitude': LATITUD, 'longitude': LONGITUD},
            'hasMap': f'https://www.google.com/maps/search/?api=1&query={LATITUD}%2C{LONGITUD}',
            'sameAs': [url for url in (self.social_instagram, self.social_tiktok, self.social_facebook) if url],
        }
        # Sin campos vacíos (Google los marca como error). Nada de cifras inventadas (rango de precios).
        datos = {k: v for k, v in datos.items() if v}
        datos['address'] = {k: v for k, v in datos['address'].items() if v}
        return json_scriptsafe.dumps(datos, ensure_ascii=False)
