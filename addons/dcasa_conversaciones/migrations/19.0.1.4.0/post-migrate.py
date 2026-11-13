"""Comentarios de Instagram y Facebook (2.ª vuelta de la revisión, 2026-11-13): la respuesta pública ya no lleva el
nombre de nadie («lo que ve todo el mundo no lleva nada que escriba quien comenta»). Un texto guardado con ``{nombre}``
(la frase de fábrica de antes u otra) se queda sin él, limpio: «¡Hola, {nombre}! Te escribimos…» → «¡Hola! Te
escribimos…». Si el resultado no quedara bien escrito, va la frase de fábrica nueva."""
import re

from odoo.addons.dcasa_conversaciones.models.ajustes import (
    RE_BUEN_INICIO,
    RE_DIRECCION_WEB,
    RE_PAR_VACIO,
    TEXTO_PUBLICO_COMENTARIOS,
    quitar_nombre,
)


def migrate(cr, version):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'dcasa_juan_ajustes' AND column_name = 'comentarios_texto_publico'""")
    if not cr.fetchone():
        return
    cr.execute("SELECT id, comentarios_texto_publico FROM dcasa_juan_ajustes "
               "WHERE comentarios_texto_publico LIKE '%{%'")
    for id_, texto in cr.fetchall():
        nuevo = quitar_nombre(texto or '').strip()
        bien = (nuevo and not re.search(r'[{}]', nuevo) and not RE_DIRECCION_WEB.search(nuevo)
                and RE_BUEN_INICIO.match(nuevo) and not RE_PAR_VACIO.search(nuevo))
        cr.execute("UPDATE dcasa_juan_ajustes SET comentarios_texto_publico = %s WHERE id = %s",
                   [nuevo if bien else TEXTO_PUBLICO_COMENTARIOS, id_])
