"""Un freno de ritmo por conexión, en memoria y sin Odoo (se prueba solo).

Para ``/payment/tilopay/*`` (el retorno del cliente y el aviso del servidor): el borde no frena esas rutas y el contador
del Worker es aproximado, así que el freno va aquí, en Odoo. Es GENEROSO a propósito: los avisos de Tilopay vienen de
pocas direcciones y no pueden toparse con él; solo corta a quien martilla.

La llave de la conexión es la de ``dcasa_base.red.llave_ip`` (la IPv4 entera; de una IPv6, su red /64), la misma de
«Busca con una foto». Vive en la memoria del proceso (``workers = 0``: un solo proceso); si algún día hubiera varios,
cada uno cuenta aparte y el freno sigue acotando. Nada se guarda en la base, y no se guarda la dirección más de un
minuto (solo la llave y las horas de los últimos intentos).
"""
import threading
import time
from collections import deque


class LimiteDeRitmo:
    """``maximo`` intentos por ``ventana`` segundos para cada llave. ``permitir`` cuenta el intento si cabe; si no, no.

    Acota su propia memoria: nunca guarda más de ``max_llaves`` llaves (si se llena, suelta las más viejas)."""

    def __init__(self, maximo, ventana, max_llaves=4000):
        self.maximo = maximo
        self.ventana = ventana
        self.max_llaves = max_llaves
        self._intentos = {}
        self._candado = threading.Lock()

    def permitir(self, llave, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        corte = ahora - self.ventana
        with self._candado:
            cola = self._intentos.get(llave)
            if cola is None:
                if len(self._intentos) >= self.max_llaves:
                    self._soltar_las_viejas(corte)
                cola = self._intentos[llave] = deque()
            while cola and cola[0] <= corte:
                cola.popleft()
            if len(cola) >= self.maximo:
                return False
            cola.append(ahora)
            return True

    def _soltar_las_viejas(self, corte):
        for llave in [k for k, cola in self._intentos.items() if not cola or cola[-1] <= corte]:
            del self._intentos[llave]
        if len(self._intentos) >= self.max_llaves:        # todas siguen activas: se sueltan las que llevan más callando
            viejas = sorted(self._intentos, key=lambda k: self._intentos[k][-1])[:self.max_llaves // 4 or 1]
            for llave in viejas:
                del self._intentos[llave]

    def olvidar(self):
        """Vacía la memoria (las pruebas)."""
        with self._candado:
            self._intentos.clear()
