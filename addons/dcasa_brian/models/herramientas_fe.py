"""Factura electrónica (DGI) para Brian: SOLO lectura.

Brian dice cómo van los envíos al PAC, cuáles rechazó la DGI y qué lleva demasiado en
contingencia. Nunca envía, regenera ni anula: eso son botones de Facturación con su
propio control de grupo. Si ``dcasa_fe_pa`` no está instalado, la herramienta lo dice.
"""
from odoo import api, models

from . import herramientas_comun as c
from .registro import herramienta

FACTURACION = ('account.group_account_invoice',)
MODELO = 'dcasa.fe.documento'


class BrianHerramientasFe(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_fe_doc(self, doc):
        return {
            'factura': doc.move_id.name or '',
            'cliente': doc.partner_id.display_name or '',
            'numero_dgi': f'{doc.punto}-{doc.numero}',
            'estado': dict(doc._fields['estado'].selection).get(doc.estado, doc.estado),
            'error': (doc.error or '')[:300],
            'en_contingencia_desde': c.fecha(doc.contingencia_inicio) if doc.contingencia_inicio else '',
        }

    @herramienta(
        nombre='estado_factura_electronica',
        descripcion='Cómo va la factura electrónica de la DGI: cuántos documentos hay por estado (autorizados, '
                    'por enviar, rechazados, en contingencia) y cuáles piden atención. Solo consulta.',
        parametros={'dias': {'type': 'integer', 'description': 'Cuántos días hacia atrás. Por defecto 30.'}},
        nivel='lectura', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['¿hay facturas rechazadas por la DGI? → estado_factura_electronica',
                  '¿cómo van los envíos al PAC? → estado_factura_electronica'],
    )
    def _h_estado_factura_electronica(self, dias=30):
        if MODELO not in self.env:
            return {'activa': False, 'mensaje': 'La factura electrónica (módulo dcasa_fe_pa) no está instalada.'}
        company = self.env.company
        resumen = self.env[MODELO]._resumen(dias=max(1, min(int(dias or 30), 366)))
        return {
            'activa': bool(company.l10n_pa_fe_activo and company.l10n_pa_fe_adaptador),
            'modo_contingencia': bool(company.l10n_pa_fe_contingencia),
            'por_estado': resumen['conteo'],
            'piden_atencion': [self._b_fe_doc(doc) for doc in resumen['atencion'][:c.MAX_FILAS]],
        }
