from urllib.parse import quote

from odoo import models
from odoo.addons.dcasa_socios.models import reglas
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_dcasa_whatsapp(self):
        """Abre WhatsApp con la cotización lista para enviar al celular del cliente.

        El mensaje lleva el total y el enlace del portal, donde el cliente la ve, la firma o la paga.
        """
        self.ensure_one()
        celular = reglas.celular_normal(self.partner_id.phone or self.partner_id.dcasa_celular)
        if not reglas.celular_valido(celular):
            raise UserError(self.env._(
                '%s no tiene un celular de Panamá anotado. Escríbelo en el contacto (8 números, como 6123-4567).',
                self.partner_id.display_name))
        tipo = self.env._('cotización') if self.state in ('draft', 'sent') else self.env._('orden')
        texto = self.env._(
            "Hola %(nombre)s, te comparto tu %(tipo)s %(numero)s de D'CASA por %(total)s: %(enlace)s",
            nombre=self.partner_id.name.split()[0], tipo=tipo, numero=self.name,
            total=formatLang(self.env, self.amount_total, currency_obj=self.currency_id),
            enlace=self.get_base_url() + self.get_portal_url())
        if self.state == 'draft':
            self.action_quotation_sent()
        return {'type': 'ir.actions.act_url', 'url': f'https://wa.me/507{celular}?text={quote(texto)}', 'target': 'new'}

    # ------------------------------------------------------------------
    # Combos (tipo «Combo» de Odoo): la línea del combo y una línea por cada pieza
    # ------------------------------------------------------------------

    def action_confirm(self):
        self._dcasa_exigir_combos_completos()
        return super().action_confirm()

    def _dcasa_exigir_combos_completos(self):
        """Un combo sin sus piezas (la cama y el colchón) no se confirma: su línea no lleva importe, así que se vendería
        en cero y no saldría nada de la bodega. La pantalla de Ventas siempre agrega las piezas; esto cubre lo que se
        arma por otro camino (una herramienta, una importación)."""
        for orden in self:
            for linea in orden.order_line.filtered(lambda ln: not ln.display_type and ln.product_type == 'combo'):
                esperadas = len(linea.product_template_id.sudo().combo_ids)
                piezas = orden.order_line.filtered(
                    lambda ln, base=linea: ln.linked_line_id == base and ln.combo_item_id)
                if len(piezas) != esperadas:
                    raise UserError(self.env._(
                        'El combo «%(combo)s» no tiene todas sus piezas (la cama y el colchón). Quítalo y vuelve a '
                        'agregarlo eligiendo sus piezas.', combo=linea.product_id.display_name))

    def _dcasa_agregar_producto(self, producto, cantidad=1, elecciones=None, **valores):
        """Agrega ``producto`` (un ``product.product``) a esta cotización y devuelve su línea.

        Un producto normal es una línea. Un **combo** se agrega como lo hace la pantalla de Ventas: la línea del combo
        y, justo debajo, una línea por cada pieza (la cama, el colchón…), con la misma cantidad; Odoo reparte el precio
        del combo entre las piezas. Si un grupo del combo tiene varias opciones, ``elecciones`` dice cuál va
        (``{id del grupo: id del producto}``); si falta, se pregunta con un error que lista las opciones. El precio
        de un combo no se cambia a mano: se rebaja con el descuento."""
        self.ensure_one()
        Linea = self.env['sale.order.line']
        base = {'order_id': self.id, 'product_id': producto.id, 'product_uom_qty': cantidad, **valores}
        if producto.type != 'combo':
            return Linea.create(base)
        if 'price_unit' in valores:
            raise UserError(self.env._('El precio de un combo no se cambia a mano: usa el descuento.'))
        piezas = []
        for grupo in producto.product_tmpl_id.sudo().combo_ids:
            opciones = grupo.combo_item_ids.filtered(lambda item: item.product_id.active)
            elegida = opciones.filtered(lambda item, g=grupo: item.product_id.id == (elecciones or {}).get(g.id))
            if len(opciones) == 1:
                elegida = opciones
            if not elegida:
                raise UserError(self.env._(
                    'En «%(grupo)s» del combo hay que escoger: %(opciones)s.', grupo=grupo.name,
                    opciones='; '.join(opciones.mapped('product_id.display_name'))))
            piezas.append(elegida[:1])
        combo = Linea.create(base)
        for numero, pieza in enumerate(piezas, start=1):
            Linea.create({
                'order_id': self.id, 'product_id': pieza.product_id.id, 'product_uom_qty': cantidad,
                'combo_item_id': pieza.id, 'linked_line_id': combo.id, 'sequence': combo.sequence + numero})
        return combo
