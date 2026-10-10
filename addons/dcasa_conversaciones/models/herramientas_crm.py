"""Brian lee el CRM de las conversaciones: «¿a quién le escribo hoy?» y «¿cómo va el CRM?».

Solo LECTURA y como el usuario (sin sudo): la vendedora ve lo que ve en Odoo. Las cifras las calcula Odoo; la
temperatura y las etapas las pone el CRM automático con reglas fijas (``crm_reglas.py``), no la IA. Brian todavía no
cierra ni gana oportunidades: eso queda en un issue del repositorio (docs/CRM_AUTOMATICO.md).
"""
from datetime import timedelta

from odoo import fields, models
from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta

from . import crm_reglas as R

VENTAS = ('sales_team.group_sale_salesman',)
MAX_OPORTUNIDADES = 20
TEMPERATURAS_DICHAS = {'caliente': R.CALIENTE, 'tibia': R.TIBIO, 'tibio': R.TIBIO, 'fria': R.FRIO, 'fría': R.FRIO,
                       'frio': R.FRIO, 'frío': R.FRIO}


class BrianHerramientasCrm(models.AbstractModel):
    _inherit = 'brian.herramientas'

    def _crm_abiertas(self):
        """Oportunidades vivas que nacieron de una conversación (las que el CRM automático maneja)."""
        return [('type', '=', 'opportunity'), ('active', '=', True), ('won_status', '=', 'pending'),
                ('dcasa_conversacion_ids', '!=', False)]

    @herramienta(
        nombre='oportunidades_abiertas',
        descripcion='Lista las oportunidades abiertas del CRM que vienen de conversaciones, de la más caliente a la '
                    'más fría: cliente, etapa, qué pidió, si esperan respuesta o ya tienen cotización.',
        parametros={
            'temperatura': {'type': 'string', 'enum': ['caliente', 'tibia', 'fria'],
                            'description': 'Opcional: solo las de esa temperatura.'},
            'para_hoy': {'type': 'boolean',
                         'description': 'true: solo las tibias y calientes a las que ninguna vendedora escribió en '
                                        'las últimas 24 horas (a quién escribirle hoy).'},
            'limite': {'type': 'integer', 'description': 'Cuántas mostrar, de 1 a 20. Por defecto 10.'},
        },
        nivel='lectura', categoria='ventas', grupos=VENTAS,
        ejemplos=['¿a quién le escribo hoy?', '¿qué oportunidades calientes tengo?'],
    )
    def _h_oportunidades_abiertas(self, temperatura=None, para_hoy=False, limite=10):
        Lead = self.env['crm.lead']
        dominio = Lead._dcasa_dominio_para_hoy() if para_hoy else self._crm_abiertas()
        if temperatura:
            nivel = TEMPERATURAS_DICHAS.get(str(temperatura).strip().lower())
            if not nivel:
                raise BrianError('La temperatura es «caliente», «tibia» o «fria».')
            dominio.append(('dcasa_temperatura', '=', nivel))
        limite = max(1, min(c.limite(limite), MAX_OPORTUNIDADES))
        leads = Lead.search(dominio, order='dcasa_temperatura desc nulls last, id desc', limit=limite)
        filas = []
        for lead in leads:
            conversaciones = lead.dcasa_conversacion_ids
            filas.append({
                'id': lead.id,
                'oportunidad': lead.name,
                'cliente': lead.partner_id.display_name or '',
                'etapa': lead.stage_id.display_name or '',
                'temperatura': R.NOMBRE_TEMPERATURA.get(lead.dcasa_temperatura, 'sin calcular').lower(),
                'porque': lead.dcasa_temperatura_motivo or '',
                'para_cuando': lead.dcasa_para_cuando or '',
                'zona': lead.dcasa_zona_entrega or '',
                'espera_respuesta': any(conv.ultimo_mensaje_autor == 'cliente' for conv in conversaciones),
                'cotizacion_enviada': any(orden.state == 'sent' for orden in lead.order_ids),
                'ultimo_mensaje_del_cliente': c.fecha(max(
                    (conv.ultimo_mensaje_cliente for conv in conversaciones if conv.ultimo_mensaje_cliente),
                    default=False)),
                'en_manos_de_una_persona': lead.dcasa_auto_off,
                'para_hoy': lead.dcasa_para_hoy,
            })
        total = Lead.search_count(dominio)
        return {'total': total, 'mostrando': len(filas), 'oportunidades': filas,
                'nota': 'La temperatura la calcula el CRM con hechos (cotización, para cuándo, cuánto escribe); '
                        'no es una opinión de la IA.'}

    @herramienta(
        nombre='resumen_del_crm',
        descripcion='Cómo va el CRM de las conversaciones: abiertas por temperatura y por etapa, cuántas esperan '
                    'respuesta, cotizaciones enviadas, y lo ganado y archivado en los últimos 30 días.',
        nivel='lectura', categoria='ventas', grupos=VENTAS,
        ejemplos=['¿cómo va el CRM esta semana?', 'resumen de oportunidades'],
    )
    def _h_resumen_del_crm(self):
        Lead = self.env['crm.lead']
        abiertas = self._crm_abiertas()
        hace_30 = fields.Datetime.now() - timedelta(days=30)

        por_temperatura = {R.NOMBRE_TEMPERATURA.get(nivel, 'sin calcular').lower(): cuantas
                           for nivel, cuantas in Lead._read_group(abiertas, ['dcasa_temperatura'], ['__count'])}
        por_etapa = {etapa.display_name: cuantas
                     for etapa, cuantas in Lead._read_group(abiertas, ['stage_id'], ['__count'])}
        esperan = Lead.search_count(abiertas + [('dcasa_conversacion_ids.ultimo_mensaje_autor', '=', 'cliente')])
        cotizadas = Lead.search_count(abiertas + [('order_ids.state', '=', 'sent')])
        manuales = Lead.search_count(abiertas + [('dcasa_auto_off', '=', True)])
        ganadas = Lead.search_count([('type', '=', 'opportunity'), ('won_status', '=', 'won'),
                                     ('dcasa_conversacion_ids', '!=', False), ('date_closed', '>=', hace_30)])
        motivo = self.env.ref('dcasa_conversaciones.perdida_sin_respuesta', raise_if_not_found=False)
        sin_respuesta = Lead.with_context(active_test=False).search_count([
            ('lost_reason_id', '=', motivo.id), ('active', '=', False), ('write_date', '>=', hace_30)]) \
            if motivo else 0
        return {
            'abiertas': Lead.search_count(abiertas),
            'por_temperatura': por_temperatura,
            'por_etapa': por_etapa,
            'para_escribirles_hoy': Lead.search_count(Lead._dcasa_dominio_para_hoy()),
            'esperan_respuesta': esperan,
            'con_cotizacion_enviada': cotizadas,
            'en_manos_de_una_persona': manuales,
            'ganadas_ultimos_30_dias': ganadas,
            'archivadas_sin_respuesta_ultimos_30_dias': sin_respuesta,
            'nota': 'Solo cuenta oportunidades que nacieron de una conversación. Ganada = factura pagada de una '
                    'cotización ligada; archivada = sin mensajes en los días de Ajustes de Juan.',
        }
