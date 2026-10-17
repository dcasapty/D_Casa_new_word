from odoo import api, fields, models

from . import condiciones

# Se escriben UNA vez por base (este parámetro) y solo si el campo está vacío: lo que el administrador cambie o borre
# después no se vuelve a pisar al actualizar el módulo. Mismo patrón que los textos de la factura (dcasa_invoice).
CONDICIONES_PUESTAS = 'dcasa_abonos.condiciones_iniciales_puestas'


class ResCompany(models.Model):
    _inherit = 'res.company'

    dcasa_abono_condiciones_titulo = fields.Char(
        string='Título de la hoja de condiciones',
        help='Lo que dice arriba de la hoja. Vacío: «Condiciones de abono».')
    dcasa_abono_condiciones = fields.Text(
        string='Condiciones de abono',
        help='La hoja que se entrega con el abono, en dos copias (cliente y empresa). Una condición por renglón: la '
             'hoja las numera sola. Vacío: la hoja no se imprime. El sistema no calcula ni cobra lo que digan '
             '(penalidades, recargos): solo lo imprime.')
    dcasa_abono_condiciones_larga = fields.Boolean(
        compute='_compute_dcasa_abono_condiciones_larga',
        help='Las condiciones ocupan tanto de la hoja que con pocos muebles la lista ya se achica o se corta.')

    @api.depends('dcasa_abono_condiciones')
    def _compute_dcasa_abono_condiciones_larga(self):
        for empresa in self:
            empresa.dcasa_abono_condiciones_larga = condiciones.demasiado_largas(
                condiciones.lista_de_condiciones(empresa.dcasa_abono_condiciones))

    @api.model
    def _dcasa_abonos_poner_condiciones_iniciales(self):
        """Llena las condiciones vacías con la hoja que ya entrega la tienda, una sola vez por base."""
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param(CONDICIONES_PUESTAS):
            return
        for empresa in self.sudo().search([]):
            if not empresa.dcasa_abono_condiciones:
                empresa.dcasa_abono_condiciones = condiciones.CONDICIONES_INICIALES
        param.set_param(CONDICIONES_PUESTAS, '1')

    def _dcasa_abono_condiciones_lista(self):
        """Las condiciones que escribió la dueña, una por renglón (vacía: la hoja no se imprime)."""
        self.ensure_one()
        return condiciones.lista_de_condiciones(self.sudo().dcasa_abono_condiciones)

    def _dcasa_abono_condiciones_titulo(self):
        self.ensure_one()
        return (self.sudo().dcasa_abono_condiciones_titulo or '').strip() or condiciones.TITULO_POR_DEFECTO
