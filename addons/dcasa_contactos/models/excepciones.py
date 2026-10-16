"""Los flujos de Odoo que crean contactos que enseguida se vinculan (usuario, empleado, empresa) o que unen dos
fichas (fusión) no pasan por el candado: su contacto todavía no tiene su vínculo, o el repetido es justo el que se
va a borrar."""
from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from .res_partner import SIN_DUPLICADOS

# Quien lleva uno de estos códigos ya es parte de un programa: dos fichas con código no se fusionan solas.
CODIGOS_DE_PROGRAMA = (
    ('dcasa_socio_codigo', 'socios'),
    ('dcasa_vendedor_codigo', 'vendedores'),
)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        usuarios = super(ResUsers, self.with_context(**{SIN_DUPLICADOS: True})).create(vals_list)
        return usuarios.with_env(self.env)


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        empresas = super(ResCompany, self.with_context(**{SIN_DUPLICADOS: True})).create(vals_list)
        return empresas.with_env(self.env)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _create_work_contacts(self):
        return super(HrEmployee, self.with_context(**{SIN_DUPLICADOS: True}))._create_work_contacts()


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    @api.model
    def _get_ordered_partner(self, partner_ids):
        """La ficha que queda por defecto es la que ya está en un programa (socio o vendedor) y, entre esas, la que
        tiene más puntos movidos; a igual condición, la activa más vieja (lo que hace Odoo)."""
        ordenadas = super()._get_ordered_partner(partner_ids)
        Movimiento = self.env['dcasa.movimiento'].sudo()

        def peso(ficha):
            return (bool(ficha.sudo().dcasa_socio_codigo), bool(ficha.sudo().dcasa_vendedor_codigo),
                    Movimiento.search_count([('partner_id', '=', ficha.id)]))

        # sorted es estable: a igual peso queda el orden de Odoo (la que debe quedar, al final).
        return ordenadas.browse([ficha.id for ficha in sorted(ordenadas, key=peso)])

    def _dcasa_campos_del_programa(self):
        """Los datos de Socios y de vendedores que viven en la ficha y que Odoo no copia al fusionar (copy=False)."""
        return [
            nombre for nombre, campo in self.env['res.partner']._fields.items()
            if nombre.startswith('dcasa_') and campo.store and not campo.compute and not campo.related
            and not campo.copy and campo.type not in ('one2many', 'many2many', 'binary', 'properties')
            and nombre != 'dcasa_socio_estado'
        ]

    def _update_values(self, src_partners, dst_partner):
        super()._update_values(src_partners, dst_partner)
        self._dcasa_traer_datos_del_programa(src_partners, dst_partner)

    def _dcasa_traer_datos_del_programa(self, src_partners, dst_partner):
        """Pasa a la ficha que queda lo de Socios y vendedores que tenía la que se va (código, celular del programa,
        PIN, quién la invitó, si ya se pagó el referido…), en vez de perderlo.

        Solo llena lo que la ficha que queda no tiene: lo que ya tiene manda. Va por SQL, como la propia fusión de
        Odoo con las llaves foráneas: el padrino «se escribe una vez» y las compras ya movidas a esta ficha harían
        que la validación normal lo rechazara. Antes de pasarlo se vacía en la ficha que se va, porque el código y el
        celular son únicos. Los puntos y los asientos ya los movió la fusión."""
        nombres = self._dcasa_campos_del_programa()
        destino = dst_partner.sudo()
        ids_fusion = (src_partners | dst_partner).ids
        origenes = src_partners.sudo()
        for origen in origenes:
            trae_socio = bool(origen.dcasa_socio_codigo) and not destino.dcasa_socio_codigo
            for nombre in nombres + (['dcasa_socio_estado'] if trae_socio else []):
                campo = origen._fields[nombre]
                valor = origen[nombre]
                if not valor or (destino[nombre] and nombre != 'dcasa_socio_estado'):
                    continue
                if campo.type == 'many2one':
                    if valor.id in ids_fusion:
                        continue  # nadie es su propio padrino ni patrocinador
                    valor = valor.id
                self.env.cr.execute(SQL('UPDATE res_partner SET %s = NULL WHERE id = %s',
                                        SQL.identifier(nombre), origen.id))
                self.env.cr.execute(SQL('UPDATE res_partner SET %s = %s WHERE id = %s',
                                        SQL.identifier(nombre), valor, destino.id))
            (origen | destino).invalidate_recordset(nombres + ['dcasa_socio_estado'])

    def _merge(self, partner_ids, dst_partner=None, extra_checks=True):
        fichas = self.env['res.partner'].browse(partner_ids).exists().sudo()
        for campo, quienes in CODIGOS_DE_PROGRAMA:
            if len(fichas.filtered(campo)) > 1:
                raise UserError(self.env._(
                    'Hay más de una ficha con código de %(quienes)s entre las que quieres fusionar. Dos personas '
                    'del programa no se fusionan aquí: se perdería uno de los dos códigos. Revísalo con la dueña '
                    'antes de unirlas.', quienes=quienes))
        # La ficha que queda llega ya leída por el asistente (sin esta excepción): se le pone también a ella, porque es
        # la que recibe los datos de la que se va mientras esa todavía existe.
        contexto = {SIN_DUPLICADOS: True}
        return super(BasePartnerMergeAutomaticWizard, self.with_context(**contexto))._merge(
            partner_ids, dst_partner=dst_partner.with_context(**contexto) if dst_partner else dst_partner,
            extra_checks=extra_checks)
