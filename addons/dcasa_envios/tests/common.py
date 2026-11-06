"""Lo común de las pruebas de envíos: el fixture sintético (lugares inventados, precios de juguete) y cargarlo.

Nada de aquí es la matriz ni la tarifa de la dueña: ``datos/fixture_envios.json`` lo dice en su primer renglón."""
import base64
import copy
import json
from pathlib import Path

from odoo.tests import TransactionCase, new_test_user

DATOS = Path(__file__).resolve().parent / 'datos'


def fixture():
    """Una copia nueva del fixture (cada prueba puede cambiarla)."""
    return copy.deepcopy(json.loads((DATOS / 'fixture_envios.json').read_text(encoding='utf-8')))


def como_html(datos):
    """El fixture con la forma del envios-dcasa.html (los tres bloques ``<script type="application/json">``)."""
    def bloque(ident, valor):
        texto = json.dumps(valor, ensure_ascii=False).replace('<', '\\u003c')
        return f'<script id="{ident}" type="application/json">{texto}</script>'
    return ('<!DOCTYPE html><html lang="es"><head><title>Envíos de prueba</title></head><body><main>…</main>'
            + bloque('ajustes', datos['ajustes']) + bloque('agregados-datos', datos.get('agregados') or [])
            + bloque('lugares', datos['lugares']) + '<script>(() => {})();</script></body></html>')


def importar(env, usuario, datos=None, formato='html', lugares=True, tarifa=True, nombre='envios-dcasa.html'):
    """Carga el fixture (o ``datos``) con el asistente, como ``usuario`` (Gerencia)."""
    datos = fixture() if datos is None else datos
    contenido = como_html(datos) if formato == 'html' else json.dumps(datos, ensure_ascii=False)
    asistente = env['dcasa.envio.importar'].with_user(usuario).create({
        'archivo': base64.b64encode(contenido.encode('utf-8')), 'nombre_archivo': nombre,
        'cargar_lugares': lugares, 'cargar_tarifa': tarifa,
    })
    asistente.action_cargar()
    return asistente


class EnviosComun(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='ger_envios', password='ger_envios', name='Gerencia Envíos',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.vendedora = new_test_user(cls.env, login='vend_envios_x', password='vend_envios_x',
                                      name='Vendedora Envíos', groups='base.group_user,dcasa_base.group_vendedora')
        cls.portal = new_test_user(cls.env, login='portal_envios', password='portal_envios', name='Cliente Portal',
                                   groups='base.group_portal')

    @classmethod
    def importar(cls, datos=None, usuario=None, formato='html', lugares=True, tarifa=True, nombre='envios-dcasa.html'):
        return importar(cls.env, usuario or cls.gerencia, datos=datos, formato=formato, lugares=lugares,
                        tarifa=tarifa, nombre=nombre)

    def lugar(self, nombre, **dominio):
        return self.env['dcasa.envio.lugar'].with_context(active_test=False).search(
            [('name', '=', nombre)] + [(k, '=', v) for k, v in dominio.items()])

    @property
    def tarifa(self):
        return self.env['dcasa.envio.tarifa'].search([], limit=1)
