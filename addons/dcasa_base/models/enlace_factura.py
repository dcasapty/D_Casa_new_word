"""El enlace factura ↔ pedido (``sale_line_ids``) solo lo escribe el código de ventas de Odoo.

La definición de «venta online» (``venta_online.py``) y todo lo que paga por ella (la comisión del sitio, el bono por
meta de las vendedoras y el programa de vendedores) lee de qué pedido salió cada línea de una factura: justo ese
enlace. Si cualquier persona con permiso sobre facturas pudiera escribirlo a mano, bastaría enlazar una factura de
mostrador a la línea de un pedido online para que se cobrara como venta del sitio (o para quitarle una venta de la
tienda a una vendedora). Tercera revisión adversarial, 2026-11-20: Caja, Nómina y Gerencia lo lograban, cada uno solo y
sin ``sudo``.

**Quién lo escribe.** Solo estos caminos, y cada uno pone la llave interna ``ENLACE`` en el contexto mientras trabaja
(un objeto, no ``True``: el contexto de una llamada RPC es JSON y nunca puede traerla):

* ``sale.order._create_invoices``: la factura que sale de un pedido (el botón «Crear factura», el pago en la página,
  lo que factura la tienda);
* el asistente de anticipos de Odoo (``sale.advance.payment.inv``): la factura del anticipo;
* ``account.move._reverse_moves``: la nota de crédito copia el enlace de la factura que revierte;
* el asistente de notas de crédito de Odoo (``account.move.reversal``), también con «Anular y crear una nueva factura».

Fuera de esos caminos, crear una línea de factura con ``sale_line_ids`` (o escribirlo, o escribir su otro lado,
``sale.order.line.invoice_lines``) da un error claro, con cualquier usuario y también con ``sudo``. Una línea de pedido
que ya se facturó tampoco cambia de pedido: si no, se podría mover la línea facturada de una venta de mostrador a un
pedido online.

**Un ``default_*`` del contexto tampoco lo fabrica** (cuarta revisión adversarial, 2026-11-20). Odoo aplica los
``default_<campo>`` del contexto DESPUÉS de mirar los valores que llegan a ``create``, y por RPC cualquiera los manda:
``account.move.line.create`` con ``context={'default_sale_line_ids': [[6, 0, [ids]]]}`` enlazaba una línea de 5,000 a
la línea de un pedido online de 1,000 sin pasar por el gancho de ``create`` (que solo miraba ``vals``). Caja, Nómina y
Gerencia, cada uno solo y sin ``sudo``, la publicaban, la cobraban y la comisión del sitio la contaba como venta del
sitio (500.00). Por eso ``default_get`` de las dos líneas descarta el enlace cuando no está la llave interna (igual que
``venta_online.default_get`` con las marcas de origen). Una factura o un pedido con líneas anidadas ya pasaba por el
gancho de ``create`` de la línea, así que ``default_invoice_line_ids`` y compañía quedan cubiertos.

No cambia ninguna factura que ya existe: el enlace que tienen se queda como está (no hay migración), y lo que se
escribe por los caminos de arriba no se toca. Duplicar una factura (``copy``) no copia el enlace (``copy=False``);
solo lo copian las notas de crédito, por el camino de arriba. Si algún día se instala ``account_debit_note``, su
asistente (``create_debit``) copia el enlace también y tendrá que ponerse en la lista de arriba.
"""
from odoo import Command, api, models
from odoo.exceptions import UserError

CLAVE_ENLACE = 'dcasa_base_enlace_de_factura'
# Un objeto, no ``True``: el contexto que llega por RPC es JSON y nunca puede traerlo.
ENLACE = object()


def _error(env):
    return UserError(env._(
        'El enlace de una factura con su pedido lo pone el sistema al facturar el pedido: no se escribe a mano. '
        'Para corregir una factura, anúlala con una nota de crédito y vuelve a facturar el pedido.'))


def _resultado(actuales, comandos):
    """El conjunto de ids que queda en un many2many con ``actuales`` al aplicar ``comandos`` (solo lo que cambia los
    enlaces: agregar, quitar, vaciar, reemplazar). Un renglón nuevo cuenta como un id que no existía."""
    ids = set(actuales)
    for comando in comandos or ():
        if not isinstance(comando, (list, tuple)) or not comando:
            ids.add(None)           # algo que no se entiende no se da por inofensivo
            continue
        tipo = comando[0]
        if tipo == Command.CREATE:
            ids.add(None)
        elif tipo in (Command.DELETE, Command.UNLINK):
            ids.discard(comando[1])
        elif tipo == Command.LINK:
            ids.add(comando[1])
        elif tipo == Command.CLEAR:
            ids.clear()
        elif tipo == Command.SET:
            ids = set(comando[2] or ())
    return ids


def _cambia(registros, campo, comandos):
    """¿Estos ``comandos`` agregan o quitan algún enlace en ``campo`` de ``registros``? Un valor vacío (el formulario de
    Odoo manda ``[(6, 0, [])]`` para un many2many sin nada) no cambia nada y no se frena."""
    if not comandos:
        return False
    if not registros:
        return bool(_resultado((), comandos))
    return any(_resultado(registro[campo].ids, comandos) != set(registro[campo].ids) for registro in registros)


class AccountMoveLineEnlace(models.Model):
    _inherit = 'account.move.line'

    def _dcasa_con_enlace_de_pedido(self):
        """Las mismas líneas con la llave que deja escribir el enlace con un pedido. Solo para el código que de verdad
        factura un pedido (y para las pruebas que arman una factura enlazada a mano)."""
        return self.with_context(**{CLAVE_ENLACE: ENLACE})

    def _dcasa_enlace_permitido(self):
        return self.env.context.get(CLAVE_ENLACE) is ENLACE

    @api.model
    def default_get(self, fields):
        """Un ``default_sale_line_ids`` del contexto (por RPC cualquiera lo manda) no fabrica el enlace: Odoo lo aplica
        después de ``create``, fuera del alcance del gancho que mira ``vals``. Solo la llave interna lo deja pasar."""
        valores = super().default_get(fields)
        if self.env.context.get(CLAVE_ENLACE) is not ENLACE:
            valores.pop('sale_line_ids', None)
        return valores

    @api.model_create_multi
    def create(self, vals_list):
        if not self._dcasa_enlace_permitido() and any(
                _cambia(self.browse(), 'sale_line_ids', vals.get('sale_line_ids')) for vals in vals_list):
            raise _error(self.env)
        return super().create(vals_list)

    def write(self, vals):
        if 'sale_line_ids' in vals and not self._dcasa_enlace_permitido() and _cambia(
                self, 'sale_line_ids', vals['sale_line_ids']):
            raise _error(self.env)
        return super().write(vals)


class SaleOrderLineEnlace(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def default_get(self, fields):
        """El otro lado del enlace: un ``default_invoice_lines`` del contexto tampoco lo fabrica (ver la línea de
        factura)."""
        valores = super().default_get(fields)
        if self.env.context.get(CLAVE_ENLACE) is not ENLACE:
            valores.pop('invoice_lines', None)
        return valores

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(CLAVE_ENLACE) is not ENLACE and any(
                _cambia(self.browse(), 'invoice_lines', vals.get('invoice_lines')) for vals in vals_list):
            raise _error(self.env)
        return super().create(vals_list)

    def write(self, vals):
        permitido = self.env.context.get(CLAVE_ENLACE) is ENLACE
        if 'invoice_lines' in vals and not permitido and _cambia(self, 'invoice_lines', vals['invoice_lines']):
            raise _error(self.env)
        if 'order_id' in vals and not permitido:
            movidas = self.filtered(lambda linea: linea.invoice_lines and linea.order_id.id != vals['order_id'])
            if movidas:
                raise UserError(self.env._('Una línea que ya se facturó no cambia de pedido.'))
        return super().write(vals)


class SaleOrderEnlace(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, *args, **kwargs):
        facturas = super(SaleOrderEnlace, self.with_context(**{CLAVE_ENLACE: ENLACE}))._create_invoices(
            *args, **kwargs)
        return facturas.with_env(self.env) if facturas else facturas      # quien llamó no hereda la llave


class AccountMoveEnlace(models.Model):
    _inherit = 'account.move'

    def _dcasa_con_enlace_de_pedido(self):
        """Las mismas facturas con la llave que deja escribir el enlace con un pedido (ver la línea de factura)."""
        return self.with_context(**{CLAVE_ENLACE: ENLACE})

    def _reverse_moves(self, *args, **kwargs):
        notas = super(AccountMoveEnlace, self.with_context(**{CLAVE_ENLACE: ENLACE}))._reverse_moves(*args, **kwargs)
        return notas.with_env(self.env) if notas else notas


class SaleAdvancePaymentInvEnlace(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _create_invoices(self, sale_orders):
        facturas = super(SaleAdvancePaymentInvEnlace, self.with_context(**{CLAVE_ENLACE: ENLACE}))._create_invoices(
            sale_orders)
        return facturas.with_env(self.env) if facturas else facturas


class AccountMoveReversalEnlace(models.TransientModel):
    _inherit = 'account.move.reversal'

    def reverse_moves(self, *args, **kwargs):
        return super(AccountMoveReversalEnlace, self.with_context(**{CLAVE_ENLACE: ENLACE})).reverse_moves(
            *args, **kwargs)
