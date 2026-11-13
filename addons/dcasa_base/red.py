"""Direcciones de red para los topes por conexión (funciones puras, sin Odoo).

* ``llave_ip``: la llave de un tope por conexión. Una IPv4, entera; una IPv6, su red /64 (lo que recibe UN cliente:
  cambiar de dirección dentro de ella no da más turnos). Una IPv4 escrita como IPv6 (``::ffff:10.0.0.1``) es la IPv4.
* ``red_truncada``: la red a la que pertenece una dirección (/24 en IPv4, /64 en IPv6), para guardar una huella que no
  apunte a una casa en particular.

La usan el enlace de los choferes (dcasa_envios) y «Busca con una foto» (dcasa_buscar_foto). El borde hace lo mismo con
su propia función (edge/src/bots.ts, ``llaveDeIp``).
"""
import ipaddress


def _direccion(ip):
    try:
        direccion = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return None
    if direccion.version == 6 and direccion.ipv4_mapped:
        return direccion.ipv4_mapped
    return direccion


def llave_ip(ip):
    """La llave del límite: la IPv4 entera; de una IPv6, su red /64 (lo que recibe un solo cliente)."""
    direccion = _direccion(ip)
    if direccion is None:
        return ip or '-'
    if direccion.version == 6:
        return str(ipaddress.ip_network(f'{direccion}/64', strict=False))
    return str(direccion)


def red_truncada(ip, v4=24, v6=64):
    """La red de la dirección (``10.20.30.0/24``, ``2001:db8:1:2::/64``); ``'-'`` si no es una dirección."""
    direccion = _direccion(ip)
    if direccion is None:
        return '-'
    prefijo = v6 if direccion.version == 6 else v4
    return str(ipaddress.ip_network(f'{direccion}/{prefijo}', strict=False))
