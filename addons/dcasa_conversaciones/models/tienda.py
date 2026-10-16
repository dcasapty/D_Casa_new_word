"""Datos verificados de la tienda (dirección, horario, WhatsApp, cómo llegar), sacados de donde ya viven.

Una sola fuente para la herramienta ``horario_y_tienda`` y para la entrada automática de conocimiento
«Dónde estamos»: la dirección sale de la empresa (``dcasa_base``), el WhatsApp del sitio (``website_dcasa``) y
el horario de los ajustes de Juan. Si la dueña cambia cualquiera de ellos, el asistente lo dice al día.
"""
from odoo.addons.website_dcasa.models.website import LATITUD, LONGITUD


def website_publico(env):
    return env['website'].sudo().search([], order='sequence, id', limit=1)


def url_base(env, website=None):
    website = website if website is not None else website_publico(env)
    base = website._dcasa_url_publica() if website else ''
    return (base or env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')


def datos_tienda(env):
    """``{tienda, direccion, como_llegar, horario, whatsapp, correo, sitio}`` con lo que ya está en Odoo."""
    ajustes = env['dcasa.juan.ajustes'].obtener()
    horario = ajustes.horario()
    empresa = env.company.sudo()
    website = website_publico(env)
    base = url_base(env, website)
    direccion = ', '.join(p for p in (empresa.street, empresa.street2, empresa.city, 'Panamá Oeste') if p)
    telefono = (website.dcasa_whatsapp_number if website and website.dcasa_whatsapp_number else empresa.phone) or ''
    mapa = f'https://www.google.com/maps/dir/?api=1&destination={LATITUD}%2C{LONGITUD}'
    return {
        'tienda': empresa.name,
        'direccion': direccion,
        'como_llegar': f'{direccion}. Ruta en Google Maps: {mapa}. Más datos en {base}/visitanos.',
        'horario': {
            'texto': f'{horario.texto()} (hora de Panamá)',
            **horario.como_json(),
        },
        'whatsapp': telefono,
        'correo': empresa.email or '',
        'sitio': base,
    }


def texto_tienda(datos):
    """Los mismos datos como párrafos para la base de conocimiento."""
    lineas = [
        f"{datos['tienda']} está en {datos['direccion']}.",
        f"Cómo llegar: {datos['como_llegar']}",
        f"El equipo atiende {datos['horario']['texto'][0].lower() + datos['horario']['texto'][1:]}. "
        'Juan te contesta por mensaje a cualquier hora.',
    ]
    if datos['whatsapp']:
        lineas.append(f"WhatsApp: {datos['whatsapp']}.")
    if datos['correo']:
        lineas.append(f"Correo: {datos['correo']}.")
    return '\n'.join(lineas)
