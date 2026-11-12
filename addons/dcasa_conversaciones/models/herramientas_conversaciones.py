"""Brian lee las pantallas de Juan (2026-11-06, «Brian al día»): Resumen, Reparto y las cotizaciones que vencen solas.
Y, desde el 2026-11-12, «Costos de IA» (``costos_de_juan``: cuánto se le debe a Meta), solo Gerencia y administradores.

Las mismas cifras de las pantallas (``dcasa.juan.panel.resumen``/``tasas_de_cierre``/``reparto`` y el dominio del cron
de ``sale_origen``), leídas como quien pregunta: la vendedora ve lo que ve en su pantalla (en el Reparto, solo lo suyo;
con «Cada vendedora ve solo sus documentos», sus ventas y cotizaciones), Gerencia ve a todo el equipo. Nada lo calcula
el modelo de IA, y nada de esto cambia datos: sacar a una vendedora del reparto o cambiar los días de una cotización se
hace en la pantalla (Gerencia).
"""
from datetime import timedelta

from odoo import models
from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.exceptions import AccessError

from . import panel_calculos as C
from .sale_origen import ORIGENES_QUE_VENCEN, PAGOS_EN_CURSO, hoy_en_panama

VENTAS = ('sales_team.group_sale_salesman',)
GERENCIA_O_ADMIN = (('sales_team.group_sale_manager', 'base.group_system'),)
ESTADOS_DEL_TOPE = {
    'bien': 'vas bien',
    'en_riesgo': 'a este ritmo vas a pasar el tope',
    'alcanzado': 'tope alcanzado: Juan sigue contestando, con el modelo económico',
    'sin_tope': 'no hay un tope puesto en Ajustes de Juan',
}
DONDE_SE_PAGA = ('Brian no marca pagos: después de pagarle a Meta, en Conversaciones › Costos de IA se toca «Pagar» y '
                 'el saldo vuelve a $0 (con «Deshacer» si fue sin querer).')
PARAM_PERIODO_JUAN = {'type': 'string', 'enum': list(C.PERIODOS),
                      'description': 'hoy, 7_dias, 30_dias, 90_dias o 12_meses (hora de Panamá). Por defecto, hoy.'}
ESTADOS_DEL_REPARTO = {
    'disponible': 'disponible: recibe',
    'no_disponible': 'se marcó «No disponible»: no recibe',
    'inactiva': 'sin usar el sistema hace rato: no recibe',
    'fuera': 'Gerencia la sacó del reparto',
    'interviene': 'Gerencia o administradora: no recibe',
}
MAX_COTIZACIONES = 20


def _porcentaje(valor):
    return '—' if valor is None else f'{valor:g} %'


def _ventas(parte):
    return f"{c.plural(parte['facturas'], 'factura')} · {c.moneda(parte['monto'])}"


class BrianHerramientasConversaciones(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @herramienta(
        nombre='resumen_de_conversaciones',
        descripcion='El Resumen de Juan (Conversaciones › Resumen): mensajes, clientes, lo que Juan resolvió solo, '
                    'oportunidades, ventas atribuidas, tasa de cierre y cuánto se tarda en contestar.',
        parametros={'periodo': PARAM_PERIODO_JUAN},
        nivel='lectura', categoria='ventas', grupos=VENTAS,
        ejemplos=['¿cuál es la tasa de cierre de Juan?', '¿cuántas conversaciones hubo esta semana? → 7_dias',
                  '¿cuánto vendió Juan este mes? → 30_dias'],
    )
    def _h_resumen_de_conversaciones(self, periodo='hoy'):
        if periodo not in C.PERIODOS:
            raise BrianError(f'Periodo desconocido. Usa {", ".join(C.PERIODOS)}.')
        panel = self.env['dcasa.juan.panel']
        r = panel.resumen(periodo)
        ventas, tasa, primera = r['ventas'], r['tasa_de_cierre'], r['primera_respuesta']
        datos = {
            'periodo': r['periodo_nombre'],
            'mensajes': {'de_clientes': r['mensajes']['entrantes'], 'de_juan': r['mensajes']['del_asistente'],
                         'de_vendedoras': r['mensajes']['de_vendedoras']},
            'clientes_que_escribieron': r['clientes_unicos'],
            'conversaciones': r['conversaciones'],
            'resueltas_por_juan_sin_una_persona': r['resueltas_sin_humano'],
            'oportunidades_creadas': r['oportunidades_creadas'],
            'ventas_atribuidas_sin_itbms': {
                'solo_juan': _ventas(ventas['solo_juan']),
                'juan_y_una_persona': _ventas(ventas['juan_y_vendedora']),
                'solo_personas': _ventas(ventas['solo_vendedora']),
                'de_una_cotizacion_de_juan': _ventas(ventas['de_cotizacion_de_juan']),
            },
            'tasa_de_cierre': {'total': _porcentaje(tasa['total']['tasa']),
                               'juan_y_una_persona': _porcentaje(tasa['juan_y_vendedora']['tasa']),
                               'solo_juan': _porcentaje(tasa['solo_juan']['tasa'])},
            'tasa_de_cierre_por_periodo': {fila['nombre']: _porcentaje(fila['total']['tasa'])
                                           for fila in panel.tasas_de_cierre()},
            'primera_respuesta': {'de_juan_o_una_persona': primera['cualquiera_texto'] or '—',
                                  'de_una_persona': primera['persona_texto'] or '—'},
            'esperan_a_una_persona_ahora': r['necesitan_atencion'],
            'juan': ('conectado' if r['bot_conectado'] else 'sin conectar') + ' y '
                    + ('encendido' if r['bot_encendido'] else 'apagado'),
            'como_se_cuenta': 'Tasa de cierre = facturas pagadas del periodo de clientes con quienes habló Juan en '
                              f'los {ventas["ventana_dias"]} días antes ÷ conversaciones del periodo × 100. Es '
                              'atribución por conversación, no causalidad. «Solo personas» es de referencia: no se '
                              'le atribuye a Juan.',
        }
        alcance = c.alcance(self.env)
        if alcance:
            datos['alcance'] = alcance
        return datos

    @herramienta(
        nombre='reparto_de_conversaciones',
        descripcion='Cómo reparte Juan los clientes entre las vendedoras: el modo, quién está activa y recibe, cuántas '
                    'recibió cada una, a quién le esperan clientes y cuántos esperan sin dueña.',
        parametros={'periodo': PARAM_PERIODO_JUAN},
        nivel='lectura', categoria='ventas', grupos=VENTAS,
        ejemplos=['¿a quién le está pasando clientes Juan?', '¿qué vendedoras están activas?',
                  '¿cuántos clientes me pasó Juan hoy?'],
    )
    def _h_reparto_de_conversaciones(self, periodo='hoy'):
        if periodo not in C.PERIODOS:
            raise BrianError(f'Periodo desconocido. Usa {", ".join(C.PERIODOS)}.')
        d = self.env['dcasa.juan.panel'].reparto(periodo)

        def fila(f):
            salida = {'nombre': f['nombre'], 'estado': ESTADOS_DEL_REPARTO.get(f['estado'], f['estado']),
                      'recibidas': f['recibidas'], 'clientes_esperandole': f['abiertas']}
            if f.get('fuera_hasta'):
                salida['fuera_hasta'] = c.fecha(f['fuera_hasta'])
            return salida
        datos = {
            'periodo': d['periodo_nombre'],
            'modo': d['modo_nombre'],
            'reglas': {
                'recibe_solo_quien_uso_el_sistema_en_minutos': d['minutos_activa'] or 'apagado',
                'pasa_a_otra_si_no_contesta_en_minutos': d['minutos_reasignar'] or 'nunca',
                'dias_que_un_cliente_sigue_con_su_vendedora': d['dias_misma_vendedora'],
            },
            'tu': fila(d['yo']),
        }
        if d['es_gerencia']:
            datos['equipo'] = [fila(f) for f in d['equipo']]
            datos['no_reciben'] = d['no_reciben']
            sin_dueno = d['sin_dueno'] or {}
            datos['esperan_sin_duena'] = sin_dueno.get('conversaciones', 0)
            if sin_dueno.get('espera_mas_min') is not None:
                datos['la_que_mas_espera_sin_duena_min'] = sin_dueno['espera_mas_min']
        else:
            datos['alcance'] = 'solo lo tuyo: los números de las demás los ve Gerencia'
        if d['modo'] == 'manual':
            datos['nota'] = ('El reparto está apagado: Juan no le asigna clientes a nadie (la toma quien quiera). Lo '
                             'enciende Gerencia en Conversaciones › Reparto.')
        return datos

    @herramienta(
        nombre='cotizaciones_que_vencen',
        descripcion='Las cotizaciones del chatbot (Juan) y de la web que se cancelan solas si nadie las confirma: '
                    'cuáles vencen en los próximos días, cuántos días quedan abiertas y qué no se toca.',
        parametros={
            'dias': {'type': 'integer', 'description': 'Las que vencen de hoy a esos días (0 a 30). Por defecto 3.'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='ventas', grupos=VENTAS, texto_externo=True,   # el nombre lo dio el cliente
        ejemplos=['¿qué cotizaciones de Juan vencen pronto?', '¿cuántos días queda abierta una cotización de la web?'],
    )
    def _h_cotizaciones_que_vencen(self, dias=3, limite=10):
        if isinstance(dias, bool) or not isinstance(dias, int) or not 0 <= dias <= 30:
            raise BrianError('«dias» va de 0 a 30.')
        abierta = self.env['dcasa.juan.ajustes'].sudo().obtener().cotizacion_dias_abierta
        hoy = hoy_en_panama()
        Orden = self.env['sale.order']   # como quien pregunta: «Cada vendedora ve solo sus documentos» se respeta
        visibles = Orden.search([('dcasa_origen', 'in', ORIGENES_QUE_VENCEN), ('state', 'in', ('draft', 'sent')),
                                 ('validity_date', '!=', False),
                                 ('validity_date', '<=', hoy + timedelta(days=dias))])
        # Lo mismo que el cron NO cancela (bloqueadas, con factura, con pago en curso, apartados): fuera de la lista. Se
        # mira con sudo sobre las que esta persona ya puede ver (los pagos y facturas no siempre los lee una vendedora).
        excluir = [('locked', '=', False), ('transaction_ids', 'not any', [('state', 'in', PAGOS_EN_CURSO)]),
                   ('order_line', 'not any', [('invoice_lines.move_id.state', '!=', 'cancel')])]
        if 'dcasa_apartado_vence' in Orden._fields:
            excluir.append(('dcasa_apartado_vence', '=', False))
        se_cancelan = Orden.sudo().search(excluir + [('id', 'in', visibles.ids)], order='validity_date asc, id asc')
        ordenes = Orden.browse(se_cancelan[:min(c.limite(limite), MAX_COTIZACIONES)].ids)
        origenes = dict(Orden._fields['dcasa_origen']._description_selection(self.env))
        filas = [{'numero': o.name, 'cliente': o.partner_id.display_name or '',
                  'origen': origenes.get(o.dcasa_origen, o.dcasa_origen), 'total': c.moneda(o.amount_total),
                  'valida_hasta': c.fecha(o.validity_date),
                  'ya_vencio': o.validity_date < hoy} for o in ordenes]
        datos = {
            'dias_que_queda_abierta': abierta or 'apagado: no se cancela ninguna sola',
            'vencen_hasta': c.fecha(hoy + timedelta(days=dias)),
            'total': len(se_cancelan),
            'cotizaciones': filas,
            'como_funciona': 'Una cotización del chatbot o de la web queda válida hasta hoy + los días de Ajustes de '
                             'Juan; cada hora se cancela (nunca se borra) la que pasó esa fecha sin confirmar. No se '
                             'tocan las de las vendedoras, las bloqueadas, las que tienen factura, pago en curso o '
                             'apartado, ni las tocadas hace menos de 12 horas. Para darle más días: «Establecer como '
                             'cotización» (si ya se canceló) o cambiar su fecha de validez.',
        }
        alcance = c.alcance(self.env, 'cotizaciones')
        if alcance:
            datos['alcance'] = alcance
        return datos

    @herramienta(
        nombre='costos_de_juan',
        descripcion='Cuánto se le debe a Meta por la IA de Juan (Conversaciones › Costos de IA): lo que hay por pagar '
                    '(lo consumido desde el último pago), el último pago, el gasto del mes y el tope. No marca pagos.',
        nivel='lectura', categoria='ventas', grupos=GERENCIA_O_ADMIN,
        ejemplos=['¿cuánto le debo a Meta de la IA?', '¿cuánto llevamos gastado en IA este mes?',
                  '¿cuándo fue el último pago de la IA?', 'marca como pagada la IA → dile dónde está «Pagar»'],
    )
    def _h_costos_de_juan(self):
        panel = self.env['dcasa.juan.panel']
        try:
            panel._exigir_pagos()   # Gerencia o administrador, como quien pregunta (sin sudo)
        except AccessError as error:
            raise BrianError(str(error)) from None
        d = panel._datos_de_costos()
        if not d.get('ok'):
            # Sin el Worker no hay cifras de hoy: se dice, no se inventan. El último pago sí se sabe (está en Odoo).
            ultimo = panel._saldo_ia()['ultimo']
            return self._con_boton_de_costos({
                'sin_cifras': ('Falta conectar el bot (Worker de Juan): ' if not d.get('configurado')
                               else 'No pude hablar con Juan (el Worker): ') + (d.get('detalle') or '')
                              + ' Sin él no hay cifras de hoy; no se inventan.',
                'ultimo_pago': self._texto_ultimo_pago_ia(ultimo),
                'para_marcar_un_pago': DONDE_SE_PAGA,
            })
        pagos = d['pagos']
        por_pagar = c.moneda(pagos['saldo'])
        if pagos['aprox']:
            por_pagar += ' (aprox.: faltan fotos del gasto de algún mes, puede ser un poco más)'
        return self._con_boton_de_costos({
            'por_pagar_a_meta': por_pagar,
            'ultimo_pago': self._texto_ultimo_pago_ia(pagos['ultimo']),
            'gasto_del_mes': {
                'mes': d['mes_nombre'], 'gasto': c.moneda(d['gasto_usd']),
                'tope': c.moneda(d['tope_usd']) if d['tope_usd'] else 'sin tope',
                'porcentaje_del_tope': _porcentaje(d['porcentaje_del_tope']),
                'si_sigue_este_ritmo_termina_en': ('todavía es pronto para proyectar' if d['proyeccion_usd'] is None
                                                   else c.moneda(d['proyeccion_usd'])),
                'estado': ESTADOS_DEL_TOPE.get(d['estado_del_tope'], d['estado_del_tope']),
            },
            'como_se_cuenta': 'Por pagar = lo que la IA de Juan consumió desde el último pago marcado (sin pagos, lo '
                              'del mes). Lo cobra Meta; lo mide el Worker de Juan. El gasto del mes sigue completo.',
            'para_marcar_un_pago': DONDE_SE_PAGA,
        })

    def _con_boton_de_costos(self, datos):
        """Agrega el botón a «Costos de IA» (donde está «Pagar»), solo si quien pregunta ve ese menú."""
        menu = self.env.ref('dcasa_conversaciones.menu_dcasa_panel_costos', raise_if_not_found=False)
        destino = self._b_destino_de_menu(menu, 'Costos de IA') if menu and self._b_menu_visible(menu) else None
        if destino:
            datos['abrir'] = destino
        return datos

    def _texto_ultimo_pago_ia(self, ultimo):
        if not ultimo:
            return 'ninguno todavía'
        return {'monto': c.moneda(ultimo['monto']), 'fecha': ultimo['texto']}
