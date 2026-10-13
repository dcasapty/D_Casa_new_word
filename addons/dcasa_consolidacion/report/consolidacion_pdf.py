from odoo import api, models


def formateador(moneda):
    """Importes con el símbolo de la moneda; el cero se muestra como raya."""
    return lambda valor: moneda.format(valor) if valor else '—'


class ReporteConsolidacionPdf(models.AbstractModel):
    _name = 'report.dcasa_consolidacion.reporte_consolidacion'
    _description = 'Consolidación en PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['dcasa.consolidacion'].browse(docids)
        docs.check_access('read')
        return {
            'doc_ids': docids,
            'doc_model': 'dcasa.consolidacion',
            'docs': docs,
            'formatos': {doc.id: formateador(doc.currency_id) for doc in docs},
            'matrices': {doc.id: doc._matriz() for doc in docs},
        }
