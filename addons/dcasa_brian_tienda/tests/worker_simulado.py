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
"""
import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
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
        estado = self.sesiones.setdefault(sid, {'vistos': {}, 'ultimo': None})
        texto = (cuerpo.get('texto') or '').strip()
        accion = cuerpo.get('accion') or {}
        if accion.get('tipo') == 'chip':
            texto = str(accion.get('valor') or '')
        t = texto.lower()
        if t in ERRORES:
            return ERRORES[t], {'ok': False, 'motivo': t}
        if cuerpo.get('ubicacion'):
            return self._ubicacion(cuerpo['ubicacion'])
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
        return self._guion(estado, t, texto)

    def _ubicacion(self, u):
        self.ubicaciones += 1
        envio = self.herramienta('cotizar_envio', {'lat': u.get('lat'), 'lon': u.get('lon')})
        lugar = (envio.get('lugar') or {}).get('nombre') or ''
        if envio.get('estado') == 'precio':
            return self._ok('mapa', [
                {'tipo': 'texto', 'texto': f'Gracias. Por tu ubicación, te lo llevamos a {lugar}.'},
                {'tipo': 'envio', 'texto': envio['frase_para_el_cliente'], 'lugar': lugar},
                {'tipo': 'sugerencias', 'texto': '¿Te explico las formas de pago?',
                 'opciones': ['Formas de pago', 'Hablar con una persona']}])
        frase = envio.get('frase_para_el_cliente') or '¿Me dices el barrio o un punto de referencia?'
        return self._ok('mapa', [{'tipo': 'texto', 'texto': frase}])

    def _buscar(self, estado, t, texto):
        consulta = 'colchón' if 'colch' in t else 'sofá' if ('sala' in t or 'sof' in t) else texto
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
        return self._ok('busto_estrella', [
            {'tipo': 'texto', 'texto': 'Encontré estos; los precios son + ITBMS.'},
            {'tipo': 'productos', 'productos': productos[:6]},
            {'tipo': 'sugerencias', 'texto': '¿Te pongo alguno en el carrito?',
             'opciones': ['Sí, ponlo en el carrito', '¿Cuánto cuesta el envío?']}])

    def _guion(self, estado, t, texto):
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
