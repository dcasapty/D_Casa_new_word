"""Motor de envíos de D'CASA: la fórmula de la tarifa y el buscador de lugares, SIN Odoo.

Es la única fuente de verdad del precio de un envío. Lo usan la pantalla interna (por RPC), la herramienta
``cotizar_envio`` de Brian y, el día que se encienda, la página web y Juan. Nada aquí importa Odoo: se puede probar y
usar desde cualquier programa de Python (``tests/test_motor.py`` lo prueba sin base de datos).

Es un puerto fiel del HTML que Gerencia aprobó como propuesta (``envios-dcasa.html``, 2026-11-04): mismas palabras,
mismos pesos y mismos redondeos, también los de JavaScript (``Math.round``, ``toFixed`` y los números con el formato de
Panamá). Ver docs/ENVIOS.md.

* :mod:`.texto` — números y dinero como los escribe el navegador.
* :mod:`.tarifa` — la fórmula (salida + por km, mínimo, redondeo, ajuste en %, cargos aparte) y los tramos.
* :mod:`.buscador` — el índice de lugares y la búsqueda (sinónimos, abreviaturas, errores de dedo, frases).
* :mod:`.tarjeta` — lo que se muestra de un lugar: chips, zona, precio, desglose y el texto para el cliente.
* :mod:`.archivo` — leer el archivo de Gerencia (el HTML o su JSON) y la llave estable de cada lugar.
"""
from . import archivo, buscador, tarifa, tarjeta, texto  # noqa: F401
