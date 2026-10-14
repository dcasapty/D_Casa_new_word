"""Campos calculados de Odoo que saltan las reglas de registro y dejan ver cifras contables de un jefe.

Las reglas de ``security/dcasa_reglas_contables.xml`` cierran los datos (asientos, pagos, bancos). Pero estos campos
los calcula Odoo con SQL directo (``bypass_access``), sin pasar por las reglas, y lo único que los frena es el grupo
del campo: Facturación (``account.group_account_invoice``), que la Vendedora y el Cajero tienen para poder cobrar.
Aquí se les pide contabilidad (lector, contador o gerente contable):

* ``res.partner.debit``: lo que la tienda le debe a cada proveedor.
* ``account.journal.kanban_dashboard`` y ``kanban_dashboard_graph``: facturas de proveedor por pagar, retrasadas,
  saldo del banco y de la caja (son las tarjetas del tablero de Facturación, que la vendedora no ve).

Ni los menús, ni las vistas, ni el código de D'CASA usan estos campos para quien vende. El que sí los necesita
(contabilidad, Gerencia, administrador) los conserva: ``account.group_account_readonly`` lo incluye el contador y
Gerencia, y ``account.group_account_manager`` va aparte porque sin ``dcasa_contabilidad`` no implica al lector.
"""
from odoo import fields, models

CONTABILIDAD = 'account.group_account_readonly,account.group_account_manager'


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    kanban_dashboard = fields.Text(groups=CONTABILIDAD)
    kanban_dashboard_graph = fields.Text(groups=CONTABILIDAD)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    debit = fields.Monetary(groups=CONTABILIDAD)
