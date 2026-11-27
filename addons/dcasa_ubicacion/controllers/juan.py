"""``POST /dcasa/juan/v1/ubicacion``: el Worker de Juan guarda la ubicación que la clienta compartió por el chat
(WhatsApp, Telegram, Messenger) o que venía en un enlace de mapa (docs/UBICACION.md, contrato §1).

Misma autenticación que el resto de la API de Juan. Las coordenadas llegan aquí sin pasar por el modelo de IA, se
guardan en la ficha de la clienta y **no** se escriben en el registro ni en la auditoría: lo que vuelve es la zona y
el resultado de ``cotizar_envio`` (auditado sin coordenadas), igual que «Usar mi ubicación» del chat de la tienda.
"""
import logging

from odoo import http
from odoo.addons.dcasa_conversaciones.controllers.juan import PREFIJO_HERRAMIENTA, RAIZ, JuanAPI, _Error, _respuesta

from ..models.zona import UbicacionInvalida
from ..motor import geo

_logger = logging.getLogger(__name__)

ORIGENES_DEL_CHAT = ('whatsapp', 'enlace')
MAX_CUERPO_UBICACION = 2048


class JuanAPIUbicacion(JuanAPI):

    @http.route(f'{RAIZ}/ubicacion', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def ubicacion(self, **_kw):
        return self._servir(self._guardar_ubicacion)

    def _guardar_ubicacion(self, entorno):
        cuerpo = self._cuerpo(MAX_CUERPO_UBICACION)
        conversacion_id = cuerpo.get('conversacion_id')
        if not isinstance(conversacion_id, int) or isinstance(conversacion_id, bool):
            raise _Error(400, '«conversacion_id» debe ser un número entero.')
        origen = cuerpo.get('origen')
        if origen not in ORIGENES_DEL_CHAT:
            raise _Error(400, '«origen» debe ser «whatsapp» o «enlace».')
        conv = entorno['dcasa.conversacion'].sudo().browse(conversacion_id).exists()
        if not conv:
            raise _Error(404, 'No existe esa conversación.')
        if not conv.partner_id:
            raise _Error(409, 'La conversación todavía no tiene ficha de cliente.')
        # La ficha de la clienta o, si en las últimas 24 horas se pidió el punto de otra dirección (otra casa, la de
        # entrega de una venta avisada), esa (auditoría 1).
        partner = conv._dcasa_ubic_destino(para_punto=True)
        try:
            zona = partner._dcasa_poner_ubicacion(
                cuerpo.get('lat'), cuerpo.get('lon'), origen, confirmada=True,
                nombre_lugar=cuerpo.get('nombre_lugar'), direccion=cuerpo.get('direccion'))
        except UbicacionInvalida as error:
            return _respuesta({'ok': False, 'error': str(error.args[0]), 'motivo': error.motivo}, 422)
        conv._aviso(partner._dcasa_ubic_aviso_para_el_equipo())
        # El precio por el mismo camino que una llamada del modelo: auditado (sin coordenadas) en ESTA conversación,
        # así ``agregar_envio`` reconoce el lugar si la clienta dice «sí, súmelo».
        resultado = entorno['brian.herramientas'].with_context(juan_conversacion_id=conv.id).ejecutar(
            PREFIJO_HERRAMIENTA + 'cotizar_envio', {}, canal='juan', auditar=True)
        envio = resultado.get('datos') if resultado.get('ok') else {
            'estado': 'error', 'por_ubicacion': True,
            'instruccion': resultado.get('error') or 'No se pudo cotizar el envío ahora: pídele el barrio.'}
        return _respuesta({'ok': True, 'resultado': {
            'guardada': True, 'zona': zona['texto'] or '', 'origen': geo.etiqueta(origen), 'envio': envio}})
