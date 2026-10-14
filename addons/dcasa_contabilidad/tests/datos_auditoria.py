"""Datos realistas para auditar los reportes contables (ayuda de pruebas, no es un test).

Arma, para un año ``anio`` (y el anterior), lo que una mueblería vive de verdad: facturas pagadas, parcialmente
pagadas, vencidas, por vencer, en borrador y canceladas; notas de crédito de cliente y de proveedor; cobros por
banco, por caja y por Yappy (unos conciliados y otros esperando su movimiento del banco); gastos con y sin ITBMS;
un aporte de capital, un mobiliario con su depreciación y un préstamo; y ventas con canal analítico repartido.

Todas las fechas salen de ``anio`` para que una prueba pueda correr en un año que ninguna otra tiene (los demás
tests usan 2030). Los borradores, los cancelados y lo fechado después de ``HOY`` existen a propósito: los
reportes NO deben contarlos (o solo a partir de su fecha).
"""
from odoo import Command

# «Hoy» de la mueblería en los datos: el 14 de octubre del año.
MES_HOY, DIA_HOY = 10, 14


def f(anio, mes, dia):
    return f'{anio:04d}-{mes:02d}-{dia:02d}'


class Auditoria:
    """Crea los datos en ``env`` y deja los registros importantes como atributos."""

    def __init__(self, env, anio=2031, empresa=None):
        self.env = env
        self.anio = anio
        self.empresa = empresa or env.ref('base.main_company')
        self.hoy = f(anio, MES_HOY, DIA_HOY)
        self.mov = env['account.move']
        self.puestos = []
        self._preparar()
        self._anio_anterior()
        self._anio_en_curso()

    # ------------------------------------------------------------------
    # Ayudas
    # ------------------------------------------------------------------

    def _preparar(self):
        env, empresa = self.env, self.empresa
        Cuenta, Socio = env['account.account'], env['res.partner']
        self.venta = empresa.account_sale_tax_id
        self.compra = env['account.tax'].search([
            ('company_id', '=', empresa.id), ('type_tax_use', '=', 'purchase'), ('amount', '=', 7),
            ('price_include', '=', False)], limit=1)
        self.exento = env['account.tax'].create({
            'name': 'ITBMS 0% exento (auditoría)', 'amount': 0, 'type_tax_use': 'sale', 'company_id': empresa.id})
        self.banco = env['account.journal'].search([('type', '=', 'bank'), ('company_id', '=', empresa.id)], limit=1)
        self.efectivo = env['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', empresa.id)], limit=1)
        self.diario_general = env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', empresa.id)], limit=1)
        self.tienda = env.ref('dcasa_contabilidad.cuenta_tienda_fisica')
        self.web = env.ref('dcasa_contabilidad.cuenta_tienda_linea')
        self.c1, self.c2, self.c3, self.c4, self.c5, self.c6 = (
            Socio.create({'name': f'Cliente auditoría {i}'}) for i in range(1, 7))
        self.v1, self.v2, self.v3 = (Socio.create({'name': f'Proveedor auditoría {i}'}) for i in range(1, 4))
        self.capital = Cuenta.search([('account_type', '=', 'equity'), ('company_ids', 'in', empresa.ids)], limit=1)
        self.mobiliario = Cuenta.create({'name': 'Mobiliario (auditoría)', 'code': '9A0001', 'account_type': 'asset_fixed'})
        self.depreciacion = Cuenta.create({'name': 'Depreciación (auditoría)', 'code': '9A0002',
                                           'account_type': 'expense_depreciation'})
        self.prestamo = Cuenta.create({'name': 'Préstamo corto plazo (auditoría)', 'code': '9A0003',
                                       'account_type': 'liability_current'})
        self.prestamo_largo = Cuenta.create({'name': 'Préstamo largo plazo (auditoría)', 'code': '9A0004',
                                             'account_type': 'liability_non_current'})
        self.costo = Cuenta.create({'name': 'Costo de ventas (auditoría)', 'code': '9A0005',
                                    'account_type': 'expense_direct_cost'})
        self.gasto_otro = Cuenta.create({'name': 'Otros gastos (auditoría)', 'code': '9A0006',
                                         'account_type': 'expense_other' if 'expense_other' in dict(
                                             Cuenta._fields['account_type'].selection) else 'expense'})
        self.cuenta_banco = self.banco.default_account_id
        self.cuenta_caja = self.efectivo.default_account_id

    def asiento(self, fecha, lineas, publicar=True, diario=None):
        """Asiento manual: ``[(cuenta, debe, haber)]`` o ``[(cuenta, debe, haber, tercero, analitica)]``."""
        comandos = []
        for linea in lineas:
            cuenta, debe, haber, *resto = linea
            tercero = resto[0] if resto else False
            analitica = resto[1] if len(resto) > 1 else False
            valores = {'account_id': cuenta.id, 'debit': debe, 'credit': haber, 'name': 'auditoría',
                       'partner_id': tercero.id if tercero else False}
            if analitica:
                valores['analytic_distribution'] = analitica
            comandos.append(Command.create(valores))
        asiento = self.mov.create({'move_type': 'entry', 'date': fecha, 'journal_id': (diario or self.diario_general).id,
                                   'line_ids': comandos})
        if publicar:
            asiento.action_post()
        return asiento

    def factura(self, cliente, monto, fecha, vence=None, impuesto=None, analitica=None, tipo='out_invoice',
                publicar=True, producto='Mueble', cuenta=None):
        compra = tipo in ('in_invoice', 'in_refund')
        impuesto = (self.compra if compra else self.venta) if impuesto is None else impuesto
        linea = {'name': producto, 'quantity': 1, 'price_unit': monto,
                 'tax_ids': [Command.set(impuesto.ids if impuesto else [])]}
        if analitica:
            linea['analytic_distribution'] = analitica
        if cuenta:
            linea['account_id'] = cuenta.id
        asiento = self.mov.create({
            'move_type': tipo, 'partner_id': cliente.id, 'invoice_date': fecha, 'date': fecha,
            'invoice_date_due': vence or fecha, 'invoice_line_ids': [Command.create(linea)]})
        if publicar:
            asiento.action_post()
        return asiento

    def movimiento_banco(self, monto, fecha, concepto, diario=None, tercero=None):
        return self.env['account.bank.statement.line'].create({
            'journal_id': (diario or self.banco).id, 'date': fecha, 'amount': monto, 'payment_ref': concepto,
            'partner_id': tercero.id if tercero else False})

    def cobrar_con_extracto(self, factura, fecha, monto=None, diario=None):
        """El banco (o la caja) recibe el dinero y se cruza de una vez con la factura (sin pasar por «Recibos pendientes»)."""
        compra = factura.move_type in ('in_invoice', 'in_refund')
        total = monto or factura.amount_residual
        linea = self.movimiento_banco(-total if compra else total, fecha, f'PAGO {factura.name}', diario)
        apunte = factura.line_ids.filtered(
            lambda ln: ln.account_id.account_type in ('asset_receivable', 'liability_payable') and not ln.reconciled)
        linea.dcasa_conciliar(apunte.ids)
        return linea

    def pago_registrado(self, factura, fecha, monto=None, diario=None):
        """«Registrar pago» en la factura: el dinero queda en «Recibos/Pagos pendientes» hasta que el banco lo confirme."""
        registro = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'payment_date': fecha, 'journal_id': (diario or self.banco).id,
                **({'amount': monto} if monto else {})})
        return registro._create_payments()

    # ------------------------------------------------------------------
    # Año anterior
    # ------------------------------------------------------------------

    def _anio_anterior(self):
        y = self.anio - 1
        self.aporte = self.asiento(f(y, 1, 5), [(self.cuenta_banco, 20000, 0), (self.capital, 0, 20000)])
        self.p1 = self.factura(self.c1, 1000, f(y, 11, 10), vence=f(y, 12, 10))
        self.cobrar_con_extracto(self.p1, f(y, 12, 20))
        self.p2 = self.factura(self.v1, 400, f(y, 11, 15), tipo='in_invoice')
        self.cobrar_con_extracto(self.p2, f(y, 12, 1))
        self.p3 = self.factura(self.c2, 500, f(y, 12, 15), vence=f(y, 12, 30))        # nunca se cobró

    # ------------------------------------------------------------------
    # Año en curso
    # ------------------------------------------------------------------

    def _anio_en_curso(self):
        y, Y = self.anio, self.anio
        self.e1 = self.factura(self.c1, 800, f(y, 1, 10), vence=f(y, 2, 9))
        self.x1 = self.cobrar_con_extracto(self.e1, f(y, 2, 20))
        self.e2 = self.factura(self.v1, 300, f(y, 3, 5), vence=f(y, 4, 4), tipo='in_invoice')   # gasto con ITBMS
        self.cobrar_con_extracto(self.e2, f(y, 4, 1), monto=150)                                 # pago parcial
        self.compra_mobiliario = self.asiento(f(y, 6, 1), [(self.mobiliario, 3000, 0), (self.cuenta_banco, 0, 3000)])
        self.deprec = self.asiento(f(y, 6, 30), [(self.depreciacion, 50, 0), (self.mobiliario, 0, 50)])
        self.prestamo_corto = self.asiento(f(y, 7, 1), [(self.cuenta_banco, 5000, 0), (self.prestamo, 0, 5000)])
        self.prestamo_largo_plazo = self.asiento(f(y, 7, 2), [(self.cuenta_banco, 2000, 0),
                                                              (self.prestamo_largo, 0, 2000)])
        self.e3 = self.factura(self.c3, 1200, f(y, 8, 20), vence=f(y, 9, 19))                    # vencida
        self.e4 = self.factura(self.c1, 600, f(y, 9, 3), vence=f(y, 10, 3))                      # vencida, abono en caja
        self.abono_caja = self.pago_registrado(self.e4, f(y, 10, 6), monto=200, diario=self.efectivo)  # sin conciliar
        self.nc3 = self.factura(self.c3, 100, f(y, 9, 10), tipo='out_refund')                    # nota de crédito (sin aplicar)
        self.e5 = self.factura(self.v2, 500, f(y, 9, 15), vence=f(y, 10, 15), tipo='in_invoice')  # por vencer
        self.nc_prov = self.factura(self.v1, 50, f(y, 9, 20), tipo='in_refund')                  # nota de crédito de proveedor
        self.e6 = self.factura(self.c2, 950, f(y, 10, 1), vence=f(y, 10, 31),
                               analitica={str(self.tienda.id): 60, str(self.web.id): 40})        # canal repartido
        self.pago_conciliado = self.pago_registrado(self.e6, f(y, 10, 8), diario=self.banco)
        self.extracto_pago = self.movimiento_banco(self.e6.amount_total, f(y, 10, 8), 'DEPOSITO e6', tercero=self.c2)
        self.env['dcasa.conciliacion'].conciliar(
            self.extracto_pago.id, apunte_ids=self._apunte_pago(self.pago_conciliado).ids)
        self.e7 = self.factura(self.c4, 300, f(y, 10, 5), vence=f(y, 10, 20), impuesto=self.exento,
                               analitica={str(self.tienda.id): 100})
        self.e8 = self.factura(self.v3, 200, f(y, 10, 7), tipo='in_invoice', impuesto=self.env['account.tax'])  # sin ITBMS
        self.e9 = self.factura(self.c5, 400, f(y, 10, 9), vence=f(y, 10, 9), analitica={str(self.web.id): 100})
        self.cobrar_con_extracto(self.e9, f(y, 10, 9), diario=self.efectivo)
        self.deposito_suelto = self.movimiento_banco(250, f(y, 10, 12), 'DEPOSITO SIN IDENTIFICAR')
        self.hoy_venta = self.factura(self.c6, 150, f(y, 10, 14), vence=f(y, 10, 14))
        self.hoy_compra = self.factura(self.v1, 80, f(y, 10, 14), tipo='in_invoice')
        self.gasto_manual = self.asiento(f(y, 10, 13), [(self._gasto(), 120, 0, self.v3, {str(self.tienda.id): 100}),
                                                         (self.cuenta_caja, 0, 120)])
        # Lo que NO debe contar (o solo desde su fecha):
        self.borrador = self.factura(self.c1, 700, f(y, 10, 10), publicar=False)
        self.borrador_prov = self.factura(self.v1, 90, f(y, 10, 11), tipo='in_invoice', publicar=False)
        self.cancelada = self.factura(self.c1, 600, f(y, 10, 11))
        self.cancelada.button_draft()
        self.cancelada.button_cancel()
        self.futuro = self.asiento(f(y, 10, 20), [(self._gasto(), 100, 0, self.v2), (self._pagar(), 0, 100, self.v2)])
        self.costo_ventas = self.asiento(f(y, 10, 9), [(self.costo, 150, 0), (self.cuenta_caja, 0, 150)])
        self.otro_gasto = self.asiento(f(y, 10, 12), [(self.gasto_otro, 30, 0), (self.cuenta_banco, 0, 30)])

    def _apunte_pago(self, pagos):
        return pagos.move_id.line_ids.filtered(lambda ln: ln.account_id == pagos.outstanding_account_id)

    def _gasto(self):
        return self.env['account.account'].search([('account_type', '=', 'expense'),
                                                   ('company_ids', 'in', self.empresa.ids)], limit=1)

    def _pagar(self):
        return self.env['account.account'].search([('account_type', '=', 'liability_payable'),
                                                   ('company_ids', 'in', self.empresa.ids)], limit=1)
