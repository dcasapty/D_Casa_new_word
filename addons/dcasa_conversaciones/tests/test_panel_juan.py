"""Resumen, Costos de IA y Conexiones: números honestos, sin cifras inventadas y sin filtrar ni un valor secreto."""
import json
import os
from datetime import date, datetime, timedelta
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import BaseCase, tagged

from ..models import panel_calculos as C
from .common import COSTOS, SALUD, TOKEN_WORKER, URL_WORKER, JuanCase, respuesta_http


def panama(anio, mes, dia, hora=0, minuto=0, segundo=0):
    """Una hora de Panamá (UTC−5) como UTC ingenuo, que es como guarda Odoo las fechas."""
    return datetime(anio, mes, dia, hora, minuto, segundo) + timedelta(hours=5)


# ----------------------------------------------------------------------------------------------------------------
# Cuentas puras
# ----------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestCalculos(BaseCase):

    def test_proyeccion_lineal_del_mes(self):
        # Día 11 a mediodía: han pasado 10,5 días y se gastaron 21 dólares → 2 por día → 62 en un mes de 31 días.
        self.assertEqual(C.proyeccion_del_mes(21.0, datetime(2026, 10, 11, 12, 0)), 62.0)
        # Último día, a las 12 de la noche: lo gastado es todo el mes.
        self.assertAlmostEqual(C.proyeccion_del_mes(30.0, datetime(2026, 10, 31, 23, 59, 59)), 30.0, delta=0.1)

    def test_antes_de_un_dia_de_datos_no_se_proyecta(self):
        self.assertIsNone(C.proyeccion_del_mes(5.0, datetime(2026, 10, 1, 20, 0)))
        self.assertIsNone(C.proyeccion_del_mes(0.0, datetime(2026, 10, 1, 0, 0)))

    def test_sin_gasto_la_proyeccion_es_cero(self):
        self.assertEqual(C.proyeccion_del_mes(0, datetime(2026, 10, 15, 10, 0)), 0.0)
        self.assertEqual(C.proyeccion_del_mes(None, datetime(2026, 10, 15, 10, 0)), 0.0)

    def test_estado_del_tope(self):
        self.assertEqual(C.estado_del_tope(5, 20, 0), 'sin_tope')
        self.assertEqual(C.estado_del_tope(30, 40, 30), 'alcanzado')
        self.assertEqual(C.estado_del_tope(10, 45, 30), 'en_riesgo')
        self.assertEqual(C.estado_del_tope(10, 25, 30), 'bien')
        self.assertEqual(C.estado_del_tope(10, None, 30), 'bien')

    def test_gasto_por_dia_es_la_resta_de_los_acumulados(self):
        fotos = {date(2026, 10, 1): 1.0, date(2026, 10, 2): 3.5, date(2026, 10, 3): 3.5, date(2026, 10, 5): 9.0,
                 date(2026, 9, 30): 40.0}
        self.assertEqual(C.gasto_por_dia(fotos, '2026-10'), [
            (date(2026, 10, 1), 1.0), (date(2026, 10, 2), 2.5), (date(2026, 10, 3), 0.0),
            (date(2026, 10, 5), None)])   # sin la foto del 4, el 5 no se adivina

    def test_gasto_por_dia_nunca_es_negativo(self):
        fotos = {date(2026, 10, 2): 5.0, date(2026, 10, 3): 4.0}
        self.assertEqual(C.gasto_por_dia(fotos, '2026-10')[1], (date(2026, 10, 3), 0.0))

    def test_mediana(self):
        self.assertIsNone(C.mediana([]))
        self.assertIsNone(C.mediana([None]))
        self.assertEqual(C.mediana([5]), 5)
        self.assertEqual(C.mediana([30, 10, 20]), 20)
        self.assertEqual(C.mediana([10, 20, 30, 40]), 25)

    def test_duracion_corta(self):
        self.assertEqual(C.duracion_corta(None), '—')
        self.assertEqual(C.duracion_corta(20), '20 s')
        self.assertEqual(C.duracion_corta(90), '1 min 30 s')
        self.assertEqual(C.duracion_corta(600), '10 min')
        self.assertEqual(C.duracion_corta(4000), '1 h 6 min')
        self.assertEqual(C.duracion_corta(3 * 86400), '3 d')

    def test_limites_del_periodo_son_a_medianoche_de_panama(self):
        ahora = datetime(2026, 10, 9, 13, 30)
        self.assertEqual(C.limites_del_periodo('hoy', ahora), (datetime(2026, 10, 9), datetime(2026, 10, 10)))
        self.assertEqual(C.limites_del_periodo('7_dias', ahora)[0], datetime(2026, 10, 3))
        self.assertEqual(C.limites_del_periodo('30_dias', ahora)[0], datetime(2026, 9, 10))
        with self.assertRaises(ValueError):
            C.limites_del_periodo('ayer', ahora)

    def test_la_direccion_que_el_puente_puede_bajar(self):
        buenas = ('https://dcasapty.com', 'https://www.dcasapty.com/x', 'https://dcasapty.workers.dev',
                  'https://dcasa-juan.dcasapty.workers.dev/a', 'https://dcasapty.com:443/a')
        malas = ('http://dcasapty.com', 'https://dcasapty.com.evil.com', 'https://evil.com/dcasapty.com',
                 'https://evildcasapty.com', 'https://user@dcasapty.com', 'https://dcasapty.com:8443/', '', None,
                 'ftp://dcasapty.com', 'https://127.0.0.1', 'https://dcasapty.com:abc/')
        for url in buenas:
            with self.subTest(url=url):
                self.assertTrue(C.url_descargable_por_el_puente(url))
        for url in malas:
            with self.subTest(url=url):
                self.assertFalse(C.url_descargable_por_el_puente(url))


# ----------------------------------------------------------------------------------------------------------------
# Resumen
# ----------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestResumen(JuanCase):

    AHORA = panama(2026, 10, 9, 13, 0)    # viernes 9 de octubre, 1:00 p. m. en Panamá

    def setUp(self):
        super().setUp()
        self.panel = self.env['dcasa.juan.panel'].with_user(self.vendedora)
        reloj = freeze_time(self.AHORA)
        reloj.start()
        self.addCleanup(reloj.stop)

    def hablan(self, id_externo, cliente_a=None, bot_a=None, vendedora_a=None, nombre=None):
        """El cliente escribe, el asistente contesta y, si se pide, una vendedora también. Horas de Panamá."""
        conv = None
        if cliente_a:
            conv = self.registrar('Hola, busco una cama', id_externo=id_externo, ts=cliente_a, nombre=nombre)[0]
        if bot_a:
            self.registrar('Claro, te cuento.', id_externo=id_externo, autor='bot', ts=bot_a)
        if vendedora_a:
            self.registrar('Te atiendo yo.', id_externo=id_externo, autor='vendedora', ts=vendedora_a)
        return conv

    def test_los_numeros_del_dia(self):
        a = self.hablan('50761000001', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 0, 20), nombre='Ana')
        self.hablan('50761000002', panama(2026, 10, 9, 10, 0), panama(2026, 10, 9, 10, 0, 40),
                    panama(2026, 10, 9, 10, 10), nombre='Beto')
        self.hablan('50761000003', panama(2026, 10, 9, 11, 0), None, nombre='Carla')
        self.registrar('Otra pregunta', id_externo='50761000001', ts=panama(2026, 10, 9, 12, 0))
        # Ayer: no cuenta para «hoy».
        self.hablan('50761000004', panama(2026, 10, 8, 9, 0), panama(2026, 10, 8, 9, 1), nombre='Diego')
        r = self.panel.resumen('hoy')
        self.assertEqual((r['periodo'], r['periodo_nombre']), ('hoy', 'Hoy'))
        self.assertEqual(r['mensajes'], {'total': 7, 'entrantes': 4, 'del_asistente': 2, 'de_vendedoras': 1})
        self.assertEqual(r['clientes_unicos'], 3, 'Ana escribió dos veces y cuenta una')
        self.assertEqual(r['conversaciones'], 3)
        self.assertEqual(r['resueltas_sin_humano'], 1,
                         'Solo la de Ana: a Beto lo atendió una persona y Carla no tuvo respuesta')
        self.assertEqual(a.estado, 'bot')

    def test_periodos(self):
        self.hablan('50761000001', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 1))
        self.hablan('50761000002', panama(2026, 10, 5, 9, 0), panama(2026, 10, 5, 9, 1))
        self.hablan('50761000003', panama(2026, 9, 20, 9, 0), panama(2026, 9, 20, 9, 1))
        self.assertEqual(self.panel.resumen('hoy')['clientes_unicos'], 1)
        self.assertEqual(self.panel.resumen('7_dias')['clientes_unicos'], 2)
        self.assertEqual(self.panel.resumen('30_dias')['clientes_unicos'], 3)
        with self.assertRaises(UserError):
            self.panel.resumen('ayer')

    def test_el_dia_es_el_de_panama_no_el_de_utc(self):
        # 8:30 p. m. del jueves en Panamá = 1:30 a. m. UTC del viernes: es de ayer.
        self.hablan('50761000001', panama(2026, 10, 8, 20, 30), None)
        # 7:00 p. m. de hoy ya pasó de la medianoche UTC... y sigue siendo de hoy.
        self.hablan('50761000002', panama(2026, 10, 9, 8, 0), None)
        self.assertEqual(self.panel.resumen('hoy')['clientes_unicos'], 1)

    def test_las_notas_y_los_avisos_no_cuentan_como_mensajes(self):
        conv = self.hablan('50761000001', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 1))
        self.env['dcasa.conversacion'].with_user(self.vendedora).agregar_nota(conv.id, 'nota')
        self.assertEqual(self.panel.resumen('hoy')['mensajes']['total'], 2)

    def test_oportunidades_creadas(self):
        conv = self.hablan('50761000001', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 1))
        self.hablan('50761000002', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 1))
        lead, _nueva = conv._oportunidad('Quiere una cama', interes='Cama queen')
        otra = self.env['crm.lead'].create({'name': 'Otra, sin conversación', 'type': 'opportunity'})
        # El reloj congelado no cambia el `now()` de PostgreSQL: se fecha a mano dentro del día de Panamá.
        self.env.cr.execute('UPDATE crm_lead SET create_date = %s WHERE id IN %s',
                            [panama(2026, 10, 9, 11, 0), (lead.id, otra.id)])
        self.env['crm.lead'].invalidate_model()
        self.assertEqual(self.panel.resumen('hoy')['oportunidades_creadas'], 1)

    def test_tiempo_de_primera_respuesta(self):
        self.hablan('50761000001', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 0, 20))
        self.hablan('50761000002', panama(2026, 10, 9, 10, 0), panama(2026, 10, 9, 10, 0, 40),
                    panama(2026, 10, 9, 10, 10))
        self.hablan('50761000003', panama(2026, 10, 9, 11, 0), None)
        primera = self.panel.resumen('hoy')['primera_respuesta']
        self.assertEqual(primera['conversaciones'], 3)
        self.assertEqual((primera['con_respuesta'], primera['cualquiera_seg']), (2, 30.0), 'Mediana de 20 s y 40 s')
        self.assertEqual(primera['cualquiera_texto'], '30 s')
        self.assertEqual((primera['con_respuesta_persona'], primera['persona_seg']), (1, 600.0))
        self.assertEqual(primera['persona_texto'], '10 min')

    def test_sin_conversaciones_no_se_inventan_tiempos(self):
        primera = self.panel.resumen('hoy')['primera_respuesta']
        self.assertEqual((primera['conversaciones'], primera['cualquiera_seg'], primera['cualquiera_texto']),
                         (0, None, '—'))

    def test_ventas_atribuidas_son_facturas_pagadas_de_clientes_que_hablaron_con_el_asistente(self):
        conv = self.hablan('50761000001', panama(2026, 10, 7, 9, 0), panama(2026, 10, 7, 9, 1), nombre='Ana')
        sin_bot = self.hablan('50761000002', panama(2026, 10, 7, 9, 0), None, nombre='Beto')
        sin_conversacion = self.env['res.partner'].create({'name': 'Zzcliente de la tienda'})
        pagada = self.factura(conv.partner_id, 100.0, pagar=True)
        self.factura(conv.partner_id, 50.0, pagar=False)                 # sin pagar: no cuenta
        self.factura(sin_bot.partner_id, 70.0, pagar=True)               # el asistente nunca le contestó
        self.factura(sin_conversacion, 30.0, pagar=True)                 # nunca habló con Juan
        r = self.panel.resumen('7_dias')['ventas']
        self.assertEqual((r['facturas'], r['monto']), (1, 100.0), 'Sin ITBMS')
        self.assertEqual(pagada.payment_state in ('paid', 'in_payment'), True)

    def test_una_factura_de_antes_de_que_el_asistente_hablara_no_se_le_atribuye(self):
        conv = self.hablan('50761000001', panama(2026, 10, 9, 9, 0), panama(2026, 10, 9, 9, 1))
        self.factura(conv.partner_id, 100.0, pagar=True, fecha=date(2026, 10, 3))
        self.assertEqual(self.panel.resumen('30_dias')['ventas']['facturas'], 0)

    def factura(self, partner, precio, pagar=True, fecha=None):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id, 'invoice_date': fecha or fields.Date.today(),
            'invoice_line_ids': [Command.create({'name': 'Cama', 'quantity': 1, 'price_unit': precio,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        if pagar:
            self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=factura.ids,
            ).create({'payment_date': factura.invoice_date})._create_payments()
        return factura

    def test_atencion_pendiente_y_estado_del_bot(self):
        conv = self.hablan('50761000001', panama(2026, 10, 9, 9, 0), None)
        conv.with_user(self.vendedora).action_atender()
        self.registrar('¿Me contestas?', id_externo='50761000001', ts=panama(2026, 10, 9, 12, 0))
        r = self.panel.resumen('hoy')
        self.assertEqual(r['necesitan_atencion'], 1)
        self.assertFalse(r['bot_conectado'])
        self.configurar_worker()
        self.assertTrue(self.panel.resumen('hoy')['bot_conectado'])

    def test_solo_el_equipo_de_ventas(self):
        for usuario in (self.interno, self.portal):
            with self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.juan.panel'], 'resumen', ['hoy'], {})


# ----------------------------------------------------------------------------------------------------------------
# Costos y Conexiones
# ----------------------------------------------------------------------------------------------------------------

class WorkerFalso:
    """Un Worker que contesta por ruta, para no salir a internet."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.llamadas = []

    def __call__(self, metodo, url, **kw):
        ruta = url.removeprefix(URL_WORKER)
        self.llamadas.append((metodo, ruta, kw))
        contestacion = self.rutas.get((metodo, ruta))
        if isinstance(contestacion, Exception):
            raise contestacion
        cuerpo, estado = contestacion if isinstance(contestacion, tuple) else (contestacion or {}, 200)
        return respuesta_http(cuerpo, estado)


@tagged('post_install', '-at_install')
class TestCostos(JuanCase):

    def setUp(self):
        super().setUp()
        self.panel = self.env['dcasa.juan.panel'].with_user(self.gerente)
        self.worker = WorkerFalso({('GET', '/odoo/salud'): SALUD, ('GET', '/odoo/costos'): COSTOS})
        self.configurar_worker()
        parche = patch('requests.request', side_effect=self.worker)
        parche.start()
        self.addCleanup(parche.stop)

    def test_el_gasto_el_tope_y_la_proyeccion(self):
        with freeze_time(panama(2026, 10, 11, 12, 0)):
            r = self.panel.costos()
        self.assertTrue(r['ok'])
        self.assertEqual((r['mes'], r['mes_nombre']), ('2026-10', 'octubre de 2026'))
        self.assertEqual((r['gasto_usd'], r['tope_usd'], r['porcentaje_del_tope']), (12.34, 30.0, 41.1))
        # 12,34 en 10,5 días → 1,1752/día → 36,43 en 31 días: pasa el tope de 30.
        self.assertAlmostEqual(r['proyeccion_usd'], 36.43, places=2)
        self.assertEqual((r['estado_del_tope'], r['tope_alcanzado']), ('en_riesgo', False))
        self.assertEqual((r['dia_del_mes'], r['dias_del_mes']), (11, 31))

    def test_por_modelo_de_mayor_a_menor(self):
        r = self.panel.costos()
        self.assertEqual([(m['modelo'], m['usd'], m['turnos']) for m in r['por_modelo']],
                         [('claude-sonnet-5-5', 9.9944, 21), ('claude-haiku-4-5', 2.3456, 300)])
        self.assertTrue(r['hay_detalle_por_modelo'])
        self.assertEqual(r['turnos'], 321)
        self.assertEqual(r['modelos_sin_precio'], ['muse-spark-1.3'])
        self.assertEqual(r['avisos'], ['el modelo x-contributor puede entrenar'])

    def test_si_el_worker_no_tiene_el_detalle_por_modelo_igual_hay_pantalla(self):
        self.worker.rutas[('GET', '/odoo/costos')] = ({'ok': False, 'error': 'no encontrado'}, 404)
        r = self.panel.costos()
        self.assertTrue(r['ok'])
        self.assertEqual((r['por_modelo'], r['hay_detalle_por_modelo']), ([], False))
        self.assertEqual(r['gasto_usd'], 12.34, 'El gasto sale de /odoo/salud')

    def test_cada_visita_deja_una_foto_y_con_ellas_se_arma_el_gasto_por_dia(self):
        Foto = self.env['dcasa.juan.costo.dia']
        with freeze_time(panama(2026, 10, 9, 12, 0)):
            self.worker.rutas[('GET', '/odoo/salud')] = {**SALUD, 'gasto_ia_mes_usd': 4.0}
            self.panel.costos()
        with freeze_time(panama(2026, 10, 10, 12, 0)):
            self.worker.rutas[('GET', '/odoo/salud')] = {**SALUD, 'gasto_ia_mes_usd': 6.5}
            r = self.panel.costos()
            self.panel.costos()    # otra visita el mismo día no duplica
        self.assertEqual(Foto.sudo().search_count([('mes', '=', '2026-10')]), 2)
        self.assertEqual(r['por_dia'], [{'fecha': '2026-10-09', 'usd': None}, {'fecha': '2026-10-10', 'usd': 2.5}])

    def test_dentro_del_dia_la_foto_solo_sube(self):
        Foto = self.env['dcasa.juan.costo.dia'].sudo()
        Foto._guardar(date(2026, 10, 9), 5.0)
        Foto._guardar(date(2026, 10, 9), 3.0)
        Foto._guardar(date(2026, 10, 9), 7.0)
        self.assertEqual(Foto.search([('fecha', '=', date(2026, 10, 9))]).acumulado_usd, 7.0)

    def test_el_cron_guarda_la_foto_del_dia(self):
        with freeze_time(panama(2026, 10, 9, 23, 50)):
            self.env['dcasa.juan.costo.dia']._cron_foto_diaria()
        foto = self.env['dcasa.juan.costo.dia'].sudo().search([('fecha', '=', date(2026, 10, 9))])
        self.assertEqual(foto.acumulado_usd, 12.34)

    def test_el_cron_no_falla_si_el_worker_no_responde(self):
        self.worker.rutas[('GET', '/odoo/salud')] = requests.ConnectionError('sin red')
        self.env['dcasa.juan.costo.dia']._cron_foto_diaria()
        self.assertFalse(self.env['dcasa.juan.costo.dia'].sudo().search([]))

    def test_tope_alcanzado(self):
        self.worker.rutas[('GET', '/odoo/salud')] = {**SALUD, 'gasto_ia_mes_usd': 31.0, 'tope_alcanzado': True}
        r = self.panel.costos()
        self.assertEqual((r['estado_del_tope'], r['tope_alcanzado']), ('alcanzado', True))

    def test_sin_tope(self):
        self.worker.rutas[('GET', '/odoo/salud')] = {**SALUD, 'tope_usd': 0}
        r = self.panel.costos()
        self.assertEqual((r['estado_del_tope'], r['porcentaje_del_tope']), ('sin_tope', None))

    def test_sin_el_worker_configurado_dice_falta_conectar_el_bot(self):
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            r = self.panel.costos()
        self.assertFalse(r['configurado'])
        self.assertEqual(r['mensaje'], 'Falta conectar el bot')
        self.assertEqual(r['faltan'], ['JUAN_URL', 'JUAN_WORKER_TOKEN'])
        self.assertNotIn(TOKEN_WORKER, json.dumps(r))

    def test_con_el_worker_caido_o_con_otra_clave_el_motivo_es_claro(self):
        self.worker.rutas[('GET', '/odoo/salud')] = requests.ConnectionError('sin red')
        r = self.panel.costos()
        self.assertEqual((r['configurado'], r['ok'], r['detalle']), (True, False, 'El Worker de Juan no responde.'))
        self.worker.rutas[('GET', '/odoo/salud')] = ({'ok': False, 'error': 'no autorizado'}, 401)
        self.assertIn('JUAN_WORKER_TOKEN', self.panel.costos()['detalle'])

    def test_solo_gerencia(self):
        for usuario in (self.vendedora, self.interno, self.portal):
            for metodo in ('costos', 'conexiones', 'qr', 'reiniciar_puente', 'desvincular_puente'):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.juan.panel'], metodo, [], {})


@tagged('post_install', '-at_install')
class TestConexiones(JuanCase):

    QR = 'data:image/png;base64,' + 'A' * 400

    def setUp(self):
        super().setUp()
        self.panel = self.env['dcasa.juan.panel'].with_user(self.gerente)
        self.worker = WorkerFalso({
            ('GET', '/odoo/salud'): SALUD,
            ('GET', '/odoo/qr'): {'ok': True, 'estado': 'necesita_qr', 'qr': self.QR, 'edad_s': 12},
            ('POST', '/odoo/reiniciar'): {'ok': True, 'mensaje': 'Reiniciando'},
            ('POST', '/odoo/desvincular'): {'ok': True}})
        self.configurar_worker()
        parche = patch('requests.request', side_effect=self.worker)
        parche.start()
        self.addCleanup(parche.stop)

    def test_el_estado_de_cada_canal_aunque_el_worker_diga_ok_false(self):
        r = self.panel.conexiones()
        self.assertTrue(r['ok'])
        self.assertFalse(r['todo_bien'])
        por_id = {c['id']: c for c in r['canales']}
        self.assertEqual(set(por_id), {'whatsapp_qr', 'whatsapp_cloud', 'telegram', 'messenger', 'instagram'})
        self.assertEqual((por_id['whatsapp_qr']['activo'], por_id['whatsapp_qr']['conectado'],
                          por_id['whatsapp_qr']['detalle']), (True, False, 'necesita_qr'))
        self.assertEqual(por_id['telegram']['faltan'], ['TELEGRAM_BOT_TOKEN_JUAN', 'TELEGRAM_WEBHOOK_SECRET_JUAN'])
        self.assertIsNone(por_id['telegram']['conectado'])
        self.assertEqual(por_id['whatsapp_cloud'], {
            'id': 'whatsapp_cloud', 'nombre': 'WhatsApp (API oficial)', 'activo': False, 'configurado': False,
            'conectado': None, 'detalle': None, 'faltan': []}, 'Un canal que el Worker no menciona sale apagado')
        self.assertEqual(r['secretos_faltantes'], ['META_AI_API_KEY'])
        self.assertEqual(r['ia']['claves_faltantes'], ['META_AI_API_KEY'])
        self.assertEqual((r['version'], r['entorno']), ('abc123', 'staging'))
        self.assertEqual(r['problemas'], ['falta META_AI_API_KEY'])

    def test_lo_que_odoo_sabe_de_si_mismo_son_solo_si_o_no(self):
        odoo = self.panel.conexiones()['odoo']
        self.assertEqual((odoo['url_del_worker'], odoo['token_del_worker']), (True, True))
        self.assertEqual(odoo['dominios_del_puente'], ['dcasapty.com', 'dcasapty.workers.dev'])
        self.assertIsInstance(odoo['direccion_de_odoo_sirve_al_puente'], bool)
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://dcasapty.com')
        self.assertTrue(self.panel.conexiones()['odoo']['direccion_de_odoo_sirve_al_puente'])
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'http://localhost:8069')
        self.assertFalse(self.panel.conexiones()['odoo']['direccion_de_odoo_sirve_al_puente'])

    def test_jamas_viaja_el_valor_de_un_secreto(self):
        enviado = json.dumps(self.panel.conexiones(), ensure_ascii=False)
        self.assertNotIn(TOKEN_WORKER, enviado)
        self.assertNotIn('Bearer', enviado)

    def test_sin_el_worker_configurado(self):
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            r = self.panel.conexiones()
        self.assertEqual((r['configurado'], r['mensaje'], r['canales']), (False, 'Falta conectar el bot', []))
        self.assertIn('odoo', r)
        with patch.dict(os.environ, {'JUAN_URL': URL_WORKER, 'JUAN_WORKER_TOKEN': ''}):
            self.assertEqual(self.panel.conexiones()['faltan'], ['JUAN_WORKER_TOKEN'])

    def test_el_qr_llega_como_imagen(self):
        r = self.panel.qr()
        self.assertEqual((r['ok'], r['estado'], r['qr'], r['edad_s']), (True, 'necesita_qr', self.QR, 12))

    def test_el_qr_nunca_se_escribe_en_los_registros(self):
        import logging
        with self.assertLogs(level=logging.DEBUG) as registro:
            logging.getLogger('odoo.addons.dcasa_conversaciones').warning('arranque')   # que assertLogs tenga algo
            self.panel.qr()
        self.assertNotIn('A' * 50, '\n'.join(registro.output))
        self.assertNotIn(self.QR, '\n'.join(registro.output))

    def test_solo_se_acepta_un_qr_que_sea_una_imagen_png(self):
        for malo in ('<script>alert(1)</script>', 'javascript:alert(1)', 'data:text/html;base64,AAAA',
                     'data:image/svg+xml;base64,AAAA', 'data:image/png;base64,' + 'A' * 300_000, 5, ['x']):
            with self.subTest(malo=str(malo)[:30]):
                self.worker.rutas[('GET', '/odoo/qr')] = {'ok': True, 'estado': 'necesita_qr', 'qr': malo}
                self.assertIsNone(self.panel.qr()['qr'])

    def test_con_la_sesion_conectada_no_hay_qr(self):
        self.worker.rutas[('GET', '/odoo/qr')] = {'ok': True, 'estado': 'conectado', 'qr': None}
        r = self.panel.qr()
        self.assertEqual((r['ok'], r['estado'], r['qr']), (True, 'conectado', None))

    def test_el_qr_sin_worker_o_con_el_worker_caido(self):
        self.worker.rutas[('GET', '/odoo/qr')] = requests.ConnectionError('sin red')
        self.assertEqual(self.panel.qr()['estado'], 'sin_respuesta')
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            self.assertEqual(self.panel.qr()['estado'], 'sin_conectar')

    def test_reiniciar_y_desvincular_dejan_historial_de_quien_lo_hizo(self):
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        antes = len(ajustes.message_ids)
        self.assertTrue(self.panel.reiniciar_puente()['ok'])
        self.assertTrue(self.panel.desvincular_puente()['ok'])
        cuerpos = ' '.join(ajustes.message_ids[:2].mapped('body'))
        self.assertEqual(len(ajustes.message_ids), antes + 2)
        self.assertIn('Gerente Prueba reinició el puente de WhatsApp', cuerpos)
        self.assertIn('Gerente Prueba desvinculó el número de WhatsApp', cuerpos)
        self.assertEqual([(m, r) for m, r, _kw in self.worker.llamadas if m == 'POST'],
                         [('POST', '/odoo/reiniciar'), ('POST', '/odoo/desvincular')])

    def test_si_el_puente_no_responde_no_se_anota_nada_y_el_error_es_claro(self):
        self.worker.rutas[('POST', '/odoo/reiniciar')] = ({'ok': False, 'error': 'el puente está apagado'}, 409)
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        antes = len(ajustes.message_ids)
        with self.assertRaises(UserError) as error:
            self.panel.reiniciar_puente()
        self.assertIn('el puente está apagado', str(error.exception))
        self.assertEqual(len(ajustes.message_ids), antes)
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}), self.assertRaises(UserError) as error:
            self.panel.desvincular_puente()
        self.assertIn('Falta conectar el bot', str(error.exception))
