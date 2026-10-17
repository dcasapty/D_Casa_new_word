{
    'name': "D'CASA Panamá — Contactos sin duplicados",
    'summary': "Un celular, un correo, un RUC o cédula: una sola ficha. Lista de posibles duplicados y fusión",
    'description': """
Una persona, una ficha:

* No se guardan dos fichas con el mismo celular o teléfono, el mismo correo ni el mismo RUC o cédula. Sí pueden
  llamarse igual. Se compara sin importar mayúsculas, espacios, guiones ni el +507 (y un número de otro país no se
  confunde con uno de Panamá).
* Las direcciones de entrega de un mismo cliente, los usuarios, los empleados y las empresas propias no cuentan.
* Lo que ya estaba guardado no se toca: solo se revisan las fichas nuevas y los datos que se cambian.
* Socios › Posibles duplicados lista lo viejo para limpiarlo, con el botón de fusionar de Odoo.
* En el sitio y en el chat, quien compra o escribe de nuevo con el mismo celular o correo cae en su misma ficha.
* Celular y correo bien escritos y obligatorios: la vendedora no confirma una venta ni publica una factura si al
  cliente le falta alguno o están mal escritos («¿Quisiste decir ana@gmail.com?»). Si de verdad no tiene correo, se
  marca «Cliente no tiene correo electrónico» en su ficha o en la cotización (el celular sigue obligatorio).
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_socios', 'hr', 'mail', 'sale_management', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/duplicado_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
}
