"""Lo que «Brian de la tienda» agrega a Juan: sus ajustes en ``GET /dcasa/juan/v1/config`` y su renglón en «Costos de
IA» (contrato §5, contrato_cambios §3 y §4)."""
import math

from odoo import api, models

MAX_MODELOS = 10


def _numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor) and valor >= 0


def tienda_de_costos(cuerpo):
    """El bloque ``tienda`` que mandó el Worker en ``/odoo/costos``, limpio. Si no vino o no se entiende: ``sin_dato``
    (nunca un $0 inventado)."""
    crudo = (cuerpo or {}).get('tienda')
    if not isinstance(crudo, dict) or not _numero(crudo.get('usd')):
        return {'sin_dato': True}
    por_modelo = [{
        'modelo': str(m.get('modelo') or '')[:80],
        'usd': round(float(m['usd']), 4),
        'turnos': int(m['turnos']) if _numero(m.get('turnos')) else 0,
        'estimado': bool(m.get('estimado')),
    } for m in (crudo.get('por_modelo') or [])[:MAX_MODELOS] if isinstance(m, dict) and _numero(m.get('usd'))]
    por_modelo.sort(key=lambda m: -m['usd'])
    return {
        'sin_dato': False,
        'usd': round(float(crudo['usd']), 2),
        'turnos': int(crudo['turnos']) if _numero(crudo.get('turnos')) else 0,
        'presupuesto_usd': round(float(crudo['presupuesto_usd']), 2) if _numero(crudo.get('presupuesto_usd')) else None,
        'por_modelo': por_modelo,
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
        """Brian de la tienda en su propio renglón: nunca entra en el gasto de Juan ni en «Por pagar a Meta»."""
        datos = super()._costos_extra(cuerpo)
        datos['tienda'] = tienda_de_costos(cuerpo)
        return datos
