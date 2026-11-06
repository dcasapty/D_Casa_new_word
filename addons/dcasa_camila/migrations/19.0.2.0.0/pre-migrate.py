"""Etapa 2 (decisión de la dueña, 2026-11-06): puede haber varias campañas abiertas a la vez. Se quita el índice único
de la etapa 1 («una sola abierta»); el tope de 15 días pasa a ser por cliente (``dcasa.camila.destinatario``)."""


def migrate(cr, version):
    cr.execute('DROP INDEX IF EXISTS dcasa_camila_campana__una_abierta')
