"""Cada vendedora ve solo lo suyo (pedido de la dueña, 2026-10-16) con su interruptor (2026-10-17).

1. El rol Vendedora deja de implicar «Ventas: todos los documentos»: queda encendido «Cada vendedora ve solo sus
   documentos», lo de fábrica. Se hace aquí, UNA vez, y no con ``(3, …)`` en security/dcasa_roles.xml: eso correría en
   cada despliegue y volvería a encender el interruptor si Gerencia lo apagó.
2. A la Vendedora que tenía ese grupo puesto a mano (sin Caja, Ventas administrador ni lectura contable) se le quita, y
   se avisa en el registro si nadie tiene Caja. No se le asigna Caja a nadie: lo decide la dueña.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    usuarios = env['res.users']
    usuarios._dcasa_encender_restriccion_al_migrar()
    usuarios._dcasa_quitar_todos_los_documentos()
