"""Extrae el catálogo REAL de herramientas de Brian sin base de datos ni Odoo instalado.

Carga los archivos addons/dcasa_brian/models/herramientas_*.py con un `odoo` simulado
(solo lo que hace falta para que se definan las clases) y lee el atributo `_brian` que el
decorador `@herramienta` deja en cada método. Así las descripciones, parámetros, grupos y
niveles son exactamente los del código, incluidas las constantes compartidas.

Uso:  python3 extraer_herramientas.py  > herramientas_reales.json
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
ADDONS = RAIZ / 'addons'


def _modulo(nombre, paquete=False):
    m = types.ModuleType(nombre)
    if paquete:
        m.__path__ = []
    sys.modules[nombre] = m
    return m


def _stub_odoo():
    if 'odoo' in sys.modules and getattr(sys.modules['odoo'], '_stub_brian', False):
        return
    odoo = _modulo('odoo', paquete=True)
    odoo._stub_brian = True

    def identidad(*a, **k):
        if len(a) == 1 and callable(a[0]) and not k:
            return a[0]
        return lambda f: f

    api = _modulo('odoo.api')
    for n in ('model', 'depends', 'constrains', 'onchange', 'model_create_multi', 'private',
              'autovacuum', 'ondelete', 'depends_context', 'returns'):
        setattr(api, n, identidad)

    models = _modulo('odoo.models')

    class _Base:
        def __init_subclass__(cls, **kw):
            pass
    for n in ('AbstractModel', 'Model', 'TransientModel', 'BaseModel'):
        setattr(models, n, type(n, (_Base,), {}))
    models.Constraint = lambda *a, **k: None
    models.Index = lambda *a, **k: None

    fields = _modulo('odoo.fields')

    class _Campo:
        def __init__(self, *a, **k):
            pass

        @staticmethod
        def now():
            return None

        @staticmethod
        def today():
            return None
    for n in ('Char', 'Text', 'Html', 'Integer', 'Float', 'Monetary', 'Boolean', 'Date', 'Datetime',
              'Selection', 'Many2one', 'One2many', 'Many2many', 'Binary', 'Json', 'Image', 'Reference'):
        setattr(fields, n, _Campo)

    exc = _modulo('odoo.exceptions')
    for n in ('AccessError', 'UserError', 'ValidationError', 'MissingError', 'AccessDenied'):
        setattr(exc, n, type(n, (Exception,), {}))

    class Command:
        @staticmethod
        def link(*a): return a

        @staticmethod
        def set(*a): return a

        @staticmethod
        def create(*a): return a
    odoo.Command = Command
    odoo.api, odoo.models, odoo.fields, odoo.exceptions = api, models, fields, exc
    odoo._ = lambda s, *a, **k: s
    tools = _modulo('odoo.tools')
    tools.SQL = lambda *a, **k: None
    tools.ormcache = identidad
    odoo.tools = tools
    http = _modulo('odoo.http')
    http.request = None
    odoo.http = http
    _modulo('odoo.addons', paquete=True)


def _cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, archivo)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


def herramientas():
    """Lista de especificaciones reales (dicts) + el texto del esquema que viaja al modelo."""
    _stub_odoo()
    for paquete in ('odoo.addons.dcasa_socios', 'odoo.addons.dcasa_socios.models',
                    'odoo.addons.dcasa_brian', 'odoo.addons.dcasa_brian.models'):
        _modulo(paquete, paquete=True)
    socios = ADDONS / 'dcasa_socios' / 'models'
    _cargar('odoo.addons.dcasa_socios.models.reglas', socios / 'reglas.py')
    _cargar('odoo.addons.dcasa_socios.models.dcasa_movimiento', socios / 'dcasa_movimiento.py')
    sys.modules['odoo.addons.dcasa_socios.models'].reglas = sys.modules['odoo.addons.dcasa_socios.models.reglas']
    base = ADDONS / 'dcasa_brian' / 'models'
    pref = 'odoo.addons.dcasa_brian.models.'
    registro = _cargar(pref + 'registro', base / 'registro.py')
    _cargar(pref + 'politica', base / 'politica.py')
    pkg = sys.modules['odoo.addons.dcasa_brian.models']
    pkg.registro = registro
    pkg.herramientas_comun = _cargar(pref + 'herramientas_comun', base / 'herramientas_comun.py')
    salida = []
    for archivo in sorted(base.glob('herramientas_*.py')):
        if archivo.stem == 'herramientas_comun':
            continue
        mod = _cargar(pref + archivo.stem, archivo)
        for clase in vars(mod).values():
            if not isinstance(clase, type):
                continue
            for atributo, metodo in vars(clase).items():
                spec = getattr(metodo, '_brian', None)
                if not spec:
                    continue
                # Mismo esquema que registro.esquema(): es lo que se le manda al modelo.
                esquema = {
                    'name': spec['nombre'],
                    'description': spec['descripcion'] + (
                        ' Ejemplos: ' + '; '.join(spec['ejemplos']) if spec['ejemplos'] else ''),
                    'input_schema': {'type': 'object', 'properties': spec['parametros'],
                                     'required': spec['requeridos'], 'additionalProperties': False},
                }
                texto = json.dumps(esquema, ensure_ascii=False, separators=(',', ':'))
                salida.append({
                    'nombre': spec['nombre'], 'archivo': archivo.name, 'metodo': atributo,
                    'nivel': spec['nivel'], 'categoria': spec['categoria'], 'grupos': list(spec['grupos']),
                    'parametros': sorted(spec['parametros']), 'requeridos': spec['requeridos'],
                    'descripcion': spec['descripcion'], 'ejemplos': spec['ejemplos'],
                    'chars_descripcion': len(esquema['description']),
                    'chars_esquema_json': len(texto),
                })
    return sorted(salida, key=lambda s: (s['categoria'], s['nombre']))


if __name__ == '__main__':
    print(json.dumps(herramientas(), ensure_ascii=False, indent=1))
