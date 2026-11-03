"""El origen «Chatbot» de una cotización (ver ``dcasa_interfaz/models/origen.py``): la armó Juan, el asistente de los
clientes, con su herramienta ``cotizar``. Su usuario técnico (``user_juan``) es quien la creó; lo que una vendedora
después le cambie no le quita el origen."""
from odoo import api, models


class SaleOrderOrigenJuan(models.Model):
    _inherit = 'sale.order'

    def _compute_dcasa_origen(self):
        super()._compute_dcasa_origen()
        juan = self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False)
        if juan:
            for orden in self.filtered(lambda o: o.create_uid == juan):
                orden.dcasa_origen = 'chatbot'

    @api.model
    def _dcasa_marcar_origen_chatbot(self):
        """Al instalar o actualizar: las cotizaciones que Juan armó antes de que existiera el origen (o mientras este
        módulo todavía no estaba cargado) pasan a «Chatbot», y sus facturas con ellas."""
        juan = self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False)
        if not juan:
            return
        ordenes = self.sudo().with_context(active_test=False).search(
            [('create_uid', '=', juan.id), ('dcasa_origen', '!=', 'chatbot')])
        if not ordenes:
            return
        self.env.add_to_compute(self._fields['dcasa_origen'], ordenes)
        ordenes.flush_recordset(['dcasa_origen'])
        facturas = ordenes.order_line.invoice_lines.move_id
        if facturas:
            self.env.add_to_compute(facturas._fields['dcasa_origen'], facturas)
            facturas.flush_recordset(['dcasa_origen'])
