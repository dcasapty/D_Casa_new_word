"""«Costos de IA › Pagar» (pedido de la dueña, 2026-11-12): «Por pagar a Meta» vuelve a $0 y empieza a contar de nuevo.

Por dentro un pago no borra ni reinicia nada: marca un corte. Las cuentas puras (con sus bordes: otro mes, Worker caído,
meses sin fotos, varios pagos), el libro que no se edita ni se borra («Deshacer» lo anula con motivo), que sin Worker no
se registra nada y quién puede pagar.
"""
import os
import threading
from datetime import date, datetime
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo import SUPERUSER_ID, sql_db
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import BaseCase, new_test_user, tagged

from ..models import pagos_ia as P
from ..models import panel_calculos as C
from ..models.panel_juan import guardar_foto
from .common import COSTOS, SALUD, JuanCase
from .test_panel_juan import WorkerFalso, panama

# ----------------------------------------------------------------------------------------------------------------
# Cuentas puras
# ----------------------------------------------------------------------------------------------------------------

def pago(ident, dia, corte, monto=None, anulado=False, exacto=True, mes=11):
    return {'id': ident, 'fecha': datetime(2026, mes, dia, 12, 0), 'corte': corte, 'exacto': exacto, 'monto': monto,
            'anulado': anulado}


@tagged('post_install', '-at_install')
class TestCuentasDeLosPagos(BaseCase):

    def test_meses_entre(self):
        self.assertEqual(C.meses_entre('2026-11', '2027-02'), ['2026-11', '2026-12', '2027-01', '2027-02'])
        self.assertEqual(C.meses_entre('2026-11', '2026-11'), ['2026-11'])
        self.assertEqual(C.meses_entre('2026-11', '2026-10'), [])

    def test_el_cierre_de_cada_mes_es_su_ultima_foto(self):
        fotos = {date(2026, 10, 30): 11.0, date(2026, 10, 31): 12.5, date(2026, 9, 20): 5.0, date(2026, 11, 3): 1.0,
                 date(2027, 2, 28): 7.0}
        self.assertEqual(C.cierres_de_mes(fotos), {
            '2026-10': (12.5, True), '2026-09': (5.0, False), '2026-11': (1.0, False), '2027-02': (7.0, True)})
        self.assertEqual(C.cierres_de_mes({}), {})

    def test_en_el_mismo_mes_es_la_resta(self):
        r = C.consumo_entre(('2026-11', 2.5), ('2026-11', 7.75), {})
        self.assertEqual(r, {'usd': 5.25, 'completo': True, 'meses_sin_datos': [], 'meses_incompletos': [],
                             'bajo': False})

    def test_pago_en_un_mes_y_consulta_en_otro(self):
        # Pago el 20 de octubre con 8 del mes; octubre cerró en 12,50; noviembre lleva 3,25 (empezó en cero).
        r = C.consumo_entre(('2026-10', 8.0), ('2026-11', 3.25), {'2026-10': (12.5, True)})
        self.assertEqual((r['usd'], r['completo']), (7.75, True))

    def test_los_meses_completos_de_en_medio_suman_su_cierre(self):
        cierres = {'2026-08': (30.0, True), '2026-09': (25.0, True), '2026-10': (27.5, True)}
        r = C.consumo_entre(('2026-08', 10.0), ('2026-11', 1.0), cierres)
        self.assertEqual((r['usd'], r['completo']), (73.5, True))   # 20 + 25 + 27,5 + 1
        r = C.consumo_entre(('2026-12', 1.0), ('2027-01', 2.0), {'2026-12': (10.0, True)})
        self.assertEqual(r['usd'], 11.0, 'de diciembre a enero')

    def test_un_mes_sin_fotos_suma_cero_y_se_nombra(self):
        """Antes de que existiera el cron (u Odoo apagado todo el mes) no hay con qué: la cifra es un mínimo."""
        cierres = {'2026-08': (30.0, True), '2026-10': (27.5, True)}
        r = C.consumo_entre(('2026-08', 10.0), ('2026-11', 1.0), cierres)
        self.assertEqual((r['usd'], r['completo'], r['meses_sin_datos']), (48.5, False, ['2026-09']))
        # El mes del pago sin ninguna foto: lo que faltaba de ese mes no se sabe.
        r = C.consumo_entre(('2026-09', 4.0), ('2026-10', 2.0), {})
        self.assertEqual((r['usd'], r['completo'], r['meses_sin_datos']), (2.0, False, ['2026-09']))

    def test_un_mes_sin_la_foto_de_su_ultimo_dia_queda_incompleto(self):
        r = C.consumo_entre(('2026-10', 8.0), ('2026-11', 3.25), {'2026-10': (11.0, False)})
        self.assertEqual((r['usd'], r['completo'], r['meses_incompletos']), (6.25, False, ['2026-10']))

    def test_cortes_al_reves_dan_cero(self):
        self.assertEqual(C.consumo_entre(('2026-11', 5.0), ('2026-10', 9.0), {})['usd'], 0.0)

    def test_un_contador_que_baja_no_da_cero_en_silencio(self):
        """Revisión (2026-11-12): si el Worker volvió a empezar su cuenta después del pago, lo que se sabe es lo que
        lleva desde entonces, marcado como mínimo (``bajo``), nunca un $0 sin aviso."""
        r = C.consumo_entre(('2026-11', 40.0), ('2026-11', 0.0), {})
        self.assertEqual((r['usd'], r['completo'], r['bajo']), (0.0, False, True))
        r = C.consumo_entre(('2026-11', 5.0), ('2026-11', 4.0), {})
        self.assertEqual((r['usd'], r['completo'], r['bajo']), (4.0, False, True))
        # El mes del corte cerró por debajo del corte: cuenta su cierre (lo de después de volver a empezar).
        r = C.consumo_entre(('2026-10', 9.0), ('2026-11', 1.5), {'2026-10': (7.0, True)})
        self.assertEqual((r['usd'], r['completo'], r['bajo']), (8.5, False, True))
        # Medio centavo menos es redondeo, no un contador que volvió a empezar.
        r = C.consumo_entre(('2026-11', 5.0), ('2026-11', 4.996), {})
        self.assertEqual((r['usd'], r['completo'], r['bajo']), (0.0, True, False))

    def test_el_mes_que_manda_el_worker(self):
        self.assertTrue(C.mes_valido('2026-11'))
        for malo in ('2026-13', '2026-1', 'noviembre', None, 202611, '2026-11-01'):
            self.assertFalse(C.mes_valido(malo), malo)
        # A las 00:00:05 del 1 de diciembre (Odoo) el Worker todavía dice noviembre: el corte va con SU mes.
        primero = datetime(2026, 12, 1, 0, 0, 5)
        self.assertEqual(C.corte_del_pago(primero, {}, es_ahora=True, acumulado_worker=31.2, mes_worker='2026-11'),
                         {'mes': '2026-11', 'acumulado': 31.2, 'origen': 'worker', 'foto': None})
        # Un Worker viejo que no lo manda (o manda basura): el mes de Odoo, como antes.
        for mes in (None, 'ayer'):
            self.assertEqual(C.corte_del_pago(primero, {}, es_ahora=True, acumulado_worker=0.1, mes_worker=mes)['mes'],
                             '2026-12')

    def test_el_corte_del_pago(self):
        fotos = {date(2026, 10, 31): 9.0, date(2026, 11, 3): 2.0, date(2026, 11, 4): 2.6, date(2026, 11, 5): 3.1}
        ahora = datetime(2026, 11, 5, 15, 0)
        self.assertEqual(C.corte_del_pago(ahora, fotos, es_ahora=True, acumulado_worker=3.4),
                         {'mes': '2026-11', 'acumulado': 3.4, 'origen': 'worker', 'foto': None})
        # El Worker no respondió: la foto de hoy vale (se tomó antes del pago).
        self.assertEqual(C.corte_del_pago(ahora, fotos, es_ahora=True),
                         {'mes': '2026-11', 'acumulado': 3.1, 'origen': 'foto', 'foto': date(2026, 11, 5)})
        # Un pago de otro momento: la foto de ese mismo día pudo tomarse después; vale la del día anterior. Y lo que
        # diga el Worker ahora no describe ese momento.
        for worker in (None, 99.0):
            self.assertEqual(C.corte_del_pago(ahora, fotos, acumulado_worker=worker),
                             {'mes': '2026-11', 'acumulado': 2.6, 'origen': 'foto', 'foto': date(2026, 11, 4)})
        # Sin fotos de ese mes antes del pago: el 1 del mes, cuando el Worker empezó en cero (la del 31 es de octubre).
        self.assertEqual(C.corte_del_pago(datetime(2026, 11, 3, 8, 0), fotos),
                         {'mes': '2026-11', 'acumulado': 0.0, 'origen': 'inicio_de_mes', 'foto': None})
        self.assertEqual(C.corte_del_pago(ahora, {}, es_ahora=True)['origen'], 'inicio_de_mes')
        self.assertEqual(C.corte_del_pago(ahora, {}, es_ahora=True, acumulado_worker=-2)['acumulado'], 0.0)

    def test_sin_pagos_no_hay_cifra(self):
        self.assertEqual(C.periodos_de_pagos([], {}, ('2026-11', 5.0)), ({}, None))

    def test_un_solo_pago(self):
        por_pago, desde = C.periodos_de_pagos([pago(1, 2, ('2026-11', 1.0), 9.0)], {}, ('2026-11', 4.5))
        self.assertEqual(por_pago, {1: {'calculado': None, 'aproximado': False, 'diferencia': None}},
                         'el primero no tiene con qué compararse')
        self.assertEqual((desde['usd'], desde['pago_id'], desde['aproximado'], desde['completo']),
                         (3.5, 1, False, True))

    def test_varios_pagos_en_cualquier_orden(self):
        """Cuenta la FECHA del pago, no el orden en que se anotaron."""
        pagos = [pago(3, 10, ('2026-11', 7.0)), pago(1, 2, ('2026-11', 1.0), 9.0), pago(2, 6, ('2026-11', 4.0), 3.05)]
        por_pago, desde = C.periodos_de_pagos(pagos, {}, ('2026-11', 8.2))
        self.assertIsNone(por_pago[1]['calculado'])
        self.assertEqual((por_pago[2]['calculado']['usd'], por_pago[2]['diferencia']), (3.0, 0.05))
        self.assertEqual((por_pago[3]['calculado']['usd'], por_pago[3]['diferencia']), (3.0, None), 'Meta sin anotar')
        self.assertEqual((desde['usd'], desde['pago_id']), (1.2, 3))

    def test_un_pago_anulado_no_cuenta(self):
        pagos = [pago(1, 2, ('2026-11', 1.0)), pago(2, 6, ('2026-11', 4.0), anulado=True),
                 pago(3, 10, ('2026-11', 7.0), 6.1)]
        por_pago, desde = C.periodos_de_pagos(pagos, {}, ('2026-11', 8.2))
        self.assertIsNone(por_pago[2]['calculado'])
        self.assertEqual((por_pago[3]['calculado']['usd'], por_pago[3]['diferencia']), (6.0, 0.1))
        self.assertEqual(desde['pago_id'], 3)
        # Si el anulado era el último, se cuenta desde el anterior.
        por_pago, desde = C.periodos_de_pagos(pagos[:2], {}, ('2026-11', 8.2))
        self.assertEqual((desde['usd'], desde['pago_id']), (7.2, 1))

    def test_sin_worker_la_lista_sigue_pero_no_la_cifra(self):
        por_pago, desde = C.periodos_de_pagos([pago(1, 2, ('2026-11', 1.0)), pago(2, 6, ('2026-11', 4.0))], {}, None)
        self.assertIsNone(desde)
        self.assertEqual(por_pago[2]['calculado']['usd'], 3.0)

    def test_la_diferencia_solo_con_cifras_completas(self):
        pagos = [pago(1, 20, ('2026-10', 8.0), mes=10), pago(2, 5, ('2026-11', 2.0), 6.0)]
        por_pago, _desde = C.periodos_de_pagos(pagos, {}, None)   # sin fotos de octubre
        self.assertEqual((por_pago[2]['calculado']['usd'], por_pago[2]['calculado']['completo']), (2.0, False))
        self.assertIsNone(por_pago[2]['diferencia'], 'con un mínimo, la diferencia sería inventada')

    def test_un_corte_aproximado_se_marca(self):
        pagos = [pago(1, 2, ('2026-11', 1.0), exacto=False), pago(2, 6, ('2026-11', 4.0))]
        por_pago, desde = C.periodos_de_pagos(pagos, {}, ('2026-11', 5.0))
        self.assertTrue(por_pago[2]['aproximado'])
        self.assertFalse(desde['aproximado'], 'el último pago tiene corte exacto')


# ----------------------------------------------------------------------------------------------------------------
# El registro de pagos y la pantalla
# ----------------------------------------------------------------------------------------------------------------

class PagosCase(JuanCase):
    """Gerencia con el Worker de mentira y sin pagos ni fotos de antes."""

    def setUp(self):
        super().setUp()
        self.panel = self.env['dcasa.juan.panel'].with_user(self.gerente)
        self.worker = WorkerFalso({('GET', '/odoo/salud'): SALUD, ('GET', '/odoo/costos'): COSTOS})
        self.configurar_worker()
        parche = patch('requests.request', side_effect=self.worker)
        parche.start()
        self.addCleanup(parche.stop)
        # Cada prueba arranca sin pagos ni fotos, aunque la base traiga otros (se deshace al terminar la prueba).
        self.env.cr.execute('DELETE FROM dcasa_juan_pago_ia; DELETE FROM dcasa_juan_costo_dia')
        self.env.invalidate_all()
        self.Pago = self.env['dcasa.juan.pago.ia'].sudo()
        self.Foto = self.env['dcasa.juan.costo.dia'].sudo()

    def gasto(self, usd):
        self.worker.rutas['GET', '/odoo/salud'] = {**SALUD, 'gasto_ia_mes_usd': usd}

    def saldo(self, cuando, gasto):
        """Lo que dice la pantalla a esa hora (de Panamá) con el Worker llevando ``gasto`` del mes."""
        self.gasto(gasto)
        with freeze_time(cuando):
            return self.panel.costos()['pagos']

    def pagar(self, cuando, gasto, saldo=None):
        """Toca «Pagar» y confirma, con el saldo que la pantalla mostraba (si no se da, el de ese momento)."""
        if saldo is None:
            saldo = self.saldo(cuando, gasto)['saldo']
        self.gasto(gasto)
        with freeze_time(cuando):
            return self.Pago.browse(self.panel.pagar_ia(saldo)['id'])



@tagged('post_install', '-at_install')
class TestPagosDeLaIa(PagosCase):

    def test_sin_pagos_el_saldo_es_lo_del_mes(self):
        datos = self.saldo(panama(2026, 11, 12, 10, 0), 7.5)
        self.assertEqual(datos, {'saldo': 7.5, 'aprox': False, 'aprox_texto': '', 'saldo_si_se_deshace': None,
                                 'ultimo': None})

    def test_pagar_deja_el_saldo_en_cero_y_empieza_a_contar(self):
        pago = self.pagar(panama(2026, 11, 12, 10, 0), 7.5)
        self.assertEqual((pago.monto_meta_usd, pago.corte_mes, pago.corte_acumulado_usd, pago.corte_origen),
                         (7.5, '2026-11', 7.5, 'worker'))
        self.assertEqual((pago.fecha, pago.registrado_por, pago.al_momento, pago.anulado),
                         (panama(2026, 11, 12, 10, 0), self.gerente, True, False))
        self.assertEqual(self.Foto.search([('fecha', '=', date(2026, 11, 12))]).acumulado_usd, 7.5,
                         'al preguntarle al Worker queda también la foto de hoy')
        despues = self.saldo(panama(2026, 11, 12, 10, 5), 7.5)
        self.assertEqual((despues['saldo'], despues['ultimo']['monto'], despues['ultimo']['id']), (0.0, 7.5, pago.id))
        self.assertEqual(despues['ultimo']['texto'], '12 nov, 10:00 a. m.')
        # Y vuelve a contar: lo del mes sigue completo, el saldo es solo lo de después del pago.
        self.assertEqual(self.saldo(panama(2026, 11, 12, 15, 0), 8.25)['saldo'], 0.75)
        with freeze_time(panama(2026, 11, 12, 15, 0)):
            self.assertEqual(self.panel.costos()['gasto_usd'], 8.25)

    def test_con_el_worker_caido_no_se_registra_nada(self):
        self.worker.rutas['GET', '/odoo/salud'] = requests.ConnectionError('sin red')
        with freeze_time(panama(2026, 11, 12, 10, 0)), self.assertRaisesRegex(UserError, 'No pude hablar con Juan'):
            self.panel.pagar_ia(7.5)
        self.worker.rutas['GET', '/odoo/salud'] = ({'ok': False, 'error': 'no autorizado'}, 401)
        with self.assertRaisesRegex(UserError, 'No pude hablar con Juan'):
            self.panel.pagar_ia(7.5)
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}), \
                self.assertRaisesRegex(UserError, 'No pude hablar con Juan'):
            self.panel.pagar_ia(7.5)
        self.assertFalse(self.Pago.search([]))
        # Con el Worker caído la pantalla no muestra un saldo inventado.
        self.worker.rutas['GET', '/odoo/salud'] = requests.ConnectionError('sin red')
        self.assertNotIn('pagos', self.panel.costos())

    def test_un_saldo_que_no_sirve(self):
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            self.gasto(7.5)
            for saldo in (-1, 'mucho', True, None, float('nan'), 1e9, [3]):
                with self.subTest(saldo=saldo), self.assertRaises(UserError):
                    self.panel.pagar_ia(saldo)
            with self.assertRaisesRegex(UserError, 'nada por pagar'):
                self.panel.pagar_ia(0)
            for viejo in (9.0, 7.2):   # más, o bastante menos que lo de ahora: la pantalla estaba vieja
                with self.subTest(saldo=viejo), self.assertRaisesRegex(UserError, 'El saldo cambió'):
                    self.panel.pagar_ia(viejo)
            # Unos centavos menos (lo que se consumió mientras confirmaba, hasta el 1 % o $0.05): se acepta lo que se
            # vio, con el corte de ahora.
            pago = self.Pago.browse(self.panel.pagar_ia(7.43)['id'])
        self.assertEqual((pago.monto_meta_usd, pago.corte_acumulado_usd), (7.43, 7.5))
        self.assertEqual(self.Pago.search_count([]), 1)

    def test_la_pantalla_vieja_no_borra_consumo_sin_pagar(self):
        """Revisión (2026-11-12): abre el lunes con $1 por pagar, el viernes hay $41 y toca «Pagar» con la cifra del
        lunes. No se registra nada (pagar $1 dejaría el saldo en $0 y los $40 de la semana sin pagar)."""
        self.pagar(panama(2026, 11, 2, 9, 0), 10.0)
        visto = self.saldo(panama(2026, 11, 9, 9, 0), 11.0)['saldo']
        self.assertEqual(visto, 1.0)
        self.gasto(51.0)
        with freeze_time(panama(2026, 11, 13, 17, 0)), self.assertRaisesRegex(UserError, 'El saldo cambió'):
            self.panel.pagar_ia(visto)
        # $41 por pagar: el $1 del lunes y los $40 de la semana (la prueba de la revisión esperaba 40: era 51 − 11).
        self.assertEqual(self.saldo(panama(2026, 11, 13, 17, 1), 51.0)['saldo'], 41.0)
        self.assertEqual(self.Pago.search_count([]), 1)
        # La tolerancia crece con el saldo: con $41 por pagar, 41 centavos (el 1 %) todavía es la misma pantalla.
        pago = self.pagar(panama(2026, 11, 13, 17, 2), 51.0, saldo=40.62)
        self.assertEqual(pago.monto_meta_usd, 40.62)

    def test_un_acumulado_que_baja_se_avisa(self):
        """Revisión (2026-11-12): el contador del Worker volvió a empezar (o devolvió 0 por un fallo): nunca $0 sin
        aviso."""
        self.pagar(panama(2026, 11, 10, 9, 0), 40.0)
        datos = self.saldo(panama(2026, 11, 12, 9, 0), 0.0)
        self.assertEqual((datos['saldo'], datos['aprox']), (0.0, True))
        self.assertIn('volvió a empezar', datos['aprox_texto'])
        datos = self.saldo(panama(2026, 11, 12, 15, 0), 2.5)
        self.assertEqual((datos['saldo'], datos['aprox']), (2.5, True), 'lo que lleva desde que volvió a empezar')

    def test_un_gasto_sin_dato_del_worker_no_es_un_cero(self):
        """Revisión (2026-11-12): el Worker contesta ``gasto_ia_mes_usd: null`` si no pudo leer su contador."""
        self.pagar(panama(2026, 11, 10, 9, 0), 4.0)
        fotos_antes = self.Foto.search_count([])
        self.worker.rutas['GET', '/odoo/salud'] = {**SALUD, 'gasto_ia_mes_usd': None, 'mes': '2026-11'}
        with freeze_time(panama(2026, 11, 12, 9, 0)):
            r = self.panel.costos()
            self.assertEqual((r['ok'], r['mensaje']), (False, 'No pude leer el gasto de IA'))
            self.assertNotIn('pagos', r)
            with self.assertRaisesRegex(UserError, 'No pude hablar con Juan'):
                self.panel.pagar_ia(1.0)
            self.env['dcasa.juan.costo.dia']._cron_foto_diaria()
        self.assertEqual(self.Foto.search_count([]), fotos_antes, 'sin dato no hay foto')
        self.assertEqual(self.Pago.search_count([]), 1)

    def test_el_mes_del_corte_lo_dice_el_worker(self):
        """Revisión (2026-11-12): a las 00:00:05 del 1 de diciembre en Odoo, el Worker todavía cuenta noviembre."""
        primero_de_diciembre = panama(2026, 12, 1, 0, 0, 5)
        self.worker.rutas['GET', '/odoo/salud'] = {**SALUD, 'gasto_ia_mes_usd': 31.2, 'mes': '2026-11'}
        with freeze_time(primero_de_diciembre):
            datos = self.panel.costos()['pagos']
            self.assertEqual(datos['saldo'], 31.2)
            pago = self.Pago.browse(self.panel.pagar_ia(31.2)['id'])
        self.assertEqual((pago.corte_mes, pago.corte_acumulado_usd), ('2026-11', 31.2))
        self.assertFalse(self.Foto.search([('fecha', '=', date(2026, 12, 1))]),
                         'el total de noviembre no queda como foto del 1 de diciembre')
        # Ya en diciembre: el saldo es lo de diciembre (noviembre se pagó entero).
        self.worker.rutas['GET', '/odoo/salud'] = {**SALUD, 'gasto_ia_mes_usd': 0.4, 'mes': '2026-12'}
        self.Foto._guardar(date(2026, 11, 30), 31.2)
        with freeze_time(panama(2026, 12, 1, 9, 0)):
            self.assertEqual(self.panel.costos()['pagos']['saldo'], 0.4)
        # Un Worker viejo que no manda el mes: el de Odoo, como antes.
        self.worker.rutas['GET', '/odoo/salud'] = {**SALUD, 'gasto_ia_mes_usd': 0.9}
        with freeze_time(panama(2026, 12, 1, 15, 0)):
            pago = self.Pago.browse(self.panel.pagar_ia(0.9)['id'])
        self.assertEqual((pago.corte_mes, pago.corte_acumulado_usd), ('2026-12', 0.9))

    def test_deshacer_toma_el_cerrojo_y_si_otro_pago_entro_no_deshace(self):
        """Revisión, segunda vuelta (2026-11-12): un «Deshacer» mientras otro «Pagar» habla con el Worker. Con el
        cerrojo ocupado (o tomado y soltado por el otro después de que empezó esta transacción), no se anula nada."""
        primero = self.pagar(panama(2026, 11, 10, 9, 0), 7.5)
        with patch.object(P, 'tomar_el_cerrojo', return_value=False), \
                self.assertRaisesRegex(UserError, 'Algo cambió mientras tanto'):
            self.panel.deshacer_pago_ia(primero.id)
        self.assertFalse(primero.anulado)
        # Con el cerrojo libre, lo toma ANTES de anular y vuelve a revisar que siga siendo el último.
        orden = []
        tomar = P.tomar_el_cerrojo
        anular = type(primero)._anular

        def cerrojo(cr, cuando):
            orden.append('cerrojo')
            return tomar(cr, cuando)

        def anulado(registro, motivo):
            orden.append('anular')
            return anular(registro, motivo)

        with patch.object(P, 'tomar_el_cerrojo', side_effect=cerrojo), \
                patch.object(type(primero), '_anular', anulado):
            self.panel.deshacer_pago_ia(primero.id)
        self.assertEqual(orden, ['cerrojo', 'anular'])
        self.assertTrue(primero.anulado)

    def test_una_foto_que_otra_pestana_sube_a_la_vez_no_es_un_error(self):
        """Revisión, segunda vuelta (2026-11-12): si otra pestaña (o el cron) sube la foto de hoy mientras «Pagar»
        habla con el Worker, el choque de serialización ya no sale en ERROR ni hace reintentar todo: se sigue sin la
        foto (la del otro queda). Con dos conexiones de verdad a la base."""
        base = sql_db.db_connect(self.env.cr.dbname)
        dia, cuando = date(2001, 1, 1), datetime(2026, 11, 12, 15, 0)
        try:
            with base.cursor() as preparar:
                preparar.execute('DELETE FROM dcasa_juan_costo_dia WHERE fecha = %s', [dia])
                self.assertTrue(guardar_foto(preparar, dia, 5.0, SUPERUSER_ID, cuando))
            with base.cursor() as otra, base.cursor() as pagar, self.assertNoLogs('odoo.sql_db', level='ERROR'):
                pagar.execute('SELECT 1')           # «Pagar» ya empezó: su transacción ve la foto de antes
                self.assertTrue(guardar_foto(otra, dia, 6.0, SUPERUSER_ID, cuando))
                otra.commit()
                self.assertFalse(guardar_foto(pagar, dia, 7.5, SUPERUSER_ID, cuando), 'choca: sigue sin la foto')
                pagar.execute('SELECT 1')           # y su transacción sigue viva (el pago se puede registrar)
                # Solo sube: una foto menor no baja la del día.
                pagar.rollback()
                self.assertTrue(guardar_foto(pagar, dia, 3.0, SUPERUSER_ID, cuando))
                pagar.commit()
            with base.cursor() as ver:
                ver.execute('SELECT acumulado_usd FROM dcasa_juan_costo_dia WHERE fecha = %s', [dia])
                self.assertEqual(ver.fetchone()[0], 6.0)
        finally:
            with base.cursor() as limpiar:
                limpiar.execute('DELETE FROM dcasa_juan_costo_dia WHERE fecha = %s', [dia])

    def test_dos_pagar_a_la_vez_el_segundo_sale_con_el_saldo_cambio(self):
        """Revisión (2026-11-12): dos «Sí, ya pagué» a la vez (dos pestañas o dos personas), con dos conexiones de
        verdad a la base. El segundo espera al primero y, cuando el primero termina, no registra nada."""
        base = sql_db.db_connect(self.env.cr.dbname)
        with base.cursor() as revisar:
            revisar.execute('SELECT 1 FROM ir_config_parameter WHERE key = %s', [P.CLAVE_DEL_CERROJO])
            existia = bool(revisar.fetchone())
        cuando = datetime(2026, 11, 12, 15, 0)
        resultado = []
        try:
            with base.cursor() as uno, base.cursor() as dos:
                dos.execute('SELECT 1')        # la transacción del segundo ya empezó (ve la base de antes)
                self.assertTrue(P.tomar_el_cerrojo(uno, cuando))
                hilo = threading.Thread(target=lambda: resultado.append(P.tomar_el_cerrojo(dos, cuando)))
                hilo.start()
                hilo.join(1.5)
                self.assertTrue(hilo.is_alive(), 'el segundo espera a que el primero termine')
                uno.commit()
                hilo.join(15)
                self.assertFalse(hilo.is_alive())
                self.assertEqual(resultado, [False], 'el segundo no se registra: «El saldo cambió»')
                dos.rollback()
                # Uno que empieza después de que el primero terminó sí puede (ve el pago nuevo y revisa su saldo).
                self.assertTrue(P.tomar_el_cerrojo(dos, cuando))
                dos.rollback()
        finally:
            if not existia:
                with base.cursor() as limpiar:
                    limpiar.execute('DELETE FROM ir_config_parameter WHERE key = %s', [P.CLAVE_DEL_CERROJO])

    def test_deshacer_el_ultimo_pago_deja_el_saldo_como_estaba(self):
        primero = self.pagar(panama(2026, 11, 10, 9, 0), 3.0)
        segundo = self.pagar(panama(2026, 11, 12, 9, 0), 6.0)
        self.assertEqual(self.saldo(panama(2026, 11, 12, 12, 0), 6.5)['saldo'], 0.5)
        with self.assertRaisesRegex(UserError, 'último'):
            self.panel.deshacer_pago_ia(primero.id)
        for raro in (999999, 'x', True):
            with self.subTest(pago=raro), self.assertRaises(UserError):
                self.panel.deshacer_pago_ia(raro)
        with freeze_time(panama(2026, 11, 12, 12, 1)):
            self.panel.deshacer_pago_ia(segundo.id)
        self.assertEqual((segundo.anulado, segundo.motivo_anulacion, segundo.anulado_por, segundo.anulado_el),
                         (True, 'Deshecho desde la pantalla', self.gerente, panama(2026, 11, 12, 12, 1)))
        datos = self.saldo(panama(2026, 11, 12, 12, 2), 6.5)
        self.assertEqual((datos['saldo'], datos['ultimo']['id']), (3.5, primero.id), 'cuenta desde el pago anterior')
        with self.assertRaises(UserError):
            self.panel.deshacer_pago_ia(segundo.id)    # ya deshecho
        # El de antes ahora es el último: también se puede deshacer, y sin pagos vuelve a ser lo del mes.
        self.panel.deshacer_pago_ia(primero.id)
        datos = self.saldo(panama(2026, 11, 12, 12, 3), 6.5)
        self.assertEqual((datos['saldo'], datos['ultimo'], datos['saldo_si_se_deshace']), (6.5, None, None))
        self.assertEqual(self.Pago.search_count([]), 2, 'nada se borra: quedan en la historia, anulados')

    def test_un_pago_no_se_edita_ni_se_borra(self):
        p = self.pagar(panama(2026, 11, 12, 10, 0), 7.5)
        for cambio in ({'monto_meta_usd': 1.0}, {'corte_acumulado_usd': 0.0}, {'anulado': True}):
            with self.subTest(cambio=cambio), self.assertRaises(UserError):
                p.write(cambio)
        with self.assertRaises(UserError):
            p.unlink()
        # Ni Gerencia por RPC: el ACL solo da lectura (los pagos se crean y se deshacen por el panel).
        Rpc = self.env(user=self.gerente)['dcasa.juan.pago.ia']
        with self.assertRaises(UserError):
            call_kw(Rpc, 'write', [[p.id], {'monto_meta_usd': 1.0}], {})
        with self.assertRaises(AccessError):
            call_kw(Rpc, 'write', [[p.id], {'anulado': True, 'motivo_anulacion': 'x'}],
                    {'context': {'dcasa_pago_ia_anulando': True}})
        with self.assertRaises(AccessError):
            call_kw(Rpc, 'create', [{'fecha': '2026-11-12 15:00:00', 'corte_mes': '2026-11',
                                     'corte_acumulado_usd': 0.0, 'corte_origen': 'worker'}], {})
        with self.assertRaises(UserError):
            call_kw(Rpc, 'unlink', [[p.id]], {})
        self.assertEqual((p.monto_meta_usd, p.corte_acumulado_usd, p.anulado), (7.5, 7.5, False))
        self.assertEqual(len(call_kw(Rpc, 'search_read', [[]], {'fields': ['monto_meta_usd']})), 1, 'Gerencia lo lee')

    def test_una_vendedora_no_puede_pagar_ni_deshacer(self):
        p = self.pagar(panama(2026, 11, 12, 10, 0), 7.5)
        for usuario in (self.vendedora, self.interno, self.portal):
            for metodo, args in (('pagar_ia', [1.0]), ('deshacer_pago_ia', [p.id]), ('costos', [])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.juan.panel'], metodo, args, {})
            with self.subTest(usuario=usuario.login, metodo='search_read'), self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.juan.pago.ia'], 'search_read', [[]], {})
        self.assertEqual((self.Pago.search_count([]), p.anulado), (1, False))
        panel = self.env['dcasa.juan.panel'].with_user(self.vendedora)
        self.assertEqual(panel._saldo_ia(('2026-11', 9.0)), {'saldo': None, 'aprox': False, 'aprox_texto': '',
                                                             'saldo_si_se_deshace': None, 'ultimo': None})

    def test_un_administrador_tambien_puede_pagar(self):
        admin = new_test_user(self.env, login='juan_admin_pagos', groups='base.group_user,base.group_system')
        self.gasto(2.0)
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            r = call_kw(self.env(user=admin)['dcasa.juan.panel'], 'pagar_ia', [2.0], {})
        self.assertEqual(self.Pago.browse(r['id']).registrado_por, admin)

    def test_pago_en_un_mes_y_saldo_en_otro(self):
        self.pagar(panama(2026, 10, 20, 10, 0), 8.0)
        self.Foto._guardar(date(2026, 10, 31), 12.5)          # octubre cerró en 12,50
        datos = self.saldo(panama(2026, 11, 12, 10, 0), 3.25)   # noviembre lleva 3,25
        self.assertEqual((datos['saldo'], datos['aprox']), (7.75, False))
        self.assertEqual(datos['ultimo']['texto'], '20 oct, 10:00 a. m.')

    def test_sin_las_fotos_de_un_mes_el_saldo_sale_aproximado(self):
        self.pagar(panama(2026, 10, 20, 10, 0), 8.0)
        self.Foto.search([]).unlink()                        # la foto que dejó el pago
        self.Foto._guardar(date(2026, 10, 25), 10.0)         # el cron dejó de correr el 25
        datos = self.saldo(panama(2026, 12, 3, 10, 0), 1.5)
        self.assertEqual((datos['saldo'], datos['aprox']), (3.5, True))   # (10 − 8) + 0 (noviembre) + 1,5: un mínimo

    def test_el_ano_sale_solo_si_no_es_el_de_ahora(self):
        self.pagar(panama(2026, 12, 30, 18, 0), 4.0)
        self.assertEqual(self.saldo(panama(2027, 1, 2, 9, 0), 0.5)['ultimo']['texto'], '30 dic 2026, 6:00 p. m.')


@tagged('post_install', '-at_install')
class TestBrianCostosDeJuan(PagosCase):
    """Brian contesta «¿cuánto le debo a Meta de la IA?» con las cifras de la pantalla. Solo lee: pagar es de la
    pantalla (lo declara la dueña después de pagarle a Meta)."""

    def brian(self, usuario, gasto=None, cuando=None):
        if gasto is not None:
            self.gasto(gasto)
        with freeze_time(cuando or panama(2026, 11, 12, 11, 0)):
            return self.env['brian.herramientas'].with_user(usuario).ejecutar('costos_de_juan', {})

    def test_es_de_lectura_y_solo_de_gerencia_y_administradores(self):
        Brian = self.env['brian.herramientas']
        catalogo = {e['name']: e for e in Brian.with_user(self.gerente).catalogo()}
        self.assertEqual(catalogo['costos_de_juan']['nivel'], 'lectura')
        admin = new_test_user(self.env, login='juan_admin_brian', groups='base.group_user,base.group_system')
        self.assertIn('costos_de_juan', {e['name'] for e in Brian.with_user(admin).catalogo()})
        self.assertTrue(self.brian(admin, 7.5)['ok'])
        for usuario in (self.vendedora, self.interno):
            with self.subTest(usuario=usuario.login):
                self.assertNotIn('costos_de_juan', {e['name'] for e in Brian.with_user(usuario).catalogo()})
                respuesta = self.brian(usuario, 7.5)
                self.assertFalse(respuesta['ok'])
                self.assertIn('no tienes permiso', respuesta['error'])
        # Pagar y deshacer el pago de la IA no son de Brian: no hay herramienta que los haga.
        self.assertFalse([n for n in Brian._todas() if 'pagar' in n or ('deshacer' in n and 'pago' in n)])

    def test_gerencia_recibe_las_cifras_de_la_pantalla(self):
        respuesta = self.brian(self.gerente, 7.5)
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        self.assertEqual((datos['por_pagar_a_meta'], datos['ultimo_pago']), ('$7.50', 'ninguno todavía'))
        self.assertEqual(datos['gasto_del_mes']['gasto'], '$7.50')
        self.assertEqual((datos['gasto_del_mes']['tope'], datos['gasto_del_mes']['porcentaje_del_tope']),
                         ('$30.00', '25 %'))
        self.assertEqual(datos['gasto_del_mes']['mes'], 'noviembre de 2026')
        self.assertIn('«Pagar»', datos['para_marcar_un_pago'])
        self.assertEqual(datos['abrir']['titulo'], 'Costos de IA')
        # Después de pagar en la pantalla: el saldo en $0 y el último pago; luego vuelve a contar.
        self.pagar(panama(2026, 11, 12, 10, 0), 7.5)
        datos = self.brian(self.gerente, 7.5)['datos']
        self.assertEqual((datos['por_pagar_a_meta'], datos['ultimo_pago']),
                         ('$0.00', {'monto': '$7.50', 'fecha': '12 nov, 10:00 a. m.'}))
        datos = self.brian(self.gerente, 8.25)['datos']
        self.assertEqual(datos['por_pagar_a_meta'], '$0.75')
        self.assertEqual(datos['gasto_del_mes']['gasto'], '$8.25', 'el gasto del mes sigue completo')
        with freeze_time(panama(2026, 11, 12, 11, 0)):
            self.assertEqual(self.panel.costos()['pagos']['saldo'], 0.75, 'la misma cifra que la pantalla')
        self.assertEqual(self.Pago.search_count([]), 1, 'Brian solo lee: no registró nada')

    def test_si_faltan_fotos_lo_dice(self):
        self.pagar(panama(2026, 10, 20, 10, 0), 8.0)
        self.Foto.search([]).unlink()
        self.Foto._guardar(date(2026, 10, 25), 10.0)
        datos = self.brian(self.gerente, 1.5, panama(2026, 12, 3, 10, 0))['datos']
        self.assertTrue(datos['por_pagar_a_meta'].startswith('$3.50 (aprox.'), datos['por_pagar_a_meta'])

    def test_con_el_worker_caido_no_inventa_cifras(self):
        self.pagar(panama(2026, 11, 12, 10, 0), 7.5)
        self.worker.rutas['GET', '/odoo/salud'] = requests.ConnectionError('sin red')
        datos = self.brian(self.gerente)['datos']
        self.assertIn('No pude hablar con el Worker', datos['sin_cifras'])
        self.assertIn('no se inventan', datos['sin_cifras'])
        self.assertNotIn('por_pagar_a_meta', datos)
        self.assertNotIn('gasto_del_mes', datos)
        self.assertEqual(datos['ultimo_pago'], {'monto': '$7.50', 'fecha': '12 nov, 10:00 a. m.'})
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            datos = self.brian(self.gerente)['datos']
        self.assertIn('Falta conectar el bot', datos['sin_cifras'])
        # El Worker contesta pero no pudo leer su contador (null): tampoco hay cifras.
        self.worker.rutas['GET', '/odoo/salud'] = {**SALUD, 'gasto_ia_mes_usd': None}
        datos = self.brian(self.gerente)['datos']
        self.assertIn('No pude leer el gasto de IA', datos['sin_cifras'])
        self.assertNotIn('por_pagar_a_meta', datos)
