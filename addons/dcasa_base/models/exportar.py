"""Exportar a Excel: qué listas puede bajar quien trae el permiso «Exportar» sin ser administrador.

El permiso de Odoo (``base.group_allow_export``) es global: abre el «Acción › Exportar» de **toda** lista. Gerencia lo
recibió el 2026-11-19 por un pedido del jefe: bajar las facturas con su forma de pago. Para que eso no sea un volcado
de todo lo que Gerencia ya ve en pantalla (empleados con datos privados, el chatter de todos los documentos, adjuntos,
cuentas bancarias de los contactos, conversaciones, todos los clientes…), ``export_data`` (y con él los botones
``/web/export/xlsx`` y ``/web/export/csv``, que lo llaman) queda así:

* **Administradores** (``env.is_admin()``: el grupo de Ajustes o el sistema, con ``sudo`` incluido): como siempre, todo.
* **Quien trae el permiso sin ser administrador** (Gerencia): solo las listas de ``MODELOS_QUE_EXPORTA_GERENCIA``,
  finanzas y ventas. Cualquier otra, ``AccessError`` en español sencillo.
* Seguir relaciones sirve: de una factura se baja ``partner_id/name``, ``invoice_user_id`` o el producto de una línea.
  Lo que no se atraviesa son los modelos de ``NO_SE_ATRAVIESAN`` (chatter, adjuntos, empleados, cuentas bancarias de
  contactos…): por ahí se llegaría al mismo volcado desde una factura. Y por una relación tampoco se piden los
  identificadores externos (``partner_id/id``): Odoo los CREA al exportarlos, también de modelos que no se pueden leer.

La lista vive aquí, en un solo lugar. Si Gerencia necesita bajar otra, se agrega aquí con su motivo y su prueba
(``tests/test_exportar.py``, ``tests/test_revision_exportar.py``).

Se pone en ``_export_rows`` y no en ``export_data``: es privado (no suma nada a la superficie RPC de
``test_superficie_rpc``), lo llama ``export_data`` para todos los modelos y lo recorre también por las relaciones.
Odoo ya hace lo mismo con el chatter: ``mail.message.export_data`` solo deja exportar a los administradores.

**No cubre** la ruta experimental ``/json/1/…`` del núcleo (también pide el permiso de exportar): solo existe si hay
datos de demostración o el parámetro ``web.json.enabled``, y entra con una llave de API (``auth='bearer'``). Debe seguir
apagada en producción.
"""
from odoo import models
from odoo.exceptions import AccessError

# Las listas que Gerencia (y quien traiga el permiso sin ser administrador) puede bajar a Excel.
#   Facturas y sus pagos: account.move (facturas, notas de crédito, recibos y sus asientos), account.move.line (las
#   líneas de factura y los apuntes) y account.payment (los pagos y cobros: con qué diario se pagó cada factura).
#   Ventas: sale.order (cotizaciones y pedidos) y sale.order.line (lo que se vendió, línea por línea).
# Quedan fuera a propósito: res.partner (la lista de todos los clientes con celular y correo), hr.* (empleados),
# mail.* (chatter), ir.attachment, res.users, res.partner.bank y las conversaciones.
MODELOS_QUE_EXPORTA_GERENCIA = (
    'account.move',
    'account.move.line',
    'account.payment',
    'sale.order',
    'sale.order.line',
)

# Modelos por los que no se sigue una relación al exportar (prefijo del nombre técnico).
NO_SE_ATRAVIESAN = (
    'hr.',                  # empleados y su nómina
    'mail.',                # chatter, seguidores y actividades de cualquier documento
    'ir.',                  # adjuntos, parámetros, tareas programadas, identificadores
    'res.partner.bank',     # cuentas bancarias de los contactos
    'res.users.',           # llaves de API, identidades, registros de entrada
    'res.groups',
    'bus.',
    'dcasa.conversacion',   # lo que dijeron los clientes a Juan
    'brian.',
)


class Base(models.AbstractModel):
    _inherit = 'base'

    def _export_rows(self, fields, *, _is_toplevel_call=True):
        self._dcasa_exigir_que_se_puede_exportar(fields, _is_toplevel_call)
        return super()._export_rows(fields, _is_toplevel_call=_is_toplevel_call)

    def _dcasa_exigir_que_se_puede_exportar(self, fields, es_la_lista):
        """Niega, con un texto sencillo, lo que quien exporta sin ser administrador no puede bajar."""
        if self.env.is_admin():
            return
        if es_la_lista:
            if self._name not in MODELOS_QUE_EXPORTA_GERENCIA:
                raise AccessError(self.env._(
                    'Ese Excel solo lo bajan los administradores: pídeselo a quien administra el sistema.'))
            return
        pide_id_externo = any(ruta and ruta[0] == 'id' for ruta in fields)
        if self._name.startswith(NO_SE_ATRAVIESAN) or (
                pide_id_externo and self._name not in MODELOS_QUE_EXPORTA_GERENCIA):
            raise AccessError(self.env._(
                'Ese dato no se puede bajar en un Excel: solo lo bajan los administradores.'))
