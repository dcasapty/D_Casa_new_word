"""Black Weekend: productos marcados y ventana de la campaña (portada, /black-weekend y la tienda del borde).

* Productos: ``product.template.dcasa_black_weekend`` (los marca la migración de dcasa_catalogo,
  ``marcar_black_weekend``), con su orden y, si el producto tiene colores, la variante que se
  muestra (``dcasa_bw_variante_id``, p. ej. 908K negro).
* Precio: el de la tienda (tarifa del visitante), nunca escrito en una plantilla. La línea del
  combo sale del texto guardado del Excel (``dcasa_combo``, «Combo con colchón <nombre> $X»).
* Ventana (``ir.config_parameter``), evaluada en hora de Panamá (America/Panama):

  - ``dcasa_black_weekend.activo`` = ``1``: visible ya, sin mirar fechas (vista previa de staging).
  - ``dcasa_black_weekend.inicio`` / ``.fin`` (``AAAA-MM-DD``, inclusivas: desde las 00:00 del
    inicio hasta las 23:59:59 del fin): visible dentro de la ventana. Una fecha vacía deja ese
    lado abierto; las dos vacías (y ``activo`` ≠ 1) = apagada. Una fecha mal escrita la apaga.

  docker/entrypoint.sh fija los tres desde DCASA_BLACK_WEEKEND(_INICIO/_FIN) (edge/wrangler.jsonc).
"""
import logging
import re
from datetime import date, datetime, time

import pytz

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.http import request
from odoo.tools.json import scriptsafe as json_scriptsafe

_logger = logging.getLogger(__name__)

PARAM_ACTIVO = 'dcasa_black_weekend.activo'
PARAM_INICIO = 'dcasa_black_weekend.inicio'
PARAM_FIN = 'dcasa_black_weekend.fin'
PARAMS = (PARAM_ACTIVO, PARAM_INICIO, PARAM_FIN)
# Decisión de la dueña (2026-10-02): desde ya (viernes 2) hasta el domingo 11 de octubre de 2026,
# hora de Panamá. Antes era del lunes 5; la adelantó para presentar la página ese lunes.
VENTANA_POR_DEFECTO = {PARAM_ACTIVO: '0', PARAM_INICIO: '2026-10-02', PARAM_FIN: '2026-10-11'}
ZONA = pytz.timezone('America/Panama')
RUTA = '/black-weekend'
# La página de cualquier campaña (Black Friday, …); /black-weekend lleva aquí (controllers/main.py).
RUTA_PROMOCIONES = '/promociones'
# Imagen para compartir (redes): la gráfica 115.png de la dueña completa (decisión suya del 2026-10-02).
OG_IMAGEN = '/website_dcasa/static/src/img/black_weekend/og.jpg'
OG_ANCHO, OG_ALTO = 1080, 1350
_COMBO = re.compile(r'^\s*(Combo con colchón)\s*(.*?)\s*\$\s*([\d,]+(?:\.\d+)?)\s*$', re.I)
_MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
          'octubre', 'noviembre', 'diciembre')
_MEMO = '_dcasa_bw_activo'


def leer_fecha(valor):
    """``AAAA-MM-DD`` → date; vacío → None; cualquier otra cosa → ValueError."""
    valor = (valor or '').strip()
    if not valor:
        return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', valor):
        raise ValueError(valor)
    return date.fromisoformat(valor)


def leer_combo(texto):
    """«Combo con colchón First Class $469.99» → {'texto': 'Combo con colchón First Class', 'colchon':
    'First Class', 'precio': 469.99}; None si el texto no es un combo con su cifra."""
    m = _COMBO.match(texto or '')
    if not m:
        return None
    try:
        precio = float(m.group(3).replace(',', ''))
    except ValueError:
        return None
    colchon = m.group(2).strip()
    return {'texto': f'{m.group(1)} {colchon}'.strip(), 'colchon': colchon, 'precio': precio}


def fechas_en_texto(inicio, fin):
    """«del 5 al 11 de octubre de 2026» (o con los dos meses/años si cambian); '' si falta una."""
    if not (inicio and fin):
        return ''
    if (inicio.year, inicio.month) == (fin.year, fin.month):
        return f'del {inicio.day} al {fin.day} de {_MESES[fin.month - 1]} de {fin.year}'
    if inicio.year == fin.year:
        return f'del {inicio.day} de {_MESES[inicio.month - 1]} al {fin.day} de {_MESES[fin.month - 1]} de {fin.year}'
    return (f'del {inicio.day} de {_MESES[inicio.month - 1]} de {inicio.year} '
            f'al {fin.day} de {_MESES[fin.month - 1]} de {fin.year}')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # El nombre técnico se queda (lo usan la tienda del borde, el catálogo y las pruebas); desde el 2026-11-15 es la
    # casilla de cualquier campaña del sitio (models/campana.py).
    dcasa_black_weekend = fields.Boolean(
        string='En la campaña', index=True, copy=False,
        help='Sale en la sección de la campaña en la portada, en su página y con su etiqueta mientras la campaña '
             'esté activa (Sitio web › Campaña del sitio), con su precio de la tienda o su precio de campaña.')
    dcasa_bw_orden = fields.Integer(string='Orden en la campaña', default=0, copy=False)
    dcasa_bw_variante_id = fields.Many2one(
        'product.product', string='Variante destacada en Black Weekend', copy=False,
        domain="[('product_tmpl_id', '=', id)]",
        help='Si el producto tiene colores: la variante cuya foto y código se muestran (p. ej. 908K negro).')


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _dcasa_bw_parametros_por_defecto(self):
        """Crea los parámetros de la ventana que falten (``VENTANA_POR_DEFECTO``); no pisa ninguno."""
        param = self.env['ir.config_parameter'].sudo()
        for clave, valor in VENTANA_POR_DEFECTO.items():
            if not param.search_count([('key', '=', clave)], limit=1):
                param.set_param(clave, valor)

    @api.model
    def _dcasa_campana_registro(self):
        """La campaña del sitio (dcasa.campana, sudo: la lee el visitante); vacía si no hay."""
        sitio = self if (self and len(self) == 1) else self.get_current_website()
        if 'dcasa.campana' not in self.env:
            return None
        return self.env['dcasa.campana'].sudo().search([('website_id', '=', sitio.id)], limit=1)

    @api.model
    def _dcasa_campana_nombre(self):
        """«Black Friday», el de la campaña del panel; «Black Weekend» mientras manden los parámetros de siempre."""
        campana = self._dcasa_campana_registro()
        if campana and (campana.fecha_inicio or campana.fecha_fin):
            return campana.name
        return 'Black Weekend'

    @api.model
    def _dcasa_campana_frase(self):
        campana = self._dcasa_campana_registro()
        return (campana.frase or '').strip() if campana and (campana.fecha_inicio or campana.fecha_fin) else ''

    @api.model
    def _dcasa_bw_ventana(self):
        """{'forzado', 'inicio', 'fin', 'valida'}: las fechas de la campaña del panel si tiene alguna; si no, las de
        los parámetros de siempre (sudo: los lee el visitante). ``forzado`` (vista previa de staging) sigue
        saliendo del parámetro."""
        param = self.env['ir.config_parameter'].sudo()
        forzado = (param.get_param(PARAM_ACTIVO) or '').strip() == '1'
        campana = self._dcasa_campana_registro()
        if campana and (campana.fecha_inicio or campana.fecha_fin):
            inicio, fin = campana.fecha_inicio, campana.fecha_fin
            return {'forzado': forzado, 'inicio': inicio, 'fin': fin, 'valida': not (inicio and fin and inicio > fin)}
        try:
            inicio, fin = leer_fecha(param.get_param(PARAM_INICIO)), leer_fecha(param.get_param(PARAM_FIN))
            valida = not (inicio and fin and inicio > fin)
        except ValueError as error:
            _logger.warning('Black Weekend: fecha inválida en los parámetros (%s): queda apagado.', error)
            inicio = fin = None
            valida = False
        return {'forzado': forzado, 'inicio': inicio, 'fin': fin, 'valida': valida}

    @api.model
    def _dcasa_black_weekend_activo(self, ahora=None):
        """¿Se muestra la campaña? ``ahora``: datetime en UTC (naive, como los de Odoo); por defecto, ya.

        Dentro de una petición web el resultado se guarda para el resto de la petición (las tarjetas
        preguntan una por una).
        """
        usar_memo = bool(request) and ahora is None
        if usar_memo and hasattr(request, _MEMO):
            return getattr(request, _MEMO)
        ventana = self._dcasa_bw_ventana()
        if ventana['forzado']:
            activo = True
        elif not ventana['valida'] or not (ventana['inicio'] or ventana['fin']):
            activo = False
        else:
            momento = pytz.utc.localize(ahora or fields.Datetime.now()).astimezone(ZONA).replace(tzinfo=None)
            desde = datetime.combine(ventana['inicio'], time.min) if ventana['inicio'] else None
            hasta = datetime.combine(ventana['fin'], time.max) if ventana['fin'] else None
            activo = (desde is None or momento >= desde) and (hasta is None or momento <= hasta)
        if usar_memo:
            setattr(request, _MEMO, activo)
        return activo

    def _dcasa_campana_precio_vigente(self, plantilla, ahora=None):
        """El precio de campaña de ``plantilla`` si rige en este momento (su regla de tarifa está en fechas); None si
        no. Para Juan y Brian, que dicen el precio sin pasar por la tarifa: así dicen el mismo que cobra el carrito."""
        plantilla = plantilla.sudo()
        precio = plantilla.dcasa_campana_precio if 'dcasa_campana_precio' in plantilla._fields else 0.0
        if not (plantilla.dcasa_black_weekend and precio and precio < plantilla.list_price):
            return None
        momento = ahora or fields.Datetime.now()
        regla = self.env['product.pricelist.item'].sudo().search([
            ('dcasa_campana', '=', True), ('product_tmpl_id', '=', plantilla.id),
            ('date_start', '<=', momento), ('date_end', '>=', momento)], limit=1)
        return precio if regla else None

    def _dcasa_bw_fechas(self):
        ventana = self._dcasa_bw_ventana()
        return fechas_en_texto(ventana['inicio'], ventana['fin']) if ventana['valida'] else ''

    def _dcasa_bw_dominio(self):
        return Domain.AND([self._dcasa_dominio_publicado(), [('dcasa_black_weekend', '=', True)]])

    def _dcasa_bw_productos(self, limit=None):
        """Productos de la campaña, publicados, en su orden, con precio de la tienda y combo.

        Cada item: producto, variante (la destacada o la principal), precio, moneda, directo
        (agregar en un clic), combo (``leer_combo``), codigo y whatsapp (mensaje con el código).
        No mira la ventana: eso lo decide quien llama (``_dcasa_black_weekend_activo``).
        """
        self.ensure_one()
        productos = self.env['product.template'].search(
            self._dcasa_bw_dominio(), limit=limit, order='dcasa_bw_orden asc, website_sequence asc, id asc')
        con_tarifa = bool(productos) and bool(request) and hasattr(request, 'pricelist')
        precios = productos._get_sales_prices(self) if con_tarifa else {}
        moneda = (request.pricelist.currency_id if con_tarifa else None) or self.currency_id
        acceso = con_tarifa and self.has_ecommerce_access()
        items = []
        for producto in productos:
            variante = producto.dcasa_bw_variante_id
            if not (variante and variante.active and variante.product_tmpl_id == producto):
                variante = producto.product_variant_id
            datos_precio = precios.get(producto.id, {})
            precio = datos_precio.get('price_reduce', producto.list_price)
            # El precio normal tachado cuando rige un precio de campaña (o un descuento de la tarifa).
            antes = datos_precio.get('base_price') or 0.0
            if variante != producto.product_variant_id or producto.product_variant_count > 1:
                # Producto con colores: el precio de la variante que se muestra (el mismo cálculo de Odoo).
                if con_tarifa:
                    info = variante.with_context(website_id=self.id)._get_combination_info_variant()
                    precio = info['price']
                    antes = info['list_price'] if info.get('has_discounted_price') else 0.0
                else:
                    precio, antes = variante.lst_price, 0.0
            codigo = producto.dcasa_codigo_publico or ''   # el del cliente; la referencia del proveedor no sale
            precio_visible = bool(precio or not self.prevent_zero_price_sale)
            directo = acceso and precio_visible and (
                self._dcasa_compra_directa(producto, precio) or self._dcasa_variante_directa(producto, variante))
            items.append({
                'producto': producto,
                'variante': variante,
                'precio': precio,
                'precio_antes': antes if antes and antes > precio else 0.0,
                'precio_visible': precio_visible,
                'moneda': moneda,
                'directo': directo,
                # Con precio de campaña rigiendo, la línea del combo (su precio de siempre, del Excel) no sale: al lado
                # de la cama rebajada confundía (decisión del 2026-11-15; la dueña puede pedir que vuelva).
                'combo': (leer_combo(producto.dcasa_combo)
                          if 'dcasa_combo' in producto._fields and not (antes and antes > precio) else None),
                'codigo': codigo,
                'whatsapp': self._dcasa_bw_whatsapp(producto, codigo),
                'alt': producto._dcasa_nombre_cliente(),
            })
        return items

    def _dcasa_variante_directa(self, producto, variante):
        """¿Se agrega la variante destacada en un clic? Solo si lo único que se elige es el color
        (variantes de atributos «siempre», sin valores a medida, sin combos ni opcionales)."""
        lineas = producto.attribute_line_ids
        return bool(
            variante and producto.product_variant_count > 1
            and producto.type != 'combo'
            and not producto.optional_product_ids
            and all(linea.attribute_id.create_variant == 'always' for linea in lineas)
            and not any(lineas.product_template_value_ids.mapped('is_custom'))
        )

    def _dcasa_bw_whatsapp(self, producto, codigo):
        nombre = producto._dcasa_nombre_cliente()
        texto = f"Hola D'CASA, me interesa del {self._dcasa_campana_nombre()}: {nombre}"
        return self._dcasa_whatsapp_url(f'{texto} (código {codigo})' if codigo else texto)

    def _dcasa_bw_marcado(self, producto):
        """¿Lleva la etiqueta «Black Weekend» esta tarjeta? (producto marcado y campaña activa)."""
        return bool(producto and 'dcasa_black_weekend' in producto._fields and producto.sudo().dcasa_black_weekend
                    and self._dcasa_black_weekend_activo())

    def _dcasa_bw_descripcion(self, items=None):
        """Descripción factual de /black-weekend para Google y redes (sin cifras que no sean del catálogo)."""
        items = self._dcasa_bw_productos() if items is None else items
        fechas = self._dcasa_bw_fechas()
        nombre = self._dcasa_campana_nombre()
        if nombre == 'Black Weekend':
            return (f"Black Weekend en D'CASA Panamá{(' ' + fechas) if fechas else ''}: {len(items)} camas y bases "
                    'seleccionadas, con el precio de la cama sola y el del combo con colchón (+ ITBMS). '
                    'Entregas en Panamá Oeste, Panamá y Colón, desde La Chorrera. Escríbenos por WhatsApp.')
        return (f"{nombre} en D'CASA Panamá{(' ' + fechas) if fechas else ''}: {len(items)} productos "
                'seleccionados (+ ITBMS). Entregas en Panamá Oeste, Panamá y Colón, desde La Chorrera. '
                'Escríbenos por WhatsApp.')

    def _dcasa_bw_json_ld(self, items):
        """``ItemList`` de /black-weekend: la URL y el nombre de cada producto, en orden."""
        base = self._dcasa_url_publica()
        lista = []
        for posicion, item in enumerate(items, start=1):
            elemento = {'@type': 'ListItem', 'position': posicion, 'name': item['producto']._dcasa_nombre_cliente()}
            if base:
                elemento['url'] = base + item['producto'].website_url
            lista.append(elemento)
        datos = {
            '@context': 'https://schema.org',
            '@type': 'ItemList',
            'name': f"{self._dcasa_campana_nombre()} | D'CASA Panamá",
            'numberOfItems': len(lista),
            'itemListElement': lista,
        }
        if base:
            datos['url'] = base + RUTA_PROMOCIONES
        return json_scriptsafe.dumps(datos, ensure_ascii=False)

    def _dcasa_bw_og(self, meta, clave):
        """Metadatos de redes de /black-weekend: la imagen de la campaña en lugar del logo."""
        base = self._dcasa_url_publica() or (request.httprequest.url_root.rstrip('/') if request else '')
        meta = dict(meta or {})
        meta[clave] = base + OG_IMAGEN
        if clave == 'og:image':
            meta['og:image:width'] = str(OG_ANCHO)
            meta['og:image:height'] = str(OG_ALTO)
            meta['og:image:alt'] = "Black Weekend en D'CASA Panamá: cama tapizada King beige (ref. 888K)"
        return meta
