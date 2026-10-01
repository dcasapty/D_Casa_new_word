"""Tope de descuento por línea para quien no es Gerencia (UI-08, H-02 de Brian).

La vendedora puede rebajar una línea hasta el tope configurado en Ajustes de Ventas
(«dcasa.descuento_max_vendedora», 10 % por defecto). Se mide el precio neto de la línea
(precio unitario con el % de descuento aplicado) contra el precio que ya autoriza la
tarifa: así cuenta igual bajar el precio unitario que poner un %, y una promoción de
tarifa que configuró Gerencia no le cuenta a la vendedora como rebaja suya.

Se valida en el modelo (create/write): aplica a la pantalla, a cualquier RPC y a Brian,
que actúa como el usuario real.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

PARAM_DESCUENTO_MAX = 'dcasa.descuento_max_vendedora'
DESCUENTO_MAX_DEFECTO = 10.0
GRUPO_SIN_TOPE = 'sales_team.group_sale_manager'  # Gerencia lo implica; el admin de Ventas también.
CAMPOS_PRECIO = {'price_unit', 'discount'}


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def _dcasa_descuento_max(self):
        """Tope en % (0-100). Un valor ilegible no abre la puerta: se usa el de por defecto."""
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_DESCUENTO_MAX, DESCUENTO_MAX_DEFECTO)
        try:
            tope = float(valor)
        except (TypeError, ValueError):
            tope = DESCUENTO_MAX_DEFECTO
        return min(max(tope, 0.0), 100.0)

    def _dcasa_exenta_tope_descuento(self):
        """Líneas que no son una rebaja sobre un producto (secciones, notas, anticipos, combos).

        dcasa_socios añade las líneas de premio canjeado con puntos.
        """
        self.ensure_one()
        return bool(self.display_type or not self.product_id or self.is_downpayment
                    or self.combo_item_id or self.product_type == 'combo')

    def _dcasa_precio_autorizado(self):
        """Precio unitario que da la tarifa, en la misma base que price_unit (con ITBMS si aplica)."""
        self.ensure_one()
        linea = self.with_company(self.company_id)
        precio = linea._get_pricelist_price()
        return linea.product_id._get_tax_included_unit_price_from_price(
            precio,
            product_taxes=linea.product_id.taxes_id._filter_taxes_by_company(linea.company_id),
            fiscal_position=linea.order_id.fiscal_position_id,
        )

    @api.model_create_multi
    def create(self, vals_list):
        lineas = super().create(vals_list)
        if any(CAMPOS_PRECIO & set(vals) for vals in vals_list):
            lineas._dcasa_validar_tope_descuento()
        return lineas

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_PRECIO & set(vals):
            self._dcasa_validar_tope_descuento()
        return resultado

    def _dcasa_validar_tope_descuento(self):
        """Va en create/write y no en @api.constrains: los constrains corren siempre en sudo
        y aquí hace falta distinguir a la persona (sin tope en sudo: tienda en línea, procesos)."""
        usuario = self.env.user
        if self.env.su or not usuario._is_internal() or usuario.has_group(GRUPO_SIN_TOPE):
            return
        tope = self._dcasa_descuento_max()
        for linea in self:
            if linea._dcasa_exenta_tope_descuento():
                continue
            autorizado = linea._dcasa_precio_autorizado()
            if autorizado <= 0:
                continue
            moneda = linea.currency_id or linea.company_id.currency_id
            neto = linea.price_unit * (1 - (linea.discount or 0.0) / 100)
            piso = moneda.round(autorizado * (1 - tope / 100))
            if moneda.compare_amounts(neto, piso) < 0:
                raise ValidationError(self.env._(
                    '«%(producto)s»: puedes rebajar hasta %(tope)s %% (precio mínimo %(piso)s). '
                    'Para un descuento mayor, pídeselo a Gerencia.',
                    producto=linea.product_id.display_name,
                    tope=f'{tope:g}',
                    piso=f'{moneda.symbol}{piso:,.2f}',
                ))


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_descuento_max_vendedora = fields.Float(
        string='Descuento máximo de la vendedora (%)',
        config_parameter=PARAM_DESCUENTO_MAX,
        default=DESCUENTO_MAX_DEFECTO,
        help='Rebaja máxima por línea (por % o bajando el precio) para quien no es Gerencia.',
    )

    @api.constrains('dcasa_descuento_max_vendedora')
    def _check_dcasa_descuento_max_vendedora(self):
        for ajustes in self:
            if not 0 <= ajustes.dcasa_descuento_max_vendedora <= 100:
                raise ValidationError(self.env._('El descuento máximo va de 0 a 100 %.'))
