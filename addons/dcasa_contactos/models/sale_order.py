"""Al cotizar, el cliente es una ficha (etapa 3, 2026-10-16).

Pedido de la dueña: una misma persona salía hasta cinco veces al elegir el cliente de una cotización (su ficha, su
usuario, su contacto de empleado y sus direcciones de entrega o de factura, todos con el mismo nombre).

* El selector de «Cliente» muestra solo contactos principales (sin padre) que no son del equipo (usuario interno o
  empleado) ni una empresa propia. Las direcciones se eligen donde siempre: «Dirección de factura» y «Dirección de
  entrega». Los clientes que se registraron en la tienda (usuarios del portal) sí salen: son clientes.
* Los usuarios y empleados no se tocan: solo dejan de ofrecerse como cliente. El dominio se arma con ``sudo`` como una
  lista de ids, así la Vendedora (que no ve empleados) puede buscar sin error.
* Si la ficha elegida comparte celular, correo o RUC con otra ficha (lo viejo, de antes del candado), se avisa con el
  nombre de la otra para fusionarlas en Socios › Configuración › Posibles duplicados.
* Puerta A (2026-10-16): no se confirma una venta si al cliente le falta el celular o el correo, o están mal escritos
  (ver ``contacto.py``). Mientras se cotiza, un aviso amarillo lo adelanta. Un teléfono fijo sirve en lugar del
  celular (2026-10-22).
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

from . import claves
from .res_partner import DATOS

MAXIMO_EN_EL_AVISO = 3


def _dominio_del_cliente(pedidos):
    return pedidos.env['res.partner']._dcasa_dominio_clientes_al_cotizar()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _dcasa_contactos_del_equipo(self):
        """Los contactos que no son clientes: usuarios internos, empleados y empresas propias (archivados incluidos)."""
        Usuarios = self.env['res.users'].sudo().with_context(active_test=False)
        Empleados = self.env['hr.employee'].sudo().with_context(active_test=False)
        return (Usuarios.search([('share', '=', False)]).partner_id
                | Empleados.search([]).work_contact_id
                | self.env['res.company'].sudo().search([]).partner_id)

    @api.model
    def _dcasa_dominio_clientes_al_cotizar(self):
        return [('parent_id', '=', False), ('id', 'not in', self._dcasa_contactos_del_equipo().ids)]

    def _dcasa_fichas_con_el_mismo_dato(self):
        """``[(dato, valor legible, otras fichas)]`` que comparten celular, correo o RUC con esta ficha."""
        self.ensure_one()
        ficha = self.commercial_partner_id
        # Las mismas fichas que ofrece el selector: también quien se registró en la tienda (usuario del portal),
        # que es un cliente; no el equipo ni las empresas propias (revisión adversarial, 2026-10-16).
        clientes = self._dcasa_dominio_clientes_al_cotizar()
        Partner = self.sudo().with_context(active_test=False)
        if not Partner.search_count([('id', '=', ficha.id)] + clientes):
            return []
        encontrados = []
        for etiqueta, llaves in ficha._dcasa_claves().items():
            for clave in sorted(llaves):
                otras = Partner.search(
                    clientes + [('id', '!=', ficha.id)]
                    + ficha._dcasa_dominio_de_la_llave(etiqueta, clave), order='id', limit=MAXIMO_EN_EL_AVISO)
                if otras:
                    valor = claves.telefono_legible(clave) if etiqueta == 'celular' else clave
                    encontrados.append((etiqueta, valor, otras))
        return encontrados


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_id = fields.Many2one(domain=_dominio_del_cliente)
    dcasa_cliente_sin_correo = fields.Boolean(
        'Cliente no tiene correo electrónico', compute='_compute_dcasa_cliente_sin_correo',
        inverse='_inverse_dcasa_cliente_sin_correo',
        help='Márcalo solo si el cliente de verdad no tiene correo: así se puede confirmar la venta sin él (el '
             'celular sigue siendo obligatorio). Se guarda en la ficha del cliente.')
    dcasa_cliente_tiene_correo = fields.Boolean(
        'El cliente tiene correo', compute='_compute_dcasa_falta_contacto')
    dcasa_falta_contacto = fields.Char(
        'Le falta al cliente', compute='_compute_dcasa_falta_contacto',
        help='Lo que le falta al cliente (celular o correo bien escritos) para poder confirmar la venta.')

    @api.depends('partner_id', 'partner_id.commercial_partner_id.dcasa_sin_correo')
    def _compute_dcasa_cliente_sin_correo(self):
        for orden in self:
            orden.dcasa_cliente_sin_correo = orden.partner_id.commercial_partner_id.dcasa_sin_correo

    def _inverse_dcasa_cliente_sin_correo(self):
        """La casilla vive en la ficha del cliente. Se escribe como quien edita la cotización (sin sudo: queda su
        nombre en el historial de la ficha) y solo si cambió: guardar la cotización no toca la ficha de balde."""
        for orden in self:
            ficha = orden.partner_id.commercial_partner_id
            if ficha and bool(ficha.dcasa_sin_correo) != bool(orden.dcasa_cliente_sin_correo):
                ficha.write({'dcasa_sin_correo': orden.dcasa_cliente_sin_correo})

    def _dcasa_sin_correo(self):
        """La casilla como está en la cotización (aunque todavía no se haya guardado) o, si la dirección de factura
        es de otra ficha, la de esa ficha."""
        self.ensure_one()
        factura = (self.partner_invoice_id or self.partner_id).commercial_partner_id
        otra = factura != self.partner_id.commercial_partner_id and factura.sudo().dcasa_sin_correo
        return bool(self.dcasa_cliente_sin_correo or otra)

    @api.depends('partner_id', 'partner_invoice_id', 'dcasa_cliente_sin_correo',
                 'partner_id.email', 'partner_id.phone', 'partner_id.commercial_partner_id.email',
                 'partner_id.commercial_partner_id.phone', 'partner_id.commercial_partner_id.dcasa_celular',
                 'partner_id.dcasa_telefono_fijo', 'partner_id.commercial_partner_id.dcasa_telefono_fijo',
                 'partner_invoice_id.email', 'partner_invoice_id.phone', 'partner_invoice_id.dcasa_telefono_fijo',
                 'partner_invoice_id.commercial_partner_id.dcasa_telefono_fijo',
                 'partner_invoice_id.commercial_partner_id.dcasa_sin_correo')
    def _compute_dcasa_falta_contacto(self):
        Partner = self.env['res.partner']
        for orden in self:
            cliente = orden.partner_invoice_id or orden.partner_id
            if not cliente:
                orden.dcasa_cliente_tiene_correo = False
                orden.dcasa_falta_contacto = False
                continue
            datos = Partner._dcasa_contacto_del_documento(cliente, sin_correo=orden._dcasa_sin_correo())
            orden.dcasa_cliente_tiene_correo = bool(datos['correo'])
            faltan = Partner._dcasa_lo_que_falta(datos)
            orden.dcasa_falta_contacto = Partner._dcasa_que_falta(faltan) if faltan else False

    def action_confirm(self):
        """Puerta A: sin un celular y un correo bien escritos del cliente (o «Cliente no tiene correo electrónico»
        marcada), la venta no se confirma. Solo el equipo, sin sudo: la tienda en línea y Juan no pasan por aquí."""
        Partner = self.env['res.partner']
        if Partner._dcasa_exige_contacto():
            for orden in self:
                mensaje = Partner._dcasa_mensaje_faltantes(
                    orden.partner_invoice_id or orden.partner_id, 'venta', sin_correo=orden._dcasa_sin_correo())
                if mensaje:
                    raise UserError(mensaje)
        return super().action_confirm()

    @api.onchange('partner_id')
    def _onchange_dcasa_cliente_duplicado(self):
        """Avisa al personal si el cliente elegido parece estar repetido en otra ficha."""
        if not self.partner_id or not self.env.user.has_group('base.group_user'):
            return None
        repetidos = self.partner_id._dcasa_fichas_con_el_mismo_dato()
        if not repetidos:
            return None
        lineas = [
            self.env._('El %(dato)s %(valor)s también está en: %(otras)s.', dato=DATOS[etiqueta], valor=valor,
                       otras=', '.join(f'«{otra.display_name}»' for otra in otras))
            for etiqueta, valor, otras in repetidos
        ]
        return {'warning': {
            'title': self.env._('Puede ser la misma persona'),
            'message': '\n'.join(lineas) + '\n' + self.env._(
                'Revisa que cotizas en la ficha correcta. Para dejar una sola, Gerencia las fusiona en '
                'Socios › Configuración › Posibles duplicados.'),
        }}
