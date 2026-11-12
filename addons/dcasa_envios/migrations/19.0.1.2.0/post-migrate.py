"""Revisión adversarial del 2026-11-12 (I7; segunda vuelta, M-6): todo lugar agregado a mano en Odoo queda «Por
revisar» (Gerencia los revisa una vez), lo haya agregado quien sea: el rol de hoy no dice quién lo agregó ni si se
revisó. Los de la tabla cargada (el archivo de Gerencia) quedan revisados."""


def migrate(cr, version):
    cr.execute("""UPDATE dcasa_envio_lugar SET revisado = FALSE, revisado_por = NULL, revisado_el = NULL
                   WHERE origen = 'mano'""")
