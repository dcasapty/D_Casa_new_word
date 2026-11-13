"""Revisión adversarial (rvf) de «Busca con una foto»: los topes aguantan pedidos al mismo tiempo (se puede repetir).

Se corre con ``odoo-bin shell -d <base> < scripts/revision_rvf_carrera_foto.py`` sobre una base con dcasa_buscar_foto
instalado (NO la de producción: borra las filas de dcasa.buscar.foto.uso y toca los topes; al final los deja vacíos).

Cada hilo es una petición web de verdad: su propio cursor (su propia transacción, como en producción) y el Worker
simulado tarda 1,5 s. Con el código revisado la fila de uso se creaba DENTRO de la transacción de la petición y no se
confirmaba hasta el final: las que llegaban mientras otra esperaba al Worker no la veían y pasaban el tope, y lo que
reventaba después de la IA no quedaba contado. Ahora (models/buscar_foto.py): el cupo se reserva en una transacción
corta aparte, confirmada antes de llamar al Worker, bajo ``pg_advisory_xact_lock``; y no hay más de 3 búsquedas a la vez
por proceso (la cuarta, «ahora no podemos» al instante).

A. Tope del día 1, cinco visitantes distintos a la vez: llega uno solo a la IA.
B. Tope por conexión 1, cinco sesiones nuevas desde la MISMA IP a la vez: llega uno solo.
C. Algo revienta DESPUÉS de la IA y la transacción de la petición se deshace: la búsqueda igual queda contada.
D. Topes altos y cinco a la vez: nunca más de 3 esperando al Worker; las demás, «no_ahora» sin esperar.
En todos: las transacciones abiertas («idle in transaction») mientras se espera al Worker no pasan de 3.
Sale con ``FALLA`` si algo de eso no se cumple; si no, ``OK``.
"""
import base64
import threading
import time
from unittest.mock import patch

from odoo import SUPERUSER_ID, api
from odoo.sql_db import db_connect

reg = env.registry  # noqa: F821 — lo pone odoo-bin shell
DB = env.cr.dbname  # noqa: F821
FOTO = base64.b64encode(b'\xff\xd8\xff\xe0' + b'foto inventada' * 8 + b'\xff\xd9').decode()
Modelo = type(env['dcasa.buscar.foto'])  # noqa: F821
MUEBLE = {'tipo': 'producto', 'codigos': [], 'categoria': 'cama', 'medida': None, 'parece_pago': False,
          'parece_identidad': False}
medida = {'abiertas': [], 'leidas': 0, 'a_la_vez': 0, 'max_a_la_vez': 0}
cerrojo = threading.Lock()


def preparar(dia, conexion, visitante=100):
    with reg.cursor() as cr:
        e = api.Environment(cr, SUPERUSER_ID, {})
        e['dcasa.buscar.foto.uso'].search([]).unlink()
        p = e['ir.config_parameter']
        p.set_param('dcasa_buscar_foto.activo', 'True')
        p.set_param('dcasa_buscar_foto.tope_dia', str(dia))
        p.set_param('dcasa_buscar_foto.tope_conexion_hora', str(conexion))
        p.set_param('dcasa_buscar_foto.tope_visitante_hora', str(visitante))
    medida.update(abiertas=[], leidas=0, a_la_vez=0, max_a_la_vez=0)


def filas():
    with reg.cursor() as cr:
        cr.execute('SELECT resultado, count(*) FROM dcasa_buscar_foto_uso GROUP BY resultado')
        return dict(cr.fetchall())


def leer_lento(self, datos, mime):
    """El Worker de Juan, simulado: tarda 1,5 s. Mientras tanto se miran las transacciones abiertas."""
    with cerrojo:
        medida['leidas'] += 1
        medida['a_la_vez'] += 1
        medida['max_a_la_vez'] = max(medida['max_a_la_vez'], medida['a_la_vez'])
    try:
        time.sleep(0.7)
        with db_connect(DB).cursor() as cr:
            cr.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND state = 'idle in transaction'",
                       [DB])
            medida['abiertas'].append(cr.fetchone()[0])
        time.sleep(0.8)
        return dict(MUEBLE)
    finally:
        with cerrojo:
            medida['a_la_vez'] -= 1


def peticion(estados, sesion, ip):
    try:
        with reg.cursor() as cr:
            e = api.Environment(cr, SUPERUSER_ID, {})
            website = e['website'].browse(1)
            publico = e(user=website.user_id.id)
            estados.append(publico['dcasa.buscar.foto']._dcasa_buscar(FOTO, website, sesion=sesion, conexion=ip)[
                'estado'])
    except RuntimeError:
        estados.append('reventó')   # como un error 500: la transacción de la petición se deshace


def a_la_vez(n, ips, pausa=0.1):
    estados = []
    hilos = [threading.Thread(target=peticion, args=(estados, f'sesion-{i}', ips(i))) for i in range(n)]
    for hilo in hilos:
        hilo.start()
        time.sleep(pausa)
    for hilo in hilos:
        hilo.join()
    return estados


def revienta(self, website, lectura):
    raise RuntimeError('algo reventó después de la IA')


fallas = []


def exigir(condicion, texto):
    if not condicion:
        fallas.append(texto)


with patch.object(Modelo, '_dcasa_leer', leer_lento):
    # A. Tope del día = 1; cinco visitantes distintos a la vez.
    preparar(dia=1, conexion=100)
    estados = a_la_vez(5, lambda i: f'10.0.{i + 1}.1')
    hechas = filas()
    print(f'A. tope del día 1 → {medida["leidas"]} llegaron a la IA, filas {hechas}, estados {sorted(estados)}; '
          f'transacciones abiertas esperando al Worker: {max(medida["abiertas"] or [0])}')
    exigir(medida['leidas'] <= 1 and sum(hechas.values()) <= 1, f'A: tope del día 1 y llegaron {medida["leidas"]}')
    exigir(max(medida['abiertas'] or [0]) <= 3, f'A: {max(medida["abiertas"])} transacciones abiertas')

    # B. Tope por conexión = 1; cinco sesiones nuevas desde la MISMA IP a la vez.
    preparar(dia=1000, conexion=1)
    estados = a_la_vez(5, lambda i: '200.46.7.7')
    hechas = filas()
    print(f'B. tope por conexión 1 → {medida["leidas"]} llegaron a la IA desde la misma IP, filas {hechas}')
    exigir(medida['leidas'] <= 1 and sum(hechas.values()) <= 1, f'B: tope por conexión 1 y llegaron {medida["leidas"]}')

    # C. Revienta después de la IA (la transacción de la petición se deshace): igual queda contada.
    preparar(dia=1000, conexion=100)
    with patch.object(Modelo, '_dcasa_parecidos', revienta):
        estados = a_la_vez(1, lambda i: '200.46.7.8')
    hechas = filas()
    print(f'C. revienta después de la IA → estados {estados}, filas {hechas}')
    exigir(estados == ['reventó'] and hechas == {'no_ahora': 1}, f'C: la búsqueda que reventó dejó {hechas}')

    # D. Topes altos, cinco a la vez: no más de 3 esperando al Worker; las demás, «no_ahora» sin esperar.
    preparar(dia=1000, conexion=100)
    inicio = time.monotonic()
    estados = a_la_vez(5, lambda i: f'10.1.{i + 1}.1', pausa=0.05)
    hechas = filas()
    print(f'D. cinco a la vez → a lo sumo {medida["max_a_la_vez"]} esperando al Worker, estados {sorted(estados)}, '
          f'filas {hechas}, {time.monotonic() - inicio:.1f} s; '
          f'transacciones abiertas: {max(medida["abiertas"] or [0])}')
    exigir(medida['max_a_la_vez'] <= 3, f'D: {medida["max_a_la_vez"]} esperando al Worker a la vez')
    exigir(estados.count('no_ahora') >= 2 and sum(hechas.values()) == medida['leidas'],
           f'D: estados {estados}, filas {hechas}')
    exigir(max(medida['abiertas'] or [0]) <= 3, f'D: {max(medida["abiertas"])} transacciones abiertas')

with reg.cursor() as cr:
    e = api.Environment(cr, SUPERUSER_ID, {})
    e['dcasa.buscar.foto.uso'].search([]).unlink()
    for clave in ('tope_dia', 'tope_conexion_hora', 'tope_visitante_hora'):
        e['ir.config_parameter'].set_param(f'dcasa_buscar_foto.{clave}', '')

print('FALLA: ' + '; '.join(fallas) if fallas else 'OK: los topes aguantan pedidos al mismo tiempo')
