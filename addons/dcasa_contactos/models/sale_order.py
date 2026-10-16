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
"""
from odoo import api, fields, models

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
        if not ficha._dcasa_es_ficha():
            return []
        encontrados = []
        for etiqueta, llaves in ficha._dcasa_claves().items():
            for clave in sorted(llaves):
                otras = self.sudo().with_context(active_test=False).search(
                    ficha._dcasa_dominio_fichas() + [('id', '!=', ficha.id)]
                    + ficha._dcasa_dominio_de_la_llave(etiqueta, clave), order='id', limit=MAXIMO_EN_EL_AVISO)
                if otras:
                    valor = claves.telefono_legible(clave) if etiqueta == 'celular' else clave
                    encontrados.append((etiqueta, valor, otras))
        return encontrados


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_id = fields.Many2one(domain=_dominio_del_cliente)

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
