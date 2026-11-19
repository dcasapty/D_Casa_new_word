"""Liquidaciones: periodos libres y solapados, nunca se paga dos veces, quien cobra no aprueba, lo aprobado no se
edita, nada se paga solo.

Cifras de PRUEBA."""
from datetime import date

from odoo import SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_comision import ComisionReloj


@tagged('post_install', '-at_install')
class TestLiquidacion(ComisionReloj):

    def setUp(self):
        super().setUp()
        self.version(10.0, tarifa=0.0, reparto=[(self.ana, 60.0), (self.beto, 40.0)])
        self.venta_marzo = self.venta_web(fecha='2030-03-04')             # 1,000 → 100: 60 + 40
        self.avanzar('2030-03-20 15:00:00')
        self.venta_web(fecha='2030-03-20')                                # otros 100: 60 + 40
        self.avanzar('2030-04-02 15:00:00')

    def liquidacion(self, desde='2030-03-01', hasta='2030-03-31', usuario=None, armar=True, **extra):
        liq = self.env['dcasa.web.liquidacion'].with_user(usuario or self.u_nomina).create({
            'fecha_desde': desde, 'fecha_hasta': hasta, **extra})
        if armar:
            liq.action_armar()
        return liq

    def totales(self, liq):
        return {(ln.empleado_id, ln.concepto): ln.centavos for ln in liq.sudo().linea_ids}

    # ------------------------------------------------------------------ armar

    def test_toma_lo_que_se_debe_hasta_la_fecha_y_no_lo_posterior(self):
        primera = self.liquidacion(hasta='2030-03-10')
        self.assertEqual(self.totales(primera), {(self.ana, 'comision'): 6000, (self.beto, 'comision'): 4000})
        todo = self.liquidacion(hasta='2030-03-31')
        self.assertEqual(self.totales(todo), {(self.ana, 'comision'): 12000, (self.beto, 'comision'): 8000})
        self.assertEqual(todo.total, 200.0)

    def test_periodos_libres_semana_quincena_mes_con_atajos(self):
        liq = self.env['dcasa.web.liquidacion'].new({'atajo': 'mes_pasado'})
        liq._onchange_atajo()
        self.assertEqual((liq.fecha_desde, liq.fecha_hasta), (date(2030, 3, 1), date(2030, 3, 31)))
        for atajo in ('este_mes', 'quincena_1', 'quincena_2_pasada', 'quincena_1_pasada', 'esta_semana',
                      'semana_pasada'):
            with self.subTest(atajo=atajo):
                liq.atajo = atajo
                liq._onchange_atajo()
                self.assertLessEqual(liq.fecha_desde, liq.fecha_hasta)

    def test_el_periodo_que_termina_antes_de_empezar_no_se_arma(self):
        with self.assertRaisesRegex(UserError, 'termina antes de empezar'):
            self.liquidacion(desde='2030-03-31', hasta='2030-03-01')

    def test_armar_otra_vez_reemplaza_los_renglones_en_vez_de_duplicarlos(self):
        liq = self.liquidacion()
        liq.action_armar()
        liq.action_armar()
        self.assertEqual(len(liq.linea_ids), 2)

    # ------------------------------------------------------------------ aprobar y no pagar dos veces

    def test_aprobar_anota_la_liquidacion_en_el_libro_y_baja_el_saldo_a_cero(self):
        liq = self.liquidacion()
        liq.action_aprobar()
        self.assertEqual((liq.estado, liq.aprobada_por), ('aprobada', self.u_nomina))
        self.assertTrue(liq.aprobada_el)
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (0, 0))
        filas = self.libro(tipo='liquidacion')
        self.assertEqual(sorted(filas.mapped('centavos')), [-12000, -8000])
        self.assertEqual(set(filas.mapped('liquidacion_id')), {liq})

    def test_nunca_se_paga_dos_veces_lo_mismo_ni_con_periodos_solapados(self):
        primera = self.liquidacion(hasta='2030-03-10')
        primera.action_aprobar()
        solapada = self.liquidacion(desde='2030-03-01', hasta='2030-03-31')
        self.assertEqual(self.totales(solapada), {(self.ana, 'comision'): 6000, (self.beto, 'comision'): 4000},
                         'del 1 al 31 solo toma lo que la primera no se llevó')
        solapada.action_aprobar()
        vacia = self.liquidacion(desde='2030-03-01', hasta='2030-04-30')
        self.assertFalse(vacia.linea_ids)
        with self.assertRaisesRegex(UserError, 'nada que liquidar'):
            vacia.action_aprobar()
        self.assertEqual(sum(self.libro(tipo='liquidacion').mapped('centavos')), -20000)

    def test_dos_propuestas_a_la_vez_solo_una_se_aprueba(self):
        a = self.liquidacion()
        b = self.liquidacion()
        a.action_aprobar()
        with self.assertRaisesRegex(UserError, 'cambió'):
            b.action_aprobar()
        b.action_armar()
        self.assertFalse(b.linea_ids, 'al armarla de nuevo ya no queda nada')
        self.assertEqual(sum(self.libro(tipo='liquidacion').mapped('centavos')), -20000)

    def test_si_llega_una_venta_mientras_tanto_hay_que_armar_otra_vez(self):
        liq = self.liquidacion(hasta='2030-04-30')
        self.venta_web(fecha='2030-04-02')
        with self.assertRaisesRegex(UserError, 'Armar'):
            liq.action_aprobar()
        liq.action_armar()
        liq.action_aprobar()
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (0, 0))

    # ------------------------------------------------------------------ quien cobra no aprueba

    def test_una_persona_que_cobra_en_la_liquidacion_no_la_aprueba(self):
        liq = self.liquidacion()
        self.assertTrue(liq.with_user(self.u_ana).tu_cobras)
        self.assertFalse(liq.tu_cobras, 'quien aprueba (Nómina) no figura entre quienes cobran')
        with self.assertRaisesRegex(UserError, 'figuras entre quienes cobran'):
            liq.with_user(self.u_ana).action_aprobar()
        self.assertEqual(liq.estado, 'borrador')
        liq.action_aprobar()
        self.assertEqual(liq.estado, 'aprobada')

    def test_quien_figura_en_la_lista_puede_aprobar_una_liquidacion_donde_no_cobra(self):
        self.liquidacion().action_aprobar()
        self.avanzar('2030-04-05 15:00:00')
        self.version(10.0, reparto=[(self.beto, 100.0)])
        self.venta_web(fecha='2030-04-05')
        liq = self.liquidacion(desde='2030-04-01', hasta='2030-04-30')
        self.assertEqual(self.totales(liq), {(self.beto, 'comision'): 10000})
        liq.with_user(self.u_ana).action_aprobar()
        self.assertEqual(liq.estado, 'aprobada')

    def test_el_contacto_de_trabajo_tambien_cuenta_para_la_proteccion(self):
        self.ana.work_contact_id = self.u_ana.partner_id
        self.ana.user_id = False
        liq = self.liquidacion()
        self.assertFalse(self.ana.user_id)
        self.assertTrue(liq.with_user(self.u_ana).tu_cobras, 'por su contacto de trabajo, sin usuario en la ficha')

    def test_ningun_proceso_aprueba_solo(self):
        liq = self.liquidacion()
        with self.assertRaisesRegex(UserError, 'una persona, con su propio usuario'):
            liq.with_user(SUPERUSER_ID).action_aprobar()
        self.env['dcasa.web.venta']._cron_barrido()
        self.assertEqual(liq.estado, 'borrador', 'el proceso de cada noche no aprueba ni paga nada')

    # ------------------------------------------------------------------ lo aprobado no se edita

    def test_una_liquidacion_aprobada_no_se_edita_ni_se_borra(self):
        liq = self.liquidacion()
        liq.action_aprobar()
        for valores in ({'fecha_hasta': '2030-12-31'}, {'notas': 'x'}, {'estado': 'borrador'}, {'total': 1.0},
                        {'aprobada_por': self.u_gerencia.id}):
            with self.subTest(valores=valores), self.assertRaisesRegex(UserError, 'no se edita'):
                liq.write(valores)
            with self.assertRaisesRegex(UserError, 'no se edita'):
                liq.sudo().write(valores)
        with self.assertRaisesRegex(UserError, 'no se edita'):
            liq.sudo().linea_ids[0].unlink()
        with self.assertRaisesRegex(UserError, 'no se borra'):
            liq.unlink()
        self.rechaza(lambda: liq.linea_ids[0].with_user(self.u_nomina).write({'centavos': 1}))

    def test_el_estado_no_se_cambia_a_mano_en_un_borrador(self):
        liq = self.liquidacion()
        with self.assertRaisesRegex(UserError, 'no se edita'):
            liq.write({'estado': 'aprobada'})

    def test_una_propuesta_se_edita_y_se_borra_mientras_es_borrador(self):
        liq = self.liquidacion()
        liq.write({'notas': 'primera quincena', 'fecha_hasta': '2030-03-15'})
        liq.action_armar()
        self.assertEqual(self.totales(liq), {(self.ana, 'comision'): 6000, (self.beto, 'comision'): 4000})
        liq.unlink()
        self.assertFalse(liq.exists())

    # ------------------------------------------------------------------ pagar y cancelar

    def test_marcar_como_pagada_pide_fecha_y_referencia_y_despues_ya_no_se_toca(self):
        liq = self.liquidacion()
        with self.assertRaisesRegex(UserError, 'aprobada'):
            liq.action_pagar()
        liq.action_aprobar()
        with self.assertRaisesRegex(UserError, 'fecha y la referencia'):
            liq.action_pagar()
        liq.write({'fecha_pago': '2030-04-03', 'referencia_pago': 'TRF-PRUEBA-1'})
        liq.action_pagar()
        self.assertEqual((liq.estado, liq.pagada_por, liq.referencia_pago), ('pagada', self.u_nomina, 'TRF-PRUEBA-1'))
        with self.assertRaisesRegex(UserError, 'no se edita'):
            liq.write({'referencia_pago': 'OTRA'})
        with self.assertRaisesRegex(UserError, 'ya pagada'):
            liq.action_cancelar()

    def test_cancelar_una_aprobada_con_filas_contrarias_devuelve_el_saldo(self):
        liq = self.liquidacion()
        liq.action_aprobar()
        with self.assertRaisesRegex(UserError, 'motivo'):
            liq.action_cancelar()
        liq._escribir({'motivo_cancelacion': 'Se calculó mal el periodo'})
        liq.action_cancelar()
        self.assertEqual(liq.estado, 'cancelada')
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (12000, 8000), 'la plata vuelve al saldo')
        contrarias = self.libro(tipo='liquidacion').filtered('reversa_id')
        self.assertEqual(sorted(contrarias.mapped('centavos')), [8000, 12000])
        self.assertTrue(all('Se calculó mal' in (m or '') for m in contrarias.mapped('motivo')))
        # y se puede armar y aprobar otra
        otra = self.liquidacion()
        otra.action_aprobar()
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (0, 0))

    def test_cancelar_una_propuesta_no_toca_el_libro(self):
        liq = self.liquidacion()
        filas = len(self.libro())
        liq.action_cancelar()
        self.assertEqual((liq.estado, len(self.libro())), ('cancelada', filas))

    # ------------------------------------------------------------------ los dos conceptos y el saldo en contra

    def test_la_tarifa_y_el_porcentaje_salen_en_renglones_aparte(self):
        self.avanzar('2030-04-02 15:00:00')
        self.env['dcasa.web.movimiento']._asentar(self.ana, 'tarifa', 741, self.company,
                                                  periodo_inicio=date(2030, 4, 1))
        liq = self.liquidacion(hasta='2030-04-30')
        self.assertEqual(self.totales(liq), {(self.ana, 'comision'): 12000, (self.ana, 'tarifa'): 741,
                                             (self.beto, 'comision'): 8000})

    def test_un_saldo_en_contra_se_avisa_se_paga_cero_y_sigue(self):
        self.liquidacion().action_aprobar()
        self.nota(self.venta_marzo, 1000.0, fecha='2030-04-02')       # devolución de una venta ya pagada
        liq = self.liquidacion(desde='2030-04-01', hasta='2030-04-30')
        self.assertFalse(liq.linea_ids, 'nunca se le cobra a alguien por la liquidación')
        self.assertIn('saldo en contra', liq.avisos)
        self.assertEqual(self.saldo(self.ana), -6000, 'el saldo negativo sigue ahí')
        self.avanzar('2030-04-10 15:00:00')
        self.venta_web(fecha='2030-04-10')
        siguiente = self.liquidacion(desde='2030-04-01', hasta='2030-04-30')
        self.assertEqual(self.totales(siguiente).get((self.ana, 'comision'), 0), 0,
                         'lo ganado ahora tapa primero lo que quedó en contra')
        self.assertEqual(self.totales(siguiente).get((self.beto, 'comision'), 0), 0)

    # ------------------------------------------------------------------ permisos

    def test_solo_gerencia_y_nomina_las_ven_y_las_manejan(self):
        liq = self.liquidacion()
        visibles = self.env['dcasa.web.liquidacion'].with_user(self.u_gerencia).search([('id', '=', liq.id)])
        self.assertEqual(visibles, liq)
        for usuario in (self.u_vendedora, self.u_caja, self.u_tecnico):
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError):
                    liq.with_user(usuario).read(['name'])
                with self.assertRaises(AccessError):
                    self.env['dcasa.web.liquidacion'].with_user(usuario).create({'fecha_desde': '2030-03-01',
                                                                                 'fecha_hasta': '2030-03-31'})
                with self.assertRaises(AccessError):
                    liq.with_user(usuario).action_aprobar()

    def test_la_numeracion_es_propia_y_consecutiva(self):
        a, b = self.liquidacion(armar=False), self.liquidacion(armar=False)
        self.assertTrue(a.name.startswith('LQW-'))
        self.assertEqual(int(b.name[4:]) - int(a.name[4:]), 1)
