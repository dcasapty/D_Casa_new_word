"""El origen «Chatbot» de una cotización (ver ``dcasa_interfaz/models/origen.py``): la armó Juan, el asistente de los
clientes, con su herramienta ``cotizar``. Su usuario técnico (``user_juan``) es quien la creó; lo que una vendedora
después le cambie no le quita el origen.

Las cotizaciones del chatbot y de la web que nadie confirmó se cancelan solas (decisión de la dueña, 2026-11-03):

* Al crearse (y al reabrirlas con «Establecer como cotización») quedan **válidas hasta** hoy (de Panamá) + los días de
  Ajustes de Juan (``cotizacion_dias_abierta``, 3 por defecto). Es lo que dice el PDF.
* El cron cancela (nunca borra) las que pasaron esa fecha. Si una vendedora mueve la fecha, manda la fecha.
* No toca: las de las vendedoras, las bloqueadas, las que tienen una factura o un pago en curso (la web: transferencia
  por confirmar), los apartados de la web (``dcasa_apartado_vence``, que tienen su propio vencimiento) ni las que
  alguien tocó en las últimas 12 horas (un carrito que el cliente está llenando ahora).
"""
import logging
from datetime import timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ORIGENES_QUE_VENCEN = ('chatbot', 'web')
PAGOS_EN_CURSO = ('pending', 'authorized', 'done')
TOCADA_HACE_POCO = timedelta(hours=12)
POR_CORRIDA = 500
ZONA_PANAMA = pytz.timezone('America/Panama')


def hoy_en_panama():
    return pytz.utc.localize(fields.Datetime.now()).astimezone(ZONA_PANAMA).date()


class SaleOrderOrigenJuan(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        ordenes = super().create(vals_list)
        ordenes._dcasa_poner_vencimiento()
        return ordenes

    def action_draft(self):
        """Reabrir una cotización cancelada le da sus días otra vez (si no, el cron la volvería a cancelar)."""
        resultado = super().action_draft()
        self._dcasa_poner_vencimiento()
        return resultado

    def _dcasa_poner_vencimiento(self):
        """«Válida hasta» = hoy (Panamá) + los días de Ajustes de Juan, para las del chatbot y la web abiertas."""
        dias = self.env['dcasa.juan.ajustes'].sudo().obtener().cotizacion_dias_abierta
        abiertas = self.filtered(lambda o: o.dcasa_origen in ORIGENES_QUE_VENCEN and o.state in ('draft', 'sent'))
        if dias and abiertas:
            abiertas.sudo().write({'validity_date': hoy_en_panama() + timedelta(days=dias)})

    @api.model
    def _dcasa_dominio_vencidas(self):
        dominio = [
            ('dcasa_origen', 'in', ORIGENES_QUE_VENCEN), ('state', 'in', ('draft', 'sent')), ('locked', '=', False),
            ('validity_date', '!=', False), ('validity_date', '<', hoy_en_panama()),
            ('write_date', '<', fields.Datetime.now() - TOCADA_HACE_POCO),
            ('transaction_ids', 'not any', [('state', 'in', PAGOS_EN_CURSO)]),
            ('order_line', 'not any', [('invoice_lines.move_id.state', '!=', 'cancel')]),
        ]
        if 'dcasa_apartado_vence' in self._fields:     # website_dcasa: el apartado tiene su propio vencimiento
            dominio.append(('dcasa_apartado_vence', '=', False))
        return dominio

    @api.model
    def _cron_dcasa_cancelar_vencidas(self):
        """Cancela (nunca borra) las cotizaciones del chatbot y de la web que pasaron su «válida hasta». Cada una en
        su savepoint: si una falla, las demás siguen. Las exclusiones van en la búsqueda: lo que no toca cancelar no
        ocupa lugar en la corrida."""
        dias = self.env['dcasa.juan.ajustes'].sudo().obtener().cotizacion_dias_abierta
        if not dias:
            return 0
        ordenes = self.sudo().search(self._dcasa_dominio_vencidas(), order='validity_date asc, id asc',
                                     limit=POR_CORRIDA)
        canceladas = 0
        for orden in ordenes:
            try:
                with self.env.cr.savepoint():
                    vencio = orden.validity_date
                    orden._action_cancel()
                    orden.message_post(
                        body=self.env._(
                            'Se canceló sola: era válida hasta el %(fecha)s y nadie la confirmó (cotización '
                            '%(origen)s). No se borró. Si el cliente todavía la quiere, toca «Establecer como '
                            'cotización»: vuelve con %(dias)s día(s) más.',
                            fecha=vencio.strftime('%d/%m/%Y'), dias=dias,
                            origen=self.env._('del chatbot') if orden.dcasa_origen == 'chatbot'
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
