"""Lo que «Brian de la tienda» agrega a Juan: sus ajustes en ``GET /dcasa/juan/v1/config`` y su renglón en «Costos de
IA» (contrato §5, contrato_cambios §3 y §4).

Brian usa los mismos modelos y la misma cuenta que Juan: lo que gasta en modelos de **Meta** también lo cobra Meta, así
que esos renglones (``proveedor: "meta"``) se suman a «Por pagar a Meta» (``_otros_de_meta``; revisión, 2026-11-14). Los
de otros proveedores siguen solo en su renglón. La cuenta de Juan no cambia."""
import math
import re

from odoo import api, models

MAX_MODELOS = 10      # renglones que se muestran (lo de Meta se suma con todos los que vengan, hasta MAX_RENGLONES)
MAX_RENGLONES = 100
PROVEEDOR_META = 'meta'
RE_MES = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def _numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor) and valor >= 0


def tienda_de_costos(cuerpo):
    """El bloque ``tienda`` que mandó el Worker en ``/odoo/costos``, limpio. Si no vino o no se entiende: ``sin_dato``
    (nunca un $0 inventado)."""
    crudo = (cuerpo or {}).get('tienda')
    if not isinstance(crudo, dict) or not _numero(crudo.get('usd')):
        return {'sin_dato': True}
    crudos = crudo.get('por_modelo') if isinstance(crudo.get('por_modelo'), list) else []
    renglones = [{
        'modelo': str(m.get('modelo') or '')[:80],
        'proveedor': str(m.get('proveedor') or '').strip().lower()[:40],
        'usd': round(float(m['usd']), 4),
        'turnos': int(m['turnos']) if _numero(m.get('turnos')) else 0,
        'estimado': bool(m.get('estimado')),
    } for m in crudos[:MAX_RENGLONES] if isinstance(m, dict) and _numero(m.get('usd'))]
    renglones.sort(key=lambda m: -m['usd'])
    mes = crudo.get('mes')
    return {
        'sin_dato': False,
        'mes': mes if isinstance(mes, str) and RE_MES.match(mes) else None,
        # Lo de modelos de Meta (por el ``proveedor`` de cada renglón, nunca por el nombre del modelo; también lo
        # estimado de un turno cortado): Meta lo cobra en la misma cuenta que Juan (va en «Por pagar a Meta»).
        'meta_usd': round(sum(m['usd'] for m in renglones if m['proveedor'] == PROVEEDOR_META), 4),
        'usd': round(float(crudo['usd']), 2),
        'turnos': int(crudo['turnos']) if _numero(crudo.get('turnos')) else 0,
        'presupuesto_usd': round(float(crudo['presupuesto_usd']), 2) if _numero(crudo.get('presupuesto_usd')) else None,
        'por_modelo': renglones[:MAX_MODELOS],
    }


class DcasaJuanAjustesTienda(models.Model):
    _inherit = 'dcasa.juan.ajustes'

    @api.private
    def como_json(self):
        datos = super().como_json()
        datos['brian_tienda'] = self.env['dcasa.brian.tienda']._para_el_worker()
        return datos


class DcasaJuanPanelTienda(models.AbstractModel):
    _inherit = 'dcasa.juan.panel'

    def _costos_extra(self, cuerpo):
        """Brian de la tienda en su propio renglón: nunca entra en el gasto de Juan (su tope). Lo de modelos de Meta va
        además en «Por pagar a Meta» (``_otros_de_meta``)."""
        datos = super()._costos_extra(cuerpo)
        datos['tienda'] = tienda_de_costos(cuerpo)
        return datos

    @api.model
    def _otros_de_meta(self, extra):
        otros = super()._otros_de_meta(extra)
        tienda = (extra or {}).get('tienda') or {}
        if otros or tienda.get('sin_dato', True):
            return otros
        return {'mes': tienda.get('mes') or self._ahora_local().strftime('%Y-%m'), 'usd': tienda['meta_usd']}

    @api.model
    def _otros_de_meta_ahora(self):
        otros = super()._otros_de_meta_ahora()
        if otros:
            return otros
        detalle = self.env['dcasa.juan.cliente'].costos()
        cuerpo = detalle['cuerpo'] if detalle['conectado'] and not detalle['error'] else {}
        return self._otros_de_meta({'tienda': tienda_de_costos(cuerpo)})
