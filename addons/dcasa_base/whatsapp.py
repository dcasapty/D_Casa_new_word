"""El enlace que abre WhatsApp con el mensaje ya escrito (función pura, sin Odoo).

Siempre ``https://api.whatsapp.com/send?phone=<número>&text=<mensaje>`` (sin número: ``…/send?text=<mensaje>``), nunca
``wa.me``: ``wa.me`` redirige a esta misma dirección y en esa vuelta WhatsApp Web, el de la computadora y los
navegadores de adentro de Instagram y Messenger cambian los emojis por «�» (auditoría 2 de la ubicación, 2026-11-25).
Con ``api.whatsapp.com`` el mensaje llega como se escribió.

Lo usan el sitio (``website._dcasa_whatsapp_url``), la ubicación (avisos, «Avisar que llegué», el respaldo de la
página ``/u``) y el chat de la tienda (Andrés arma el mismo enlace en el navegador: ``brian_tienda.js``).
"""
from urllib.parse import parse_qs, quote, urlsplit

BASE = 'https://api.whatsapp.com/send'


def solo_digitos(numero):
    """Los dígitos del número (``'+507 6026-1919'`` → ``'50760261919'``), o ``''``."""
    return ''.join(c for c in str(numero or '') if c.isdigit())


def enlace(numero=None, texto=None):
    """``https://api.whatsapp.com/send?phone=<dígitos>&text=<mensaje>``; sin número, ``…/send?text=<mensaje>`` (la
    persona elige a quién se lo manda). El mensaje va entero (con sus emojis) y codificado para la dirección."""
    digitos = solo_digitos(numero)
    mensaje = 'text=' + quote(texto or '', safe='')
    return f'{BASE}?phone={digitos}&{mensaje}' if digitos else f'{BASE}?{mensaje}'


def es_enlace(url):
    """¿Es un enlace de WhatsApp armado con ``enlace``?"""
    return isinstance(url, str) and url.startswith(BASE + '?')


def numero_del_enlace(url):
    """El número de un enlace de ``enlace`` (``'50760261919'``), o ``''`` si no lleva o no es de WhatsApp."""
    if not es_enlace(url):
        return ''
    return solo_digitos((parse_qs(urlsplit(url).query).get('phone') or [''])[0])
