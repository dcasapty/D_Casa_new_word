"""Las notas de voz que llegaron antes del arreglo del 2026-11-03 se guardaron como «application/octet-stream» con el
nombre «adjunto»: WhatsApp las manda como «audio/ogg; codecs=opus» y ese «; codecs…» hacía que se perdiera el tipo. Las
de WhatsApp y Telegram son siempre OGG (Opus); un audio con otro formato trae un tipo sin parámetros y no cayó aquí.
Solo se tocan los adjuntos de WhatsApp y Telegram cuyo canal dijo «audio» (Messenger e Instagram pueden mandar otro
formato)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_attachment a
           SET mimetype = 'audio/ogg',
               name = CASE WHEN a.name = 'adjunto' THEN 'nota-de-voz.ogg'
                           WHEN position('.' IN a.name) = 0 THEN a.name || '.ogg'
                           ELSE a.name END
          FROM dcasa_mensaje m
          JOIN dcasa_conversacion c ON c.id = m.conversacion_id
         WHERE a.res_model = 'dcasa.mensaje' AND a.res_id = m.id AND a.description = 'audio'
           AND c.canal IN ('whatsapp_cloud', 'whatsapp_qr', 'telegram')
           AND COALESCE(a.mimetype, 'application/octet-stream') = 'application/octet-stream'""")
