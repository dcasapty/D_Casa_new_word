from . import models


def _dcasa_invoice_post_init(env):
    """Aplica el formato D'CASA (layout y hoja carta) a los documentos de la empresa principal."""
    company = env.ref('base.main_company')
    company.write({
        'external_report_layout_id': env.ref('dcasa_invoice.external_layout_dcasa').id,
        'paperformat_id': env.ref('dcasa_invoice.paperformat_dcasa_carta').id,
        'display_invoice_amount_total_words': True,
    })
