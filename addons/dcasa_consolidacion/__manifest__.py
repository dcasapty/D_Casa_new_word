{
    'name': "D'CASA Panamá — Consolidación",
    'summary': "Los estados financieros de varias empresas del grupo en uno solo, sin contar dos veces lo que "
               "se hacen entre ellas",
    'description': """
Consolidación de D'CASA
=======================

Suma las empresas del grupo (multiempresa ya viene incluido en Odoo Community) en un solo
estado de resultados, balance general o balance de comprobación:

* Una columna por empresa, una de **Eliminaciones** y una de **Consolidado**.
* Las cuentas se unen por código (las empresas de D'CASA usan el mismo plan ``l10n_pa``); si algún
  día los planes difieren, el **mapa de cuentas** dice a qué cuenta consolidada va cada una.
* Se eliminan las operaciones entre empresas del grupo: por cobrar contra por pagar, e ingresos contra
  gastos, cuando el tercero del apunte es la ficha de otra empresa del grupo.
* Si lo que una empresa dice que le deben no es lo que la otra dice que debe, lo avisa («Descuadre
  entre A y B de $X»): nunca lo esconde ni lo arregla solo.
* Todo sale de los asientos publicados; solo se guardan las líneas calculadas. Imprime en PDF.

No convierte monedas (todas las empresas deben usar la misma) ni hace ajustes manuales de
consolidación, utilidades no realizadas en inventario ni participaciones minoritarias:
eso lo decide el contador.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_contabilidad'],
    'data': [
        'security/ir.model.access.csv',
        'security/consolidacion_security.xml',
        'report/consolidacion_pdf.xml',
        'views/consolidacion_views.xml',
        'views/mapa_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
