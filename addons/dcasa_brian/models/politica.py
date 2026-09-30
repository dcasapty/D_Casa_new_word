"""Política de Brian: lo que no hace aunque se lo pidan (ver docs/BRIAN.md).

``brian.herramientas.ejecutar`` llama a ``verificar(spec, argumentos)`` antes de correr
cualquier herramienta y ``resumir`` para la tarjeta de confirmación de las sensibles.

Las herramientas deben apoyarse en los ayudantes públicos, que lanzan ``BrianError`` con
un mensaje en español cuando algo está prohibido::

    politica = self.env['brian.politica']
    politica.proteger_usuario(usuario, 'archivar')       # admin, OdooBot o uno mismo
    politica.puede_editar_factura(factura)               # publicada / pagada / cancelada
    politica.proteger_borrado('account.move')             # contabilidad, puntos, auditoría
    politica.proteger_campos('res.users', ['password'])  # secretos y parámetros técnicos
    politica.proteger_libro_puntos('write')               # dcasa.movimiento no se edita

Reglas específicas por herramienta: definir en un ``_inherit = 'brian.politica'`` los
métodos opcionales ``_verificar_<nombre>(argumentos)`` (lanza BrianError) y
``_resumir_<nombre>(argumentos)`` (devuelve el texto de la tarjeta).
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .registro import BrianError, normalizar

LIMITE_POR_MINUTO = 30

# Nunca se borran (se corrigen con asientos contrarios, por una persona).
MODELOS_NO_BORRABLES = {
    'account.move', 'account.move.line', 'account.payment', 'account.partial.reconcile',
    'account.full.reconcile', 'account.bank.statement', 'account.bank.statement.line',
    'account.analytic.line', 'dcasa.movimiento', 'brian.accion', 'brian.mensaje',
}

# Técnicos: Brian no los lee ni los cambia de forma genérica.
MODELOS_TECNICOS = {
    'ir.config_parameter', 'ir.cron', 'ir.actions.server', 'ir.actions.actions', 'ir.model',
    'ir.model.fields', 'ir.model.access', 'ir.rule', 'ir.module.module', 'ir.ui.view',
    'ir.mail_server', 'ir.attachment', 'res.users.apikeys', 'res.users.apikeys.description',
    'base.automation', 'auth_totp.device', 'fetchmail.server', 'res.groups',
    'brian.accion', 'dcasa.movimiento',
}

# Fragmentos de nombres de campo/argumento que delatan un secreto.
SECRETOS = ('password', 'contrasena', 'clave_api', 'api_key', 'apikey', 'token', 'secret', 'secreto',
            'pepper', 'totp', 'pin_hash', 'signup')

# Argumentos cuyo valor es un nombre de campo.
CLAVES_DE_CAMPO = ('campo', 'campos', 'field', 'fields')

TEXTOS_PROHIBIDOS = ('dcasa_pin_pepper', 'brian_api_key', 'telegram_bot_token')

ESTADOS_PAGO_BLOQUEADOS = {
    'paid': 'pagada', 'in_payment': 'en proceso de pago', 'partial': 'pagada en parte',
    'reversed': 'revertida',
}


class BrianPolitica(models.AbstractModel):
    _name = 'brian.politica'
    _description = 'Política de Brian'

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------

    @api.model
    def verificar(self, spec, argumentos):
        """Lanza ``BrianError`` si la acción no se puede hacer. No devuelve nada útil."""
        argumentos = argumentos or {}
        self.limite_por_minuto()
        modelo = argumentos.get('modelo') or argumentos.get('model')
        if isinstance(modelo, str) and modelo in MODELOS_TECNICOS:
            raise BrianError(self.env._('No trabajo con «%s»: es configuración técnica del sistema.', modelo))
        self._revisar_secretos(argumentos)
        nombre = normalizar(spec.get('nombre', ''))
        if nombre.startswith(('eliminar_', 'borrar_')) and isinstance(modelo, str):
            self.proteger_borrado(modelo)
        propia = getattr(self, f"_verificar_{spec.get('nombre')}", None)
        if propia:
            propia(argumentos)
        return True

    @api.model
    def resumir(self, spec, argumentos):
        """Texto humano para la tarjeta «¿Lo hago?» de una acción sensible."""
        argumentos = argumentos or {}
        propio = getattr(self, f"_resumir_{spec.get('nombre')}", None)
        if propio:
            texto = propio(argumentos)
            if texto:
                return texto
        descripcion = (spec.get('descripcion') or spec.get('nombre', '')).strip()
        primera = descripcion.split('. ')[0].rstrip('.')
        lineas = [f'{primera}.']
        for clave, valor in argumentos.items():
            etiqueta = clave.replace('_', ' ').capitalize()
            lineas.append(f'• {etiqueta}: {self._humano(valor)}')
        return '\n'.join(lineas)

    # ------------------------------------------------------------------
    # Ayudantes reutilizables por las herramientas
    # ------------------------------------------------------------------

    @api.model
    def es_administrador(self, usuario):
        usuario = usuario.sudo()
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        return bool(usuario._is_superuser() or (admin and usuario == admin)
                    or usuario.has_group('base.group_system'))

    @api.model
    def proteger_usuario(self, usuario, operacion='modificar'):
        """Nadie borra, archiva ni le quita permisos al administrador ni a sí mismo."""
        for u in usuario:
            if u == self.env.user:
                raise BrianError(self.env._(
                    'No puedo %s tu propio usuario: eso lo hace otro administrador desde Ajustes.', operacion))
            if self.es_administrador(u):
                raise BrianError(self.env._(
                    'No puedo %(op)s a %(nombre)s: es administrador. Eso se hace a mano desde Ajustes › Usuarios.',
                    op=operacion, nombre=u.name))
        return True

    @api.model
    def puede_editar_factura(self, move):
        """Solo se editan facturas/asientos en borrador y sin pagos."""
        for m in move:
            nombre = m.display_name
            if m.state == 'posted':
                raise BrianError(self.env._(
                    '%s ya está publicada: no se modifica. Se corrige con una nota de crédito '
                    'o un asiento contrario, hecho por una persona.', nombre))
            if m.state == 'cancel':
                raise BrianError(self.env._('%s está cancelada: no se modifica.', nombre))
            estado_pago = m.payment_state if 'payment_state' in m._fields else None
            if estado_pago in ESTADOS_PAGO_BLOQUEADOS:
                raise BrianError(self.env._('%(n)s está %(e)s: no se modifica.',
                                            n=nombre, e=ESTADOS_PAGO_BLOQUEADOS[estado_pago]))
        return True

    @api.model
    def proteger_conciliacion(self):
        raise BrianError(self.env._('Las conciliaciones no las toco: las revisa una persona en Contabilidad.'))

    @api.model
    def proteger_borrado(self, modelo):
        if modelo in MODELOS_NO_BORRABLES:
            raise BrianError(self.env._(
                'Eso no se borra: los registros contables, el libro de puntos y el registro de '
                'acciones se corrigen con asientos contrarios, nunca borrando.'))
        return True

    @api.model
    def proteger_libro_puntos(self, operacion='write'):
        """El libro de puntos (dcasa.movimiento) solo acepta asientos nuevos."""
        if operacion in ('write', 'unlink'):
            raise BrianError(self.env._(
                'El libro de puntos no se edita ni se borra: se corrige con un asiento contrario con motivo.'))
        return True

    @api.model
    def proteger_campos(self, modelo, campos):
        """Bloquea modelos técnicos y campos secretos (contraseñas, claves, tokens)."""
        if modelo in MODELOS_TECNICOS:
            raise BrianError(self.env._('No trabajo con «%s»: es configuración técnica del sistema.', modelo))
        for campo in campos or ():
            if self._es_secreto(campo):
                raise BrianError(self.env._(
                    'No veo ni cambio contraseñas, claves ni tokens («%s»).', campo))
        if modelo == 'res.users':
            prohibidos = {'group_ids', 'groups_id', 'active', 'login'} & set(campos or ())
            if prohibidos and not self.env.context.get('brian_permiso_revisado'):
                raise BrianError(self.env._(
                    'Los roles, el acceso y el usuario de ingreso se cambian con la herramienta de '
                    'roles (pide confirmación), no editando el usuario directamente.'))
        return True

    @api.model
    def limite_por_minuto(self):
        """Frena ráfagas: máximo N acciones por minuto por usuario (parámetro configurable)."""
        limite = self._limite()
        desde = fields.Datetime.now() - timedelta(minutes=1)
        cuantas = self.env['brian.accion'].sudo().search_count([
            ('create_uid', '=', self.env.uid), ('create_date', '>=', desde)])
        if cuantas > limite:
            raise BrianError(self.env._(
                'Vamos muy rápido: ya van %s acciones en el último minuto. Espera un momento y seguimos.',
                cuantas))
        return True

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    @api.model
    def _limite(self):
        try:
            valor = int(self.env['ir.config_parameter'].sudo().get_param(
                'dcasa_brian.acciones_por_minuto', LIMITE_POR_MINUTO))
        except (TypeError, ValueError):
            valor = LIMITE_POR_MINUTO
        return max(valor, 1)

    @api.model
    def _es_secreto(self, nombre):
        nombre = normalizar(str(nombre))
        return any(s in nombre for s in SECRETOS)

    @api.model
    def _revisar_secretos(self, valor, profundidad=0):
        """Recorre los argumentos: claves secretas, nombres de campo secretos y textos prohibidos."""
        if profundidad > 5:
            return
        if isinstance(valor, dict):
            for clave, sub in valor.items():
                if self._es_secreto(clave):
                    raise BrianError(self.env._('No veo ni cambio contraseñas, claves ni tokens («%s»).', clave))
                if clave in CLAVES_DE_CAMPO:
                    nombres = sub if isinstance(sub, (list, tuple)) else [sub]
                    for nombre in nombres:
                        if isinstance(nombre, str) and self._es_secreto(nombre):
                            raise BrianError(self.env._(
                                'No veo ni cambio contraseñas, claves ni tokens («%s»).', nombre))
                self._revisar_secretos(sub, profundidad + 1)
        elif isinstance(valor, (list, tuple)):
            for sub in valor:
                self._revisar_secretos(sub, profundidad + 1)
        elif isinstance(valor, str):
            texto = normalizar(valor)
            if any(t in texto for t in TEXTOS_PROHIBIDOS):
                raise BrianError(self.env._('Eso toca secretos del sistema: no lo hago.'))

    @api.model
    def _humano(self, valor):
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        if isinstance(valor, (list, tuple)):
            return ', '.join(self._humano(v) for v in valor) or '—'
        if isinstance(valor, dict):
            return ', '.join(f'{k}: {self._humano(v)}' for k, v in valor.items()) or '—'
        if valor in (None, ''):
            return '—'
        return str(valor)

    @api.model
    def _acceso(self, registro, operacion):
        """Comprueba como el usuario (y traduce el error) — útil antes de proponer una acción."""
        try:
            registro.check_access(operacion)
        except AccessError as error:
            raise BrianError(self.env._('No tienes permiso para eso: %s', error.args[0])) from error
        return True
