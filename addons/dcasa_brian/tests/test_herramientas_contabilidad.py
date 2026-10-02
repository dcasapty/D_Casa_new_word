"""Herramientas contables nuevas de Brian: resumen, antigüedad de saldos, comparativos y cierre de mes."""
from datetime import date

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestHerramientasContabilidad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            return Usuarios.create({'name': login, 'login': login, 'group_ids': [
                Command.set([cls.env.ref(g).id for g in ('base.group_user', *grupos)])]})

        cls.vendedor = usuario('brian_c_vendedor', ('sales_team.group_sale_salesman',))
        cls.contador = usuario('brian_c_contador', ('account.group_account_user',))
        cls.gerente = usuario('brian_c_gerente', ('account.group_account_manager',))
        cls.cliente = cls.env['res.partner'].create({'name': 'Brianzeta Deudor', 'phone': '6123-4599'})
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        cls.factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'invoice_date': '2030-03-05',
            'invoice_date_due': '2030-03-05',
            'date': '2030-03-05',
            'invoice_line_ids': [Command.create({'name': 'Sofá', 'quantity': 1, 'price_unit': 100.0,
                                                 'tax_ids': [Command.set(impuesto.ids)]})]})
        cls.factura.action_post()

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def test_vendedor_no_las_ve(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedor).catalogo()}
        for nombre in ('resumen_contable', 'antiguedad_saldos', 'comparar_periodos', 'cerrar_mes'):
            self.assertNotIn(nombre, nombres)
        # cerrar_mes es de la gerencia contable: el contador no la tiene.
        del_contador = {h['name'] for h in self.env['brian.herramientas'].with_user(self.contador).catalogo()}
        self.assertIn('resumen_contable', del_contador)
        self.assertNotIn('cerrar_mes', del_contador)

    def test_cuanto_gane_y_quien_me_debe(self):
        datos = self.ok(self.ejecutar(self.contador, 'resumen_contable', {'desde': '01/03/2030',
                                                                           'hasta': '31/03/2030'}))
        self.assertEqual(datos['ventas']['monto'], '$100.00')
        self.assertEqual(datos['utilidad']['periodo_anterior'], '$0.00')
        self.assertIn('ITBMS por pagar: $7.00', datos['itbms'])
        self.assertIn('Brianzeta Deudor', [d['cliente'] for d in datos['quien_debe_mas']])
        deuda = self.ok(self.ejecutar(self.contador, 'antiguedad_saldos', {'fecha': '30/04/2030'}))
        fila = next(f for f in deuda['detalle'] if f['tercero'] == 'Brianzeta Deudor')
        self.assertEqual(fila['total'], '$107.00')
        self.assertEqual(fila['vencido'], '$107.00')
        self.assertIn('31 a 60 días', fila['tramos'])
        self.assertTrue(self.ok(self.ejecutar(self.contador, 'antiguedad_saldos', {'tipo': 'por_pagar'})))

    def test_comparar_y_flujo(self):
        datos = self.ok(self.ejecutar(self.contador, 'comparar_periodos', {
            'reporte': 'estado_resultados', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertIn('Periodo anterior', datos['comparado_con'])
        ventas = datos['variaciones'][0]
        self.assertEqual((ventas['actual'], ventas['comparado'], ventas['variacion_pct']),
                         ('$100.00', '$0.00', 'sin base'))
        flujo = self.ok(self.ejecutar(self.contador, 'reporte_contable', {
            'reporte': 'flujo_efectivo', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertEqual(flujo['cuadra'], 'sí')
        respuesta = self.ejecutar(self.contador, 'comparar_periodos', {'reporte': 'itbms'})
        self.assertFalse(respuesta['ok'])

    def test_cerrar_mes_pide_confirmacion(self):
        fin = '2030-03-31'
        self.env['account.bank.statement.line'].search([('is_reconciled', '=', False), ('date', '<=', fin)]).unlink()
        self.env['account.move'].search([('state', '=', 'draft'), ('date', '<=', fin)]).unlink()
        respuesta = self.ejecutar(self.gerente, 'cerrar_mes', {'mes': '03/2030'})
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        self.assertFalse(self.env.company.fiscalyear_lock_date)  # nada pasa sin el clic
        datos = self.ok(self.env['brian.herramientas'].with_user(self.gerente).confirmar(respuesta['accion_id']))
        self.assertIn('Marzo 2030 cerrado', datos['mensaje'])
        self.assertEqual(self.env.company.fiscalyear_lock_date, date(2030, 3, 31))
        guia = self.ok(self.ejecutar(self.gerente, 'guia_cierre_mes', {'mes': '03/2030'}))
        self.assertEqual(guia['mes_cerrado'], 'sí')
        otra = self.env['brian.herramientas'].with_user(self.gerente).confirmar(
            self.ejecutar(self.gerente, 'cerrar_mes', {'mes': '03/2030'})['accion_id'])
        self.assertFalse(otra['ok'])
        self.assertIn('ya está cerrado', otra['error'])
