"""Costo por interacción y por mes de Brian (supuestos explícitos; precios de data/precios.json).

Interacción típica = 1 mensaje de la persona que usa 1 herramienta = 2 llamadas al modelo.
Uso: python3 costos/calcular.py   (sin dependencias)
"""
import json
import pathlib

PRECIOS = json.loads((pathlib.Path(__file__).parent.parent / "data" / "precios.json").read_text())["modelos"]

# --- Supuestos (tokens) ------------------------------------------------------
P = 3500      # prefijo estable: sistema + herramientas del perfil (r3-brian-habilidades: 2 100-3 900 de herramientas + ~1 300 núcleo)
H1 = 1500     # contexto + historial reciente en la llamada 1
RES = 800     # resultado de herramienta que entra en la llamada 2
S1, S2 = 400, 300   # salida por llamada (incluye razonamiento a esfuerzo bajo)
# Probabilidad de que el prefijo esté «tibio» en la PRIMERA llamada de un turno (TTL 5 min; tráfico en ~10 h hábiles)
TIBIO = {50: 0.3, 300: 0.7, 1500: 0.9}
MIN_CACHE = {"anthropic/claude-haiku-4-5": 4096, "anthropic/claude-sonnet-5-5": 512, "anthropic/claude-opus-5-5": 512}


def costo_llamada(modelo, entrada_total, prefijo_cacheable, tibio, salida):
    p = PRECIOS[modelo]
    usa_cache = prefijo_cacheable >= MIN_CACHE.get(modelo, 0)
    if not usa_cache:
        return (entrada_total * p["entrada"] + salida * p["salida"]) / 1e6
    resto = entrada_total - prefijo_cacheable
    lectura = tibio * prefijo_cacheable * p["cache_lectura"]
    escritura = (1 - tibio) * prefijo_cacheable * p["cache_escritura"]
    return (lectura + escritura + resto * p["entrada"] + salida * p["salida"]) / 1e6


def interaccion(modelo, tibio, cache=True):
    e1, e2 = P + H1, P + H1 + S1 + RES
    if not cache:
        return costo_llamada(modelo, e1, 0, 0, S1) + costo_llamada(modelo, e2, 0, 0, S2)
    if modelo.startswith("meta/"):
        # Caché automática por prefijo: llamada 2 reutiliza P+H1 (misma conversación, segundos después).
        return costo_llamada(modelo, e1, P, tibio, S1) + costo_llamada(modelo, e2, P + H1, 1.0, S2)
    # Claude con breakpoints en system y última herramienta (prototipo): solo P es cacheable.
    return costo_llamada(modelo, e1, P, tibio, S1) + costo_llamada(modelo, e2, P, 1.0, S2)


MODELOS = ["meta/muse-spark-1.3", "anthropic/claude-haiku-4-5", "anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5"]
print(f"Supuestos: P={P} H1={H1} RES={RES} salida={S1}+{S2} tokens; 30 días/mes\n")
print(f"{'modelo':32} {'estado':14} {'sin caché':>10} " + " ".join(f"{v:>6}/día" for v in TIBIO) + "   (USD por interacción, con caché)")
for m in MODELOS:
    fila = [f"{interaccion(m, TIBIO[v]):.5f}" for v in TIBIO]
    print(f"{m:32} {PRECIOS[m]['estado']:14} {interaccion(m, 0, cache=False):10.5f} " + " ".join(f"{x:>10}" for x in fila))

print("\nUSD por MES (con caché)")
mezcla = {"meta/muse-spark-1.3": 0.8, "anthropic/claude-sonnet-5-5": 0.2}
filas = MODELOS + ["mezcla 80 % Meta + 20 % Sonnet"]
print(f"{'ruta':32} " + " ".join(f"{v:>9}/día" for v in TIBIO))
for m in filas:
    vals = []
    for v, t in TIBIO.items():
        c = sum(w * interaccion(k, t) for k, w in mezcla.items()) if m.startswith("mezcla") else interaccion(m, t)
        vals.append(c * v * 30)
    print(f"{m:32} " + " ".join(f"{x:13.2f}" for x in vals))
