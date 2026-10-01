#!/usr/bin/env python3
"""Simula ventas/asientos: inserta una fila por intervalo y registra cada COMMIT confirmado.

Cada fila es determinista (monto = id*1.07, glosa = md5(id)) para poder verificar la
restauración sin la base original. El archivo de registro guarda "id,epoch_commit" tras
cada COMMIT: es la verdad de lo que el cliente creyó guardado (para medir el RPO).
Uso: carga.py PUERTO REGISTRO INTERVALO_S [MODO]   (MODO: asiento | cron)
"""
import os, sys, time, psycopg2

port, log, intervalo = int(sys.argv[1]), sys.argv[2], float(sys.argv[3])
modo = sys.argv[4] if len(sys.argv) > 4 else "asiento"
cn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="dcasa")
cur = cn.cursor()
cur.execute("SELECT coalesce(max(id),0) FROM r3_asiento"); i = cur.fetchone()[0]; cn.commit()
with open(log, "a", buffering=1) as f:
    while True:
        if modo == "cron":   # reposo de Odoo: un cron que actualiza su marca cada intervalo
            cur.execute("UPDATE ir_cron SET lastcall = now() WHERE id = (SELECT min(id) FROM ir_cron)")
            cn.commit()
        else:
            i += 1
            cur.execute("INSERT INTO r3_asiento(id, monto, glosa) VALUES (%s, round(%s*1.07,2), md5(%s::text))", (i, i, i))
            cn.commit()
            f.write(f"{i},{time.time():.3f}\n")
        time.sleep(intervalo)
