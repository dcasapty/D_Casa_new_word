"""Interfaz de adaptador de PAC (Proveedor Autorizado Calificado) y el adaptador simulado.

El resto del módulo NO sabe qué PAC hay detrás: llama a cuatro operaciones y recibe un
``dict`` de respuesta con forma fija. Para enchufar un PAC real (ver docs/FACTURA_ELECTRONICA.md):

1. Crear ``models/pac_<nombre>.py`` con un AbstractModel ``dcasa.fe.pac.<nombre>`` que
   herede ``dcasa.fe.pac`` e implemente ``_enviar``, ``_consultar``, ``_anular`` y ``_descargar``.
2. Agregar la opción con ``selection_add`` a ``res.company.l10n_pa_fe_adaptador``.
3. Credenciales: variables de entorno del contenedor (``DCASA_FE_PAC_USUARIO``…), nunca en git.
4. Errores de red/tiempo de espera → ``resultado='error_comunicacion'`` (la cola reintenta);
   rechazo de validación del PAC o la DGI → ``'rechazado'`` con el mensaje tal cual.

Todo es privado (``_``): estos modelos no tienen ACL y nada de aquí se llama por RPC.

Respuesta (todas las claves opcionales salvo ``resultado``)::

    {'resultado': 'autorizado' | 'recibido' | 'rechazado' | 'error_comunicacion' | 'anulado',
     'cufe': str, 'qr': str, 'protocolo': str, 'fecha': datetime, 'mensaje': str,
     'respuesta': str  # lo que devolvió el PAC, para el histórico
    }
"""
import hashlib
import json
from urllib.parse import urlencode

from lxml import etree

from odoo import fields, models

from . import catalogos as C

AUTORIZADO, RECIBIDO, RECHAZADO, ERROR_COMUNICACION, ANULADO = (
    'autorizado', 'recibido', 'rechazado', 'error_comunicacion', 'anulado')

# Parámetro que gobierna el simulado (staging y pruebas): autorizar | rechazar | caido | pendiente.
PARAM_MODO_SIMULADO = 'dcasa_fe_pa.simulado_modo'


class DcasaFePac(models.AbstractModel):
    _name = 'dcasa.fe.pac'
    _description = 'Adaptador de PAC (interfaz)'

    def _enviar(self, documento):
        """Envía ``documento.payload`` al PAC. Debe devolver la respuesta normalizada."""
        raise NotImplementedError

    def _consultar(self, documento):
        """Estado de un documento ya recibido por el PAC (``recibido`` → ``autorizado``/``rechazado``)."""
        raise NotImplementedError

    def _anular(self, documento, motivo):
        """Registra el evento de anulación de una FE autorizada."""
        raise NotImplementedError

    def _descargar(self, documento, tipo):
        """Descarga el XML autorizado (``tipo='xml'``) o el CAFE en PDF (``tipo='cafe'``): bytes o None."""
        raise NotImplementedError


class DcasaFePacSimulado(models.AbstractModel):
    """PAC de mentira para pruebas y staging: no sale a internet.

    Valida que el payload sea XML y que el CUFE cuadre; luego responde según el parámetro
    ``dcasa_fe_pa.simulado_modo``. El QR apunta al ambiente de pruebas de la DGI y dice
    SIMULADO: nunca puede pasar por una factura autorizada de verdad.
    """
    _name = 'dcasa.fe.pac.simulado'
    _inherit = 'dcasa.fe.pac'
    _description = 'PAC simulado'

    def _modo(self):
        return self.env['ir.config_parameter'].sudo().get_param(PARAM_MODO_SIMULADO, 'autorizar')

    def _protocolo(self, documento):
        return 'SIM' + hashlib.sha256(documento.cufe.encode()).hexdigest()[:17].upper()

    def _qr(self, documento):
        parametros = {'chFE': documento.cufe, 'iAmb': '2', 'digestValue': 'SIMULADO', 'jwt': 'SIMULADO'}
        return f"{C.URL_QR['2']}?{urlencode(parametros)}"

    def _enviar(self, documento):
        modo = self._modo()
        if modo == 'caido':
            return {'resultado': ERROR_COMUNICACION, 'mensaje': 'PAC simulado: sin conexión.'}
        try:
            raiz = etree.fromstring(documento.payload.encode())
        except (etree.XMLSyntaxError, AttributeError):
            return {'resultado': RECHAZADO, 'mensaje': 'PAC simulado: el payload no es XML válido.'}
        did = raiz.findtext(f'{{{C.NAMESPACE}}}dId')
        if did != documento.cufe or not C.cufe_valido(did):
            return {'resultado': RECHAZADO, 'mensaje': 'PAC simulado: el CUFE no cuadra con el documento.'}
        if modo == 'rechazar':
            return {'resultado': RECHAZADO, 'mensaje': 'PAC simulado: rechazo de prueba (código SIM-99).',
                    'respuesta': json.dumps({'codigo': 'SIM-99'})}
        if modo == 'pendiente':
            return {'resultado': RECIBIDO, 'mensaje': 'PAC simulado: recibido, en proceso.'}
        return self._autorizacion(documento)

    def _autorizacion(self, documento):
        protocolo = self._protocolo(documento)
        return {'resultado': AUTORIZADO, 'cufe': documento.cufe, 'qr': self._qr(documento),
                'protocolo': protocolo, 'fecha': fields.Datetime.now(),
                'mensaje': 'PAC simulado: autorizado el uso (ambiente de pruebas).',
                'respuesta': json.dumps({'protocolo': protocolo, 'simulado': True})}

    def _consultar(self, documento):
        modo = self._modo()
        if modo == 'caido':
            return {'resultado': ERROR_COMUNICACION, 'mensaje': 'PAC simulado: sin conexión.'}
        if modo == 'pendiente':
            return {'resultado': RECIBIDO, 'mensaje': 'PAC simulado: sigue en proceso.'}
        if modo == 'rechazar':
            return {'resultado': RECHAZADO, 'mensaje': 'PAC simulado: rechazo de prueba (código SIM-99).'}
        return self._autorizacion(documento)

    def _anular(self, documento, motivo):
        if self._modo() == 'caido':
            return {'resultado': ERROR_COMUNICACION, 'mensaje': 'PAC simulado: sin conexión.'}
        return {'resultado': ANULADO, 'fecha': fields.Datetime.now(),
                'mensaje': f'PAC simulado: anulación registrada ({motivo}).'}

    def _descargar(self, documento, tipo):
        if tipo == 'xml':
            return (documento.payload or '').encode()
        return None
