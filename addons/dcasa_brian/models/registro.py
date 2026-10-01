"""Registro de herramientas de Brian: el contrato que comparten el chat, Telegram y MCP.

Cada capacidad de Brian es un método de ``brian.herramientas`` decorado con
``@herramienta``. El mismo catálogo se ofrece al modelo de IA (tool calling), al servidor
MCP (``tools/list`` y ``tools/call``) y a Telegram, siempre ejecutado COMO EL USUARIO que
conversa: los permisos, reglas de registro y compañías de Odoo se respetan tal cual.

Niveles (``nivel``):

* ``lectura``       — consulta; nunca cambia nada. Se ejecuta directo.
* ``construccion``  — «el constructor»: crea o edita. Se ejecuta directo, queda en el
                      registro de acciones y se puede revisar.
* ``sensible``      — cambia algo difícil de revertir (roles, confirmar ventas, publicar
                      facturas…). Brian propone y el humano confirma con un clic.
* Lo prohibido NO es una herramienta: no existe forma de pedirlo (ver ``politica.py``).

Contrato de una herramienta::

    @herramienta(
        nombre='buscar_productos',
        descripcion='Busca productos por nombre, código o categoría.',   # español, 1–2 frases
        parametros={'texto': {'type': 'string', 'description': '…'}, …},  # JSON Schema (properties)
        requeridos=['texto'],
        nivel='lectura',
        categoria='catalogo',
        grupos=('sales_team.group_sale_salesman',),                       # opcional: quién la ve
    )
    def _h_buscar_productos(self, texto, limite=10):
        return {'productos': [...]}            # dict serializable a JSON

La función devuelve un ``dict``. Para errores de uso levanta ``BrianError`` con un mensaje
en español que el modelo pueda entender y corregir.

Pensado para modelos pequeños: nombres en español con verbo + objeto, pocos parámetros,
tipos simples, descripciones cortas con ejemplos, y ``catalogo(consulta=…)`` que entrega
solo las herramientas relevantes para el mensaje (ver ``seleccionar``).
"""
import json
import logging
import unicodedata

from odoo import api, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

NIVELES = ('lectura', 'construccion', 'sensible')

CATEGORIAS = {
    'general': 'Pantalla actual, búsqueda en todo, ayuda',
    'ventas': 'Ventas, cotizaciones, pedidos, reporte del día',
    'catalogo': 'Productos, precios, inventario, existencias',
    'clientes': 'Clientes, proveedores, contactos, socios y puntos',
    'contabilidad': 'Facturas, pagos, bancos, reportes contables, ITBMS',
    'usuarios': 'Usuarios, roles y permisos',
}


class BrianError(Exception):
    """Error de uso de una herramienta: el mensaje va de vuelta al modelo para que corrija."""


def herramienta(nombre, descripcion, parametros=None, requeridos=(), nivel='lectura', categoria='general',
                grupos=(), ejemplos=()):
    """Marca un método de ``brian.herramientas`` como herramienta de Brian."""
    if nivel not in NIVELES:
        raise ValueError(f'Nivel desconocido: {nivel}')
    if categoria not in CATEGORIAS:
        raise ValueError(f'Categoría desconocida: {categoria}')

    def decorar(metodo):
        metodo._brian = {
            'nombre': nombre,
            'descripcion': descripcion,
            'parametros': parametros or {},
            'requeridos': list(requeridos),
            'nivel': nivel,
            'categoria': categoria,
            'grupos': tuple(grupos),
            'ejemplos': list(ejemplos),
            'metodo': metodo.__name__,
        }
        return metodo
    return decorar


def normalizar(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


class BrianHerramientas(models.AbstractModel):
    """Catálogo y ejecución de herramientas. AbstractModel sin ACL: NADA se llama por RPC.

    Todo es ``_`` o ``@api.private``: si ``ejecutar(..., confirmado=True)`` o ``confirmar``
    fueran públicos, cualquiera se saltaría la confirmación de las acciones sensibles. Los
    únicos caminos son ``brian.conversacion.enviar/confirmar_accion/rechazar_accion`` (que
    validan dueño de la conversación y de la acción), el webhook de Telegram y el servidor
    MCP (controladores que llaman en Python, como el usuario autenticado).
    """
    _name = 'brian.herramientas'
    _description = 'Herramientas de Brian'

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------

    @api.model
    def _todas(self):
        """{nombre: especificación} de todas las herramientas declaradas (sin filtrar por usuario)."""
        especificaciones = {}
        for atributo in dir(type(self)):
            metodo = getattr(type(self), atributo, None)
            spec = getattr(metodo, '_brian', None)
            if spec:
                especificaciones[spec['nombre']] = spec
        return especificaciones

    @api.model
    def _disponible(self, spec):
        return all(self.env.user.has_group(grupo) for grupo in spec['grupos'])

    @api.private
    @api.model
    def esquema(self, spec):
        """La herramienta en el formato neutro que traducen los proveedores y MCP."""
        return {
            'name': spec['nombre'],
            'description': spec['descripcion'] + (
                ' Ejemplos: ' + '; '.join(spec['ejemplos']) if spec['ejemplos'] else ''),
            'input_schema': {
                'type': 'object',
                'properties': spec['parametros'],
                'required': spec['requeridos'],
                'additionalProperties': False,
            },
            'nivel': spec['nivel'],
            'categoria': spec['categoria'],
        }

    @api.private
    @api.model
    def catalogo(self, consulta=None, maximo=None):
        """Herramientas que este usuario puede usar; con ``consulta``, solo las relevantes."""
        specs = [s for s in self._todas().values() if self._disponible(s)]
        if consulta and maximo:
            specs = self.seleccionar(specs, consulta, maximo)
        return [self.esquema(s) for s in sorted(specs, key=lambda s: (s['categoria'], s['nombre']))]

    @api.private
    @api.model
    def seleccionar(self, specs, consulta, maximo):
        """Preselección barata por palabras (para modelos pequeños con pocas herramientas a la vez).

        Siempre incluye las de la categoría ``general``; el resto se ordena por coincidencias
        entre el mensaje y el nombre, la descripción y la categoría de la herramienta.
        """
        palabras = {p for p in normalizar(consulta).replace('_', ' ').split() if len(p) > 2}

        def puntaje(spec):
            texto = normalizar(' '.join([spec['nombre'].replace('_', ' '), spec['descripcion'],
                                         CATEGORIAS[spec['categoria']], ' '.join(spec['ejemplos'])]))
            return sum(1 for p in palabras if p in texto)

        # Las generales (pantalla actual, ayuda, buscar…) van siempre, pero sin ocupar más de
        # un tercio de los cupos: el resto es para las herramientas relevantes al mensaje.
        generales = sorted((s for s in specs if s['categoria'] == 'general'), key=puntaje, reverse=True)
        generales = generales[:max(1, maximo // 3)]
        resto = sorted((s for s in specs if s['categoria'] != 'general'), key=puntaje, reverse=True)
        return (generales + resto)[:maximo]

    # ------------------------------------------------------------------
    # Ejecución
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def ejecutar(self, nombre, argumentos=None, canal='chat', conversacion=None, confirmado=False):
        """Ejecuta una herramienta como el usuario actual, con política y registro de auditoría.

        Devuelve siempre un dict:
          {'ok': True, 'datos': {...}}
          {'ok': False, 'error': 'mensaje en español'}
          {'ok': False, 'requiere_confirmacion': True, 'accion_id': id, 'resumen': '…'}
        """
        argumentos = dict(argumentos or {})
        spec = self._todas().get(nombre)
        Accion = self.env['brian.accion']
        if not spec or not self._disponible(spec):
            return {'ok': False, 'error': f'No existe la herramienta «{nombre}» o no tienes permiso para usarla.'}
        faltan = [r for r in spec['requeridos'] if argumentos.get(r) in (None, '')]
        if faltan:
            return {'ok': False, 'error': f'Faltan datos: {", ".join(faltan)}.'}
        desconocidos = set(argumentos) - set(spec['parametros'])
        if desconocidos:
            return {'ok': False, 'error': f'Parámetros que no existen: {", ".join(sorted(desconocidos))}.'}

        accion = Accion.registrar(spec, argumentos, canal=canal, conversacion=conversacion)
        politica = self.env['brian.politica']
        try:
            politica.verificar(spec, argumentos)
        except BrianError as error:
            accion.marcar('bloqueada', error=str(error))
            return {'ok': False, 'error': str(error)}
        if spec['nivel'] == 'sensible' and not confirmado:
            resumen = politica.resumir(spec, argumentos)
            accion.marcar('por_confirmar', resumen=resumen)
            return {'ok': False, 'requiere_confirmacion': True, 'accion_id': accion.id, 'resumen': resumen}
        return self._correr(spec, argumentos, accion)

    @api.model
    def _correr(self, spec, argumentos, accion):
        metodo = getattr(self, spec['metodo'])
        try:
            with self.env.cr.savepoint():
                datos = metodo(**argumentos)
            json.dumps(datos, default=str)
        except BrianError as error:
            accion.marcar('error', error=str(error))
            return {'ok': False, 'error': str(error)}
        except (AccessError, UserError, ValidationError) as error:
            mensaje = error.args[0] if error.args else str(error)
            accion.marcar('error', error=mensaje)
            return {'ok': False, 'error': mensaje}
        except TypeError as error:
            accion.marcar('error', error=str(error))
            return {'ok': False, 'error': 'Parámetros inválidos para esta herramienta.'}
        except Exception as error:  # noqa: BLE001 — nunca se cae la conversación
            _logger.exception('Brian: fallo en la herramienta %s', spec['nombre'])
            accion.marcar('error', error=repr(error))
            return {'ok': False, 'error': 'Ocurrió un error inesperado; quedó registrado para revisarlo.'}
        accion.marcar('hecha', resultado=datos)
        return {'ok': True, 'datos': datos}

    @api.private
    @api.model
    def confirmar(self, accion_id):
        """El humano aprueba una acción sensible propuesta por Brian."""
        accion = self.env['brian.accion'].browse(accion_id).exists()
        if not accion or accion.create_uid != self.env.user or accion.estado != 'por_confirmar':
            return {'ok': False, 'error': 'Esa acción ya no está pendiente de confirmación.'}
        spec = self._todas().get(accion.herramienta)
        if not spec or not self._disponible(spec):
            accion.marcar('error', error='La herramienta ya no existe o ya no tienes permiso para usarla.')
            return {'ok': False, 'error': 'Esa herramienta ya no está disponible para ti.'}
        argumentos = json.loads(accion.argumentos or '{}')
        try:
            self.env['brian.politica'].verificar(spec, argumentos)
        except BrianError as error:
            accion.marcar('bloqueada', error=str(error))
            return {'ok': False, 'error': str(error)}
        return self._correr(spec, argumentos, accion)

    @api.private
    @api.model
    def rechazar(self, accion_id):
        accion = self.env['brian.accion'].browse(accion_id).exists()
        if accion and accion.create_uid == self.env.user and accion.estado == 'por_confirmar':
            accion.marcar('rechazada')
        return {'ok': True}
