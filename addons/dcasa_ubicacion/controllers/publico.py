"""Las rutas públicas de la ubicación (docs/UBICACION.md). Van estrictas, como el enlace de los choferes:

* ``GET /u/<secreto>``: la página donde la clienta marca su punto (el enlace de un solo uso que le manda Juan).
  ``POST …/zona`` ({lat, lon}) dice qué zona y qué precio salen del punto, sin guardar nada; ``POST …/guardar``
  ({lat, lon, origen, precision, referencia, recibe?, telefono?}) lo guarda. ``POST …/foto`` (el cuerpo es la foto,
  de a lo sumo 8 MB) guarda la foto de la fachada, sin EXIF (``motor/casa.py``), apenas la toma (y hasta una hora
  después de usar el enlace). El secreto autentica: sin sesión ni cookie (``save_session=False``), sin CSRF.
  Vencido o inventado: la misma página de «este enlace ya no sirve», con «Pedir otro enlace por WhatsApp»; usado,
  «Ya la tenemos» con «Cambiar» (también por WhatsApp). Con la venta ya confirmada, ``…/zona`` no da precio.
* ``GET /entrega/<secreto>``: la página del motorizado (el QR del comprobante). Solo lee; vence a los 30 días. Sin
  punto, primero «Llamar» y «Buscar la dirección en Google Maps» (con lo que escribió la clienta).
  ``GET …/fachada``: la foto de la casa, con el mismo secreto (nunca por ``/web/content``).
* ``POST /tienda/ubicacion/zona`` (JSON-RPC del sitio): la vista previa del checkout (zona, precio y el aviso si lo
  escrito nombra otro distrito). No guarda nada.

Todas: ``Cache-Control: no-store``, ``X-Robots-Tag: noindex``, ``Referrer-Policy: strict-origin`` (Google valida la
clave del mapa por el dominio; el secreto del camino nunca sale), CSP con nonce en las páginas, cuerpo de a lo sumo
2 KB (la foto, 8 MB) y 60 peticiones por minuto por IP (la red /64 en IPv6). Pasado el tope, las páginas salen con su
plantilla («Un momento», «Reintentar» y una salida por WhatsApp; antes era texto plano sin estilos: auditoría 2). Las
coordenadas no se escriben en el registro del servidor. Los enlaces de WhatsApp son ``api.whatsapp.com/send``
(dcasa_base/whatsapp.py: con ``wa.me`` los emojis llegaban como «�»).
"""
import json
import secrets
import threading
from datetime import timedelta
from urllib.parse import quote

from odoo import fields, http
from odoo.addons.dcasa_base import whatsapp
from odoo.addons.dcasa_base.red import llave_ip
from odoo.addons.dcasa_envios.controllers.choferes import excede
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from ..models.zona import UbicacionInvalida
from ..motor import casa, geo

MAX_CUERPO = 2048
MAX_BUSQUEDA = 60
MAX_POR_MINUTO = 60
ESPERA_S = 60
FOTO_DESPUES_DE_USAR = timedelta(hours=1)   # la foto puede llegar justo después de «Sí, aquí es»
MAX_FOTOS_POR_ENLACE = 5                    # cambiar de foto unas veces sí; llenar R2 con un enlace no
_FOTOS_A_LA_VEZ = threading.BoundedSemaphore(2)
CABECERAS = {
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
    'Referrer-Policy': 'strict-origin',
    'X-Content-Type-Options': 'nosniff',
}
# Google Maps en el navegador (su guía de CSP estricta): el cargador trae más scripts (``strict-dynamic``), imágenes y
# teselas de sus dominios, y pone estilos en línea.
CSP_CON_MAPA = ("default-src 'none'; script-src 'nonce-{nonce}' 'strict-dynamic' https: 'unsafe-eval' blob:; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: blob: https://*.googleapis.com https://*.gstatic.com https://*.google.com "
                "https://*.googleusercontent.com; connect-src 'self' https://*.googleapis.com https://*.google.com "
                "https://*.gstatic.com data: blob:; frame-src https://*.google.com; worker-src blob:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
CSP_SIN_MAPA = ("default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; font-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                "frame-ancestors 'none'")


def _cabeceras(**extra):
    return list(dict(CABECERAS, **extra).items())


def _json(datos, status=200):
    return request.make_json_response(datos, headers=_cabeceras(), status=status)


TEXTO_TOPE = 'Muchos intentos seguidos: espere un minuto y vuelva a intentar.'


def _demasiado(en_json=True):
    respuesta = _json({'error': TEXTO_TOPE, 'motivo': 'tope'}, 429) if en_json else request.make_response(
        TEXTO_TOPE, headers=_cabeceras(**{'Content-Type': 'text/plain; charset=utf-8'}), status=429)
    respuesta.headers['Retry-After'] = str(ESPERA_S)
    return respuesta


def _aqui():
    """La dirección de esta misma página (para «Reintentar»), solo el camino y la consulta."""
    consulta = request.httprequest.query_string.decode('utf-8', 'replace')
    return request.httprequest.path + ('?' + consulta if consulta else '')


def _tope_en_pagina(plantilla, valores):
    """Pasado el tope de una página que abre una persona: la misma plantilla con «⏳ Un momento», «Reintentar» y, en la
    de la clienta, «Escríbanos por WhatsApp» (auditoría 2: era un texto plano sin estilos)."""
    empresa = request.env.company.sudo()
    valores = dict(valores, empresa=empresa.name, estado='tope', reintentar=_aqui())
    respuesta = _pagina(plantilla, valores, status=429)
    respuesta.headers['Retry-After'] = str(ESPERA_S)
    return respuesta


def _cuerpo():
    """El JSON pequeño que manda la página, o ``None``."""
    if (request.httprequest.content_length or 0) > MAX_CUERPO:
        return None
    crudo = request.httprequest.get_data()
    if len(crudo) > MAX_CUERPO:
        return None
    try:
        cuerpo = json.loads(crudo.decode('utf-8') or 'null')
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    return cuerpo if isinstance(cuerpo, dict) else None


def _limite():
    return excede('ubicacion:' + llave_ip(request.httprequest.remote_addr), maximo=MAX_POR_MINUTO)


def _pagina(plantilla, valores, con_mapa=False, status=200):
    nonce = secrets.token_urlsafe(16)
    html = request.env['ir.qweb']._render(plantilla, dict(valores, nonce=nonce))
    csp = (CSP_CON_MAPA if con_mapa else CSP_SIN_MAPA).format(nonce=nonce)
    return request.make_response(html, status=status, headers=_cabeceras(**{
        'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': csp,
        'Permissions-Policy': 'geolocation=(self), camera=(), microphone=()'}))


def vista_previa(env, lat, lon, texto='', con_mapa=True):
    """Lo que la página muestra antes de confirmar: la zona, el precio (o «se lo confirmamos») y, si lo escrito nombra
    otro distrito, el aviso (sin mapa no dice «mueva el mapa»). ``UbicacionInvalida`` si el punto no sirve. No guarda
    nada."""
    Ubicacion = env['dcasa.ubicacion']
    _lat, _lon, zona = Ubicacion._validar(lat, lon)
    precio = Ubicacion._precio(zona['lugar'])
    return {
        'zona': zona['texto'],
        'barriada': zona['barriada'], 'corregimiento': zona['corregimiento'], 'distrito': zona['distrito'],
        'provincia': zona['provincia'],
        'precio': precio['total_txt'] if precio['con_precio'] else None,
        'aviso': geo.aviso_de_cruce(texto, zona, Ubicacion._distritos(), con_mapa=con_mapa) if texto else '',
    }


def _numero_de_la_tienda():
    website = request.env['website'].sudo().search([], limit=1)
    return website._dcasa_whatsapp_numero() if website else ''


def _whatsapp_de_la_tienda(texto):
    """El enlace de WhatsApp de la tienda con el mensaje listo, o ``''`` si la tienda no tiene WhatsApp."""
    numero = _numero_de_la_tienda()
    return whatsapp.enlace(numero, texto) if numero else ''


def _pedido_ya_cobrado(enlace):
    """¿El enlace va ligado a una venta ya confirmada? Entonces la página no habla de precio: lo cobrado no se cambia
    (como el «listo» de ``_texto_para_la_clienta``)."""
    orden = enlace.sudo().orden_id
    return bool(orden) and orden.state not in ('draft', 'sent')


def buscar_en_google_maps(datos):
    """Para el motorizado sin punto: buscar en Google Maps lo que escribió la clienta (la dirección; si no hay, la
    zona), o ``''``."""
    texto = datos.get('direccion') or (datos.get('zona') or '').replace(' · ', ', ')
    if not texto:
        return ''
    return 'https://www.google.com/maps/search/?api=1&query=' + quote(f'{texto}, Panamá', safe='')


def buscar_lugares(env, texto):
    """Hasta 6 lugares de la tabla (barriadas, PH, lugares conocidos) con su zona y su punto, para centrar el mapa.
    Sin precios, km ni ids: es lo mismo que se ve en cualquier mapa."""
    texto = geo.texto_corto(texto, MAX_BUSQUEDA)
    if len(texto) < 2 or len(texto.split()) > 8:
        return []
    Lugar = env['dcasa.envio.lugar'].sudo()
    datos = Lugar.buscar_para_cotizar(texto, limite=10)
    salida = []
    for resultado in datos['resultados']:
        lugar = Lugar.browse(resultado['id'])
        punto = geo.punto(lugar.lat, lugar.lon)
        if punto:
            salida.append({'nombre': resultado['nombre'], 'zona': resultado.get('zona') or '',
                           'lat': punto[0], 'lon': punto[1]})
        if len(salida) >= 6:
            break
    return salida


class UbicacionPublica(http.Controller):

    # --- El enlace de un solo uso (chat) ---------------------------------------------------------------------------

    def _enlace(self, token):
        enlace = request.env['dcasa.ubicacion.enlace']._del_secreto(token)
        if not enlace or enlace.estado == 'vencido':
            return None
        return enlace

    @http.route('/u/<string:token>', type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def enlace_pagina(self, token, **_parametros):
        if _limite():
            return self._tope_de_la_clienta()
        enlace = self._enlace(token)
        empresa = request.env.company.sudo()
        base = (request.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        # La vista previa del enlace en WhatsApp, Instagram y Messenger: un pin en un mapa (se entiende sin leer).
        valores = {'empresa': empresa.name, 'token': token, 'estado': 'no_sirve', 'zona': '',
                   'imagen': base + '/dcasa_ubicacion/static/src/img/enlace_mapa.png'}
        if enlace and enlace.orden_id and enlace.creado_por == 'pedido':
            # «Volver a mi pedido» lleva el permiso del pedido (no vence): solo para quien ya lo tenía, que llegó
            # desde la página de su pedido. Un enlace del chat puede ir a otra persona (quien recibe): sin él.
            valores['volver'] = enlace.orden_id.sudo().get_portal_url()
        # Sin callejones sin salida (auditoría 1): vencido o inventado, «💬 Pedir otro enlace por WhatsApp» (sin decir
        # de quién ni de qué pedido); ya usado, «📍 Cambiar» pide otro por WhatsApp.
        if not enlace:
            valores['wa_otro'] = _whatsapp_de_la_tienda(
                'Hola 👋 El enlace para marcar mi casa ya no sirve. ¿Me manda otro? 📍')
        elif enlace.estado == 'usado':
            valores.update(estado='usado', zona=enlace.zona or '',
                           wa_otro=_whatsapp_de_la_tienda('Hola 👋 Quiero cambiar mi ubicación de entrega 📍'))
        else:
            clave = request.env['dcasa.ubicacion']._clave_navegador()
            numero = _numero_de_la_tienda()
            # La página le pega el mensaje al final (``…&text=`` + el mensaje codificado).
            valores['wa_base'] = whatsapp.enlace(numero, '') if numero else ''
            valores.update(estado='vigente', clave_google=clave, nombre=(enlace.partner_id.name or '').split()[0]
                           if enlace.partner_id.name else '')
            return _pagina('dcasa_ubicacion.enlace_pagina', valores, con_mapa=bool(clave))
        return _pagina('dcasa_ubicacion.enlace_pagina', valores, status=200 if enlace else 404)

    def _tope_de_la_clienta(self):
        return _tope_en_pagina('dcasa_ubicacion.enlace_pagina', {
            'token': '', 'zona': '', 'imagen': '',
            'wa_otro': _whatsapp_de_la_tienda('Hola 👋 No me abre la página para marcar mi casa. ¿Me ayudan? 📍')})

    @http.route('/u/pedido/<int:orden_id>', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def enlace_del_pedido(self, orden_id, access_token=None, **_parametros):
        """El botón «Marcar mi casa en el mapa» de la página del pedido (el link de pago): con el permiso del pedido
        (su token o la sesión de la clienta) arma un enlace de un solo uso para su dirección de entrega y lleva ahí."""
        if _limite():
            return self._tope_de_la_clienta()
        try:
            orden = CustomerPortal()._document_check_access('sale.order', orden_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.make_response('Not Found', headers=_cabeceras(**{
                'Content-Type': 'text/plain; charset=utf-8'}), status=404)
        if orden.state == 'cancel':
            return request.redirect(orden.get_portal_url())
        destino = (orden.partner_shipping_id or orden.partner_id).sudo()
        _enlace, url = request.env['dcasa.ubicacion.enlace']._crear(destino, orden=orden.sudo(), creado_por='pedido')
        return request.redirect('/u/' + url.rsplit('/u/', 1)[1], code=303, local=True)

    @http.route('/u/<string:token>/zona', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False, max_content_length=MAX_CUERPO)
    def enlace_zona(self, token, **_parametros):
        if _limite():
            return _demasiado()
        enlace = self._enlace(token)
        if not enlace or enlace.estado != 'vigente':
            return _json({'error': 'Este enlace ya no sirve.'}, 404)
        cuerpo = _cuerpo() or {}
        try:
            datos = vista_previa(request.env, cuerpo.get('lat'), cuerpo.get('lon'))
            if _pedido_ya_cobrado(enlace):
                # La venta ya está confirmada: nada de «Envío $15» (auditoría 1).
                datos.update(precio=None, mostrar_precio=False)
            return _json(datos)
        except UbicacionInvalida as error:
            return _json({'error': str(error.args[0]), 'motivo': error.motivo}, 422)

    @http.route('/u/<string:token>/buscar', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False, max_content_length=MAX_CUERPO)
    def enlace_buscar(self, token, **_parametros):
        if _limite():
            return _demasiado()
        enlace = self._enlace(token)
        if not enlace or enlace.estado != 'vigente':
            return _json({'error': 'Este enlace ya no sirve.'}, 404)
        return _json({'lugares': buscar_lugares(request.env, (_cuerpo() or {}).get('texto'))})

    @http.route('/u/<string:token>/guardar', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False, max_content_length=MAX_CUERPO)
    def enlace_guardar(self, token, **_parametros):
        if _limite():
            return _demasiado()
        enlace = self._enlace(token)
        if not enlace or enlace.estado != 'vigente':
            return _json({'error': 'Este enlace ya no sirve.'}, 404)
        cuerpo = _cuerpo() or {}
        origen = cuerpo.get('origen')
        if origen not in ('gps', 'pin', 'busqueda'):
            return _json({'error': 'No sabemos cómo marcó el punto: vuelva a intentarlo.'}, 400)
        referencia = geo.texto_corto(cuerpo.get('referencia'), geo.MAX_REFERENCIA)
        if not referencia:
            return _json({'error': 'Cuéntenos cómo reconocer el sitio (color de la casa, portón, un punto de '
                                   'referencia).', 'campo': 'referencia'}, 400)
        # Opcionales (que no estorben): quién recibe y otro teléfono de Panamá por si no contesta.
        recibe = casa.recibe_limpio(cuerpo.get('recibe'))
        telefono = geo.texto_corto(cuerpo.get('telefono'), casa.MAX_TELEFONO)
        if telefono and not casa.telefono_de_respaldo(telefono):
            return _json({'error': casa.MENSAJE_TELEFONO, 'campo': 'telefono'}, 400)
        try:
            zona = enlace._confirmar(cuerpo.get('lat'), cuerpo.get('lon'), origen,
                                     precision=cuerpo.get('precision'), referencia=referencia,
                                     recibe=recibe, telefono=telefono)
        except UbicacionInvalida as error:
            return _json({'error': str(error.args[0]), 'motivo': error.motivo}, 422)
        return _json({'ok': True, 'zona': zona['texto']})

    @http.route('/u/<string:token>/foto', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False, max_content_length=casa.MAX_FOTO_BYTES)
    def enlace_foto(self, token, **_parametros):
        """La foto de la fachada (opcional). El cuerpo es la imagen tal cual (la página la achica antes); aquí se abre
        con PIL, se le quita el EXIF y se guarda como JPEG en la ficha. Sirve mientras el enlace esté vigente y hasta
        una hora después de usarlo («Sí, aquí es» puede llegar antes que la foto)."""
        if _limite():
            return _demasiado()
        enlace = self._enlace(token)
        if not enlace or (enlace.estado == 'usado'
                          and enlace.usado_el < fields.Datetime.now() - FOTO_DESPUES_DE_USAR):
            return _json({'error': 'Este enlace ya no sirve.'}, 404)
        if enlace.sudo().fotos_subidas >= MAX_FOTOS_POR_ENLACE:
            return _demasiado()
        # A lo sumo dos fotos a la vez por proceso (abrir una cuesta memoria): la tercera espera su turno en el
        # navegador en vez de tumbar Odoo (auditoría 1).
        if not _FOTOS_A_LA_VEZ.acquire(blocking=False):
            return _json({'error': 'Estamos ocupados: intente otra vez en un momento.', 'motivo': 'ocupado'}, 503)
        try:
            # get_data() con caché: si la base reintenta la petición, el cuerpo sigue ahí (sin caché llegaba vacío).
            datos = request.httprequest.get_data()
            enlace.sudo().fotos_subidas += 1
            enlace.partner_id._dcasa_poner_fachada(datos)
        except casa.FotoInvalida as error:
            return _json({'error': str(error.args[0]), 'motivo': error.motivo}, 422)
        finally:
            _FOTOS_A_LA_VEZ.release()
        return _json({'ok': True})

    # --- La página del motorizado (QR) -----------------------------------------------------------------------------

    @http.route('/entrega/<string:token>', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def entrega_pagina(self, token, **_parametros):
        if _limite():
            return _tope_en_pagina('dcasa_ubicacion.entrega_pagina', {'datos': None})
        entrega = request.env['dcasa.ubicacion.entrega']._del_secreto(token)
        empresa = request.env.company.sudo()
        if not entrega:
            return _pagina('dcasa_ubicacion.entrega_pagina', {'empresa': empresa.name, 'datos': None}, status=404)
        datos = entrega._para_el_motorizado()
        if not datos['tiene_punto']:
            datos['buscar_en_maps'] = buscar_en_google_maps(datos)
        return _pagina('dcasa_ubicacion.entrega_pagina', {'empresa': empresa.name, 'datos': datos})

    @http.route('/entrega/<string:token>/fachada', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def entrega_fachada(self, token, **_parametros):
        """La foto de la casa para el motorizado: con el secreto de su página (vence con ella), sin caché y sin que la
        indexe nadie. Sin foto, vencida o inventada: 404."""
        if _limite():
            return _demasiado(en_json=False)
        entrega = request.env['dcasa.ubicacion.entrega']._del_secreto(token)
        orden = entrega.order_id.sudo() if entrega else None
        jpeg = (orden.partner_shipping_id or orden.partner_id)._dcasa_fachada_jpeg() if orden else None
        if not jpeg:
            return request.make_response('Not Found', status=404, headers=_cabeceras(**{
                'Content-Type': 'text/plain; charset=utf-8'}))
        return request.make_response(jpeg, headers=_cabeceras(**{
            'Content-Type': 'image/jpeg', 'Content-Disposition': 'inline; filename="casa.jpg"',
            'Content-Security-Policy': "default-src 'none'; sandbox", 'Cross-Origin-Resource-Policy': 'same-origin'}))

    # --- La vista previa del checkout ------------------------------------------------------------------------------

    @http.route('/tienda/ubicacion/zona', type='jsonrpc', auth='public', website=True, methods=['POST'])
    def tienda_zona(self, lat=None, lon=None, texto=None, con_mapa=True, **_parametros):
        # ``motivo: 'tope'``: no es que el punto no sirva; la página lo deja reintentar (auditoría 2).
        if _limite():
            return {'error': 'Muchos intentos seguidos: espere un minuto.', 'motivo': 'tope'}
        try:
            return vista_previa(request.env, lat, lon, geo.texto_corto(texto, 300), con_mapa=con_mapa is not False)
        except UbicacionInvalida as error:
            return {'error': str(error.args[0]), 'motivo': error.motivo}

    @http.route('/tienda/ubicacion/buscar', type='jsonrpc', auth='public', website=True, methods=['POST'])
    def tienda_buscar(self, texto=None, **_parametros):
        if _limite():
            return {'error': 'Muchos intentos seguidos: espere un minuto.', 'motivo': 'tope'}
        return {'lugares': buscar_lugares(request.env, texto)}
