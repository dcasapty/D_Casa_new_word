"""«Brian de la tienda»: el pase que Odoo le da al navegador para hablar con el Worker de Juan (contrato §1).

El navegador NO habla con la IA a través de Odoo (una respuesta tarda de 3 a 20 s y ocuparía un hilo y una conexión de
la base todo ese tiempo): le pide a Odoo un pase corto y firmado y con él habla directo con el Worker
(``POST {JUAN_URL}/tienda/v1/mensaje``). Sin secretos nuevos: la llave sale de ``JUAN_WORKER_TOKEN``, que Odoo y el
Worker ya comparten (``llave = HMAC-SHA256(JUAN_WORKER_TOKEN, "brian-tienda-pase-v1")``, los 32 bytes crudos).

* ``pase = B64U(payload) + "." + B64U(HMAC-SHA256(llave, B64U(payload)))``, B64U = base64url sin «=».
* ``payload = {"v": 1, "sid", "exp", "red", "sitio"}``: ``sid`` vive en la sesión del visitante (el mismo navegador
  recibe el mismo), ``exp`` = ahora + 30 min y ``red`` = la red del visitante (IPv4 /24, IPv6 /64; formato exacto en
  ``red_de``). El Worker ya NO la compara con la conexión (contrato_cambios, «2026-11-13 (2)»: el navegador puede llegar
  a dcasapty.com por IPv6 y al Worker por IPv4); queda en el payload como dato.
* **Tope de pases por conexión** (20 por hora de fábrica): un contador por conexión (la IPv4 entera o la red /64 de la
  IPv6, ``conexion_de``; nunca la /24, que comparten muchos clientes del mismo operador) y por hora en
  ``dcasa.brian.tienda.cupo``,
  reservado DENTRO de la transacción del pase (si algo falla después, la reserva se deshace con ella) y bajo
  ``pg_advisory_xact_lock``. La lección de la búsqueda por foto (B1): contar filas y después insertar no aguanta dos
  pedidos a la vez. Aquí el contador es UNA fila que se actualiza con ``INSERT … ON CONFLICT DO UPDATE``: Odoo trabaja
  en REPEATABLE READ, así que el segundo pedido que llega a la vez espera el candado y, al ver que la fila cambió
  después de empezar su transacción, PostgreSQL le da un error de serialización y Odoo repite la petición entera (ya con
  la cuenta nueva). Nunca dos pedidos se llevan el mismo cupo.
* Una sesión que ya pidió un pase en esta hora no gasta otro cupo (abrir el chat en otra página o recargar no cuenta).
* Turnstile solo si el sitio ya lo tiene configurado (``website_cf_turnstile``: las dos claves puestas); hoy está
  apagado y el pase sale sin él.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time

from odoo import SUPERUSER_ID, api, fields, models
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)

ETIQUETA_LLAVE = b'brian-tienda-pase-v1'
VIDA_PASE_S = 1800
VERSION_PASE = 1

# Lo que vive en la sesión del visitante. No cambia la página que dibuja Odoo: dcasa_tienda_borde las tiene entre sus
# CLAVES_NEUTRAS y quien abrió el chat sigue recibiendo las páginas guardadas en el borde.
SESION_SID = 'dcasa_brian_sid'
SESION_HORA = 'dcasa_brian_hora'
SESION_VERIFICADO = 'dcasa_brian_verificado'
SESION_PDF = 'dcasa_brian_pdf'
SESION_CALIFICADO = 'dcasa_brian_calificado'
CLAVES_DE_SESION = (SESION_SID, SESION_HORA, SESION_VERIFICADO, SESION_PDF, SESION_CALIFICADO)

PARAM_ACTIVO = 'dcasa_brian_tienda.activo'
# Los dos interruptores de la noche (Sitio web › Brian de la tienda; data/parametros.xml, noupdate).
PARAM_AVISAR_CERRADO = 'dcasa_brian_tienda.avisar_cerrado'   # apagado de fábrica: saluda como de día
PARAM_DORMIR_DE_NOCHE = 'dcasa_brian_tienda.dormir_de_noche'  # encendido de fábrica: el robot de la burbuja duerme
SI = ('1', 'true', 'yes', 'si', 'sí')
PARAMS = {
    'presupuesto_mes_usd': 'dcasa_brian_tienda.presupuesto_mes_usd',
    'tope_sesion_hora': 'dcasa_brian_tienda.tope_sesion_hora',
    'tope_red_hora': 'dcasa_brian_tienda.tope_red_hora',
    'tope_dia': 'dcasa_brian_tienda.tope_dia',
    'tope_pases_red_hora': 'dcasa_brian_tienda.tope_pases_red_hora',
}
# De fábrica (contrato §2 y §5). El presupuesto, 30 USD al mes «sin margen extra». Se cambian en Sitio web › Brian de
# la tienda (Gerencia y administradores).
DE_FABRICA = {
    'presupuesto_mes_usd': 30,
    'tope_sesion_hora': 20,
    'tope_red_hora': 60,
    'tope_dia': 1000,
    'tope_pases_red_hora': 20,
}
MAXIMOS = {
    'presupuesto_mes_usd': 1000,
    'tope_sesion_hora': 200,
    'tope_red_hora': 2000,
    'tope_dia': 20000,
    'tope_pases_red_hora': 2000,
}
# Verificado por Turnstile, la sesión no lo vuelve a pedir en este tiempo.
VERIFICADO_S = 1800


def b64u(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode('ascii')


def de_b64u(texto):
    return base64.urlsafe_b64decode(texto + '=' * (-len(texto) % 4))


def red_de(ip):
    """La red del visitante, como la escriben Odoo y el Worker (contrato_cambios §2). ``None`` si no es una IP.

    IPv4 → ``a.b.c.0/24``. IPv6 → los cuatro primeros grupos en hexadecimal sin ceros a la izquierda + ``::/64``, SIN
    comprimir (``2001:db8:0:0::/64``). Una IPv4 escrita como IPv6 (``::ffff:1.2.3.4``) cuenta como IPv4."""
    try:
        direccion = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return None
    if direccion.version == 6 and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    crudo = direccion.packed
    if direccion.version == 4:
        return f'{crudo[0]}.{crudo[1]}.{crudo[2]}.0/24'
    grupos = [format(int.from_bytes(crudo[i:i + 2], 'big'), 'x') for i in range(0, 8, 2)]
    return ':'.join(grupos) + '::/64'


def conexion_de(ip):
    """La conexión que cuenta para el tope de pases: la IPv4 entera o la red /64 de la IPv6 (una IPv4 escrita como IPv6
    cuenta como IPv4), igual que el borde, la búsqueda por foto y el tope por red del Worker. ``None`` si no es IP."""
    try:
        direccion = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return None
    if direccion.version == 6 and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    return str(direccion) if direccion.version == 4 else red_de(str(direccion))


def llave_de(token):
    """Los 32 bytes de la llave del pase (nunca se guardan ni se escriben en un registro)."""
    return hmac.new(token.encode('utf-8'), ETIQUETA_LLAVE, hashlib.sha256).digest()


def firmar(payload, token):
    cuerpo = b64u(json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode('ascii'))
    firma = hmac.new(llave_de(token), cuerpo.encode('ascii'), hashlib.sha256).digest()
    return f'{cuerpo}.{b64u(firma)}'


def leer_pase(pase, token, ahora=None):
    """El payload si la firma es buena y no venció; si no, ``None``. Lo usan las pruebas y el Worker simulado; el Worker
    de verdad hace lo mismo en TypeScript."""
    if not isinstance(pase, str) or pase.count('.') != 1 or not token:
        return None
    cuerpo, firma = pase.split('.')
    esperada = b64u(hmac.new(llave_de(token), cuerpo.encode('ascii'), hashlib.sha256).digest())
    if not hmac.compare_digest(firma, esperada):
        return None
    try:
        payload = json.loads(de_b64u(cuerpo))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get('v') != VERSION_PASE:
        return None
    if not isinstance(payload.get('exp'), int) or payload['exp'] < (ahora or time.time()):
        return None
    return payload


class DcasaBrianTienda(models.AbstractModel):
    _name = 'dcasa.brian.tienda'
    _description = 'Andrés (chat de la tienda): pase, ajustes y carrito'

    # ------------------------------------------------------------------
    # Ajustes (ir.config_parameter; Sitio web › Brian de la tienda)
    # ------------------------------------------------------------------

    @api.model
    def _activo(self):
        """Encendido de fábrica (data/parametros.xml, noupdate). Apagado: sin burbuja, sin pases, el Worker se calla."""
        return self._interruptor(PARAM_ACTIVO, False)

    @api.model
    def _avisar_cerrado(self):
        """Fuera del horario, ¿el chat avisa que la tienda está cerrada? Apagado de fábrica: saluda como de día."""
        return self._interruptor(PARAM_AVISAR_CERRADO, False)

    @api.model
    def _dormir_de_noche(self):
        """De noche, ¿el robot de la burbuja duerme? Encendido de fábrica."""
        return self._interruptor(PARAM_DORMIR_DE_NOCHE, True)

    @api.model
    def _interruptor(self, parametro, de_fabrica):
        valor = self.env['ir.config_parameter'].sudo().get_param(parametro)
        if valor is None or valor is False or str(valor).strip() == '':
            return de_fabrica
        return str(valor).strip().lower() in SI

    @api.model
    def _ajustes(self):
        """Los números vigentes: lo que puso Gerencia o, si falta o no es un número, los de fábrica (nunca sin tope)."""
        Parametro = self.env['ir.config_parameter'].sudo()
        valores = {}
        for clave, parametro in PARAMS.items():
            try:
                valor = int(Parametro.get_param(parametro) or DE_FABRICA[clave])
            except (TypeError, ValueError):
                valor = DE_FABRICA[clave]
            valores[clave] = min(max(valor, 0), MAXIMOS[clave])
        return valores

    @api.model
    def _para_el_worker(self):
        """La clave ``brian_tienda`` de ``GET /dcasa/juan/v1/config`` (contrato_cambios §3)."""
        ajustes = self._ajustes()
        return {
            'activo': self._activo(),
            'avisar_cerrado': self._avisar_cerrado(),
            'presupuesto_mes_usd': ajustes['presupuesto_mes_usd'],
            'tope_sesion_hora': ajustes['tope_sesion_hora'],
            'tope_red_hora': ajustes['tope_red_hora'],
            'tope_dia': ajustes['tope_dia'],
        }

    # ------------------------------------------------------------------
    # Turnstile (solo si el sitio ya lo tiene)
    # ------------------------------------------------------------------

    @api.model
    def _turnstile_clave_publica(self):
        """La clave pública de Turnstile si el sitio lo tiene configurado (las dos claves); si no, ``''``."""
        Parametro = self.env['ir.config_parameter'].sudo()
        publica = (Parametro.get_param('cf.turnstile_site_key') or '').strip()
        secreta = (Parametro.get_param('cf.turnstile_secret_key') or '').strip()
        if not (publica and secreta) or not hasattr(self.env['ir.http'], '_verify_turnstile_token'):
            return ''
        return publica

    @api.model
    def _verificar_turnstile(self, token, ip):
        """``True`` si Turnstile no está configurado o el token es bueno (lo comprueba ``website_cf_turnstile``)."""
        if not self._turnstile_clave_publica():
            return True
        if not isinstance(token, str) or not token or len(token) > 4096:
            return False
        resultado = self.env['ir.http']._verify_turnstile_token(ip, token, False)
        return resultado in ('is_human', 'no_secret')

    # ------------------------------------------------------------------
    # El tope de pases por red (contador reservado bajo candado)
    # ------------------------------------------------------------------

    @api.model
    def _huella(self, valor):
        """HMAC con el secreto de la base: cuenta sin guardar la red de nadie."""
        secreto = self.env['ir.config_parameter'].sudo().get_param('database.secret') or self.env.cr.dbname
        return hmac.new(secreto.encode(), f'brian-tienda:{valor}'.encode(), hashlib.sha256).hexdigest()[:32]

    @api.model
    def _reservar(self, llave, tope, ahora=None):
        """Suma 1 al contador de ``llave`` en esta hora y dice si cabe (``cuenta <= tope``). ``tope`` 0 = cerrado.

        La fila se reserva en la transacción de quien llama: si después algo falla, se deshace con ella. Bajo
        ``pg_advisory_xact_lock`` por llave y con ``INSERT … ON CONFLICT DO UPDATE`` (ver el docstring del módulo): dos
        pedidos a la vez de la misma red nunca se llevan el mismo cupo."""
        ahora = ahora or fields.Datetime.now()
        ventana = ahora.replace(minute=0, second=0, microsecond=0)
        cr = self.env.cr
        cr.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', [f'dcasa_brian_tienda.cupo:{llave}'])
        cr.execute("""
            INSERT INTO dcasa_brian_tienda_cupo (llave, ventana, cuenta)
                 VALUES (%(llave)s, %(ventana)s, 1)
            ON CONFLICT (llave) DO UPDATE
                    SET cuenta = CASE WHEN dcasa_brian_tienda_cupo.ventana = EXCLUDED.ventana
                                      THEN dcasa_brian_tienda_cupo.cuenta + 1 ELSE 1 END,
                        ventana = EXCLUDED.ventana
              RETURNING cuenta""", {'llave': llave, 'ventana': ventana})
        cuenta = cr.fetchone()[0]
        return cuenta <= tope

    @api.model
    def _reservar_confirmado(self, llave, tope):
        """Como ``_reservar``, pero en una transacción PROPIA y corta que se confirma al salir: cuenta aunque lo que
        venga después falle, y el cerrojo no queda tomado mientras dura (p. ej. un PDF). En READ COMMITTED: el segundo
        pedido que espera el cerrojo ve la cuenta del primero (en REPEATABLE READ la foto de la base se tomaría antes de
        esperar). En las pruebas la transacción es la de la prueba (``TestCursor``): ahí no se cambia el aislamiento."""
        with self.env.registry.cursor() as cr:
            if isinstance(cr, Cursor):
                cr.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            return api.Environment(cr, SUPERUSER_ID, {})['dcasa.brian.tienda']._reservar(llave, tope)

    # ------------------------------------------------------------------
    # El pase
    # ------------------------------------------------------------------

    @api.model
    def _sid(self, sesion):
        """El ``sid`` de este navegador (16 bytes al azar en base64url), el mismo mientras dure su sesión."""
        sid = sesion.get(SESION_SID)
        if not isinstance(sid, str) or len(sid) != 22:
            sid = b64u(secrets.token_bytes(16))
            sesion[SESION_SID] = sid
        return sid

    @api.model
    def _emitir(self, sesion, ip, website, turnstile=None):
        """``{ok, …}`` del contrato §1. ``sesion`` es la del visitante (``request.session``)."""
        if not self._activo():
            return {'ok': False, 'motivo': 'apagado'}
        Ajustes = self.env['dcasa.juan.ajustes']
        token = Ajustes.token_worker()
        url = Ajustes.url_worker()
        if not token or not url or not self.env['dcasa.juan.cliente']._url_valida(url):
            # Sin Worker conectado no hay con quién hablar: lo mismo que apagado para el visitante.
            _logger.info('Brian de la tienda: sin JUAN_URL o JUAN_WORKER_TOKEN; no se da el pase.')
            return {'ok': False, 'motivo': 'apagado'}
        red = red_de(ip)
        if not red:
            return {'ok': False, 'motivo': 'verificacion'}
        ahora = fields.Datetime.now()
        hora = ahora.strftime('%Y-%m-%d %H')
        verificado = sesion.get(SESION_VERIFICADO)
        if not (isinstance(verificado, (int, float)) and time.time() - verificado < VERIFICADO_S):
            if not self._verificar_turnstile(turnstile, ip):
                return {'ok': False, 'motivo': 'verificacion'}
            if self._turnstile_clave_publica():
                sesion[SESION_VERIFICADO] = int(time.time())
        if sesion.get(SESION_HORA) != hora:
            if not self._reservar(f'red:{self._huella(conexion_de(ip))}', self._ajustes()['tope_pases_red_hora'],
                                  ahora):
                _logger.info('Brian de la tienda: una conexión llegó al tope de pases de esta hora.')
                return {'ok': False, 'motivo': 'tope'}
            sesion[SESION_HORA] = hora
        exp = int(time.time()) + VIDA_PASE_S
        payload = {'v': VERSION_PASE, 'sid': self._sid(sesion), 'exp': exp, 'red': red, 'sitio': website.id}
        horario = Ajustes.obtener().horario()
        return {
            'ok': True,
            'pase': firmar(payload, token),
            'worker': url,
            'vence_en': VIDA_PASE_S,
            # La verdad (fuera del horario) y si hay que decirla: el saludo lo decide la página con los dos.
            'noche': not H.dentro_de_horario(ahora, horario),
            'avisar_cerrado': self._avisar_cerrado(),
            'horario_texto': horario.texto()[:1].lower() + horario.texto()[1:],
        }

