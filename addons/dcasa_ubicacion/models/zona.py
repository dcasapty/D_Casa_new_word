"""Servicios de la ubicación: la zona de un punto (con la tabla de la calculadora), el precio del envío a ese punto y,
si hay clave, la calle que da Google. Nada aquí guarda nada ni escribe coordenadas en el registro."""
import logging
import os
import re
import threading
from collections import OrderedDict
from datetime import date

import requests

from odoo import api, models
from odoo.exceptions import UserError

from ..motor import geo

_logger = logging.getLogger(__name__)

VARIABLE_CLAVE_NAVEGADOR = 'GOOGLE_MAPS_CLAVE_NAVEGADOR'
VARIABLE_CLAVE_SERVIDOR = 'GOOGLE_MAPS_CLAVE_SERVIDOR'
FORMA_CLAVE = re.compile(r'^[A-Za-z0-9_-]{20,80}$')
URL_GEOCODING = 'https://maps.googleapis.com/maps/api/geocode/json'
ESPERA_GOOGLE_S = 4
MAX_CACHE = 500
MAX_CONSULTAS_GOOGLE_DIA = 800     # por proceso y por día; el presupuesto y la cuota se ponen además en Google Cloud

_cache_calles = OrderedDict()       # (lat, lon) redondeados a 5 decimales (≈ 1 m) → calle; para no pagar dos veces
_candado = threading.Lock()
_consultas_de_hoy = [None, 0]       # [día, cuántas] — el tope diario de Geocoding


class UbicacionInvalida(UserError):
    """Un punto que no sirve. ``motivo``: ``coordenadas`` (no son números de Panamá) o ``fuera_de_panama`` (con la
    tabla cargada, no hay ningún lugar a 25 km: mar, Costa Rica o Colombia)."""

    def __init__(self, mensaje, motivo):
        super().__init__(mensaje)
        self.motivo = motivo


def clave(variable):
    """La clave de Google del entorno (Cloudflare la pasa al contenedor), o ``''`` si falta o tiene mala forma."""
    valor = (os.environ.get(variable) or '').strip()
    return valor if FORMA_CLAVE.match(valor) else ''


class DcasaUbicacion(models.AbstractModel):
    _name = 'dcasa.ubicacion'
    _description = 'Ubicación de entrega: zona, precio y calle'

    @api.model
    def _clave_navegador(self):
        """La clave del mapa en el navegador (se ve en la página: Google la limita a los sitios de la tienda)."""
        return clave(VARIABLE_CLAVE_NAVEGADOR)

    @api.model
    def _validar(self, lat, lon):
        """``(lat, lon, zona)`` de un punto que sirve, o ``UbicacionInvalida``."""
        valido = geo.punto(lat, lon)
        if not valido:
            raise UbicacionInvalida(self.env._('No pudimos leer esa ubicación: tiene que ser un punto de Panamá.'),
                                    'coordenadas')
        zona = self._zona(*valido)
        if not geo.en_cobertura(zona):
            raise UbicacionInvalida(self.env._('Ese punto no está en Panamá (o está en el mar). Revisa el mapa y '
                                               'marca el lugar de entrega.'), 'fuera_de_panama')
        return valido[0], valido[1], zona

    @api.model
    def _zona(self, lat, lon):
        """La zona del punto con la tabla de la calculadora (``geo.deducir_zona``) más el registro del lugar que pone
        el precio (``lugar``, vacío si no hay ninguno a 3 km) y el texto («Brisas del Golf · Rufina Alfaro · …»)."""
        Lugar = self.env['dcasa.envio.lugar'].sudo()
        indice, ids = Lugar._indice()
        zona = geo.deducir_zona(indice.lugares, lat, lon)
        zona['lugar'] = Lugar.browse(ids[zona['precio']]).exists() if zona['precio'] is not None else Lugar
        zona['texto'] = geo.zona_texto(zona)
        return zona

    @api.model
    def _distritos(self):
        """Los distritos de la tabla (para avisar si lo escrito nombra otro distrito que el del punto)."""
        indice, _ids = self.env['dcasa.envio.lugar'].sudo()._indice()
        return sorted({lugar['dist'] for lugar in indice.lugares if lugar.get('dist')})

    @api.model
    def _precio(self, lugar):
        """El precio del envío al lugar que puso la zona, con las mismas reglas con que Juan se lo da a un cliente:
        la tarifa aprobada por Gerencia, el lugar revisado y con precio (no «se cotiza aparte»).

        ``{'con_precio': True, 'total', 'total_txt', 'lugar'}`` o ``{'con_precio': False, 'motivo'}`` con motivo
        ``sin_lugar``, ``en_revision``, ``sin_revisar`` o ``aparte``."""
        if not lugar:
            return {'con_precio': False, 'motivo': 'sin_lugar'}
        Tarifa = self.env['dcasa.envio.tarifa'].sudo()
        if not Tarifa._estado_publico().get('aprobada'):
            return {'con_precio': False, 'motivo': 'en_revision'}
        lugar = lugar.sudo()
        if not lugar.exists() or not lugar.active:
            return {'con_precio': False, 'motivo': 'sin_lugar'}     # un lugar archivado ya no da precio
        if not lugar.revisado:
            return {'con_precio': False, 'motivo': 'sin_revisar'}
        cotizacion = Tarifa.cotizar_lugar(lugar)
        if not cotizacion.get('con_precio'):
            return {'con_precio': False, 'motivo': 'aparte'}
        return {'con_precio': True, 'total': cotizacion['total'], 'total_txt': cotizacion['total_txt'],
                'lugar': lugar}

    @api.model
    def _calle_de_google(self, lat, lon):
        """La dirección que da Google para el punto (Geocoding, clave del servidor), o ``''``. Es una ayuda: si no
        hay clave, si Google tarda más de 4 s o responde otra cosa, no pasa nada. Nunca escribe el punto en el
        registro."""
        llave = clave(VARIABLE_CLAVE_SERVIDOR)
        if not llave:
            return ''
        guardada = (round(lat, 5), round(lon, 5))
        with _candado:
            if guardada in _cache_calles:
                _cache_calles.move_to_end(guardada)
                return _cache_calles[guardada]
            # Tope diario por proceso (auditoría 1): cada consulta a Google se paga y el checkout no tiene límite
            # por IP. Pasado el tope no se pide la calle (es una ayuda): el punto, la zona y el precio siguen.
            hoy = date.today()
            if _consultas_de_hoy[0] != hoy:
                _consultas_de_hoy[:] = [hoy, 0]
            if _consultas_de_hoy[1] >= MAX_CONSULTAS_GOOGLE_DIA:
                return ''
            _consultas_de_hoy[1] += 1
        try:
            respuesta = requests.get(URL_GEOCODING, params={
                'latlng': f'{lat:.7f},{lon:.7f}', 'key': llave, 'language': 'es', 'region': 'pa',
                'result_type': 'street_address|route|premise|establishment|point_of_interest|neighborhood',
            }, timeout=ESPERA_GOOGLE_S)
            datos = respuesta.json() if respuesta.ok else {}
        except (requests.RequestException, ValueError):
            _logger.warning('Ubicación: Google Geocoding no respondió a tiempo.')
            return ''
        if datos.get('status') not in ('OK', 'ZERO_RESULTS'):
            _logger.warning('Ubicación: Google Geocoding respondió %s.', str(datos.get('status'))[:40])
            return ''
        calle = ''
        for resultado in datos.get('results') or []:
            texto = geo.texto_corto(resultado.get('formatted_address') or '')
            if texto and '+' not in texto.split(',')[0]:        # sin «Plus Codes» («7Q2F+3X …»)
                calle = texto
                break
        with _candado:
            _cache_calles[guardada] = calle
            while len(_cache_calles) > MAX_CACHE:
                _cache_calles.popitem(last=False)
        return calle
