"""«Costos de IA › Pagar» (pedido de la dueña, 2026-11-12): «Por pagar a Meta» vuelve a $0 y empieza a contar de nuevo.

Por dentro un pago no borra ni reinicia nada: marca un corte. Las cuentas puras (con sus bordes: otro mes, Worker caído,
meses sin fotos, varios pagos), el libro que no se edita ni se borra («Deshacer» lo anula con motivo), que sin Worker no
se registra nada y quién puede pagar.
"""
import os
from datetime import date, datetime
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import BaseCase, new_test_user, tagged

from ..models import panel_calculos as C
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
        self.assertEqual(r, {'usd': 5.25, 'completo': True, 'meses_sin_datos': [], 'meses_incompletos': []})

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

    def test_nunca_da_negativo(self):
        self.assertEqual(C.consumo_entre(('2026-11', 5.0), ('2026-10', 9.0), {})['usd'], 0.0, 'cortes al revés')
        self.assertEqual(C.consumo_entre(('2026-11', 5.0), ('2026-11', 4.0), {})['usd'], 0.0, 'el acumulado bajó')
        self.assertEqual(C.consumo_entre(('2026-10', 9.0), ('2026-11', 1.5), {'2026-10': (7.0, True)})['usd'], 1.5)

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

@tagged('post_install', '-at_install')
class TestPagosDeLaIa(JuanCase):

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

    def test_sin_pagos_el_saldo_es_lo_del_mes(self):
        datos = self.saldo(panama(2026, 11, 12, 10, 0), 7.5)
        self.assertEqual(datos, {'saldo': 7.5, 'aprox': False, 'ultimo': None})

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
            with self.assertRaisesRegex(UserError, 'cambió'):
                self.panel.pagar_ia(9.0)      # más de lo que hay: la pantalla estaba vieja
            # Menos sí (se siguió consumiendo mientras confirmaba): queda lo que se vio y el corte de ahora.
            pago = self.Pago.browse(self.panel.pagar_ia(7.2)['id'])
        self.assertEqual((pago.monto_meta_usd, pago.corte_acumulado_usd), (7.2, 7.5))
        self.assertEqual(self.Pago.search_count([]), 1)

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
        self.assertEqual(self.saldo(panama(2026, 11, 12, 12, 3), 6.5), {'saldo': 6.5, 'aprox': False, 'ultimo': None})
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
        self.assertEqual(panel._saldo_ia(('2026-11', 9.0)), {'saldo': None, 'aprox': False, 'ultimo': None})

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
