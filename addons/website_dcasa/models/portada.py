"""Portada: el carrusel del hero con productos propios y la sección «de cine» (pedido de la dueña, 2026-11-16).

* **Carrusel del hero** (``dcasa.portada.diapositiva``): la dueña quiere fotos propias que «se vean muy bien», en
  carrusel («algo dinámico, interactivo, que cambie»). Qué productos salen y en qué orden se elige en el panel
  (Sitio web › Carrusel de la portada, Gerencia y administradores), sin tocar código. Vacío = el hero de siempre (la
  foto con el texto encima). Cada diapositiva es la foto principal del producto, su nombre de cliente y un enlace a
  su ficha; solo salen los productos que un visitante puede comprar (publicados y a la venta en el sitio) y con foto.
* **Sección «de cine»** (``website._dcasa_cine``): dos cintas de fotos que corren solas a media portada, sacadas del
  catálogo publicado por categoría (camas, colchones, salas…), con un botón al catálogo. Nada se escribe a mano.

Las plantillas están en ``views/homepage_templates.xml`` (``hero_carrusel``, ``seccion_cine``) y el movimiento en
``static/src/js/portada.js``.
"""
import logging
import math

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.http import request

from .website import CATEGORIAS_PORTADA

_logger = logging.getLogger(__name__)

# Diapositivas que se muestran como mucho: más no se alcanzan a ver y cada una es una foto grande.
MAX_DIAPOSITIVAS = 8
# Anchos de la foto del hero (WebP de /dcasa/img, models/imagen.py) y el ancho con que se pinta.
ANCHOS_HERO = (512, 1024, 1600)
TAMANOS_HERO = '(min-width: 992px) 40vw, 92vw'

# Sección «de cine»: de qué categorías salen las fotos (en este orden, intercaladas) y cuántas de cada una.
CATEGORIAS_CINE = ('recamaras', 'colchones', 'salas', 'zapateras', 'organizacion', 'oficina')
POR_CATEGORIA_CINE = 4
# Con menos fotos que esto la sección no sale: una cinta de dos o tres fotos repetidas se ve pobre.
MINIMO_CINE = 4
# Cada cinta repite su lista hasta tener al menos este número de fotos por vuelta (llena una pantalla ancha).
FOTOS_POR_VUELTA = 8
SEGUNDOS_POR_FOTO = 4.5
# El orden de la tienda (el mismo de los carriles de la portada, ``website._dcasa_productos``).
ORDEN_CATALOGO = 'website_sequence asc, id desc'

_MEMO = '_dcasa_hero_carrusel'

# Las camas que la dueña aprobó para el carrusel (2026-11-16, con la hoja de fotos de producción a la vista: «sí, están
# bien»), por su código público («DC-…», el que sale en la ficha), en este orden: Cama Queen Color Black (la «300-300»),
# Cama King Rosada (la «801»), Cama Queen Black 805, Cama Queen Beige 805, Cama Queen Light Gray 805, Cama Queen Ivory
# 8017-1002-Q, Cama King Dark Grey y Cama King Ivory. El carrusel nace con ellas UNA sola vez (``_dcasa_sembrar``); lo
# que no exista en la base (una copia local, staging) se salta.
CARRUSEL_INICIAL = ('DC-ZKXSHJ', 'DC-SVQ7QF', 'DC-VTQJDJ', 'DC-2THJMG', 'DC-7RFSYH', 'DC-YY9N99', 'DC-FQNH3X',
                    'DC-STGW72')
# Ya se sembró (fecha): no se vuelve a hacer aunque Gerencia vacíe la lista después.
PARAM_SEMBRADO = 'website_dcasa.carrusel_sembrado'


class DcasaPortadaDiapositiva(models.Model):
    _name = 'dcasa.portada.diapositiva'
    _description = 'Producto del carrusel de la portada'
    _order = 'sequence, id'

    sequence = fields.Integer('Orden', default=10)
    website_id = fields.Many2one('website', 'Sitio', required=True, ondelete='cascade', index=True,
                                 default=lambda self: self.env['website'].get_current_website())
    product_tmpl_id = fields.Many2one(
        'product.template', 'Producto', required=True, ondelete='cascade', index=True,
        domain="[('sale_ok', '=', True), ('is_published', '=', True)]",
        help='Su foto principal, su nombre y un botón a su ficha salen en la portada.')
    default_code = fields.Char('Referencia', related='product_tmpl_id.default_code')
    imagen = fields.Image('Foto', related='product_tmpl_id.image_128')
    is_published = fields.Boolean('Publicado', related='product_tmpl_id.is_published')
    en_portada = fields.Boolean(
        'Sale en la portada', compute='_compute_en_portada',
        help='Solo salen los productos publicados y a la venta en el sitio, con foto.')

    _producto_unico = models.Constraint('unique(website_id, product_tmpl_id)', 'Ese producto ya está en el carrusel.')

    @api.model
    def _dcasa_sembrar(self):
        """El carrusel nace con las camas que aprobó la dueña (``CARRUSEL_INICIAL``), una sola vez.

        Corre al instalar y en cada actualización del módulo (data/portada_data.xml), pero solo hace algo la primera
        vez: deja la marca ``PARAM_SEMBRADO`` y desde ahí la lista es de Gerencia (cambiarla, reordenarla o vaciarla
        para volver al hero de siempre). Solo llena la lista de un sitio que la tenga vacía; los códigos que no existen
        se saltan sin error. Devuelve cuántas diapositivas creó.
        """
        Param = self.env['ir.config_parameter'].sudo()
        if Param.get_param(PARAM_SEMBRADO):
            return 0
        Diapositiva = self.sudo()
        Producto = self.env['product.template'].sudo()
        productos = []
        for codigo in CARRUSEL_INICIAL:
            producto = Producto.search([('dcasa_codigo_publico', '=', codigo)], limit=1)
            if producto and producto not in productos:
                productos.append(producto)
        creadas = 0
        for sitio in self.env['website'].sudo().search([]):
            if Diapositiva.search_count([('website_id', '=', sitio.id)], limit=1):
                continue
            for orden, producto in enumerate(productos, start=1):
                Diapositiva.create({'website_id': sitio.id, 'product_tmpl_id': producto.id, 'sequence': orden * 10})
                creadas += 1
        Param.set_param(PARAM_SEMBRADO, fields.Datetime.to_string(fields.Datetime.now()))
        _logger.info("D'CASA portada: carrusel sembrado con %s diapositiva(s) (%s de %s camas encontradas).",
                     creadas, len(productos), len(CARRUSEL_INICIAL))
        return creadas

    @api.depends('product_tmpl_id.is_published', 'product_tmpl_id.sale_ok', 'product_tmpl_id.image_128',
                 'product_tmpl_id.active')
    def _compute_en_portada(self):
        for diapositiva in self:
            producto = diapositiva.product_tmpl_id
            diapositiva.en_portada = bool(producto and producto.active and producto.sale_ok and producto.is_published
                                          and producto.image_128)


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_hero_firma(self):
        """Lo que define el carrusel de este sitio (productos y orden): va en la clave de la caché de la portada."""
        self.ensure_one()
        return tuple(self.env['dcasa.portada.diapositiva'].sudo().search(
            [('website_id', '=', self.id)]).mapped('product_tmpl_id').ids)

    def _dcasa_hero_carrusel(self):
        """Diapositivas del hero, en el orden del panel: el producto, su nombre de cliente, su ficha y su foto grande
        (``srcset`` en WebP, ``srcset_respaldo`` y ``src`` de Odoo).

        Vacío (el hero de siempre) si nadie eligió productos o si ninguno se puede mostrar: sin publicar, fuera de la
        venta en el sitio, archivado o sin foto. La precarga de la cabecera y la portada lo piden en la misma
        petición: se calcula una vez.
        """
        self.ensure_one()
        memo = getattr(request, _MEMO, None) if request else None
        if memo is not None and self.id in memo:
            return memo[self.id]
        ids = list(self._dcasa_hero_firma())
        diapositivas = []
        if ids:
            dominio = Domain.AND([self._dcasa_dominio_publicado(), [('id', 'in', ids)]])
            visibles = {p.id: p for p in self.env['product.template'].search(dominio)}
            for producto in (visibles[i] for i in ids if i in visibles):
                # La foto grande: WebP del ancho justo (/dcasa/img) y, de respaldo, el JPEG/PNG de Odoo a 512-1920 px.
                webp = self._dcasa_img_srcset(producto, ANCHOS_HERO)
                if not (webp or producto.with_context(bin_size=True).image_1920):
                    continue
                diapositivas.append({
                    'producto': producto,
                    'nombre': producto._dcasa_nombre_cliente(),
                    'url': producto.website_url,
                    'srcset': webp,
                    'srcset_respaldo': ', '.join(
                        f'{self.image_url(producto, f"image_{ancho}")} {ancho}w' for ancho in (512, 1024, 1920)),
                    'sizes': TAMANOS_HERO,
                    'src': self.image_url(producto, 'image_1024'),
                })
                if len(diapositivas) == MAX_DIAPOSITIVAS:
                    break
        if request:
            if memo is None:
                memo = {}
                setattr(request, _MEMO, memo)
            memo[self.id] = diapositivas
        return diapositivas

    def _dcasa_cine(self):
        """Fotos de la sección «de cine»: productos publicados con foto, por categoría e intercalados.

        Lo que ya enseñan los carriles de arriba («Lo más buscado» y «Para dormir mejor») no se repite: la cinta es para
        darse una vuelta por lo demás (si así no alcanza, se usa todo el catálogo). Devuelve ``None`` si no alcanzan
        (``MINIMO_CINE``); si alcanzan, las dos cintas: sus fotos, cuántas veces se repiten para cerrar la vuelta sin
        salto y cuánto dura una vuelta.
        """
        self.ensure_one()
        fotos = self._dcasa_cine_fotos(self._dcasa_ids_en_carriles())
        if len(fotos) < MINIMO_CINE:
            fotos = self._dcasa_cine_fotos(set())
        if len(fotos) < MINIMO_CINE:
            return None
        cintas = []
        for indice, lista in enumerate((fotos[0::2], fotos[1::2])):
            copias = 2 * math.ceil(FOTOS_POR_VUELTA / len(lista))
            # La segunda va un poco más lenta y al revés: las dos cintas no se mueven en bloque.
            segundos = len(lista) * copias / 2 * SEGUNDOS_POR_FOTO * (1.15 if indice else 1)
            cintas.append({'fotos': lista, 'copias': copias, 'duracion': f'{round(segundos)}s',
                           'reversa': bool(indice)})
        return {'cintas': cintas, 'total': len(fotos)}

    def _dcasa_ids_en_carriles(self):
        """Ids de lo que muestran los carriles de la portada (las mismas búsquedas que ``_dcasa_productos``)."""
        Producto = self.env['product.template']
        publicado = self._dcasa_dominio_publicado()
        ids = set(Producto.search(publicado, limit=8, order=ORDEN_CATALOGO).ids)
        dormir = [c.id for clave in ('recamaras', 'colchones') if (c := self._dcasa_categoria(clave))]
        if dormir:
            dominio = Domain.AND([publicado, [('public_categ_ids', 'child_of', dormir)]])
            ids.update(Producto.search(dominio, limit=8, order=ORDEN_CATALOGO).ids)
        return ids

    def _dcasa_cine_fotos(self, excluir):
        """Hasta ``POR_CATEGORIA_CINE`` productos con foto de cada categoría de ``CATEGORIAS_CINE``, intercalados (una
        cama, un colchón, una sala…), en el orden de la tienda y sin los de ``excluir``."""
        nombres = {clave: nombre for clave, nombre, _alt in CATEGORIAS_PORTADA}
        Producto = self.env['product.template']
        publicado = self._dcasa_dominio_publicado()
        vistos, por_categoria = set(excluir), []
        for clave in CATEGORIAS_CINE:
            categoria = self._dcasa_categoria(clave)
            if not categoria:
                continue
            dominio = Domain.AND([publicado, [('public_categ_ids', 'child_of', categoria.sudo().id),
                                              ('id', 'not in', list(vistos))]])
            # Algunos más de los que hacen falta: los que no tienen foto se saltan.
            candidatos = Producto.search(dominio, limit=POR_CATEGORIA_CINE * 3, order=ORDEN_CATALOGO)
            elegidos = [p for p in candidatos if self._dcasa_img_base(p)][:POR_CATEGORIA_CINE]
            vistos.update(p.id for p in elegidos)
            if elegidos:
                por_categoria.append((nombres.get(clave, categoria.sudo().name), elegidos))
        return [
            {'producto': lista[i], 'nombre': lista[i]._dcasa_nombre_cliente(), 'categoria': nombre}
            for i in range(POR_CATEGORIA_CINE) for nombre, lista in por_categoria if i < len(lista)
        ]
