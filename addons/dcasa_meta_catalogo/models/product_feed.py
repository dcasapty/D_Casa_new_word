"""El catálogo para Meta (Facebook e Instagram): un CSV que Meta lee por URL de forma programada.

Se apoya en el ``product.feed`` de Odoo (el del feed de Google): el mismo registro, el mismo token y la misma caché
(``feed_cache`` / ``cache_expiry``), con ``target = 'meta'``. Lo propio (diseño §4, docs/META_CATALOGO.md):

* **Apagado de fábrica** (``dcasa_activo``): mientras no lo enciendan, la ruta no sirve nada.
* **Qué entra:** lo publicado y a la venta en el sitio (el mismo dominio de los carruseles), menos lo marcado «No
  anunciar en Facebook e Instagram», lo que no tiene foto y lo que tiene precio cero. Si el feed tiene categorías,
  solo esas.
* **Contrato con dcasa_meta_eventos** (píxel y Conversions API): ``id`` = ``str(product.product.id)``;
  ``item_group_id`` = ``g<product.template.id>`` solo si hay más de una variante. Nunca la referencia del
  proveedor (``default_code``), el código de barras ni el costo.
* **Precio:** el mismo número que dibuja la ficha (``_get_additionnal_combination_info`` del sitio, para un visitante
  anónimo): hoy sin ITBMS, con «+ ITBMS» en la página.
* **Caché:** el CSV se guarda en gzip en ``feed_cache`` y se vuelve a armar solo si cambió la huella (``dcasa_huella``:
  pocas consultas de cuántos y última modificación) o si pasó un día. Así no se reescribe el adjunto (R2) cada vez
  que Meta pregunta.
* ``/gmc.xml`` (el feed de Google) nunca sirve un feed de Meta.
"""
import base64
import csv
import gzip
import io
import logging
import re
import uuid
from contextlib import contextmanager
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from werkzeug.exceptions import NotFound

from odoo import api, fields, models
from odoo.addons.website_sale import const, utils
from odoo.addons.website_sale.models.website import (
    FISCAL_POSITION_SESSION_CACHE_KEY,
    PRICELIST_SELECTED_SESSION_CACHE_KEY,
    PRICELIST_SESSION_CACHE_KEY,
)
from odoo.exceptions import AccessError, LockError, UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import split_every

from . import reglas_meta as R

_logger = logging.getLogger(__name__)

RUTA = '/dcasa/meta/catalogo.csv'
COLUMNAS = (
    'id', 'item_group_id', 'title', 'description', 'availability', 'condition', 'price', 'sale_price',
    'sale_price_effective_date', 'link', 'image_link', 'additional_image_link', 'brand', 'product_type',
    'custom_label_0', 'custom_label_1', 'custom_label_2', 'custom_label_3', 'custom_label_4',
)
LOTE = 200               # variantes por lote: fotos y existencias por lote, no por producto
ANCHO_FOTO = 1024        # JPEG a 1024 px de ancho (Meta pide al menos 500 × 500)
FORMATO_FOTO = 'jpg'
MAX_FOTOS_EXTRA = 10     # additional_image_link: hasta 10
VIGENCIA = relativedelta(days=1)
GRUPOS_GERENCIA = ('sales_team.group_sale_manager', 'base.group_system')
_TOKEN = re.compile(r'[0-9a-f]{32}')
CLAVES_DE_SESION = (PRICELIST_SESSION_CACHE_KEY, PRICELIST_SELECTED_SESSION_CACHE_KEY,
                    FISCAL_POSITION_SESSION_CACHE_KEY)
_SIN_VALOR = object()


class ProductFeed(models.Model):
    _inherit = 'product.feed'

    target = fields.Selection(selection_add=[('meta', 'Meta (Facebook e Instagram)')], ondelete={'meta': 'cascade'})
    dcasa_activo = fields.Boolean(
        'Encendido', default=False, tracking=True,
        help='Apagado, la dirección no entrega nada y Meta no puede leer el catálogo. Viene apagado: enciéndelo '
             'cuando vayas a pegar la dirección en Meta (Commerce Manager › Orígenes de datos).')
    dcasa_marca = fields.Char(
        'Marca', default=lambda self: self.env.company.name, tracking=True,
        help='La marca que Meta muestra en cada producto. Viene con el nombre de la empresa; cámbiala si prefieres '
             'otra.')
    dcasa_condicion = fields.Selection(
        [('new', 'Nuevo'), ('refurbished', 'Reacondicionado'), ('used', 'Usado')],
        string='Condición', default='new', required=True, tracking=True,
        help='La condición de todos los productos del catálogo.')
    dcasa_disponibilidad = fields.Selection(
        [('web', 'Como la tienda en línea: todo lo publicado está disponible'),
         ('existencias', 'Según las existencias: lo que no tiene unidades sale agotado')],
        string='Disponibilidad', default='web', required=True, tracking=True,
        help='Mientras el inventario no esté confirmado, «Como la tienda en línea» (la web vende sin mirar las '
             'existencias). Cuando el inventario sea real, «Según las existencias».')
    dcasa_huella = fields.Char(
        'Huella del catálogo', readonly=True, copy=False,
        help='Técnico: resume lo que el catálogo usó la última vez que se armó.')
    dcasa_meta_en_catalogo = fields.Integer('En el catálogo', compute='_compute_dcasa_meta_conteos')
    dcasa_meta_fuera_sin_foto = fields.Integer('Fuera: sin foto', compute='_compute_dcasa_meta_conteos')
    dcasa_meta_fuera_sin_precio = fields.Integer('Fuera: sin precio', compute='_compute_dcasa_meta_conteos')
    dcasa_meta_fuera_marcados = fields.Integer(
        'Fuera: marcados para no anunciar', compute='_compute_dcasa_meta_conteos')

    # ------------------------------------------------------------------
    # Dirección, dominio y conteos
    # ------------------------------------------------------------------

    def _dcasa_meta_base(self):
        """La dirección pública ``https://…`` del sitio del feed, o '' (sitio local o sin https).

        Nunca se le da a Meta una dirección de la máquina ni un enlace sin cifrar.
        """
        self.ensure_one()
        base = self.website_id.sudo()._dcasa_url_publica() if self.website_id else ''
        return base if base.startswith('https://') else ''

    @api.depends('target', 'access_token', 'website_id', 'website_id.domain')
    def _compute_url(self):
        meta = self.filtered(lambda feed: feed.target == 'meta')
        super(ProductFeed, self - meta)._compute_url()
        for feed in meta:
            base = feed._dcasa_meta_base()
            feed.url = (
                f'{base}{RUTA}?{urlencode({"feed": feed.id, "token": feed.access_token})}'
                if base and feed.id and feed.access_token else False)

    def _dcasa_meta_sitio(self):
        """El sitio del feed visto por su visitante anónimo (el usuario público del sitio, con el contexto del sitio
        como en una página de la tienda), con sudo."""
        self.ensure_one()
        sitio = self.website_id.sudo()
        return sitio.with_user(sitio.user_id).with_context(website_id=sitio.id).sudo()

    def _dcasa_meta_dominio_base(self):
        """Lo que el catálogo publicaría sin mirar «No anunciar»: publicado y a la venta en el sitio para cualquier
        visitante (el mismo dominio de los carruseles y del «Agregar»), y de las categorías elegidas."""
        self.ensure_one()
        dominio = Domain.AND([self._dcasa_meta_sitio()._dcasa_dominio_publicado(), Domain('sale_ok', '=', True)])
        if self.product_category_ids:
            dominio &= Domain('public_categ_ids', 'child_of', self.product_category_ids.ids)
        return dominio

    def _get_feed_product_domain(self):
        """El dominio nativo (lo usa también el límite de 5,000 productos) para el feed de Meta."""
        if self.target != 'meta':
            return super()._get_feed_product_domain()
        return self._dcasa_meta_dominio_base() & Domain('dcasa_meta_no_anunciar', '=', False)

    def _dcasa_meta_candidatos(self):
        """Variantes que entrarían si tienen foto y precio, hasta el tope duro de Odoo (6,000)."""
        self.ensure_one()
        return self.env['product.product'].sudo().with_context(lang=self.lang_id.code).search(
            self._get_feed_product_domain(), order='id', limit=const.PRODUCT_FEED_HARD_LIMIT)

    def _dcasa_meta_marcados(self):
        """Productos (plantillas) publicados que alguien marcó «No anunciar»."""
        self.ensure_one()
        return self.env['product.template'].sudo().search(
            self._dcasa_meta_dominio_base() & Domain('dcasa_meta_no_anunciar', '=', True))

    def _dcasa_meta_tarifa(self, sitio):
        """La tarifa del visitante anónimo que llega por primera vez (o la elegida en el feed).

        Es la misma función que usa la ficha (``website._get_and_cache_current_pricelist``), como el usuario público
        SIN sudo y con ``request.website`` ya puesto, sin carrito y sin lo que recuerde la sesión de quien pide (lo
        quita ``_dcasa_meta_visitante``). La tarifa calculada del cliente público se descarta antes y después: no se
        mezcla con una calculada fuera del sitio.
        """
        self.ensure_one()
        if self.pricelist_id:
            return self.pricelist_id.sudo()
        publico = sitio.sudo(False)
        cliente = publico.env.user.partner_id
        cliente.invalidate_recordset(['property_product_pricelist'])
        try:
            return publico._get_and_cache_current_pricelist().sudo()
        finally:
            cliente.invalidate_recordset(['property_product_pricelist'])

    def _dcasa_meta_fotos(self, variantes):
        """``{variante.id: (foto principal, [fotos extra])}``: rutas ``/dcasa/img/…`` en JPEG a 1024 px.

        Son las mismas rutas que ``website._dcasa_img_url`` (una prueba lo compara), pero del lote entero en pocas
        consultas: ``_dcasa_img_url`` solo agrupa dentro de una petición web y por su orden de prefetch.
        """
        sitio = self.website_id.sudo()
        fuentes, extras = {}, {}
        for variante in variantes:
            fuentes[variante] = sitio._dcasa_img_fuente(variante)
            # El mismo orden que la galería de la ficha: fotos de la variante y después las del producto.
            imagenes = list(variante.product_variant_image_ids) + list(
                variante.product_tmpl_id.product_template_image_ids)
            extras[variante.id] = imagenes
            for imagen in imagenes:
                fuentes[imagen] = sitio._dcasa_img_fuente(imagen)
        adjuntos = sitio._dcasa_img_adjuntos([fuente for fuente in fuentes.values() if fuente])

        def ruta(registro):
            fuente = fuentes.get(registro)
            adjunto = adjuntos.get(fuente) if fuente else None
            if not adjunto or not adjunto.checksum:
                return ''
            return '/dcasa/img/{}/{}/{}'.format(*fuente) + f'/{ANCHO_FOTO}.{FORMATO_FOTO}?v={adjunto.checksum[:12]}'

        resultado = {}
        for variante in variantes:
            vistas = [r for r in (ruta(imagen) for imagen in extras[variante.id]) if r]
            resultado[variante.id] = (ruta(variante), vistas[:MAX_FOTOS_EXTRA])
        return resultado

    def _dcasa_meta_clasificar(self):
        """Reparte las variantes candidatas: las que van al catálogo y las que quedan fuera (sin foto o con precio de
        lista cero). Fotos por lotes de 200. La fila, además, se salta si el precio que dibuja la ficha es cero."""
        self.ensure_one()
        feed = self.sudo().with_context(lang=self.lang_id.code)
        Producto = feed.env['product.product']
        candidatos = feed._dcasa_meta_candidatos()
        moneda = feed.website_id.currency_id or feed.env.company.currency_id
        incluidos, sin_foto, sin_precio = [], [], []
        fotos = {}
        for lote in split_every(LOTE, candidatos.ids, candidatos.browse):
            posibles = lote.filtered(lambda variante: variante._is_variant_possible())
            fotos.update(feed._dcasa_meta_fotos(posibles))
            for variante in posibles:
                if not fotos[variante.id][0]:
                    sin_foto.append(variante.id)
                elif moneda.is_zero(variante.lst_price):
                    sin_precio.append(variante.id)
                else:
                    incluidos.append(variante.id)
        return {
            'incluidos': Producto.browse(incluidos),
            'sin_foto': Producto.browse(sin_foto),
            'sin_precio': Producto.browse(sin_precio),
            'fotos': fotos,
        }

    def _compute_dcasa_meta_conteos(self):
        campos = ('dcasa_meta_en_catalogo', 'dcasa_meta_fuera_sin_foto', 'dcasa_meta_fuera_sin_precio',
                  'dcasa_meta_fuera_marcados')
        for feed in self:
            if feed.target != 'meta' or not feed.id or not feed.website_id:
                feed.update(dict.fromkeys(campos, 0))
                continue
            reparto = feed._dcasa_meta_clasificar()
            feed.dcasa_meta_en_catalogo = len(reparto['incluidos'])
            feed.dcasa_meta_fuera_sin_foto = len(reparto['sin_foto'])
            feed.dcasa_meta_fuera_sin_precio = len(reparto['sin_precio'])
            feed.dcasa_meta_fuera_marcados = len(feed._dcasa_meta_marcados().product_variant_ids)

    # ------------------------------------------------------------------
    # El CSV
    # ------------------------------------------------------------------

    @contextmanager
    def _dcasa_meta_visitante(self):
        """La tienda como la ve un visitante anónimo, en la petición en curso.

        ``_get_additionnal_combination_info`` (el precio de la ficha) lee de ``request`` la tarifa y la posición
        fiscal. La ruta del CSV no pasa por la capa del sitio (pondría la cookie ``frontend_lang``), así que se ponen
        aquí, las del visitante anónimo, y al salir se deja la petición como estaba.
        """
        self.ensure_one()
        if not request:
            raise UserError(self.env._('El catálogo para Meta se arma dentro de una petición web.'))
        sitio = self._dcasa_meta_sitio()
        nombres = ('website', 'cart', 'pricelist', 'fiscal_position')
        antes = {nombre: getattr(request, nombre, _SIN_VALOR) for nombre in nombres}
        # Lo que la sesión de quien pide recuerda (una tarifa elegida, su posición fiscal) no entra en el catálogo.
        sesion = {clave: request.session.pop(clave) for clave in CLAVES_DE_SESION if clave in request.session}
        try:
            request.website = sitio
            request.cart = sitio.env['sale.order']
            request.pricelist = self._dcasa_meta_tarifa(sitio).with_env(sitio.env)
            request.fiscal_position = sitio.env['account.fiscal.position']._get_fiscal_position(
                sitio.user_id.partner_id)
            yield sitio
        finally:
            for nombre, valor in antes.items():
                if valor is _SIN_VALOR:
                    if hasattr(request, nombre):
                        delattr(request, nombre)
                else:
                    setattr(request, nombre, valor)
            for clave in CLAVES_DE_SESION:
                request.session.pop(clave, None)
            request.session.update(sesion)

    def _dcasa_meta_filas(self):
        """Una fila por variante que va al catálogo, en el orden de las columnas de Meta."""
        self.ensure_one()
        feed = self.sudo().with_context(lang=self.lang_id.code)
        base = feed._dcasa_meta_base()
        if not base:
            raise UserError(self.env._(
                'El sitio no tiene todavía una dirección pública https (web.base.url): el catálogo no se puede armar.'))
        reparto = feed._dcasa_meta_clasificar()
        idioma = ''
        if feed.lang_id and feed.lang_id != feed.website_id.default_lang_id:
            idioma = f'/{feed.lang_id.url_code}'
        hoy = fields.Date.context_today(feed)
        filas = []
        with feed._dcasa_meta_visitante() as sitio:
            variantes = reparto['incluidos'].with_env(sitio.env).with_context(lang=feed.lang_id.code)
            for lote in split_every(LOTE, variantes.ids, variantes.browse):
                for variante in lote:
                    fila = feed._dcasa_meta_fila(variante, sitio, hoy, base, idioma, reparto['fotos'][variante.id])
                    if fila:
                        filas.append(fila)
        return filas

    def _dcasa_meta_fila(self, variante, sitio, hoy, base, idioma, fotos):
        """La fila de una variante, con el precio que dibuja su ficha (``variante`` en el entorno del visitante)."""
        plantilla = variante.product_tmpl_id
        # Igual que la ficha y que el feed de Google de Odoo: el contexto de precio de la combinación.
        contexto = variante._get_product_price_context(variante.product_template_attribute_value_ids)
        info = variante.with_context(**contexto).product_tmpl_id._get_additionnal_combination_info(
            variante, quantity=1.0, uom=variante.uom_id, date=hoy, website=sitio)
        moneda = info['currency']
        if info['prevent_zero_price_sale'] or moneda.is_zero(info['price']):
            return None

        def precio(monto):
            return R.formato_precio(moneda.round(monto), moneda.name, moneda.decimal_places)

        # Existencias según dcasa_stock (lo de la plantilla, todas sus medidas); sin control de inventario, None.
        cantidad = plantilla.dcasa_stock if plantilla.is_storable else None
        nombre = R.titulo(variante.with_context(display_default_code=False).display_name)
        descripcion = R.texto_plano(plantilla.description_sale) or R.texto_plano(plantilla.description_ecommerce)
        categoria = plantilla.public_categ_ids.sorted(lambda c: (c.sequence, c.name or '', c.id))[:1]
        campana = plantilla.dcasa_meta_campana_id
        fila = dict.fromkeys(COLUMNAS, '')
        fila.update({
            'id': str(variante.id),
            'item_group_id': f'g{plantilla.id}' if plantilla.product_variant_count > 1 else '',
            'title': nombre,
            'description': descripcion or nombre,
            'availability': R.disponibilidad(self.dcasa_disponibilidad, cantidad),
            'condition': self.dcasa_condicion,
            'price': precio(info['list_price']),
            'link': f'{base}{idioma}{variante.website_url}',
            'image_link': f'{base}{fotos[0]}',
            'additional_image_link': ','.join(f'{base}{ruta}' for ruta in fotos[1]),
            'brand': R.titulo(self.dcasa_marca or '', 100, oracion=False),
            'product_type': ' > '.join(categoria.parents_and_self.mapped('name')) if categoria else '',
            'custom_label_0': R.etiqueta_ascii(categoria.name) if categoria else '',
            'custom_label_1': campana.codigo if campana.active else '',
            'custom_label_2': R.nivel_existencias(cantidad),
            'custom_label_3': R.banda_precio(moneda.round(info['list_price'])),
            'custom_label_4': plantilla.dcasa_codigo_publico or '',
        })
        if info['has_discounted_price']:
            fila['sale_price'] = precio(info['price'])
            inicio, fin = info['discount_start_date'], info['discount_end_date']
            if inicio and fin:
                # ISO 8601 como el feed de Google de Odoo (inicio/fin, en UTC).
                fila['sale_price_effective_date'] = f'{utils.gmc_format_date(inicio)}/{utils.gmc_format_date(fin)}'
        return fila

    def _dcasa_meta_csv(self):
        """El catálogo en CSV (UTF-8 sin BOM), con la cabecera en el orden de ``COLUMNAS``."""
        salida = io.StringIO()
        escritor = csv.DictWriter(salida, fieldnames=COLUMNAS, extrasaction='raise', lineterminator='\n')
        escritor.writeheader()
        escritor.writerows(self._dcasa_meta_filas())
        return salida.getvalue().encode('utf-8')

    # ------------------------------------------------------------------
    # Caché
    # ------------------------------------------------------------------

    def _dcasa_meta_huella(self):
        """Resume en un texto lo que el catálogo usa: si no cambió, el CSV guardado sigue sirviendo.

        Pocas consultas de «cuántos» y «última modificación» (no se lee ningún producto): los productos del catálogo
        y sus variantes, sus fotos extra y precios extra, las categorías, las campañas, las tarifas, los impuestos y
        las existencias; más la configuración del feed y del sitio. La fecha de hoy entra para que una promoción que
        empieza o termina se note a más tardar al día siguiente.
        """
        self.ensure_one()
        feed = self.sudo()
        sitio = feed.website_id
        partes = [
            fields.Date.today().isoformat(), feed._dcasa_meta_base(), str(sitio.write_date),
            str(sitio.prevent_zero_price_sale), str(feed.lang_id.id), str(feed.pricelist_id.id),
            ','.join(map(str, feed.product_category_ids.ids)), feed.dcasa_marca or '', feed.dcasa_condicion or '',
            feed.dcasa_disponibilidad or '',
        ]
        dominio_base = feed._dcasa_meta_dominio_base()
        consultas = (
            ('product.template', dominio_base),
            ('product.product', dominio_base),
            ('product.image', []),
            ('product.template.attribute.value', []),
            ('product.public.category', []),
            ('dcasa.meta.campana', []),
            ('product.pricelist.item', []),
            ('account.tax', []),
            ('stock.quant', []),
        )
        for modelo, dominio in consultas:
            [(cuantos, ultima)] = self.env[modelo].sudo().with_context(active_test=False)._read_group(
                dominio, [], ['__count', 'write_date:max'])
            partes.append(f'{modelo}:{cuantos}:{ultima}')
        return '|'.join(partes)

    def _dcasa_meta_guardado(self):
        return gzip.decompress(base64.b64decode(self.feed_cache))

    def _dcasa_meta_servir(self):
        """El CSV para Meta: el guardado si nada cambió y no venció; si no, se vuelve a armar y se guarda.

        Si otra petición lo está armando en este momento, se sirve el anterior; sin anterior, ``LockError`` (la ruta
        responde 503 con Retry-After).
        """
        self.ensure_one()
        if self.target != 'meta' or not self.dcasa_activo:
            raise NotFound()
        huella = self._dcasa_meta_huella()
        vigente = self.cache_expiry and self.cache_expiry >= fields.Datetime.now()
        if self.feed_cache and vigente and self.dcasa_huella == huella:
            return self._dcasa_meta_guardado()
        try:
            self.lock_for_update()
        except LockError:  # otra petición lo está armando en este momento
            if self.feed_cache:
                return self._dcasa_meta_guardado()
            raise
        contenido = self._dcasa_meta_csv()
        _logger.info('Catálogo para Meta (feed %s) armado de nuevo: %s filas', self.id, contenido.count(b'\n') - 1)
        self.sudo().write({
            # El binario vive en un adjunto (R2): base64 de los bytes en gzip, como lo guarda Odoo.
            'feed_cache': base64.b64encode(gzip.compress(contenido)),
            'cache_expiry': fields.Datetime.now() + VIGENCIA,
            'dcasa_huella': huella,
        })
        return contenido

    # ------------------------------------------------------------------
    # El feed de Google nunca sirve uno de Meta
    # ------------------------------------------------------------------

    def _render_and_cache_compressed_gmc_feed(self):
        if any(feed.target == 'meta' for feed in self):
            raise NotFound()
        return super()._render_and_cache_compressed_gmc_feed()

    def _render_gmc_feed(self):
        if any(feed.target == 'meta' for feed in self):
            raise NotFound()
        return super()._render_gmc_feed()

    # ------------------------------------------------------------------
    # Escritura y botones (Gerencia y administradores)
    # ------------------------------------------------------------------

    def write(self, vals):
        """Un catálogo de Meta no se convierte en otro (el de Google publica la referencia del proveedor y el código
        de barras) y su token solo es uno largo y al azar («Cambiar la dirección secreta»)."""
        meta = self.filtered(lambda feed: feed.target == 'meta')
        if meta and 'target' in vals and vals['target'] != 'meta':
            raise UserError(self.env._('El catálogo para Meta no se puede convertir en otro tipo de catálogo.'))
        if (meta or vals.get('target') == 'meta') and 'access_token' in vals \
                and not (isinstance(vals['access_token'], str) and _TOKEN.fullmatch(vals['access_token'])):
            raise UserError(self.env._('La dirección secreta se cambia con el botón «Cambiar la dirección secreta».'))
        return super().write(vals)

    def _dcasa_meta_exigir_gerencia(self):
        if not any(self.env.user.has_group(grupo) for grupo in GRUPOS_GERENCIA):
            raise AccessError(self.env._('Solo Gerencia o un administrador puede hacer esto.'))

    def action_dcasa_meta_nueva_direccion(self):
        """«Cambiar la dirección secreta»: un token nuevo; la dirección vieja deja de funcionar."""
        self._dcasa_meta_exigir_gerencia()
        for feed in self.filtered(lambda f: f.target == 'meta'):
            feed.write({'access_token': uuid.uuid4().hex})
            feed.message_post(body=self.env._(
                'Se cambió la dirección secreta del catálogo. La anterior ya no funciona: hay que pegar la nueva en '
                'Meta (Commerce Manager › Orígenes de datos).'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning',
                'sticky': True,
                'message': self.env._(
                    'Listo: la dirección cambió. Cópiala y pégala en Meta (Commerce Manager › Orígenes de datos); '
                    'mientras tanto Meta no puede leer el catálogo.'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_dcasa_meta_ver_fuera(self):
        """«Ver los que quedan fuera»: los productos publicados que no van a Meta (sin foto, sin precio o marcados para
        no anunciar)."""
        self._dcasa_meta_exigir_gerencia()
        self.ensure_one()
        plantillas = self.env['product.template']
        if self.target == 'meta':
            reparto = self._dcasa_meta_clasificar()
            plantillas = (reparto['sin_foto'] | reparto['sin_precio']).product_tmpl_id | self._dcasa_meta_marcados()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Quedan fuera de Meta'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', plantillas.ids)],
            'context': {'create': False},
            'help': self.env._('<p>Todos los productos publicados van al catálogo de Meta.</p>'),
        }
