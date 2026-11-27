"""El chat de la tienda (Andrés): cuando el cliente tocó «Usar mi ubicación actual» y escribió el número de casa y las
indicaciones, la página los guarda en SU carrito (``POST /dcasa/brian/v1/carrito/ubicacion``). Al pagar, el checkout
ya trae ese punto y esas indicaciones: el cliente solo toca «Sí, aquí es» (docs/UBICACION.md).

Mismas reglas que las demás rutas del carrito del chat (``_post``: CSRF en la cabecera, JSON de a lo sumo 2 KB, el chat
encendido) y el límite por IP de la ubicación. Las coordenadas no se escriben en el registro. Un GPS de más de 100 m
de error no se guarda (``motivo: 'impreciso'``): Andrés le pide intentarlo en su puerta. Pero la casa que escribió sí
(``casa_guardada``): sin eso, al pagar tenía que escribirla otra vez (auditoría 2).
"""
from odoo import http
from odoo.addons.dcasa_brian_tienda.controllers.main import MAX_CUERPO, RAIZ, DcasaBrianTiendaAPI, _json
from odoo.http import request

from ..models.zona import UbicacionInvalida
from ..motor import geo
from .publico import _limite


class TiendaUbicacion(DcasaBrianTiendaAPI):

    @http.route(f'{RAIZ}/carrito/ubicacion', type='http', auth='public', website=True, methods=['POST'], csrf=False,
                sitemap=False, max_content_length=MAX_CUERPO)
    def carrito_ubicacion(self, **_kw):
        return self._post(self._guardar_ubicacion_del_carrito)

    def _guardar_ubicacion_del_carrito(self, cuerpo):
        if _limite():
            return _json({'ok': False, 'motivo': 'tope'}, 429)
        referencia = geo.texto_corto(cuerpo.get('referencia'), geo.MAX_REFERENCIA)
        if not referencia:
            return _json({'ok': False, 'motivo': 'indicaciones'}, 400)
        precision = geo.precision_m(cuerpo.get('precision'))
        if precision is not None and precision > geo.PRECISION_MAX_M:
            # Un GPS de ±800 m no es su casa (auditoría 1): Andrés le pide intentarlo en su puerta; el punto no se
            # guarda. La casa que escribió, sí: el checkout la trae (auditoría 2). Un punto bueno de antes se queda.
            orden = request.cart or request.website._create_cart()
            orden.sudo().write({'dcasa_ubic_pend_referencia': referencia})
            return _json({'ok': False, 'motivo': 'impreciso', 'precision': precision, 'casa_guardada': True}, 422)
        try:
            lat, lon, zona = request.env['dcasa.ubicacion']._validar(cuerpo.get('lat'), cuerpo.get('lon'))
        except UbicacionInvalida as error:
            return _json({'ok': False, 'motivo': error.motivo}, 422)
        orden = request.cart or request.website._create_cart()
        orden.sudo().write({
            'dcasa_ubic_pend_lat': lat, 'dcasa_ubic_pend_lon': lon,
            'dcasa_ubic_pend_precision': precision or 0,
            'dcasa_ubic_pend_referencia': referencia,
        })
        return _json({'ok': True, 'zona': zona['texto']})
