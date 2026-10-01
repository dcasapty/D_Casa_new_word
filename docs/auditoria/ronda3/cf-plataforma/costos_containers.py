#!/usr/bin/env python3
"""Recalculo del costo mensual de Odoo en Cloudflare Containers (ronda 3).

Autor: r3-cf-plataforma, 2026-10-01. Solo aritmetica; ejecutar con `python3 costos_containers.py`.

Tarifas OFICIALES (https://developers.cloudflare.com/containers/platform/pricing/, Last updated 2026-08-28):
  - Cobro cada 10 ms mientras la instancia corre.
  - Memoria: 25 GiB-h/mes incluidas; $0.0000025 por GiB-s extra  (se cobra lo APROVISIONADO).
  - CPU:     375 vCPU-min/mes incluidos; $0.000020 por vCPU-s extra (se cobra el USO ACTIVO).
  - Disco:   200 GB-h/mes incluidos; $0.00000007 por GB-s extra   (se cobra lo APROVISIONADO).
  - Plan Workers Paid: $5/mes (obligatorio para Containers).
Tipos (https://developers.cloudflare.com/containers/platform/limits/, Last updated 2026-09-30):
  basic 1/4 vCPU 1 GiB 4 GB; standard-1 1/2 vCPU 4 GiB 8 GB; standard-2 1 vCPU 6 GiB 12 GB.
Durable Object del contenedor (https://developers.cloudflare.com/durable-objects/platform/pricing/,
Last updated 2026-09-30): 400 000 GB-s/mes incluidos, se factura a 128 MB; $12.50 por millon de GB-s
(redondeo al millon siguiente). 1 M solicitudes/mes incluidas.

Supuestos PROPIOS (no medidos; reemplazar cuando r3-odoo-medicion publique datos reales):
  - Mes de 30 dias (720 h). Horario comercial = 12 h x 26 dias = 312 h.
  - Uso de CPU = fraccion del vCPU aprovisionado: 3 %, 10 %, 25 %.
  - "A demanda": ver horas_a_demanda().
"""

from __future__ import annotations

MEM_INCL_GIBS = 25 * 3600          # GiB-s
CPU_INCL_VCPUS = 375 * 60          # vCPU-s
DISK_INCL_GBS = 200 * 3600         # GB-s
P_MEM = 0.0000025
P_CPU = 0.000020
P_DISK = 0.00000007
PLAN = 5.00

DO_INCL_GBS = 400_000
DO_GB = 0.125                      # 128 MB facturados

TIPOS = {
    "basic": (0.25, 1, 4),
    "standard-1": (0.5, 4, 8),
    "standard-2": (1.0, 6, 12),
}
USOS = (0.03, 0.10, 0.25)


def horas_a_demanda(sleep_min: float, bursts_staff: int = 4, min_staff: float = 45,
                    dias_staff: int = 26, despertares_web: int = 10, min_web: float = 2,
                    dias_web: int = 30) -> float:
    """Horas activas al mes si el contenedor duerme de verdad (sin cron que lo despierte).

    Cada despertar cuesta (actividad + sleepAfter). Supuestos explicitos:
      - personal: 4 rafagas/dia de 45 min de trabajo, 26 dias habiles;
      - sitio/bots: 10 despertares/dia de 2 min fuera de esas rafagas, 30 dias.
    Si las visitas no cacheadas llegan con menos separacion que sleepAfter, el contenedor
    ya no duerme y el caso converge a 24/7.
    """
    staff = bursts_staff * (min_staff + sleep_min) / 60 * dias_staff
    web = despertares_web * (min_web + sleep_min) / 60 * dias_web
    return staff + web


def horas_por_cron(intervalo_min: float, sleep_min: float, arranque_min: float = 1.0,
                   trabajo_min: float = 1.0) -> float:
    """Horas activas al mes causadas SOLO por un cron que hace fetch al contenedor.

    Una peticion entrante reinicia el temporizador sleepAfter
    (https://developers.cloudflare.com/containers/api/container-class/#renewactivitytimeout).
    Si intervalo <= sleepAfter, el contenedor nunca duerme: 720 h.
    Si no, cada disparo lo mantiene despierto arranque + trabajo + sleepAfter.
    """
    if intervalo_min <= sleep_min:
        return 720.0
    por_disparo = min(intervalo_min, arranque_min + trabajo_min + sleep_min)
    disparos = 30 * 24 * 60 / intervalo_min
    return disparos * por_disparo / 60


def costo(tipo: str, horas: float, uso: float) -> dict:
    vcpu, gib, gb = TIPOS[tipo]
    s = horas * 3600
    mem = max(0.0, gib * s - MEM_INCL_GIBS) * P_MEM
    cpu = max(0.0, vcpu * uso * s - CPU_INCL_VCPUS) * P_CPU
    disk = max(0.0, gb * s - DISK_INCL_GBS) * P_DISK
    # Durable Object del contenedor: peor caso, activo todo el tiempo que corre el contenedor.
    do_gbs = DO_GB * s
    do = 0.0 if do_gbs <= DO_INCL_GBS else -(-(do_gbs - DO_INCL_GBS) // 1_000_000) * 12.50
    total = mem + cpu + disk + do
    return {"mem": mem, "cpu": cpu, "disk": disk, "do": do, "cont": total, "total": total + PLAN}


def fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    patrones = [
        ("24/7 (720 h; hoy, por el cron */10)", 720.0),
        ("Horario comercial 12 h x 26 d (312 h)", 312.0),
        ("A demanda, sleepAfter 10 min", horas_a_demanda(10)),
        ("A demanda, sleepAfter 15 min", horas_a_demanda(15)),
        ("A demanda, sleepAfter 30 min", horas_a_demanda(30)),
    ]
    print("## Horas activas supuestas\n")
    for nombre, h in patrones:
        print(f"- {nombre}: {fmt(h)} h/mes")

    print("\n## Costo mensual en USD (contenedor + DO + $5 del plan)\n")
    print("| Patron | Horas | Tipo | CPU 3 % | CPU 10 % | CPU 25 % | de ello memoria | disco |")
    print("|---|---|---|---|---|---|---|---|")
    for nombre, h in patrones:
        for tipo in TIPOS:
            cs = [costo(tipo, h, u) for u in USOS]
            print(f"| {nombre} | {fmt(h)} | {tipo} | {fmt(cs[0]['total'])} | {fmt(cs[1]['total'])} | "
                  f"{fmt(cs[2]['total'])} | {fmt(cs[0]['mem'])} | {fmt(cs[0]['disk'])} |")

    print("\n## Desglose 24/7 standard-2 (configuracion actual de edge/wrangler.jsonc)\n")
    for u in USOS:
        c = costo("standard-2", 720, u)
        print(f"- CPU {int(u*100)} %: memoria {fmt(c['mem'])} + CPU {fmt(c['cpu'])} + disco {fmt(c['disk'])} "
              f"+ DO {fmt(c['do'])} = {fmt(c['cont'])} -> con plan {fmt(c['total'])}")

    print("\n## Horas que un cron mantiene despierto el contenedor (sin contar trafico)\n")
    print("| Intervalo del cron | sleepAfter 10 min | 15 min | 30 min |")
    print("|---|---|---|---|")
    for intervalo in (10, 30, 60, 180, 360, 1440):
        fila = [fmt(horas_por_cron(intervalo, s)) for s in (10, 15, 30)]
        print(f"| cada {intervalo} min | " + " | ".join(fila) + " |")

    print("\n## Costo del cron solo (standard-2, CPU 10 %, sin trafico), USD/mes con plan\n")
    for intervalo, s in ((10, 30), (60, 10), (360, 10), (1440, 10)):
        h = horas_por_cron(intervalo, s)
        print(f"- cron cada {intervalo} min, sleepAfter {s} min: {fmt(h)} h -> "
              f"{fmt(costo('standard-2', h, 0.10)['total'])}")

    print("\n## Punto en que se agota lo incluido (horas/mes)\n")
    for tipo, (vcpu, gib, gb) in TIPOS.items():
        h_mem = MEM_INCL_GIBS / (gib * 3600)
        h_disk = DISK_INCL_GBS / (gb * 3600)
        h_cpu = {u: CPU_INCL_VCPUS / (vcpu * u * 3600) for u in USOS}
        print(f"- {tipo}: memoria {fmt(h_mem)} h, disco {fmt(h_disk)} h, CPU "
              + ", ".join(f"{int(u*100)} % -> {fmt(x)} h" for u, x in h_cpu.items()))


if __name__ == "__main__":
    main()
