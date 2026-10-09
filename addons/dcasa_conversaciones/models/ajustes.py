"""Ajustes de Juan: un solo registro (singleton) que edita la dueña.

Los valores por defecto son las decisiones de la dueña (docs/JUAN.md y
docs/auditoria/ronda7/crm-whatsapp.md, «Decisiones de la dueña»): atiende 24/7, nombre público
«el equipo de D'CASA», seguimiento a las 5 h y a los 5 días (máximo 2, solo en horario laboral),
horario laboral de 8:00 a 17:00 todos los días (hora de Panamá), tope de IA de 30 USD al mes.

Los SECRETOS (``JUAN_ODOO_TOKEN``, ``JUAN_WORKER_TOKEN``) no se guardan aquí: viven en variables
de entorno del contenedor (o, como alternativa, en parámetros del sistema) y esta pantalla solo
dice si están puestos, nunca los muestra.
"""
import logging
import os

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from . import horario as H

_logger = logging.getLogger(__name__)

CANALES = [
    ('whatsapp_qr', 'WhatsApp (QR)'),
    ('whatsapp_cloud', 'WhatsApp (API oficial)'),
    ('telegram', 'Telegram'),
    ('messenger', 'Messenger'),
    ('instagram', 'Instagram'),
]
# Dónde se enciende cada canal. WhatsApp por QR y Telegram (pruebas y avisos) arrancan prendidos;
# la API oficial de WhatsApp (plan B), Messenger e Instagram quedan apagados hasta que se activen.
CANALES_PRENDIDOS = {'whatsapp_qr', 'telegram'}

# Los canales cuyo id externo es un celular (E.164 sin «+»).
CANALES_CON_CELULAR = {'whatsapp_qr', 'whatsapp_cloud'}

DIAS_CAMPOS = [
    ('dia_domingo', 0), ('dia_lunes', 1), ('dia_martes', 2), ('dia_miercoles', 3),
    ('dia_jueves', 4), ('dia_viernes', 5), ('dia_sabado', 6),
]

PARAM_URL = 'dcasa_conversaciones.juan_url'
PARAM_TOKEN_ODOO = 'dcasa_conversaciones.juan_odoo_token'
PARAM_TOKEN_WORKER = 'dcasa_conversaciones.juan_worker_token'
ENV_URL = 'JUAN_URL'
ENV_TOKEN_ODOO = 'JUAN_ODOO_TOKEN'
ENV_TOKEN_WORKER = 'JUAN_WORKER_TOKEN'
LARGO_MINIMO_TOKEN = 32

PROVEEDORES_IA = [('anthropic', 'Anthropic (Claude)'), ('meta', 'Meta (Muse Spark)'), ('openai', 'OpenAI')]
# Modelos por defecto (rápido, inteligente) de cada proveedor. OpenAI queda vacío a propósito: no se inventa un
# nombre de modelo; la dueña lo escribe (y el formulario no deja guardar sin él).
MODELOS_POR_PROVEEDOR = {
    'anthropic': ('claude-haiku-4-5', 'claude-sonnet-5-5'),
    'meta': ('muse-spark-1.3', 'muse-spark-1.3'),
    'openai': ('', ''),
}
NIVELES_IA = ('rapido', 'inteligente')
TIPOS_PRECIO = ('entrada', 'salida', 'cache')
MAX_LECCIONES = 20
MAX_LARGO_LECCION = 300

BIENVENIDA = (
    "Hola, soy el asistente automático del equipo de D'CASA. Te ayudo con camas, colchones y muebles, "
    "y con el programa Socios. Si prefieres hablar con una persona, escríbeme *persona* y te atiende "
    "una vendedora."
)
PRIVACIDAD = (
    "Esta conversación la atiende un asistente automático con inteligencia artificial, y lo que "
    "escribes se envía a nuestro proveedor de IA y a WhatsApp o la red por la que nos escribes para "
    "poder responderte. Se guarda en el sistema de D'CASA mientras seas cliente. Puedes pedir una "
    "persona o que borremos tus datos cuando quieras. Más en dcasapty.com/privacidad."
)
PALABRAS_PROHIBIDAS = "remate\ncorre\n¡¡\n!!"


class JuanAjustes(models.Model):
    _name = 'dcasa.juan.ajustes'
    _description = 'Ajustes de Juan (conversaciones con clientes)'
    _inherit = ['mail.thread']
    _rec_name = 'nombre_publico'

    nombre_publico = fields.Char(
        'Nombre público', required=True, default="el equipo de D'CASA", tracking=True,
        help="Cómo se presenta el asistente ante los clientes. «Juan» es solo el nombre interno.")

    # --- Encendido -----------------------------------------------------------------------------
    bot_activo_global = fields.Boolean(
        'Asistente encendido', default=True, tracking=True,
        help='Apágalo para que el asistente no conteste a nadie (las vendedoras siguen atendiendo).')
    canal_whatsapp_qr = fields.Boolean('WhatsApp (QR)', default=True, tracking=True)
    canal_whatsapp_cloud = fields.Boolean('WhatsApp (API oficial)', default=False, tracking=True)
    canal_telegram = fields.Boolean('Telegram', default=True, tracking=True)
    canal_messenger = fields.Boolean('Messenger', default=False, tracking=True)
    canal_instagram = fields.Boolean('Instagram', default=False, tracking=True)

    # --- Horario laboral (hora de Panamá) -------------------------------------------------------
    horario_inicio = fields.Float('Desde', default=8.0, tracking=True, help='Hora a la que empieza el horario laboral.')
    horario_fin = fields.Float('Hasta', default=17.0, tracking=True, help='Hora a la que termina el horario laboral.')
    dia_domingo = fields.Boolean('Domingo', default=True)
    dia_lunes = fields.Boolean('Lunes', default=True)
    dia_martes = fields.Boolean('Martes', default=True)
    dia_miercoles = fields.Boolean('Miércoles', default=True)
    dia_jueves = fields.Boolean('Jueves', default=True)
    dia_viernes = fields.Boolean('Viernes', default=True)
    dia_sabado = fields.Boolean('Sábado', default=True)
    zona_horaria = fields.Char('Zona horaria', default=H.ZONA_PANAMA, readonly=True)

    # --- Seguimiento ------------------------------------------------------------------------------
    seguimiento_primero_horas = fields.Float(
        'Primer seguimiento (horas)', default=5.0,
        help='Horas después del último mensaje, si la persona preguntó y no volvió a escribir.')
    seguimiento_segundo_dias = fields.Float(
        'Segundo seguimiento (días)', default=5.0,
        help='Días después del primer seguimiento, si sigue sin responder.')
    seguimiento_solo_horario_laboral = fields.Boolean(
        'Solo en horario laboral', default=True,
        help='Si le toca fuera del horario laboral, espera al siguiente horario laboral.')
    seguimiento_maximo = fields.Integer(
        'Máximo de seguimientos', default=2, tracking=True,
        help='Como máximo cuántos mensajes de seguimiento recibe una persona.')

    # --- IA ---------------------------------------------------------------------------------------
    proveedor_ia = fields.Selection(
        PROVEEDORES_IA, 'Proveedor de IA', default='anthropic', required=True, tracking=True,
        help='Quién pone el modelo que conversa con los clientes. Las claves de acceso NO se guardan en Odoo: '
             'viven solo en el Worker de Juan.')
    proveedor_respaldo_ia = fields.Selection(
        PROVEEDORES_IA, 'Proveedor de respaldo', tracking=True,
        help='Opcional: si el proveedor principal falla, el Worker intenta con este.')
    presupuesto_ia_mensual_usd = fields.Float(
        'Tope de IA al mes (USD)', default=30.0, tracking=True,
        help='Al llegar, el asistente baja al modelo barato; nunca se queda sin contestar por dinero.')
    modelo_rapido = fields.Char('Modelo rápido (barato)', default='claude-haiku-4-5', tracking=True)
    modelo_inteligente = fields.Char('Modelo inteligente', default='claude-sonnet-5-5', tracking=True)
    aviso_contributor = fields.Boolean('Entrena con las conversaciones', compute='_compute_aviso_contributor')
    # Precios en dólares por millón de tokens. Vacío (0) = sin precio verificado: no se inventa ninguno.
    precio_rapido_entrada_usd_mtok = fields.Float('Rápido: entrada', digits=(12, 4), tracking=True)
    precio_rapido_salida_usd_mtok = fields.Float('Rápido: salida', digits=(12, 4), tracking=True)
    precio_rapido_cache_usd_mtok = fields.Float('Rápido: caché', digits=(12, 4), tracking=True)
    precio_inteligente_entrada_usd_mtok = fields.Float('Inteligente: entrada', digits=(12, 4), tracking=True)
    precio_inteligente_salida_usd_mtok = fields.Float('Inteligente: salida', digits=(12, 4), tracking=True)
    precio_inteligente_cache_usd_mtok = fields.Float('Inteligente: caché', digits=(12, 4), tracking=True)

    # --- Textos ------------------------------------------------------------------------------------
    mensaje_bienvenida = fields.Text('Mensaje de bienvenida', default=BIENVENIDA, translate=False)
    texto_privacidad_corto = fields.Text('Aviso de privacidad (corto)', default=PRIVACIDAD, translate=False)
    palabras_prohibidas = fields.Text(
        'Palabras prohibidas', default=PALABRAS_PROHIBIDAS,
        help='Una por línea. El asistente no las usa jamás.')
    lecciones_aprendidas = fields.Text(
        'Lecciones aprendidas', tracking=True,
        help=f'Una por línea, hasta {MAX_LECCIONES}. Lo que el asistente debe recordar siempre, p. ej. «cuando '
             'pregunten por X, haz Y». El Worker las suma a sus instrucciones.')
    pausa_por_defecto_minutos = fields.Integer(
        'Pausa al atender (minutos)', default=120, tracking=True,
        help='Cuánto calla el asistente cuando una vendedora toma una conversación o la pide. '
             'Cada mensaje de la vendedora la renueva. 0 = hasta que la devuelvan.')

    # --- Avisos -------------------------------------------------------------------------------------
    responsable_id = fields.Many2one(
        'res.users', 'Responsable por defecto', default=lambda self: self.env.ref('base.user_admin', False),
        domain=[('share', '=', False)],
        help='A quién se le asigna la actividad cuando el asistente pasa una conversación a una vendedora '
             'y nadie la tiene asignada.')
    usuarios_aviso_ids = fields.Many2many(
        'res.users', 'dcasa_juan_ajustes_aviso_rel', 'ajustes_id', 'user_id', string='Avisar por Telegram a',
        domain=[('share', '=', False)],
        help='Quienes reciben el aviso por Telegram cuando se pide una vendedora (necesitan haber vinculado '
             'su Telegram con Brian). Vacío: todas las personas de ventas con Telegram vinculado.')

    # --- Conexión con el Worker (sin secretos) ----------------------------------------------------------
    juan_url = fields.Char(
        'Dirección del Worker de Juan', compute='_compute_juan_url', inverse='_inverse_juan_url',
        help='URL base del Worker «juan» (https://…). Se guarda en el parámetro dcasa_conversaciones.juan_url '
             'o se toma de la variable JUAN_URL.')
    token_odoo_configurado = fields.Boolean('JUAN_ODOO_TOKEN puesto', compute='_compute_tokens')
    token_worker_configurado = fields.Boolean('JUAN_WORKER_TOKEN puesto', compute='_compute_tokens')

    _nombre_largo = models.Constraint(
        'CHECK(char_length(nombre_publico) > 0)', 'El nombre público no puede estar vacío.')

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def obtener(self):
        """El único registro de ajustes (lo crea con los valores por defecto si no existe)."""
        ajustes = self.sudo().search([], limit=1)
        return ajustes or self.sudo().create({})

    @api.model_create_multi
    def create(self, vals_list):
        if len(vals_list) > 1 or self.sudo().search_count([]):
            raise UserError(self.env._('Solo hay un registro de ajustes de Juan: edita el que ya existe.'))
        return super().create(vals_list)

    def unlink(self):
        raise UserError(self.env._('Los ajustes de Juan no se borran: se editan.'))

    @api.model
    def action_abrir(self):
        self.check_access('read')
        ajustes = self.obtener()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Ajustes de Juan'),
            'res_model': self._name,
            'res_id': ajustes.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------

    @api.constrains('horario_inicio', 'horario_fin', 'dia_domingo', 'dia_lunes', 'dia_martes', 'dia_miercoles',
                    'dia_jueves', 'dia_viernes', 'dia_sabado')
    def _check_horario(self):
        for registro in self:
            if not 0 <= registro.horario_inicio < 24 or not 0 < registro.horario_fin <= 24:
                raise ValidationError(self.env._('El horario va de 0:00 a 24:00.'))
            if registro.horario_fin >= 24:
                raise ValidationError(self.env._('El horario termina antes de las 24:00 (por ejemplo, 23:59).'))
            if not registro.horario_inicio < registro.horario_fin:
                raise ValidationError(self.env._('La hora de inicio tiene que ser anterior a la hora de fin.'))
            if not registro._dias():
                raise ValidationError(self.env._('Marca al menos un día de atención.'))

    @api.constrains('seguimiento_primero_horas', 'seguimiento_segundo_dias', 'seguimiento_maximo')
    def _check_seguimiento(self):
        for registro in self:
            if registro.seguimiento_primero_horas < 0 or registro.seguimiento_segundo_dias < 0:
                raise ValidationError(self.env._('Los tiempos de seguimiento no pueden ser negativos.'))
            if not 0 <= registro.seguimiento_maximo <= 2:
                raise ValidationError(self.env._(
                    'El seguimiento admite como máximo 2 mensajes (decisión de la dueña): pon 0, 1 o 2.'))

    @api.constrains('proveedor_ia', 'proveedor_respaldo_ia', 'modelo_rapido', 'modelo_inteligente')
    def _check_ia(self):
        for registro in self:
            if registro.proveedor_respaldo_ia and registro.proveedor_respaldo_ia == registro.proveedor_ia:
                raise ValidationError(self.env._('El proveedor de respaldo tiene que ser distinto del principal.'))
            for nivel in (registro.modelo_rapido, registro.modelo_inteligente):
                if not (nivel or '').strip() or len(nivel) > 100 or any(c.isspace() for c in nivel.strip()):
                    raise ValidationError(self.env._(
                        'Escribe el nombre del modelo rápido y del inteligente (una sola palabra, p. ej. '
                        'claude-haiku-4-5). Para OpenAI no hay uno por defecto: pon el que quieras usar.'))

    @api.constrains(*[f'precio_{n}_{t}_usd_mtok' for n in NIVELES_IA for t in TIPOS_PRECIO])
    def _check_precios(self):
        for registro in self:
            for nivel in NIVELES_IA:
                for tipo in TIPOS_PRECIO:
                    if registro[f'precio_{nivel}_{tipo}_usd_mtok'] < 0:
                        raise ValidationError(self.env._('Los precios de la IA no pueden ser negativos.'))

    @api.constrains('lecciones_aprendidas')
    def _check_lecciones(self):
        for registro in self:
            lecciones = registro.lista_lecciones()
            if len(lecciones) > MAX_LECCIONES:
                raise ValidationError(self.env._(
                    'Son demasiadas lecciones (%(n)s): el máximo es %(max)s. Junta o quita algunas.',
                    n=len(lecciones), max=MAX_LECCIONES))
            if any(len(leccion) > MAX_LARGO_LECCION for leccion in lecciones):
                raise ValidationError(self.env._(
                    'Cada lección admite hasta %s caracteres. Acórtala.', MAX_LARGO_LECCION))

    @api.constrains('presupuesto_ia_mensual_usd', 'pausa_por_defecto_minutos')
    def _check_numeros(self):
        for registro in self:
            if registro.presupuesto_ia_mensual_usd < 0:
                raise ValidationError(self.env._('El tope de IA no puede ser negativo.'))
            if registro.pausa_por_defecto_minutos < 0:
                raise ValidationError(self.env._('La pausa no puede ser negativa.'))

    # ------------------------------------------------------------------
    # Lectura (usada por la API y por el resto del módulo)
    # ------------------------------------------------------------------

    def _dias(self):
        self.ensure_one()
        return frozenset(dia for campo, dia in DIAS_CAMPOS if self[campo])

    @api.private
    def horario(self):
        """El horario laboral como objeto puro (ver ``horario.py``)."""
        self.ensure_one()
        return H.Horario(
            inicio=H.float_a_hora(self.horario_inicio), fin=H.float_a_hora(self.horario_fin),
            dias=self._dias(), zona=self.zona_horaria or H.ZONA_PANAMA)

    @api.private
    def regla_seguimiento(self):
        self.ensure_one()
        return H.ReglaSeguimiento(
            primero_horas=self.seguimiento_primero_horas, segundo_dias=self.seguimiento_segundo_dias,
            solo_horario_laboral=self.seguimiento_solo_horario_laboral, maximo=self.seguimiento_maximo)

    @api.private
    def canal_activo(self, canal):
        self.ensure_one()
        return bool(self.bot_activo_global and canal in dict(CANALES) and self[f'canal_{canal}'])

    @api.private
    def canales_activos(self):
        self.ensure_one()
        return {canal: bool(self[f'canal_{canal}']) for canal, _nombre in CANALES}

    @api.depends('modelo_rapido', 'modelo_inteligente')
    def _compute_aviso_contributor(self):
        for registro in self:
            registro.aviso_contributor = any(
                'contributor' in (modelo or '').lower()
                for modelo in (registro.modelo_rapido, registro.modelo_inteligente))

    @api.onchange('proveedor_ia')
    def _onchange_proveedor_ia(self):
        """Al cambiar de proveedor, los modelos pasan a los suyos (si seguían siendo los de otro proveedor)."""
        rapido, inteligente = MODELOS_POR_PROVEEDOR.get(self.proveedor_ia, ('', ''))
        conocidos = {m for par in MODELOS_POR_PROVEEDOR.values() for m in par if m}
        if not self.modelo_rapido or self.modelo_rapido in conocidos:
            self.modelo_rapido = rapido
        if not self.modelo_inteligente or self.modelo_inteligente in conocidos:
            self.modelo_inteligente = inteligente

    @api.private
    def lista_lecciones(self):
        self.ensure_one()
        return [linea.strip() for linea in (self.lecciones_aprendidas or '').splitlines() if linea.strip()]

    @api.private
    def precios_ia(self):
        """Precios por nivel y tipo; ``None`` donde no hay precio verificado (0 o vacío): nunca una cifra inventada."""
        self.ensure_one()
        return {nivel: {tipo: (self[f'precio_{nivel}_{tipo}_usd_mtok'] or None) for tipo in TIPOS_PRECIO}
                for nivel in NIVELES_IA}

    @api.private
    def lista_palabras_prohibidas(self):
        self.ensure_one()
        return [linea.strip() for linea in (self.palabras_prohibidas or '').splitlines() if linea.strip()]

    @api.private
    def como_json(self):
        """La configuración tal como la lee el Worker (``GET /dcasa/juan/v1/config``)."""
        self.ensure_one()
        return {
            'nombre_publico': self.nombre_publico,
            'bot_activo_global': bool(self.bot_activo_global),
            'canales_activos': self.canales_activos(),
            'horario': self.horario().como_json(),
            'seguimiento': {
                'primero_horas': _entero_si_se_puede(self.seguimiento_primero_horas),
                'segundo_dias': _entero_si_se_puede(self.seguimiento_segundo_dias),
                'solo_horario_laboral': bool(self.seguimiento_solo_horario_laboral),
                'maximo': self.seguimiento_maximo,
            },
            'presupuesto_ia_mensual_usd': _entero_si_se_puede(self.presupuesto_ia_mensual_usd),
            'proveedor_ia': self.proveedor_ia,
            'proveedor_respaldo_ia': self.proveedor_respaldo_ia or None,
            'modelo_rapido': self.modelo_rapido or '',
            'modelo_inteligente': self.modelo_inteligente or '',
            'modelos_por_defecto': {proveedor: {'rapido': rapido, 'inteligente': inteligente}
                                    for proveedor, (rapido, inteligente) in MODELOS_POR_PROVEEDOR.items()},
            'precios': self.precios_ia(),
            'lecciones': self.lista_lecciones(),
            'mensaje_bienvenida': self.mensaje_bienvenida or '',
            'texto_privacidad_corto': self.texto_privacidad_corto or '',
            'palabras_prohibidas': self.lista_palabras_prohibidas(),
            'pausa_por_defecto_minutos': self.pausa_por_defecto_minutos,
        }

    # ------------------------------------------------------------------
    # Conexión con el Worker: URL y secretos (el valor del secreto nunca sale de aquí por la interfaz)
    # ------------------------------------------------------------------

    @api.model
    def _parametro(self, clave):
        return (self.env['ir.config_parameter'].sudo().get_param(clave) or '').strip()

    @api.private
    @api.model
    def url_worker(self):
        return (os.environ.get(ENV_URL) or self._parametro(PARAM_URL)).strip().rstrip('/')

    @api.private
    @api.model
    def token_odoo(self):
        """Token que el Worker presenta a Odoo. Vacío o demasiado corto = no configurado."""
        token = (os.environ.get(ENV_TOKEN_ODOO) or self._parametro(PARAM_TOKEN_ODOO)).strip()
        return token if len(token) >= LARGO_MINIMO_TOKEN else ''

    @api.private
    @api.model
    def token_worker(self):
        """Token que Odoo presenta al Worker."""
        token = (os.environ.get(ENV_TOKEN_WORKER) or self._parametro(PARAM_TOKEN_WORKER)).strip()
        return token if len(token) >= LARGO_MINIMO_TOKEN else ''

    def _compute_juan_url(self):
        url = self.url_worker()
        for registro in self:
            registro.juan_url = url

    def _inverse_juan_url(self):
        for registro in self:
            valor = (registro.juan_url or '').strip().rstrip('/')
            if valor and not self.env['dcasa.juan.cliente']._url_valida(valor):
                raise ValidationError(self.env._(
                    'La dirección del Worker debe empezar con https:// (o http://localhost para pruebas).'))
            self.env['ir.config_parameter'].sudo().set_param(PARAM_URL, valor)

    def _compute_tokens(self):
        odoo, worker = bool(self.token_odoo()), bool(self.token_worker())
        for registro in self:
            registro.token_odoo_configurado = odoo
            registro.token_worker_configurado = worker

    def action_probar_conexion(self):
        """Botón «Probar conexión»: le pregunta su salud al Worker."""
        if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
            raise AccessError(self.env._('Solo Gerencia prueba la conexión con el Worker.'))
        self.ensure_one()
        resultado = self.env['dcasa.juan.cliente'].salud()
        if resultado.get('ok'):
            canales = resultado.get('canales') or {}
            detalle = ', '.join(f'{nombre}: {estado}' for nombre, estado in canales.items()) or 'sin detalle'
            mensaje = self.env._('El Worker respondió. Canales: %s.', detalle)
            tipo = 'success'
        else:
            mensaje = self.env._('No pude hablar con el Worker: %s', resultado.get('error') or 'sin respuesta')
            tipo = 'warning'
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': self.env._('Conexión con Juan'), 'message': mensaje, 'type': tipo,
                           'sticky': False}}


def _entero_si_se_puede(valor):
    """5.0 → 5 (el Worker espera 5, no 5.0); 5.5 se queda."""
    return int(valor) if float(valor).is_integer() else valor
