{
    'name': "D'CASA Panamá — Nómina",
    'summary': "Planilla quincenal, décimo tercer mes, vacaciones, prima, liquidación y reembolsos en nómina",
    'description': """
La nómina de D'CASA, hecha para Panamá sobre los empleados de Odoo (módulo ``hr``):

* Fichas de colaboradores: salario mensual (con su historial), fecha de ingreso, cédula, seguro social, cuenta
  bancaria y forma de pago.
* Tasas y reglas CON VIGENCIA que VALIDA EL CONTADOR (seguro social, seguro educativo, riesgo profesional, tramos
  del ISR): ninguna cifra de la ley vive en el código; una planilla no se confirma con tasas sin validar.
* Planilla quincenal con seguro social, seguro educativo e ISR (proyección anual), horas extras y descuentos a
  mano, asiento contable automático, pago por colaborador y comprobante de pago en PDF.
* Décimo tercer mes en sus tres partidas (con su asiento y, si el contador lo decide, provisión mensual).
* Vacaciones (saldo ganado, tomado y su valor) y prima de antigüedad acumulada; cálculo de liquidación para el
  contador.
* Reembolsos en nómina: el colaborador registra el gasto con la foto del recibo, la administración lo aprueba y
  la siguiente planilla se lo suma.
* Bono por meta de ventas: quien está en el departamento de Ventas gana el porcentaje de lo que cobró en el mes si
  llega a la meta; entra solo en la primera planilla del mes siguiente y cada vendedora ve su avance en el Inicio.
""",
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_contabilidad', 'hr', 'account', 'mail'],
    'data': [
        'security/nomina_security.xml',
        'security/ir.model.access.csv',
        'data/nomina_data.xml',
        'data/meta_ventas_data.xml',
        'report/nomina_reportes.xml',
        'views/parametros_views.xml',
        'views/config_views.xml',
        'views/planilla_views.xml',
        'views/reembolso_views.xml',
        'views/vacacion_views.xml',
        'views/liquidacion_views.xml',
        'views/hr_employee_views.xml',
        'views/meta_ventas_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
}
