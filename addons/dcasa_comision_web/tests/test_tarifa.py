"""La tarifa fija por mantener la plataforma: se anota el primer día de cada periodo, repartida, sin repetirse.

Cifras de PRUEBA (12.34 no es la de nadie)."""
from datetime import date

from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .test_comision import ComisionReloj


@tagged('post_install', '-at_install')
class TestTarifa(ComisionReloj):

    def tarifa(self, hasta):
        return self.env['dcasa.web.movimiento']._cron_tarifa(hoy=hasta)

    def filas(self):
        return self.libro(tipo='tarifa')

    def test_sin_tarifa_no_se_anota_nada(self):
        self.version(10.0)
        self.assertEqual(self.tarifa(date(2031, 1, 1)), 0)
        self.assertFalse(self.filas())

    def test_mensual_se_anota_el_primer_dia_del_mes_y_se_reparte_sin_perder_un_centavo(self):
        self.version(0.0, tarifa=12.34, reparto=[(self.ana, 60.0), (self.beto, 40.0)])
        self.assertEqual(self.tarifa(date(2030, 3, 31)), 0, 'empezó a regir el 4: marzo ya arrancó sin ella')
        self.assertEqual(self.tarifa(date(2030, 4, 1)), 2)
        self.assertEqual({(f.empleado_id, f.centavos) for f in self.filas()},
                         {(self.ana, 741), (self.beto, 493)}, '12.34 = 741 + 493 (el centavo sobrante, a la primera)')
        self.assertEqual(self.filas().mapped('concepto'), ['tarifa', 'tarifa'])
        self.assertEqual(set(self.filas().mapped('periodo_inicio')), {date(2030, 4, 1)})

    def test_es_idempotente_y_cada_periodo_se_anota_una_vez(self):
        self.version(0.0, tarifa=12.34)
        self.tarifa(date(2030, 4, 1))
        self.assertEqual(self.tarifa(date(2030, 4, 1)), 0)
        self.assertEqual(self.tarifa(date(2030, 4, 20)), 0)
        self.assertEqual(self.tarifa(date(2030, 5, 1)), 2)
        self.assertEqual(len(self.filas()), 4)

    def test_si_el_proceso_se_atrasa_se_anotan_los_periodos_que_faltan(self):
        self.version(0.0, tarifa=12.34)
        self.assertEqual(self.tarifa(date(2030, 7, 20)), 8, 'abril, mayo, junio y julio × 2 personas')

    def test_quincenal_y_semanal(self):
        self.version(0.0, tarifa=1.0, tarifa_periodo='quincenal')
        self.assertEqual(self.tarifa(date(2030, 4, 16)), 6, '16/03, 01/04 y 16/04 × 2 personas')
        self.avanzar('2030-04-17 15:00:00')
        self.version(0.0, tarifa=1.0, tarifa_periodo='semanal')
        self.assertEqual(self.tarifa(date(2030, 4, 29)), 2 * 1 + 2 * 1, 'los lunes 22 y 29 de abril')
        self.assertEqual(set(self.filas().filtered(lambda f: f.periodo_inicio >= date(2030, 4, 17)).mapped(
            'periodo_inicio')), {date(2030, 4, 22), date(2030, 4, 29)})

    def test_un_cambio_de_tarifa_rige_hacia_adelante(self):
        self.version(0.0, tarifa=12.34)
        self.tarifa(date(2030, 4, 1))
        self.avanzar('2030-04-10 15:00:00')
        self.version(0.0, tarifa=5.0, reparto=[(self.ana, 100.0)])
        self.tarifa(date(2030, 5, 1))
        abril = self.filas().filtered(lambda f: f.periodo_inicio == date(2030, 4, 1))
        mayo = self.filas().filtered(lambda f: f.periodo_inicio == date(2030, 5, 1))
        self.assertEqual(sum(abril.mapped('centavos')), 1234, 'abril se anotó con la tarifa de entonces')
        self.assertEqual((len(mayo), sum(mayo.mapped('centavos'))), (1, 500))

    def test_una_pausa_deja_de_anotar_la_tarifa(self):
        self.version(0.0, tarifa=12.34)
        self.tarifa(date(2030, 4, 1))
        self.avanzar('2030-04-10 15:00:00')
        self.version(0.0, reparto=[])
        self.assertEqual(self.tarifa(date(2030, 6, 1)), 0)
        self.assertEqual(len(self.filas()), 2)

    def test_la_misma_tarifa_de_un_periodo_no_entra_dos_veces_ni_a_la_fuerza(self):
        self.version(0.0, tarifa=12.34)
        self.tarifa(date(2030, 4, 1))
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['dcasa.web.movimiento']._asentar(
                self.ana, 'tarifa', 100, self.company, periodo_inicio=date(2030, 4, 1))

    def test_la_tarifa_y_el_porcentaje_son_dos_conceptos_aparte(self):
        self.version(10.0, tarifa=12.34)
        self.venta_web()
        self.tarifa(date(2030, 4, 1))
        saldos = self.env['dcasa.web.movimiento']._saldos(self.ana)
        self.assertEqual((saldos[(self.ana.id, 'comision')], saldos[(self.ana.id, 'tarifa')]), (6000, 741))

    def test_el_proceso_de_cada_noche_anota_la_tarifa_y_barre(self):
        self.version(10.0, tarifa=12.34)
        self.venta_web()
        self.avanzar('2030-04-01 08:30:00')
        self.env['dcasa.web.venta']._cron_barrido()
        self.assertEqual(len(self.filas()), 2)


