"""Compras › Reponer pasa a ser una pantalla propia (2026-10-22): el asistente ``dcasa.reponer`` (TransientModel) y sus
filas ``dcasa.reponer.linea`` ya no existen como tablas (``dcasa.reponer`` es ahora un AbstractModel sin datos). Odoo
borra sus modelos y vistas, pero deja las dos tablas temporales: aquí se quitan. Solo guardaban filtros y filas de
pantalla de un rato (nada que se pierda). Es seguro de repetir.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    for tabla in ('dcasa_reponer_linea', 'dcasa_reponer'):
        cr.execute("SELECT 1 FROM pg_class WHERE relname = %s AND relkind = 'r'", (tabla,))
        if cr.fetchone():
            cr.execute(f'DROP TABLE {tabla}')  # noqa: S608 (nombre fijo, no viene de afuera)
            _logger.info('Reponer: se quitó la tabla vieja %s.', tabla)
