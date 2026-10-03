"""Parámetros de seguridad (``ir.config_parameter``) y textos derivados.

Los fija ``docker/entrypoint.sh`` desde variables de entorno (sección «2e») o un
administrador en Ajustes › Técnico › Parámetros del sistema. Todos tienen un valor por
defecto prudente: sin parámetro, nada queda más abierto ni nadie queda fuera.

| Parámetro                           | Variable de entorno          | Por defecto  |
|-------------------------------------|------------------------------|--------------|
| dcasa_seguridad.2fa_obligatorio     | DCASA_2FA_OBLIGATORIO        | 0 (apagado)  |
| dcasa_seguridad.2fa_alcance         | DCASA_2FA_ALCANCE            | admins       |
| dcasa_seguridad.bloqueo_tope_s      | —                            | 1800 (30 min)|
| dcasa_seguridad.aviso_telegram      | DCASA_AVISO_LOGIN_TELEGRAM   | 1            |
| dcasa_seguridad.aviso_operacion     | DCASA_ALERTA_TELEGRAM        | 1            |
| dcasa_seguridad.robots_ia           | DCASA_ROBOTS_IA              | equilibrada  |
| grupo Administración/Ajustes        | DCASA_SESION_ADMIN_HORAS     | 12           |
|   (auth_timeout)                    | DCASA_INACTIVIDAD_ADMIN_MIN  | 60           |
"""
from odoo.tools import str2bool

PREFIJO = 'dcasa_seguridad.'

ALCANCES = ('admins', 'internos')

SESION_ADMIN_HORAS = 12
INACTIVIDAD_ADMIN_MIN = 60
BLOQUEO_TOPE_S = 30 * 60


def param(env, clave, defecto=None):
    return env['ir.config_parameter'].sudo().get_param(PREFIJO + clave, defecto)


def activo(env, clave, defecto=False):
    valor = param(env, clave)
    if valor in (None, False, ''):
        return defecto
    return str2bool(str(valor).strip().lower(), defecto)


def entero(env, clave, defecto):
    try:
        return max(0, int(param(env, clave, defecto)))
    except (TypeError, ValueError):
        return defecto


def aplicar_sesiones_admin(env, horas=SESION_ADMIN_HORAS, minutos=INACTIVIDAD_ADMIN_MIN):
    """Sesiones del grupo «Administración / Ajustes» (auth_timeout de Odoo).

    * ``horas``: cierre de sesión obligatorio a las N horas de entrar (pide clave y, si la
      tiene, el código de la app). 0 = sin cierre.
    * ``minutos``: bloqueo de pantalla tras N minutos sin actividad (pide la clave). 0 = sin
      bloqueo.
    Solo afecta a quien tiene ese grupo: vendedoras, socios y clientes del portal no cambian.
    """
    grupo = env.ref('base.group_system')
    grupo.write({
        'lock_timeout': max(0, int(horas)) * 60,
        'lock_timeout_mfa': bool(horas),
        'lock_timeout_inactivity': max(0, int(minutos)),
        'lock_timeout_inactivity_mfa': False,
    })


# ---------------------------------------------------------------------------------------
# robots.txt para rastreadores de IA
# ---------------------------------------------------------------------------------------
# Se separan los que ENTRENAN modelos con el contenido (no traen clientes) de los que
# buscan o responden en nombre de una persona (ChatGPT, Claude, Perplexity… pueden citar
# la tienda y mandar visitas). Googlebot, Bingbot y los previsualizadores de enlaces
# (facebookexternalhit, meta-externalfetcher, WhatsApp, Twitterbot) no se tocan nunca.
# robots.txt es una petición de buena fe: los que no la respetan se frenan en Cloudflare
# («Block AI bots», AI Crawl Control; ver docs/SEGURIDAD_ACCESO.md).
IA_ENTRENAMIENTO = (
    'GPTBot',
    'ClaudeBot',
    'anthropic-ai',
    'Google-Extended',
    'Applebot-Extended',
    'CCBot',
    'Bytespider',
    'Meta-ExternalAgent',
    'cohere-training-data-crawler',
    'Diffbot',
    'Omgilibot',
    'Timpibot',
    'ImagesiftBot',
    'PanguBot',
    'AI2Bot',
)
IA_BUSQUEDA = (
    'OAI-SearchBot',
    'ChatGPT-User',
    'Claude-SearchBot',
    'Claude-User',
    'PerplexityBot',
    'Perplexity-User',
    'DuckAssistBot',
    'MistralAI-User',
)
POLITICAS_ROBOTS = ('abierta', 'equilibrada', 'cerrada')
SENALES = {
    'abierta': 'search=yes, ai-input=yes, ai-train=yes',
    'equilibrada': 'search=yes, ai-input=yes, ai-train=no',
    'cerrada': 'search=yes, ai-input=no, ai-train=no',
}


def politica_robots(env):
    valor = (param(env, 'robots_ia') or 'equilibrada').strip().lower()
    return valor if valor in POLITICAS_ROBOTS else 'equilibrada'


def texto_robots_ia(politica):
    """Bloque que se agrega al final de /robots.txt según la política."""
    bloqueados = ()
    if politica in ('equilibrada', 'cerrada'):
        bloqueados += IA_ENTRENAMIENTO
    if politica == 'cerrada':
        bloqueados += IA_BUSQUEDA
    lineas = ['', f'# D’CASA: politica para rastreadores de IA ({politica})', '']
    for agente in bloqueados:
        lineas += [f'User-agent: {agente}', 'Disallow: /', '']
    lineas += ['User-agent: *', f'Content-Signal: {SENALES[politica]}', '']
    return '\n'.join(lineas)
