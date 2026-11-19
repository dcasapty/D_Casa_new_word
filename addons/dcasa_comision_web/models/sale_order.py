"""Lo que le toca decidir a la comisión web sobre cada pedido (la definición vive en
``dcasa_base.models.venta_online``).

* **Desde cuándo** una venta online deja de ser de una vendedora: el día de la primera versión de las reglas.
* **Si la llevó una vendedora**: al confirmar un pedido que nació en la web, se mira el chat de Juan. Si una
  vendedora le
  escribió al cliente en los 30 días anteriores (la misma ventana con que el panel de Juan atribuye las ventas), la
  venta
  fue de ella, aunque el pedido salga de la página: no es venta online. Si solo contestó el asistente, o nadie, la
  persona
  compró sola: es venta online. Andrés manda sobre esto: toda venta de Andrés cuenta.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

from .movimiento import dia_de_panama

_logger = logging.getLogger(__name__)
VENTANA_DE_CHAT_DIAS = 30


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _dcasa_online_desde(self, company=None):
        primera = self.env['dcasa.web.reglas']._primera(company or self.env.company)
        return dia_de_panama(primera.rige_desde) if primera else False

    def _dcasa_chat_antes_de_comprar(self):
        """``(habló el asistente, escribió una vendedora)`` con el cliente de este pedido en los días anteriores a que
        se confirmó. Los mensajes del cliente no cuentan, y tampoco las notas internas."""
        self.ensure_one()
        cliente = self.partner_id.commercial_partner_id
        if not cliente or cliente._is_public():
            return False, False
        fin = self.date_order or fields.Datetime.now()
        self.env.cr.execute("""
            SELECT COALESCE(BOOL_OR(m.autor = 'bot'), FALSE), COALESCE(BOOL_OR(m.autor = 'vendedora'), FALSE)
              FROM dcasa_mensaje m
              JOIN dcasa_conversacion c ON c.id = m.conversacion_id
              JOIN res_partner p ON p.id = c.partner_id
             WHERE p.commercial_partner_id = %s AND m.tipo = 'mensaje' AND m.autor IN ('bot', 'vendedora')
               AND m.ts >= %s AND m.ts <= %s""", [cliente.id, fin - timedelta(days=VENTANA_DE_CHAT_DIAS), fin])
        hablo_juan, escribio_vendedora = self.env.cr.fetchone()
        return bool(hablo_juan), bool(escribio_vendedora)

    def _action_confirm(self):
        resultado = super()._action_confirm()
        for orden in self.filtered(lambda o: o.dcasa_nacio_en_web and not o.dcasa_via_andres):
            try:
                with self.env.cr.savepoint():
                    if orden._dcasa_chat_antes_de_comprar()[1]:
                        orden._dcasa_escribir_marca(dcasa_llevada_por_vendedora=True)
            except Exception:  # noqa: BLE001 — confirmar una venta nunca falla por esto
                _logger.exception('Comisión web: no se pudo revisar si una vendedora llevó el pedido %s', orden.name)
        return resultado
