"""Brian también manda por correo la factura o la cotización (docs/LEEME_PRIMERO.md §4: todo lo nuevo, Brian lo usa).

Y desde el 2026-11-06 («Brian al día») dice cómo va el correo a clientes (``estado_del_correo``): si sale o por qué no,
y la cola de ``dcasa.correo.envio`` de los últimos días (lo mismo que *Ventas › Configuración › Correos a clientes
(enviados)*). La clave de Resend nunca se lee ni se muestra (ni sus últimas letras).
"""
from datetime import timedelta

from odoo import fields, models
from odoo.addons.dcasa_brian.models.herramientas_comun import ZONA_PANAMA
from odoo.addons.dcasa_brian.models.herramientas_contabilidad import FACTURACION, PARAM_FACTURA
from odoo.addons.dcasa_brian.models.herramientas_ventas import PARAM_VENTA
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.exceptions import UserError

VENTAS = ('sales_team.group_sale_salesman',)
GERENCIA_O_ADMIN = (('dcasa_base.group_gerencia', 'base.group_system'),)
MAX_FALLIDOS = 5


class BrianHerramientasCorreo(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @herramienta(
        nombre='enviar_factura_por_correo',
        descripcion="Le manda al cliente su factura publicada en PDF por correo, con la marca de D'CASA. Si todavía "
                    'debe algo, sale como abono: lo que pagó, lo que le falta y hasta cuándo.',
        parametros={'factura': PARAM_FACTURA}, requeridos=['factura'],
        nivel='construccion', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['mándale por correo la factura INV/2026/00012', 'envíale a Ana su factura por correo'],
    )
    def _h_enviar_factura_por_correo(self, factura):
        movimiento = self._b_factura(factura, dominio=[('move_type', '=', 'out_invoice')])
        try:
            envio = movimiento._dcasa_correo_enviar_factura()
        except UserError as error:
            raise BrianError(error.args[0] if error.args else str(error)) from None
        return {'mensaje': f'Listo: la factura {movimiento.name} sale por correo en unos minutos, con su PDF.',
                'correo_a': movimiento._dcasa_correo_destino().email_normalized or '',
                'tipo': envio.tipo}

    @herramienta(
        nombre='enviar_cotizacion_por_correo',
        descripcion="Le manda al cliente la cotización (borrador o enviada) en PDF por correo, con la marca de "
                    "D'CASA. Si estaba en borrador, pasa a «Enviada»; no se confirma.",
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENTAS,
        ejemplos=['mándale la cotización S00012 por correo'],
    )
    def _h_enviar_cotizacion_por_correo(self, venta):
        orden = self._b_venta(venta)
        try:
            envio = orden._dcasa_correo_enviar_cotizacion()
        except UserError as error:
            raise BrianError(error.args[0] if error.args else str(error)) from None
        return {'mensaje': f'Listo: la cotización {orden.name} sale por correo en unos minutos, con su PDF.',
                'correo_a': envio.correo or '', 'estado': orden.state}

    @herramienta(
        nombre='estado_del_correo',
        descripcion='Cómo va el correo a los clientes (facturas, abonos, bienvenidas, cotizaciones y recordatorios): '
                    'si está saliendo o por qué no, cuántos salieron, cuántos no y los que fallaron.',
        parametros={'dias': {'type': 'integer', 'description': 'Los últimos N días (1 a 90). Por defecto 7.'}},
        nivel='lectura', categoria='contabilidad', grupos=GERENCIA_O_ADMIN, texto_externo=True,   # nombres de clientes
        ejemplos=['¿están saliendo los correos a los clientes?', '¿qué correos fallaron esta semana?'],
    )
    def _h_estado_del_correo(self, dias=7):
        if isinstance(dias, bool) or not isinstance(dias, int) or not 1 <= dias <= 90:
            raise BrianError('«dias» va de 1 a 90.')
        Correo = self.env['dcasa.correo']
        Envio = self.env['dcasa.correo.envio']   # como quien pregunta: Gerencia y administradores lo leen
        config = Correo._config()
        desde = fields.Datetime.now() - timedelta(days=dias)
        tipos = dict(Envio._fields['tipo'].selection)
        estados = dict(Envio._fields['estado'].selection)
        cuentas = {}
        for tipo, estado, n in Envio._read_group([('create_date', '>=', desde)], ['tipo', 'estado'], ['__count']):
            cuentas.setdefault(tipos.get(tipo, tipo), {})[estados.get(estado, estado)] = n
        panama = self.with_context(tz=ZONA_PANAMA)   # las fechas, en hora de Panamá (no en UTC)
        problemas = Envio.search([('create_date', '>=', desde), ('estado', 'in', ('fallido', 'omitido'))],
                                 limit=MAX_FALLIDOS)
        return {
            'sale_correo_a_clientes': Correo._activo_para_clientes(),
            'por_que_no': Correo._motivo_apagado() or '',
            'que_se_manda': {'al_pagar': config['al_pagar'], 'bienvenida': config['bienvenida'],
                             'recordatorio_de_abono': config['recordatorio']},
            'periodo': f'últimos {dias} días',
            'por_tipo': cuentas,
            'ultimos_que_no_salieron': [{
                'tipo': tipos.get(e.tipo, e.tipo), 'estado': estados.get(e.estado, e.estado),
                'cliente': e.partner_id.display_name or '', 'motivo': (e.motivo or '')[:200],
                'fecha': fields.Datetime.context_timestamp(panama, e.create_date).strftime('%d/%m/%Y'),
            } for e in problemas],
            'donde': 'Ventas › Configuración › Correos a clientes (enviados); se enciende en Ventas › Configuración › '
                     'Correo a clientes.',
            'nota': '«No se envió» casi siempre es un cliente sin correo bien escrito o el correo apagado: se corrige '
                    'su ficha y el siguiente pago lo vuelve a armar. Brian no reenvía en bloque.',
        }
