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
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.http import request

from .website import CATEGORIAS_PORTADA

_logger = logging.getLogger(__name__)

# Diapositivas que se muestran como mucho: más no se alcanzan a ver y cada una es una foto grande.
MAX_DIAPOSITIVAS = 8
# Anchos de la foto del hero (WebP de /dcasa/img, models/imagen.py) y el ancho con que se pinta.
ANCHOS_HERO = (512, 1024, 1600)
TAMANOS_HERO = '(min-width: 992px) 58vw, 100vw'

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

# Cuánto dura cada foto del hero (la dueña, 2026-11-19: «demoran tal vez demasiado, 5 a 6 segundos… de unos 2 a 3
# segundos, o tal vez poderlo definir yo mismo»). De fábrica 3 s; Gerencia lo cambia en el panel, entre el mínimo y
# el máximo (más corto que 2 s marea; más largo que 15 s ya no se siente un fondo vivo). Se guarda en
# ``dcasa.portada.ajustes`` (uno por sitio), no en ``website``: así Gerencia no necesita escribir en el sitio.
SEGUNDOS_HERO_FABRICA = 3.0
SEGUNDOS_HERO_MINIMO = 2.0
SEGUNDOS_HERO_MAXIMO = 15.0
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
    # Los ajustes de su sitio (los segundos de cada foto): es el padre con que la pantalla «Carrusel de la portada»
    # arma su lista editable. Se deduce del sitio, así que quien crea una diapositiva solo con ``website_id`` (la
    # siembra, las pruebas) queda igual de bien puesta.
    ajustes_id = fields.Many2one('dcasa.portada.ajustes', 'Ajustes del sitio', compute='_compute_ajustes_id',
                                 store=True, readonly=False, ondelete='cascade', index=True)
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

    @api.depends('website_id')
    def _compute_ajustes_id(self):
        Ajustes = self.env['dcasa.portada.ajustes']
        for diapositiva in self:
            sitio = diapositiva.website_id
            if sitio and diapositiva.ajustes_id.website_id != sitio:
                diapositiva.ajustes_id = Ajustes._dcasa_del_sitio(sitio, crear=True)

    @api.constrains('ajustes_id', 'website_id')
    def _check_ajustes_del_sitio(self):
        for diapositiva in self:
            if diapositiva.ajustes_id and diapositiva.ajustes_id.website_id != diapositiva.website_id:
                raise ValidationError(self.env._('La diapositiva tiene que ser del mismo sitio que sus ajustes.'))

    @api.model_create_multi
    def create(self, vals_list):
        # Desde la lista de la pantalla del carrusel llega ``ajustes_id`` (su padre) y no el sitio: el sitio es el de
        # esos ajustes, no el «actual» que pondría el valor por defecto.
        if any(vals.get('ajustes_id') and not vals.get('website_id') for vals in vals_list):
            # Antes de mirar los ajustes con sudo: quien no puede crear no debe poder distinguir si un id existe.
            self.check_access('create')
        for vals in vals_list:
            if vals.get('ajustes_id') and not vals.get('website_id'):
                vals['website_id'] = self.env['dcasa.portada.ajustes'].sudo().browse(vals['ajustes_id']).website_id.id
        return super().create(vals_list)

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


class DcasaPortadaAjustes(models.Model):
    """Los ajustes del carrusel de la portada de un sitio: por ahora, los segundos que dura cada foto.

    Uno por sitio (``website_id`` único). Gerencia y los administradores lo cambian en «Sitio web › Carrusel de la
    portada», que es este formulario con la lista de productos debajo. Va en un modelo propio y no en ``website`` a
    propósito (revisión independiente, 2026-11-19): escribir en el sitio le abría a Gerencia, como superusuario, las
    acciones de servidor del sitio que Odoo deja sin grupo. Sin registro, o con un valor suelto en la base que no sirva,
    la portada usa los ``SEGUNDOS_HERO_FABRICA`` (``Website._dcasa_hero_segundos``).
    """
    _name = 'dcasa.portada.ajustes'
    _description = 'Ajustes del carrusel de la portada'
    _order = 'website_id'

    website_id = fields.Many2one('website', 'Sitio', required=True, ondelete='cascade', index=True,
                                 default=lambda self: self.env['website'].get_current_website())
    segundos = fields.Float(
        'Segundos que dura cada foto', default=SEGUNDOS_HERO_FABRICA, digits=(4, 1), required=True,
        help='Cuánto se queda cada foto de la portada antes de pasar a la siguiente (de 2 a 15 segundos; de fábrica '
             '3). El fundido y el zoom lento se ajustan solos a este tiempo.')
    diapositiva_ids = fields.One2many('dcasa.portada.diapositiva', 'ajustes_id', 'Productos del carrusel',
                                      help='Qué productos salen en el fondo de la portada y en qué orden. Vacío = el '
                                           'hero de siempre.')

    _sitio_unico = models.Constraint('unique(website_id)', 'Cada sitio tiene un solo juego de ajustes del carrusel.')

    @api.model
    def _dcasa_normalizar_segundos(self, valor):
        """Los segundos como número entre el mínimo y el máximo, o ``ValidationError`` en palabras sencillas.

        Por RPC llega de todo: texto, ``None``, NaN, infinito, números enormes. Se revisa ANTES de que el ORM intente
        convertirlo (que daría ``ValueError`` u ``OverflowError``), y con el redondeo a un decimal que ya hace el campo.
        """
        error = ValidationError(self.env._(
            'Los segundos que dura cada foto van de %(minimo)s a %(maximo)s. Escribe un número en ese rango.',
            minimo=f'{SEGUNDOS_HERO_MINIMO:g}', maximo=f'{SEGUNDOS_HERO_MAXIMO:g}'))
        if isinstance(valor, bool) or valor is None or isinstance(valor, (list, dict, tuple, set)):
            raise error
        try:
            numero = float(valor)
        except (TypeError, ValueError, OverflowError):
            raise error from None
        if not math.isfinite(numero) or not SEGUNDOS_HERO_MINIMO <= round(numero, 1) <= SEGUNDOS_HERO_MAXIMO:
            raise error
        return round(numero, 1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'segundos' in vals:
                vals['segundos'] = self._dcasa_normalizar_segundos(vals['segundos'])
        return super().create(vals_list)

    def write(self, vals):
        if 'website_id' in vals and any(ajustes.website_id.id != vals['website_id'] for ajustes in self):
            # Las diapositivas cuelgan de sus ajustes y deben ser del mismo sitio: mover los ajustes de sitio dejaría
            # diapositivas de un sitio colgando de los ajustes de otro. Para otro sitio se crean ajustes nuevos.
            raise ValidationError(self.env._(
                'Los ajustes del carrusel no se pasan a otro sitio: cada sitio tiene los suyos.'))
        if 'segundos' in vals:
            vals = {**vals, 'segundos': self._dcasa_normalizar_segundos(vals['segundos'])}
        return super().write(vals)

    @api.constrains('segundos')
    def _check_segundos(self):
        for ajustes in self:
            valor = ajustes.segundos
            if not math.isfinite(valor) or not SEGUNDOS_HERO_MINIMO <= valor <= SEGUNDOS_HERO_MAXIMO:
                raise ValidationError(self.env._(
                    'Los segundos que dura cada foto van de %(minimo)s a %(maximo)s.',
                    minimo=f'{SEGUNDOS_HERO_MINIMO:g}', maximo=f'{SEGUNDOS_HERO_MAXIMO:g}'))

    @api.model
    def _dcasa_del_sitio(self, sitio, crear=False):
        """Los ajustes de ``sitio`` (vacíos si no hay y no se pide crearlos). Siempre en sudo: lo usa la portada pública
        y la siembra, y lo que se lee o crea aquí son solo los segundos del sitio que se pide."""
        Ajustes = self.sudo()
        ajustes = Ajustes.search([('website_id', '=', sitio.id)], limit=1)
        if not ajustes and crear:
            ajustes = Ajustes.create({'website_id': sitio.id})
        return ajustes

    @api.model
    def action_abrir(self):
        """El menú «Carrusel de la portada»: abre los ajustes del sitio actual (los crea con el valor de fábrica si
        faltan): los segundos arriba y la lista de productos debajo."""
        sitio = self.env['website'].get_current_website()
        ajustes = self.search([('website_id', '=', sitio.id)], limit=1) or self.create({'website_id': sitio.id})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Carrusel de la portada'),
            'res_model': self._name,
            'res_id': ajustes.id,
            'view_mode': 'form',
            'views': [(self.env.ref('website_dcasa.view_dcasa_portada_ajustes_form').id, 'form')],
            'target': 'current',
        }


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_hero_segundos(self):
        """Los segundos de cada foto del hero: los de los ajustes del sitio o, si no hay ajustes o el valor no sirve
        (no es un número finito, o está fuera de rango: solo cabe en la base por SQL a mano), los de fábrica."""
        self.ensure_one()
        ajustes = self.env['dcasa.portada.ajustes']._dcasa_del_sitio(self)
        valor = ajustes.segundos if ajustes else SEGUNDOS_HERO_FABRICA
        if not math.isfinite(valor) or not SEGUNDOS_HERO_MINIMO <= valor <= SEGUNDOS_HERO_MAXIMO:
            return SEGUNDOS_HERO_FABRICA
        return valor

    def _dcasa_hero_tiempo(self):
        """El tiempo para la plantilla, tal cual lo lee el CSS y el JavaScript (``--vitrina-tiempo: 3s``)."""
        return f'{self._dcasa_hero_segundos():g}s'

    def _dcasa_hero_ids(self):
        """Los productos del carrusel de este sitio, en el orden del panel (sin mirar si se pueden mostrar)."""
        self.ensure_one()
        return tuple(self.env['dcasa.portada.diapositiva'].sudo().search(
            [('website_id', '=', self.id)]).mapped('product_tmpl_id').ids)

    def _dcasa_hero_firma(self):
        """Lo que define el carrusel de este sitio (productos, orden y segundos por foto): va en la clave de la caché
        de la portada, así cambiar cualquiera de los tres se ve al momento."""
        self.ensure_one()
        return self._dcasa_hero_ids(), self._dcasa_hero_segundos()

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
        ids = list(self._dcasa_hero_ids())
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
