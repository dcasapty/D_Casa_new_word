{
    'name': "D'CASA Panamá — Condiciones de abono",
    'summary': "La hoja «Condiciones de abono» en dos copias (cliente y empresa) con la marca de las facturas",
    'description': """
La hoja que la tienda entrega con el abono, impresa desde el sistema con la misma placa, banda y pie de las facturas
de D'CASA (dcasa_invoice):

* Dos páginas por factura: **COPIA CLIENTE** y **COPIA EMPRESA**. Cada una con el cliente (y su cédula o RUC si la
  ficha la tiene), el número de factura, la fecha de inicio del abono y la de vencimiento, los muebles con su código
  público (DC-…) y su descripción (la copia de la empresa, además, con la referencia del proveedor), el total, lo
  abonado y el saldo, las condiciones numeradas y las rayas para la firma y la cédula del cliente.
* Cada copia cabe en UNA hoja carta (sin «Página 1 / 2» en el pie: cada una se entrega sola). Con muchos muebles solo
  se achica la tabla de los muebles, lo justo; en una factura enorme la lista se corta y la hoja dice cuántos muebles
  más hay (están todos en la factura). Las condiciones, los totales y las firmas nunca se achican.
* Las cifras salen de ``account.move._dcasa_estado_abono`` (la misma fuente del papel de ABONO y de «Mi cuenta»).
* Las condiciones se escriben en Ajustes › Empresas › pestaña «Documentos D'CASA» (una por renglón; vacías, la hoja no
  se imprime; si el texto es tan largo que ya no caben ni cinco muebles sin achicar, sale un aviso). El texto inicial es
  la hoja que la tienda ya entrega, puesto una sola vez sin pisar lo que se cambie.
* Se imprime desde el menú «Imprimir» de una factura de cliente publicada con al menos un abono, o desde el cuadro
  «Imprimir documentos» (casilla «Condiciones de abono (2 copias)», marcada en el primer abono), justo después de la
  factura del cliente.
* Solo imprime: no cambia la factura, sus pagos, sus impuestos ni sus asientos, y no calcula ni cobra penalidades.
* **Abonos por vencer** (D3, Facturación › Clientes): los abonos que vencen en los próximos días (5 de fábrica) o que
  ya vencieron, con lo que falta y un botón para escribirle al cliente por WhatsApp desde el teléfono. El vencimiento
  se guarda en la factura (``dcasa_abono_vence``) y se recalcula con cada pago y cada noche.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_invoice'],
    'data': [
        'views/report_condiciones.xml',
        'views/res_company_views.xml',
        'views/paquete_views.xml',
        'data/condiciones_data.xml',
        'views/abonos_por_vencer_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'dcasa_abonos/static/src/scss/condiciones.scss',
        ],
    },
    'installable': True,
}
