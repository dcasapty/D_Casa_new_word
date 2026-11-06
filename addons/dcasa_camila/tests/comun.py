"""Lo común de las pruebas de Camila. NUNCA se llama a Resend de verdad: ``requests.request`` es un Resend falso en
memoria (``ResendFalso``) y ``requests.post`` falla si algo lo llama sin que la prueba lo pida. Datos inventados obvios
(ZZCM…, correos @example.com)."""
import base64
import io
import os
import re
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.parse import unquote

from PIL import Image

from odoo import Command
from odoo.addons.dcasa_brian.models import proveedores as P
from odoo.tests import TransactionCase

from ..models import resend_campanas as RC

CLAVE_CAMPANAS = 're_campanas_prueba_123'
CLAVE_CORREO = 're_correo_prueba_456'


def foto(color=(19, 64, 177)):
    imagen = Image.new('RGB', (320, 240), color)
    salida = io.BytesIO()
    imagen.save(salida, format='JPEG')
    return base64.b64encode(salida.getvalue()).decode()


def respuesta(estado=200, cuerpo=None, cabeceras=None):
    r = MagicMock()
    r.status_code = estado
    r.json.return_value = {} if cuerpo is None else cuerpo
    r.text = ''
    r.headers = cabeceras or {}
    return r


class ResendFalso:
    """Un Resend en memoria con lo que usa Camila (segmentos, contactos, broadcasts y destinatarios)."""

    URL = RC.URL

    def __init__(self):
        self.segmentos = {}
        self.contactos = {}
        self.broadcasts = {}
        self.destinatarios = {}
        self.llamadas = []
        self.fallar = []          # [(método, regex de la ruta, estado, mensaje)]
        self._n = 0

    def _id(self, prefijo):
        self._n += 1
        return f'{prefijo}-{self._n:04d}'

    def contacto(self, correo, suscrito=True, segmentos=()):
        """Deja un contacto como si ya estuviera en Resend."""
        self.contactos[correo] = {'id': self._id('ct'), 'email': correo, 'unsubscribed': not suscrito,
                                  'segmentos': set(segmentos)}

    def en_segmento(self, segmento):
        return {c['email']: c['unsubscribed'] for c in self.contactos.values() if segmento in c['segmentos']}

    def __call__(self, metodo, url, json=None, params=None, headers=None, timeout=None):
        assert url.startswith(self.URL), url
        assert headers['Authorization'] == f'Bearer {CLAVE_CAMPANAS}'
        ruta = url[len(self.URL):]
        self.llamadas.append((metodo, ruta, json, params))
        for f_metodo, f_ruta, f_estado, f_mensaje in self.fallar:
            if metodo == f_metodo and re.search(f_ruta, ruta):
                return respuesta(f_estado, {'message': f_mensaje})
        return self._atender(metodo, ruta, json or {}, params or {})

    def _pagina(self, filas, params):
        despues = params.get('after')
        if despues:
            ids = [f['id'] for f in filas]
            filas = filas[ids.index(despues) + 1:]
        limite = int(params.get('limit') or 20)
        return respuesta(200, {'object': 'list', 'has_more': len(filas) > limite, 'data': filas[:limite]})

    def _atender(self, metodo, ruta, cuerpo, params):  # noqa: PLR0911, PLR0912
        if ruta == '/segments' and metodo == 'GET':
            return respuesta(200, {'data': [{'id': i, 'name': n} for i, n in self.segmentos.items()]})
        if ruta == '/segments' and metodo == 'POST':
            nuevo = self._id('seg')
            self.segmentos[nuevo] = cuerpo['name']
            return respuesta(200, {'object': 'segment', 'id': nuevo, 'name': cuerpo['name']})
        encontrado = re.fullmatch(r'/segments/([^/]+)/contacts', ruta)
        if encontrado and metodo == 'GET':
            filas = [{'id': c['id'], 'email': c['email'], 'unsubscribed': c['unsubscribed']}
                     for c in self.contactos.values() if encontrado.group(1) in c['segmentos']]
            return self._pagina(filas, params)
        if ruta == '/contacts' and metodo == 'POST':
            correo = cuerpo['email']
            if correo in self.contactos:
                return respuesta(422, {'message': 'Contact already exists'})
            self.contacto(correo, segmentos=[s['id'] for s in cuerpo.get('segments') or []])
            return respuesta(200, {'object': 'contact', 'id': self.contactos[correo]['id']})
        encontrado = re.fullmatch(r'/contacts/([^/]+)/segments/([^/]+)', ruta)
        if encontrado:
            contacto = self._contacto_de(encontrado.group(1))
            if not contacto:
                return respuesta(404, {'message': 'Contact not found'})
            if metodo == 'POST':
                contacto['segmentos'].add(encontrado.group(2))
            else:
                contacto['segmentos'].discard(encontrado.group(2))
            return respuesta(200, {'id': encontrado.group(2)})
        encontrado = re.fullmatch(r'/contacts/([^/]+)', ruta)
        if encontrado and metodo == 'PATCH':
            contacto = self._contacto_de(encontrado.group(1))
            if not contacto:
                return respuesta(404, {'message': 'Contact not found'})
            contacto['unsubscribed'] = bool(cuerpo.get('unsubscribed'))
            return respuesta(200, {'object': 'contact', 'id': contacto['id']})
        if ruta == '/broadcasts' and metodo == 'POST':
            nuevo = self._id('bc')
            self.broadcasts[nuevo] = dict(cuerpo, status='draft')
            return respuesta(200, {'object': 'broadcast', 'id': nuevo})
        encontrado = re.fullmatch(r'/broadcasts/([^/]+)(/send|/recipients)?', ruta)
        if encontrado and encontrado.group(1) in self.broadcasts:
            broadcast = self.broadcasts[encontrado.group(1)]
            if encontrado.group(2) == '/send' and metodo == 'POST':
                broadcast['status'] = 'queued'
                broadcast['enviado_a'] = sorted(c for c, baja in self.en_segmento(broadcast['segment_id']).items()
                                                if not baja)
                return respuesta(200, {'id': encontrado.group(1)})
            if encontrado.group(2) == '/recipients' and metodo == 'GET':
                # Un número (cuántos, con correos inventados) o la lista de correos de ese evento.
                valor = self.destinatarios.get((encontrado.group(1), params.get('type')), 0)
                correos = valor if isinstance(valor, list) else [f'r{i}@example.com' for i in range(valor)]
                return self._pagina([{'id': f'r{i}', 'contact_id': None, 'email': correo}
                                     for i, correo in enumerate(correos)], params)
            if not encontrado.group(2) and metodo == 'GET':
                return respuesta(200, {'object': 'broadcast', 'id': encontrado.group(1),
                                       'status': broadcast['status']})
            if not encontrado.group(2) and metodo == 'DELETE':
                if broadcast['status'] not in ('draft', 'scheduled'):
                    return respuesta(422, {'message': 'Only draft or scheduled broadcasts can be deleted'})
                del self.broadcasts[encontrado.group(1)]
                return respuesta(200, {'object': 'broadcast', 'id': encontrado.group(1), 'deleted': True})
        return respuesta(404, {'message': 'not found'})

    def _contacto_de(self, clave):
        """El contacto por su correo (tal como se escribió en Resend) o por su id, como la API de Resend."""
        clave = unquote(clave)
        if clave in self.contactos:
            return self.contactos[clave]
        return next((c for c in self.contactos.values() if c['id'] == clave), None)


class CamilaComun(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.website = cls.env['dcasa.camila']._sitio()
        cls.website.write({'domain': 'https://tienda.example.com', 'dcasa_whatsapp_number': '+507 6000-0000'})
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos, correo):
            return Users.create({
                'name': login.replace('_', ' ').title(), 'login': login, 'password': login, 'email': correo,
                'tz': 'America/Panama',
                'group_ids': [Command.set([cls.env.ref('base.group_user').id] + [cls.env.ref(g).id for g in grupos])]})

        cls.marketing = usuario('zzcm_marketing', ['dcasa_marketing.group_marketing'], 'marketing.zzcm@example.com')
        cls.gerencia = usuario('zzcm_gerencia', ['dcasa_base.group_gerencia'], 'gerencia.zzcm@example.com')
        cls.vendedora = usuario('zzcm_vendedora', ['dcasa_base.group_vendedora'], 'vendedora.zzcm@example.com')
        cls.categoria = cls.env['product.category'].create({'name': 'ZZCM Salas de prueba'})
        cls.bodega = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.productos = cls.env['product.template']
        for i in range(8):
            cls.productos |= cls.producto(f'ZZCM SOFÁ DE PRUEBA {i}', precio=100.0 + i * 10)
        # Solo los productos de la prueba se pueden ofrecer (la base de pruebas trae el catálogo con existencias).
        cls.env['product.template'].search([('is_published', '=', True), ('id', 'not in', cls.productos.ids)]).write(
            {'is_published': False})
        Partner = cls.env['res.partner']
        cls.ana = Partner.create({'name': 'Ana Zzcm', 'email': 'ana.zzcm@example.com', 'phone': '6000-1001'})
        cls.beto = Partner.create({'name': 'Beto Zzcm', 'email': 'beto.zzcm@example.com', 'phone': '6000-1002'})
        cls.carla = Partner.create({'name': 'Carla Zzcm', 'email': 'carla.zzcm@example.com', 'phone': '6000-1003'})

    @classmethod
    def producto(cls, nombre, precio=100.0, stock=3, con_foto=True, publicado=True):
        plantilla = cls.env['product.template'].create({
            'name': nombre, 'list_price': precio, 'is_storable': True, 'sale_ok': True, 'type': 'consu',
            'categ_id': cls.categoria.id, 'taxes_id': [Command.clear()], 'is_published': publicado,
            'image_1920': foto() if con_foto else False,
        })
        if stock:
            cls.env['stock.quant']._update_available_quantity(
                plantilla.product_variant_id, cls.bodega.lot_stock_id, stock)
        return plantilla

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'DCASA_ENTORNO': 'produccion'})
        entorno.start()
        self.addCleanup(entorno.stop)
        for variable in ('RESEND_CAMPANAS_API_KEY', 'RESEND_API_KEY'):
            os.environ.pop(variable, None)
        self.resend = ResendFalso()
        for parche in (patch('requests.request', self.resend),
                       patch('requests.post', MagicMock(side_effect=AssertionError('requests.post no debe llamarse'))),
                       patch.object(RC, 'PAUSA', 0), patch.object(P, 'ESPERA_BASE', 0)):
            parche.start()
            self.addCleanup(parche.stop)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('dcasa_brian.proveedor', 'prueba')
        ICP.set_param('dcasa_brian.modelo', 'prueba')
        P.fijar_guion([])
        self.Camila = self.env['dcasa.camila']

    # ------------------------------------------------------------------

    def con_clave(self):
        parche = patch.dict(os.environ, {'RESEND_CAMPANAS_API_KEY': CLAVE_CAMPANAS})
        parche.start()
        self.addCleanup(parche.stop)

    def permiso(self, *fichas, origen='tienda'):
        for ficha in fichas:
            ficha.sudo()._dcasa_promos_registrar(origen)

    def guion_ia(self, asunto='Lo nuevo para tu sala', entrada='Llegaron muebles que te van a gustar.', lineas=None):
        """Lo que contesta la IA de prueba (el proveedor «prueba» de Brian)."""
        import json

        P.fijar_guion([json.dumps({'asunto': asunto, 'entrada': entrada, 'lineas': lineas or {}})])

    def armar(self, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).armar()

    @contextmanager
    def correo_transaccional(self):
        """La clave de los correos de siempre y ``requests.post`` que contesta como Resend (para la prueba)."""
        post = MagicMock(return_value=respuesta(200, {'id': 'email-1'}))
        servidor = type(self.env['ir.mail_server'])
        with patch.dict(os.environ, {'RESEND_API_KEY': CLAVE_CORREO}), patch('requests.post', post), \
                patch.object(servidor, '_disable_send', return_value=False):
            yield post
