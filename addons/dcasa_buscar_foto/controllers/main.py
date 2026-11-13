"""``/shop/foto``: la página de «Busca con una foto» (models/buscar_foto.py hace el trabajo).

* ``GET``: la página para empezar (el botón grande de la cámara). También es a donde vuelve un «recargar» después de una
  búsqueda: el navegador no reenvía la foto. Con ``?espera=1`` (el borde frenó una ráfaga), el aviso «Ahora no podemos».
* ``POST`` (con CSRF; la manda static/src/js/buscar_foto.js con la foto ya achicada en base64, en un campo de texto que
  Werkzeug guarda en memoria, nunca en un archivo temporal): la misma página con lo que se encontró o con un mensaje.

Apagada (Sitio web › Busca con una foto), la ruta no existe (404). La respuesta lleva ``Cache-Control: no-store``: ni el
borde ni el navegador la guardan (el borde tampoco guarda ``/shop/foto``: no está en su lista de páginas estáticas).
"""
from odoo import http
from odoo.addons.website_dcasa.controllers.main import DcasaTienda
from odoo.http import request

from ..models.buscar_foto import MAX_PETICION

# La política de privacidad cambia con este módulo (views/templates.xml, «Busca con una foto»): su fecha también.
FECHA_PRIVACIDAD = '13 de noviembre de 2026'

TITULO_RESULTADOS = 'Esto se parece a tu foto'
MENSAJES = {
    'documento': 'Esa foto parece un documento; para buscar, sube la foto de un mueble.',
    'no_ahora': 'Ahora no podemos buscar por foto; búscalo por nombre o escríbenos por WhatsApp.',
    'formato': 'Esa foto no la pudimos abrir. Prueba con otra en JPG, PNG o WebP de menos de 4 MB.',
    'otra': 'No reconocimos un mueble en tu foto. Prueba con otra donde se vea el mueble completo.',
    'nada': 'No encontramos algo parecido en la tienda en línea. Mándanos la foto por WhatsApp y te decimos si lo '
            'tenemos.',
}
WHATSAPP = ("Hola D'CASA, busqué un mueble con una foto en la tienda y quiero que me ayuden a encontrarlo. "
            'Les mando la foto por aquí.')


class DcasaBuscarFotoTienda(http.Controller):

    @http.route('/shop/foto', type='http', auth='public', website=True, methods=['GET', 'POST'], sitemap=False,
                max_content_length=MAX_PETICION)
    def buscar_con_foto(self, foto=None, espera=None, **kwargs):
        website = request.website
        if not website._dcasa_buscar_foto_activa():
            raise request.not_found()
        if request.httprequest.method != 'POST':
            # ``?espera=1``: el borde frenó una ráfaga de fotos desde esa conexión (edge/src/bots.ts, cubeta «foto»).
            return self._pagina({'estado': 'no_ahora' if espera else 'inicio'})
        resultado = request.env['dcasa.buscar.foto']._dcasa_buscar(
            foto if isinstance(foto, str) else None, website,
            sesion=request.session.sid, conexion=request.httprequest.remote_addr)
        return self._pagina(resultado)

    def _items(self, productos):
        """Las tarjetas de la portada (``website_dcasa.tarjeta_producto``): precio de la tarifa del visitante y
        «Agregar» de un clic donde la tienda lo permite (las mismas reglas que ``website._dcasa_productos``)."""
        if not productos:
            return []
        website = request.website
        precios = productos._get_sales_prices(website)
        moneda = request.pricelist.currency_id or website.currency_id
        acceso = website.has_ecommerce_access()
        items = []
        for producto in productos:
            precio = precios.get(producto.id, {}).get('price_reduce', producto.list_price)
            items.append({'producto': producto, 'precio': precio, 'moneda': moneda,
                          'directo': acceso and website._dcasa_compra_directa(producto, precio)})
        return items

    def _pagina(self, resultado):
        estado = resultado['estado']
        respuesta = request.render('dcasa_buscar_foto.pagina', {
            'estado': estado,
            'titulo': TITULO_RESULTADOS if estado == 'resultados' else 'Busca con una foto',
            'mensaje': MENSAJES.get(estado, ''),
            'items': self._items(resultado.get('productos')),
            'etiqueta': resultado.get('etiqueta') or '',
            'por_codigo': bool(resultado.get('por_codigo')),
            'whatsapp': request.website._dcasa_whatsapp_url(WHATSAPP),
        })
        respuesta.headers['Cache-Control'] = 'no-store'
        respuesta.headers['X-Robots-Tag'] = 'noindex'
        return respuesta


class DcasaPrivacidadConFoto(DcasaTienda):
    """La política de privacidad dice cuándo cambió: con el párrafo de «Busca con una foto», esta fecha."""

    @http.route()
    def privacidad(self, **kwargs):
        respuesta = super().privacidad(**kwargs)
        if getattr(respuesta, 'qcontext', None) is not None:
            respuesta.qcontext['actualizado'] = FECHA_PRIVACIDAD
        return respuesta
