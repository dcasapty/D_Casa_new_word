"""Los correos de Odoo que listan productos los nombran en formato título (F5, decisión de la dueña 2026-10-22).

Por dentro los nombres van en MAYÚSCULAS; el cliente los lee «Cama Queen Tapizada» (``dcasa_base/nombres.py``). Dos
correos de Odoo pintan el nombre tal cual: la confirmación del pedido y el del carrito abandonado. Sus plantillas
son datos (``noupdate``) que la tienda puede editar, así que no se reemplazan enteras: solo se cambia la expresión
que pinta el nombre, en todos los idiomas, y solo si sigue como la dejó Odoo. Se puede repetir.
"""
from psycopg2.extras import Json

CAMBIOS = {
    'sale.mail_template_sale_confirmation': [
        ('t-out="line.product_id.name or \'\'"', 't-out="line.product_id._dcasa_nombre_cliente() or \'\'"'),
        ('t-out="line.name or \'\'"', 't-out="line._dcasa_nombre_cliente() or \'\'"'),
    ],
    'website_sale.mail_template_sale_cart_recovery': [
        ('t-out="line.product_id.display_name or \'\'"', 't-out="line.product_id._dcasa_nombre_cliente() or \'\'"'),
        ('t-out="line.name or \'\'"', 't-out="line._dcasa_nombre_cliente() or \'\'"'),
    ],
}


def nombres_en_correos(env):
    """Aplica ``CAMBIOS``. Devuelve las plantillas que cambió."""
    cambiadas = env['mail.template']
    for xmlid, cambios in CAMBIOS.items():
        plantilla = env.ref(xmlid, raise_if_not_found=False)
        if not plantilla:
            continue
        plantilla.flush_recordset(['body_html'])
        env.cr.execute('SELECT body_html FROM mail_template WHERE id = %s', [plantilla.id])
        cuerpos = env.cr.fetchone()[0] or {}
        nuevos = {}
        for idioma, cuerpo in cuerpos.items():
            texto = cuerpo or ''
            for viejo, nuevo in cambios:
                texto = texto.replace(viejo, nuevo)
            nuevos[idioma] = texto
        if nuevos != cuerpos:
            env.cr.execute('UPDATE mail_template SET body_html = %s WHERE id = %s', [Json(nuevos), plantilla.id])
            plantilla.invalidate_recordset(['body_html'])
            cambiadas |= plantilla
    return cambiadas
