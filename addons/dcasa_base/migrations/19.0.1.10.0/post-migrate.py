"""Marca, una sola vez, los pedidos que ya existían y nacieron en la tienda en línea (``dcasa_nacio_en_web``).

Es el testigo de origen de la venta online (``models/venta_online.py``): desde aquí se escribe al crear el pedido y nadie
lo cambia. Solo los pedidos con ``website_id`` hoy. Ninguna otra marca se toca: lo que ya pasó no se vuelve a clasificar.
"""


def migrate(cr, version):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'sale_order' AND column_name = 'website_id'")
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE sale_order SET dcasa_nacio_en_web = TRUE
         WHERE website_id IS NOT NULL AND dcasa_nacio_en_web IS NOT TRUE""")
    cr.execute("""
        UPDATE sale_order
           SET dcasa_venta_online = (COALESCE(dcasa_nacio_en_web, FALSE)
                                     AND NOT COALESCE(dcasa_llevada_por_vendedora, FALSE))
                                    OR COALESCE(dcasa_via_andres, FALSE)
         WHERE dcasa_venta_online IS DISTINCT FROM ((COALESCE(dcasa_nacio_en_web, FALSE)
                                     AND NOT COALESCE(dcasa_llevada_por_vendedora, FALSE))
                                    OR COALESCE(dcasa_via_andres, FALSE))""")
