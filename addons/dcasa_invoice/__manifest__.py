{
    'name': "D'CASA Panamá — Factura",
    'summary': "Formato de factura con la marca D'CASA: en español, Cédula/RUC con DV, pago verídico y monto en letras",
    'description': """
Plantilla de documentos (facturas, cotizaciones, órdenes) con la identidad de
D'CASA: la "placa" azul con banda amarilla, datos de la empresa con RUC y DV,
pie de página que no se corta y tipografía de marca alojada en el módulo.

* Siempre en español: etiquetas, fechas dd/mm/aaaa, montos $1,070.50 y el total
  en letras («… Dólares con 50/100»).
* Precio unitario e importe con el mismo criterio de ITBMS, y la columna lo dice.
* Cliente con dirección, teléfono y «Cédula» o «RUC» (con DV), igual en la
  cotización que en la factura.
* Una factura pagada dice cuándo, con qué y que el saldo es $0.00 (sin sellos
  de imitación); una parcial, lo pagado y lo que queda.
* Enlaces al sitio público, nunca a localhost.
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
