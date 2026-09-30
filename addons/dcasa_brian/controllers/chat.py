"""Chat de Brian en el panel: no necesita rutas HTTP propias.

La interfaz (static/src/js/brian_panel.js) habla con ``brian.conversacion`` por
``orm.call`` (/web/dataset/call_kw, con la sesión del usuario) y sube los adjuntos como
``ir.attachment`` con ``orm.create`` (res_model='brian.conversacion', res_id=conversación).
"""
