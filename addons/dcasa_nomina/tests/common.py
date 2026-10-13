"""Datos comunes de las pruebas de nómina: cuentas de prueba, tasas validadas (cifras redondas de PRUEBA, no las de la
ley) y dos colaboradores con salario de 1,200 y 1,200."""
from contextlib import contextmanager
from datetime import date

from odoo.tests import TransactionCase, new_test_user

# Tasas de prueba: distintas entre sí para que un cruce de campos se note.
TASAS = {
    'css_trabajador': 9.75, 'css_patronal': 13.25, 'se_trabajador': 1.25, 'se_patronal': 1.5,
    'riesgo_profesional': 0.98,
    'css_trabajador_decimo': 7.25, 'css_patronal_decimo': 10.75, 'se_trabajador_decimo': 0.0,
    'se_patronal_decimo': 0.0, 'riesgo_profesional_decimo': 0.0, 'decimo_listo': True,
}
TRAMOS = [(0, 11000, 0), (11000, 50000, 15), (50000, 0, 25)]
DESDE, HASTA = date(2030, 3, 1), date(2030, 3, 15)


class NominaCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        Cuenta = cls.env['account.account']

        def cuenta(codigo, nombre, tipo, reconciliable=False):
            return Cuenta.create({'name': nombre, 'code': codigo, 'account_type': tipo, 'reconcile': reconciliable})

        cls.c_sueldos = cuenta('9N0001', 'Sueldos prueba', 'expense')
        cls.c_cargas = cuenta('9N0002', 'Cargas sociales prueba', 'expense')
        cls.c_por_pagar = cuenta('9N0003', 'Sueldos por pagar prueba', 'liability_current', True)
        cls.c_css = cuenta('9N0004', 'Seguro social por pagar prueba', 'liability_current')
        cls.c_se = cuenta('9N0005', 'Seguro educativo por pagar prueba', 'liability_current')
        cls.c_rp = cuenta('9N0006', 'Riesgo profesional por pagar prueba', 'liability_current')
        cls.c_isr = cuenta('9N0007', 'ISR por pagar prueba', 'liability_current')
        cls.c_otros = cuenta('9N0008', 'Otros descuentos prueba', 'asset_current')
        cls.c_decimo = cuenta('9N0009', 'Provision decimo prueba', 'liability_current')
        cls.c_reembolso = cuenta('9N0010', 'Gasto reembolsos prueba', 'expense')
        cls.config = cls.env['dcasa.nomina.config']._de(cls.company)
        cls.config.write({
            'cuenta_gasto_sueldos_id': cls.c_sueldos.id, 'cuenta_gasto_cargas_id': cls.c_cargas.id,
            'cuenta_sueldos_pagar_id': cls.c_por_pagar.id, 'cuenta_css_pagar_id': cls.c_css.id,
            'cuenta_se_pagar_id': cls.c_se.id, 'cuenta_rp_pagar_id': cls.c_rp.id, 'cuenta_isr_pagar_id': cls.c_isr.id,
            'cuenta_otros_descuentos_id': cls.c_otros.id, 'cuenta_decimo_id': cls.c_decimo.id,
            'cuenta_reembolsos_id': cls.c_reembolso.id, 'provisionar_decimo': False})
        cls.banco = cls.env['account.journal'].search([('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
                                                      limit=1)

        cls.vigencia = cls._vigencia('2030-01-01', validar=True)

        Empleado = cls.env['hr.employee']
        cls.ana = cls._empleado('Ana Prueba Nómina', 1200, '2029-01-01')
        cls.beto = cls._empleado('Beto Prueba Nómina', 1200, '2030-03-09')
        # Nadie más (p. ej. el empleado del administrador) entra en las cuentas de estas pruebas.
        Empleado.search([('id', 'not in', (cls.ana + cls.beto).ids)]).write({'dcasa_en_planilla': False})

        cls.usuario = new_test_user(cls.env, login='nomina_prueba', name='Nómina Prueba',
                                    groups='base.group_user,dcasa_nomina.group_nomina')
        cls.entorno = cls.env(user=cls.usuario)

    @contextmanager
    def assertRaisesTexto(self, excepcion, patron):
        """Como ``assertRaisesRegex`` pero con el punto de guardado de ``assertRaises`` de Odoo: lo que el método
        alcanzó a escribir antes de fallar no se queda en la base de la prueba."""
        with self.assertRaises(excepcion) as cm:
            yield
        self.assertRegex(str(cm.exception), patron)

    @classmethod
    def _vigencia(cls, desde, validar=False, **cambios):
        vigencia = cls.env['dcasa.nomina.parametros'].create({
            'company_id': cls.company.id, 'fecha_desde': desde, **TASAS, **cambios,
            'tramo_ids': [(0, 0, {'desde': d, 'hasta': h, 'tasa': t}) for d, h, t in TRAMOS]})
        if validar:
            vigencia.action_validar()
        return vigencia

    @classmethod
    def _empleado(cls, nombre, salario, ingreso, **extra):
        return cls.env['hr.employee'].create({
            'name': nombre, 'company_id': cls.company.id, 'wage': salario, 'contract_date_start': ingreso, **extra})

    def _planilla(self, desde=DESDE, hasta=HASTA, entorno=None, **extra):
        Planilla = (entorno or self.env)['dcasa.nomina.planilla']
        return Planilla.create({'tipo': 'quincenal', 'fecha_desde': desde, 'fecha_hasta': hasta,
                                'fecha_pago': hasta, **extra})

    def _linea(self, planilla, empleado):
        return planilla.linea_ids.filtered(lambda ln: ln.empleado_id == empleado)

    def _sumas(self, asiento):
        """{cuenta: (debe, haber)} del asiento."""
        sumas = {}
        for linea in asiento.line_ids:
            debe, haber = sumas.get(linea.account_id, (0.0, 0.0))
            sumas[linea.account_id] = (round(debe + linea.debit, 2), round(haber + linea.credit, 2))
        return sumas
