"""Datos y ayudas comunes de las pruebas de la consolidación: dos empresas con el plan ``l10n_pa``."""
from collections import defaultdict

from odoo import Command
from odoo.tests import TransactionCase

# Periodo aislado: nada más en la base tiene movimientos en marzo de 2030.
DESDE, HASTA = '2030-03-01', '2030-03-31'


class ConsolidacionCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empresa_a = cls.env.ref('base.main_company')
        cls.empresa_b = cls._crear_empresa('Zona Libre Prueba SA')
        cls.grupo = cls.empresa_a | cls.empresa_b
        cls.motor = cls.env['dcasa.reporte.contable']
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente externo de prueba'})
        cls.proveedor = cls.env['res.partner'].create({'name': 'Proveedor externo de prueba'})
        cls._datos_base()

    @classmethod
    def _crear_empresa(cls, nombre, con_plan=True):
        usd = cls.env.ref('base.USD')
        empresa = cls.env['res.company'].create({'name': nombre, 'currency_id': usd.id})
        if con_plan:
            cls.env['account.chart.template'].try_loading('pa', empresa, install_demo=False)
            empresa.currency_id = usd  # el plan «pa» deja la moneda del país (PAB)
        return empresa

    @classmethod
    def cuenta(cls, empresa, tipo, indice=0):
        """La cuenta de ese tipo que tiene el código más bajo en la empresa (el plan es el mismo en las dos)."""
        cuentas = cls.env['account.account'].with_company(empresa).search(
            [('account_type', '=', tipo), ('company_ids', 'in', empresa.id)], order='code')
        return cuentas[indice]

    @classmethod
    def asiento(cls, empresa, fecha, lineas, publicar=True):
        """lineas: [(cuenta, debe, haber, tercero)]"""
        diario = cls.env['account.journal'].search([('company_id', '=', empresa.id), ('type', '=', 'general')], limit=1)
        asiento = cls.env['account.move'].with_company(empresa).create({
            'move_type': 'entry', 'company_id': empresa.id, 'journal_id': diario.id, 'date': fecha,
            'line_ids': [Command.create({'account_id': cuenta.id, 'debit': debe, 'credit': haber, 'name': 'Prueba',
                                         'partner_id': tercero.id if tercero else False})
                         for cuenta, debe, haber, tercero in lineas],
        })
        if publicar:
            asiento.action_post()
        return asiento

    @classmethod
    def _datos_base(cls):
        """Ventas, gastos, capital y resultados de años anteriores en cada empresa, todo con terceros EXTERNOS."""
        a, b = cls.empresa_a, cls.empresa_b
        cxc_a, ventas_a = cls.cuenta(a, 'asset_receivable'), cls.cuenta(a, 'income')
        cxp_a, gasto_a = cls.cuenta(a, 'liability_payable'), cls.cuenta(a, 'expense')
        activo_a = cls.cuenta(a, 'asset_current')
        cls.asiento(a, '2029-06-10', [(cxc_a, 200, 0, cls.cliente), (ventas_a, 0, 200, cls.cliente)])  # año anterior
        cls.asiento(a, '2030-01-20', [(cxc_a, 150, 0, cls.cliente), (ventas_a, 0, 150, cls.cliente)])  # antes
        cls.asiento(a, '2030-03-05', [(cxc_a, 1000, 0, cls.cliente), (ventas_a, 0, 1000, cls.cliente)])
        cls.asiento(a, '2030-03-10', [(gasto_a, 300, 0, cls.proveedor), (cxp_a, 0, 300, cls.proveedor)])
        cls.asiento(a, '2030-03-15', [(activo_a, 500, 0, cls.proveedor), (cxp_a, 0, 500, cls.proveedor)])
        cls.asiento(a, '2030-03-20', [(cxc_a, 777, 0, cls.cliente), (ventas_a, 0, 777, cls.cliente)], publicar=False)
        cxc_b, ventas_b = cls.cuenta(b, 'asset_receivable'), cls.cuenta(b, 'income')
        cxp_b, gasto_b = cls.cuenta(b, 'liability_payable'), cls.cuenta(b, 'expense')
        activo_b, capital_b = cls.cuenta(b, 'asset_current'), cls.cuenta(b, 'equity')
        cls.asiento(b, '2029-08-01', [(gasto_b, 50, 0, cls.proveedor), (cxp_b, 0, 50, cls.proveedor)])  # año anterior
        cls.asiento(b, '2030-02-10', [(cxc_b, 60, 0, cls.cliente), (ventas_b, 0, 60, cls.cliente)])
        cls.asiento(b, '2030-03-02', [(activo_b, 2000, 0, None), (capital_b, 0, 2000, None)])
        cls.asiento(b, '2030-03-08', [(cxc_b, 500, 0, cls.cliente), (ventas_b, 0, 500, cls.cliente)])
        cls.asiento(b, '2030-03-18', [(gasto_b, 120, 0, cls.proveedor), (cxp_b, 0, 120, cls.proveedor)])

    def venta_externa(self, empresa, monto, fecha, publicar=True):
        return self.asiento(empresa, fecha, [
            (self.cuenta(empresa, 'asset_receivable'), monto, 0, self.cliente),
            (self.cuenta(empresa, 'income'), 0, monto, self.cliente)], publicar=publicar)

    # ------------------------------------------------------------------
    # Operaciones entre empresas
    # ------------------------------------------------------------------

    def venta_entre_empresas(self, vendedora, compradora, cobrar, pagar=None, fecha='2030-03-15'):
        """``vendedora`` registra una venta a crédito a ``compradora`` por ``cobrar``; ``compradora`` registra el
        gasto y lo que debe por ``pagar`` (por omisión lo mismo). Con ``pagar`` distinto hay un descuadre."""
        pagar = cobrar if pagar is None else pagar
        self.asiento(vendedora, fecha, [
            (self.cuenta(vendedora, 'asset_receivable'), cobrar, 0, compradora.partner_id),
            (self.cuenta(vendedora, 'income'), 0, cobrar, compradora.partner_id)])
        self.asiento(compradora, fecha, [
            (self.cuenta(compradora, 'expense'), pagar, 0, vendedora.partner_id),
            (self.cuenta(compradora, 'liability_payable'), 0, pagar, vendedora.partner_id)])

    # ------------------------------------------------------------------
    # Consolidaciones y lecturas
    # ------------------------------------------------------------------

    def consolidacion(self, tipo='resultados', empresas=None, calcular=True, **valores):
        consolidacion = self.env['dcasa.consolidacion'].create({
            'name': f'Prueba {tipo}', 'tipo_reporte': tipo, 'fecha_desde': DESDE, 'fecha_hasta': HASTA,
            'company_ids': [Command.set((self.grupo if empresas is None else empresas).ids)], **valores})
        if calcular:
            consolidacion.action_calcular()
        return consolidacion

    @staticmethod
    def tabla(consolidacion, campo='importe'):
        """{(sección, código o nombre): {columna: importe}}; la columna es el nombre de la empresa,
        ``'eliminaciones'`` o ``'consolidado'``."""
        tabla = defaultdict(dict)
        for linea in consolidacion.linea_ids:
            columna = linea.columna if linea.tipo_columna == 'empresa' else linea.tipo_columna
            tabla[(linea.seccion, linea.codigo or linea.nombre)][columna] = linea[campo]
        return tabla

    def motor_de(self, empresa, reporte, **argumentos):
        """El reporte de ``dcasa_contabilidad`` para esa empresa sola."""
        return getattr(self.motor.with_context(allowed_company_ids=[empresa.id]), reporte)(**argumentos)
