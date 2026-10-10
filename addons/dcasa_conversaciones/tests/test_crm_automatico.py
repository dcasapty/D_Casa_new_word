"""El CRM que se ajusta solo, con Odoo de verdad (``models/crm_lead.py``; diseño en docs/CRM_AUTOMATICO.md).

Cada regla se prueba con el escenario que la rompería: la vendedora que mueve la etapa a mano, la factura sin pagar, el
error en una oportunidad, la etapa que la dueña borró, el interruptor apagado.
"""
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import ConcurrencyError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.misc import file_path

from ..models import crm_reglas as R
from ..models.crm_lead import ETAPA_COTIZADA
from .test_cotizacion_automatica import RENDER, CotizarCase
from .test_panel_catalogo import CatalogoCase

AHORA = '2026-10-09 16:00:00'   # una hora después del mensaje de prueba (2026-10-09 15:00)


class CrmCase(CotizarCase):
    """Una conversación con su cliente, productos publicados (Zz…) y el PDF simulado."""

    def lead(self, **extra):
        datos = self.salida('crear_oportunidad', {'resumen': 'Quiere una cama queen', 'interes': 'Cama queen', **extra})
        return self.env['crm.lead'].browse(datos['oportunidad_id'])

    def etapa(self, xmlid):
        return self.env.ref(xmlid)

    def nombres_de_notas(self, lead):
        return [(m.body or '') for m in lead.message_ids]

    def factura_pagada(self, orden):
        """Una factura del cliente, ligada a las líneas de la cotización y pagada."""
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': orden.partner_id.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({
                'name': 'Cama', 'quantity': 1, 'price_unit': 100.0, 'tax_ids': [Command.clear()],
                'sale_line_ids': [Command.set(orden.order_line.ids)]})]})
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'payment_date': factura.invoice_date})._create_payments()
        return factura

    def orden_enviada(self, lead, confirmar=False):
        orden = self.env['sale.order'].create({
            'partner_id': lead.partner_id.id, 'opportunity_id': lead.id,
            'order_line': [Command.create({'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        orden.action_quotation_sent()
        if confirmar:
            orden.action_confirm()
        return orden


@tagged('post_install', '-at_install')
class TestDatosQueDijoElCliente(CrmCase):

    def test_la_zona_y_el_para_cuando_se_anotan_con_lo_que_dijo_el_cliente(self):
        lead = self.lead(zona='La Chorrera, Barrio Balboa', cuando='este fin de semana')
        self.assertEqual(lead.dcasa_zona_entrega, 'La Chorrera, Barrio Balboa')
        self.assertEqual(lead.dcasa_para_cuando, 'este fin de semana')

    def test_si_llegan_despues_en_otra_llamada_tambien_se_anotan(self):
        lead = self.lead()
        self.assertFalse(lead.dcasa_zona_entrega)
        self.lead(zona='Arraiján')
        self.assertEqual(lead.dcasa_zona_entrega, 'Arraiján')
        self.assertEqual(self.env['crm.lead'].search_count([('partner_id', '=', lead.partner_id.id)]), 1)

    def test_nunca_pisa_lo_que_ya_tiene_valor_y_deja_una_nota(self):
        lead = self.lead(zona='Arraiján')
        self.lead(zona='Chame')
        self.assertEqual(lead.dcasa_zona_entrega, 'Arraiján')
        self.assertTrue(any('Chame' in nota and 'Arraiján' in nota for nota in self.nombres_de_notas(lead)))

    def test_lo_que_escribio_una_persona_tampoco_se_pisa(self):
        lead = self.lead()
        lead.with_user(self.vendedora).write({'dcasa_para_cuando': 'el 20 de octubre'})
        self.lead(cuando='mañana')
        self.assertEqual(lead.dcasa_para_cuando, 'el 20 de octubre')

    def test_el_mismo_dato_con_otras_mayusculas_no_hace_ruido(self):
        lead = self.lead(zona='Arraiján')
        antes = len(lead.message_ids)
        self.lead(zona='ARRAIJÁN')
        self.assertEqual(lead.dcasa_zona_entrega, 'Arraiján')
        self.assertEqual(len(lead.message_ids) - antes, 1, 'solo la nota del resumen, ninguna de «difiere»')

    def test_texto_plano_de_una_linea_y_con_tope(self):
        lead = self.lead(zona='x' * 300, cuando='  pronto \n por favor ')
        self.assertEqual(len(lead.dcasa_zona_entrega), R.MAX_TEXTO_DATO)
        self.assertEqual(lead.dcasa_para_cuando, 'pronto por favor')

    def test_lo_que_no_es_texto_es_un_error_que_el_modelo_puede_corregir(self):
        self.assertIn('es texto', self.error('crear_oportunidad', {
            'resumen': 'x', 'interes': 'y', 'zona': {'distrito': 'Chame'}}))
        self.assertIn('es texto', self.error('crear_oportunidad', {
            'resumen': 'x', 'interes': 'y', 'cuando': 5}))

    def test_basura_se_ignora(self):
        lead = self.lead(zona='---', cuando='   ')
        self.assertFalse(lead.dcasa_zona_entrega or lead.dcasa_para_cuando)

    def test_el_contrato_de_la_herramienta_sigue_dentro_de_cinco_parametros(self):
        catalogo = {t['name']: t for t in self.env['brian.herramientas'].with_user(self.juan).catalogo()}
        esquema = catalogo['juan_crear_oportunidad']['input_schema']
        self.assertEqual(sorted(esquema['properties']), ['cuando', 'interes', 'presupuesto', 'resumen', 'zona'])
        self.assertEqual(esquema['required'], ['resumen', 'interes'])
        self.assertTrue(all(p['type'] in ('string', 'number') for p in esquema['properties'].values()))


@tagged('post_install', '-at_install')
class TestTemperaturaAlInstante(CrmCase):

    @freeze_time(AHORA)
    def test_cada_hecho_sube_la_temperatura_y_la_ficha_dice_por_que(self):
        lead = self.lead()
        self.assertEqual(lead.dcasa_temperatura, R.FRIO, 'solo escribió hace poco: 1 punto')
        lead = self.lead(cuando='esta semana')
        self.assertEqual(lead.dcasa_temperatura, R.TIBIO, 'para cuándo (2) + escribió hace poco (1)')
        self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 1})
        self.assertEqual(lead.dcasa_temperatura, R.CALIENTE)
        self.assertIn('pidió cotización', lead.dcasa_temperatura_motivo)
        self.assertIn('dijo para cuándo lo quiere', lead.dcasa_temperatura_motivo)

    @freeze_time(AHORA)
    def test_solo_deja_nota_cuando_cambia_el_nivel(self):
        lead = self.lead()
        notas = len([n for n in self.nombres_de_notas(lead) if 'Temperatura' in n])
        self.assertEqual(notas, 1)
        lead._dcasa_recalcular_temperatura()
        lead._dcasa_recalcular_temperatura()
        self.assertEqual(len([n for n in self.nombres_de_notas(lead) if 'Temperatura' in n]), 1)

    @freeze_time(AHORA)
    def test_con_el_interruptor_apagado_no_se_calcula(self):
        self.ajustes.crm_automatico = False
        self.assertFalse(self.lead().dcasa_temperatura)


@tagged('post_install', '-at_install')
class TestCotizarLigaYAvanza(CrmCase):

    @freeze_time(AHORA)
    def test_pedir_una_cotizacion_crea_la_oportunidad_y_la_liga(self):
        self.assertFalse(self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)]))
        self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 2})
        (lead,) = self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)])
        (orden,) = self.ordenes()
        self.assertEqual(orden.opportunity_id, lead)
        self.assertEqual(self.conv.oportunidad_id, lead)
        self.assertEqual(lead.type, 'opportunity')
        self.assertIn('Zzsofa Gris', lead.name)
        self.assertEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA), 'enviada → «Propuesta»')
        self.assertTrue(any('automático' in nota and orden.name in nota for nota in self.nombres_de_notas(lead)))

    @freeze_time(AHORA)
    def test_si_ya_habia_oportunidad_abierta_se_usa_esa(self):
        lead = self.lead()
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(self.ordenes().opportunity_id, lead)
        self.assertEqual(self.env['crm.lead'].search_count([('partner_id', '=', lead.partner_id.id)]), 1)

    @freeze_time(AHORA)
    def test_la_misma_cotizacion_pedida_otra_vez_no_duplica_ni_retrocede(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (lead,) = self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)])
        otra = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertTrue(otra['reutilizada'])
        self.assertEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))
        self.assertEqual(len(self.ordenes()), 1)

    @freeze_time(AHORA)
    def test_con_el_crm_apagado_la_cotizacion_se_liga_pero_nada_se_mueve(self):
        self.ajustes.crm_automatico = False
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (lead,) = self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)])
        self.assertEqual(self.ordenes().opportunity_id, lead, 'ligar es orden de datos: no depende del interruptor')
        self.assertNotEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))
        self.assertFalse(lead.dcasa_temperatura)

    @freeze_time(AHORA)
    @mute_logger('odoo.addons.dcasa_conversaciones.models.conversacion')
    def test_un_fallo_al_ligar_no_tumba_la_cotizacion(self):
        with patch.object(type(self.conv), '_oportunidad', side_effect=RuntimeError('se cayó el CRM')):
            datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertTrue(datos['creada'])
        (orden,) = self.ordenes()
        self.assertFalse(orden.opportunity_id)
        self.assertEqual(orden.state, 'sent')

    @freeze_time(AHORA)
    @mute_logger('odoo.addons.dcasa_conversaciones.models.crm_lead')
    def test_un_fallo_al_mover_la_etapa_tampoco_tumba_la_cotizacion(self):
        with patch.object(type(self.env['crm.lead']), '_dcasa_avanzar_a_cotizada', side_effect=RuntimeError('boom')):
            datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertTrue(datos['creada'])
        self.assertTrue(self.ordenes().opportunity_id, 'la oportunidad sí quedó ligada')

    @freeze_time(AHORA)
    @mute_logger('odoo.addons.dcasa_conversaciones.models.crm_lead')
    def test_la_etapa_que_la_duena_borro_no_rompe_nada(self):
        with patch('odoo.addons.dcasa_conversaciones.models.crm_lead.ETAPA_COTIZADA', 'crm.etapa_que_no_existe'):
            datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertTrue(datos['creada'])
        (lead,) = self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)])
        self.assertNotEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))

    @freeze_time(AHORA)
    def test_nunca_retrocede_de_una_etapa_posterior(self):
        lead = self.lead()
        posterior = self.env['crm.stage'].create({'name': 'Zzvisita', 'sequence': 50})
        lead.sudo().with_context(dcasa_auto=True).write({'stage_id': posterior.id})
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(lead.stage_id, posterior)


@tagged('post_install', '-at_install')
class TestCotizacionDeLaVendedora(CatalogoCase):
    """La cotización que se hace con el botón «Cotización» de la pantalla también queda ligada."""

    def setUp(self):
        super().setUp()
        self.partner = self.conv.partner_id

    def crear(self):
        resultado = self.panel.crear_cotizacion(self.conv.id, [
            {'variante_id': self.sofa.product_variant_id.id, 'cantidad': 1}])
        return self.env['sale.order'].browse(resultado['cotizacion']['id'])

    def enviar(self, orden):
        with patch('odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf',
                   return_value=(b'%PDF-1.4 prueba', 'pdf')):
            return self.panel.enviar_cotizacion(self.conv.id, orden.id)

    def test_al_crear_el_borrador_queda_ligada_pero_la_etapa_espera_al_envio(self):
        orden = self.crear()
        lead = orden.opportunity_id
        self.assertTrue(lead)
        self.assertEqual(self.conv.oportunidad_id, lead)
        self.assertNotEqual(lead.stage_id, self.env.ref(ETAPA_COTIZADA), 'un borrador no es una propuesta')

    def test_al_enviarla_pasa_a_propuesta(self):
        orden = self.crear()
        self.enviar(orden)
        self.assertEqual(orden.opportunity_id.stage_id, self.env.ref(ETAPA_COTIZADA))
        self.assertEqual(orden.state, 'sent')

    def test_una_cotizacion_sin_ligar_se_liga_al_enviarla(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.partner.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        self.assertFalse(orden.opportunity_id)
        self.enviar(orden)
        self.assertTrue(orden.opportunity_id)
        self.assertEqual(orden.opportunity_id.stage_id, self.env.ref(ETAPA_COTIZADA))


@tagged('post_install', '-at_install')
class TestElCronAjustaSolo(CrmCase):

    def cron(self):
        return self.env['crm.lead']._dcasa_cron_crm()

    @freeze_time(AHORA)
    def test_gana_cuando_se_paga_la_factura_de_una_cotizacion_ligada(self):
        lead = self.lead()
        orden = self.orden_enviada(lead, confirmar=True)
        self.factura_pagada(orden)
        resumen = self.cron()
        self.assertEqual(resumen.get('ganada'), 1)
        self.assertEqual(lead.won_status, 'won')
        self.assertTrue(lead.stage_id.is_won)
        self.assertTrue(any('Ganada' in nota and orden.name in nota for nota in self.nombres_de_notas(lead)))
        self.assertFalse(lead.dcasa_auto_off, 'ganarla sola no es «una persona tomó el control»')

    @freeze_time(AHORA)
    def test_confirmada_sin_pagar_no_es_ganada_es_un_apartado(self):
        lead = self.lead()
        self.orden_enviada(lead, confirmar=True)
        self.cron()
        self.assertEqual(lead.won_status, 'pending')
        self.assertEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))

    @freeze_time(AHORA)
    def test_la_factura_de_otra_cosa_del_mismo_cliente_no_la_gana(self):
        lead = self.lead()
        self.orden_enviada(lead, confirmar=True)
        otra = self.env['sale.order'].create({
            'partner_id': lead.partner_id.id,
            'order_line': [Command.create({'product_id': self.sofa.product_variant_id.id, 'product_uom_qty': 1})]})
        otra.action_confirm()
        self.factura_pagada(otra)
        self.cron()
        self.assertEqual(lead.won_status, 'pending')

    @freeze_time(AHORA)
    def test_el_cron_es_idempotente(self):
        lead = self.lead(cuando='esta semana')
        self.orden_enviada(lead)
        primera = self.cron()
        notas = len(lead.message_ids)
        segunda = self.cron()
        self.assertTrue(primera)
        self.assertEqual(segunda, {})
        self.assertEqual(len(lead.message_ids), notas, 'sin cambios no se escribe nada')

    @freeze_time(AHORA)
    def test_las_cotizaciones_hechas_por_otro_camino_tambien_se_deducen(self):
        lead = self.lead()
        self.orden_enviada(lead)
        self.assertNotEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))
        self.cron()
        self.assertEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))

    @freeze_time(AHORA)
    def test_con_el_interruptor_apagado_el_cron_no_hace_nada(self):
        lead = self.lead()
        self.orden_enviada(lead)
        self.ajustes.crm_automatico = False
        self.assertEqual(self.cron(), {})
        self.assertNotEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))

    @freeze_time(AHORA)
    def test_solo_maneja_oportunidades_que_nacieron_de_una_conversacion(self):
        ajena = self.env['crm.lead'].create({'name': 'Oportunidad de la vendedora', 'type': 'opportunity',
                                             'partner_id': self.conv.partner_id.id})
        self.orden_enviada(ajena)
        self.cron()
        self.assertFalse(ajena.dcasa_temperatura)
        self.assertNotEqual(ajena.stage_id, self.etapa(ETAPA_COTIZADA))

    @freeze_time(AHORA)
    @mute_logger('odoo.addons.dcasa_conversaciones.models.crm_lead')
    def test_un_error_en_una_oportunidad_no_frena_a_las_demas(self):
        primera = self.lead()
        otro = self.conversacion(nombre='Ana', id_externo='50769990000')
        segunda = self.salida('crear_oportunidad', {'resumen': 'Quiere un sofá', 'interes': 'Sofá'}, conv=otro)
        segunda = self.env['crm.lead'].browse(segunda['oportunidad_id'])
        self.orden_enviada(primera)
        self.orden_enviada(segunda)
        original = type(primera)._dcasa_avanzar_a_cotizada

        def falla_en_la_primera(lead, orden=None):
            if lead == primera:
                raise RuntimeError('boom')
            return original(lead, orden)

        with patch.object(type(primera), '_dcasa_avanzar_a_cotizada', falla_en_la_primera):
            self.cron()
        self.assertNotEqual(primera.stage_id, self.etapa(ETAPA_COTIZADA))
        self.assertEqual(segunda.stage_id, self.etapa(ETAPA_COTIZADA))


@tagged('post_install', '-at_install')
class TestLaPersonaManda(CrmCase):

    @freeze_time(AHORA)
    def test_si_la_vendedora_mueve_la_etapa_el_cron_ya_no_la_toca(self):
        lead = self.lead()
        self.orden_enviada(lead)
        nueva = self.env.ref('crm.stage_lead2')
        lead.with_user(self.vendedora).write({'stage_id': nueva.id})
        self.assertTrue(lead.dcasa_auto_off)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertEqual(lead.stage_id, nueva, 'la persona mandó: no vuelve a «Propuesta»')

    @freeze_time(AHORA)
    def test_si_la_vendedora_cambia_la_temperatura_queda_como_ella_dijo(self):
        lead = self.lead()
        lead.with_user(self.vendedora).write({'dcasa_temperatura': R.CALIENTE})
        self.assertTrue(lead.dcasa_auto_off)
        self.lead(zona='Chame')                 # con este dato Odoo calcularía «frío»: no debe pisar a la persona
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertEqual(lead.dcasa_temperatura, R.CALIENTE)

    @freeze_time(AHORA)
    def test_devolver_el_control_vuelve_a_ajustarla(self):
        lead = self.lead()
        orden = self.orden_enviada(lead)
        lead.with_user(self.vendedora).write({'stage_id': self.env.ref('crm.stage_lead1').id})
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertNotEqual(lead.stage_id, self.env.ref(ETAPA_COTIZADA))
        lead.with_user(self.vendedora).action_dcasa_devolver_control()
        self.assertFalse(lead.dcasa_auto_off)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertEqual(lead.stage_id, self.env.ref(ETAPA_COTIZADA))
        self.assertTrue(orden)

    @freeze_time(AHORA)
    def test_lo_que_hace_el_propio_crm_no_cuenta_como_una_persona(self):
        lead = self.lead()
        self.orden_enviada(lead)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertFalse(lead.dcasa_auto_off)

    @freeze_time(AHORA)
    def test_restaurar_una_archivada_la_deja_en_manos_de_una_persona(self):
        """Si no, el cron la volvería a archivar a los 15 minutos."""
        lead = self.lead()
        lead.with_user(self.vendedora).action_set_lost()
        self.assertFalse(lead.active)
        lead.with_user(self.vendedora).write({'active': True})
        self.assertTrue(lead.dcasa_auto_off)

    @freeze_time(AHORA)
    def test_marcarla_ganada_a_mano_cierra_el_seguimiento_y_el_cron_la_ignora(self):
        lead = self.lead()
        lead.with_user(self.vendedora).action_set_won()
        self.assertEqual(lead.won_status, 'won')
        self.assertEqual(self.env['crm.lead']._dcasa_cron_crm(), {})

    def test_el_cambio_de_otro_campo_no_quita_el_control_automatico(self):
        lead = self.lead()
        lead.with_user(self.vendedora).write({'expected_revenue': 500.0, 'description': '<p>nota</p>'})
        self.assertFalse(lead.dcasa_auto_off)


@tagged('post_install', '-at_install')
class TestSinRespuesta(CrmCase):

    def conversacion_inactiva(self, dias):
        self.conv.write({'ultima_actividad': fields.Datetime.now() - timedelta(days=dias)})

    @freeze_time(AHORA)
    def test_pasados_los_dias_se_archiva_con_su_motivo(self):
        lead = self.lead()
        self.conversacion_inactiva(31)
        resumen = self.env['crm.lead']._dcasa_cron_crm()
        self.assertEqual(resumen.get('archivada'), 1)
        self.assertFalse(lead.active)
        self.assertEqual(lead.won_status, 'lost')
        self.assertEqual(lead.lost_reason_id, self.env.ref('dcasa_conversaciones.perdida_sin_respuesta'))
        self.assertTrue(any('no escribió en 31 días' in nota for nota in self.nombres_de_notas(lead)))

    @freeze_time(AHORA)
    def test_antes_de_los_dias_no(self):
        lead = self.lead()
        self.conversacion_inactiva(29)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertTrue(lead.active)

    @freeze_time(AHORA)
    def test_con_0_dias_nunca_se_archiva(self):
        self.ajustes.crm_dias_para_perdida = 0
        lead = self.lead()
        self.conversacion_inactiva(400)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertTrue(lead.active)

    @freeze_time(AHORA)
    def test_si_una_vendedora_tiene_algo_pendiente_no_se_archiva(self):
        lead = self.lead()
        lead.activity_schedule('mail.mail_activity_data_todo', user_id=self.vendedora.id, summary='Llamar')
        self.conversacion_inactiva(90)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertTrue(lead.active)

    @freeze_time(AHORA)
    def test_si_la_conversacion_esta_en_manos_de_una_vendedora_no_se_archiva(self):
        lead = self.lead()
        self.conv.with_user(self.vendedora).action_atender()
        self.conversacion_inactiva(90)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertTrue(lead.active)

    @freeze_time(AHORA)
    def test_un_pedido_confirmado_sin_pagar_no_se_archiva(self):
        lead = self.lead()
        self.orden_enviada(lead, confirmar=True)
        self.conversacion_inactiva(90)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertTrue(lead.active)

    @freeze_time(AHORA)
    def test_al_archivarla_se_cancela_el_seguimiento_que_estaba_programado(self):
        lead = self.lead()
        self.conv.write({'seguimiento_proximo': fields.Datetime.now() + timedelta(hours=2)})
        lead.with_user(self.vendedora).action_set_lost()
        self.assertFalse(self.conv.seguimiento_proximo, 'el próximo seguimiento se recalcula al cambiar la oportunidad')

    @freeze_time(AHORA)
    def test_el_cliente_que_vuelve_a_escribir_tiene_oportunidad_nueva(self):
        lead = self.lead()
        self.conversacion_inactiva(40)
        self.env['crm.lead']._dcasa_cron_crm()
        self.assertFalse(lead.active)
        nueva = self.lead()
        self.assertNotEqual(nueva, lead)
        self.assertTrue(nueva.active)


@tagged('post_install', '-at_install')
class TestAjustesDelCrm(CrmCase):

    def test_vienen_encendidos_y_con_30_dias(self):
        self.assertTrue(self.ajustes.crm_automatico)
        self.assertEqual(self.ajustes.crm_dias_para_perdida, 30)

    def test_los_dias_son_cero_o_de_catorce_a_trescientos_sesenta_y_cinco(self):
        for valido in (0, 14, 30, 365):
            self.ajustes.crm_dias_para_perdida = valido
        for malo in (1, 13, 366, -5):
            with self.assertRaises(Exception):   # noqa: B017 — ValidationError de la restricción
                self.ajustes.crm_dias_para_perdida = malo
                self.ajustes.flush_recordset()


@tagged('post_install', '-at_install')
class TestPantallasDelCrm(CrmCase):

    def test_la_ficha_la_lista_y_la_busqueda_traen_los_campos_nuevos(self):
        Lead = self.env['crm.lead']
        form = Lead.get_view(self.env.ref('crm.crm_lead_view_form').id, 'form')['arch']
        for campo in ('dcasa_temperatura', 'dcasa_zona_entrega', 'dcasa_para_cuando', 'dcasa_auto_off',
                      'action_dcasa_devolver_control'):
            self.assertIn(campo, form)
        lista = Lead.get_view(self.env.ref('crm.crm_case_tree_view_oppor').id, 'list')['arch']
        self.assertIn('dcasa_temperatura', lista)
        busqueda = Lead.get_view(self.env.ref('crm.view_crm_case_opportunities_filter').id, 'search')['arch']
        for filtro in ('dcasa_para_hoy', 'dcasa_calientes', 'dcasa_esperan', 'dcasa_cotizadas', 'dcasa_manuales'):
            self.assertIn(f'name="{filtro}"', busqueda)

    def test_la_lista_de_oportunidades_abre_primero_lo_mas_caliente(self):
        accion = self.env.ref('dcasa_conversaciones.accion_oportunidades_hoy')
        self.assertEqual(accion.res_model, 'crm.lead')
        self.assertIn('dcasa_conversacion_ids', accion.domain)
        vista = accion.view_ids.filtered(lambda v: v.view_mode == 'list').view_id
        self.assertIn('default_order="dcasa_temperatura desc', self.env['crm.lead'].get_view(vista.id, 'list')['arch'])
        menu = self.env.ref('dcasa_conversaciones.menu_dcasa_oportunidades')
        self.assertEqual(menu.parent_id, self.env.ref('dcasa_conversaciones.menu_dcasa_conversaciones_root'))

    @freeze_time(AHORA)
    def test_a_quien_escribirle_hoy_son_las_tibias_y_calientes_que_nadie_del_equipo_toco(self):
        tibia = self.lead(cuando='esta semana')                      # tibia: para cuándo (2) + escribió hace poco (1)
        otra = self.conversacion(nombre='Ana', id_externo='50760000009', texto='hola')
        fria = self.env['crm.lead'].browse(self.salida(
            'crear_oportunidad', {'resumen': 'Solo preguntó', 'interes': 'Lámpara'}, conv=otra)['oportunidad_id'])
        self.assertEqual((tibia.dcasa_temperatura, fria.dcasa_temperatura), (R.TIBIO, R.FRIO))
        Lead = self.env['crm.lead']
        para_hoy = Lead.search([('dcasa_para_hoy', '=', True)])
        self.assertIn(tibia, para_hoy)
        self.assertNotIn(fria, para_hoy, 'una fría no es prioridad')
        self.assertTrue(tibia.dcasa_para_hoy and not fria.dcasa_para_hoy)
        self.assertIn(fria, Lead.search([('dcasa_para_hoy', '=', False), ('id', 'in', [tibia.id, fria.id])]))

    @freeze_time(AHORA)
    def test_si_una_vendedora_le_escribio_hoy_ya_no_aparece_pero_a_las_24_horas_si(self):
        lead = self.lead(cuando='esta semana')
        self.assertTrue(lead.dcasa_para_hoy)
        self.registrar('Hola, soy Ana de D\'CASA', autor='vendedora', ts=fields.Datetime.now() - timedelta(hours=2))
        lead.invalidate_recordset()
        self.assertFalse(lead.dcasa_para_hoy, 'una vendedora ya le escribió hace 2 horas')
        self.assertNotIn(lead, self.env['crm.lead'].search([('dcasa_para_hoy', '=', True)]))
        with freeze_time('2026-10-10 20:00:00'):   # pasaron más de 24 horas
            lead.invalidate_recordset()
            self.assertTrue(lead.dcasa_para_hoy)

    @freeze_time(AHORA)
    def test_las_ganadas_y_las_archivadas_no_son_para_hoy(self):
        lead = self.lead(cuando='esta semana')
        lead.with_user(self.vendedora).action_set_won()
        self.assertFalse(lead.dcasa_para_hoy)

    def test_el_filtro_y_el_operador_raro(self):
        busqueda = self.env['crm.lead'].get_view(
            self.env.ref('crm.view_crm_case_opportunities_filter').id, 'search')['arch']
        self.assertIn('dcasa_para_hoy', busqueda)
        with self.assertRaises(Exception):   # noqa: B017 — UserError: solo sí o no
            self.env['crm.lead'].search([('dcasa_para_hoy', 'ilike', 'x')])


@tagged('post_install', '-at_install')
class TestBrianLeeElCrm(CrmCase):
    """Brian solo LEE el CRM de las conversaciones, como el usuario y con el permiso de ventas."""

    def brian(self, nombre, argumentos=None, usuario=None):
        return self.env['brian.herramientas'].with_user(usuario or self.vendedora).ejecutar(
            nombre, argumentos or {})

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def preparar(self):
        """Tres oportunidades: caliente (cotizada + para cuándo), tibia (para cuándo) y fría."""
        caliente = self.lead(cuando='esta semana')
        self.cotizar({'codigo': 'ZZ-SOFA'})
        otra = self.conversacion(nombre='Ana', id_externo='50769990001')
        tibia = self.env['crm.lead'].browse(self.salida('crear_oportunidad', {
            'resumen': 'Quiere un sofá', 'interes': 'Sofá', 'cuando': 'el sábado'}, conv=otra)['oportunidad_id'])
        otra2 = self.conversacion(nombre='Luis', id_externo='50769990002')
        fria = self.env['crm.lead'].browse(self.salida('crear_oportunidad', {
            'resumen': 'Solo mira', 'interes': 'Lámpara'}, conv=otra2)['oportunidad_id'])
        return caliente, tibia, fria

    @freeze_time(AHORA)
    def test_las_herramientas_estan_en_el_catalogo_de_ventas_y_no_de_otros(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertLessEqual({'oportunidades_abiertas', 'resumen_del_crm'}, nombres)
        sin_ventas = {h['name'] for h in self.env['brian.herramientas'].with_user(self.interno).catalogo()}
        self.assertFalse({'oportunidades_abiertas', 'resumen_del_crm'} & sin_ventas)
        para_juan = {h['name'] for h in self.env['brian.herramientas'].with_user(self.juan).catalogo()}
        self.assertFalse({'oportunidades_abiertas', 'resumen_del_crm'} & para_juan,
                         'el CRM interno no es para el asistente de clientes')

    @freeze_time(AHORA)
    def test_oportunidades_abiertas_va_de_la_mas_caliente_a_la_mas_fria(self):
        caliente, tibia, fria = self.preparar()
        datos = self.ok(self.brian('oportunidades_abiertas'))
        orden = [o['id'] for o in datos['oportunidades']]
        self.assertEqual(orden, [caliente.id, tibia.id, fria.id])
        primera = datos['oportunidades'][0]
        self.assertEqual(primera['temperatura'], 'caliente')
        self.assertIn('pidió cotización', primera['porque'])
        self.assertTrue(primera['cotizacion_enviada'])
        self.assertEqual(primera['para_cuando'], 'esta semana')
        self.assertTrue(primera['espera_respuesta'] or primera['cotizacion_enviada'])
        self.assertEqual(datos['total'], 3)

    @freeze_time(AHORA)
    def test_se_puede_pedir_solo_una_temperatura_y_acepta_acentos(self):
        caliente, tibia, _fria = self.preparar()
        self.assertEqual([o['id'] for o in self.ok(self.brian(
            'oportunidades_abiertas', {'temperatura': 'caliente'}))['oportunidades']], [caliente.id])
        self.assertEqual([o['id'] for o in self.ok(self.brian(
            'oportunidades_abiertas', {'temperatura': 'tibia'}))['oportunidades']], [tibia.id])
        fria = self.ok(self.brian('oportunidades_abiertas', {'temperatura': 'fría'}))
        self.assertEqual(len(fria['oportunidades']), 1)

    @freeze_time(AHORA)
    def test_para_hoy_trae_solo_las_tibias_y_calientes_sin_contacto_de_una_vendedora(self):
        caliente, tibia, fria = self.preparar()
        datos = self.ok(self.brian('oportunidades_abiertas', {'para_hoy': True}))
        self.assertEqual([o['id'] for o in datos['oportunidades']], [caliente.id, tibia.id])
        self.assertTrue(all(o['para_hoy'] for o in datos['oportunidades']))
        self.assertNotIn(fria.id, [o['id'] for o in datos['oportunidades']])
        self.assertEqual(self.ok(self.brian('resumen_del_crm'))['para_escribirles_hoy'], 2)

    @freeze_time(AHORA)
    def test_una_temperatura_inventada_es_un_error_claro(self):
        respuesta = self.brian('oportunidades_abiertas', {'temperatura': 'ardiente'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('caliente', respuesta['error'])

    @freeze_time(AHORA)
    def test_el_limite_se_respeta_y_no_pasa_de_veinte(self):
        self.preparar()
        self.assertEqual(self.ok(self.brian('oportunidades_abiertas', {'limite': 1}))['mostrando'], 1)
        self.assertEqual(self.ok(self.brian('oportunidades_abiertas', {'limite': 1}))['total'], 3)
        self.assertLessEqual(self.ok(self.brian('oportunidades_abiertas', {'limite': 999}))['mostrando'], 20)

    @freeze_time(AHORA)
    def test_no_muestra_ganadas_ni_archivadas_ni_las_que_no_nacieron_de_una_conversacion(self):
        caliente, tibia, fria = self.preparar()
        tibia.with_user(self.vendedora).action_set_won()
        fria.with_user(self.vendedora).action_set_lost()
        self.env['crm.lead'].create({'name': 'Suelta', 'type': 'opportunity'})
        ids = [o['id'] for o in self.ok(self.brian('oportunidades_abiertas'))['oportunidades']]
        self.assertEqual(ids, [caliente.id])

    @freeze_time(AHORA)
    def test_el_resumen_cuenta_por_temperatura_etapa_y_espera(self):
        self.preparar()
        datos = self.ok(self.brian('resumen_del_crm'))
        self.assertEqual(datos['abiertas'], 3)
        self.assertEqual(datos['por_temperatura'], {'caliente': 1, 'tibio': 1, 'frío': 1})
        self.assertEqual(sum(datos['por_etapa'].values()), 3)
        self.assertEqual(datos['con_cotizacion_enviada'], 1)
        self.assertEqual(datos['esperan_respuesta'], 3, 'el último mensaje de las tres es del cliente')
        self.assertEqual(datos['en_manos_de_una_persona'], 0)
        self.assertEqual(datos['ganadas_ultimos_30_dias'], 0)

    @freeze_time(AHORA)
    def test_el_resumen_cuenta_lo_ganado_y_lo_archivado_sin_respuesta(self):
        caliente, tibia, fria = self.preparar()
        tibia.with_user(self.vendedora).action_set_won()
        self.conv.write({'ultima_actividad': fields.Datetime.now() - timedelta(days=40)})
        self.env['crm.lead']._dcasa_cron_crm()
        datos = self.ok(self.brian('resumen_del_crm'))
        self.assertEqual(datos['ganadas_ultimos_30_dias'], 1)
        self.assertEqual(datos['archivadas_sin_respuesta_ultimos_30_dias'], 1)
        self.assertFalse(caliente.active)

    @freeze_time(AHORA)
    def test_quien_no_es_de_ventas_no_puede(self):
        for nombre in ('oportunidades_abiertas', 'resumen_del_crm'):
            respuesta = self.brian(nombre, usuario=self.interno)
            self.assertFalse(respuesta['ok'], nombre)


@tagged('post_install', '-at_install')
class TestCorreccionesDeLaAuditoria(CrmCase):
    """Los huecos que encontró la auditoría del 2026-10-10, cada uno con el escenario que lo rompía."""

    @freeze_time(AHORA)
    def test_si_el_pdf_no_sale_la_cotizacion_sigue_en_borrador_y_la_oportunidad_no_avanza(self):
        with patch(RENDER, return_value=(b'<html>no es pdf</html>', 'html')):
            datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(datos['motivo'], 'sin_pdf')
        (orden,) = self.ordenes()
        (lead,) = self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)])
        self.assertEqual(orden.state, 'draft', 'no se envió nada: no puede figurar como enviada')
        self.assertEqual(orden.opportunity_id, lead, 'sí queda ligada, para que la vendedora la encuentre')
        self.assertNotEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))
        self.cron()
        self.assertNotEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA), 'tampoco el cron la adelanta')
        self.assertNotIn('cotización', (lead.dcasa_temperatura_motivo or ''))

    @freeze_time(AHORA)
    def test_con_el_pdf_enviado_la_cotizacion_pasa_a_enviada_y_la_oportunidad_a_propuesta(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (orden,) = self.ordenes()
        (lead,) = self.env['crm.lead'].search([('partner_id', '=', self.conv.partner_id.id)])
        self.assertEqual(orden.state, 'sent')
        self.assertEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))

    def cron(self):
        return self.env['crm.lead']._dcasa_cron_crm()

    @freeze_time(AHORA)
    def test_una_oportunidad_hecha_a_mano_se_liga_pero_queda_en_manos_de_su_persona(self):
        manual = self.env['crm.lead'].with_user(self.vendedora).create({
            'name': 'Sala para Karen (llamada)', 'type': 'opportunity', 'partner_id': self.conv.partner_id.id,
            'user_id': self.vendedora.id})
        self.assertFalse(manual.dcasa_auto_off)
        datos = self.salida('crear_oportunidad', {'resumen': 'Quiere una cama queen', 'interes': 'Cama queen'})
        self.assertEqual(datos['oportunidad_id'], manual.id, 'no duplica: usa la que ya había')
        self.assertTrue(manual.dcasa_auto_off, 'el CRM automático no adopta lo que una persona abrió')
        self.conv.write({'ultima_actividad': fields.Datetime.now() - timedelta(days=90)})
        self.cron()
        self.assertTrue(manual.active, 'ni la archiva por días sin mensajes')
        self.assertEqual(manual.dcasa_temperatura, R.FRIO, 'sin juicio propio: «fría» para que no salga de primera')
        self.assertEqual(manual.dcasa_temperatura_motivo, 'la maneja una persona')

    @freeze_time(AHORA)
    def test_una_oportunidad_que_nacio_de_la_conversacion_si_queda_automatica(self):
        lead = self.lead()
        self.assertFalse(lead.dcasa_auto_off)
        self.assertTrue(lead.dcasa_temperatura)

    def test_la_migracion_deja_en_manos_de_personas_lo_que_ya_existia(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'mig110', file_path('dcasa_conversaciones/migrations/19.0.1.1.0/post-migrate.py'))
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        de_conversacion = self.env['crm.lead'].create({'name': 'Vieja de Juan', 'type': 'opportunity'})
        self.conv.write({'oportunidad_id': de_conversacion.id})
        suelta = self.env['crm.lead'].create({'name': 'Hecha a mano sin conversación', 'type': 'opportunity'})
        self.assertFalse(de_conversacion.dcasa_auto_off or suelta.dcasa_auto_off)
        self.env.flush_all()
        mig.migrate(self.env.cr, '19.0.1.0.2')
        self.env.invalidate_all()
        self.assertTrue(de_conversacion.dcasa_auto_off)
        self.assertEqual(de_conversacion.dcasa_temperatura, R.FRIO, 'sin temperatura saldría de primera en la lista')
        self.assertFalse(suelta.dcasa_auto_off, 'solo lo que viene de una conversación')
        self.assertFalse(suelta.dcasa_temperatura)

    @freeze_time(AHORA)
    def test_el_cron_revisa_todas_las_oportunidades_aunque_pasen_del_tamano_de_la_tanda(self):
        otras = []
        for i in range(4):
            conv = self.conversacion(nombre=f'Cliente {i}', id_externo=f'5076000010{i}', texto='hola')
            datos = self.salida('crear_oportunidad', {'resumen': 'Quiere un sofá', 'interes': f'Sofá {i}'}, conv=conv)
            otras.append(self.env['crm.lead'].browse(datos['oportunidad_id']))
        for lead in otras:
            self.orden_enviada(lead)
        with patch('odoo.addons.dcasa_conversaciones.models.crm_lead.LOTE_DEL_CRON', 2):
            resumen = self.cron()
        self.assertEqual(resumen.get('cotizada'), 4, 'las cuatro, también las más viejas')
        for lead in otras:
            self.assertEqual(lead.stage_id, self.etapa(ETAPA_COTIZADA))

    @freeze_time(AHORA)
    def test_una_nota_interna_o_un_mensaje_que_no_salio_no_cuentan_como_haberle_escrito(self):
        lead = self.lead(cuando='esta semana')
        self.assertTrue(lead.dcasa_para_hoy)
        Mensaje = self.env['dcasa.mensaje'].sudo()
        base = {'conversacion_id': self.conv.id, 'autor': 'vendedora',
                'ts': fields.Datetime.now() - timedelta(hours=1)}
        Mensaje.create({**base, 'id_mensaje': 'nota-1', 'tipo': 'nota', 'direccion': 'interna',
                        'texto': 'ojo con ella'})
        for i, estado in enumerate(('por_enviar', 'fallido')):
            Mensaje.create({**base, 'id_mensaje': f'odoo-{i}', 'tipo': 'mensaje', 'direccion': 'saliente',
                            'texto': 'Hola, soy Ana', 'origen': 'odoo', 'estado_envio': estado})
        Mensaje.create({**base, 'id_mensaje': 'prog-1', 'tipo': 'mensaje', 'direccion': 'saliente', 'texto': 'Mañana',
                        'origen': 'odoo', 'estado_envio': 'programado',
                        'programado_para': fields.Datetime.now() + timedelta(days=1),
                        'ts': fields.Datetime.now() + timedelta(hours=20)})
        lead.invalidate_recordset()
        self.assertTrue(lead.dcasa_para_hoy, 'nadie le escribió de verdad')
        self.registrar('Hola, soy Ana de D\'CASA', autor='vendedora', ts=fields.Datetime.now() - timedelta(hours=1))
        lead.invalidate_recordset()
        self.assertFalse(lead.dcasa_para_hoy, 'ahora sí')

    def test_un_choque_de_concurrencia_se_reintenta_no_se_traga(self):
        lead = self.lead()

        def choca():
            raise ConcurrencyError('res.partner')

        with self.assertRaises(ConcurrencyError):
            lead._dcasa_seguro('prueba', choca)
        with mute_logger('odoo.addons.dcasa_conversaciones.models.crm_lead'):
            self.assertIsNone(lead._dcasa_seguro('prueba', lambda: 1 / 0), 'un error cualquiera sí se registra y sigue')

    @freeze_time(AHORA)
    def test_ligar_la_cotizacion_tampoco_traga_un_choque_de_concurrencia(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (orden,) = self.ordenes()
        with patch.object(type(self.conv), '_oportunidad', side_effect=ConcurrencyError('crm.lead')):
            with self.assertRaises(ConcurrencyError):
                self.conv._ligar_cotizacion(orden)
