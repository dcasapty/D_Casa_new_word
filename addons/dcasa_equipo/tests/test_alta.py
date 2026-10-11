"""Alta del equipo: usuario + empleado + departamento + rol, sin invitación. Datos inventados (``.test``)."""
import os
import re
from unittest.mock import patch

from odoo.addons.dcasa_equipo.models.alta import DcasaEquipoAltaLinea
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

DOMINIO = '@equipo-prueba.test'


def _correo(nombre):
    return nombre + DOMINIO


def _linea(nombre, corto, departamento='Ventas', cargo='x', rol='Vendedora'):
    """Una persona de la lista pegada (``corto`` es la parte del correo antes de la arroba)."""
    return f"{nombre} | {_correo(corto)} | {departamento} | {cargo} | {rol}"


@tagged('post_install', '-at_install')
class TestAlta(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empresa = cls.env.ref('base.main_company')
        # Quien da de alta: administrador de Ajustes (Brian) y quien solo administra accesos.
        cls.admin = new_test_user(cls.env, login='admin_alta_prueba', groups='base.group_system')
        cls.accesos = new_test_user(
            cls.env, login='accesos_alta_prueba', groups='base.group_erp_manager,base.group_user')
        cls.gerencia = new_test_user(cls.env, login='gerencia_alta_prueba', groups='dcasa_base.group_gerencia')

    def _alta(self, texto, usuario=None):
        """Pega la lista, la lee y crea. Devuelve las líneas (en orden)."""
        alta = self.env['dcasa.equipo.alta'].with_user(usuario or self.admin).create({'texto': texto})
        alta.action_leer()
        alta.action_crear()
        return alta, alta.linea_ids.sorted('id')

    def _usuario(self, nombre):
        return self.env['res.users'].sudo().with_context(active_test=False).search([('login', '=', _correo(nombre))])

    # ------------------------------------------------------------------
    def test_crea_usuario_empleado_departamento_y_cargo_conectados(self):
        alta, lineas = self._alta(_linea("Persona Uno", 'uno', cargo='Vendedor/a'))
        self.assertEqual(lineas.estado, 'creado', lineas.resultado)
        usuario = self._usuario('uno')
        self.assertEqual(usuario.name, 'Persona Uno')
        self.assertEqual(usuario.email, _correo('uno'))
        empleado = usuario.employee_ids
        self.assertEqual(len(empleado), 1)
        # todo enlazado: el empleado es del usuario y su contacto de trabajo es el contacto del usuario
        self.assertEqual(empleado.user_id, usuario)
        self.assertEqual(empleado.work_contact_id, usuario.partner_id)
        self.assertEqual(empleado.department_id.name, 'Ventas')
        self.assertEqual(empleado.job_title, 'Vendedor/a')
        self.assertEqual(empleado.work_email, _correo('uno'))
        self.assertEqual(empleado.company_id, self.empresa)
        self.assertEqual(usuario.company_ids, self.empresa)
        self.assertEqual(usuario.tz, 'America/Panama')
        self.assertTrue(usuario.has_group('base.group_user'))

    def test_zona_horaria_de_panama_aunque_el_defecto_sea_otro(self):
        self.env['ir.default'].set('res.partner', 'tz', 'Europe/Madrid')
        self._alta(_linea("Persona Zona", 'zona', cargo='Cargo'))
        self.assertEqual(self._usuario('zona').tz, 'America/Panama')

    def test_no_se_manda_ninguna_invitacion(self):
        correos_antes = self.env['mail.mail'].sudo().search_count([])
        _alta, lineas = self._alta(_linea("Persona Dos", 'dos', cargo='Cargo'))
        self.assertEqual(lineas.estado, 'creado', lineas.resultado)
        usuario = self._usuario('dos')
        self.assertEqual(usuario.state, 'new', "Nunca conectado: nadie le ha mandado la invitación")
        self.assertFalse(usuario.partner_id.sudo().signup_type, "ninguna invitación preparada")
        self.assertEqual(self.env['mail.mail'].sudo().search_count([]), correos_antes)
        self.assertEqual(self.env['mail.mail'].sudo().search_count([('email_to', 'ilike', _correo('dos'))]), 0)

    def test_la_invitacion_se_puede_mandar_despues(self):
        self._alta(_linea("Persona Tres", 'tres', cargo='Cargo'))
        usuario = self._usuario('tres')
        self.assertFalse(usuario.partner_id.sudo().signup_type)
        usuario.with_user(self.admin).with_context(create_user=True).action_reset_password()
        self.assertEqual(usuario.partner_id.sudo().signup_type, 'signup')

    def test_roles(self):
        _alta, lineas = self._alta('\n'.join([
            _linea("Vende Prueba", 'vende', cargo='Cargo'),
            _linea("Gerente Prueba", 'gerente', 'Gerencia', 'CEO', 'Gerencia'),
            _linea("Admin Prueba", 'admin', 'Tecnología', 'Programador', 'Administrador')]))
        self.assertEqual(lineas.mapped('estado'), ['creado'] * 3, lineas.mapped('resultado'))
        vende, gerente, admin = self._usuario('vende'), self._usuario('gerente'), self._usuario('admin')
        self.assertTrue(vende.has_group('dcasa_base.group_vendedora'))
        self.assertTrue(vende.has_group('sales_team.group_sale_salesman'))
        self.assertFalse(vende.has_group('dcasa_base.group_gerencia'))
        self.assertFalse(vende.has_group('base.group_system'))
        self.assertTrue(gerente.has_group('dcasa_base.group_gerencia'))
        self.assertTrue(gerente.has_group('dcasa_base.group_vendedora'), "Gerencia incluye lo de Vendedora")
        self.assertFalse(gerente.has_group('base.group_system'), "Gerencia no es control total")
        self.assertTrue(admin.has_group('base.group_system'))
        self.assertTrue(admin.has_group('dcasa_base.group_gerencia'))

    def test_departamento_se_reutiliza_aunque_cambien_las_mayusculas(self):
        existente = self.env['hr.department'].create({'name': 'Ventas', 'company_id': self.empresa.id})
        antes = self.env['hr.department'].search_count([])
        self._alta('\n'.join([_linea("A Prueba", 'a', 'ventas'), _linea("B Prueba", 'b', 'VENTAS'),
                              _linea("C Prueba", 'c', 'Marketing')]))
        self.assertEqual(self._usuario('a').employee_ids.department_id, existente)
        self.assertEqual(self._usuario('b').employee_ids.department_id, existente)
        self.assertEqual(self.env['hr.department'].search_count([]), antes + 1, "solo se creó Marketing")

    def test_sin_departamento_ni_cargo(self):
        _alta, lineas = self._alta(f"Sin Depto | {_correo('sd')} |  |  | Vendedora")
        self.assertEqual(lineas.estado, 'creado', lineas.resultado)
        empleado = self._usuario('sd').employee_ids
        self.assertFalse(empleado.department_id)
        self.assertFalse(empleado.job_title)

    # ------------------------------------------------------------------
    def test_repetir_no_cambia_nada(self):
        texto = _linea("Persona Cuatro", 'cuatro', cargo='Cargo', rol='Gerencia')
        self._alta(texto)
        usuario = self._usuario('cuatro')
        # alguien le quitó Gerencia a mano: repetir el alta no se lo devuelve
        usuario.sudo().write({'group_ids': [(3, self.env.ref('dcasa_base.group_gerencia').id)]})
        usuario.employee_ids.sudo().write({'job_title': 'Otro cargo'})
        _alta, lineas = self._alta(texto)
        self.assertEqual(lineas.estado, 'ya_estaba', lineas.resultado)
        self.assertEqual(self.env['res.users'].sudo().with_context(active_test=False).search_count(
            [('login', '=', _correo('cuatro'))]), 1)
        self.assertEqual(len(usuario.employee_ids), 1)
        self.assertFalse(usuario.has_group('dcasa_base.group_gerencia'))
        self.assertEqual(usuario.employee_ids.job_title, 'Otro cargo')

    def test_usuario_que_ya_existia_sin_ficha_de_empleado(self):
        previo = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Nombre Previo', 'login': _correo('previo'), 'email': _correo('previo'),
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.assertFalse(previo.employee_ids)
        _alta, lineas = self._alta(_linea("Otro Nombre", 'previo', cargo='Cargo', rol='Gerencia'))
        self.assertEqual(lineas.estado, 'ya_estaba', lineas.resultado)
        self.assertIn('ficha de empleado', lineas.resultado)
        previo.invalidate_recordset()
        self.assertEqual(previo.name, 'Nombre Previo', "al usuario existente no se le cambia nada")
        self.assertFalse(previo.has_group('dcasa_base.group_gerencia'))
        self.assertEqual(previo.employee_ids.user_id, previo)
        self.assertEqual(previo.employee_ids.work_contact_id, previo.partner_id)
        self.assertEqual(previo.employee_ids.department_id.name, 'Ventas')

    def test_usuario_archivado_cuenta_como_existente(self):
        self._alta(_linea("Persona Cinco", 'cinco', cargo='Cargo'))
        self._usuario('cinco').sudo().action_archive()
        _alta, lineas = self._alta(_linea("Persona Cinco", 'cinco', cargo='Cargo'))
        self.assertEqual(lineas.estado, 'ya_estaba', lineas.resultado)
        self.assertEqual(self.env['res.users'].sudo().with_context(active_test=False).search_count(
            [('login', '=', _correo('cinco'))]), 1)

    def test_el_correo_del_contacto_tambien_cuenta_como_existente(self):
        self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Por Contacto', 'login': 'otro-acceso-prueba', 'email': _correo('contacto'),
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        _alta, lineas = self._alta(_linea("Por Contacto", 'contacto', cargo='Cargo'))
        self.assertEqual(lineas.estado, 'ya_estaba', lineas.resultado)
        self.assertEqual(self.env['res.users'].sudo().search_count([('email', '=', _correo('contacto'))]), 1)

    # ------------------------------------------------------------------
    def test_un_error_no_frena_a_los_demas_ni_deja_nada_a_medias(self):
        original = DcasaEquipoAltaLinea._alta

        def alta_con_falla(linea, fila):
            resultado = original(linea, fila)
            if fila['correo'] == _correo('falla'):
                raise ValidationError("Falla de prueba")
            return resultado

        with patch.object(DcasaEquipoAltaLinea, '_alta', alta_con_falla):
            _alta, lineas = self._alta('\n'.join([
                _linea("Bien Uno", 'bien1'), _linea("Falla", 'falla'), _linea("Bien Dos", 'bien2')]))
        self.assertEqual(lineas.mapped('estado'), ['creado', 'error', 'creado'])
        self.assertIn('Falla de prueba', lineas[1].resultado)
        self.assertFalse(self._usuario('falla'), "lo que falló se deshizo completo")
        self.assertTrue(self._usuario('bien1').employee_ids)
        self.assertTrue(self._usuario('bien2').employee_ids)

    def test_linea_con_error_se_corrige_y_se_crea(self):
        alta = self.env['dcasa.equipo.alta'].with_user(self.admin).create({
            'texto': _linea("Corrige Prueba", 'corrige', rol='jefa suprema') + '\n' + _linea("Bien Prueba", 'bien')})
        alta.action_leer()
        malo, bueno = alta.linea_ids.sorted('id')
        self.assertEqual((malo.estado, bueno.estado), ('error', 'pendiente'))
        self.assertIn('rol', malo.resultado)
        alta.action_crear()
        self.assertEqual(malo.estado, 'error', "sigue mal: no se crea")
        self.assertFalse(self._usuario('corrige'))
        self.assertEqual(bueno.estado, 'creado')
        malo.rol = 'vendedora'
        alta.action_crear()
        self.assertEqual(malo.estado, 'creado', malo.resultado)
        self.assertTrue(self._usuario('corrige').employee_ids)
        self.assertEqual(bueno.estado, 'creado', "quien ya estaba creado no se toca")

    def test_correo_mal_corregido_a_mano_se_revisa_otra_vez(self):
        alta = self.env['dcasa.equipo.alta'].with_user(self.admin).create({
            'texto': _linea("Mano Prueba", 'mano')})
        alta.action_leer()
        alta.linea_ids.correo = 'esto-no-es-un-correo'
        alta.action_crear()
        self.assertEqual(alta.linea_ids.estado, 'error')
        self.assertIn('correo', alta.linea_ids.resultado)

    def test_leer_otra_vez_reemplaza_las_lineas(self):
        alta = self.env['dcasa.equipo.alta'].with_user(self.admin).create({
            'texto': _linea("Uno", 'r1')})
        alta.action_leer()
        alta.texto = _linea("Dos", 'r2') + '\n' + _linea("Tres", 'r3')
        alta.action_leer()
        self.assertEqual(alta.linea_ids.mapped('nombre'), ['Dos', 'Tres'])

    def test_sin_texto_o_sin_nadie_por_crear_avisa(self):
        alta = self.env['dcasa.equipo.alta'].with_user(self.admin).create({'texto': '# nada\n'})
        with self.assertRaises(UserError):
            alta.action_leer()
        with self.assertRaises(UserError):
            alta.action_crear()

    # ------------------------------------------------------------------
    def test_administrador_solo_lo_da_un_administrador_de_ajustes(self):
        _alta, lineas = self._alta(
            _linea("Quiere Admin", 'quiere', 'Tecnología', rol='Administrador') + '\n' + _linea("Vende", 'vende2'),
            usuario=self.accesos)
        self.assertEqual(lineas.mapped('estado'), ['error', 'creado'])
        self.assertIn('administrador de Ajustes', lineas[0].resultado)
        self.assertFalse(self._usuario('quiere'), "no se creó ni a medias")
        self.assertTrue(self._usuario('vende2'))

    def test_quien_no_administra_accesos_no_puede(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.equipo.alta'].with_user(self.gerencia).create({'texto': 'x'})
        # y aunque el asistente exista, los botones lo comprueban en el servidor
        alta = self.env['dcasa.equipo.alta'].create({'texto': _linea("Uno", 'nopuede')})
        with self.assertRaises(AccessError):
            alta.with_user(self.gerencia).action_leer()
        alta.action_leer()
        with self.assertRaises(AccessError):
            alta.with_user(self.gerencia).action_crear()
        self.assertFalse(self._usuario('nopuede'))

    def test_la_comprobacion_del_servidor_no_depende_del_acl(self):
        alta = self.env['dcasa.equipo.alta'].create({'texto': 'x'})
        with self.assertRaises(AccessError):
            alta.with_user(self.gerencia)._exigir_administrador()
        alta.with_user(self.accesos)._exigir_administrador()
        alta.with_user(self.admin)._exigir_administrador()

    def test_es_una_pagina_normal_y_no_una_ventana_emergente(self):
        """Una ventana emergente abierta desde un menú reaparece vacía al recargar o volver atrás."""
        accion = self.env.ref('dcasa_equipo.action_dcasa_equipo_alta')
        self.assertEqual(accion.target, 'current')
        self.assertEqual(self.env.ref('dcasa_equipo.menu_dcasa_equipo_alta').action, accion)

    def test_el_menu_es_solo_de_quien_administra_accesos(self):
        menu = self.env.ref('dcasa_equipo.menu_dcasa_equipo_alta')
        self.assertEqual(menu.group_ids, self.env.ref('base.group_erp_manager'))
        self.assertEqual(menu.parent_id, self.env.ref('hr.menu_hr_root'))

    # ------------------------------------------------------------------
    def test_el_menu_empleados_tiene_el_icono_de_la_marca(self):
        menu = self.env.ref('hr.menu_hr_root')
        self.assertEqual(menu.web_icon, 'dcasa_equipo,static/src/img/empleados.svg')
        self.assertTrue(menu.web_icon_data)
        ruta = os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'img', 'empleados.svg')
        with open(ruta, encoding='utf-8') as f:
            svg = f.read()
        self.assertIn('#1340B1', svg)
        self.assertIn('#FED00F', svg)
        self.assertNotIn('gradient', svg.lower())

    def test_el_modulo_no_trae_datos_de_personas(self):
        """Los nombres y correos del equipo viven solo en la base de datos de Odoo, nunca en el repositorio."""
        raiz = os.path.join(os.path.dirname(__file__), '..')
        permitidos = {'equipo-prueba.test', 'ejemplo.com'}
        encontrados = set()
        for carpeta, _dirs, archivos in os.walk(raiz):
            for archivo in archivos:
                if not archivo.endswith(('.py', '.xml', '.csv', '.json', '.md', '.svg')):
                    continue
                with open(os.path.join(carpeta, archivo), encoding='utf-8') as f:
                    for dominio in re.findall(r'[\w.+-]+@([\w-]+(?:\.[\w-]+)+)', f.read()):
                        if dominio.lower() not in permitidos:
                            encontrados.add((archivo, dominio))
        self.assertFalse(encontrados, "Hay correos reales dentro del módulo")
