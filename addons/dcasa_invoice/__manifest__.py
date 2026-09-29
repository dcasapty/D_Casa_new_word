{
    'name': "D'CASA Panamá — Factura",
    'summary': "Formato de factura con la marca D'CASA: RUC con DV, sello de pagado y monto en letras",
    'description': """
Plantilla de documentos (facturas, cotizaciones, órdenes) con la identidad de
D'CASA: la "placa" azul con banda amarilla, datos de la empresa con RUC y DV,
pie de página que no se corta, sello digital "PAGADO" con la fecha del pago y
el importe total en letras.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'account', 'sale'],
    'data': [
        'views/report_layout.xml',
        'views/report_invoice.xml',
        'data/report_layout_data.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'dcasa_invoice/static/src/scss/report_dcasa.scss',
        ],
    },
    'post_init_hook': '_dcasa_invoice_post_init',
    'installable': True,
}
