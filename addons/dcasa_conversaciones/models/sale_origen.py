"""El origen «Chatbot» de una cotización (ver ``dcasa_interfaz/models/origen.py``): la armó Juan, el asistente de los
clientes, con su herramienta ``cotizar``. Su usuario técnico (``user_juan``) es quien la creó; lo que una vendedora
después le cambie no le quita el origen.

Las cotizaciones del chatbot y de la web que nadie confirmó se cancelan solas pasados los días de Ajustes de Juan
(``cotizacion_dias_abierta``, 3 por defecto; decisión de la dueña, 2026-11-03). Nunca se borran ni se tocan las de las
vendedoras, las bloqueadas, las que tienen una factura o un pago en curso (la web: transferencia por confirmar).
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ORIGENES_QUE_VENCEN = ('chatbot', 'web')
PAGOS_EN_CURSO = ('pending', 'authorized', 'done')
POR_CORRIDA = 500


class SaleOrderOrigenJuan(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        ordenes = super().create(vals_list)
        dias = self.env['dcasa.juan.ajustes'].sudo().obtener().cotizacion_dias_abierta
        if dias:
            vence = fields.Date.context_today(self) + timedelta(days=dias)
            # Lo que dice el PDF («válida hasta») es lo mismo que hace el cron.
            ordenes.filtered(lambda o: o.dcasa_origen in ORIGENES_QUE_VENCEN and o.state in ('draft', 'sent')).sudo(
            ).write({'validity_date': vence})
        return ordenes

    def _dcasa_pago_en_curso(self):
        self.ensure_one()
        return any(t.state in PAGOS_EN_CURSO for t in self.sudo().transaction_ids)

    @api.model
    def _cron_dcasa_cancelar_vencidas(self):
        """Cancela (nunca borra) las cotizaciones del chatbot y de la web abiertas desde hace más de los días de
        Ajustes de Juan. Cada una en su savepoint: si una falla, las demás siguen."""
        dias = self.env['dcasa.juan.ajustes'].sudo().obtener().cotizacion_dias_abierta
        if not dias:
            return 0
        limite = fields.Datetime.now() - timedelta(days=dias)
        ordenes = self.sudo().search([
            ('dcasa_origen', 'in', ORIGENES_QUE_VENCEN), ('state', 'in', ('draft', 'sent')), ('locked', '=', False),
            ('create_date', '<', limite)], order='create_date asc, id asc', limit=POR_CORRIDA)
        canceladas = 0
        for orden in ordenes:
            if orden._dcasa_pago_en_curso() or orden.invoice_ids.filtered(lambda f: f.state != 'cancel'):
                continue
            try:
                with self.env.cr.savepoint():
                    orden._action_cancel()
                    orden.message_post(
                        body=self.env._(
                            'Se canceló sola: pasaron %(dias)s día(s) sin confirmarse (cotización %(origen)s). No se '
                            'borró. Si el cliente todavía la quiere, toca «Establecer como cotización».',
                            dias=dias, origen=self.env._('del chatbot') if orden.dcasa_origen == 'chatbot'
                            else self.env._('de la web')),
                        subtype_xmlid='mail.mt_note')
                canceladas += 1
            except Exception:   # noqa: BLE001 — una cotización rara no detiene a las demás
                _logger.exception('No se pudo cancelar la cotización vencida %s.', orden.name)
        if canceladas:
            _logger.info('Se cancelaron %s cotizaciones del chatbot o de la web que vencieron.', canceladas)
        return canceladas

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
