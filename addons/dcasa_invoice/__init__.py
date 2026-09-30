from . import models


def _dcasa_invoice_post_init(env):
    """Aplica el formato D'CASA a los documentos de la empresa principal."""
    company = env.ref('base.main_company')
    company.write({
        'external_report_layout_id': env.ref('dcasa_invoice.external_layout_dcasa').id,
        'display_invoice_amount_total_words': True,
    })
