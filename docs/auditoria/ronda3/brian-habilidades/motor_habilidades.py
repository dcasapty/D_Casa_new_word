"""Prototipo del motor de habilidades de Brian (ronda 3, r3-brian-habilidades).

Hace tres cosas, sin red ni base de datos:
  (a) resuelve qué paquetes y herramientas VE cada usuario según sus grupos de Odoo y su perfil;
  (b) corre los casos de permisos de casos_permisos.yaml y reporta aprobado/fallado;
  (c) MIDE el ahorro de tokens de cargar herramientas bajo demanda frente a mandar todas de golpe,
      con las descripciones y esquemas REALES extraídos de addons/dcasa_brian (extraer_herramientas.py).

Uso:  python3 motor_habilidades.py            (todo)
      python3 motor_habilidades.py --json     (además vuelca resultados.json)
Requiere PyYAML (ya presente en el entorno de Odoo).
"""
import json
import statistics
import sys
from pathlib import Path

import extraer_herramientas as ex
import yaml

AQUI = Path(__file__).resolve().parent

# Factores explícitos caracteres → tokens (los mismos supuestos de la ronda 2, brian-evals §2.2):
#   3.3 car/token: español + JSON con el tokenizador clásico; 2.5: tokenizador nuevo (+30 %).
FACTORES = {'base (car/3.3)': 3.3, 'tokenizador nuevo (car/2.5)': 2.5}
# Precio de entrada de Claude Sonnet 5.5 (modelo por defecto de Brian): US$ 2 por millón de tokens
# (skill claude-api, tabla de modelos «cached 2026-09-25»). Lectura de caché: US$ 0.20.
PRECIO_ENTRADA_MTOK = 2.0
# Prompt de sistema actual: 1 222 caracteres medidos en la ronda 2 (conversacion.py:357-385).
CHARS_SISTEMA = 1222
ESCALA = {'lectura': 1, 'construccion': 2, 'sensible': 3}

# Esquema real (redactado aquí) de la meta-herramienta nueva; se mide igual que las demás.
ESQUEMA_CARGAR = {
    'name': 'cargar_habilidad',
    'description': ('Carga las instrucciones y herramientas de un paquete del índice de habilidades. '
                    'Úsala antes de trabajar en un tema cuyo paquete no está cargado.'),
    'input_schema': {'type': 'object', 'properties': {'paquete': {
        'type': 'string', 'description': 'Id del paquete, p. ej. «ventas».', 'enum': []}},
        'required': ['paquete'], 'additionalProperties': False},
}


# ----------------------------------------------------------------------------------------------
# Carga y armado del catálogo
# ----------------------------------------------------------------------------------------------

def cargar():
    catalogo = yaml.safe_load((AQUI / 'catalogo_habilidades.yaml').read_text(encoding='utf-8'))
    perfiles = yaml.safe_load((AQUI / 'perfiles_por_rol.yaml').read_text(encoding='utf-8'))
    casos = yaml.safe_load((AQUI / 'casos_permisos.yaml').read_text(encoding='utf-8'))
    reales = {h['nombre']: h for h in ex.herramientas()}
    return catalogo, perfiles, casos, reales


def armar_indice(catalogo, reales):
    """{nombre: herramienta} con metadatos del YAML + grupos/nivel REALES cuando existe en el código."""
    indice, avisos = {}, []
    for paquete in catalogo['paquetes']:
        for h in paquete['herramientas']:
            h = dict(h, paquete=paquete['id'])
            real = reales.get(h['nombre'])
            if h['estado'] in ('existe', 'cambiar'):
                if not real:
                    avisos.append(f"{h['nombre']}: marcada «{h['estado']}» pero no existe en el código")
                    continue
                h['grupos_reales'] = real['grupos']
                h['nivel_real'] = real['nivel']
                h['chars_esquema'] = real['chars_esquema_json']
                h.setdefault('grupos', real['grupos'])
                if ESCALA[real['nivel']] != h['nivel_min']:
                    avisos.append(f"{h['nombre']}: nivel real «{real['nivel']}» (→{ESCALA[real['nivel']]}) "
                                  f"y propuesto {h['nivel_min']}")
                if sorted(h['grupos']) != sorted(real['grupos']):
                    avisos.append(f"{h['nombre']}: grupos reales {real['grupos'] or '(ninguno)'} → propuestos {h['grupos']}")
            else:
                h.setdefault('grupos', [])
            if h['nombre'] in indice:
                avisos.append(f"{h['nombre']}: duplicada en dos paquetes")
            indice[h['nombre']] = h
    faltan = sorted(set(reales) - set(indice))
    for nombre in faltan:
        avisos.append(f'{nombre}: existe en el código y no está en ningún paquete')
    return indice, avisos


def cierre_grupos(grupos, perfiles):
    impl = {k: set(v) for k, v in perfiles['implicaciones_odoo'].items()}
    for rol in perfiles['roles_odoo_propuestos'].values():
        if str(rol['xmlid']).startswith('dcasa_base.'):
            impl[rol['xmlid']] = set(rol['implica'])
    vistos, pila = set(), list(grupos)
    while pila:
        g = pila.pop()
        if g in vistos:
            continue
        vistos.add(g)
        pila.extend(impl.get(g, ()))
    return vistos


def resolver_perfil(grupos_cerrados, perfiles, directo=None):
    lista = {p['id']: p for p in perfiles['perfiles']}
    if directo:
        return lista[directo]
    candidatos = [p for p in perfiles['perfiles'] if set(p['grupos']) & grupos_cerrados]
    if not candidatos:
        return lista['predeterminado']
    return max(candidatos, key=lambda p: p['prioridad'])


# ----------------------------------------------------------------------------------------------
# (a) Visibilidad
# ----------------------------------------------------------------------------------------------

def motivo_no_visible(h, grupos, perfil, canal):
    if canal not in perfil['canales']:
        return 'canal'
    if not set(h['grupos']) <= grupos:
        return 'odoo'
    if h['nombre'] in perfil.get('excluir', ()):
        return 'excluida'
    if h['nivel_min'] >= 5 and not perfil.get('modo_constructor'):
        return 'nivel'
    if perfil['niveles'].get(h['paquete'], 0) < h['nivel_min']:
        return 'nivel'
    return None


def visibles(indice, grupos, perfil, canal):
    return {n: h for n, h in indice.items() if motivo_no_visible(h, grupos, perfil, canal) is None}


# ----------------------------------------------------------------------------------------------
# Decisión de ejecución (lo que haría brian.herramientas.ejecutar con perfiles)
# ----------------------------------------------------------------------------------------------

def politica_dura(args):
    """Reutiliza las listas REALES de politica.py (cargadas por extraer_herramientas)."""
    pol = sys.modules['odoo.addons.dcasa_brian.models.politica']
    norm = sys.modules['odoo.addons.dcasa_brian.models.registro'].normalizar

    def recorrer(v):
        if isinstance(v, dict):
            for k, s in v.items():
                if any(x in norm(str(k)) for x in pol.SECRETOS):
                    return True
                if k in ('modelo', 'model') and s in pol.MODELOS_TECNICOS:
                    return True
                if recorrer(s):
                    return True
        elif isinstance(v, (list, tuple)):
            return any(recorrer(s) for s in v)
        elif isinstance(v, str):
            return any(t in norm(v) for t in pol.TEXTOS_PROHIBIDOS)
        return False
    return recorrer(args)


def decidir(h, args, ctx, grupos, perfil, canal, perfiles):
    if h is None:
        return 'bloquear', 'no_existe'
    if politica_dura(args):
        return 'bloquear', 'politica'
    motivo = motivo_no_visible(h, grupos, perfil, canal)
    if motivo:
        return 'bloquear', motivo
    for arg, permitidos in perfil.get('restricciones_argumentos', {}).get(h['nombre'], {}).items():
        if arg in args and args[arg] not in permitidos:
            return 'bloquear', 'restriccion'
    topes = perfil['topes']
    if h.get('descuento') and h['descuento'] in args:
        valor = args[h['descuento']]
        lista = ctx.get('precio_lista')
        pct = valor if h['descuento'] == 'porcentaje' else (
            (lista - valor) / lista * 100 if lista else 0)
        if pct > topes['descuento_max_pct'] + 1e-9:
            otros = [p for p in perfiles['perfiles'] if p['topes']['descuento_max_pct'] >= pct
                     and p['id'] not in ('predeterminado', perfil['id'])]
            return ('escalar', 'tope_descuento') if otros else ('bloquear', 'tope_descuento')
    contaminado = bool(ctx.get('contaminado'))
    monto = ctx.get('total', args.get(h.get('monto'))) if h.get('monto') else 0
    if h['confirmacion'] == 'siempre':
        decision, motivo = 'confirmar', 'siempre'
    elif h['confirmacion'] == 'segun_perfil':
        nivel = perfil['niveles'].get(h['paquete'], 0)
        if contaminado:
            decision, motivo = 'confirmar', 'contaminado'
        elif nivel < 4:
            decision, motivo = 'confirmar', 'nivel_3'
        elif canal not in perfil.get('autonomia_en', ()):
            decision, motivo = 'confirmar', 'autonomia_canal'
        elif h['reversible'] == 'no':
            decision, motivo = 'confirmar', 'irreversible'
        elif (monto or 0) > topes['monto_autonomo_max']:
            decision, motivo = 'confirmar', 'sobre_tope'
        else:
            decision, motivo = 'permitir', 'autonomo'
    elif h.get('escribe') and contaminado:
        decision, motivo = 'confirmar', 'contaminado'
    else:
        decision, motivo = 'permitir', 'directo'
    if decision == 'confirmar' and canal == 'mcp':
        return 'confirmar_fuera_de_banda', motivo
    return decision, motivo


# ----------------------------------------------------------------------------------------------
# (c) Medición de tokens
# ----------------------------------------------------------------------------------------------

def chars_paquete_cuerpo(paquete, indice, nombres_visibles, media_real):
    """Instrucciones + esquemas de las herramientas visibles del paquete (reales; nuevas a la media real)."""
    reales = nuevas = 0
    for h in paquete['herramientas']:
        if h['nombre'] not in nombres_visibles:
            continue
        info = indice[h['nombre']]
        if 'chars_esquema' in info:
            reales += info['chars_esquema']
        else:
            nuevas += media_real
    return len(paquete['instrucciones']), reales, nuevas


def chars_indice(paquetes):
    lineas = [f"- {p['id']}: {p['descripcion']}" for p in paquetes]
    return len('Habilidades disponibles (carga con cargar_habilidad):\n' + '\n'.join(lineas))


def tokens(chars, factor):
    return chars / factor


def medir(catalogo, indice, reales, perfiles, casos):
    todas = sum(h['chars_esquema_json'] for h in reales.values())
    media_real = statistics.mean(h['chars_esquema_json'] for h in reales.values())
    cargar = len(json.dumps(ESQUEMA_CARGAR, ensure_ascii=False, separators=(',', ':')))
    paquetes = {p['id']: p for p in catalogo['paquetes']}
    usuarios = casos['usuarios']
    escenarios = [
        ('vendedora: «cotízale un sofá gris a Juan»', 'ana_vendedora', ['ventas']),
        ('vendedora: «¿quién me debe?»', 'ana_vendedora', ['cobros_facturas']),
        ('gerencia: «sube 5 % los colchones Queen»', 'gaby_gerencia', ['catalogo_precios']),
        ('admin: «hagamos el cierre de septiembre»', 'dueno_admin', ['contabilidad', 'cobros_facturas']),
        ('admin: «crea el usuario de la nueva vendedora»', 'dueno_admin', ['equipo']),
        ('admin: peor caso, carga TODOS sus paquetes', 'dueno_admin', None),
    ]
    filas = []
    for titulo, usuario, cargados in escenarios:
        grupos = cierre_grupos(usuarios[usuario]['grupos'], perfiles)
        perfil = resolver_perfil(grupos, perfiles)
        vis = visibles(indice, grupos, perfil, 'chat')
        paq_vis = [p for p in catalogo['paquetes'] if any(h['nombre'] in vis for h in p['herramientas'])]
        if cargados is None:
            cargados = [p['id'] for p in paq_vis if not p.get('siempre_cargado')]
        # Hoy: el modelo grande recibe todo lo que los grupos de Odoo del usuario permiten (registro.py:111,133).
        hoy = sum(h['chars_esquema_json'] for h in reales.values() if set(h['grupos']) <= grupos)
        nucleo_real = sum(indice[h['nombre']].get('chars_esquema', 0)
                          for h in paquetes['nucleo']['herramientas'] if h['nombre'] in vis)
        fijo = nucleo_real + cargar + chars_indice([p for p in paq_vis if not p.get('siempre_cargado')])
        instr = real = nuevas = 0
        for pid in cargados:
            i, r, n = chars_paquete_cuerpo(paquetes[pid], indice, vis, media_real)
            instr, real, nuevas = instr + i, real + r, nuevas + n
        filas.append({'escenario': titulo, 'perfil': perfil['id'], 'paquetes': cargados,
                      'hoy_todas_45': todas, 'hoy_filtrado_odoo': hoy,
                      'bajo_demanda_fijo': fijo, 'bajo_demanda_cargado_real': instr + real,
                      'bajo_demanda_cargado_nuevas_estimadas': nuevas})
    return {'chars_45': todas, 'media_real': media_real, 'chars_cargar_habilidad': cargar, 'filas': filas}


# ----------------------------------------------------------------------------------------------
# Salida
# ----------------------------------------------------------------------------------------------

def main():
    catalogo, perfiles, casos, reales = cargar()
    indice, avisos = armar_indice(catalogo, reales)
    salida = {}
    print('=' * 100)
    print('MOTOR DE HABILIDADES DE BRIAN — prototipo r3-brian-habilidades')
    print('=' * 100)
    n_paq = len(catalogo['paquetes'])
    estados = {}
    for h in indice.values():
        estados[h['estado']] = estados.get(h['estado'], 0) + 1
    print(f'Herramientas reales extraídas del código: {len(reales)} · paquetes: {n_paq} · '
          f'herramientas en el catálogo objetivo: {len(indice)} ({estados})')
    print('\nDiferencias código → catálogo propuesto:')
    for a in avisos:
        print('  -', a)

    # (a) visibilidad por usuario y canal
    print('\n(a) QUÉ VE CADA PERSONA (canal chat)')
    print(f"{'usuario':18} {'perfil':15} {'paquetes visibles':>17} {'herram.':>8}  paquetes")
    salida['visibilidad'] = {}
    for usuario, datos in casos['usuarios'].items():
        grupos = cierre_grupos(datos['grupos'], perfiles)
        perfil = resolver_perfil(grupos, perfiles)
        vis = visibles(indice, grupos, perfil, 'chat')
        paq = sorted({h['paquete'] for h in vis.values()})
        salida['visibilidad'][usuario] = {'perfil': perfil['id'], 'herramientas': sorted(vis)}
        print(f"{usuario:18} {perfil['id']:15} {len(paq):>17} {len(vis):>8}  {', '.join(paq)}")
    for usuario in ('ana_vendedora', 'dueno_admin'):
        grupos = cierre_grupos(casos['usuarios'][usuario]['grupos'], perfiles)
        perfil = resolver_perfil(grupos, perfiles)
        vis = visibles(indice, grupos, perfil, 'chat')
        print(f'\n  Detalle {usuario} ({perfil["id"]}):')
        por = {}
        for n, h in sorted(vis.items()):
            por.setdefault(h['paquete'], []).append(n)
        for p, ns in por.items():
            print(f'    {p:17} nivel {perfil["niveles"].get(p, 0)}: {", ".join(ns)}')

    # (b) casos de permisos
    print('\n(b) CASOS DE PERMISOS')
    print(f"{'id':4} {'usuario':16} {'canal':8} {'herramienta':24} {'esperado':26} {'obtenido':26} res")
    aprobados = 0
    salida['casos'] = []
    for caso in casos['casos']:
        grupos = cierre_grupos(casos['usuarios'][caso['usuario']]['grupos'], perfiles)
        perfil = resolver_perfil(grupos, perfiles)
        decision, motivo = decidir(indice.get(caso['herramienta']), caso.get('args', {}), caso.get('contexto', {}),
                                   grupos, perfil, caso['canal'], perfiles)
        ok = decision == caso['esperado'] and (not caso.get('motivo') or caso['motivo'] == motivo)
        aprobados += ok
        esperado = caso['esperado'] + (f"/{caso['motivo']}" if caso.get('motivo') else '')
        print(f"{caso['id']:4} {caso['usuario']:16} {caso['canal']:8} {caso['herramienta']:24} "
              f"{esperado:26} {decision + '/' + motivo:26} {'APROBADO' if ok else 'FALLADO'}")
        salida['casos'].append({**caso, 'obtenido': decision, 'motivo_obtenido': motivo, 'ok': ok})
    print(f'Resultado: {aprobados}/{len(casos["casos"])} aprobados')

    # (c) tokens
    m = medir(catalogo, indice, reales, perfiles, casos)
    salida['tokens'] = m
    print('\n(c) TOKENS DE DEFINICIONES DE HERRAMIENTAS POR LLAMADA (caracteres reales → tokens)')
    print(f"Catálogo actual completo: {m['chars_45']} car. (45 esquemas reales, JSON compacto); "
          f"media {m['media_real']:.0f} car./herramienta; cargar_habilidad: {m['chars_cargar_habilidad']} car.")
    print('Las herramientas NUEVAS no tienen esquema todavía: se cuentan aparte a la media real.')
    for etiqueta, factor in FACTORES.items():
        print(f'\n  Factor {etiqueta}  ·  costo de entrada Sonnet 5.5 US$ {PRECIO_ENTRADA_MTOK}/M sin caché')
        print(f"  {'escenario':48} {'hoy 45':>7} {'hoy rol':>8} {'demanda':>8} {'ahorro':>7} {'+nuevas':>8} {'turno hoy':>10} {'turno dem.':>10}")
        for f in m['filas']:
            hoy45 = tokens(f['hoy_todas_45'], factor)
            hoy_rol = tokens(f['hoy_filtrado_odoo'], factor)
            dem = tokens(f['bajo_demanda_fijo'] + f['bajo_demanda_cargado_real'], factor)
            fijo = tokens(f['bajo_demanda_fijo'], factor)
            nuevas = tokens(f['bajo_demanda_cargado_nuevas_estimadas'], factor)
            # Turno de 2 llamadas (herramienta + respuesta). Bajo demanda la 1.ª vez del tema suma una
            # llamada (cargar_habilidad) con solo el prefijo fijo. Sistema incluido en ambos; historial
            # y resultados son iguales en los dos y no se cuentan.
            sis = tokens(CHARS_SISTEMA, factor)
            turno_hoy = 2 * (hoy_rol + sis)
            turno_dem = (fijo + sis) + 2 * (dem + sis)
            ahorro = 1 - dem / hoy_rol if hoy_rol else 0
            print(f"  {f['escenario'][:48]:48} {hoy45:7.0f} {hoy_rol:8.0f} {dem:8.0f} {ahorro:7.0%} "
                  f"{nuevas:8.0f} {turno_hoy:10.0f} {turno_dem:10.0f}")
        f = m['filas'][0]
        dem = tokens(f['bajo_demanda_fijo'] + f['bajo_demanda_cargado_real'], factor)
        hoy = tokens(f['hoy_todas_45'], factor)
        print(f"  US$ por llamada, solo definiciones (fila 1): hoy-45 {hoy * PRECIO_ENTRADA_MTOK / 1e6:.4f} · "
              f"bajo demanda {dem * PRECIO_ENTRADA_MTOK / 1e6:.4f}")
    if '--json' in sys.argv:
        (AQUI / 'resultados.json').write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str),
                                              encoding='utf-8')
    return 0 if aprobados == len(casos['casos']) else 1


if __name__ == '__main__':
    sys.exit(main())
