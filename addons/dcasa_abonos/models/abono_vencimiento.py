"""Abonos por vencer (decisión D3 de la gerencia: abonos a 30 días, aviso 5 días antes del vencimiento).

* ``dcasa_abono_vence``: la fecha en que vence el abono de una factura, guardada para poder ordenar y filtrar. Sale de
  ``_dcasa_estado_abono`` (la misma fuente del papel de ABONO, las Condiciones, Mi cuenta, los correos y Brian): el
  primer pago + los días del plazo, mientras falte pagar. Se recalcula con cada pago (cambia el saldo) y todas las
  noches (por si cambió el plazo en Ajustes).
* **Facturación › Clientes › Abonos por vencer** (Caja, Gerencia y contabilidad): los que vencen en los próximos días
  (``dcasa_abonos.aviso_dias``, 5 de fábrica, la cifra de D3) y los ya vencidos, del más urgente al menos, con lo que
  falta y un botón para **escribirle por WhatsApp**: abre WhatsApp (en el teléfono o en la computadora) con el mensaje
  listo y una persona lo manda. El sistema no le escribe solo por WhatsApp (ver ``docs/CORREO.md``).
* El correo de recordatorio lo manda ``dcasa_correo`` (apagado mientras no haya clave de Resend).
"""
import re
from datetime import timedelta
from urllib.parse import quote

from odoo import api, fields, models

PARAM_AVISO_DIAS = 'dcasa_abonos.aviso_dias'
AVISO_DIAS_DEFECTO = 5   # D3: «correo 5 días antes del vencimiento»


def whatsapp_de(telefono):
    """El número para wa.me (solo dígitos, con el 507 de Panamá si son 8), o ``''``."""
    texto = (telefono or '').strip()
    digitos = re.sub(r'\D', '', texto)
    if texto.startswith('00'):
        digitos = digitos[2:]
    if len(digitos) == 8:
        return f'507{digitos}'
    if texto.startswith(('+', '00')) and len(digitos) >= 8:
        return digitos
    if len(digitos) == 11 and digitos.startswith('507'):
        return digitos
    return ''


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_abono_vence = fields.Date(
        'El abono vence', compute='_compute_dcasa_abono_vence', store=True, index='btree_not_null', copy=False,
        help='Primer pago + los días del plazo del abono (Ajustes), mientras falte pagar.')
    dcasa_abono_dias = fields.Integer('Días para que venza', compute='_compute_dcasa_abono_dias',
                                      help='Negativo: ya venció hace esos días.')
    dcasa_abono_pronto = fields.Boolean('Vence pronto', compute='_compute_dcasa_abono_dias',
                                        search='_search_dcasa_abono_pronto')

    @api.depends('move_type', 'state', 'payment_state', 'amount_residual')
    def _compute_dcasa_abono_vence(self):
        for factura in self:
            if (factura.move_type == 'out_invoice' and factura.state == 'posted'
                    and factura.payment_state == 'partial'):
                factura.dcasa_abono_vence = factura._dcasa_estado_abono()['vence']
            else:
                factura.dcasa_abono_vence = False

    @api.model
    def _dcasa_aviso_dias(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_AVISO_DIAS)
        try:
            return max(int(str(valor).strip()), 0) if valor not in (None, False, '') else AVISO_DIAS_DEFECTO
        except ValueError:
            return AVISO_DIAS_DEFECTO

    @api.depends('dcasa_abono_vence')
    def _compute_dcasa_abono_dias(self):
        hoy = fields.Date.context_today(self)
        aviso = self._dcasa_aviso_dias()
        for factura in self:
            if factura.dcasa_abono_vence:
                dias = (factura.dcasa_abono_vence - hoy).days
                factura.dcasa_abono_dias = dias
                factura.dcasa_abono_pronto = dias <= aviso
            else:
                factura.dcasa_abono_dias = 0
                factura.dcasa_abono_pronto = False

    def _search_dcasa_abono_pronto(self, operator, value):
        # Odoo 19 entrega «= True» como «in [True]».
        if operator in ('=', '!='):
            operator, value = ('in' if operator == '=' else 'not in'), [value]
        if operator not in ('in', 'not in'):
            return NotImplemented
        quiere = (True in value) if operator == 'in' else (True not in value)
        limite = fields.Date.context_today(self) + timedelta(days=self._dcasa_aviso_dias())
        if quiere:
            return [('dcasa_abono_vence', '!=', False), ('dcasa_abono_vence', '<=', limite)]
        return ['|', ('dcasa_abono_vence', '=', False), ('dcasa_abono_vence', '>', limite)]

    @api.model
    def _dcasa_recalcular_vencimientos(self):
        """Vuelve a calcular el vencimiento de los abonos abiertos (cambió el plazo, o se arregló algo a mano)."""
        abiertas = self.sudo().search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                                       '|', ('payment_state', '=', 'partial'), ('dcasa_abono_vence', '!=', False)])
        self.env.add_to_compute(self._fields['dcasa_abono_vence'], abiertas)
        abiertas.flush_recordset(['dcasa_abono_vence'])
        return abiertas

    @api.model
    def _dcasa_cron_abonos(self):
        """Todas las mañanas: recalcula los vencimientos (``dcasa_correo`` agrega aquí el recordatorio por correo)."""
        self._dcasa_recalcular_vencimientos()
        return True

    # ------------------------------------------------------------------
    # WhatsApp: lo manda una persona, desde su teléfono
    # ------------------------------------------------------------------

    def _dcasa_abono_texto_whatsapp(self):
        self.ensure_one()
        estado = self._dcasa_estado_abono()
        nombre = ((self.partner_id.name or '').split() or [''])[0].capitalize()
        saldo = f'${estado["saldo"]:,.2f}'
        vence = estado['vence'].strftime('%d/%m/%Y') if estado['vence'] else ''
        saludo = f'Hola {nombre}, ' if nombre else 'Hola, '
        if estado['vencido']:
            cuerpo = (f'te saludamos de D\'CASA. El abono de tu factura {self.name} venció el {vence} y te faltan '
                      f'{saldo}. Escríbenos y vemos juntos cómo completarlo.')
        else:
            cuerpo = (f'te saludamos de D\'CASA. Te recordamos que el abono de tu factura {self.name} vence el '
                      f'{vence} y te faltan {saldo}. Cualquier duda, escríbenos por aquí.')
        return saludo + cuerpo

    def action_dcasa_abono_whatsapp(self):
        """Abre WhatsApp con el recordatorio listo; lo manda la persona. Solo lee la factura (con sus permisos)."""
        self.ensure_one()
        self.check_access('read')
        cliente = self.partner_id
        numero = whatsapp_de(cliente.phone or cliente.commercial_partner_id.phone)
        texto = quote(self._dcasa_abono_texto_whatsapp())
        url = f'https://wa.me/{numero}?text={texto}' if numero else f'https://wa.me/?text={texto}'
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}
