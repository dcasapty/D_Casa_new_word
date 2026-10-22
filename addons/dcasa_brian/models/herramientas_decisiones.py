"""Brian y las decisiones D1 y D3 de la gerencia: descuento mayor al tope con la clave de Gerencia, los saldos de
centavos y los abonos por vencer.

* La clave de un descuento le llega a cada persona de Gerencia por **Telegram**, por el mismo bot de Brian, solo a los
  chats vinculados a su usuario (``brian.telegram.enlace``) y respetando la lista de chats permitidos. Sin el bot o
  sin nadie de Gerencia vinculado no sale nada: la pantalla dice que hay que pedírselo en persona.
* Las herramientas corren como la persona: pedir y usar la clave pasan por las mismas comprobaciones que la pantalla
  (``dcasa.descuento.autorizacion``); aprobar o rechazar es de Gerencia; cerrar centavos, de Gerencia o contabilidad.
"""
from odoo import api, models

from . import herramientas_comun as c
from .registro import BrianError, herramienta

INTERNO = ('base.group_user',)
GERENTE_VENTAS = ('sales_team.group_sale_manager',)
VEN_ABONOS = (('dcasa_base.group_caja', 'account.group_account_user', 'sales_team.group_sale_manager'),)
CIERRAN_CENTAVOS = (('dcasa_base.group_gerencia', 'account.group_account_user', 'account.group_account_manager',
                     'base.group_system'),)
PARAM_COTIZACION = {'type': 'string', 'description': 'Número de la cotización («S00123») o el cliente.'}
ESTADOS = {'pendiente': 'esperando la clave', 'usada': 'aplicado', 'rechazada': 'rechazado', 'vencida': 'venció',
           'bloqueada': 'bloqueado por claves equivocadas', 'cancelada': 'cancelado'}


class DcasaDescuentoAutorizacion(models.Model):
    _inherit = 'dcasa.descuento.autorizacion'

    def _dcasa_enviar_claves(self, claves):
        """Por Telegram, a los chats vinculados de cada persona de Gerencia, su propia clave."""
        enviados = super()._dcasa_enviar_claves(claves)
        Enlace = self.env['brian.telegram.enlace'].sudo()
        if not Enlace._token():
            return enviados
        for usuario, codigo in claves.items():
            texto = self._dcasa_texto_para_gerencia(codigo)
            for enlace in Enlace.search([('user_id', '=', usuario.id), ('activo', '=', True)]):
                if Enlace._enlace_vigente(enlace.chat_id) and Enlace._enviar(enlace.chat_id, texto):
                    enviados |= usuario
        return enviados


class BrianHerramientasAutorizaciones(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_solicitud(self, cotizacion, estados=('pendiente', 'vencida')):
        orden = self._b_venta(cotizacion)
        solicitud = self.env['dcasa.descuento.autorizacion'].search(
            [('order_id', '=', orden.id), ('estado', 'in', estados)], limit=1)
        if not solicitud:
            raise BrianError(f'{orden.name} no tiene un descuento esperando la autorización de Gerencia.')
        return solicitud

    @api.model
    def _b_fila_solicitud(self, solicitud):
        tipo = (f'{solicitud.porcentaje:g} %' if solicitud.tipo == 'porcentaje' else c.moneda(solicitud.monto))
        return {
            'cotizacion': solicitud.order_id.name, 'cliente': solicitud.partner_id.display_name,
            'pidio': solicitud.solicitante_id.name, 'descuento': tipo, 'motivo': solicitud.motivo,
            'total_antes': c.moneda(solicitud.total_antes), 'total_despues': c.moneda(solicitud.total_despues),
            'estado': ESTADOS.get(solicitud.estado, solicitud.estado),
            'autorizo': solicitud.aprobador_id.name or '',
        }

    @herramienta(
        nombre='pedir_descuento_a_gerencia',
        descripcion='Pide a Gerencia un descuento MAYOR a tu tope para una cotización: a cada persona de Gerencia le '
                    'llega por Telegram una clave. Cuando te la den, usa aplicar_descuento_con_clave.',
        parametros={
            'cotizacion': PARAM_COTIZACION,
            'porcentaje': {'type': 'number', 'description': 'Descuento en % sobre el total, p. ej. 15. O usa monto.'},
            'monto': {'type': 'number', 'description': 'Descuento de importe fijo en dólares, p. ej. 120.'},
            'motivo': {'type': 'string', 'description': 'Por qué, para Gerencia, p. ej. «lleva la sala completa».'},
        },
        requeridos=['cotizacion', 'motivo'],
        nivel='construccion', categoria='ventas', grupos=INTERNO,
        ejemplos=['pide a Gerencia 15 % de descuento para S00123 porque lleva todo el juego'],
    )
    def _h_pedir_descuento_a_gerencia(self, cotizacion, motivo, porcentaje=None, monto=None):
        if bool(porcentaje) == bool(monto):
            raise BrianError('Dime el descuento en porcentaje o en monto (uno de los dos).')
        orden = self._b_venta(cotizacion)
        tipo = 'porcentaje' if porcentaje else 'monto'
        solicitud = self.env['dcasa.descuento.autorizacion']._dcasa_pedir(
            orden, tipo, float(porcentaje or 0.0), float(monto or 0.0), motivo or '')
        if solicitud.enviada_a:
            mensaje = (f'Le mandé la clave por Telegram a {solicitud.enviada_a}. Cuando te la den, dímela y aplico el '
                       'descuento (vale una vez y vence pronto).')
        else:
            mensaje = ('Telegram no está conectado para Gerencia: no salió ninguna clave. Pídele a Gerencia que lo '
                       'apruebe en persona (Ventas › Descuentos por autorizar).')
        return {'mensaje': mensaje, **self._b_fila_solicitud(solicitud), 'vence': c.fecha(solicitud.vence)}

    @herramienta(
        nombre='aplicar_descuento_con_clave',
        descripcion='Aplica el descuento que pediste a Gerencia, con la clave de 6 números que te dieron.',
        parametros={'cotizacion': PARAM_COTIZACION,
                    'clave': {'type': 'string', 'description': 'La clave de 6 números que te dio Gerencia.'}},
        requeridos=['cotizacion', 'clave'],
        nivel='construccion', categoria='ventas', grupos=INTERNO,
        ejemplos=['la clave para S00123 es 482913'],
    )
    def _h_aplicar_descuento_con_clave(self, cotizacion, clave):
        solicitud = self._b_solicitud(cotizacion, estados=('pendiente', 'vencida', 'bloqueada'))
        listo, motivo = solicitud._dcasa_usar_clave(clave)
        if not listo:
            raise BrianError(motivo)
        return {'mensaje': f'Listo: descuento aplicado en {solicitud.order_id.name}.',
                **self._b_fila_solicitud(solicitud)}

    @herramienta(
        nombre='descuentos_por_autorizar',
        descripcion='Los descuentos mayores al tope que pidieron las vendedoras o Caja y esperan a Gerencia.',
        parametros={'limite': c.PARAM_LIMITE},
        nivel='lectura', categoria='ventas', grupos=GERENTE_VENTAS,
        ejemplos=['¿qué descuentos esperan mi autorización?'],
    )
    def _h_descuentos_por_autorizar(self, limite=10):
        solicitudes = self.env['dcasa.descuento.autorizacion'].search(
            [('estado', 'in', ('pendiente', 'vencida'))], limit=c.limite(limite))
        return {'esperando': len(solicitudes), 'descuentos': [self._b_fila_solicitud(s) for s in solicitudes]}

    @herramienta(
        nombre='decidir_descuento',
        descripcion='Gerencia aprueba (y se aplica) o rechaza un descuento pedido para una cotización.',
        parametros={'cotizacion': PARAM_COTIZACION,
                    'decision': {'type': 'string', 'enum': ['aprobar', 'rechazar'], 'description': 'Qué decides.'}},
        requeridos=['cotizacion', 'decision'],
        nivel='sensible', categoria='ventas', grupos=GERENTE_VENTAS,
        ejemplos=['aprueba el descuento de S00123', 'rechaza el descuento de la cotización de Ana'],
    )
    def _h_decidir_descuento(self, cotizacion, decision):
        solicitud = self._b_solicitud(cotizacion)
        if decision == 'aprobar':
            solicitud.action_aprobar()
            mensaje = f'Aprobado y aplicado en {solicitud.order_id.name}.'
        elif decision == 'rechazar':
            solicitud.action_rechazar()
            mensaje = f'Rechazado el descuento de {solicitud.order_id.name}.'
        else:
            raise BrianError('La decisión es «aprobar» o «rechazar».')
        return {'mensaje': mensaje, **self._b_fila_solicitud(solicitud)}

    # ------------------------------------------------------------------
    # Saldos de centavos
    # ------------------------------------------------------------------

    @herramienta(
        nombre='saldos_de_centavos',
        descripcion='Facturas y cobros de clientes que quedaron abiertos por 1 a 5 centavos de redondeo.',
        parametros={'limite': c.PARAM_LIMITE},
        nivel='lectura', categoria='contabilidad', grupos=CIERRAN_CENTAVOS,
        ejemplos=['¿hay facturas que quedaron debiendo un centavo?'],
    )
    def _h_saldos_de_centavos(self, limite=10):
        Asistente = self.env['dcasa.saldos.centavos']
        lineas = Asistente._dcasa_buscar()
        Apunte = self.env['account.move.line']
        filas = []
        for valores in lineas[:c.limite(limite)]:
            apunte = Apunte.browse(valores['move_line_id'])
            filas.append({'documento': apunte.move_id.name, 'cliente': apunte.partner_id.display_name or '',
                          'saldo': c.moneda(valores['saldo']), 'tipo': valores['tipo']})
        return {'cuantos': len(lineas), 'saldos': filas,
                'nota': 'Para cerrarlos con su ajuste por redondeo: cerrar_saldos_de_centavos (o Contabilidad › '
                        'Clientes › Saldos de centavos).' if lineas else 'No hay saldos de centavos.'}

    @herramienta(
        nombre='cerrar_saldos_de_centavos',
        descripcion='Cierra TODOS los saldos de 1 a 5 centavos de redondeo con su asiento de ajuste (cada documento '
                    'queda con una nota).',
        nivel='sensible', categoria='contabilidad', grupos=CIERRAN_CENTAVOS,
        ejemplos=['cierra los saldos de un centavo'],
    )
    def _h_cerrar_saldos_de_centavos(self):
        Asistente = self.env['dcasa.saldos.centavos']
        asistente = Asistente.create(Asistente.default_get(['linea_ids', 'company_id']))
        if not asistente.linea_ids:
            return {'mensaje': 'No hay saldos de centavos que cerrar.'}
        if asistente.falta:
            raise BrianError(asistente.falta)
        cuantos = len(asistente.linea_ids)
        asistente.action_cerrar()
        return {'mensaje': f'Cerré {cuantos} saldos de centavos con su ajuste por redondeo.'}

    # ------------------------------------------------------------------
    # Abonos por vencer (D3)
    # ------------------------------------------------------------------

    @herramienta(
        nombre='abonos_por_vencer',
        descripcion='Abonos que vencen en los próximos días (o ya vencieron): cliente, factura, lo que falta, la '
                    'fecha, si ya salió el recordatorio por correo y el enlace para escribirle por WhatsApp.',
        parametros={'limite': c.PARAM_LIMITE},
        nivel='lectura', categoria='contabilidad', grupos=VEN_ABONOS,
        ejemplos=['¿qué abonos vencen esta semana?', 'abonos vencidos'],
    )
    def _h_abonos_por_vencer(self, limite=10):
        Factura = self.env['account.move']
        facturas = Factura.search([('move_type', '=', 'out_invoice'), ('dcasa_abono_pronto', '=', True)],
                                  order='dcasa_abono_vence, id', limit=c.limite(limite))
        filas = []
        for factura in facturas:
            fila = {'cliente': factura.partner_id.display_name, 'factura': factura.name,
                    'le_falta': c.moneda(factura.amount_residual), 'vence': c.fecha(factura.dcasa_abono_vence),
                    'dias': factura.dcasa_abono_dias,
                    'whatsapp': factura.action_dcasa_abono_whatsapp()['url']}
            if 'dcasa_recordatorio' in factura._fields:
                fila['recordatorio_por_correo'] = factura.dcasa_recordatorio or 'todavía no'
            filas.append(fila)
        return {'dias_de_aviso': Factura._dcasa_aviso_dias(), 'abonos': filas,
                'nota': 'El enlace de WhatsApp abre el mensaje listo: lo manda una persona desde su teléfono.'
                if filas else 'Ningún abono vence en los próximos días.'}
