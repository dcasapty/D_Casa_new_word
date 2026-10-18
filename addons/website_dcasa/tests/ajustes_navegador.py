"""Guardar Ajustes como el navegador, siendo una administradora sin el grupo «Editor y diseñador» del sitio.

Lo usan las pruebas de este módulo y las de otros con su propia sección de Ajustes (dcasa_correo, dcasa_interfaz).
Ver test_ajustes_sin_disenador.py y models/res_config_settings.py.
"""
from lxml import etree

from odoo import Command
from odoo.tests import HttpCase, new_test_user

GRUPOS_EDITOR = ('website.group_website_designer', 'website.group_website_restricted_editor')
SOLO_LECTURA = ('1', 'true', 'True')


def sitio_por_codigo(env):
    """Lo que hace dcasa_interfaz en producción (``dcasa.sitio._sitio_por_codigo``): nadie es editor ni diseñador.

    Se repite aquí para no depender de ese módulo (website_dcasa no lo necesita para instalarse).
    """
    grupos = env['res.groups'].browse([env.ref(x).id for x in GRUPOS_EDITOR])
    implicadores = env['res.groups'].search([('implied_ids', 'in', grupos.ids)]) - grupos
    implicadores.write({'implied_ids': [Command.unlink(g.id) for g in grupos]})
    usuarios = env['res.users'].with_context(active_test=False).search([('group_ids', 'in', grupos.ids)])
    usuarios.write({'group_ids': [Command.unlink(g.id) for g in grupos]})


class GuardarAjustesComoElNavegador(HttpCase):
    """Abre Ajustes y pulsa «Guardar» con las mismas llamadas del cliente web, sin navegador.

    El cliente arma el registro nuevo con el onchange inicial, manda en ``web_save`` todos los campos de la vista que
    no son de solo lectura (más lo que la persona cambió) y después llama al botón ``execute``.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sitio_por_codigo(cls.env)
        cls.duena = new_test_user(cls.env, login='ajustes_duena', name='Dueña de Prueba',
                                  groups='base.group_user,base.group_system')

    def _rpc(self, ruta, modelo, metodo, args, kwargs=None):
        respuesta = self.opener.post(f'{self.base_url()}/web/dataset/{ruta}/{modelo}/{metodo}', json={
            'id': 1, 'jsonrpc': '2.0', 'method': 'call',
            'params': {'model': modelo, 'method': metodo, 'args': args, 'kwargs': kwargs or {}},
        }, timeout=120)
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        if 'error' in cuerpo:
            raise AssertionError(f"{metodo}: {cuerpo['error']['data']['message']}")
        return cuerpo.get('result')

    @staticmethod
    def _campos_de_la_vista(arch):
        """Los ``<field>`` del formulario de Ajustes (no los de una lista o un formulario dentro de un campo)."""
        raiz = etree.fromstring(arch)
        for nodo in raiz.iter('field'):
            if not any(a.tag in ('list', 'kanban', 'form') for a in nodo.iterancestors() if a is not raiz):
                yield nodo

    @staticmethod
    def _para_escribir(campo, valor):
        if campo['type'] == 'many2one':
            return valor['id'] if isinstance(valor, dict) else valor
        if campo['type'] in ('one2many', 'many2many'):
            ids = []
            for item in valor or []:
                if isinstance(item, dict):
                    ids.append(item['id'])
                elif isinstance(item, int):
                    ids.append(item)
                elif item[0] == Command.SET:
                    ids.extend(item[2])
                elif item[0] in (Command.LINK, Command.UPDATE):
                    ids.append(item[1])
            return [Command.set(ids)]
        return valor

    def guardar_ajustes(self, login, cambios=None):
        """Entra como ``login`` (contraseña = login), cambia ``cambios`` y pulsa «Guardar». Devuelve el id guardado."""
        self.authenticate(login, login)
        modelo = 'res.config.settings'
        vista = self._rpc('call_kw', modelo, 'get_views', [], {'views': [[False, 'form']]})
        campos = vista['models'][modelo]['fields']
        especificacion, solo_lectura = {}, set()
        for nodo in self._campos_de_la_vista(vista['views']['form']['arch']):
            nombre = nodo.get('name')
            especificacion[nombre] = {'fields': {'display_name': {}}} if campos[nombre]['type'] == 'many2one' else {}
            atributo = nodo.get('readonly')
            if atributo in SOLO_LECTURA or (atributo is None and campos[nombre].get('readonly')):
                solo_lectura.add(nombre)
        for nombre in cambios or {}:
            self.assertIn(nombre, especificacion, f'{nombre} no está en la pantalla de Ajustes de {login}')
            self.assertNotIn(nombre, solo_lectura, f'{nombre} es de solo lectura en Ajustes')
        inicial = self._rpc('call_kw', modelo, 'onchange', [[], {}, [], especificacion])['value']
        valores = {nombre: self._para_escribir(campos[nombre], valor) for nombre, valor in inicial.items()
                   if nombre in especificacion and nombre not in solo_lectura}
        valores.update(cambios or {})
        guardado = self._rpc('call_kw', modelo, 'web_save', [[], valores], {'specification': {}})
        ajustes_id = guardado[0]['id']
        self._rpc('call_button', modelo, 'execute', [[ajustes_id]])
        return ajustes_id
