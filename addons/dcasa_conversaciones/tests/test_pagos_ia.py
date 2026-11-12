"""«Costos de IA»: anotar que Meta ya cobró y ver lo consumido desde el último pago (pedido de la dueña, 2026-11-12).

Un pago no borra ni reinicia nada: marca un corte. Las cuentas puras (con sus bordes: otro mes, Worker caído, meses sin
fotos, varios pagos), el libro que no se edita ni se borra (se anula con motivo) y quién puede verlo y anotarlo.
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

    def anotar(self, cuando, gasto=None, fecha=None, monto=None, nota=None):
        """Anota un pago a esa hora (de Panamá) con el Worker diciendo ``gasto``."""
        if gasto is not None:
            self.gasto(gasto)
        with freeze_time(cuando):
            return self.Pago.browse(self.panel.registrar_pago_ia(fecha, monto, nota)['id'])

    def pagos(self, cuando, gasto):
        self.gasto(gasto)
        with freeze_time(cuando):
            return self.panel.costos()['pagos']

    def test_anotado_ahora_el_corte_lo_da_el_worker(self):
        self.gasto(7.5)
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            r = self.panel.registrar_pago_ia(None, 7.4, '  cobro   a la tarjeta ')
        p = self.Pago.browse(r['id'])
        self.assertTrue(r['exacto'])
        self.assertIn('exacto', r['corte'])
        self.assertEqual((p.corte_mes, p.corte_acumulado_usd, p.corte_origen, p.al_momento),
                         ('2026-11', 7.5, 'worker', True))
        self.assertEqual((p.monto_meta_usd, p.nota, p.registrado_por, p.fecha),
                         (7.4, 'cobro a la tarjeta', self.gerente, panama(2026, 11, 12, 10, 0)))
        self.assertEqual(self.Foto.search([('fecha', '=', date(2026, 11, 12))]).acumulado_usd, 7.5,
                         'al preguntarle al Worker queda también la foto de hoy')

    def test_la_fecha_de_hace_un_momento_tambien_es_ahora(self):
        p = self.anotar(panama(2026, 11, 12, 10, 4), 7.5, fecha='2026-11-12T10:00')
        self.assertEqual((p.corte_origen, p.fecha), ('worker', panama(2026, 11, 12, 10, 0)))
        # Unos minutos «adelante» (el reloj del teléfono) son ahora, con la hora del servidor.
        p = self.anotar(panama(2026, 11, 12, 10, 4), 7.5, fecha='2026-11-12T10:09')
        self.assertEqual((p.corte_origen, p.fecha), ('worker', panama(2026, 11, 12, 10, 4)))

    def test_sin_worker_usa_la_ultima_foto_y_lo_dice(self):
        self.Foto._guardar(date(2026, 11, 10), 4.0)
        self.Foto._guardar(date(2026, 11, 11), 5.5)
        self.worker.rutas['GET', '/odoo/salud'] = requests.ConnectionError('sin red')
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            r = self.panel.registrar_pago_ia()
        p = self.Pago.browse(r['id'])
        self.assertEqual((p.corte_origen, p.corte_foto, p.corte_acumulado_usd), ('foto', date(2026, 11, 11), 5.5))
        self.assertFalse(r['exacto'])
        self.assertIn('no respondió', r['corte'])
        self.assertIn('11 de noviembre', r['corte'])

    def test_un_pago_de_otro_dia_usa_la_foto_del_dia_anterior_sin_preguntar_al_worker(self):
        for dia, usd in ((3, 2.0), (4, 2.6), (5, 3.1)):
            self.Foto._guardar(date(2026, 11, dia), usd)
        p = self.anotar(panama(2026, 11, 12, 10, 0), fecha='2026-11-05T09:30')
        self.assertEqual((p.corte_origen, p.corte_foto, p.corte_acumulado_usd, p.al_momento),
                         ('foto', date(2026, 11, 4), 2.6, False))
        self.assertEqual((p.fecha, p.monto_meta_usd), (panama(2026, 11, 5, 9, 30), 0.0))
        self.assertEqual(self.worker.llamadas, [])

    def test_sin_fotos_de_ese_mes_cuenta_desde_el_inicio_del_mes(self):
        self.Foto._guardar(date(2026, 10, 31), 9.0)
        p = self.anotar(panama(2026, 11, 12, 10, 0), fecha='2026-11-03T08:00')
        self.assertEqual((p.corte_origen, p.corte_mes, p.corte_acumulado_usd), ('inicio_de_mes', '2026-11', 0.0))
        self.assertIn('1 de noviembre', self.panel._texto_del_corte(p, self.panel._horario()))

    def test_fechas_y_montos_que_no_sirven(self):
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            for fecha in ('2026-11-12T11:00', '2025-01-01T10:00', 'ayer', '12/11/2026 10:00', '2026-02-30T10:00', 5):
                with self.subTest(fecha=fecha), self.assertRaises(UserError):
                    self.panel.registrar_pago_ia(fecha)
            for monto in (-1, 'mucho', True, float('nan'), 1e9, [3]):
                with self.subTest(monto=monto), self.assertRaises(UserError):
                    self.panel.registrar_pago_ia(None, monto)
            with self.assertRaises(UserError):
                self.panel.registrar_pago_ia(None, None, {'texto': 'x'})
        self.assertFalse(self.Pago.search([]))
        self.assertEqual(self.anotar(panama(2026, 11, 12, 10, 0), monto='11,20').monto_meta_usd, 11.2)
        self.assertEqual(self.anotar(panama(2026, 11, 12, 10, 0), monto='').monto_meta_usd, 0.0, 'vacío = sin anotar')
        self.assertEqual(len(self.anotar(panama(2026, 11, 12, 10, 0), nota='x' * 900).nota), 300)

    def test_un_pago_no_se_edita_ni_se_borra(self):
        p = self.anotar(panama(2026, 11, 12, 10, 0), 7.5, monto=7.4)
        for cambio in ({'monto_meta_usd': 1.0}, {'corte_acumulado_usd': 0.0}, {'anulado': True}):
            with self.subTest(cambio=cambio), self.assertRaises(UserError):
                p.write(cambio)
        with self.assertRaises(UserError):
            p.unlink()
        # Ni Gerencia por RPC: el ACL solo da lectura (los pagos se crean y se anulan por el panel).
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
        self.assertEqual((p.monto_meta_usd, p.corte_acumulado_usd, p.anulado), (7.4, 7.5, False))
        self.assertEqual(len(call_kw(Rpc, 'search_read', [[]], {'fields': ['monto_meta_usd']})), 1, 'Gerencia lo lee')

    def test_anular_deja_la_historia_y_deja_de_contar(self):
        primero = self.anotar(panama(2026, 11, 10, 9, 0), 3.0, monto=3.0)
        segundo = self.anotar(panama(2026, 11, 12, 9, 0), 6.0, monto=3.1)
        antes = self.pagos(panama(2026, 11, 12, 12, 0), 6.5)
        self.assertEqual((antes['desde_el_ultimo']['usd'], antes['total']), (0.5, 2))
        with self.assertRaises(UserError):
            self.panel.anular_pago_ia(segundo.id, '   ')
        with freeze_time(panama(2026, 11, 12, 11, 0)):
            self.panel.anular_pago_ia(segundo.id, 'Me equivoqué de fecha')
        self.assertEqual((segundo.anulado, segundo.motivo_anulacion, segundo.anulado_por, segundo.anulado_el),
                         (True, 'Me equivoqué de fecha', self.gerente, panama(2026, 11, 12, 11, 0)))
        for repetido in (segundo.id, 999999, 'x'):
            with self.subTest(pago=repetido), self.assertRaises(UserError):
                self.panel.anular_pago_ia(repetido, 'otra vez')
        despues = self.pagos(panama(2026, 11, 12, 12, 0), 6.5)
        self.assertEqual(despues['desde_el_ultimo']['usd'], 3.5, 'desde el primer pago: el anulado no cuenta')
        self.assertEqual(despues['ultimo']['id'], primero.id)
        fila = next(f for f in despues['lista'] if f['id'] == segundo.id)
        self.assertTrue(fila['anulado'])
        self.assertIn('Me equivoqué de fecha', fila['anulado_texto'])
        self.assertIn(self.gerente.name, fila['anulado_texto'])
        self.assertEqual((fila['calculado'], fila['diferencia'], despues['total']), (None, None, 2))

    def test_una_vendedora_no_ve_ni_anota_ni_anula(self):
        p = self.anotar(panama(2026, 11, 12, 10, 0), 7.5)
        for usuario in (self.vendedora, self.interno, self.portal):
            for metodo, args in (('registrar_pago_ia', []), ('anular_pago_ia', [p.id, 'no me gusta'])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.juan.panel'], metodo, args, {})
            with self.subTest(usuario=usuario.login, metodo='search_read'), self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.juan.pago.ia'], 'search_read', [[]], {})
            with self.subTest(usuario=usuario.login, metodo='costos'), self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.juan.panel'], 'costos', [], {})
        self.assertEqual((self.Pago.search_count([]), p.anulado), (1, False))
        self.assertFalse(self.env['dcasa.juan.panel'].with_user(self.vendedora)._pagos_ia()['hay'])

    def test_un_administrador_tambien_anota_pagos(self):
        admin = new_test_user(self.env, login='juan_admin_pagos', groups='base.group_user,base.group_system')
        self.gasto(2.0)
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            r = call_kw(self.env(user=admin)['dcasa.juan.panel'], 'registrar_pago_ia', [], {'monto': 2.5})
        self.assertEqual(self.Pago.browse(r['id']).registrado_por, admin)

    def test_sin_pagos_la_pantalla_queda_como_hoy(self):
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            r = self.panel.costos()
        self.assertTrue(r['ok'])
        self.assertEqual(r['gasto_usd'], 12.34)
        self.assertEqual((r['pagos']['hay'], r['pagos']['desde_el_ultimo'], r['pagos']['lista']), (False, None, []))
        self.assertEqual((r['pagos']['ahora_local'], r['pagos']['zona']), ('2026-11-12T10:00', 'America/Panama'))

    def test_el_mes_del_pago_y_el_de_la_consulta_son_distintos(self):
        self.anotar(panama(2026, 10, 20, 10, 0), 8.0, monto=20.0)
        self.Foto._guardar(date(2026, 10, 31), 12.5)
        desde = self.pagos(panama(2026, 11, 12, 10, 0), 3.25)['desde_el_ultimo']
        self.assertEqual((desde['usd'], desde['completo'], desde['aproximado']), (7.75, True, False))

    def test_sin_el_cierre_del_mes_la_cifra_es_un_minimo_y_lo_dice(self):
        self.anotar(panama(2026, 10, 20, 10, 0), 8.0)
        self.Foto.search([]).unlink()      # la foto que dejó el pago
        self.Foto._guardar(date(2026, 10, 25), 10.0)   # el cron dejó de correr el 25
        desde = self.pagos(panama(2026, 12, 3, 10, 0), 1.5)['desde_el_ultimo']
        self.assertEqual((desde['usd'], desde['completo']), (3.5, False))   # (10 − 8) + 0 (noviembre) + 1,5
        self.assertEqual(desde['meses_incompletos'], ['octubre de 2026'])
        self.assertEqual(desde['meses_sin_datos'], ['noviembre de 2026'])
        self.assertEqual(desde['faltan_texto'], 'octubre de 2026, noviembre de 2026')

    def test_varios_pagos_cada_uno_con_su_periodo_y_su_diferencia(self):
        p1 = self.anotar(panama(2026, 11, 2, 9, 0), 1.0, monto=9.0)
        p2 = self.anotar(panama(2026, 11, 6, 9, 0), 4.0, monto=3.05)
        p3 = self.anotar(panama(2026, 11, 10, 9, 0), 7.0)
        datos = self.pagos(panama(2026, 11, 12, 10, 0), 8.2)
        filas = {f['id']: f for f in datos['lista']}
        self.assertEqual([f['id'] for f in datos['lista']], [p3.id, p2.id, p1.id], 'el más reciente arriba')
        self.assertEqual((filas[p1.id]['primero'], filas[p1.id]['calculado']), (True, None))
        self.assertEqual((filas[p2.id]['calculado'], filas[p2.id]['monto'], filas[p2.id]['diferencia']),
                         (3.0, 3.05, 0.05))
        self.assertEqual((filas[p3.id]['calculado'], filas[p3.id]['monto'], filas[p3.id]['diferencia']),
                         (3.0, None, None))
        self.assertEqual(datos['desde_el_ultimo']['usd'], 1.2)
        self.assertIn('10 nov. 2026', filas[p3.id]['fecha_texto'])
        self.assertIn('10 de noviembre de 2026', datos['ultimo']['fecha_texto'])

    def test_con_el_worker_caido_o_sin_conectar_se_ven_los_pagos_sin_la_cifra(self):
        self.anotar(panama(2026, 11, 12, 9, 0), 7.5, monto=7.4)
        self.worker.rutas['GET', '/odoo/salud'] = requests.ConnectionError('sin red')
        with freeze_time(panama(2026, 11, 12, 10, 0)):
            r = self.panel.costos()
        self.assertFalse(r['ok'])
        self.assertEqual((r['pagos']['hay'], r['pagos']['desde_el_ultimo'], len(r['pagos']['lista'])), (True, None, 1))
        self.assertTrue(r['pagos']['ultimo'])
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}), \
                freeze_time(panama(2026, 11, 12, 10, 0)):
            r = self.panel.costos()
            self.assertFalse(r['configurado'])
            self.assertTrue(r['pagos']['hay'])
            # Sin Worker también se puede anotar (el corte sale de las fotos).
            self.assertFalse(self.panel.registrar_pago_ia()['exacto'])
