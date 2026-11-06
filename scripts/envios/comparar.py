"""Compara el motor de envíos de Python (addons/dcasa_envios/motor) con lo que da el JavaScript del HTML.

Uso (los esperados salen de ``node scripts/envios/paridad.mjs``):

    python scripts/envios/comparar.py <envios-dcasa.html | datos.json> <consultas.json> <esperados.json>

Imprime, por búsqueda, si los primeros 10 lugares, el total y las sugerencias coinciden, y si cada tarjeta (chips,
zona, precio, desglose, ruta y texto para el cliente) dice lo mismo; luego los precios, los tramos y los textos de la
regla. Termina con el porcentaje que coincide. No escribe nada.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'addons' / 'dcasa_envios'))

from motor import buscador, tarifa, tarjeta  # noqa: E402
from motor.texto import dinero, km_txt  # noqa: E402


def leer_datos(ruta):
    texto = Path(ruta).read_text(encoding='utf-8')
    if ruta.endswith('.json'):
        datos = json.loads(texto)
        return datos['lugares'], datos['ajustes'], datos.get('agregados') or []

    def bloque(ident):
        m = re.search(rf'<script id="{ident}" type="application/json">(.*?)</script>', texto, re.S)
        return json.loads(m.group(1))
    return bloque('lugares'), bloque('ajustes'), bloque('agregados-datos')


def tarjeta_como_el_html(datos):
    """La tarjeta del motor con la misma forma que saca paridad.mjs del HTML."""
    clases = {'tipo': 'cat', 'revisar': 'revisar', 'aparte': 'aparte', 'mano': 'google'}
    salida = {
        'chips': [[clases[c['clase']], c['texto']] for c in datos['chips']],
        'zona': datos['zona'],
        'tambien': [t for t in (datos['tambien'], datos['nota']) if t],
        'url': datos['url_mapa'],
    }
    if datos['con_precio']:
        salida.update({'total': datos['total_txt'], 'km': datos['km_txt'] + (' · Google' if datos['google'] else ''),
                       'desglose': [f"{d['texto']} {d['monto']}" for d in datos['desglose']],
                       'copiar': datos['texto_cliente']})
    else:
        salida.update({'total': 'Cotizar aparte', 'km': datos['km_txt'] or None, 'desglose': [], 'copiar': None})
    return salida


class Comparacion:
    def __init__(self, ruta_datos, ruta_consultas, ruta_esperados):
        lugares, self.ajustes, agregados = leer_datos(ruta_datos)
        self.todos = list(lugares) + [{**lugar, 'agregado': True} for lugar in agregados]
        consultas = json.loads(Path(ruta_consultas).read_text(encoding='utf-8'))
        self.esperados = json.loads(Path(ruta_esperados).read_text(encoding='utf-8'))
        self.variantes = {v['nombre']: v.get('cambios') or {} for v in consultas['variantes']}
        self.indice = buscador.Indice(self.todos)
        self.tarifa = tarifa.Tarifa(self.ajustes)
        self.cuentas = {'busquedas': [0, 0], 'tarjetas': [0, 0], 'precios': [0, 0], 'tramos': [0, 0],
                        'textos': [0, 0]}
        self.diferencias = []

    def contar(self, que, igual, diferencia):
        self.cuentas[que][0] += bool(igual)
        self.cuentas[que][1] += 1
        if not igual:
            self.diferencias.append(diferencia())

    def con_variante(self, nombre):
        return tarifa.Tarifa({**json.loads(json.dumps(self.ajustes)), **self.variantes[nombre]})

    def constantes(self):
        constantes = self.esperados['constantes']
        for nombre in ('ABREV', 'CAT_SIN', 'DIST_SIN', 'PROV_SIN', 'PRIORIDAD'):
            if constantes[nombre] != getattr(buscador, nombre):
                self.diferencias.append(f'Constante distinta: {nombre}')
        for nombre in ('VACIAS', 'GENERICAS'):
            if constantes[nombre] != sorted(getattr(buscador, nombre)):
                self.diferencias.append(f'Constante distinta: {nombre}')

    def busquedas(self):
        for esperado in self.esperados['busquedas']:
            posiciones = self.indice.buscar(esperado['texto'], esperado.get('tipo'), esperado.get('distrito'))
            sugerencias = [] if posiciones else self.indice.sugerir(esperado['texto'])
            top = posiciones[:10]
            igual = (not esperado.get('error') and top == esperado['top'] and len(posiciones) == esperado['total']
                     and sugerencias == esperado['sugerencias'])
            self.contar('busquedas', igual, lambda e=esperado, p=posiciones, s=sugerencias: (
                f"Búsqueda {e['texto']!r} (tipo={e.get('tipo')}, distrito={e.get('distrito')}): JS {e['total']} "
                f"{e['top']} sug {e['sugerencias']} error={e.get('error')} · Python {len(p)} {p[:10]} sug {s}"))
            for posicion, tarjeta_js in zip(top, esperado['tarjetas'], strict=False):
                mia = tarjeta_como_el_html(tarjeta.tarjeta(self.todos[posicion], self.tarifa))
                self.contar('tarjetas', mia == tarjeta_js, lambda p=posicion, j=tarjeta_js, m=mia: (
                    f"Tarjeta de {self.todos[p]['nombre']!r}: JS {j} · Python {m}"))

    def precios(self):
        for precio in self.esperados['precios']:
            c = self.con_variante(precio['variante']).cotizar(precio['km'], precio['peaje'])
            igual = (c['base'] == precio['base'] and c['total'] == precio['total'] and c['extras'] == precio['extras']
                     and dinero(c['total']) == precio['dinero'] and km_txt(precio['km']) == precio['km_txt'])
            self.contar('precios', igual, lambda p=precio, c=c: f'Precio {p} · Python {c}')

    def tramos_y_textos(self):
        for tramo in self.esperados['tramos']:
            tv = self.con_variante(tramo['variante'])
            mostrar = ''.join(f"{f['km_txt']}{f['precio_txt']}|" for f in tv.tramos_para_mostrar())
            igual = ((tramo['tramos'] is None or tv.tramos() == tramo['tramos']) and mostrar == tramo['mostrar']
                     and tv.nota_tramos() == tramo['nota'])
            self.contar('tramos', igual, lambda t=tramo, m=mostrar: (
                f"Tramos de {t['variante']}: JS {t['mostrar'][:200]} · Python {m[:200]}"))
        for texto in self.esperados['textos']:
            tv = self.con_variante(texto['variante'])
            regla = ''.join(f'{f[1]}|' for f in tv.regla())
            efecto = ''.join(f"{e['texto']}|" for e in tv.efecto())
            formula = tv.formula_txt()
            igual = regla == texto['regla'] and efecto == texto['efecto'] and formula == texto['formula']
            self.contar('textos', igual, lambda t=texto, r=regla, e=efecto, f=formula: (
                f'Textos de {t["variante"]}: JS {t} · Python {r} / {e} / {f}'))

    def informe(self):
        for linea in self.diferencias:
            print('✗', linea)
        for nombre, (bien, todas) in self.cuentas.items():
            print(f'{nombre}: {bien}/{todas} ({100 * bien / max(1, todas):.1f} %)')
        bien = sum(c[0] for c in self.cuentas.values())
        todas = sum(c[1] for c in self.cuentas.values())
        print(f'TOTAL: {bien}/{todas} ({100 * bien / max(1, todas):.1f} %)')
        return 0 if bien == todas and not self.diferencias else 1


def main(ruta_datos, ruta_consultas, ruta_esperados):
    comparacion = Comparacion(ruta_datos, ruta_consultas, ruta_esperados)
    comparacion.constantes()
    comparacion.busquedas()
    comparacion.precios()
    comparacion.tramos_y_textos()
    return comparacion.informe()


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
