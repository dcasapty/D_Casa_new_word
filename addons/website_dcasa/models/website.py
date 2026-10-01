import json
import math
import os
from urllib.parse import quote, urlsplit

from markupsafe import Markup

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

# Hosts que nunca deben salir en los datos estructurados: son de la máquina, no del sitio.
HOSTS_LOCALES = ('localhost', '0.0.0.0', '::1')

# Título y descripción de la portada para Google. Solo categorías que el catálogo tiene de
# verdad (dcasa_catalogo/data/catalogo.json: no hay comedores) y nada de financiamiento
# mientras no exista (regla 4: no inventar).
SEO_PORTADA = {
    'website_meta_title': "Mueblería en La Chorrera | D'CASA Panamá",
    'website_meta_description': (
        'Recámaras, colchones, zapateras, muebles de TV, estantes y escritorios con precios claros '
        'en La Chorrera. Entrega a todo Panamá. Escríbenos por WhatsApp.'),
}
# Valores que se pueden pisar: vacíos, los de ejemplo de Odoo y los anteriores de D'CASA.
# Lo que la dueña escriba desde el editor (Sitio web > SEO) no se toca.
SEO_PORTADA_REEMPLAZABLES = {
    'website_meta_title': {'', "Mueblería en La Chorrera | D'CASA Panamá"},
    'website_meta_description': {
        '',
        'This is the homepage of the website',
        'Esta es la página principal del sitio web',
        'Esta es la página de inicio del sitio web',
        'Salas, recámaras, colchones y comedores con precios claros en La Chorrera. '
        'Entrega a todo Panamá y financiamiento. Escríbenos por WhatsApp.',
    },
}

# Promesas sin respaldo que versiones anteriores publicaron (SW-03): si quedaron copiadas en
# una vista del sitio (bloque guardado desde el editor, copia por sitio), se reemplazan por el
# texto nuevo. Solo coincidencias exactas: lo que la dueña haya reescrito se respeta.
PROMESAS_RETIRADAS = [
    ('<span class="d-none d-md-inline"><i class="fa fa-credit-card me-2" aria-hidden="true"/>'
     'Financiamiento flexible</span>',
     '<span class="d-none d-md-inline"><i class="fa fa-map-marker me-2" aria-hidden="true"/>'
     'Tienda en La Chorrera</span>'),
    ('<li><i class="fa fa-credit-card" aria-hidden="true"/><span><strong>Financiamiento.</strong> '
     'Crédito flexible, te explicamos cómo.</span></li>',
     ''),
    ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect x="3" y="7" width="26" height="18" rx="3"/>'
     '<path d="M3 13h26M8 20h6"/></svg>',
     '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 29s-9-8.5-9-15a9 9 0 0 1 18 0c0 6.5-9 15-9 15z"/>'
     '<circle cx="16" cy="14" r="3.2"/></svg>'),
    ('<strong>Financiamiento</strong><span>Crédito flexible para que amueblar no te apriete.</span>',
     '<strong>Míralo en tienda</strong><span>Visítanos en La Chorrera y pruébalo antes de llevártelo.</span>'),
    ('Varias, y también financiamiento flexible. Escríbenos y te explicamos la que mejor te sirve.',
     'Transferencia bancaria, Yappy, o pagas al recibir o en la tienda. Escríbenos y te explicamos '
     'la que mejor te sirve.'),
    ('Pagas al recibir o en la tienda: efectivo, Yappy o tarjeta.',
     'Pagas al recibir o en la tienda: efectivo o Yappy.'),
]

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

    def _dcasa_mas_itbms(self, producto):
        """¿Va «+ ITBMS» junto al precio? Sí, si la tienda muestra el precio sin impuesto y el
        producto lleva ITBMS: los precios de D'CASA son sin ITBMS y el 7 % se suma en el carrito."""
        self.ensure_one()
        return bool(
            self.show_line_subtotals_tax_selection == 'tax_excluded'
            # sudo: el visitante no lee impuestos; solo se pregunta si el producto lleva alguno.
            and producto.sudo().taxes_id._filter_taxes_by_company(self.company_id)
        )

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

    def _dcasa_url_publica(self):
        """URL pública del sitio para los datos estructurados; '' si solo hay una local.

        Sale de ``website.domain`` o, si está vacío, del parámetro ``web.base.url``
        (``get_base_url``). En el despliegue hay que fijar ``web.base.url`` con el dominio
        real (https://…) y ``web.base.url.freeze = True``: sin el «freeze», Odoo lo reescribe
        con la URL desde la que entra el administrador. Si aun así quedara una URL local
        (localhost, 127.x…), los JSON-LD salen sin URLs absolutas antes que mandarle a Google
        una dirección de la máquina.
        """
        self.ensure_one()
        base = (self.get_base_url() or '').rstrip('/')
        host = (urlsplit(base).hostname or '').lower()
        if not host or host in HOSTS_LOCALES or host.startswith('127.') or host.endswith('.localhost'):
            return ''
        return base

    def _dcasa_json_ld_organizacion(self, company=None):
        """JSON-LD ``Organization`` de todas las páginas (reemplaza el de website_sale).

        El de Odoo arma el JSON a mano con ``t-out``, que escapa para HTML: «D'CASA» salía como
        ``D&#39;CASA`` dentro del JSON y Google lee el texto literal. Aquí va como JSON seguro
        para <script> (json_scriptsafe), y la URL nunca es la de una máquina local.
        """
        self.ensure_one()
        company = company or self.company_id
        base = self._dcasa_url_publica()
        datos = {
            '@context': 'https://schema.org',
            '@type': 'Organization',
            'name': company.name,
        }
        if base:
            datos['url'] = base
            datos['logo'] = f'{base}/logo.png?company={company.id}'
        return json_scriptsafe.dumps(datos, ensure_ascii=False)

    def _dcasa_json_ld(self):
        """Datos estructurados FurnitureStore para Google (tienda local).

        JSON seguro dentro de <script> (escapa <, >, & y U+2028/9) con el helper de Odoo.
        """
        self.ensure_one()
        company = self.company_id
        base = self._dcasa_url_publica()  # '' si solo hay una URL local: sin URLs absolutas
        datos = {
            '@context': 'https://schema.org',
            '@type': 'FurnitureStore',
            '@id': base and f'{base}/#tienda',
            'name': company.name,
            'url': base,
            'logo': base and base + self.image_url(self, 'logo'),
            'image': base and f'{base}/website_dcasa/static/src/img/hero.webp',
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

    @api.model
    def _dcasa_seo_portada(self):
        """Título y descripción de la portada en todos los idiomas y en todas sus copias.

        Odoo crea una copia de la portada por sitio (``_bootstrap_homepage``) con su descripción
        de ejemplo, y la carga de traducciones pone la suya en español: un registro de datos sobre
        ``website.homepage_page`` no llegaba a lo que ve Google. Se corre en cada actualización y
        solo pisa valores vacíos, de ejemplo o anteriores de D'CASA.
        """
        idiomas = list(dict.fromkeys(['en_US', *(c for c, _n in self.env['res.lang'].get_installed())]))
        paginas = self.env['website.page'].sudo().with_context(active_test=False).search([('url', '=', '/')])
        for pagina in paginas:
            for idioma in idiomas:
                en_idioma = pagina.with_context(lang=idioma)
                valores = {
                    campo: valor for campo, valor in SEO_PORTADA.items()
                    if (en_idioma[campo] or '').strip() in SEO_PORTADA_REEMPLAZABLES[campo]
                    and en_idioma[campo] != valor
                }
                if valores:
                    en_idioma.write(valores)

    @api.model
    def _dcasa_retirar_promesas(self):
        """Quita las promesas sin respaldo (SW-03) de lo que quedó copiado fuera de las plantillas.

        Vistas por sitio (copias y bloques guardados desde el editor) y el mensaje del pago al
        recibir. Las plantillas del módulo ya traen el texto nuevo. Devuelve cuántos registros
        cambió.
        """
        idiomas = list(dict.fromkeys(['en_US', *(c for c, _n in self.env['res.lang'].get_installed())]))
        # Todas las promesas viejas de las vistas dicen «financiamiento»; se busca en todos los
        # idiomas a la vez (el texto traducido vive en el jsonb de arch_db).
        self.env['ir.ui.view'].flush_model(['arch_db', 'website_id', 'type'])
        self.env.cr.execute("""
            SELECT id FROM ir_ui_view
             WHERE website_id IS NOT NULL AND type = 'qweb' AND arch_db::text ILIKE '%%financiamiento%%'
        """)
        View = self.env['ir.ui.view'].sudo().with_context(active_test=False, no_cow=True)
        registros = [(vista, 'arch_db') for vista in View.browse(r[0] for r in self.env.cr.fetchall())]
        cod = self.env.ref('delivery.payment_provider_cod', raise_if_not_found=False)
        if cod:
            registros.append((cod.sudo(), 'pending_msg'))
        cambiados = 0
        for registro, campo in registros:
            tocado = False
            for idioma in idiomas:
                texto = registro.with_context(lang=idioma)[campo] or ''
                nuevo = str(texto)
                for viejo, reemplazo in PROMESAS_RETIRADAS:
                    nuevo = nuevo.replace(viejo, reemplazo)
                if nuevo != str(texto):
                    registro.with_context(lang=idioma).write(
                        {campo: Markup(nuevo) if isinstance(texto, Markup) else nuevo})
                    tocado = True
            cambiados += tocado
        return cambiados
