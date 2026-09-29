from . import models

DCASA_LANG = 'es_419'


def _setup_panama_accounting(env):
    """Plan contable e ITBMS de Panamá (``l10n_pa``) en USD.

    Solo actúa si la empresa aún no tiene asientos contables: sobre una base con
    contabilidad existente no se cambia ni el plan ni la moneda.
    """
    company = env.ref('base.main_company')
    if company.root_id._existing_accounting():
        return
    if company.chart_template != 'pa':
        env['account.chart.template'].try_loading('pa', company, force_create=True)
    # Panamá factura en dólares; el plan ``pa`` deja la moneda del país (PAB).
    usd = env.ref('base.USD')
    usd.active = True
    previous_currency = company.currency_id
    company.currency_id = usd
    # Las listas de precios creadas mientras la empresa estaba en PAB también
    # pasan a USD (si no, las ventas y facturas saldrían en balboas).
    if previous_currency != usd:
        env['product.pricelist'].with_context(active_test=False).search([
            ('company_id', 'in', [company.id, False]),
            ('currency_id', '=', previous_currency.id),
        ]).currency_id = usd


def _formato_panama(env):
    """Números como en Panamá: $1,070.50 (punto decimal, coma de miles).

    El es_419 de Odoo trae coma decimal («$ 1.070,50»), que en Panamá se lee mal.
    """
    lang = env['res.lang'].with_context(active_test=False)._lang_get(DCASA_LANG)
    if lang:
        lang.write({'decimal_point': '.', 'thousands_sep': ','})


def _dcasa_base_post_init(env):
    """Deja la empresa lista para facturar en Panamá."""
    # Al instalar ``account`` en una base nueva, Odoo difiere la carga del plan
    # contable hasta el final de la carga del registro (``_register_hook``) y
    # cargaría el plan genérico encima del nuestro. Nos colgamos de ese mismo
    # punto para que el plan de Panamá sea el último en aplicarse.
    if hasattr(env.registry, '_auto_install_template'):
        env.registry._auto_install_template = _setup_panama_accounting
    else:
        _setup_panama_accounting(env)

    # Adjuntos en base de datos: el contenedor en Cloudflare no tiene disco persistente.
    icp = env['ir.config_parameter'].sudo()
    if icp.get_param('ir_attachment.location') != 'db':
        icp.set_param('ir_attachment.location', 'db')
        env['ir.attachment'].force_storage()

    # Español por defecto: facturas y monto en letras en español.
    if env['res.lang']._activate_lang(DCASA_LANG):
        env.ref('base.main_company').partner_id.lang = DCASA_LANG
        env['ir.default'].set('res.partner', 'lang', DCASA_LANG)
    _formato_panama(env)
