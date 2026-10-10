"""Telegram de Juan deja de ser un canal abierto: solo contesta a una lista de chats (y al equipo vinculado con Brian).

Para que quien ya probaba a Juan por Telegram no se quede sin respuesta de un día para otro, la lista arranca con los
chats que ya habían hablado con Juan. Se puede editar en Ajustes de Juan. Solo se llena si estaba vacía.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE dcasa_juan_ajustes
           SET telegram_chats_permitidos = (
                 SELECT string_agg(DISTINCT id_externo, E'\\n') FROM dcasa_conversacion
                  WHERE canal = 'telegram' AND id_externo ~ '^[0-9]{3,20}$')
         WHERE COALESCE(telegram_chats_permitidos, '') = ''""")
