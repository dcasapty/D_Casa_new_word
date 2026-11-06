"""Las novedades por correo al confirmar una venta o registrar un pago (etapa 1b, decisiones de la dueña, 2026-11-06).

Cuando una persona del equipo confirma una venta o registra un pago **desde la pantalla**, sale un cuadro corto, sin
«Cancelar» ni X:

* **Con correo**: la casilla «Quiere recibir novedades por correo» ya viene activada (la regla de la dueña: se activan
  solas con el correo) y dice a qué correo le llegarían. Si el cliente dijo que no, se desactiva: queda el «no» (con
  cuándo, en qué venta y quién) y ya no se activa sola. Si quedó activada y no tenía permiso, queda «En la venta» con
  la referencia «venía activada» (lo honesto: nadie le preguntó). Si ya se había activado sola, sigue así.
* **Sin correo**: «Sí / No». Con «Sí», el mismo cuadro pide el correo, lo revisa y lo guarda en la ficha con las reglas
  de contactos de siempre; queda «En la venta». Con «No», queda el «no».

El cuadro no vuelve a salir para esa ficha en el plazo del ajuste (``dcasa_camila.dias_entre_preguntas``, 180 días).

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
    paso = fields.Selection([('casilla', 'La casilla (tiene correo)'), ('pregunta', 'Pregunta (sin correo)'),
                             ('correo', 'Pide el correo')], default='pregunta', required=True, readonly=True)
    quiere = fields.Boolean('Quiere recibir novedades por correo', default=True)
    venia_activada = fields.Boolean('La casilla venía activada', readonly=True)
    no_fecha = fields.Datetime(related='partner_id.dcasa_promos_no_fecha', string='Dijo que no el')
    correo = fields.Char('Su correo')
    siguiente = fields.Text(readonly=True, help='La acción que seguía (p. ej. «Imprimir documentos» tras pagar).')

    # ------------------------------------------------------------------
    # Abrir el cuadro (después de confirmar o de pagar)
    # ------------------------------------------------------------------

    @api.model
    def _accion_para(self, partner, orden=None, facturas=None, siguiente=None):
        """La acción que abre el cuadro para la ficha comercial de ``partner``, o ``None`` si no hay que preguntar."""
        ficha = partner.commercial_partner_id
        if not ficha:
            return None
        paso, casilla = ficha._dcasa_promos_que_preguntar()
        if not paso:
            return None
        if orden:
            referencia = self.env._('Venta %s', orden.name)
        else:
            referencia = self.env._('Pago de %s', ', '.join(facturas.mapped('name'))[:90])
        cuadro = self.create({
            'partner_id': ficha.id,
            'paso': paso,
            'quiere': bool(casilla),
            'venia_activada': bool(casilla),
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

    def action_listo(self):
        """Con correo: la casilla como la dejó la persona. Desactivada, queda el «no»; activada, queda el permiso (si ya
        lo tenía, sigue igual: si se había activado sola, sigue diciendo eso)."""
        ficha = self._revisar()
        if self.paso != 'casilla':
            raise UserError(self.env._('Esta pregunta ya no está en ese paso: ciérrala y vuelve a abrir la venta.'))
        if not self.quiere:
            ficha._dcasa_promos_anotar_no('venta', self.env.user)
            return self._siguiente()
        if ficha._dcasa_promos_motivo_para_no_activar() == 'baja':
            raise UserError(self.env._('Ese correo se dio de baja de las novedades: no se le vuelve a escribir.'))
        if ficha.sudo().dcasa_promos_estado != 'si':
            detalle = self.env._('venía activada') if self.venia_activada else self.env._('la activó quien atendió')
            ficha._dcasa_promos_registrar('venta', self.env.user, referencia=f'{self.referencia} · {detalle}')
        ficha._dcasa_promos_anotar_pregunta()
        return self._siguiente()

    def action_si(self):
        """Sin correo, «Sí»: el mismo cuadro pide el correo, lo guarda en la ficha y anota «En la venta» (sin correo no
        hay sí)."""
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
        if ficha._dcasa_promos_motivo_para_no_activar() == 'baja':
            raise UserError(self.env._('Ese correo se dio de baja de las novedades: no se le vuelve a escribir.'))
        if not ficha._dcasa_promos_registrar('venta', self.env.user, referencia=self.referencia):
            _logger.info('DCASA_CAMILA el sí en la venta no cambió nada (ficha %s)', ficha.id)
        return self._siguiente()

    def action_no(self):
        """«No»: queda el «no» (cuándo, en qué venta, quién); ya no se activa sola y el cuadro no vuelve a salir en el
        plazo del ajuste."""
        ficha = self._revisar()
        ficha._dcasa_promos_anotar_no('venta', self.env.user)
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
