"""Base común de los tests del núcleo de Brian: usuarios, herramientas de prueba y proveedor 'prueba'."""
import os
from unittest.mock import patch

from odoo.addons.dcasa_brian.models import proveedores
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.tests.common import TransactionCase


@herramienta(nombre='prueba_leer', descripcion='Devuelve el eco de un texto (herramienta de prueba).',
             parametros={'texto': {'type': 'string', 'description': 'Texto a repetir.'}},
             requeridos=['texto'], nivel='lectura', categoria='general')
def _h_prueba_leer(self, texto):
    return {'eco': texto, 'usuario': self.env.user.login}


@herramienta(nombre='prueba_crear_contacto', descripcion='Crea un contacto de prueba (palabra clave: zanahoria).',
             parametros={'nombre': {'type': 'string', 'description': 'Nombre.'}},
             requeridos=['nombre'], nivel='construccion', categoria='clientes')
def _h_prueba_crear_contacto(self, nombre):
    return {'creado': self.env['res.partner'].create({'name': nombre}).display_name}


@herramienta(nombre='prueba_sensible', descripcion='Crea un contacto importante. Necesita confirmación.',
             parametros={'nombre': {'type': 'string', 'description': 'Nombre.'}},
             requeridos=['nombre'], nivel='sensible', categoria='clientes')
def _h_prueba_sensible(self, nombre):
    socio = self.env['res.partner'].create({'name': nombre})
    return {'creado': socio.display_name, 'abrir': {'modelo': 'res.partner', 'res_id': socio.id,
                                                    'titulo': socio.display_name}}


@herramienta(nombre='prueba_abrir', descripcion='Devuelve destinos para abrir (prueba).',
             parametros={'url': {'type': 'boolean', 'description': 'Si es un enlace.'}},
             nivel='lectura', categoria='ventas')
def _h_prueba_abrir(self, url=False):
    if url:
        return {'mensaje': 'Listo', 'abrir_url': 'https://wa.me/50760261919'}
    return {'abrir': [{'modelo': 'res.partner', 'dominio': [['is_company', '=', True]], 'titulo': 'Empresas'}]}


@herramienta(nombre='prueba_admin', descripcion='Solo para administradores (prueba de grupos).',
             nivel='lectura', categoria='usuarios', grupos=('base.group_system',))
def _h_prueba_admin(self):
    return {'ok': True}


@herramienta(nombre='prueba_falla', descripcion='Siempre falla con un error de uso.',
             nivel='lectura', categoria='ventas')
def _h_prueba_falla(self):
    raise BrianError('Dato inválido: prueba con otro.')


@herramienta(nombre='eliminar_prueba', descripcion='Borra un registro de prueba de cualquier modelo.',
             parametros={'modelo': {'type': 'string', 'description': 'Modelo.'},
                         'campos': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Campos.'}},
             nivel='construccion', categoria='contabilidad')
def _h_eliminar_prueba(self, modelo=None, campos=None):
    return {'hecho': True}


HERRAMIENTAS_PRUEBA = {f.__name__: f for f in (
    _h_prueba_leer, _h_prueba_crear_contacto, _h_prueba_sensible, _h_prueba_abrir, _h_prueba_admin, _h_prueba_falla,
    _h_eliminar_prueba)}


class BrianCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        clase = type(cls.env['brian.herramientas'])
        for nombre, funcion in HERRAMIENTAS_PRUEBA.items():
            parche = patch.object(clase, nombre, funcion, create=True)
            parche.start()
            cls.addClassCleanup(parche.stop)
        entorno = patch.dict(os.environ, {k: '' for k in (
            'BRIAN_PROVEEDOR', 'BRIAN_MODELO', 'BRIAN_API_KEY', 'BRIAN_BASE_URL', 'BRIAN_HERRAMIENTAS_MAX')})
        entorno.start()
        cls.addClassCleanup(entorno.stop)
        espera = patch.object(proveedores, 'ESPERA_BASE', 0)
        espera.start()
        cls.addClassCleanup(espera.stop)

        cls.env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'prueba')
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)
        cls.usuario = Usuarios.create({
            'name': 'Vendedora Prueba', 'login': 'brian_vendedora',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref('base.group_partner_manager').id])],
        })
        cls.otro = Usuarios.create({
            'name': 'Otro Prueba', 'login': 'brian_otro',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.jefe = Usuarios.create({
            'name': 'Jefa Prueba', 'login': 'brian_jefa',
            'group_ids': [(6, 0, [cls.env.ref('base.group_system').id,
                                  cls.env.ref('base.group_partner_manager').id])],
        })

    def setUp(self):
        super().setUp()
        proveedores.fijar_guion([])

    def herramientas(self, usuario=None):
        return self.env['brian.herramientas'].with_user(usuario or self.usuario)
