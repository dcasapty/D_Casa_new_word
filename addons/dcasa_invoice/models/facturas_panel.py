"""Panel de facturas de Facturación › Tablero: dos tarjetas, «Facturas de clientes» y «Facturas de proveedores».

Cada tarjeta cuenta lo que importa (borradores, por cobrar o por pagar, vencidas) y cada número abre la lista ya
filtrada, a un clic. Los números y la lista salen del MISMO dominio (``_dominios``), así que siempre coinciden.

Permisos: las facturas de clientes, para quien ya puede verlas; las de proveedores, solo contabilidad, Gerencia y
administradores (docs/PERMISOS.md). La vendedora ni ve la tarjeta ni puede pedirla por RPC. Los conteos se hacen
como quien mira, sin ``sudo()``: las reglas de registro también cierran el paso.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.misc import format_amount

TARJETAS = {
    'clientes': {
        'tipo': 'out_invoice', 'titulo': 'Facturas de clientes', 'accion': 'account.action_move_out_invoice_type',
        'pendientes': 'Por cobrar', 'icono': 'fa-users',
        'orden': ('borradores', 'pendientes', 'vencidas'),
    },
    'proveedores': {
        'tipo': 'in_invoice', 'titulo': 'Facturas de proveedores', 'accion': 'account.action_move_in_invoice_type',
        'pendientes': 'Por pagar', 'icono': 'fa-truck',
        'orden': ('pendientes', 'vencidas', 'borradores'),
    },
}
NOMBRES = {'borradores': 'Borradores', 'vencidas': 'Vencidas'}


class DcasaFacturasPanel(models.AbstractModel):
    _name = 'dcasa.facturas.panel'
    _description = 'Panel de facturas de clientes y de proveedores'

    @api.model
    def _puede(self, tarjeta):
        """Clientes: quien ya puede ver facturas. Proveedores: contabilidad, Gerencia y administradores."""
        usuario = self.env.user
        if tarjeta == 'clientes':
            return self.env['account.move'].has_access('read') and (
                usuario.has_group('account.group_account_invoice') or usuario.has_group('account.group_account_readonly'))
        return self.env['account.move'].has_access('read') and (
            usuario.has_group('account.group_account_readonly') or usuario.has_group('account.group_account_manager'))

    @api.model
    def _dominios(self, tarjeta):
        base = [('move_type', '=', TARJETAS[tarjeta]['tipo'])]
        pendientes = base + [('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]
        return {
            'todas': base,
            'borradores': base + [('state', '=', 'draft')],
            'pendientes': pendientes,
            'vencidas': pendientes + [('invoice_date_due', '<', fields.Date.context_today(self))],
        }

    @api.model
    def _fila(self, tarjeta, clave, dominio):
        [(cuenta, residuo)] = self.env['account.move']._read_group(dominio, [], ['__count', 'amount_residual_signed:sum'])
        fila = {'clave': clave, 'texto': NOMBRES.get(clave) or TARJETAS[tarjeta]['pendientes'], 'cuenta': cuenta,
                'monto': None, 'alerta': clave == 'vencidas' and cuenta > 0}
        if clave != 'borradores':
            fila['monto'] = format_amount(self.env, abs(residuo or 0.0), self.env.company.currency_id)
        return fila

    @api.model
    def obtener_datos(self):
        """Las tarjetas que quien mira puede ver, con sus conteos."""
        tarjetas = []
        for clave, config in TARJETAS.items():
            if not self._puede(clave):
                continue
            dominios = self._dominios(clave)
            tarjetas.append({
                'clave': clave, 'titulo': config['titulo'], 'icono': config['icono'],
                'filas': [self._fila(clave, fila, dominios[fila]) for fila in config['orden']],
            })
        return {'tarjetas': tarjetas}

    @api.model
    def abrir(self, tarjeta, fila='todas'):
        """La lista de facturas de la tarjeta (o de una de sus filas), con el mismo dominio que el conteo."""
        if tarjeta not in TARJETAS or not self._puede(tarjeta):
            raise AccessError(self.env._('No tienes permiso para ver estas facturas.'))
        dominios = self._dominios(tarjeta)
        if fila not in dominios:
            fila = 'todas'
        config = TARJETAS[tarjeta]
        accion = self.env['ir.actions.actions']._for_xml_id(config['accion'])
        accion['domain'] = dominios[fila]
        accion['name'] = accion['display_name'] = config['titulo'] if fila == 'todas' else '%s · %s' % (
            config['titulo'], NOMBRES.get(fila) or config['pendientes'])
        return accion
