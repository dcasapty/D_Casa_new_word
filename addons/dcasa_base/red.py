"""La llave de una conexión para los topes por conexión (función pura, sin Odoo).

``llave_ip``: una IPv4, entera; una IPv6, su red /64 (lo que recibe UN cliente: cambiar de dirección dentro de ella no
da más turnos). Una IPv4 escrita como IPv6 (``::ffff:10.0.0.1``) es la IPv4. Lo que no es una dirección, tal cual.

Es la misma que tenía el enlace de los choferes (dcasa_envios/controllers/choferes.py, sin cambios de comportamiento) y
la usa también «Busca con una foto» (dcasa_buscar_foto). El borde hace lo mismo con su propia función
(edge/src/bots.ts, ``llaveDeIp``).
"""
import ipaddress


def llave_ip(ip):
    """La llave del límite: la IPv4 entera; de una IPv6, su red /64 (lo que recibe un solo cliente)."""
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return ip or '-'
    if direccion.version == 6:
        if direccion.ipv4_mapped:
            return str(direccion.ipv4_mapped)
        return str(ipaddress.ip_network(f'{direccion}/64', strict=False))
    return str(direccion)
