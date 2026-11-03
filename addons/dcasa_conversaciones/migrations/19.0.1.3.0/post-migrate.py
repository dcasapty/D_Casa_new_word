"""Las notas de voz que llegaron antes del arreglo del 2026-11-03 se guardaron como «application/octet-stream» con el
nombre «adjunto»: WhatsApp las manda como «audio/ogg; codecs=opus» y ese «; codecs…» hacía que se perdiera el tipo. Las
de WhatsApp y Telegram son siempre OGG (Opus); un audio con otro formato trae un tipo sin parámetros y no cayó aquí.
Solo se tocan los adjuntos de mensajes de clientes cuyo canal dijo «audio»."""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_attachment
           SET mimetype = 'audio/ogg',
               name = CASE WHEN name = 'adjunto' THEN 'nota-de-voz.ogg'
                           WHEN position('.' IN name) = 0 THEN name || '.ogg'
                           ELSE name END
         WHERE res_model = 'dcasa.mensaje' AND description = 'audio'
           AND COALESCE(mimetype, 'application/octet-stream') = 'application/octet-stream'""")
