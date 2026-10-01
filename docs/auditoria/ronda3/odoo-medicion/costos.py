#!/usr/bin/env python3
"""Costo mensual de Odoo en Cloudflare Containers con las cifras MEDIDAS de esta ronda.

Fórmulas oficiales (https://developers.cloudflare.com/containers/platform/pricing/,
Last updated 2026-08-28; changelog 2025-11-21 «New CPU Pricing»):
  - memoria y disco: por lo APROVISIONADO del tipo de instancia, mientras la instancia está activa
  - CPU: solo por USO ACTIVO (vCPU-s consumidos)
  - incluidos en Workers Paid ($5/mes): 25 GiB-h memoria, 375 vCPU-min, 200 GB-h disco
  - excedente: $0.0000025/GiB-s, $0.000020/vCPU-s, $0.00000007/GB-s
Tipos (https://developers.cloudflare.com/containers/platform/limits/, Last updated 2026-09-30).
No incluye egress ni Workers/R2/BD externa: solo la instancia de Odoo.

Entradas medidas (docs/auditoria/ronda3/odoo-medicion.md):
  CPU_REPOSO_S_POR_H: CPU que gasta Odoo sin tráfico (cron, bus) por hora activa.
  CPU_MS_POR_PETICION: mezcla medida bajo carga (/, /shop, ficha, /visitanos, /web/login,
                       /socios, 2 RPC del backend) en la máquina de medición.
El volumen de peticiones NO es un dato del negocio: son escenarios (no inventamos tráfico).
"""
import json
import sys

PRECIO_MEM = 0.0000025      # $/GiB-s
PRECIO_CPU = 0.000020       # $/vCPU-s
PRECIO_DISCO = 0.00000007   # $/GB-s
INCL_MEM_GIBH = 25
INCL_CPU_MIN = 375
INCL_DISCO_GBH = 200
WORKERS_PAID = 5.0

TIPOS = {  # vCPU, GiB, GB
    'lite': (1 / 16, 0.25, 2),
    'basic': (0.25, 1, 4),
    'standard-1': (0.5, 4, 8),
    'standard-2': (1, 6, 12),
}

# Escenarios de horas activas al mes
HORARIOS = {
    '24/7': 730,
    'horario comercial 12 h x 26 d': 12 * 26,
    'a demanda ~4 h/dia x 30 d': 4 * 30,
}
# Peticiones dinámicas que llegan a Odoo por día (lo que el caché del borde no absorbe)
VOLUMENES = {'bajo 1 000/d': 1000, 'medio 5 000/d': 5000, 'alto 20 000/d': 20000}


def costo(tipo, horas, peticiones_dia, cpu_ms_pet, cpu_reposo_s_h, dias=30):
    vcpu, gib, gb = TIPOS[tipo]
    mem_gibh = gib * horas
    disco_gbh = gb * horas
    cpu_s = cpu_reposo_s_h * horas + peticiones_dia * dias * cpu_ms_pet / 1000
    # La CPU activa no puede exceder la aprovisionada
    cpu_s = min(cpu_s, vcpu * horas * 3600)
    exc_mem = max(0, mem_gibh - INCL_MEM_GIBH) * 3600 * PRECIO_MEM
    exc_disco = max(0, disco_gbh - INCL_DISCO_GBH) * 3600 * PRECIO_DISCO
    exc_cpu = max(0, cpu_s - INCL_CPU_MIN * 60) * PRECIO_CPU
    return {
        'mem_GiBh': round(mem_gibh), 'disco_GBh': round(disco_gbh), 'cpu_vCPU_min': round(cpu_s / 60),
        'exc_mem': round(exc_mem, 2), 'exc_disco': round(exc_disco, 2), 'exc_cpu': round(exc_cpu, 2),
        'total_sin_plan': round(exc_mem + exc_disco + exc_cpu, 2),
        'total_con_plan': round(WORKERS_PAID + exc_mem + exc_disco + exc_cpu, 2),
        'uso_cpu_medio_%': round(100 * cpu_s / (vcpu * horas * 3600), 1),
    }


if __name__ == '__main__':
    cpu_ms = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
    reposo = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    print(f'CPU por petición = {cpu_ms} ms · CPU en reposo = {reposo} s por hora activa')
    print(f"{'tipo':11s} {'horario':32s} {'volumen':14s} {'GiB-h':>6s} {'vCPU-min':>8s} "
          f"{'mem$':>6s} {'cpu$':>6s} {'disco$':>6s} {'+plan $5':>8s} {'%CPU':>5s}")
    filas = []
    for tipo in ('basic', 'standard-1'):
        for h_nombre, horas in HORARIOS.items():
            for v_nombre, vol in VOLUMENES.items():
                c = costo(tipo, horas, vol, cpu_ms, reposo)
                filas.append({'tipo': tipo, 'horario': h_nombre, 'volumen': v_nombre, **c})
                print(f"{tipo:11s} {h_nombre:32s} {v_nombre:14s} {c['mem_GiBh']:6d} {c['cpu_vCPU_min']:8d} "
                      f"{c['exc_mem']:6.2f} {c['exc_cpu']:6.2f} {c['exc_disco']:6.2f} {c['total_con_plan']:8.2f} "
                      f"{c['uso_cpu_medio_%']:5.1f}")
    json.dump(filas, open(__file__.replace('costos.py', 'res_costos.json'), 'w'), indent=1)
