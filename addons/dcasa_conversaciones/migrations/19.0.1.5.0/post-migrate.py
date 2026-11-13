"""Avisos de Telegram ordenados (pedido de la dueña, 2026-11-13: «son muchos o muy repetidos… a la 1 de la mañana veo
vendedoras activas»). En la base que ya existe:

* se enciende «De noche nadie recibe clientes» (``reparto_nadie_de_noche``): fuera del horario nadie recibe clientes ni
  avisos y al abrir cada vendedora recibe un solo aviso con su lista;
* se apaga «Avisar de fotos y archivos» (``avisar_archivos``): las fotos que no son comprobante ni cédula se ven en el
  chat, sin aviso. El interruptor se queda por si algún día lo quieren.

Lo demás de los ajustes no se toca."""


def migrate(cr, version):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'dcasa_juan_ajustes' AND column_name = 'reparto_nadie_de_noche'""")
    if cr.fetchone():
        cr.execute("UPDATE dcasa_juan_ajustes SET reparto_nadie_de_noche = TRUE")
    cr.execute("UPDATE dcasa_juan_ajustes SET avisar_archivos = FALSE")
