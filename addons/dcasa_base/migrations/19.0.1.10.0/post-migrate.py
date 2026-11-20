"""Marca, una sola vez, los pedidos que ya existían y nacieron por un flujo digital (``dcasa_nacio_en_web``).

Es el testigo de origen de la venta online (``models/venta_online.py``). Desde aquí solo lo escribe el flujo real (el
carrito del sitio, ``website._create_cart``, y la herramienta de cotizar de Juan); a lo que ya existe se le pone UNA vez
por tener ``website_id`` hoy o por haberlo creado el usuario del asistente Juan (antes de esta versión nadie podía
haberlo fabricado, porque el origen no se medía). Además, a los pedidos de la página ya
confirmados y que todavía no están pagados por completo se les mira el chat de Juan UNA vez (una vendedora que le
escribió al cliente en los 30 días anteriores a la confirmación): sin eso, un pedido atendido por una vendedora antes
del despliegue y cobrado después contaría como online.
"""


def _existe(cr, tabla, columna=None):
    if columna:
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                   [tabla, columna])
    else:
        cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", [tabla])
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _existe(cr, 'sale_order', 'website_id'):
        return
    cr.execute("""
        UPDATE sale_order SET dcasa_nacio_en_web = TRUE
         WHERE website_id IS NOT NULL AND dcasa_nacio_en_web IS NOT TRUE""")
    # Las cotizaciones que armó Juan (la herramienta de cotizar corre con el usuario del asistente).
    cr.execute("""
        UPDATE sale_order o SET dcasa_nacio_en_web = TRUE,
                                dcasa_creada_por_id = COALESCE(o.dcasa_creada_por_id, d.res_id)
          FROM ir_model_data d
         WHERE d.module = 'dcasa_conversaciones' AND d.name = 'user_juan' AND d.model = 'res.users'
           AND o.create_uid = d.res_id AND o.dcasa_nacio_en_web IS NOT TRUE""")
    if _existe(cr, 'dcasa_mensaje') and _existe(cr, 'dcasa_conversacion'):
        cr.execute("""
            UPDATE sale_order o SET dcasa_llevada_por_vendedora = TRUE
             WHERE o.dcasa_nacio_en_web AND o.state = 'sale' AND o.dcasa_llevada_por_vendedora IS NOT TRUE
               AND NOT EXISTS (
                    SELECT 1 FROM sale_order_line l
                      JOIN sale_order_line_invoice_rel r ON r.order_line_id = l.id
                      JOIN account_move_line ml ON ml.id = r.invoice_line_id
                      JOIN account_move m ON m.id = ml.move_id
                     WHERE l.order_id = o.id AND m.move_type = 'out_invoice' AND m.state = 'posted'
                       AND m.payment_state IN ('paid', 'in_payment'))
               AND EXISTS (
                    SELECT 1 FROM dcasa_mensaje b
                      JOIN dcasa_conversacion c ON c.id = b.conversacion_id
                      JOIN res_partner p ON p.id = c.partner_id
                      JOIN res_partner pc ON pc.id = o.partner_id
                     WHERE p.commercial_partner_id = pc.commercial_partner_id AND b.tipo = 'mensaje'
                       AND b.autor = 'vendedora' AND b.ts <= COALESCE(o.date_order, now())
                       AND b.ts >= COALESCE(o.date_order, now()) - interval '30 days')""")
    cr.execute("""
        UPDATE sale_order
           SET dcasa_venta_online = COALESCE(dcasa_nacio_en_web, FALSE)
                                    AND NOT COALESCE(dcasa_llevada_por_vendedora, FALSE)
         WHERE dcasa_venta_online IS DISTINCT FROM (COALESCE(dcasa_nacio_en_web, FALSE)
                                    AND NOT COALESCE(dcasa_llevada_por_vendedora, FALSE))""")
