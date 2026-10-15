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
* Cabecera Cliente | Entrega | Datos: identificación, teléfono, correo, dirección de
  entrega si es otra, fechas, pedido, vendedora, condiciones y medio de pago.
* El código del producto en su columna; flete, envío y servicios en su propio bloque
  (producto «Flete / envío a domicilio», sin precio: se cotiza en cada venta).
* Abonos con fecha y medio, pagado y por pagar debajo del total; descuento aplicado.
* Garantía, cambios y términos: textos cortos que la dueña escribe en la empresa.
* Hoja carta con la placa, la banda y un pie de dos líneas que no se corta.
* «Imprimir documentos»: botón extra en la factura y en el pedido (y «Imprimir paquete» en sus listas) que junta en
  un solo PDF la factura del cliente, la copia de la empresa y la nota de entrega; «Imprimir» abre el cuadro de
  impresión sin guardar archivos y «Descargar» lo guarda. Al completar un pago, el asistente lo ofrece (se apaga
  en la empresa). Todo lo que se imprimía antes sigue igual.
* Facturación › Tablero: tarjetas «Facturas de clientes» y «Facturas de proveedores» con sus conteos.
* Código QR de uso interno (/dcasa/doc/…): el pedido de compra lo lleva siempre; la factura, la nota de crédito, la
  cotización y la nota de entrega solo si la empresa enciende «Mostrar el código QR…» (apagado, salen exactamente
  como siempre). El equipo lo escanea y se abre ese documento en el sistema, si tiene permiso para verlo.
* «Mostrar el código público de los productos…» (apagado de fábrica): la columna «Código» de la factura, la cotización
  y la nota de entrega muestra DC-K7M4PX en lugar de la referencia del proveedor.
""",
    'version': '19.0.2.3.0',
    'category': 'Accounting/Accounting',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'account', 'sale', 'stock', 'sale_stock', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/report_layout.xml',
        'views/report_invoice.xml',
        'views/report_qr.xml',
        'views/report_compra.xml',
        'views/report_entrega.xml',
        'views/res_company_views.xml',
        'views/paquete_views.xml',
        'data/report_layout_data.xml',
        'data/paperformat_data.xml',
        'data/product_data.xml',
        'data/textos_data.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'dcasa_invoice/static/src/scss/report_dcasa.scss',
        ],
        'web.assets_backend': [
            'dcasa_invoice/static/src/scss/panel_facturas.scss',
            'dcasa_invoice/static/src/js/paquete_pdf.js',
            'dcasa_invoice/static/src/js/panel_facturas.js',
            'dcasa_invoice/static/src/xml/panel_facturas.xml',
        ],
    },
    'post_init_hook': '_dcasa_invoice_post_init',
    'installable': True,
}
