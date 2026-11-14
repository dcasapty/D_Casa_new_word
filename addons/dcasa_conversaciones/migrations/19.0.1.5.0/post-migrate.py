"""Avisos de Telegram ordenados (pedido de la dueña, 2026-11-13: «son muchos o muy repetidos… a la 1 de la mañana veo
vendedoras activas»). En la base que ya existe:

* se enciende «De noche nadie recibe clientes» (``reparto_nadie_de_noche``): fuera del horario nadie recibe clientes ni
  avisos y al abrir cada vendedora recibe un solo aviso con su lista;
* se apaga «Avisar de fotos y archivos» (``avisar_archivos``): las fotos que no son comprobante ni cédula se ven en el
  chat, sin aviso. El interruptor se queda por si algún día lo quieren.

Con el ORM (no con SQL directo): los dos ajustes tienen ``tracking`` y el cambio queda en el historial de Ajustes de
Juan, con una nota que dice qué cambió y por qué (si Gerencia lo había encendido a propósito, sabe dónde volver a
encenderlo).

Ojo: al actualizar, Odoo crea la columna nueva de «De noche nadie recibe clientes» y la llena con su valor de fábrica
(encendido) ANTES de esta migración: aquí ya se ve encendido. Por eso, viniendo de una versión anterior a 19.0.1.5.0, la
nota siempre dice que se encendió (es lo que pasó al actualizar). Idempotente: el interruptor y las fotos solo se
escriben si no están como deben, y sin nada que contar no deja nota."""
from odoo import SUPERUSER_ID, api
from odoo.tools import parse_version

VERSION = '19.0.1.5.0'

NOTA = ('Actualización de los avisos de Telegram (pedido de la dueña, 2026-11-13: «son muchos o muy repetidos»): %s. '
        'Si lo quieres de otra forma, cámbialo aquí mismo.')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    de_antes = not version or parse_version(version) < parse_version(VERSION)
    for ajustes in env['dcasa.juan.ajustes'].search([]):
        cambios, que = {}, []
        if not ajustes.reparto_nadie_de_noche:
            cambios['reparto_nadie_de_noche'] = True
        if de_antes or cambios:
            que.append('se encendió «De noche nadie recibe clientes» (fuera del horario nadie recibe clientes ni '
                       'avisos; al abrir, cada vendedora recibe un solo aviso con su lista)')
        if ajustes.avisar_archivos:
            cambios['avisar_archivos'] = False
            que.append('se apagó «Avisar de fotos y archivos» (las fotos que no son comprobante ni cédula se ven en el '
                       'chat, sin aviso; los comprobantes, las cédulas y lo que Juan no puede leer siguen avisando)')
        if not que:
            continue
        if cambios:
            ajustes.write(cambios)
        ajustes.message_post(body=NOTA % '; '.join(que), message_type='comment', subtype_xmlid='mail.mt_note')
