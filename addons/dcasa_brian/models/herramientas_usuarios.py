"""Herramientas de usuarios: roles simples de D'CASA sobre los grupos de Odoo.

Nunca: tocar al administrador principal (base.user_admin) ni a quien conversa, ni ver o
cambiar contraseñas o claves. Todo lo que cambia algo es «sensible» (lo confirma un humano).
"""
from odoo import Command, api, models

from . import herramientas_comun as c
from .registro import BrianError, herramienta

GESTION_USUARIOS = ('base.group_erp_manager',)

# EL mapeo rol → grupos de Odoo (único lugar). Orden: del más alto al más bajo (así se detecta el rol).
ROLES = {
    'administrador': ('base.group_system', 'sales_team.group_sale_manager', 'account.group_account_manager',
                      'stock.group_stock_manager'),
    'contador': ('account.group_account_manager', 'sales_team.group_sale_salesman_all_leads',
                 'stock.group_stock_user'),
    'cajero': ('account.group_account_invoice', 'sales_team.group_sale_salesman_all_leads',
               'stock.group_stock_user'),
    'vendedor': ('sales_team.group_sale_salesman', 'stock.group_stock_user'),
}
NOMBRES_ROL = {'administrador': 'Administrador/a', 'contador': 'Contador/a', 'cajero': 'Cajero/a',
               'vendedor': 'Vendedor/a'}
# Grupos que un cambio de rol quita antes de poner los del rol nuevo (los de estas mismas áreas).
GESTIONADOS = {
    'base.group_system', 'base.group_erp_manager',
    'sales_team.group_sale_salesman', 'sales_team.group_sale_salesman_all_leads', 'sales_team.group_sale_manager',
    'account.group_account_invoice', 'account.group_account_basic', 'account.group_account_readonly',
    'account.group_account_user', 'account.group_account_manager',
    'stock.group_stock_user', 'stock.group_stock_manager',
}
PARAM_USUARIO = {'type': 'string', 'description': 'Nombre o correo (login) del usuario, p. ej. «maria@dcasapty.com».'}
PARAM_ROL = {'type': 'string', 'enum': list(ROLES),
             'description': 'vendedor (ventas), cajero (ventas + facturas y cobros), contador (contabilidad) '
                            'o administrador (todo).'}


class BrianHerramientasUsuarios(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_grupos_rol(self, rol):
        if rol not in ROLES:
            raise BrianError(f'Rol desconocido. Usa uno de: {", ".join(ROLES)}.')
        grupos = self.env['res.groups']
        for xmlid in ROLES[rol]:
            grupos |= self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.groups']
        return grupos

    @api.model
    def _b_rol(self, usuario):
        for rol, xmlids in ROLES.items():
            if all(usuario.has_group(x) for x in xmlids if self.env.ref(x, raise_if_not_found=False)):
                return NOMBRES_ROL[rol]
        return 'Otro (permisos a medida)' if not usuario.share else 'Portal'

    @api.model
    def _b_exigir_admin_para(self, rol):
        if rol == 'administrador' and not self.env.user.has_group('base.group_system'):
            raise BrianError('Solo un administrador del sistema puede dar el rol de administrador.')

    @api.model
    def _b_fila_usuario(self, usuario):
        return {'nombre': usuario.name, 'login': usuario.login, 'rol': self._b_rol(usuario),
                'activo': usuario.active, 'ultimo_acceso': c.fecha(usuario.login_date)}

    @herramienta(
        nombre='listar_usuarios',
        descripcion='Usuarios internos con su rol (vendedor, cajero, contador, administrador) y último acceso.',
        parametros={'incluir_inactivos': {'type': 'boolean', 'description': 'true para ver también los '
                                                                            'desactivados.'}},
        nivel='lectura', categoria='usuarios', grupos=GESTION_USUARIOS,
        ejemplos=['¿quién tiene acceso al sistema?'],
    )
    def _h_listar_usuarios(self, incluir_inactivos=False):
        Users = self.env['res.users'].with_context(active_test=not incluir_inactivos)
        usuarios = Users.search([('share', '=', False)], order='name')
        return {'usuarios': [self._b_fila_usuario(u) for u in usuarios[:50]], 'total': len(usuarios),
                'roles_disponibles': NOMBRES_ROL}

    @herramienta(
        nombre='cambiar_rol_usuario',
        descripcion='Cambia el rol de un usuario: vendedor, cajero, contador o administrador.',
        parametros={'usuario': PARAM_USUARIO, 'rol': PARAM_ROL}, requeridos=['usuario', 'rol'],
        nivel='sensible', categoria='usuarios', grupos=GESTION_USUARIOS,
        ejemplos=['María ahora es cajera → rol=cajero'],
    )
    def _h_cambiar_rol_usuario(self, usuario, rol):
        persona = self._b_usuario(usuario)
        self._b_proteger_usuario(persona)
        self._b_exigir_admin_para(rol)
        nuevos = self._b_grupos_rol(rol)
        quitar = self.env['res.groups']
        for xmlid in GESTIONADOS:
            quitar |= self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.groups']
        antes = self._b_rol(persona)
        persona.write({'group_ids': [Command.unlink(g.id) for g in quitar & persona.group_ids]
                                    + [Command.link(g.id) for g in nuevos]})
        return {'mensaje': f'{persona.name}: {antes} → {NOMBRES_ROL[rol]}.', **self._b_fila_usuario(persona)}

    @herramienta(
        nombre='crear_usuario',
        descripcion='Crea un usuario interno con un rol. Recibe la invitación por correo para poner su propia '
                    'contraseña (Brian nunca maneja contraseñas).',
        parametros={
            'nombre': {'type': 'string', 'description': 'Nombre completo, p. ej. «María Rodríguez».'},
            'correo': {'type': 'string', 'description': 'Correo con el que entrará, p. ej. «maria@dcasapty.com».'},
            'rol': PARAM_ROL,
        },
        requeridos=['nombre', 'correo', 'rol'],
        nivel='sensible', categoria='usuarios', grupos=GESTION_USUARIOS,
        ejemplos=['crea a María Rodríguez, maria@dcasapty.com, vendedora'],
    )
    def _h_crear_usuario(self, nombre, correo, rol):
        nombre, correo = (nombre or '').strip(), (correo or '').strip().lower()
        if not nombre or '@' not in correo:
            raise BrianError('Necesito el nombre y un correo válido.')
        self._b_exigir_admin_para(rol)
        existe = self.env['res.users'].with_context(active_test=False).search([('login', '=ilike', correo)], limit=1)
        if existe:
            raise BrianError(f'Ya existe un usuario con {correo} ({existe.name}'
                             + ('' if existe.active else ', desactivado') + ').')
        grupos = self.env.ref('base.group_user') | self._b_grupos_rol(rol)
        persona = self.env['res.users'].create({
            'name': nombre, 'login': correo, 'email': correo, 'group_ids': [Command.set(grupos.ids)]})
        return {'mensaje': f'Usuario {persona.name} creado como {NOMBRES_ROL[rol]}.', **self._b_fila_usuario(persona)}

    @herramienta(
        nombre='desactivar_usuario',
        descripcion='Desactiva un usuario (ya no puede entrar). No se borra: su historial queda.',
        parametros={'usuario': PARAM_USUARIO}, requeridos=['usuario'],
        nivel='sensible', categoria='usuarios', grupos=GESTION_USUARIOS,
        ejemplos=['quítale el acceso a Pedro'],
    )
    def _h_desactivar_usuario(self, usuario):
        persona = self._b_usuario(usuario)
        self._b_proteger_usuario(persona)
        persona.active = False
        return {'mensaje': f'{persona.name} quedó desactivado.', 'nombre': persona.name, 'login': persona.login}


class BrianPoliticaUsuarios(models.AbstractModel):
    """Se bloquea ANTES de proponer: al administrador o a uno mismo ni siquiera se le ofrece la tarjeta."""
    _inherit = 'brian.politica'

    @api.model
    def _verificar_usuario_protegido(self, argumentos):
        if argumentos.get('usuario'):
            herramientas = self.env['brian.herramientas']
            herramientas._b_proteger_usuario(herramientas._b_usuario(argumentos['usuario']))

    @api.model
    def _verificar_cambiar_rol_usuario(self, argumentos):
        self._verificar_usuario_protegido(argumentos)
        self.env['brian.herramientas']._b_exigir_admin_para(argumentos.get('rol'))

    @api.model
    def _verificar_desactivar_usuario(self, argumentos):
        self._verificar_usuario_protegido(argumentos)

    @api.model
    def _verificar_crear_usuario(self, argumentos):
        self.env['brian.herramientas']._b_exigir_admin_para(argumentos.get('rol'))
