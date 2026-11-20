"""Cuarta revisión adversarial, menor 4: valores raros en el tope, la tarifa, el porcentaje, el reparto y el monto de un
ajuste. Por RPC cualquiera manda ``nan``, ``inf``, un texto o un 1e30: antes acababan en ``ValueError``,
``OverflowError`` o ``InvalidOperation`` sin traducir, y un tope de 1e30 se guardaba y rompía todos los ajustes.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501
import math
from decimal import Decimal

from odoo.addons.dcasa_comision_web.models import calculo
from odoo.addons.dcasa_comision_web.tests.test_comision import ComisionReloj
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

RAROS = (float('nan'), float('inf'), float('-inf'), 'nan', 'inf', '-inf', 'abc', '1e400', 10 ** 400, [1], {'a': 1}, True)


@tagged('post_install', '-at_install')
class TestCifrasEnFuncionesPuras(TransactionCase):

    def test_numero_finito_acepta_numeros_y_textos_de_numeros_y_rechaza_lo_demas(self):
        for valor, esperado in ((5, 5.0), (2.5, 2.5), ('25.50', 25.5), (Decimal('3.1'), 3.1), (10 ** 30, 1e30), (None, 0.0),
                                (False, 0.0), ('', 0.0), (-4, -4.0)):
            with self.subTest(valor=valor):
                self.assertEqual(calculo.numero_finito(valor), esperado)
        for valor in RAROS + (Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity')):
            with self.subTest(valor=valor):
                self.assertIsNone(calculo.numero_finito(valor))

    def test_a_centavos_aguanta_cualquier_cifra_finita_y_rechaza_lo_que_no_es_numero(self):
        self.assertEqual(calculo.a_centavos(25.51), 2551)
        self.assertEqual(calculo.a_centavos(-0.01), -1)
        self.assertEqual(calculo.a_centavos(1e30), 10 ** 32)
        self.assertEqual(calculo.a_centavos(1e300), 10 ** 302)
        self.assertEqual(calculo.a_centavos(None), 0)
        for valor in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                calculo.a_centavos(valor)
        self.assertTrue(math.isfinite(1e30))


@tagged('post_install', '-at_install')
class TestValoresRarosDeLasReglas(ComisionReloj):

    def crear(self, **valores):
        return self.env['dcasa.web.reglas'].with_user(self.u_nomina).create({
            'company_id': self.company.id, 'porcentaje': 0.0, **valores})

    def rechaza_limpio(self, **valores):
        with self.assertRaises(UserError) as error, self.env.cr.savepoint():
            self.crear(**valores)
        mensaje = str(error.exception)
        self.assertNotIn('InvalidOperation', mensaje)
        self.assertNotIn('Traceback', mensaje)
        return mensaje

    def test_un_tope_una_tarifa_o_un_porcentaje_que_no_son_numeros_se_rechazan_con_un_mensaje_claro(self):
        for campo in ('tope_ajuste', 'tarifa_fija', 'porcentaje'):
            for valor in RAROS:
                with self.subTest(campo=campo, valor=valor):
                    self.assertTrue(self.rechaza_limpio(**{campo: valor}))
        self.assertFalse(self.env['dcasa.web.reglas'].search([]), 'no se guardó ninguna versión')

    def test_un_tope_o_una_tarifa_que_no_caben_en_el_libro_se_rechazan(self):
        for campo in ('tope_ajuste', 'tarifa_fija'):
            for valor in (1e30, 10 ** 30, 1e300, 21_474_836.48, '99999999999'):
                with self.subTest(campo=campo, valor=valor):
                    self.assertIn('demasiado grande', self.rechaza_limpio(**{campo: valor}))

    def test_el_mensaje_dice_cual_cifra_es(self):
        self.assertIn('Tope de un ajuste a mano', self.rechaza_limpio(tope_ajuste=float('nan')))
        self.assertIn('Tarifa fija', self.rechaza_limpio(tarifa_fija='inf'))
        self.assertIn('Porcentaje', self.rechaza_limpio(porcentaje=float('inf')))

    def test_un_porcentaje_fuera_de_0_a_100_se_rechaza_como_siempre(self):
        for valor in (-1.0, 100.01, 1e30):
            with self.subTest(valor=valor), self.assertRaisesRegex(UserError, 'va de 0 a 100'), self.env.cr.savepoint():
                self.crear(porcentaje=valor)

    def test_lo_mas_grande_que_cabe_en_el_libro_si_se_guarda(self):
        version = self.crear(tope_ajuste=21_474_836.47)
        self.assertEqual(version.tope_ajuste, 21_474_836.47)
        con_tarifa = self.version(0.0, tarifa=21_474_836.47)
        self.assertEqual(con_tarifa.tarifa_fija, 21_474_836.47)
        self.version(100.0)
        self.version(0.0, tope_ajuste=0.0)

    def test_un_reparto_con_un_porcentaje_que_no_es_numero_se_rechaza_con_un_mensaje_claro(self):
        from odoo import Command
        for valor in RAROS:
            with self.subTest(valor=valor), self.assertRaisesRegex(UserError, 'no es un número válido'), self.env.cr.savepoint():
                self.crear(porcentaje=10.0, reparto_ids=[Command.create({'empleado_id': self.ana.id, 'porcentaje': valor})])


@tagged('post_install', '-at_install')
class TestValoresRarosDeUnAjuste(ComisionReloj):

    def ajustar(self, monto, usuario=None):
        ajuste = self.env['dcasa.web.ajuste'].with_user(usuario or self.u_nomina).create({
            'empleado_id': self.ana.id, 'monto': monto, 'motivo': 'prueba de valores raros'})
        ajuste.action_anotar()

    def test_un_monto_raro_da_un_error_claro_en_vez_de_un_error_de_python(self):
        self.version(10.0)
        for monto in RAROS + (1e12, 1e300, 10 ** 30, 21_474_836.48, -21_474_836.48):
            with self.subTest(monto=monto):
                with self.assertRaises(UserError) as error, self.env.cr.savepoint():
                    self.ajustar(monto)
                self.assertRegex(str(error.exception), 'no es un número válido|demasiado grande')
        self.assertFalse(self.libro(tipo='ajuste'), 'ninguno se anotó')

    def test_un_monto_escrito_como_texto_con_un_numero_se_anota_normal(self):
        self.version(10.0)
        self.ajustar('25.50')
        self.assertEqual(self.libro(tipo='ajuste').mapped('centavos'), [2550])

    def test_el_monto_mas_grande_que_cabe_si_se_anota(self):
        self.version(10.0)
        self.ajustar(21_474_836.47)
        self.ajustar(-21_474_836.47)
        self.assertEqual(sorted(self.libro(tipo='ajuste').mapped('centavos')), [-2147483647, 2147483647])

    def test_un_tope_enorme_que_ya_estaba_guardado_no_rompe_los_ajustes(self):
        """Antes de cerrar la puerta se podía guardar un tope de 1e30 (``InvalidOperation`` en cada ajuste): si hay una
        así guardada, los ajustes siguen funcionando y el tope, que ya no frena nada, no estorba."""
        version = self.version(10.0)
        self.env.cr.execute('UPDATE dcasa_web_reglas SET tope_ajuste = 1e30 WHERE id = %s', [version.id])
        self.env.invalidate_all()
        self.assertEqual(self.env['dcasa.web.reglas']._vigente(self.company).tope_ajuste, 1e30)
        self.ajustar(5.0)
        self.ajustar(-5.0)
        self.assertEqual(sorted(self.libro(tipo='ajuste').mapped('centavos')), [-500, 500])
        with self.assertRaisesRegex(UserError, 'demasiado grande'), self.env.cr.savepoint():
            self.ajustar(21_474_836.48)

    def test_un_tope_que_no_es_numero_ya_guardado_tampoco_rompe_los_ajustes(self):
        version = self.version(10.0)
        self.env.cr.execute("UPDATE dcasa_web_reglas SET tope_ajuste = 'NaN' WHERE id = %s", [version.id])
        self.env.invalidate_all()
        self.ajustar(5.0)
        self.assertEqual(self.libro(tipo='ajuste').mapped('centavos'), [500])

    def test_el_tope_de_las_reglas_sigue_frenando_como_siempre(self):
        self.version(10.0, tope_ajuste=100.0)
        self.ajustar(100.0)
        self.ajustar(-100.0)
        for monto in (100.01, -100.01):
            with self.subTest(monto=monto), self.assertRaisesRegex(UserError, 'no puede pasar de 100.00'), self.env.cr.savepoint():
                self.ajustar(monto)
