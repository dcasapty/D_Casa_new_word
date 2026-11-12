"""Revisión adversarial, segunda vuelta (M-6): donde ya corrió la 19.0.1.2.0 de antes (que dejaba revisados los lugares
que agregó alguien que HOY es Gerencia), todo lugar agregado a mano que Gerencia no revisó con «Marcar revisado» (sin
«Lo revisó») queda «Por revisar». Los de la tabla cargada no se tocan. (Los que se crean ahora ya nacen bien: los de
Gerencia con «Lo revisó».)"""


def migrate(cr, version):
    cr.execute("""UPDATE dcasa_envio_lugar SET revisado = FALSE, revisado_el = NULL
                   WHERE origen = 'mano' AND revisado_por IS NULL""")
