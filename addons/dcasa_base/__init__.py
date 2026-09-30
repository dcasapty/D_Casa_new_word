from . import models

DCASA_LANG = 'es_419'
DCASA_TZ = 'America/Panama'
IMPUESTO_INCLUIDO = 'ITBMS 7% incluido'

# Formas de cobro de la tienda: (código, nombre, tipo de diario).
DIARIOS_COBRO = [
    ('EFE', 'Efectivo', 'cash'),
    ('YAPPY', 'Yappy', 'bank'),
    ('TARJ', 'Tarjeta', 'bank'),
]

# Menús raíz que una mueblería no usa en el día a día: quedan solo en modo desarrollador.
MENUS_OCULTOS = [
    'mail.menu_root_discuss',
    'calendar.mail_menu_calendar',
    'spreadsheet_dashboard.spreadsheet_dashboard_menu_root',
    'utm.menu_link_tracker_root',
    'base.menu_tests',
    'base.menu_management',
]


def _setup_panama_accounting(env):
    """Plan contable e ITBMS de Panamá (``l10n_pa``) en USD.

    Solo actúa si la empresa aún no tiene asientos contables: sobre una base con
    contabilidad existente no se cambia ni el plan ni la moneda.
    """
    company = env.ref('base.main_company')
    if company.root_id._existing_accounting():
        _configurar_ventas_panama(env)
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
    _configurar_ventas_panama(env)


def _configurar_ventas_panama(env):
    """Precios con ITBMS incluido y las formas de cobro de la tienda. Se puede repetir.

    En la tienda el precio de la etiqueta ya trae el ITBMS: con la empresa en «impuesto
    incluido» las cotizaciones y facturas muestran el importe con ITBMS (el mismo número
    de la etiqueta) y un producto nuevo nace con el ITBMS incluido. Los impuestos que ya
    existían (compras, exentos) conservan su comportamiento: se fija de forma explícita.
    """
    company = env.ref('base.main_company')
    Tax = env['account.tax'].with_context(active_test=False)
    impuestos = Tax.search([('company_id', '=', company.id)])
    impuestos.filtered(lambda t: not t.price_include_override).price_include_override = 'tax_excluded'

    base = company.account_sale_tax_id
    if base and not base.price_include:
        incluido = Tax.search([
            ('company_id', '=', company.id), ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', base.amount_type), ('amount', '=', base.amount),
            ('price_include_override', '=', 'tax_included'),
        ], limit=1) or base.copy({'name': IMPUESTO_INCLUIDO, 'price_include_override': 'tax_included'})
        _nombrar(base, 'ITBMS 7% (se suma al precio)')
        _nombrar(incluido, IMPUESTO_INCLUIDO)
        (base | incluido).invoice_label = 'ITBMS 7%'
        company.account_sale_tax_id = incluido
    company.account_price_include = 'tax_included'

    Journal = env['account.journal'].with_context(active_test=False)
    for codigo, nombre, tipo in DIARIOS_COBRO:
        if not Journal.search_count([('company_id', '=', company.id), ('code', '=', codigo)]):
            Journal.create({'name': nombre, 'code': codigo, 'type': tipo, 'company_id': company.id})


def _nombrar(registro, nombre):
    """El mismo nombre en todos los idiomas instalados (si no, cada idioma ve otro)."""
    registro.name = nombre
    idiomas = [codigo for codigo, _n in registro.env['res.lang'].get_installed()]
    registro.update_field_translations('name', dict.fromkeys(idiomas, nombre))


def _configurar_interfaz(env):
    """Odoo en español de Panamá, al grano: lo que la tienda usa y nada más. Se puede repetir.

    - Usuarios internos en español y hora de Panamá, con las traducciones cargadas.
    - Descuentos en la cotización y precios por tamaño (variantes) a la vista.
    - Al entrar se abre Ventas, no el chat.
    - Menús que no se usan (chat, calendario, tableros…) solo en modo desarrollador.
    - El almacén con el nombre de la tienda.
    """
    if env['res.lang']._activate_lang(DCASA_LANG):
        env['ir.module.module'].search([('state', '=', 'installed')])._update_translations([DCASA_LANG])
    env['ir.default'].set('res.partner', 'tz', DCASA_TZ)
    usuarios = env['res.users'].with_context(active_test=False).search([('share', '=', False)])
    usuarios.filtered(lambda u: u.lang != DCASA_LANG).lang = DCASA_LANG
    usuarios.filtered(lambda u: not u.tz).tz = DCASA_TZ
    ventas = env.ref('sale.action_quotations_with_onboarding', raise_if_not_found=False)
    if ventas:
        usuarios.filtered(lambda u: not u.action_id).action_id = ventas.id

    empleados = env.ref('base.group_user')
    for xmlid in ('sale.group_discount_per_so_line', 'product.group_product_variant'):
        grupo = env.ref(xmlid, raise_if_not_found=False)
        if grupo and grupo not in empleados.implied_ids:
            empleados.implied_ids = [(4, grupo.id)]

    desarrollador = env.ref('base.group_no_one')
    for xmlid in MENUS_OCULTOS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.group_ids = [(6, 0, desarrollador.ids)]

    # Se venden camas, no cuartos de cama: cantidades enteras en ventas, compras e inventario.
    unidades = env.ref('uom.decimal_product_uom', raise_if_not_found=False)
    if unidades:
        unidades.digits = 0
    _formato_panama(env)

    company = env.ref('base.main_company')
    almacen = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
    if almacen and almacen.name in ('My Company', 'YourCompany', company.name):
        almacen.name = "D'CASA La Chorrera"


def _formato_panama(env):
    """Números como en Panamá: $1,070.50 (punto decimal, coma de miles).

    El es_419 de Odoo trae coma decimal («$ 1.070,50»), que en Panamá se lee mal.
    """
    lang = env['res.lang'].with_context(active_test=False).search([('code', '=', DCASA_LANG)], limit=1)
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
    _configurar_interfaz(env)
