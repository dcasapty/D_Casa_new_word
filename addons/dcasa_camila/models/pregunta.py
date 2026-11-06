"""«¿El cliente quiere recibir novedades por correo?» al confirmar una venta o registrar un pago (etapa 1b, decisión de
la dueña, 2026-11-06).

La lista crece sola: cuando una persona del equipo confirma una venta o registra un pago **desde la pantalla**, Odoo le
pregunta en un cuadro corto, con «Sí» y «No» (sin «Cancelar»). Si es «Sí» y la ficha no tiene un correo bien escrito,
el mismo cuadro lo pide, lo revisa y lo guarda en la ficha con las reglas de contactos de siempre. Queda «En la venta»
(``venta``), con quién lo preguntó, cuándo y la venta o el pago. Un «No» queda con su fecha y no se vuelve a preguntar
en el plazo del ajuste.

**La regla de oro: esto NUNCA traba ni hace fallar una venta o un pago.** El cuadro sale DESPUÉS de confirmar o de
pagar (la venta o el pago ya quedaron hechos y confirmados en esa petición) y solo cuando el botón de la pantalla trae
la marca ``dcasa_camila_preguntar`` (``views/pregunta_views.xml``) y quien lo toca es del equipo: nunca en Juan, la
web, Brian, los crones ni un RPC sin esa marca. Armar el cuadro va en un savepoint: si falla, la venta o el pago
siguen igual y no sale nada. Y lo que se anota (en otra petición) tampoco puede tocarlos.

Antes de anotar se vuelve a revisar todo en el servidor (el cuadro se podría crear por RPC con cualquier ficha): la
venta tiene que estar confirmada o la factura publicada, quien contesta poder leerla y la ficha ser la de ese cliente.
"""
import json
import logging

from odoo import api, fields, models
from odoo.addons.dcasa_correo.models.correo import correo_valido
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

MARCA = 'dcasa_camila_preguntar'


class CamilaPregunta(models.TransientModel):
    _name = 'dcasa.camila.pregunta'
    _description = 'Camila: ¿el cliente quiere recibir novedades por correo?'

    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, readonly=True, ondelete='cascade')
    nombre = fields.Char(related='partner_id.name', string='Nombre')
    orden_id = fields.Many2one('sale.order', 'Venta', readonly=True, ondelete='cascade')
    move_ids = fields.Many2many('account.move', string='Facturas pagadas', readonly=True)
    referencia = fields.Char('Dónde', readonly=True)
    correo_actual = fields.Char('Correo de la ficha', readonly=True)
    paso = fields.Selection([('pregunta', 'Pregunta'), ('correo', 'Pide el correo')], default='pregunta',
                            required=True, readonly=True)
    correo = fields.Char('Su correo')
    siguiente = fields.Text(readonly=True, help='La acción que seguía (p. ej. «Imprimir documentos» tras pagar).')

    # ------------------------------------------------------------------
    # Abrir el cuadro (después de confirmar o de pagar)
    # ------------------------------------------------------------------

    @api.model
    def _accion_para(self, partner, orden=None, facturas=None, siguiente=None):
        """La acción que abre el cuadro para la ficha comercial de ``partner``, o ``None`` si no hay que preguntar."""
        ficha = partner.commercial_partner_id
        if not ficha or ficha._dcasa_promos_motivo_para_no_preguntar():
            return None
        if orden:
            referencia = self.env._('Venta %s', orden.name)
        else:
            referencia = self.env._('Pago de %s', ', '.join(facturas.mapped('name'))[:90])
        cuadro = self.create({
            'partner_id': ficha.id,
            'orden_id': orden.id if orden else False,
            'move_ids': [fields.Command.set(facturas.ids)] if facturas else [],
            'referencia': referencia,
            'correo_actual': correo_valido(ficha.sudo().email) or False,
            'siguiente': json.dumps(siguiente) if isinstance(siguiente, dict) else False,
        })
        return cuadro._accion()

    def _accion(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Novedades por correo'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'dialog_size': 'medium'},
        }

    # ------------------------------------------------------------------
    # Sí / No
    # ------------------------------------------------------------------

    def _revisar(self):
        """Todo otra vez en el servidor: una venta confirmada o facturas publicadas que quien contesta puede leer, y la
        ficha ES la de ese cliente."""
        self.ensure_one()
        if not self.env.user._is_internal():
            raise AccessError(self.env._('Solo el equipo contesta esta pregunta.'))
        ficha = self.partner_id.commercial_partner_id
        if self.orden_id:
            self.orden_id.check_access('read')
            documentos = self.orden_id
            valido = self.orden_id.state == 'sale' and (
                self.orden_id.partner_invoice_id or self.orden_id.partner_id).commercial_partner_id == ficha
        elif self.move_ids:
            self.move_ids.check_access('read')
            documentos = self.move_ids
            valido = all(f.move_type == 'out_invoice' and f.state == 'posted' for f in self.move_ids) \
                and self.move_ids.commercial_partner_id == ficha
        else:
            documentos, valido = None, False
        if not documentos or not valido:
            raise UserError(self.env._('Esta pregunta no corresponde a una venta o un pago de este cliente.'))
        return ficha

    def _siguiente(self):
        if self.siguiente:
            try:
                accion = json.loads(self.siguiente)
                if isinstance(accion, dict):
                    return accion
            except ValueError:
                pass
        return {'type': 'ir.actions.act_window_close'}

    def action_si(self):
        """«Sí»: anota «En la venta». Sin un correo bien escrito en la ficha, primero lo pide (sin correo no hay sí)."""
        ficha = self._revisar()
        correo_ficha = correo_valido(ficha.sudo().email)
        if not correo_ficha:
            if self.paso == 'pregunta':
                self.write({'paso': 'correo'})   # el mismo cuadro pide el correo
                return self._accion()
            correo = correo_valido(self.correo)
            if not correo:
                raise UserError(self.env._('Escribe su correo bien escrito: sin correo no se le pueden mandar las '
                                           'novedades.'))
            try:
                ficha.write({'email': correo})   # las reglas de contactos de siempre (errores de dedo, del equipo)
            except ValidationError as error:
                raise UserError(str(error.args[0] if error.args else error)) from None
            correo_ficha = correo_valido(ficha.sudo().email)
        if ficha._dcasa_promos_motivo_para_no_preguntar() == 'baja':
            raise UserError(self.env._('Ese correo se dio de baja de las novedades: no se le vuelve a escribir.'))
        if not ficha._dcasa_promos_registrar('venta', self.env.user, referencia=self.referencia):
            _logger.info('DCASA_CAMILA el sí en la venta no cambió nada (ficha %s)', ficha.id)
        return self._siguiente()

    def action_no(self):
        """«No»: queda con su fecha y no se le vuelve a preguntar en el plazo del ajuste."""
        ficha = self._revisar()
        ficha._dcasa_promos_anotar_no()
        return self._siguiente()

    def action_sin_correo(self):
        """Dijo que sí pero no dio su correo: no se anota nada (sin correo no hay sí); la próxima vez se pregunta."""
        self._revisar()
        return self._siguiente()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Después de confirmar (la venta ya quedó hecha): si el botón de la pantalla trae la marca, la pregunta."""
        resultado = super().action_confirm()
        if not self.env.context.get(MARCA) or len(self) != 1 or not self.env.user._is_internal() or self.env.su:
            return resultado
        try:
            with self.env.cr.savepoint():
                accion = self.env['dcasa.camila.pregunta']._accion_para(
                    self.partner_invoice_id or self.partner_id, orden=self,
                    siguiente=resultado if isinstance(resultado, dict) else None)
        except Exception:   # noqa: BLE001 — la venta ya está confirmada: la pregunta nunca la estorba
            _logger.warning('DCASA_CAMILA no se pudo armar la pregunta de novedades en la venta %s', self.id,
                            exc_info=True)
            return resultado
        return accion or resultado


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def action_create_payments(self):
        """Después de pagar (el pago ya quedó hecho): si el botón de la pantalla trae la marca, la pregunta. Lo que
        seguía (el cuadro «Imprimir documentos») sale después de contestar."""
        resultado = super().action_create_payments()
        if not self.env.context.get(MARCA) or not self.env.user._is_internal() or self.env.su:
            return resultado
        try:
            with self.env.cr.savepoint():
                facturas = self.line_ids.move_id.filtered(
                    lambda f: f.move_type == 'out_invoice' and f.state == 'posted')
                if not facturas or len(facturas.commercial_partner_id) != 1:
                    return resultado
                accion = self.env['dcasa.camila.pregunta']._accion_para(
                    facturas.commercial_partner_id, facturas=facturas,
                    siguiente=resultado if isinstance(resultado, dict) else None)
        except Exception:   # noqa: BLE001 — el pago ya está hecho: la pregunta nunca lo estorba
            _logger.warning('DCASA_CAMILA no se pudo armar la pregunta de novedades tras un pago', exc_info=True)
            return resultado
        return accion or resultado
