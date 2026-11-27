"""Checkout: guarda el punto de entrega con la dirección (views/checkout_templates.xml, docs/UBICACION.md).

Los campos ``dcasa_ubic_*`` y ``dcasa_referencia`` se sacan del formulario antes de que Odoo lo procese (no son de su
dirección) y, si Odoo aceptó la dirección, se guardan en la dirección de entrega del carrito:

* Solo cuenta en la dirección de **entrega** (o la que sirve de las dos, o la primera de una invitada:
  ``es_la_de_entrega``). En la de facturación sola el bloque no sale ni se exige (auditoría 1: pedía el mapa y la casa
  y no los guardaba).
* «Marcar en el mapa»: hace falta un punto de Panamá **confirmado** («Sí, aquí es», o «Confirmar» con el punto bueno:
  la página llena el «sí») y la referencia; si no, el formulario vuelve con el aviso, sin guardar nada. El origen vale
  si es de la página (GPS, mapa, búsqueda) o el del punto que ya tenía guardado (WhatsApp o un enlace de mapa: el
  checkout abre con él y ella solo dice «sí»). Si es el mismo punto guardado, se conserva su origen (y su precisión).
  Si lo escrito nombra otro distrito que el del punto (el aviso de cruce), hace falta además su «📍 Es aquí»
  (``dcasa_ubic_cruce_ok``): «Confirmar» se lo saltaba y guardaba la casa de La Chorrera para el regalo de San
  Miguelito (auditoría 2). Lo que llenó el mapa (la barriada y el distrito del punto) no cuenta como escrito.
* «Escribirla»: queda como escrita a mano (el chofer llama antes) y el envío se cotiza como siempre. Pero si ya
  tenía un punto **confiable** (de WhatsApp, por ejemplo), no se borra porque prefirió escribir (auditoría 1), salvo
  que lo escrito nombre otro distrito: entonces ese punto ya no es su casa.
* Opcionales, debajo del número de casa: **quién recibe** y **otro teléfono** de Panamá (``dcasa_recibe`` y
  ``dcasa_tel_respaldo``). Vienen llenos con lo de la ficha: vacíos, se borran. Un teléfono que no es de Panamá
  devuelve el formulario con el aviso, sin guardar nada.
* Guardado, el punto que dio en el chat de la tienda (el «pendiente» del carrito) se olvida: si no, volvería a ganarle
  a lo que acaba de confirmar. Con cuenta, Odoo no pasa por aquí: la tarjeta de arriba de ``/shop/checkout`` pregunta
  «¿Te entregamos ahí?» y «No» lo olvida (``/tienda/ubicacion/olvidar-chat``).
* Una invitada que vuelve atrás desde «Método de entrega» llega a ``/shop/address`` sin ``partner_id`` (un formulario
  vacío: perdía el punto, la casa y quién recibe): va a «Editar» su dirección de entrega (auditoría 2).

Después se vuelve a poner el método de entrega del carrito: así el precio del envío sale del punto nuevo.

La página «¡Gracias por su compra!» (``/shop/confirmation``) muestra la tarjeta «📍 Marcar mi casa en el mapa» si el
pedido va a domicilio y la casa no tiene un punto confiable (views/pedido_templates.xml).
"""
import json

from odoo.addons.website_dcasa.controllers.main import DcasaCheckout
from odoo.http import request, route
from odoo.tools import str2bool

from ..models.zona import UbicacionInvalida
from ..motor import casa, geo

CAMPOS = ('dcasa_ubic_modo', 'dcasa_ubic_lat', 'dcasa_ubic_lon', 'dcasa_ubic_origen', 'dcasa_ubic_precision',
          'dcasa_ubic_confirmada', 'dcasa_ubic_cruce_ok', 'dcasa_referencia')
ORIGENES_WEB = ('gps', 'pin', 'busqueda')
# El punto que ya tenía guardado (lo compartió por el chat o pegó un enlace de mapa): el checkout abre con él.
ORIGENES_GUARDADOS = ('whatsapp', 'enlace')
MISMO_PUNTO_GRADOS = 1e-6          # ≈ 10 cm: el mismo punto que está guardado
FALTA_EL_PUNTO = 'Marca tu casa en el mapa y toca «Sí, aquí es» (o elige «Escribir»).'
FALTAN_INDICACIONES = 'Escribe el número de casa y las indicaciones para el chofer.'
CAMPOS_CASA = ('dcasa_recibe', 'dcasa_tel_respaldo')
SIN_PENDIENTE = {'dcasa_ubic_pend_lat': 0.0, 'dcasa_ubic_pend_lon': 0.0, 'dcasa_ubic_pend_precision': 0,
                 'dcasa_ubic_pend_referencia': False}


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def quien_recibe_del_formulario(formulario):
    """``(recibe, telefono, error)`` de los campos opcionales del bloque: ``None`` si el campo no vino (un formulario
    viejo: no se toca la ficha), ``''`` si vino vacío (se borra) y el teléfono ya bien escrito («+507 6123-4567»).
    ``error``: el aviso si el teléfono no es de Panamá."""
    recibe = formulario.get('dcasa_recibe')
    texto = formulario.get('dcasa_tel_respaldo')
    recibe = None if recibe is None else casa.recibe_limpio(recibe)
    if texto is None:
        return recibe, None, None
    texto = geo.texto_corto(texto, casa.MAX_TELEFONO)
    if not texto:
        return recibe, '', None
    numero = casa.telefono_de_respaldo(texto)
    if not numero:
        return recibe, None, casa.MENSAJE_TELEFONO
    return recibe, numero['guardar'], None


def es_la_de_entrega(orden, partner_id, address_type, use_delivery_as_billing):
    """¿Esta dirección es (también) la de entrega del carrito? La de entrega, la que sirve de las dos, la primera de una
    invitada (Odoo la usa para todo) o la que ya es la de entrega del carrito. La misma regla que la plantilla
    (``dcasa_es_entrega``). ``use_delivery_as_billing`` llega como texto («True»/«False»)."""
    if address_type == 'delivery' or str2bool(use_delivery_as_billing or 'false', False):
        return True
    if not orden:
        return False
    if orden._is_anonymous_cart():
        return True
    try:
        partner = int(partner_id or 0)
    except (TypeError, ValueError):
        return False
    return bool(partner) and partner == orden.partner_shipping_id.id


def _mismo_punto(a, b):
    return bool(a and b) and abs(a[0] - b[0]) < MISMO_PUNTO_GRADOS and abs(a[1] - b[1]) < MISMO_PUNTO_GRADOS


def origen_a_guardar(destino, punto, origen, precision):
    """``(origen, precision)`` con que se guarda el punto confirmado en el checkout. Si es el mismo que ya tenía la
    ficha, el suyo (un «whatsapp» no se vuelve «pin» por decir «sí»). Un «whatsapp» o «enlace» con otro punto ya no
    es el del chat: lo confirmó en el mapa («pin»)."""
    guardado = destino._dcasa_ubic_punto()
    if _mismo_punto(guardado, punto):
        return destino.dcasa_ubic_origen, destino.dcasa_ubic_precision_m or None
    if origen in ORIGENES_GUARDADOS:
        return 'pin', None
    return origen, precision


def texto_escrito(formulario, zona):
    """Lo que escribió en la calle y la ciudad, sin lo que llenó el mapa (la barriada y el corregimiento del punto en la
    calle, su distrito en la ciudad: ``checkout_ubicacion.js``, ``llenarSiVacio``)."""
    relleno = {'street': ', '.join(p for p in (zona.get('barriada'), zona.get('corregimiento')) if p),
               'city': zona.get('distrito') or ''}
    partes = []
    for nombre in ('street', 'street2', 'city'):
        valor = geo.texto_corto(formulario.get(nombre) or '')
        if valor and valor != geo.texto_corto(relleno.get(nombre) or ''):
            partes.append(valor)
    return ', '.join(partes)


def cruce_sin_responder(formulario, zona, distritos, con_mapa=True):
    """El aviso de cruce que la página tenía que mostrar con «📍 Es aquí» / «🏠 Es otra casa», o ``''``. Solo si lo dice
    tanto lo escrito entero como lo escrito sin lo que llenó el mapa: la página compara sin lo que llenó ella, y un
    rechazo que la página no mostró dejaría al cliente sin salida."""
    todo = ', '.join(geo.texto_corto(formulario.get(n) or '') for n in ('street', 'street2', 'city'))
    if not geo.aviso_de_cruce(todo, zona, distritos, con_mapa=con_mapa):
        return ''
    return geo.aviso_de_cruce(texto_escrito(formulario, zona), zona, distritos, con_mapa=con_mapa)


def _calle(partner):
    """La calle como la tenía guardada (para saber si la cambió al «Escribir»)."""
    return tuple(' '.join((partner[n] or '').lower().split()) for n in ('street', 'street2', 'city')) if partner \
        else None


def conservar_punto_al_escribir(destino, formulario, calle_antes=None):
    """«Escribir» con un punto confiable guardado: ¿se queda? Sí, salvo que lo escrito nombre otro distrito que el del
    punto, o que haya escrito OTRA calle (se mudó dentro del mismo distrito: el punto viejo ya no es su casa y el
    chofer iría a la vieja; auditoría 2)."""
    if not destino._dcasa_ubic_punto() or not geo.es_confiable(destino.dcasa_ubic_origen,
                                                                destino.dcasa_ubic_precision_m or None):
        return False
    if calle_antes is not None and _calle(destino) != calle_antes:
        return False
    escrito = ', '.join(geo.texto_corto(formulario.get(n) or '') for n in ('street', 'street2', 'city'))
    cruce = geo.aviso_de_cruce(escrito, {'distrito': destino.dcasa_distrito or ''},
                               request.env['dcasa.ubicacion']._distritos())
    return not cruce


def _odoo_la_acepto(respuesta):
    """¿Odoo guardó la dirección? (Sin campos malos y sin mandarla de vuelta al carrito.)"""
    # Llamada con super(), la ruta de Odoo devuelve un Response (``route_wrapper``: ``Response.load``), no texto.
    texto = respuesta.get_data(as_text=True) if hasattr(respuesta, 'get_data') else respuesta
    try:
        resultado = json.loads(texto) if isinstance(texto, str) else None
    except ValueError:
        return False
    if not isinstance(resultado, dict) or resultado.get('invalid_fields'):
        return False
    return '/shop/cart' not in str(resultado.get('redirectUrl') or '')


def _lo_que_falta(referencia, error_del_telefono):
    """La respuesta del formulario con lo que falta o está mal (sin guardar nada), o ``None``."""
    if not referencia:
        # Siempre, en el mapa o escrita (el dueño, 2026-11-25, como en PedidosYa).
        return json.dumps({'invalid_fields': ['dcasa_referencia'], 'messages': [FALTAN_INDICACIONES]})
    if error_del_telefono:
        return json.dumps({'invalid_fields': ['dcasa_tel_respaldo'], 'messages': [error_del_telefono]})
    return None


def _el_punto_del_mapa(ubicacion, formulario):
    """``(punto, None)`` si el punto del mapa vale, o ``(None, respuesta)`` con lo que falta: un punto de Panamá
    confirmado, de un origen que vale, y el «📍 Es aquí» si lo escrito nombra otro distrito (auditoría 2)."""
    punto = geo.punto(_numero(ubicacion['dcasa_ubic_lat']), _numero(ubicacion['dcasa_ubic_lon']))
    if not punto or ubicacion['dcasa_ubic_origen'] not in ORIGENES_WEB + ORIGENES_GUARDADOS \
            or ubicacion['dcasa_ubic_confirmada'] != '1':
        return None, json.dumps({'invalid_fields': [], 'messages': [FALTA_EL_PUNTO]})
    Ubicacion = request.env['dcasa.ubicacion']
    try:
        _lat, _lon, zona = Ubicacion._validar(*punto)
    except UbicacionInvalida as error:
        return None, json.dumps({'invalid_fields': [], 'messages': [str(error.args[0])]})
    cruce = cruce_sin_responder(formulario, zona, Ubicacion._distritos(),
                                con_mapa=bool(Ubicacion.sudo()._clave_navegador()))
    if cruce and ubicacion['dcasa_ubic_cruce_ok'] != '1':
        return None, json.dumps({'invalid_fields': [], 'messages': [cruce]})
    return punto, None


class UbicacionCheckout(DcasaCheckout):

    @route()
    def shop_address(self, partner_id=None, address_type='billing', use_delivery_as_billing=None, **query_params):
        # La invitada que vuelve atrás desde el paso siguiente llega a «/shop/address» sin nada: Odoo le abría una
        # dirección NUEVA vacía (sin el punto, la casa ni quién recibe). Si su carrito ya tiene la de entrega, a
        # «Editar» esa (auditoría 2). Con cuenta, «/shop/address?address_type=…» es «Agregar dirección»: no se toca.
        orden = request.cart
        if (not partner_id and not request.httprequest.args and request.env.user._is_public() and orden
                and orden.state == 'draft' and not orden.only_services and orden.partner_shipping_id
                and not orden._is_anonymous_cart()):
            return request.redirect(
                f'/shop/address?partner_id={orden.partner_shipping_id.id}&address_type=delivery', code=303)
        return super().shop_address(partner_id=partner_id, address_type=address_type,
                                    use_delivery_as_billing=use_delivery_as_billing, **query_params)

    @route('/tienda/ubicacion/olvidar-chat', type='http', auth='public', website=True, methods=['POST'],
           sitemap=False)
    def olvidar_punto_del_chat(self, **_kw):
        """«No, en …» de la tarjeta «¿Te entregamos ahí?» de ``/shop/checkout``: olvida el punto que dio en el chat de
        la tienda (solo el de SU carrito; con el CSRF del sitio) y vuelve al checkout."""
        orden = request.cart
        if orden and orden.state in ('draft', 'sent') and orden.sudo()._dcasa_ubic_hay_pendiente():
            orden.sudo().write(SIN_PENDIENTE)
        return request.redirect('/shop/checkout', code=303)

    @route()
    def shop_address_submit(self, partner_id=None, address_type='billing', use_delivery_as_billing=None,
                            callback=None, **form_data):
        ubicacion = {campo: form_data.pop(campo, None) for campo in CAMPOS}
        de_la_casa = {campo: form_data.pop(campo) for campo in CAMPOS_CASA if campo in form_data}
        modo = ubicacion['dcasa_ubic_modo']
        de_entrega = es_la_de_entrega(request.cart, partner_id, address_type, use_delivery_as_billing)
        if modo not in ('mapa', 'escrita') or not de_entrega:
            # Sin el bloque (un formulario viejo, sin productos que entregar o la dirección de facturación): como
            # siempre.
            return super().shop_address_submit(partner_id=partner_id, address_type=address_type,
                                               use_delivery_as_billing=use_delivery_as_billing, callback=callback,
                                               **form_data)
        referencia = geo.texto_corto(ubicacion['dcasa_referencia'] or '', geo.MAX_REFERENCIA)
        recibe, telefono, error = quien_recibe_del_formulario(de_la_casa)
        problema = _lo_que_falta(referencia, error)
        if problema:
            return problema
        punto = None
        origen = ubicacion['dcasa_ubic_origen']
        if modo == 'mapa':
            punto, problema = _el_punto_del_mapa(ubicacion, form_data)
            if problema:
                return problema
        previo = request.env['res.partner'].sudo().browse(int(partner_id)).exists() \
            if str(partner_id or '').isdigit() else None
        calle_antes = _calle(previo) if previo else None
        respuesta = super().shop_address_submit(partner_id=partner_id, address_type=address_type,
                                                use_delivery_as_billing=use_delivery_as_billing, callback=callback,
                                                **form_data)
        orden = request.cart
        if not _odoo_la_acepto(respuesta) or not orden or not orden.partner_shipping_id:
            return respuesta
        destino = orden.partner_shipping_id.sudo()
        destino._dcasa_poner_quien_recibe(recibe=recibe, telefono=telefono, al_dia=False)
        if modo == 'mapa':
            origen, precision = origen_a_guardar(destino, punto, origen, _numero(ubicacion['dcasa_ubic_precision']))
            try:
                destino._dcasa_poner_ubicacion(punto[0], punto[1], origen, precision=precision,
                                               referencia=referencia, confirmada=True)
            except UbicacionInvalida as error:
                return json.dumps({'invalid_fields': [], 'messages': [str(error.args[0])]})
        elif conservar_punto_al_escribir(destino, form_data,
                                         calle_antes if previo and previo == destino else None):
            destino.write({'dcasa_referencia': referencia})
        else:
            destino._dcasa_poner_escrita(referencia=referencia)
        # Lo que dio en el chat de la tienda ya pasó por aquí: que no le gane a lo que acaba de confirmar.
        if orden.sudo()._dcasa_ubic_hay_pendiente():
            orden.sudo().write(SIN_PENDIENTE)
        if modo == 'mapa':
            # D'CASA tiene «Retiro en tienda»: si el cliente marcó su casa en el mapa, se elige sola la entrega a
            # domicilio (sin esto quedaba «Retiro en tienda — Gratis» marcado y el total salía sin envío). «Retiro en
            # tienda» sigue disponible: lo puede volver a elegir en el pago.
            orden.sudo()._dcasa_ubic_elegir_domicilio()
        # Con un pago abierto (o uno recién abierto que la pasarela tiene en borrador) o con un envío que puso una
        # persona NO se recalcula: cambiar el total haría que el pago ya abierto no confirme la venta (revisión
        # adversarial 2026-11-27).
        if orden.carrier_id and orden.carrier_id.dcasa_por_cotizar and not orden.sudo()._dcasa_ubic_no_recalcular():
            orden._set_delivery_method(orden.carrier_id)
        return respuesta
