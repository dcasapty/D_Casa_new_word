"""Un Worker de Juan SIMULADO para «Brian de la tienda»: responde ``POST /tienda/v1/mensaje`` según el contrato §2.

Sirve para las pruebas en el navegador (tests/test_navegador.py) y para las capturas, mientras el Worker de verdad
(``juan/``, otra rama) no esté. Solo usa la biblioteca estándar: se puede correr suelto.

    python3 worker_simulado.py --puerto 8787 --token-worker <JUAN_WORKER_TOKEN> \\
        --odoo http://127.0.0.1:8069 --token-odoo <JUAN_ODOO_TOKEN>

Hace lo que el contrato pide del Worker, en pequeño:

* CORS (y ``OPTIONS``) y el pase: la firma con la llave derivada de ``JUAN_WORKER_TOKEN`` y que no esté vencido (si no,
  401 ``motivo: pase``). La ``red`` del pase no se compara con la conexión (contrato_cambios, «2026-11-13 (2)»).
* Las tarjetas salen SOLO de las herramientas de Odoo de ese turno (``POST /dcasa/juan/v1/herramienta`` con
  ``origen: tienda`` y sin conversación), nunca inventadas. ``proponer_carrito`` solo con un producto ya visto.
* Una conversación por guion (palabras clave), no un modelo de IA: colchones o salas → ``buscar_productos``; «ponlo» o
  «agrega» → ``proponer_carrito``; envío → ``ubicacion``; la ubicación → ``cotizar_envio`` con ``lat``/``lon``;
  «persona» o «whatsapp» → ``whatsapp``; «gracias» → ``calificar``. Con ``texto`` igual a un motivo de error
  (``tope_dia``, ``presupuesto``…) responde ese error, para probar los avisos.
* Andrés vendedor (A1 a A5, docs/PLAN_ANDRES_VOZ_PORTADA.md), como el Worker de verdad: cada bloque de tarjetas con su
  ``titulo`` (lo buscado); el envío con su ``lugar_id`` y, con algo en el carrito, «¿Te lo sumo a la cotización?»;
  «sí» o «súmalo» → ``sumar_envio``; ``confirmar_envio`` → «Listo, te lo sumé…» (sin cifras); «quita …» o «deja N» →
  ``proponer_cambio_carrito`` (solo lo que está en el carrito) y ``confirmar_cambio`` con lo que dice el carrito;
  ``carrito_bajo`` → la reacción, una sola vez por sesión (la segunda, sin bloques).
"""
import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ETIQUETA = b'brian-tienda-pase-v1'
ERRORES = {'tope_sesion': 429, 'tope_red': 429, 'tope_dia': 429, 'presupuesto': 429, 'apagado': 503, 'fallo': 502}


def _red(ip):
    try:
        d = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if d.version == 6 and d.ipv4_mapped:
        d = d.ipv4_mapped
    b = d.packed
    if d.version == 4:
        return f'{b[0]}.{b[1]}.{b[2]}.0/24'
    return ':'.join(format(int.from_bytes(b[i:i + 2], 'big'), 'x') for i in range(0, 8, 2)) + '::/64'


def _b64u(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode()


def leer_pase(pase, token):
    """El payload si el pase es bueno; si no, ``None`` (lo mismo que hará el Worker de verdad)."""
    if not isinstance(pase, str) or pase.count('.') != 1:
        return None
    cuerpo, firma = pase.split('.')
    llave = hmac.new(token.encode(), ETIQUETA, hashlib.sha256).digest()
    if not hmac.compare_digest(firma, _b64u(hmac.new(llave, cuerpo.encode(), hashlib.sha256).digest())):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cuerpo + '=' * (-len(cuerpo) % 4)))
    except ValueError:
        return None
    if payload.get('v') != 1 or not isinstance(payload.get('exp'), int) or payload['exp'] < time.time():
        return None
    return payload


class WorkerSimulado:
    def __init__(self, token_worker, odoo, token_odoo, cookie_odoo=None, puerto=0):
        self.token_worker = token_worker
        self.odoo = odoo.rstrip('/')
        self.token_odoo = token_odoo
        self.cookie_odoo = cookie_odoo          # en las pruebas: la galleta del cursor de prueba de Odoo
        self.puerto = puerto
        self.sesiones = {}                      # sid → {'vistos': {producto_id: producto}, 'ultimo': producto_id}
        self.recibidos = []                     # lo que llegó (para las pruebas), sin la ubicación
        self.ubicaciones = 0
        self.servidor = None

    # ------------------------------------------------------------------ Odoo

    def herramienta(self, nombre, argumentos):
        pedido = urllib.request.Request(
            f'{self.odoo}/dcasa/juan/v1/herramienta', method='POST',
            data=json.dumps({'nombre': nombre, 'argumentos': argumentos, 'origen': 'tienda'}).encode(),
            headers={'Authorization': f'Bearer {self.token_odoo}', 'Content-Type': 'application/json'})
        if self.cookie_odoo:
            pedido.add_header('Cookie', self.cookie_odoo())
        try:
            with urllib.request.urlopen(pedido, timeout=20) as r:
                datos = json.loads(r.read())
        except Exception:  # noqa: BLE001 — simulado: cualquier fallo es «sin datos»
            return {}
        return datos.get('resultado') or {} if datos.get('ok') else {}

    # ------------------------------------------------------------------ el guion

    @staticmethod
    def _tarjeta(p):
        return {k: p.get(k) for k in ('producto_id', 'plantilla_id', 'nombre', 'precio_texto', 'disponibilidad',
                                      'imagen', 'agregable')} | {'url': p.get('ruta') or p.get('url')}

    WA = {'tipo': 'whatsapp', 'texto': 'Escríbenos por WhatsApp', 'mensaje': 'Hola, vengo del chat de la web.'}

    @staticmethod
    def _ok(pose, bloques, chips=None):
        datos = {'ok': True, 'pose': pose, 'bloques': bloques}
        if chips:
            datos['chips'] = chips
        return 200, datos

    def responder(self, sid, cuerpo):
        estado = self.sesiones.setdefault(sid, {'vistos': {}, 'ultimo': None, 'envio': None, 'oferta_envio': False,
                                                'pendiente_envio': None, 'pendiente_cambio': None,
                                                'reaccion': False})
        texto = (cuerpo.get('texto') or '').strip()
        accion = cuerpo.get('accion') or {}
        if accion.get('tipo') == 'chip':
            texto = str(accion.get('valor') or '')
        t = texto.lower()
        carrito = (cuerpo.get('carrito') or {}).get('lineas') or []
        if t in ERRORES:
            return ERRORES[t], {'ok': False, 'motivo': t}
        if cuerpo.get('ubicacion'):
            return self._envio(estado, self.herramienta('cotizar_envio', {'lat': cuerpo['ubicacion'].get('lat'),
                                                                          'lon': cuerpo['ubicacion'].get('lon')}),
                               carrito, ubicacion=True)
        if accion.get('tipo') in ('confirmar_envio', 'confirmar_cambio', 'carrito_bajo'):
            return self._vendedor(estado, accion, carrito)
        if accion.get('tipo') == 'confirmar_carrito':
            if accion.get('resultado') == 'ok':
                return self._ok('bolsita', [{'tipo': 'texto', 'texto': 'Listo, te lo puse en el carrito. Gracias por '
                                                                       'escogernos.'}],
                                ['¿Cuánto cuesta el envío?', 'Formas de pago'])
            return self._ok('burbuja_chat', [{'tipo': 'texto', 'texto': 'No pude ponerlo en el carrito. Te dejo la '
                                                                        'ficha o te ayudan por WhatsApp.'}])
        if accion.get('tipo') == 'calificar':
            return self._ok('corazon', [{'tipo': 'texto', 'texto': 'Gracias por calificarme, de verdad me ayuda. Que '
                                                                   'tengas un lindo día.'}])
        return self._guion(estado, t, texto, carrito)

    def _envio(self, estado, envio, carrito, ubicacion=False):
        if ubicacion:
            self.ubicaciones += 1
        lugar = (envio.get('lugar') or {}).get('nombre') or ''
        lugar_id = (envio.get('lugar') or {}).get('lugar_id')
        if envio.get('estado') != 'precio':
            frase = envio.get('frase_para_el_cliente') or '¿Me dices el barrio o un punto de referencia?'
            return self._ok('mapa', [{'tipo': 'texto', 'texto': frase}])
        primero = (f'Gracias. Por tu ubicación, te lo llevamos a {lugar}.' if ubicacion else
                   f'Gracias. Te cuento el envío a {lugar}.')
        bloques = [{'tipo': 'texto', 'texto': primero},
                   {'tipo': 'envio', 'texto': envio['frase_para_el_cliente'], 'lugar': lugar, 'lugar_id': lugar_id}]
        estado['envio'] = {'lugar_id': lugar_id, 'lugar': lugar} if lugar_id else None
        if carrito and lugar_id:
            # Como el Worker: con algo en el carrito, ofrece sumarlo a la cotización (la página se lo pide a Odoo).
            estado['oferta_envio'] = True
            bloques.append({'tipo': 'texto', 'texto': '¿Te lo sumo a la cotización?'})
            return self._ok('mapa', bloques, ['Sí, súmalo a la cotización', 'No, gracias'])
        bloques.append({'tipo': 'sugerencias', 'texto': '¿Te explico las formas de pago?',
                        'opciones': ['Formas de pago', 'Hablar con una persona']})
        return self._ok('mapa', bloques)

    def _vendedor(self, estado, accion, carrito):
        """Lo que la página cuenta de Odoo (A2, A4) o que el visitante quitó algo (A3): textos fijos, sin cifras."""
        tipo = accion.get('tipo')
        if tipo == 'confirmar_envio':
            pendiente, estado['pendiente_envio'] = estado['pendiente_envio'], None
            if not pendiente or pendiente['lugar_id'] != accion.get('lugar_id'):
                return self._ok('asomado_burbuja', [{'tipo': 'texto', 'texto': 'Gracias. ¿Te ayudo con algo más?'}])
            if accion.get('resultado') == 'ok':
                return self._ok('bolsita', [
                    {'tipo': 'texto', 'texto': 'Listo, te lo sumé: el total lo ves en tu carrito y en la cotización.'},
                    {'tipo': 'sugerencias', 'texto': '¿Seguimos?', 'opciones': ['Formas de pago', 'Seguir viendo']}])
            return self._ok('burbuja_chat', [{'tipo': 'texto', 'texto': 'No pude sumar el envío ahorita, disculpa.'},
                                             self.WA])
        if tipo == 'confirmar_cambio':
            pendiente, estado['pendiente_cambio'] = estado['pendiente_cambio'], None
            if not pendiente or pendiente['producto_id'] != accion.get('producto_id'):
                return self._ok('asomado_burbuja', [{'tipo': 'texto', 'texto': 'Gracias. ¿Te ayudo con algo más?'}])
            linea = next((x for x in carrito if x.get('producto_id') == pendiente['producto_id']), None)
            real = linea['cantidad'] if linea else 0
            if accion.get('resultado') != 'ok' or (pendiente['cantidad'] == 0) != (real == 0):
                return self._ok('burbuja_chat', [{'tipo': 'texto', 'texto': 'No pude cambiar el carrito ahorita.'},
                                                 self.WA])
            if pendiente['cantidad'] < pendiente['antes']:
                estado['reaccion'] = True      # la alternativa ya se ofrece aquí: la reacción no se repite
            listo = (f'Listo, quité {pendiente["nombre"]} del carrito.' if real == 0 else
                     f'Listo, ahora tienes {real} × {pendiente["nombre"]} en el carrito.')
            return self._ok('bolsita', [{'tipo': 'texto', 'texto': listo},
                                        {'tipo': 'sugerencias', 'texto': '¿Te busco otra opción?',
                                         'opciones': ['Una más económica', 'Con más prestaciones']}])
        # carrito_bajo: una sola vez por sesión.
        if estado['reaccion']:
            return self._ok('asomado_burbuja', [])
        estado['reaccion'] = True
        nombre = str(accion.get('nombre') or '').strip()[:60]
        vista = estado['vistos'].get(accion.get('producto_id'))
        nombre = (vista or {}).get('nombre') or nombre
        if not carrito:
            texto = 'Vi que vaciaste el carrito. ¿Te ayudo a buscar otra opción, más económica o con más prestaciones?'
        elif accion.get('ahora') == 0:
            texto = f'Vi que quitaste {nombre}. ¿Te busco una opción más económica o una con más prestaciones?'
        else:
            texto = (f'Vi que bajaste la cantidad de {nombre}. Si quieres, te busco otra opción, más económica o con '
                     'más prestaciones.')
        return self._ok('corazon', [{'tipo': 'texto', 'texto': texto}],
                        ['Una más económica', 'Con más prestaciones', 'No, gracias'])

    def _cambio(self, estado, t, carrito):
        """«quita la cama», «déjame 2 colchones»: solo lo que ya está en el carrito (como el Worker)."""
        if not carrito:
            return None
        palabras = [w for w in re.findall(r'\w+', t) if len(w) >= 4]
        linea = next((x for x in carrito if any(w[:5] in x.get('nombre', '').lower() for w in palabras)), carrito[-1])
        numero = re.search(r'\b(\d{1,2})\b', t)
        cantidad = 0 if re.search(r'quit|saca|ya no', t) else int(numero.group(1)) if numero else None
        if cantidad is None or cantidad == linea.get('cantidad') or not linea.get('producto_id'):
            return None
        estado['pendiente_cambio'] = {'producto_id': linea['producto_id'], 'cantidad': cantidad,
                                      'nombre': linea['nombre'], 'antes': linea['cantidad']}
        return self._ok('bolsita', [
            {'tipo': 'texto', 'texto': 'Con gusto, ya lo cambio.'},
            {'tipo': 'proponer_cambio_carrito', 'producto_id': linea['producto_id'], 'cantidad': cantidad,
             'nombre': linea['nombre']}])

    def _buscar(self, estado, t, texto):
        consulta = ('colchón' if 'colch' in t else 'cama' if 'cama' in t else 'sofá' if ('sala' in t or 'sof' in t)
                    else texto)
        productos = [self._tarjeta(p) for p in self.herramienta('buscar_productos', {'consulta': consulta}).get(
            'productos') or []]
        for p in productos:
            if p.get('producto_id'):
                estado['vistos'][p['producto_id']] = p
        agregables = [p for p in productos if p.get('agregable')]
        estado['ultimo'] = agregables[0]['producto_id'] if agregables else None
        if not productos:
            return self._ok('con_laptop', [{'tipo': 'texto', 'texto': 'No encontré eso en la tienda en línea. ¿Te '
                                                                      'ayudo por WhatsApp?'}, self.WA])
        titulo = {'colchón': 'Colchones', 'cama': 'Camas', 'sofá': 'Salas'}.get(consulta)
        return self._ok('busto_estrella', [
            {'tipo': 'texto', 'texto': 'Encontré estos; los precios son + ITBMS.'},
            {'tipo': 'productos', 'productos': productos[:6], 'titulo': titulo},
            {'tipo': 'sugerencias', 'texto': '¿Te pongo alguno en el carrito?',
             'opciones': ['Sí, ponlo en el carrito', '¿Cuánto cuesta el envío?']}])

    def _guion(self, estado, t, texto, carrito=()):
        envio = estado.get('envio')
        if envio and ('súm' in t or 'sum' in t or (estado.get('oferta_envio') and t in ('sí', 'si', 'dale'))):
            estado['oferta_envio'] = False
            if not carrito:
                return self._ok('bolsita', [{'tipo': 'texto', 'texto': 'Para sumarte el envío, primero pon en el '
                                                                       'carrito lo que te gustó.'}])
            estado['pendiente_envio'] = envio
            return self._ok('bolsita', [{'tipo': 'texto', 'texto': 'Con gusto, te lo sumo a la cotización.'},
                                        {'tipo': 'sumar_envio', **envio}])
        if t.startswith(('no,', 'no ')) or t == 'no':
            estado['oferta_envio'] = False
            return self._ok('asomado_burbuja', [{'tipo': 'texto', 'texto': 'Perfecto, sin problema. ¿Te muestro algo '
                                                                           'más?'}])
        if re.search(r'\b(quita|quítal|quital|saca|ya no quiero|deja|déjame|dejame)', t):
            cambio = self._cambio(estado, t, list(carrito))
            if cambio:
                return cambio
        if 'envío a ' in t or 'envio a ' in t:
            lugar = re.split(r'env[ií]o a ', texto, maxsplit=1, flags=re.IGNORECASE)[-1].strip(' ¿?.')
            return self._envio(estado, self.herramienta('cotizar_envio', {'lugar': lugar}), list(carrito))
        if any(p in t for p in ('colch', 'sala', 'sofa', 'sofá', 'cama', 'busco', 'mesa')):
            return self._buscar(estado, t, texto)
        if any(p in t for p in ('ponlo', 'agrega', 'carrito')) and estado['ultimo']:
            p = estado['vistos'][estado['ultimo']]
            return self._ok('bolsita', [
                {'tipo': 'texto', 'texto': f'Con gusto. Te pongo 1 {p["nombre"]}.'},
                {'tipo': 'proponer_carrito', 'producto_id': p['producto_id'], 'cantidad': 1, 'nombre': p['nombre']}])
        if 'envío' in t or 'envio' in t or 'entrega' in t:
            return self._ok('mapa', [{'tipo': 'ubicacion', 'texto': 'Con gusto te lo calculo. ¿A dónde te lo '
                                                                    'llevamos?'}])
        if 'persona' in t or 'whatsapp' in t or 'vendedora' in t:
            return self._ok('burbuja_chat', [
                {'tipo': 'texto', 'texto': 'Claro que sí. Una persona del equipo te atiende por WhatsApp.'}, self.WA])
        if 'gracias' in t:
            return self._ok('cinco_estrellas', [
                {'tipo': 'texto', 'texto': 'Con mucho gusto. Si quieres, califica cómo te atendí.'},
                {'tipo': 'calificar'}])
        if 'pago' in t:
            return self._ok('bolsita', [{'tipo': 'texto', 'texto': 'Las formas de pago te las confirma una vendedora '
                                                                   'por WhatsApp.'}], ['Hablar con una persona'])
        return self._ok('saludando', [{'tipo': 'texto', 'texto': 'Gracias por escribirme. ¿Buscas un mueble, el costo '
                                                                 'del envío o las formas de pago?'}],
                        ['Colchones', 'Salas', '¿Cuánto cuesta el envío?'])

    # ------------------------------------------------------------------ HTTP

    def _manejador(self):
        worker = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _cors(self):
                origen = self.headers.get('Origin')
                if origen:
                    self.send_header('Access-Control-Allow-Origin', origen)
                    self.send_header('Vary', 'Origin')

            def _json(self, estado, datos):
                cuerpo = json.dumps(datos, ensure_ascii=False).encode()
                self.send_response(estado)
                self._cors()
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_GET(self):  # noqa: N802
                # Lo poco de «Odoo → Worker» que leen las pantallas (Costos de IA, Sitio web › Brian de la tienda): el
                # simulado no gasta IA, así que su gasto es $0 y sus respuestas, las que contestó de verdad.
                esquema, _, token = (self.headers.get('Authorization') or '').partition(' ')
                if esquema != 'Bearer' or not hmac.compare_digest(token, worker.token_worker):
                    self._json(401, {'ok': False, 'error': 'token'})
                    return
                mes = time.strftime('%Y-%m')
                if self.path == '/odoo/salud':
                    self._json(200, {'ok': True, 'mes': mes, 'gasto_ia_mes_usd': 0.0, 'tope_usd': 0, 'avisos': [],
                                     'ia': {'proveedor': 'simulado', 'claves_faltantes': [], 'modelos_sin_precio': []}})
                elif self.path == '/odoo/costos':
                    self._json(200, {'ok': True, 'mes': mes, 'turnos': 0, 'por_modelo': [], 'por_dia': [],
                                     'tienda': {'usd': 0.0, 'turnos': len(worker.recibidos), 'presupuesto_usd': 30,
                                                'por_modelo': []}})
                else:
                    self._json(404, {'ok': False})

            def do_OPTIONS(self):  # noqa: N802
                self.send_response(204)
                self._cors()
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                self.send_header('Access-Control-Max-Age', '600')
                self.end_headers()

            def do_POST(self):  # noqa: N802
                if self.path != '/tienda/v1/mensaje':
                    self._json(404, {'ok': False, 'motivo': 'fallo'})
                    return
                esquema, _, pase = (self.headers.get('Authorization') or '').partition(' ')
                payload = leer_pase(pase, worker.token_worker) if esquema == 'Pase' else None
                if not payload:
                    self._json(401, {'ok': False, 'motivo': 'pase'})
                    return
                largo = int(self.headers.get('Content-Length') or 0)
                try:
                    cuerpo = json.loads(self.rfile.read(min(largo, 16384)) or b'{}')
                except ValueError:
                    self._json(400, {'ok': False, 'motivo': 'fallo'})
                    return
                if len(cuerpo.get('texto') or '') > 500:
                    self._json(400, {'ok': False, 'motivo': 'fallo'})
                    return
                worker.recibidos.append({k: v for k, v in cuerpo.items() if k != 'ubicacion'})
                estado, datos = worker.responder(payload['sid'], cuerpo)
                self._json(estado, datos)

        return Manejador

    def iniciar(self):
        self.servidor = ThreadingHTTPServer(('127.0.0.1', self.puerto), self._manejador())
        self.puerto = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        return self.puerto

    def detener(self):
        if self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    argumentos.add_argument('--puerto', type=int, default=8787)
    argumentos.add_argument('--token-worker', required=True)
    argumentos.add_argument('--odoo', required=True)
    argumentos.add_argument('--token-odoo', required=True)
    a = argumentos.parse_args()
    worker = WorkerSimulado(a.token_worker, a.odoo, a.token_odoo, puerto=a.puerto)
    print(f'Worker simulado en http://127.0.0.1:{worker.iniciar()}', flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        worker.detener()


if __name__ == '__main__':
    main()
