"""Issue #25 (auditoría ronda 8, aprobado por la dueña el 2026-11-07): el seguimiento en Odoo.

* Un seguimiento muy atrasado (el sistema estuvo detenido, un despliegue, el asistente apagado) no sale de golpe días
  después.
* A quien Juan pasó a una persona y nadie atendió no le llega «¿sigues interesado?»: espera a una persona.
* El seguimiento es por PERSONA (su ficha), no por conversación; «No contactar» sigue a la persona si su conversación
  cambia de ficha.
* Un aviso tardío del Worker no cierra el ciclo que el cliente acaba de reiniciar.
* Notas repetidas en la oportunidad, borradores de Telegram viejos y la zona que no es una dirección exacta.
"""
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from ..models import crm_reglas as R
from .common import respuesta_http
from .test_crm_automatico import CrmCase
from .test_seguimiento import SeguimientoCase, panama


class Ronda8Case(SeguimientoCase):

    def setUp(self):
        super().setUp()
        self.llamadas = self.configurar_worker()

    def llamadas_a(self, ruta):
        return [c for c in self.llamadas.call_args_list if c.args[1].endswith(ruta)]

    def notas(self, registro):
        return [m.body or '' for m in registro.message_ids]


# ----------------------------------------------------------------------
# 7. Lo atrasado no sale de golpe
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSeguimientoAtrasado(Ronda8Case):

    def test_viene_en_seis_horas_y_es_un_ajuste_con_limites(self):
        self.assertEqual(self.ajustes.seguimiento_atraso_maximo_horas, 6)
        for malo in (-1, 73):
            with self.subTest(horas=malo), self.assertRaises(ValidationError):
                self.ajustes.seguimiento_atraso_maximo_horas = malo

    def test_un_seguimiento_vencido_hace_dias_no_sale_y_se_salta(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)          # tocaba el 9 a las 2:05 p. m.
        with freeze_time(panama(2026, 10, 12, 10, 0)):              # el sistema estuvo detenido tres días
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertFalse(self.llamadas_a('/odoo/seguimiento'), 'No se le escribe tres días tarde')
        self.assertEqual(conv.seguimientos_enviados, 1, 'El 1.º se da por pasado (no se envió)')
        self.assertTrue(any('no se envió' in n and 'atrasó' in n for n in self.notas(conv)))
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 14, 9, 5),
                         'El 2.º sigue a los 5 días del último mensaje')

    def test_un_atraso_corto_sale_igual(self):
        self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 16, 30)):              # dos horas y media tarde: un despliegue
            self.assertEqual(self.Conversacion._cron_seguimientos(), 1)
        self.assertEqual(len(self.llamadas_a('/odoo/seguimiento')), 1)

    def test_con_el_ajuste_en_cero_sale_aunque_vaya_atrasado(self):
        self.ajustes.seguimiento_atraso_maximo_horas = 0
        self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 12, 10, 0)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 1)

    def test_tras_volver_a_encender_al_asistente_no_salen_todos_los_viejos(self):
        convs = [self.pregunta_y_bot_contesta(hora_panama=9, id_externo=f'5076123{n:04d}') for n in range(3)]
        self.ajustes.bot_activo_global = False
        with freeze_time(panama(2026, 10, 10, 10, 0)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.ajustes.bot_activo_global = True
        with freeze_time(panama(2026, 10, 10, 10, 15)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertFalse(self.llamadas_a('/odoo/seguimiento'))
        self.assertTrue(all(c.seguimientos_enviados == 1 for c in convs))


# ----------------------------------------------------------------------
# 8. Traspaso sin atender: espera a una persona
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestTraspasoSinAtender(Ronda8Case):

    def pasada_a_una_persona(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 9, 6)):
            conv._pasar_a_vendedora('El cliente pidió hablar con una persona.')
            self.registrar('Listo, ya avisé a una vendedora para que te atienda por aquí.', autor='bot',
                           ts=panama(2026, 10, 9, 9, 6))
        return conv

    def test_si_la_pausa_vence_sin_que_nadie_atienda_no_hay_seguimiento(self):
        conv = self.pasada_a_una_persona()
        self.assertTrue(conv.traspaso_sin_atender_desde)
        with freeze_time(panama(2026, 10, 9, 11, 30)):              # vencen las 2 horas: vuelve al asistente
            self.Conversacion._cron_mantenimiento()
        self.assertEqual(conv.estado, 'bot')
        self.assertFalse(conv.seguimiento_proximo)
        self.assertIn('espera a una persona', conv._motivo_sin_seguimiento())
        with freeze_time(panama(2026, 10, 9, 16, 30)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertFalse(self.llamadas_a('/odoo/seguimiento'), 'Nada de «¿sigues interesado?» a quien espera')

    def test_si_una_vendedora_le_escribe_vuelve_el_seguimiento_normal(self):
        conv = self.pasada_a_una_persona()
        self.registrar('Hola, soy Ana. ¿Para cuándo la necesitas?', autor='vendedora', ts=panama(2026, 10, 9, 9, 30))
        self.assertFalse(conv.traspaso_sin_atender_desde)
        conv._devolver(self.vendedora)
        self.registrar('¿Algo más en que te ayude?', autor='bot', ts=panama(2026, 10, 9, 9, 40))
        self.assertTrue(conv.seguimiento_proximo)

    def test_si_le_escribe_desde_odoo_tambien_cuenta_como_atendida(self):
        conv = self.pasada_a_una_persona()
        conv.with_user(self.vendedora)._crear_mensaje_de_odoo('Hola, te atiendo yo.', usuario=self.vendedora)
        self.assertFalse(conv.traspaso_sin_atender_desde)

    def test_devolverla_o_cerrarla_es_una_decision_de_una_persona(self):
        conv = self.pasada_a_una_persona()
        conv._devolver(self.vendedora)
        self.assertFalse(conv.traspaso_sin_atender_desde)
        otra = self.pregunta_y_bot_contesta(hora_panama=9, id_externo='50761239999')
        otra._pasar_a_vendedora('Pidió una persona.')
        otra._cerrar(self.vendedora)
        self.assertFalse(otra.traspaso_sin_atender_desde)

    def test_que_el_cliente_vuelva_a_escribir_no_lo_borra(self):
        conv = self.pasada_a_una_persona()
        self.registrar('¿Hola? ¿Alguien?', ts=panama(2026, 10, 9, 10, 0))
        self.assertTrue(conv.traspaso_sin_atender_desde, 'Sigue esperando a una persona')


# ----------------------------------------------------------------------
# 9. Por persona, no por conversación
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSeguimientoPorPersona(Ronda8Case):

    def dos_canales(self):
        """La misma persona por WhatsApp (9:00) y por Telegram (9:30, con su celular): una sola ficha."""
        wa = self.pregunta_y_bot_contesta(hora_panama=9)
        tg = self.conversacion('Hola, sigo por aquí', canal='telegram', id_externo='777001',
                               celular='+50761234567', ts=panama(2026, 10, 9, 9, 30))
        self.registrar('Claro, te ayudo por aquí.', autor='bot', canal='telegram', id_externo='777001',
                       ts=panama(2026, 10, 9, 9, 35))
        tg._oportunidad('Busca una cama queen', interes='camas queen')
        self.assertEqual(wa.partner_id, tg.partner_id)
        return wa, tg

    def test_solo_el_canal_por_donde_escribio_ultimo_hace_el_seguimiento(self):
        wa, tg = self.dos_canales()
        self.assertIn('otro canal', wa._motivo_sin_seguimiento())
        self.assertIsNone(tg._motivo_sin_seguimiento())
        with freeze_time(panama(2026, 10, 9, 14, 40)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 1)
        (llamada,) = self.llamadas_a('/odoo/seguimiento')
        self.assertEqual(llamada.kwargs['json']['canal'], 'telegram')

    def test_los_seguimientos_de_sus_otros_canales_cuentan(self):
        wa, tg = self.dos_canales()
        # Uno que salió por WhatsApp después de su último mensaje (antes de esta regla): cuenta para la persona.
        wa.sudo().write({'seguimientos_enviados': 1, 'ultimo_seguimiento_en': panama(2026, 10, 9, 14, 5)})
        tg.sudo().write({'seguimientos_enviados': 1, 'ultimo_seguimiento_en': panama(2026, 10, 9, 14, 40)})
        self.assertIn('otros canales', tg._motivo_sin_seguimiento())

    def test_si_otro_canal_ya_tiene_uno_en_camino_no_se_pide_otro(self):
        wa, tg = self.dos_canales()
        wa.sudo().write({'seguimiento_pedido_en': panama(2026, 10, 9, 14, 6), 'seguimiento_numero_pedido': 1})
        self.assertIn('en camino', tg._motivo_sin_seguimiento())

    def test_no_contactar_sigue_a_la_persona_cuando_su_conversacion_cambia_de_ficha(self):
        wa = self.pregunta_y_bot_contesta(hora_panama=9)
        tg = self.conversacion('ya no me escriban más', canal='telegram', id_externo='777002',
                               ts=panama(2026, 10, 9, 9, 30))
        provisional = tg.partner_id
        self.assertNotEqual(provisional, wa.partner_id)
        self.assertTrue(provisional.dcasa_no_contactar)
        # Telegram da después su celular: la conversación pasa a la ficha de siempre.
        self.registrar('Mi celular es este', canal='telegram', id_externo='777002', celular='+50761234567',
                       ts=panama(2026, 10, 9, 9, 40))
        self.assertEqual(tg.partner_id, wa.partner_id)
        self.assertTrue(wa.partner_id.dcasa_no_contactar, '«No contactar» no se queda en la ficha provisional')
        self.assertIn('pidió que no lo contacten', wa._motivo_sin_seguimiento())

    def test_tambien_si_una_vendedora_elige_la_ficha_correcta(self):
        wa = self.pregunta_y_bot_contesta(hora_panama=9)
        tg = self.conversacion('no me escriban', canal='telegram', id_externo='777003', ts=panama(2026, 10, 9, 9, 30))
        tg.with_user(self.vendedora).write({'partner_id': wa.partner_id.id})
        self.assertTrue(wa.partner_id.dcasa_no_contactar)

    def test_una_ficha_que_no_era_de_juan_no_le_pasa_su_marca_a_otra(self):
        """Si una vendedora corrige una conversación mal ligada a la ficha de OTRA persona, la marca de esa otra persona
        no viaja: solo la provisional que Juan creó para esta conversación es de la misma persona."""
        ajena = self.Partner.create({'name': 'Otra Persona', 'dcasa_no_contactar': True})
        correcta = self.Partner.create({'name': 'La Correcta'})
        conv = self.conversacion('hola', canal='telegram', id_externo='777004')
        conv.sudo().write({'partner_id': ajena.id})
        conv.with_user(self.vendedora).write({'partner_id': correcta.id})
        self.assertFalse(correcta.dcasa_no_contactar)


# ----------------------------------------------------------------------
# 10. Un «hecho» tardío no cierra el ciclo nuevo
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestHechoTardio(Ronda8Case):

    def test_un_descartado_tardio_no_cierra_el_ciclo_que_el_cliente_reinicio(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
        self.registrar('Perdón, sí la quiero', ts=panama(2026, 10, 9, 14, 12))      # reinicia el ciclo
        with freeze_time(panama(2026, 10, 9, 14, 13)):
            resultado = conv._seguimiento_hecho(1, 'descartado', 'el cliente ya volvió a escribir')
        self.assertTrue(resultado.get('repetido'))
        self.assertEqual(conv.seguimientos_enviados, 0)
        with freeze_time(panama(2026, 10, 9, 14, 14)):
            self.registrar('¡Genial! ¿Para cuándo la quieres?', autor='bot', ts=panama(2026, 10, 9, 14, 14))
        self.assertTrue(conv.seguimiento_proximo, 'El ciclo nuevo tiene su seguimiento')

    def test_un_descartado_tardio_por_no_contactar_se_honra_igual(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        self.registrar('Perdón, estaba ocupada', ts=panama(2026, 10, 9, 14, 12))
        self.assertFalse(conv.partner_id.dcasa_no_contactar)
        with freeze_time(panama(2026, 10, 9, 14, 13)):
            conv._seguimiento_hecho(1, 'descartado', 'no_contactar')
        self.assertTrue(conv.partner_id.dcasa_no_contactar)

    def test_un_enviado_tardio_cuando_odoo_no_oyo_la_respuesta_si_cuenta(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        self.llamadas.return_value = respuesta_http({'ok': False, 'error': 'plazo vencido'}, 504)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
        self.assertFalse(conv.seguimiento_pedido_en)
        with freeze_time(panama(2026, 10, 9, 14, 11)):
            conv._seguimiento_hecho(1, 'enviado')
        self.assertEqual(conv.seguimientos_enviados, 1)


# ----------------------------------------------------------------------
# 11. Notas que no se repiten
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestNotasSinRepetir(CrmCase):

    def test_crear_oportunidad_con_lo_mismo_no_repite_la_nota(self):
        lead = self.lead()
        self.lead()
        self.lead()
        self.assertEqual(len([n for n in self.nombres_de_notas(lead) if 'Quiere una cama queen' in n]), 1)
        self.lead(resumen='Ahora quiere también un colchón')
        self.assertEqual(len([n for n in self.nombres_de_notas(lead) if 'colchón' in n]), 1, 'Lo nuevo sí queda')

    def test_una_temperatura_que_oscila_no_llena_la_ficha_de_notas(self):
        lead = self.lead()
        vaiven = [(R.TIBIO, 'dijo para cuándo lo quiere'), (R.CALIENTE, 'pidió cotización')] * 3
        with patch.object(R, 'temperatura', side_effect=vaiven):
            for _ in vaiven:
                lead._dcasa_recalcular_temperatura()
        notas = [n for n in self.nombres_de_notas(lead) if 'Temperatura' in n]
        self.assertEqual(len([n for n in notas if 'tibio' in n]), 1)
        self.assertEqual(len([n for n in notas if 'caliente' in n]), 1)


# ----------------------------------------------------------------------
# 12. Borradores de Telegram viejos
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestBorradoresViejos(Ronda8Case):

    def test_el_mantenimiento_borra_los_borradores_vencidos(self):
        conv = self.conversacion('Hola')
        Borrador = self.env['dcasa.telegram_borrador'].sudo()
        viejo = Borrador.create({'user_id': self.vendedora.id, 'conversacion_id': conv.id, 'texto': 'Hola',
                                 'vence': fields.Datetime.now() - timedelta(hours=1)})
        vigente = Borrador.create({'user_id': self.vendedora.id, 'conversacion_id': conv.id, 'texto': 'Hola',
                                   'vence': fields.Datetime.now() + timedelta(minutes=10)})
        self.Conversacion._cron_mantenimiento()
        self.assertFalse(viejo.exists())
        self.assertTrue(vigente.exists())


# ----------------------------------------------------------------------
# 13. La zona no es una dirección exacta
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestZonaSinDireccionExacta(CrmCase):

    def test_reconoce_una_direccion_exacta(self):
        for exacta in ('Calle 5, casa 23, Barrio Balboa', 'Edificio Las Palmas, apto 4B', 'Mz 3 lote 12',
                       'Barrio Colón casa #45', 'Torre 2, piso 14', 'Calle 50 #12-30', 'Apartamento 7, Arraiján'):
            with self.subTest(zona=exacta):
                self.assertTrue(R.parece_direccion_exacta(exacta))
        for zona in ('La Chorrera', 'Arraiján, Vista Alegre', 'Calle 50', 'Costa del Este', 'Panamá Oeste',
                     'Barrio Balboa', 'Vía España', 'Torres de Alba', 'Cerca del Parque Libertadores'):
            with self.subTest(zona=zona):
                self.assertFalse(R.parece_direccion_exacta(zona))

    def test_una_direccion_exacta_no_se_guarda_ni_queda_en_una_nota(self):
        lead = self.lead(zona='Barrio Colón, calle 3, casa 45')
        self.assertFalse(lead.dcasa_zona_entrega)
        self.assertFalse(any('casa 45' in n for n in self.nombres_de_notas(lead)))
        lead = self.lead(zona='Barrio Colón')
        self.assertEqual(lead.dcasa_zona_entrega, 'Barrio Colón')
