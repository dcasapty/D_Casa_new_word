"""Quién ve solo lo suyo (pedido de la dueña, 2026-10-16), el interruptor que lo enciende o lo apaga y la migración.

«Solo lo suyo» es quien vende o factura sin ver los documentos de toda la tienda: la Vendedora. Caja (Ventas «todos
los documentos»), contabilidad y Gerencia ven todo. Las reglas de registro (security/dcasa_reglas_*.xml) hacen el
filtro; aquí está la pregunta que usan el código (dueña del documento, títulos, Brian), el interruptor y la migración.

**El interruptor** «Cada vendedora ve solo sus documentos» (pedido de la dueña, 2026-10-17: «así como está funciona
bien… si el día de mañana esto genera algún problema operativo se puede retroceder fácilmente»). Encendido (lo de
fábrica), el rol Vendedora NO implica «Ventas: todos los documentos»; apagado, sí, y todas las vendedoras vuelven a ver
todo como antes, sin tocar a ninguna persona: solo cambia lo que implica el rol. Caja y Gerencia ven todo siempre.
La implicación del rol ES el estado del interruptor (no hay otro dato que se pueda desincronizar), y por eso
security/dcasa_roles.xml no la nombra: si la nombrara, cada despliegue (``-u``) volvería a encender o a apagar.
"""
import logging

from odoo import Command, api, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

TODOS_LOS_DOCUMENTOS = 'sales_team.group_sale_salesman_all_leads'
VENDEDORA = 'dcasa_base.group_vendedora'
# Quien puede mover el interruptor: Gerencia y los administradores del sistema.
CAMBIAN_EL_INTERRUPTOR = ('dcasa_base.group_gerencia', 'base.group_system')
# Quien tiene alguno de estos grupos ve los documentos de clientes de toda la tienda.
VEN_TODO = (
    TODOS_LOS_DOCUMENTOS, 'account.group_account_readonly', 'account.group_account_user',
    'account.group_account_manager',
)
# Quien tiene alguno de estos vende o factura (si no, «solo lo suyo» no aplica: no crea pedidos ni facturas).
VENDE_O_FACTURA = ('sales_team.group_sale_salesman', 'account.group_account_invoice')


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _dcasa_solo_lo_suyo(self):
        """¿Esta persona ve solo sus cotizaciones, pedidos, facturas, notas y cobros (y los sin vendedora)?

        Usuario interno que vende o factura y que no tiene «Ventas: todos los documentos» (Caja, Gerencia) ni
        contabilidad (lector, contador o administrador contable). El superusuario y los procesos automáticos no.
        Sin registro, pregunta por quien está conectado.
        """
        usuario = self[:1] or self.env.user
        if usuario._is_superuser() or not usuario._is_internal():
            return False
        if not any(usuario.has_group(grupo) for grupo in VENDE_O_FACTURA):
            return False
        return not any(usuario.has_group(grupo) for grupo in VEN_TODO)

    # ------------------------------------------------------------------
    # El interruptor «Cada vendedora ve solo sus documentos»
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_restriccion_activa(self):
        """¿Está encendido «Cada vendedora ve solo sus documentos»? Sí, mientras el rol Vendedora no implique «Ventas:
        todos los documentos». Sin los grupos (módulo a medio instalar), no: no hay nada que restringir."""
        vendedora = self.env.ref(VENDEDORA, raise_if_not_found=False)
        todos = self.env.ref(TODOS_LOS_DOCUMENTOS, raise_if_not_found=False)
        if not vendedora or not todos:
            return False
        return todos not in vendedora.sudo().all_implied_ids

    @api.model
    def _dcasa_poner_restriccion(self, activa):
        """Enciende (``activa``) o apaga «Cada vendedora ve solo sus documentos». Devuelve True si cambió algo.

        Solo Gerencia o un administrador (se comprueba aquí, en el servidor, antes del ``sudo``). No toca ninguna ficha
        de usuario: cambia lo que implica el rol Vendedora, y Odoo recalcula al momento lo que ve cada persona (Caja y
        Gerencia lo traen por su cuenta, así que no cambian). En el registro queda quién lo cambió (su id).
        """
        if not self.env.su and not any(self.env.user.has_group(g) for g in CAMBIAN_EL_INTERRUPTOR):
            raise AccessError(self.env._('Solo Gerencia o un administrador eligen qué documentos ve cada vendedora.'))
        activa = bool(activa)
        if activa == self._dcasa_restriccion_activa():
            return False
        vendedora = self.env.ref(VENDEDORA).sudo()
        todos = self.env.ref(TODOS_LOS_DOCUMENTOS).sudo()
        if activa:
            vendedora.write({'implied_ids': [Command.unlink(todos.id)]})
        else:
            vendedora.write({'implied_ids': [Command.link(todos.id)]})
        _logger.info("D'CASA permisos: «Cada vendedora ve solo sus documentos» quedó %s (usuario id %s).",
                     'ENCENDIDO' if activa else 'APAGADO: todas ven todo', self.env.uid)
        return True

    # ------------------------------------------------------------------
    # Migración 19.0.1.8.0
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_encender_restriccion_al_migrar(self):
        """Migración 19.0.1.8.0: la base de antes trae el rol Vendedora con «Ventas: todos los documentos». Se le quita
        UNA vez (queda el interruptor encendido, lo de fábrica). No se hace en el XML del rol con ``(3, …)`` porque
        correría en cada despliegue y volvería a encender un interruptor que Gerencia apagó. Devuelve True si cambió."""
        vendedora = self.env.ref(VENDEDORA, raise_if_not_found=False)
        todos = self.env.ref(TODOS_LOS_DOCUMENTOS, raise_if_not_found=False)
        if not vendedora or not todos or todos not in vendedora.implied_ids:
            return False
        vendedora.sudo().write({'implied_ids': [Command.unlink(todos.id)]})
        _logger.info("D'CASA permisos: el rol Vendedora deja de implicar «Ventas: todos los documentos» "
                     "(«Cada vendedora ve solo sus documentos» encendido).")
        return True

    @api.model
    def _dcasa_quitar_todos_los_documentos(self):
        """Migración 19.0.1.8.0: a la Vendedora que tiene «Ventas: todos los documentos» puesto a mano se le quita.

        La Vendedora ya no lo implica (security/dcasa_roles.xml), pero si alguien se lo puso a mano en la ficha (o
        Brian la hizo «cajero» sin quitarle Vendedora), lo seguiría teniendo y vería lo de sus compañeras. No se
        toca a quien tiene Caja, Ventas administrador o lectura contable: esas personas ven todo a propósito.
        Activos o no (un usuario archivado puede volver). En el registro va solo la cantidad, sin nombres.
        Devuelve cuántos usuarios cambió.
        """
        todos = self.env.ref(TODOS_LOS_DOCUMENTOS, raise_if_not_found=False)
        vendedora = self.env.ref('dcasa_base.group_vendedora', raise_if_not_found=False)
        if not todos or not vendedora:
            return 0
        respetar = self.env['res.groups']
        for xmlid in ('dcasa_base.group_caja', 'sales_team.group_sale_manager', 'account.group_account_readonly'):
            respetar |= self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.groups']
        usuarios = self.sudo().with_context(active_test=False).search([('group_ids', 'in', todos.ids)])
        usuarios = usuarios.filtered(
            lambda u: vendedora in u.all_group_ids and not (respetar & u.all_group_ids))
        if usuarios:
            usuarios.write({'group_ids': [Command.unlink(todos.id)]})
        _logger.info("D'CASA permisos: a %s vendedora(s) se les quitó «Ventas: todos los documentos» puesto a mano.",
                     len(usuarios))
        self._dcasa_avisar_si_nadie_tiene_caja()
        return len(usuarios)

    @api.model
    def _dcasa_avisar_si_nadie_tiene_caja(self):
        """Deja en el registro un aviso si nadie (sin contar Gerencia) tiene el rol Caja. Devuelve True si avisó."""
        caja = self.env.ref('dcasa_base.group_caja', raise_if_not_found=False)
        gerencia = self.env.ref('dcasa_base.group_gerencia', raise_if_not_found=False)
        if not caja:
            return False
        con_caja = self.sudo().search([('share', '=', False), ('all_group_ids', 'in', caja.ids)])
        if gerencia:
            con_caja = con_caja.filtered(lambda u: gerencia not in u.all_group_ids)
        if con_caja:
            return False
        _logger.warning("D'CASA permisos: nadie tiene el rol Caja: asígnalo antes de abrir (Ajustes › Usuarios › "
                        "la persona que cobra › «D'CASA: Caja», o Brian: «ponle el rol cajero a …»).")
        return True
