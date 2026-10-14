"""Herramientas del programa de VENDEDORES D'CASA (código de vendedor, colmena de un nivel, puntos de vendedor).

Reglas del programa que se respetan aquí (están en ``docs/VENDEDORES.md``):
* Un vendedor es la misma ficha que el cliente y el socio (``res.partner``); su saldo de vendedor ES la suma de
  ``dcasa.vend.movimiento``: se lee, nunca se escribe. El único ajuste que se ofrece pasa por el asistente del módulo.
* Afiliar exige cédula/RUC, celular válido y que la PERSONA haya aceptado los términos: Brian no acepta por nadie, solo
  anota que quien pide la afiliación confirma que la persona los aceptó.
* El patrocinador se escribe una vez y no se cambia: Brian no tiene herramienta para cambiarlo.
* Ninguna cifra vive aquí: salen de la sección ``vendedores`` de ``puntos.json``.
"""
from odoo import fields, models
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.addons.dcasa_socios.models import reglas_vendedores as RV
from odoo.addons.dcasa_socios.models.res_partner_vend import TIPOS_VENDEDOR
from odoo.addons.dcasa_socios.models.vend_comision import RESULTADOS

from . import herramientas_comun as c
from .registro import BrianError, herramienta

VENTAS = ('sales_team.group_sale_salesman',)
GERENCIA = ('sales_team.group_sale_manager',)
PARAM_VENDEDOR = {'type': 'string', 'description': 'Nombre, celular, cédula o código del vendedor, p. ej. '
                                                    '«Ana Gómez», «6123-4567» o «VEN7K2M9P».'}
TIPOS = dict(TIPOS_VENDEDOR)
RESULTADOS_TEXTO = dict(RESULTADOS)


class BrianHerramientasVendedores(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _b_vendedor(self, texto):
        """La ficha de un vendedor del programa (si es solo cliente, dice que todavía no es vendedor)."""
        persona = self._b_contacto(texto, 'vendedor').commercial_partner_id
        if not persona.dcasa_vendedor_codigo:
            raise BrianError(f'{persona.display_name} todavía no es vendedor del programa. Se afilia desde su ficha '
                             '(pestaña «Vendedor D\'CASA») o con la herramienta afiliar_vendedor.')
        return persona

    def _b_mes_en_curso(self):
        hoy = fields.Date.context_today(self)
        return hoy.replace(day=1)

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='consultar_vendedor',
        descripcion='Ficha de un vendedor del programa: código, tipo, patrocinador, directos, puntos disponibles y '
                    'por liberar, ventas del mes y últimas comisiones.',
        parametros={'vendedor': PARAM_VENDEDOR}, requeridos=['vendedor'],
        nivel='lectura', categoria='clientes', grupos=VENTAS,
        ejemplos=['¿cuántos puntos tiene el vendedor Ana?', 'ficha del vendedor VEN7K2M9P', 'quién patrocina a Juan'],
    )
    def _h_consultar_vendedor(self, vendedor):
        persona = self._b_vendedor(vendedor)
        inicio = self._b_mes_en_curso()
        Comision = self.env['dcasa.vend.comision']
        del_mes = Comision.search([('partner_id', '=', persona.id), ('anulada_en', '=', False),
                                   ('registrada_en', '>=', fields.Datetime.to_datetime(inicio))])
        ultimas = Comision.search([('partner_id', '=', persona.id)], limit=5)
        patrocinador = persona.dcasa_vendedor_patrocinador_id
        return {
            'vendedor': persona.display_name,
            'codigo': persona.dcasa_vendedor_codigo,
            'estado': dict(persona._fields['dcasa_vendedor_estado'].selection).get(persona.dcasa_vendedor_estado, ''),
            'tipo': TIPOS.get(persona.dcasa_vendedor_tipo, ''),
            'patrocinador': patrocinador.display_name if patrocinador else 'ninguno',
            'directos': persona.dcasa_vend_directos_count,
            'puntos_total': persona.dcasa_vend_saldo,
            'puntos_disponibles': persona.dcasa_vend_disponible,
            'puntos_por_liberar': persona.dcasa_vend_por_liberar,
            'ventas_del_mes': len(del_mes.filtered(lambda x: x.tipo == 'directa' and x.puntos)),
            'puntos_ganados_del_mes': sum(del_mes.mapped('puntos')),
            'ultimas_comisiones': [{'fecha': c.fecha(x.registrada_en), 'factura': x.name,
                                    'tipo': 'venta propia' if x.tipo == 'directa' else 'patrocinio',
                                    'puntos': x.puntos, 'resultado': RESULTADOS_TEXTO.get(x.resultado, x.resultado)}
                                   for x in ultimas],
        }

    @herramienta(
        nombre='resumen_programa_vendedores',
        descripcion='Cómo va el programa de vendedores este mes: ventas atribuidas, puntos pagados, costo contra la '
                    'venta, pasivo y comisiones que no pagaron (para revisar fraude).',
        parametros={}, nivel='lectura', categoria='clientes', grupos=GERENCIA,
        ejemplos=['cómo va el programa de vendedores', 'cuánto nos cuesta el programa de vendedores'],
    )
    def _h_resumen_programa_vendedores(self):
        reglas = R.cargar_reglas()
        inicio = fields.Datetime.to_datetime(self._b_mes_en_curso())
        Comision = self.env['dcasa.vend.comision']
        del_mes = Comision.search([('anulada_en', '=', False), ('registrada_en', '>=', inicio)])
        directas = del_mes.filtered(lambda x: x.tipo == 'directa')
        neto = sum(directas.mapped('neto_centavos'))
        puntos = sum(del_mes.mapped('puntos'))
        por_resultado = {}
        for comision in del_mes:
            por_resultado[comision.resultado] = por_resultado.get(comision.resultado, 0) + 1
        a_revisar = {RESULTADOS_TEXTO[k]: n for k, n in por_resultado.items() if k not in ('pagada', 'recortada')}
        Vendedores = self.env['res.partner'].search([('dcasa_vendedor_codigo', '!=', False)])
        mejores = {}
        for comision in del_mes:
            mejores[comision.partner_id] = mejores.get(comision.partner_id, 0) + comision.puntos
        pasivo = sum(self.env['dcasa.vend.movimiento']._saldos(Vendedores).values())
        falta = RV.falta_para_comisionar(reglas)
        return {
            'programa': 'encendido' if not falta else 'apagado o incompleto: ' + ' '.join(falta),
            'vendedores_activos': len(Vendedores.filtered(lambda p: p.dcasa_vendedor_estado == 'activo')),
            'vendedores_suspendidos': len(Vendedores.filtered(lambda p: p.dcasa_vendedor_estado == 'suspendido')),
            'ventas_con_vendedor_este_mes': len(directas.filtered('puntos')),
            'venta_neta_atribuida': c.moneda(neto / 100),
            'puntos_pagados': puntos,
            'costo_nominal': c.moneda(puntos / 100),
            'costo_como_porcentaje_de_la_venta': f'{puntos / neto * 100:.2f} %' if neto else 'sin ventas todavía',
            'puntos_que_se_deben_a_vendedores': pasivo,
            'comisiones_que_no_pagaron': a_revisar or 'ninguna',
            'quienes_mas_ganaron': [{'vendedor': p.display_name, 'puntos': n}
                                    for p, n in sorted(mejores.items(), key=lambda x: -x[1])[:5]],
            'nota': 'Los puntos son nominales (100 = $1); canjeados por mercancía cuestan solo el costo del producto.',
        }

    # ------------------------------------------------------------------
    # Sensibles
    # ------------------------------------------------------------------

    @herramienta(
        nombre='afiliar_vendedor',
        descripcion='Afilia a una persona como vendedor del programa (empleado o de afuera). Necesita su cédula y '
                    'celular en la ficha, y que la persona haya aceptado los términos.',
        parametros={
            'persona': {'type': 'string', 'description': 'Nombre, celular o cédula de la persona, p. ej. «Ana Gómez».'},
            'tipo': {'type': 'string', 'enum': list(TIPOS), 'description': 'empleado o externo (de afuera).'},
            'patrocinador': {'type': 'string', 'description': 'Código VEN… o nombre del vendedor que la trajo. '
                                                               'Opcional; se escribe una vez y no se cambia.'},
            'acepto_terminos': {'type': 'boolean', 'description': 'true solo si la persona ya leyó y aceptó los '
                                                                  'términos del programa.'},
        },
        requeridos=['persona', 'tipo', 'acepto_terminos'],
        nivel='sensible', categoria='clientes', grupos=VENTAS,
        ejemplos=['afilia a Ana Gómez como vendedora de afuera, ya aceptó los términos'],
    )
    def _h_afiliar_vendedor(self, persona, tipo, acepto_terminos, patrocinador=None):
        if tipo not in TIPOS:
            raise BrianError('El tipo es «empleado» o «externo» (persona de afuera).')
        ficha = self._b_contacto(persona, 'persona').commercial_partner_id
        padrino = self._b_vendedor(patrocinador) if patrocinador else self.env['res.partner']
        try:
            ficha._dcasa_afiliar_vendedor(tipo, padrino, autor=self.env.user.login,
                                          acepto_terminos=bool(acepto_terminos))
        except Exception as error:
            # Lo que falte (cédula, celular, términos, tope de directos…) vuelve al modelo con palabras del programa.
            raise BrianError(str(error.args[0] if error.args else error)) from error
        return {'mensaje': f'{ficha.display_name} ya es vendedor del programa.',
                'codigo': ficha.dcasa_vendedor_codigo, 'tipo': TIPOS[tipo],
                'patrocinador': padrino.display_name if padrino else 'ninguno',
                'nota': 'Con ese código entra a /socios con su celular y un PIN para ver su panel de vendedor.'}

    @herramienta(
        nombre='suspender_vendedor',
        descripcion='Suspende a un vendedor: no gana puntos ni canjea hasta que se reactive. Deja el motivo escrito.',
        parametros={'vendedor': PARAM_VENDEDOR,
                    'motivo': {'type': 'string', 'description': 'Por qué se suspende (queda en su ficha).'}},
        requeridos=['vendedor', 'motivo'],
        nivel='sensible', categoria='clientes', grupos=GERENCIA,
        ejemplos=['suspende al vendedor VEN7K2M9P, compraba con su propio código'],
    )
    def _h_suspender_vendedor(self, vendedor, motivo):
        persona = self._b_vendedor(vendedor)
        if persona.dcasa_vendedor_estado == 'suspendido':
            raise BrianError(f'{persona.display_name} ya está suspendido.')
        if not (motivo or '').strip():
            raise BrianError('Escribe el motivo: queda anotado en la ficha.')
        persona.action_dcasa_suspender_vendedor()
        persona._dcasa_dejar_rastro(f'Motivo de la suspensión: {motivo.strip()}')
        return {'mensaje': f'{persona.display_name} quedó suspendido como vendedor.'}

    @herramienta(
        nombre='reactivar_vendedor',
        descripcion='Reactiva a un vendedor suspendido.',
        parametros={'vendedor': PARAM_VENDEDOR}, requeridos=['vendedor'],
        nivel='sensible', categoria='clientes', grupos=GERENCIA,
        ejemplos=['reactiva al vendedor VEN7K2M9P'],
    )
    def _h_reactivar_vendedor(self, vendedor):
        persona = self._b_vendedor(vendedor)
        if persona.dcasa_vendedor_estado == 'activo':
            raise BrianError(f'{persona.display_name} ya está activo.')
        persona.action_dcasa_reactivar_vendedor()
        return {'mensaje': f'{persona.display_name} volvió a ser vendedor activo.'}

    @herramienta(
        nombre='ajustar_puntos_vendedor',
        descripcion='Ajuste manual de los puntos de un vendedor (suma o resta) con motivo que verá en su panel. '
                    'Queda como asiento en su libro de vendedor.',
        parametros={'vendedor': PARAM_VENDEDOR,
                    'puntos': {'type': 'integer', 'description': 'Positivo suma, negativo resta, p. ej. -200.'},
                    'motivo': {'type': 'string', 'description': 'Por qué, escrito para el vendedor.'}},
        requeridos=['vendedor', 'puntos', 'motivo'],
        nivel='sensible', categoria='clientes', grupos=GERENCIA,
        ejemplos=['súmale 300 puntos al vendedor Ana por la venta que no se registró'],
    )
    def _h_ajustar_puntos_vendedor(self, vendedor, puntos, motivo):
        persona = self._b_vendedor(vendedor)
        if not isinstance(puntos, int) or isinstance(puntos, bool) or not puntos:
            raise BrianError('Los puntos van en un número entero distinto de cero.')
        antes = persona.dcasa_vend_saldo
        try:
            self.env['dcasa.vend.ajuste.wizard'].create(
                {'partner_id': persona.id, 'puntos': puntos, 'motivo': (motivo or '').strip()}).action_confirmar()
        except Exception as error:
            raise BrianError(str(error.args[0] if error.args else error)) from error
        persona.invalidate_recordset(['dcasa_vend_saldo'])
        return {'mensaje': f'Ajuste de {puntos:+d} puntos a {persona.display_name}.', 'antes': antes,
                'ahora': persona.dcasa_vend_saldo, 'fecha': c.fecha(fields.Date.context_today(self))}


class BrianPoliticaVendedores(models.AbstractModel):
    _inherit = 'brian.politica'

    def _resumir_afiliar_vendedor(self, argumentos):
        """La tarjeta dice quién, de qué tipo y que la persona aceptó los términos, antes del clic."""
        if not argumentos.get('acepto_terminos'):
            return 'No se puede afiliar sin que la persona haya leído y aceptado los términos del programa.'
        tipo = TIPOS.get(argumentos.get('tipo'), argumentos.get('tipo'))
        lineas = [f'Afiliar a {argumentos.get("persona")} como vendedor ({tipo}).',
                  '• La persona ya leyó y aceptó los términos del programa.']
        if argumentos.get('patrocinador'):
            lineas.append(f'• La patrocina {argumentos["patrocinador"]} (se escribe una vez y no se cambia).')
        return '\n'.join(lineas)

    def _resumir_suspender_vendedor(self, argumentos):
        return (f'Suspender a {argumentos.get("vendedor")} como vendedor: no gana ni canjea puntos hasta que se '
                f'reactive.\n• Motivo: {argumentos.get("motivo")}')

    def _resumir_ajustar_puntos_vendedor(self, argumentos):
        return (f'Ajustar {argumentos.get("puntos"):+d} puntos de vendedor a {argumentos.get("vendedor")}.\n'
                f'• Motivo (lo verá el vendedor): {argumentos.get("motivo")}')
