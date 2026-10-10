"""Alta del equipo: usuario + empleado + departamento + rol, sin mandar invitaciones.

La lista se pega en Empleados › Alta del equipo (una persona por línea):
``nombre | correo | departamento | cargo | rol``.
Se revisa antes de crear. Lo que se pega vive solo en la base de datos (ninguna lista queda en el repositorio).

Por qué una pantalla propia: crear un usuario desde Odoo con su correo MANDA solo la invitación para elegir clave
(``auth_signup``), y la importación normal también. Aquí se crea con ``no_reset_password``: la persona queda sin
poder entrar hasta que alguien le envíe la invitación desde su ficha de usuario («Enviar correo de invitación»).

Los roles son los de siempre (``dcasa_base``): Vendedora, Gerencia y, además, Administrador (Gerencia + Ajustes:
control total). No se crean permisos nuevos.
"""
import logging
import re
import unicodedata

from psycopg2 import Error as ErrorSql

from odoo import fields, models, tools
from odoo.addons.dcasa_base import DCASA_LANG, DCASA_TZ
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

SEPARADOR = re.compile(r'\s*[|;\t]\s*')
FORMATO = 'nombre | correo | departamento | cargo | rol'

# rol → (nombre que se muestra, grupos). El grupo «Usuario interno» va siempre: sin él no entra al panel.
ROLES = {
    'vendedora': ("Vendedora", ('dcasa_base.group_vendedora',)),
    'gerencia': ("Gerencia", ('dcasa_base.group_gerencia',)),
    'administrador': ("Administrador (control total)", ('dcasa_base.group_gerencia', 'base.group_system')),
}
ALIAS_ROL = {
    'vendedora': 'vendedora', 'vendedor': 'vendedora', 'vendedor/a': 'vendedora', 'ventas': 'vendedora',
    'gerencia': 'gerencia', 'gerente': 'gerencia',
    'administrador': 'administrador', 'admin': 'administrador', 'control total': 'administrador',
    'total': 'administrador',
}

# Crear sin invitación, sin avisos ni seguimiento en el chatter: es una carga, no una conversación.
CONTEXTO_SIN_AVISOS = {
    'no_reset_password': True,
    'mail_create_nosubscribe': True,
    'mail_create_nolog': True,
    'mail_notrack': True,
    'tracking_disable': True,
}


def _normal(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').strip().lower())
    return re.sub(r'\s+', ' ', ''.join(c for c in texto if not unicodedata.combining(c)))


def _limpio(texto):
    return re.sub(r'\s+', ' ', (texto or '').strip())


def leer_rol(texto):
    """«Vendedor», «vendedora», «Gerente», «control total»… → clave de ROLES, o ``False``."""
    return ALIAS_ROL.get(_normal(texto), False)


def revisar_fila(nombre, correo, departamento, cargo, rol):
    """Devuelve ``(fila_limpia, error)``; ``error`` vacío si la fila se puede crear."""
    nombre, departamento, cargo = _limpio(nombre), _limpio(departamento), _limpio(cargo)
    clave = leer_rol(rol)
    normal = tools.email_normalize(correo or '') or ''
    fila = {'nombre': nombre, 'correo': normal or _limpio(correo), 'departamento': departamento, 'cargo': cargo,
            'rol': clave}
    if not nombre:
        return fila, "Falta el nombre."
    if not normal:
        return fila, "El correo no es válido."
    if not clave:
        return fila, "El rol no se reconoce: usa Vendedora, Gerencia o Administrador."
    return fila, ''


def leer_lista(texto):
    """Lista pegada → filas ``dict(nombre, correo, departamento, cargo, rol, error)``.

    Se ignoran las líneas en blanco y las que empiezan con ``#``. Separadores: ``|``, ``;`` o tabulador.
    """
    filas, vistos = [], set()
    for renglon in (texto or '').splitlines():
        if not renglon.strip() or renglon.strip().startswith('#'):
            continue
        partes = SEPARADOR.split(renglon.strip())
        if len(partes) != 5:
            partes = (partes + [''] * 5)[:5]
            fila, _error = revisar_fila(*partes)
            fila['error'] = f"Cada línea lleva cinco datos separados por «|»: {FORMATO}."
        else:
            fila, error = revisar_fila(*partes)
            if not error and fila['correo'] in vistos:
                error = "Este correo está repetido en la lista."
            fila['error'] = error
        vistos.add(fila['correo'])
        filas.append(fila)
    return filas


class DcasaEquipoAlta(models.TransientModel):
    _name = 'dcasa.equipo.alta'
    _description = "Alta del equipo (asistente)"

    texto = fields.Text(
        string="Lista del equipo",
        help=f"Una persona por línea: {FORMATO}. El rol es Vendedora, Gerencia o Administrador. "
             "Las líneas que empiezan con # se ignoran.")
    linea_ids = fields.One2many('dcasa.equipo.alta.linea', 'alta_id', string="Personas")

    def _exigir_administrador(self):
        """Gestionar usuarios lo puede hacer quien administra accesos (Odoo: ``base.group_erp_manager``)."""
        if not self.env.su and not self.env.user.has_group('base.group_erp_manager'):
            raise AccessError(self.env._("Solo quien administra los accesos puede dar de alta al equipo."))

    def _reabrir(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_leer(self):
        """Lee la lista pegada y arma las líneas para revisarlas. No crea nada todavía."""
        self.ensure_one()
        self._exigir_administrador()
        filas = leer_lista(self.texto)
        if not filas:
            raise UserError(self.env._("Pega al menos una persona. Formato de cada línea: %s", FORMATO))
        self.linea_ids.unlink()
        self.env['dcasa.equipo.alta.linea'].create([{
            'alta_id': self.id,
            'nombre': f['nombre'],
            'correo': f['correo'],
            'departamento': f['departamento'],
            'cargo': f['cargo'],
            'rol': f['rol'],
            'estado': 'error' if f['error'] else 'pendiente',
            'resultado': f['error'],
        } for f in filas])
        return self._reabrir()

    def action_crear(self):
        """Crea a quien está por crear (y reintenta lo que tenía error). Quien ya se creó no se vuelve a tocar."""
        self.ensure_one()
        self._exigir_administrador()
        pendientes = self.linea_ids.filtered(lambda linea: linea.estado in ('pendiente', 'error'))
        if not pendientes:
            raise UserError(self.env._("No hay nadie por crear. Pega la lista y pulsa «Leer lista»."))
        for linea in pendientes:
            linea._procesar()
        return self._reabrir()


class DcasaEquipoAltaLinea(models.TransientModel):
    _name = 'dcasa.equipo.alta.linea'
    _description = "Persona del alta del equipo"
    _order = 'id'

    alta_id = fields.Many2one('dcasa.equipo.alta', required=True, ondelete='cascade')
    nombre = fields.Char(required=True)
    correo = fields.Char(required=True)
    departamento = fields.Char()
    cargo = fields.Char()
    rol = fields.Selection([(k, v[0]) for k, v in ROLES.items()])
    estado = fields.Selection([
        ('pendiente', "Por crear"),
        ('creado', "Creado"),
        ('ya_estaba', "Ya estaba"),
        ('error', "Revisar"),
    ], default='pendiente', required=True)
    resultado = fields.Char(readonly=True)

    # ------------------------------------------------------------------
    # Proceso de una línea
    # ------------------------------------------------------------------
    def _procesar(self):
        """Revisa la fila (puede haberse corregido a mano) y la crea; un error no frena a las demás."""
        self.ensure_one()
        fila, error = revisar_fila(self.nombre, self.correo, self.departamento, self.cargo, self.rol)
        if not error and fila['rol'] == 'administrador' and not self._puede_dar_control_total():
            error = "Solo un administrador de Ajustes puede dar el rol Administrador."
        if error:
            self.write({'estado': 'error', 'resultado': error})
            return
        try:
            with self.env.cr.savepoint():
                estado, texto = self._alta(fila)
        except (UserError, ValidationError, AccessError) as e:
            self.write({'estado': 'error', 'resultado': str(e)})
        except ErrorSql:
            _logger.exception("Equipo: no se pudo crear a %s", fila['correo'])
            self.write({'estado': 'error', 'resultado': "No se pudo crear (la base de datos lo rechazó)."})
        else:
            self.write({'estado': estado, 'resultado': texto, **fila})

    def _puede_dar_control_total(self):
        return self.env.su or self.env.user.has_group('base.group_system')

    def _alta(self, fila):
        """Usuario (sin invitación) + empleado enlazado a su usuario y su contacto + departamento + rol."""
        correo = fila['correo']
        empresa = self.env.company
        Usuarios = self.env['res.users'].sudo().with_context(**CONTEXTO_SIN_AVISOS)
        usuario = Usuarios.with_context(active_test=False).search(
            ['|', ('login', '=', correo), ('email_normalized', '=', correo)], limit=1)
        nuevo = not usuario
        if nuevo:
            usuario = Usuarios.create(self._valores_de_usuario(fila, empresa))
        empleado = usuario.employee_ids.filtered(lambda e: e.company_id == empresa)[:1]
        if not empleado:
            Empleado = self.env['hr.employee'].sudo().with_context(**CONTEXTO_SIN_AVISOS)
            valores = dict(name=usuario.name, company_id=empresa.id, **Empleado._sync_user(usuario))
            departamento = self._departamento(fila['departamento'], empresa)
            if departamento:
                valores['department_id'] = departamento.id
            if fila['cargo']:
                valores['job_title'] = fila['cargo']
            Empleado.create(valores)
        rol = ROLES[fila['rol']][0]
        if nuevo:
            return 'creado', (f"Usuario creado sin invitación; empleado en "
                              f"{fila['departamento'] or 'sin departamento'}; rol {rol}.")
        if not empleado:
            return 'ya_estaba', "Ya tenía usuario (no se tocó); se le creó la ficha de empleado."
        return 'ya_estaba', "Ya tenía usuario y ficha de empleado: no se cambió nada."

    def _valores_de_usuario(self, fila, empresa):
        grupos = self.env.ref('base.group_user')
        for xmlid in ROLES[fila['rol']][1]:
            grupos |= self.env.ref(xmlid)
        valores = {
            'name': fila['nombre'],
            'login': fila['correo'],
            'email': fila['correo'],
            'company_id': empresa.id,
            'company_ids': [(6, 0, [empresa.id])],
            'group_ids': [(6, 0, grupos.ids)],
            'tz': DCASA_TZ,
        }
        if self.env['res.lang'].sudo().search_count([('code', '=', DCASA_LANG), ('active', '=', True)]):
            valores['lang'] = DCASA_LANG
        return valores

    def _departamento(self, nombre, empresa):
        if not nombre:
            return self.env['hr.department']
        Departamento = self.env['hr.department'].sudo()
        existente = Departamento.search(
            [('name', '=ilike', tools.escape_psql(nombre)), ('company_id', 'in', [False, empresa.id])], limit=1)
        return existente or Departamento.create({'name': nombre, 'company_id': empresa.id})
