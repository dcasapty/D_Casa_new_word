"""``/dcasa/brian/v1/*``: lo que la página de la tienda le pide a Odoo para el chat «Brian de la tienda».

* ``POST /pase``                    — el pase firmado para hablar con el Worker (contrato §1, ``models/pase.py``).
* ``GET  /carrito``                 — el carrito de ESTA sesión (para abrir el chat sabiendo qué hay).
* ``POST /carrito/agregar``         — ``{producto_id, cantidad}``: lo que Brian propuso o tocó el visitante (§3).
* ``POST /carrito/cantidad``        — ``{producto_id, cantidad}`` (0 = quitar).
* ``GET  /carrito/cotizacion.pdf``  — la cotización del carrito, con los números de Odoo y «Cliente: (por confirmar)».
  Cada una arranca wkhtmltopdf y ocupa una conexión de la base (Odoo corre con ``workers = 0``): a lo sumo 2 a la vez
  por proceso (sin esperar: la tercera recibe 503 con ``Retry-After``), 10 por hora por conexión (la IPv4 entera o la
  /64, contador confirmado aparte), 10 por hora por sesión, y el borde frena las ráfagas (6 por minuto por conexión).
* ``POST /calificar``               — ``{estrellas}``: solo número y fecha, una vez por ``sid`` (contrato_cambios §5).

Reglas de todas:

* **La sesión del visitante** (``auth='public'``): cada quien ve y cambia solo SU carrito. El modelo de IA nunca llama
  aquí: el navegador aplica lo que Brian propone y le cuenta el resultado.
* **CSRF en los POST**: el token va en la cabecera ``X-CSRF-Token`` (las páginas guardadas en el borde traen el de otra
  sesión: la página pide uno fresco a ``/dcasa/borde/csrf``) y el cuerpo tiene que ser JSON (un formulario de otro
  sitio no puede mandarlo sin permiso del navegador). Se valida con ``request.validate_csrf`` antes de leer nada.
* **Cuerpos de a lo sumo 2 KB**, cantidades de 1 a 20 (una línea no pasa de 20) y solo productos publicados en la
  tienda, que se puedan agregar directo y con precio; si hay que elegir medida, color o combo: ``motivo: elegir`` con la
  ficha.
* Respuestas JSON ``no-store`` y ``noindex``: ni el borde ni el navegador las guardan (el borde nunca guarda
  ``/dcasa/*``; ``edge/src/routing.ts``).
* Apagado (Sitio web › Brian de la tienda): todas responden ``{ok: false, motivo: "apagado"}``.
"""
import json
import logging
import threading
import time

from odoo import http
from odoo.addons.dcasa_base.red import llave_ip
from odoo.addons.dcasa_conversaciones.models import publico as P
from odoo.addons.website_dcasa.controllers.main import DcasaTienda
from odoo.addons.website_dcasa.models.website import CATEGORIAS_PORTADA
from odoo.fields import Domain
from odoo.http import request

from ..models.pase import SESION_CALIFICADO, SESION_PDF, SESION_SID

_logger = logging.getLogger(__name__)

RAIZ = '/dcasa/brian/v1'
MAX_CUERPO = 2048
MAX_CANTIDAD = 20
MAX_PDF_POR_HORA = 10              # por sesión
MAX_PDF_POR_CONEXION_HORA = 10     # por conexión (IPv4 entera o /64): una cookie nueva no da cupo nuevo
MAX_PDF_A_LA_VEZ = 2               # por proceso: cada PDF es un wkhtmltopdf y una conexión de la base
_SEMAFORO_PDF = threading.BoundedSemaphore(MAX_PDF_A_LA_VEZ)
TEXTO_SIN_PDF = 'Por ahora no podemos armar más cotizaciones. Inténtalo en un rato o escríbenos por WhatsApp.'
TEXTO_PDF_OCUPADO = 'Estamos armando otras cotizaciones. Inténtalo de nuevo en unos segundos.'
MAX_ID = 2 ** 31
# Las sugerencias del saludo dicen la categoría con la palabra que escribiría un cliente («Camas», no «Recámaras»).
NOMBRE_SUGERENCIA = {'recamaras': 'Camas', 'oficina': 'Escritorios'}
# Lo que la página necesita de cada producto para pintar su tarjeta (lo mismo que valida `productoValido` en el JS).
CAMPOS_TARJETA = ('producto_id', 'plantilla_id', 'nombre', 'precio_texto', 'disponibilidad', 'imagen', 'ruta',
                  'agregable')
# La política de privacidad cambia con este módulo (views/templates.xml, «Brian, el chat de la tienda»): su fecha.
FECHA_PRIVACIDAD = '16 de noviembre de 2026'   # el chat se llama Andrés y entiende notas de voz (el audio no se guarda)
MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre')


def _json(datos, estado=200):
    return request.make_response(
        json.dumps(datos, ensure_ascii=False, separators=(',', ':')),
        headers=[('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'),
                 ('X-Content-Type-Options', 'nosniff'), ('X-Robots-Tag', 'noindex')],
        status=estado)


def _fecha(texto):
    """«14 de noviembre de 2026» → ``(2026, 11, 14)``; lo que no se entiende, ``(0, 0, 0)``."""
    partes = str(texto or '').lower().split(' de ')
    try:
        return int(partes[2]), MESES.index(partes[1].strip()) + 1, int(partes[0])
    except (IndexError, ValueError):
        return 0, 0, 0


def _entero(valor, minimo, maximo):
    """Un entero de verdad (no un booleano ni un texto) entre ``minimo`` y ``maximo``; si no, ``None``."""
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        return None
    return valor


class DcasaBrianTiendaAPI(http.Controller):

    # ------------------------------------------------------------------
    # Entrada común
    # ------------------------------------------------------------------

    def _post(self, funcion):
        """CSRF (cabecera), JSON de a lo sumo 2 KB e interruptor; después ``funcion(cuerpo)``."""
        if not request.validate_csrf(request.httprequest.headers.get('X-CSRF-Token') or ''):
            return _json({'ok': False, 'motivo': 'csrf'}, 403)
        tipo = (request.httprequest.mimetype or '').lower()
        if tipo != 'application/json':
            return _json({'ok': False, 'motivo': 'formato'}, 415)
        largo = request.httprequest.content_length
        if largo and largo > MAX_CUERPO:
            return _json({'ok': False, 'motivo': 'formato'}, 413)
        crudo = request.httprequest.get_data(cache=True)
        if len(crudo) > MAX_CUERPO:
            return _json({'ok': False, 'motivo': 'formato'}, 413)
        try:
            cuerpo = json.loads(crudo.decode('utf-8') or '{}')
        except (ValueError, UnicodeDecodeError):
            return _json({'ok': False, 'motivo': 'formato'}, 400)
        if not isinstance(cuerpo, dict):
            return _json({'ok': False, 'motivo': 'formato'}, 400)
        if not request.env['dcasa.brian.tienda'].sudo()._activo():
            return _json({'ok': False, 'motivo': 'apagado'})
        return funcion(cuerpo)

    # ------------------------------------------------------------------
    # El pase
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/pase', type='http', auth='public', website=True, methods=['POST'], csrf=False,
                sitemap=False, max_content_length=MAX_CUERPO)
    def pase(self, **_kw):
        return self._post(self._pase)

    def _pase(self, cuerpo):
        turnstile = cuerpo.get('turnstile') if isinstance(cuerpo.get('turnstile'), str) else ''
        resultado = request.env['dcasa.brian.tienda'].sudo()._emitir(
            request.session, request.httprequest.remote_addr, request.website, turnstile=turnstile)
        if resultado.get('ok'):
            resultado['sugerencias'] = self._sugerencias()
        return _json(resultado)

    def _sugerencias(self):
        """Las dos categorías de la portada con más productos publicados, para las sugerencias del saludo (pedido de la
        dueña, 2026-11-15, «opción 2»: la lista fija decía «Salas» con 2 productos y no decía «Camas», con 121). Es el
        mismo número que la portada pone debajo de cada categoría; con empate, el orden de la portada. Sin nada
        publicado, ninguna: la página usa las de fábrica."""
        website = request.website
        cuentas = [(website._dcasa_categoria_cantidad(clave), -orden, NOMBRE_SUGERENCIA.get(clave, nombre))
                   for orden, (clave, nombre, _alt) in enumerate(CATEGORIAS_PORTADA)]
        return [nombre for cantidad, _orden, nombre in sorted(cuentas, reverse=True) if cantidad][:2]

    # ------------------------------------------------------------------
    # El carrito
    # ------------------------------------------------------------------

    def _carrito(self):
        """El carrito de esta sesión como lo lee la página (contrato §3). Los números salen de Odoo."""
        orden = request.cart
        vacio = {'lineas': [], 'cantidad_total': 0, 'total_texto': P.precio_texto(0, False),
                 'itbms_texto': P.precio_texto(0, False), 'total_con_itbms_texto': P.precio_texto(0, False)}
        if not orden:
            return vacio
        lineas = []
        for linea in orden.website_order_line:
            producto = linea.product_id
            if not producto:
                continue
            lineas.append({
                'producto_id': producto.id,
                'nombre': producto._dcasa_nombre_cliente(),
                'cantidad': int(linea.product_uom_qty),
                'subtotal_texto': P.precio_texto(linea.price_subtotal, bool(linea.tax_ids)),
                'imagen': f'/web/image/product.product/{producto.id}/image_128',
                'url': producto.product_tmpl_id.website_url or '',
            })
        mas_itbms = orden.amount_tax > 0
        return {
            'lineas': lineas,
            'cantidad_total': int(orden.cart_quantity),
            'total_texto': P.precio_texto(orden.amount_untaxed, mas_itbms),
            'itbms_texto': P.precio_texto(orden.amount_tax, False),
            'total_con_itbms_texto': P.precio_texto(orden.amount_total, False),
        }

    @http.route(f'{RAIZ}/carrito', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def carrito(self, **_kw):
        if not request.env['dcasa.brian.tienda'].sudo()._activo():
            return _json({'ok': False, 'motivo': 'apagado'})
        return _json({'ok': True, 'carrito': self._carrito()})

    @http.route(f'{RAIZ}/vitrina', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def vitrina(self, **_kw):
        if not request.env['dcasa.brian.tienda'].sudo()._activo():
            return _json({'ok': False, 'motivo': 'apagado'})
        return _json({'ok': True, 'productos': self._sugeridos()})

    def _sugeridos(self):
        """Lo que muestra el chat ampliado mientras Brian no ha mostrado nada (pedido de la dueña, 2026-11-15: «cómo
        aprovechamos ese espacio enorme»): «Lo más buscado» de la portada, los mismos productos en el mismo orden, con
        lo que tiene existencia primero y sin lo que ya está en el carrito. Las tarjetas son las de las herramientas de
        Brian (`_j_ficha_corta`): mismo precio, disponibilidad y «Agregar» que cuando él los muestra."""
        orden = request.cart
        en_carrito = set(orden.website_order_line.product_id.product_tmpl_id.ids) if orden else set()
        herramientas = request.env['brian.herramientas'].sudo()
        fichas = [herramientas._j_ficha_corta(item['producto'], '')
                  for item in request.website._dcasa_productos(limit=12) if item['producto'].id not in en_carrito]
        fichas.sort(key=lambda ficha: ficha.get('disponibilidad') == 'agotado')   # estable: el orden de la portada
        return [{clave: ficha.get(clave) for clave in CAMPOS_TARJETA} for ficha in fichas[:6]]

    def _producto(self, producto_id):
        """``(variante, plantilla)`` publicada en este sitio, buscada como el visitante; ``(None, None)`` si no."""
        variante = request.env['product.product'].sudo().browse(producto_id).exists()
        if not variante:
            return None, None
        # Buscar (no leer) con las reglas del visitante: solo lo publicado y a la venta en este sitio.
        plantilla = request.env['product.template'].search(Domain.AND([
            request.website._dcasa_dominio_publicado(), [('id', '=', variante.product_tmpl_id.id)]]), limit=1)
        if not plantilla:
            return None, None
        return request.env['product.product'].browse(variante.id), plantilla

    def _se_agrega_directo(self, variante, plantilla):
        """Las reglas del «Agregar» de un clic de la portada: sin elegir nada, con precio y que la tienda lo deje."""
        website = request.website
        precio = plantilla._get_sales_prices(website).get(plantilla.id, {}).get('price_reduce', plantilla.list_price)
        if plantilla.product_variant_count > 1:
            directa = website._dcasa_variante_directa(plantilla, variante)
        else:
            directa = website._dcasa_compra_directa(plantilla, precio)
        return bool(directa and precio and precio > 0 and variante._is_add_to_cart_allowed())

    def _poner(self, cuerpo, sumar):
        producto_id = _entero(cuerpo.get('producto_id'), 1, MAX_ID - 1)
        cantidad = _entero(cuerpo.get('cantidad'), 1 if sumar else 0, MAX_CANTIDAD)
        if producto_id is None or cantidad is None:
            return _json({'ok': False, 'motivo': 'formato'}, 400)
        orden = request.cart
        if sumar:
            variante, plantilla = self._producto(producto_id)
            if not variante:
                return _json({'ok': False, 'motivo': 'no_disponible'})
            if not self._se_agrega_directo(variante, plantilla):
                return _json({'ok': False, 'motivo': 'elegir', 'url': plantilla.website_url})
            orden = orden or request.website._create_cart()
        elif not orden:
            return _json({'ok': True, 'carrito': self._carrito()})
        linea = orden.website_order_line.filtered(lambda sol: sol.product_id.id == producto_id)[:1]
        if linea:
            actual = int(linea.product_uom_qty)
            # Sumar nunca baja una línea: si ya tenía más de 20 (puestas en /shop/cart), se queda como estaba.
            nueva = max(actual, min(actual + cantidad, MAX_CANTIDAD)) if sumar else cantidad
            orden._cart_update_line_quantity(line_id=linea.id, quantity=nueva)
        elif sumar:
            orden._cart_add(product_id=producto_id, quantity=cantidad)
        return _json({'ok': True, 'carrito': self._carrito()})

    @http.route(f'{RAIZ}/carrito/agregar', type='http', auth='public', website=True, methods=['POST'], csrf=False,
                sitemap=False, max_content_length=MAX_CUERPO)
    def carrito_agregar(self, **_kw):
        return self._post(lambda cuerpo: self._poner(cuerpo, sumar=True))

    @http.route(f'{RAIZ}/carrito/cantidad', type='http', auth='public', website=True, methods=['POST'], csrf=False,
                sitemap=False, max_content_length=MAX_CUERPO)
    def carrito_cantidad(self, **_kw):
        return self._post(lambda cuerpo: self._poner(cuerpo, sumar=False))

    # ------------------------------------------------------------------
    # La cotización en PDF
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/carrito/cotizacion.pdf', type='http', auth='public', website=True, methods=['GET'],
                sitemap=False)
    def cotizacion(self, **_kw):
        """La cotización del carrito de ESTA sesión. Sin carrito, al carrito. Con los topes del docstring del módulo:
        a la vez por proceso, por conexión y por sesión."""
        Tienda = request.env['dcasa.brian.tienda'].sudo()
        if not Tienda._activo():
            raise request.not_found()
        orden = request.cart
        if not orden or not orden.website_order_line:
            return request.redirect('/shop/cart')
        # Sin esperar: con dos armándose, la tercera se va al instante (no retiene la conexión de la base esperando).
        if not _SEMAFORO_PDF.acquire(blocking=False):
            _logger.info('Brian de la tienda: ya hay %s cotizaciones en PDF a la vez.', MAX_PDF_A_LA_VEZ)
            return self._sin_pdf(TEXTO_PDF_OCUPADO, 503, 20)
        try:
            ahora = time.time()
            recientes = [t for t in request.session.get(SESION_PDF) or []
                         if isinstance(t, (int, float)) and ahora - t < 3600]
            if len(recientes) >= MAX_PDF_POR_HORA:
                return self._sin_pdf(TEXTO_SIN_PDF, 429, 600)
            conexion = llave_ip(request.httprequest.remote_addr or '')
            if not Tienda._reservar_confirmado(f'pdf:{Tienda._huella(conexion)}', MAX_PDF_POR_CONEXION_HORA):
                _logger.info('Brian de la tienda: una conexión llegó al tope de cotizaciones en PDF de esta hora.')
                return self._sin_pdf(TEXTO_SIN_PDF, 429, 600)
            request.session[SESION_PDF] = recientes + [int(ahora)]
            contenido, tipo = request.env['ir.actions.report'].sudo().with_context(
                dcasa_brian_cliente=self._cliente_de(orden), report_pdf_no_attachment=True)._render_qweb_pdf(
                'dcasa_brian_tienda.action_report_cotizacion_carrito', [orden.id])
        finally:
            _SEMAFORO_PDF.release()
        es_pdf = tipo == 'pdf'
        return request.make_response(contenido, headers=[
            ('Content-Type', 'application/pdf' if es_pdf else 'text/html; charset=utf-8'),
            ('Content-Disposition', 'attachment; filename="cotizacion-dcasa.pdf"' if es_pdf else 'inline'),
            ('Cache-Control', 'no-store'), ('X-Robots-Tag', 'noindex'), ('X-Content-Type-Options', 'nosniff')])

    @staticmethod
    def _sin_pdf(texto, estado, reintento_s):
        return request.make_response(texto, status=estado, headers=[
            ('Content-Type', 'text/plain; charset=utf-8'), ('Cache-Control', 'no-store'),
            ('Retry-After', str(reintento_s)), ('X-Robots-Tag', 'noindex')])

    @staticmethod
    def _cliente_de(orden):
        """El nombre que va en «Cliente:». Solo si quien pide es un usuario con sesión y el carrito es suyo; si no,
        «(por confirmar)»: un carrito anónimo nunca muestra datos de nadie."""
        usuario = request.env.user
        if not usuario._is_public() and orden.partner_id == usuario.partner_id:
            return usuario.partner_id.name or ''
        return ''

    # ------------------------------------------------------------------
    # Las estrellas
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/calificar', type='http', auth='public', website=True, methods=['POST'], csrf=False,
                sitemap=False, max_content_length=MAX_CUERPO)
    def calificar(self, **_kw):
        return self._post(self._calificar)

    def _calificar(self, cuerpo):
        estrellas = _entero(cuerpo.get('estrellas'), 1, 5)
        if estrellas is None:
            return _json({'ok': False, 'motivo': 'formato'}, 400)
        sid = request.session.get(SESION_SID)
        if not sid:
            return _json({'ok': False, 'motivo': 'sin_chat'})   # solo quien conversó (recibió un pase) califica
        ya = request.session.get(SESION_CALIFICADO)
        if ya == sid:
            return _json({'ok': True, 'repetida': True})
        request.env['dcasa.brian.tienda.calificacion'].sudo().create({'estrellas': estrellas})
        request.session[SESION_CALIFICADO] = sid
        return _json({'ok': True})


class DcasaPrivacidadConBrian(DcasaTienda):
    """La política de privacidad dice cuándo cambió: con el párrafo de «Brian, el chat de la tienda», esta fecha, salvo
    que otro módulo (p. ej. «Busca con una foto») ya puso una más reciente: la fecha solo avanza."""

    @http.route()
    def privacidad(self, **kwargs):
        respuesta = super().privacidad(**kwargs)
        qcontext = getattr(respuesta, 'qcontext', None)
        if qcontext is not None and _fecha(qcontext.get('actualizado')) < _fecha(FECHA_PRIVACIDAD):
            qcontext['actualizado'] = FECHA_PRIVACIDAD
        return respuesta
