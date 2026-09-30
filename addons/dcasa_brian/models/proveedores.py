"""Proveedores de IA de Brian: un formato neutro y adaptadores por API.

Formato neutro de MENSAJES (lista, en orden; el system prompt va aparte)::

    {'rol': 'user', 'texto': '…', 'imagenes': [{'mimetype': 'image/png', 'datos': '<base64>'}]}
    {'rol': 'assistant', 'texto': '…',
     'tool_calls': [{'id': 'x1', 'nombre': 'buscar_productos', 'argumentos': {...}}],
     'crudo': {'anthropic': [...bloques tal cual...]}}          # opcional, se reenvía igual
    {'rol': 'tool', 'tool_call_id': 'x1', 'nombre': 'buscar_productos', 'texto': '{json}', 'error': False}

HERRAMIENTAS: la lista de ``brian.herramientas.esquema`` (``name``, ``description``,
``input_schema``; se ignoran ``nivel`` y ``categoria``).

RESPUESTA de ``Proveedor.chatear(sistema, mensajes, herramientas)``::

    {'texto': str, 'tool_calls': [{'id', 'nombre', 'argumentos'}],
     'fin': 'fin' | 'herramientas' | 'limite' | 'rechazo',
     'uso': {'entrada': int, 'salida': int}, 'crudo': {...}}

Configuración (variables de entorno = secretos de Cloudflare; ``ir.config_parameter``
``dcasa_brian.<clave>`` la sobrescribe desde Ajustes, salvo la clave API que va primero
por entorno):

====================  =========================  ==========================================
Entorno               Parámetro                  Ejemplos
====================  =========================  ==========================================
BRIAN_PROVEEDOR       dcasa_brian.proveedor      anthropic, openai, xai, groq, openrouter,
                                                 together, ollama, prueba
BRIAN_MODELO          dcasa_brian.modelo         claude-haiku-4-5, claude-sonnet-5-5,
                                                 gpt-4o-mini, grok-3-mini,
                                                 llama-3.3-70b-versatile
BRIAN_API_KEY         dcasa_brian.api_key        (secreto; nunca se muestra completa)
BRIAN_BASE_URL        dcasa_brian.base_url       https://api.groq.com/openai/v1
BRIAN_HERRAMIENTAS_MAX dcasa_brian.herramientas_max  12 (0 = todas si el modelo es grande)
====================  =========================  ==========================================

Solo Anthropic trae modelo por defecto; para los demás proveedores el modelo se configura.
"""
import json
import logging
import os
import time

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

TIMEOUT = (10, 120)          # conexión, lectura (segundos)
REINTENTOS = 2
ESPERA_BASE = 1.5            # segundos; los tests la ponen en 0
MAX_TOKENS = 8000

MODELO_ANTHROPIC_PEQUENO = 'claude-haiku-4-5'
MODELO_ANTHROPIC_GRANDE = 'claude-sonnet-5-5'

PROVEEDORES = {
    'anthropic': {'tipo': 'anthropic', 'nombre': 'Anthropic (Claude)', 'base_url': 'https://api.anthropic.com',
                  'modelo': MODELO_ANTHROPIC_PEQUENO, 'vision': True, 'clave': True},
    'openai': {'tipo': 'openai', 'nombre': 'OpenAI (ChatGPT)', 'base_url': 'https://api.openai.com/v1',
               'vision': True, 'clave': True},
    'xai': {'tipo': 'openai', 'nombre': 'xAI (Grok)', 'base_url': 'https://api.x.ai/v1',
            'vision': True, 'clave': True},
    'groq': {'tipo': 'openai', 'nombre': 'Groq (Llama y otros)', 'base_url': 'https://api.groq.com/openai/v1',
             'vision': False, 'clave': True},
    'openrouter': {'tipo': 'openai', 'nombre': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1',
                   'vision': True, 'clave': True},
    'together': {'tipo': 'openai', 'nombre': 'Together AI', 'base_url': 'https://api.together.xyz/v1',
                 'vision': False, 'clave': True},
    'ollama': {'tipo': 'openai', 'nombre': 'Ollama (local)', 'base_url': 'http://localhost:11434/v1',
               'vision': False, 'clave': False},
    'prueba': {'tipo': 'prueba', 'nombre': 'Prueba (sin IA, para tests)', 'modelo': 'prueba',
               'vision': True, 'clave': False},
}

# Palabras que delatan un modelo pequeño (se le ofrecen menos herramientas a la vez).
PEQUENOS = ('haiku', 'mini', 'nano', 'small', 'lite', '1b', '3b', '7b', '8b', '9b', 'instant', 'prueba')


class ProveedorError(Exception):
    """Error del proveedor de IA, con mensaje en español para mostrar al usuario."""


# ----------------------------------------------------------------------
# Adaptadores
# ----------------------------------------------------------------------

class Proveedor:
    tipo = None

    def __init__(self, config):
        self.config = config
        self.modelo = config.get('modelo')
        self.base_url = (config.get('base_url') or '').rstrip('/')
        self.api_key = config.get('api_key') or ''
        self.vision = bool(config.get('vision'))
        self.max_tokens = config.get('max_tokens') or MAX_TOKENS

    def chatear(self, sistema, mensajes, herramientas=None):
        raise NotImplementedError

    # -- HTTP ---------------------------------------------------------------

    def _post(self, url, headers, cuerpo):
        """POST JSON con timeout y reintentos en 429/5xx/red. Lanza ProveedorError en español."""
        ultimo = None
        for intento in range(REINTENTOS + 1):
            respuesta = None
            try:
                respuesta = requests.post(url, headers=headers, json=cuerpo, timeout=TIMEOUT)
            except requests.Timeout as error:
                ultimo = ProveedorError('El proveedor de IA tardó demasiado en responder. Intenta de nuevo.')
                ultimo.__cause__ = error
            except requests.RequestException as error:
                ultimo = ProveedorError('No pude conectarme con el proveedor de IA. Revisa la dirección y la red.')
                ultimo.__cause__ = error
            else:
                if respuesta.status_code < 400:
                    try:
                        return respuesta.json()
                    except ValueError as error:
                        raise ProveedorError('El proveedor de IA respondió algo que no entiendo.') from error
                if respuesta.status_code != 429 and respuesta.status_code < 500:
                    raise ProveedorError(self._mensaje_http(respuesta))
                ultimo = ProveedorError(self._mensaje_http(respuesta))
            if intento < REINTENTOS:
                espera = ESPERA_BASE * (2 ** intento)
                if respuesta is not None:
                    try:
                        espera = max(espera, min(float(respuesta.headers.get('retry-after') or 0), 10))
                    except (TypeError, ValueError):
                        pass
                if espera > 0:
                    time.sleep(espera)
        _logger.warning('Brian: el proveedor falló tras %s intentos: %s', REINTENTOS + 1, ultimo)
        raise ultimo

    @staticmethod
    def _mensaje_http(respuesta):
        codigo = respuesta.status_code
        try:
            detalle = respuesta.json()
            detalle = detalle.get('error', detalle)
            if isinstance(detalle, dict):
                detalle = detalle.get('message') or json.dumps(detalle)[:300]
        except ValueError:
            detalle = (respuesta.text or '')[:300]
        if codigo in (401, 403):
            return 'La clave de API de Brian no es válida o no tiene permiso. Revísala en Ajustes › Brian.'
        if codigo == 404:
            return f'El proveedor no encontró el modelo o la dirección configurada ({detalle}).'
        if codigo == 429:
            return 'El proveedor de IA está saturado o se alcanzó el límite de uso. Intenta en un rato.'
        if codigo >= 500:
            return 'El proveedor de IA tuvo un problema de su lado. Intenta de nuevo en un momento.'
        return f'El proveedor de IA rechazó la solicitud: {detalle}'


class ProveedorAnthropic(Proveedor):
    """Messages API de Anthropic (tool use y visión), por HTTP directo."""
    tipo = 'anthropic'
    VERSION = '2023-06-01'

    def chatear(self, sistema, mensajes, herramientas=None):
        cuerpo = {
            'model': self.modelo,
            'max_tokens': self.max_tokens,
            'messages': self.mensajes(mensajes),
        }
        if sistema:
            cuerpo['system'] = sistema
        if herramientas:
            cuerpo['tools'] = [{'name': h['name'], 'description': h['description'],
                                'input_schema': h['input_schema']} for h in herramientas]
        headers = {'x-api-key': self.api_key, 'anthropic-version': self.VERSION,
                   'content-type': 'application/json'}
        datos = self._post(f'{self.base_url}/v1/messages', headers, cuerpo)
        return self.respuesta(datos)

    @staticmethod
    def mensajes(mensajes):
        salida = []

        def agregar(rol, bloques):
            if salida and salida[-1]['role'] == rol:
                salida[-1]['content'].extend(bloques)
            else:
                salida.append({'role': rol, 'content': list(bloques)})

        for m in mensajes:
            rol = m.get('rol')
            if rol == 'user':
                bloques = [{'type': 'image', 'source': {'type': 'base64', 'media_type': i['mimetype'],
                                                        'data': i['datos']}}
                           for i in m.get('imagenes') or ()]
                bloques.append({'type': 'text', 'text': m.get('texto') or '(sin texto)'})
                agregar('user', bloques)
            elif rol == 'assistant':
                crudo = (m.get('crudo') or {}).get('anthropic')
                if crudo:
                    agregar('assistant', crudo)
                    continue
                bloques = [{'type': 'text', 'text': m['texto']}] if m.get('texto') else []
                bloques += [{'type': 'tool_use', 'id': c['id'], 'name': c['nombre'],
                             'input': c.get('argumentos') or {}} for c in m.get('tool_calls') or ()]
                if bloques:
                    agregar('assistant', bloques)
            elif rol == 'tool':
                agregar('user', [{'type': 'tool_result', 'tool_use_id': m['tool_call_id'],
                                  'content': m.get('texto') or '{}', 'is_error': bool(m.get('error'))}])
        # tool_result debe ir primero en su mensaje de usuario.
        for s in salida:
            if s['role'] == 'user':
                s['content'].sort(key=lambda b: 0 if b['type'] == 'tool_result' else 1)
        if salida and salida[0]['role'] != 'user':
            salida.insert(0, {'role': 'user', 'content': [{'type': 'text', 'text': '(inicio)'}]})
        return salida

    @staticmethod
    def respuesta(datos):
        bloques = datos.get('content') or []
        texto = '\n'.join(b.get('text', '') for b in bloques if b.get('type') == 'text').strip()
        llamadas = [{'id': b['id'], 'nombre': b['name'], 'argumentos': b.get('input') or {}}
                    for b in bloques if b.get('type') == 'tool_use']
        razon = datos.get('stop_reason')
        fin = {'tool_use': 'herramientas', 'max_tokens': 'limite', 'refusal': 'rechazo'}.get(razon, 'fin')
        if llamadas:
            fin = 'herramientas'
        if fin == 'rechazo' and not texto:
            texto = 'No puedo ayudarte con eso.'
        uso = datos.get('usage') or {}
        return {'texto': texto, 'tool_calls': llamadas, 'fin': fin,
                'uso': {'entrada': uso.get('input_tokens', 0), 'salida': uso.get('output_tokens', 0)},
                'crudo': {'anthropic': bloques}}


class ProveedorOpenAI(Proveedor):
    """Chat Completions compatible (OpenAI, xAI, Groq, OpenRouter, Together, Ollama…)."""
    tipo = 'openai'

    def chatear(self, sistema, mensajes, herramientas=None):
        cuerpo = {'model': self.modelo, 'messages': self.mensajes(sistema, mensajes)}
        clave_max = 'max_completion_tokens' if self.config.get('proveedor') == 'openai' else 'max_tokens'
        cuerpo[clave_max] = self.max_tokens
        if herramientas:
            cuerpo['tools'] = [{'type': 'function', 'function': {
                'name': h['name'], 'description': h['description'], 'parameters': h['input_schema']}}
                for h in herramientas]
        headers = {'content-type': 'application/json'}
        if self.api_key:
            headers['authorization'] = f'Bearer {self.api_key}'
        datos = self._post(f'{self.base_url}/chat/completions', headers, cuerpo)
        return self.respuesta(datos)

    def mensajes(self, sistema, mensajes):
        salida = [{'role': 'system', 'content': sistema}] if sistema else []
        for m in mensajes:
            rol = m.get('rol')
            if rol == 'user':
                imagenes = m.get('imagenes') or ()
                if imagenes and self.vision:
                    contenido = [{'type': 'text', 'text': m.get('texto') or ''}] + [
                        {'type': 'image_url', 'image_url': {'url': f"data:{i['mimetype']};base64,{i['datos']}"}}
                        for i in imagenes]
                else:
                    contenido = m.get('texto') or ''
                salida.append({'role': 'user', 'content': contenido})
            elif rol == 'assistant':
                item = {'role': 'assistant', 'content': m.get('texto') or None}
                if m.get('tool_calls'):
                    item['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {
                        'name': c['nombre'], 'arguments': json.dumps(c.get('argumentos') or {}, ensure_ascii=False)}}
                        for c in m['tool_calls']]
                salida.append(item)
            elif rol == 'tool':
                salida.append({'role': 'tool', 'tool_call_id': m['tool_call_id'], 'content': m.get('texto') or '{}'})
        return salida

    @staticmethod
    def respuesta(datos):
        opciones = datos.get('choices') or [{}]
        mensaje = opciones[0].get('message') or {}
        llamadas = []
        for c in mensaje.get('tool_calls') or ():
            funcion = c.get('function') or {}
            try:
                argumentos = json.loads(funcion.get('arguments') or '{}')
                if not isinstance(argumentos, dict):
                    raise ValueError
            except ValueError:
                argumentos = {'__invalidos__': funcion.get('arguments')}
            llamadas.append({'id': c.get('id') or f"llamada_{len(llamadas)}", 'nombre': funcion.get('name'),
                             'argumentos': argumentos})
        razon = opciones[0].get('finish_reason')
        fin = 'herramientas' if llamadas else {'length': 'limite', 'content_filter': 'rechazo'}.get(razon, 'fin')
        uso = datos.get('usage') or {}
        return {'texto': (mensaje.get('content') or '').strip(), 'tool_calls': llamadas, 'fin': fin,
                'uso': {'entrada': uso.get('prompt_tokens', 0), 'salida': uso.get('completion_tokens', 0)},
                'crudo': {}}


# Guion del proveedor de prueba (lo fijan los tests).
GUION = []
LLAMADAS = []


def fijar_guion(respuestas):
    """Fija las próximas respuestas del proveedor 'prueba'.

    Cada respuesta es un texto (respuesta final) o un dict
    ``{'texto': '…', 'herramientas': [('nombre', {args}), …]}``.
    """
    GUION[:] = list(respuestas)
    LLAMADAS[:] = []


class ProveedorPrueba(Proveedor):
    """Determinista, sin red: sigue ``GUION`` y anota cada llamada en ``LLAMADAS``."""
    tipo = 'prueba'

    def chatear(self, sistema, mensajes, herramientas=None):
        LLAMADAS.append({'sistema': sistema, 'mensajes': json.loads(json.dumps(mensajes, default=str)),
                         'herramientas': [h['name'] for h in herramientas or ()]})
        if not GUION:
            return {'texto': 'Listo.', 'tool_calls': [], 'fin': 'fin', 'uso': {'entrada': 0, 'salida': 0},
                    'crudo': {}}
        paso = GUION.pop(0)
        if isinstance(paso, str):
            paso = {'texto': paso}
        llamadas = []
        for i, h in enumerate(paso.get('herramientas') or ()):
            nombre, argumentos = (h['nombre'], h.get('argumentos')) if isinstance(h, dict) else h
            llamadas.append({'id': f'prueba_{len(LLAMADAS)}_{i}', 'nombre': nombre, 'argumentos': argumentos or {}})
        return {'texto': paso.get('texto') or '', 'tool_calls': llamadas,
                'fin': 'herramientas' if llamadas else 'fin', 'uso': {'entrada': 0, 'salida': 0}, 'crudo': {}}


ADAPTADORES = {'anthropic': ProveedorAnthropic, 'openai': ProveedorOpenAI, 'prueba': ProveedorPrueba}


def enmascarar(clave):
    if not clave:
        return ''
    return f'…{clave[-4:]}' if len(clave) > 8 else '••••'


# ----------------------------------------------------------------------
# Modelo Odoo: configuración y fábrica
# ----------------------------------------------------------------------

class BrianProveedores(models.AbstractModel):
    _name = 'brian.proveedores'
    _description = 'Proveedores de IA de Brian'

    @api.model
    def _valor(self, clave, entorno, primero_entorno=False):
        parametro = self.env['ir.config_parameter'].sudo().get_param(f'dcasa_brian.{clave}') or ''
        variable = os.environ.get(entorno) or ''
        if primero_entorno:
            return (variable or parametro).strip()
        return (parametro or variable).strip()

    @api.model
    def configuracion(self):
        """Configuración efectiva (incluye la clave: NO devolver al navegador)."""
        proveedor = (self._valor('proveedor', 'BRIAN_PROVEEDOR') or 'anthropic').lower()
        base = PROVEEDORES.get(proveedor, {})
        modelo = self._valor('modelo', 'BRIAN_MODELO') or base.get('modelo') or ''
        try:
            maximo = int(self._valor('herramientas_max', 'BRIAN_HERRAMIENTAS_MAX') or 0)
        except ValueError:
            maximo = 0
        return {
            'proveedor': proveedor,
            'tipo': base.get('tipo'),
            'nombre': base.get('nombre', proveedor),
            'modelo': modelo,
            'base_url': self._valor('base_url', 'BRIAN_BASE_URL') or base.get('base_url', ''),
            'api_key': self._valor('api_key', 'BRIAN_API_KEY', primero_entorno=True),
            'requiere_clave': base.get('clave', True),
            'vision': base.get('vision', False),
            'herramientas_max': maximo,
            'grande': self.es_grande(modelo),
        }

    @api.model
    def es_grande(self, modelo):
        modelo = (modelo or '').lower()
        return bool(modelo) and not any(p in modelo for p in PEQUENOS)

    @api.model
    def estado(self):
        """Para la interfaz: nunca incluye la clave completa."""
        config = self.configuracion()
        faltan = []
        if not config['tipo']:
            faltan.append(self.env._('un proveedor válido'))
        if not config['modelo']:
            faltan.append(self.env._('el modelo'))
        if config['requiere_clave'] and not config['api_key']:
            faltan.append(self.env._('la clave de API'))
        mensaje = ''
        if faltan:
            mensaje = self.env._(
                'Brian todavía no está conectado a una IA: falta %s. Un administrador lo configura '
                'en Ajustes › Brian (o con las variables BRIAN_PROVEEDOR, BRIAN_MODELO y BRIAN_API_KEY).',
                ', '.join(faltan))
        return {
            'configurado': not faltan,
            'proveedor': config['proveedor'],
            'nombre': config['nombre'],
            'modelo': config['modelo'],
            'clave': enmascarar(config['api_key']),
            'vision': config['vision'],
            'mensaje': mensaje,
        }

    @api.model
    def obtener(self):
        """Devuelve el adaptador listo, o lanza ProveedorError si falta configuración."""
        estado = self.estado()
        if not estado['configurado']:
            raise ProveedorError(estado['mensaje'])
        config = self.configuracion()
        return ADAPTADORES[config['tipo']](config)

    @api.model
    def probar(self):
        """Llamada mínima para el botón «Probar conexión»."""
        try:
            proveedor = self.obtener()
            respuesta = proveedor.chatear('Responde solo con la palabra: listo',
                                          [{'rol': 'user', 'texto': 'Prueba de conexión'}], [])
        except ProveedorError as error:
            return {'ok': False, 'mensaje': str(error)}
        return {'ok': True, 'mensaje': self.env._('Conexión correcta con %(p)s (%(m)s). Respondió: %(r)s',
                                                  p=proveedor.config['nombre'], m=proveedor.modelo,
                                                  r=(respuesta['texto'] or '—')[:200])}
