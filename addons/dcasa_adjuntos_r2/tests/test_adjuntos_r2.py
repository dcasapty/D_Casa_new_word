"""Adjuntos en R2 con un S3 falso en memoria (el cliente se reemplaza en la frontera:
``r2.configuracion`` y ``r2.cliente``). moto no está en el entorno de tests de Odoo; el CI
de la imagen sí lo ejercita contra moto real (job «docker»)."""
import hashlib
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .. import r2
from ..models.ir_attachment import PARAM_DIAS, PARAM_GC_ULTIMA

LOGGER = 'odoo.addons.dcasa_adjuntos_r2'
_CONFIGURACION_REAL = r2.configuracion
CONF = {
    'endpoint': 'https://s3.falso', 'bucket': 'dcasa-test', 'access_key_id': 'k',
    'secret_access_key': 's', 'region': 'auto', 'verify_tls': True,
}


class ErrorS3(Exception):
    """Como botocore.exceptions.ClientError: el código va en ``response['Error']['Code']``."""

    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {'Error': {'Code': codigo}}


class Cuerpo:
    def __init__(self, datos):
        self._datos = datos

    def read(self):
        return self._datos


class S3Falso:
    def __init__(self):
        self.objetos = {}  # (bucket, clave) -> [bytes, LastModified]
        self.fallar = None  # código de error a lanzar en la próxima operación
        self.puts = 0
        self.borrados = []

    def _quizas_fallar(self):
        if self.fallar:
            raise ErrorS3(self.fallar)

    def put_object(self, Bucket, Key, Body, **_kw):
        self._quizas_fallar()
        self.puts += 1
        self.objetos[Bucket, Key] = [bytes(Body), datetime.now().astimezone()]

    def get_object(self, Bucket, Key, Range=None):
        self._quizas_fallar()
        if (Bucket, Key) not in self.objetos:
            raise ErrorS3('NoSuchKey')
        datos = self.objetos[Bucket, Key][0]
        if Range:
            fin = int(Range.split('-')[1])
            datos = datos[:fin + 1]
        return {'Body': Cuerpo(datos)}

    def delete_objects(self, Bucket, Delete):
        self._quizas_fallar()
        for objeto in Delete['Objects']:
            self.objetos.pop((Bucket, objeto['Key']), None)
            self.borrados.append(objeto['Key'])
        return {}

    def get_paginator(self, _nombre):
        s3 = self

        class Paginador:
            def paginate(self, Bucket, Prefix):
                s3._quizas_fallar()
                contenido = [{'Key': k, 'LastModified': v[1], 'Size': len(v[0])}
                             for (b, k), v in sorted(s3.objetos.items()) if b == Bucket and k.startswith(Prefix)]
                yield {'Contents': contenido[:2]}
                yield {'Contents': contenido[2:]}

        return Paginador()

    def envejecer(self, clave, dias):
        self.objetos[CONF['bucket'], clave][1] = datetime.now().astimezone() - timedelta(days=dias)


def sha(datos):
    return hashlib.sha1(datos).hexdigest()


@tagged('post_install', '-at_install')
class TestAdjuntosR2(TransactionCase):

    def setUp(self):
        super().setUp()
        self.s3 = S3Falso()
        r2.cache.limpiar()
        self.addCleanup(r2.cache.limpiar)
        for objetivo in (patch.object(r2, 'configuracion', return_value=CONF),
                         patch.object(r2, 'cliente', return_value=self.s3)):
            objetivo.start()
            self.addCleanup(objetivo.stop)
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.set_param('ir_attachment.location', 'r2')
        self.Adjunto = self.env['ir.attachment']

    def crear(self, datos, nombre='foto.jpg'):
        return self.Adjunto.create({'name': nombre, 'raw': datos})

    def releer(self, adjunto):
        r2.cache.limpiar()
        adjunto.invalidate_recordset()
        return adjunto.raw

    # ---------------------------------------------------------------- básico
    def test_escribir_y_leer(self):
        datos = b'sofa de tres puestos' * 50
        adjunto = self.crear(datos)
        clave = f'adjuntos/{sha(datos)[:2]}/{sha(datos)}'
        self.assertEqual(adjunto.store_fname, f'r2://{clave}')
        self.assertFalse(adjunto.db_datas)
        self.assertEqual(self.s3.objetos[CONF['bucket'], clave][0], datos)
        self.assertEqual(self.releer(adjunto), datos)
        # Lectura parcial (Odoo la usa para adivinar el tipo).
        self.assertEqual(self.Adjunto._file_read(adjunto.store_fname, 4), datos[:4])

    def test_deduplica_por_checksum_y_refresca_lastmodified(self):
        datos = b'misma foto'
        primero = self.crear(datos, 'a.jpg')
        clave = r2.clave_de(primero.store_fname)
        self.s3.envejecer(clave, 100)
        segundo = self.crear(datos, 'b.jpg')
        self.assertEqual(primero.store_fname, segundo.store_fname)
        self.assertEqual(len(self.s3.objetos), 1)
        edad = datetime.now().astimezone() - self.s3.objetos[CONF['bucket'], clave][1]
        self.assertLess(edad, timedelta(minutes=5), 'reusar un contenido debe renovar LastModified')

    def test_desvincular_no_borra_en_r2(self):
        adjunto = self.crear(b'factura vieja')
        clave = r2.clave_de(adjunto.store_fname)
        adjunto.unlink()
        self.assertIn((CONF['bucket'], clave), self.s3.objetos)
        # Tampoco al cambiar el contenido.
        otro = self.crear(b'v1')
        clave_v1 = r2.clave_de(otro.store_fname)
        otro.raw = b'v2'
        self.assertIn((CONF['bucket'], clave_v1), self.s3.objetos)
        self.assertEqual(self.releer(otro), b'v2')
        self.assertEqual(self.s3.borrados, [])

    def test_falla_la_subida_no_guarda_nada(self):
        self.s3.fallar = 'InternalError'
        with self.assertRaises(UserError), self.assertLogs(LOGGER, 'ERROR') as logs:
            self.crear(b'no debe quedar', 'perdida.pdf')
        self.s3.fallar = None
        self.assertFalse(self.Adjunto.search([('name', '=', 'perdida.pdf')]))
        self.assertIn('no se pudo subir', logs.output[0])

    def test_error_de_lectura_no_es_archivo_vacio(self):
        adjunto = self.crear(b'catalogo')
        r2.cache.limpiar()
        adjunto.invalidate_recordset()
        self.s3.fallar = 'SlowDown'
        with self.assertRaises(UserError), self.assertLogs(LOGGER, 'ERROR'):
            adjunto.raw  # noqa: B018
        self.s3.fallar = None
        # Un objeto que falta sí devuelve vacío (como un archivo que falta en el filestore).
        self.s3.objetos.clear()
        with self.assertLogs(LOGGER, 'ERROR') as logs:
            self.assertEqual(self.releer(adjunto), b'')
        self.assertIn('falta el objeto', logs.output[0])

    def test_stream_http_desde_r2(self):
        adjunto = self.crear(b'\x89PNG imagen', 'logo.png')
        stream = adjunto._to_http_stream()
        self.assertEqual(stream.type, 'data')
        self.assertEqual(stream.data, b'\x89PNG imagen')
        self.assertEqual(stream.etag, adjunto.checksum)

    def test_sin_credenciales_usa_la_base(self):
        sin_r2 = {k: v for k, v in os.environ.items() if not k.startswith('DCASA_ADJUNTOS_R2_')}
        with patch.object(r2, 'configuracion', _CONFIGURACION_REAL), patch.dict(os.environ, sin_r2, clear=True):
            self.assertEqual(self.Adjunto._storage(), 'db')
            adjunto = self.crear(b'en la base')
            self.assertFalse(adjunto.store_fname)
            self.assertEqual(adjunto.db_datas, b'en la base')
        self.assertEqual(self.s3.puts, 0)

    def test_configuracion_desde_el_entorno(self):
        self.assertIsNone(_CONFIGURACION_REAL({}))
        self.assertIsNone(_CONFIGURACION_REAL({'DCASA_ADJUNTOS_R2_ENDPOINT': 'https://x'}))
        completo = {variable: 'x' for variable in r2.VARIABLES.values()}
        with patch.object(r2, 'boto3_disponible', return_value=False), self.assertLogs(LOGGER, 'ERROR'):
            self.assertIsNone(_CONFIGURACION_REAL(completo))
        with patch.object(r2, 'boto3_disponible', return_value=True):
            conf = _CONFIGURACION_REAL({**completo, 'DCASA_ADJUNTOS_R2_VERIFY_TLS': 'n'})
        self.assertEqual((conf['bucket'], conf['region'], conf['verify_tls']), ('x', 'auto', False))

    # ----------------------------------------------------------- migración
    def test_migrar_de_la_base_a_r2_y_de_vuelta(self):
        self.icp.set_param('ir_attachment.location', 'db')
        datos = [b'foto %d' % i for i in range(5)]
        adjuntos = self.Adjunto.browse([self.crear(d, f'm{i}.jpg').id for i, d in enumerate(datos)])
        self.assertTrue(all(a.db_datas and not a.store_fname for a in adjuntos))

        self.icp.set_param('ir_attachment.location', 'r2')
        self.Adjunto._dcasa_r2_migrar_todo('r2', lote=2, confirmar=False)
        adjuntos.invalidate_recordset()
        for adjunto, contenido in zip(adjuntos, datos, strict=True):
            self.assertTrue(r2.es_r2(adjunto.store_fname))
            self.assertFalse(adjunto.db_datas)
            self.assertEqual(self.releer(adjunto), contenido)
        self.assertEqual(self.Adjunto._dcasa_r2_migrar('r2', desde_id=adjuntos[0].id - 1)[0], 0)

        # Emergencia: todo de vuelta a la base. Los objetos siguen en R2 (restauraciones).
        self.icp.set_param('ir_attachment.location', 'db')
        objetos = len(self.s3.objetos)
        self.Adjunto._dcasa_r2_migrar_todo('db', lote=2, confirmar=False)
        adjuntos.invalidate_recordset()
        for adjunto, contenido in zip(adjuntos, datos, strict=True):
            self.assertFalse(adjunto.store_fname)
            self.assertEqual(adjunto.db_datas, contenido)
        self.assertEqual(len(self.s3.objetos), objetos)

    def test_migrar_de_vuelta_no_pisa_con_vacio(self):
        adjunto = self.crear(b'contrato firmado')
        fname = adjunto.store_fname
        self.s3.objetos.clear()
        r2.cache.limpiar()
        self.icp.set_param('ir_attachment.location', 'db')
        with self.assertLogs(LOGGER, 'ERROR'):
            _total, fallidos = self.Adjunto._dcasa_r2_migrar_todo('db', confirmar=False)
        self.assertEqual(fallidos, 1)
        adjunto.invalidate_recordset()
        self.assertEqual(adjunto.store_fname, fname, 'sin el objeto, la fila no se toca')
        with self.assertRaises(UserError), self.assertLogs(LOGGER, 'ERROR'):
            self.Adjunto._dcasa_r2_migrar('db', estricto=True)

    def test_cron_sigue_a_location(self):
        self.icp.set_param('ir_attachment.location', 'db')
        adjunto = self.crear(b'sigue la location', 'cron.txt')
        self.icp.set_param('ir_attachment.location', 'r2')
        self.Adjunto._dcasa_r2_cron_migrar(confirmar=False)
        adjunto.invalidate_recordset()
        self.assertTrue(r2.es_r2(adjunto.store_fname))
        # DCASA_ADJUNTOS=db con credenciales: el cron los trae de vuelta.
        self.icp.set_param('ir_attachment.location', 'db')
        self.Adjunto._dcasa_r2_cron_migrar(confirmar=False)
        adjunto.invalidate_recordset()
        self.assertFalse(adjunto.store_fname)
        self.assertEqual(adjunto.db_datas, b'sigue la location')
        # Sin credenciales (CI): no hace nada.
        with patch.object(r2, 'configuracion', return_value=None):
            self.assertEqual(self.Adjunto._dcasa_r2_cron_migrar(confirmar=False), (0, 0))

    def test_migracion_sin_credenciales_se_niega(self):
        with patch.object(r2, 'configuracion', return_value=None), self.assertRaises(UserError):
            self.Adjunto._dcasa_r2_migrar('r2')

    # ----------------------------------------------------------- recolección
    def _gc(self, ahora=None):
        return self.Adjunto._dcasa_r2_gc(confirmar=False, ahora=ahora)

    def test_gc_solo_borra_lo_huerfano_y_viejo(self):
        self.icp.set_param(PARAM_GC_ULTIMA, '')
        en_uso = self.crear(b'en uso')
        huerfano_viejo = self.crear(b'borrado hace mucho')
        huerfano_reciente = self.crear(b'borrado hace poco')
        claves = {n: r2.clave_de(a.store_fname) for n, a in
                  (('uso', en_uso), ('viejo', huerfano_viejo), ('reciente', huerfano_reciente))}
        (huerfano_viejo | huerfano_reciente).unlink()
        self.s3.objetos[CONF['bucket'], 'pgbackrest/archive/dcasa/x'] = [b'wal', datetime.now().astimezone()]
        for clave in claves.values():
            self.s3.envejecer(clave, 100)
        self.s3.envejecer('pgbackrest/archive/dcasa/x', 400)
        self.s3.envejecer(claves['reciente'], 10)

        hoy = fields.Datetime.now()
        # 1.ª corrida: marca los huérfanos, no borra nada (aún no sabe desde cuándo).
        self.assertEqual(self._gc(hoy - timedelta(days=50)), [])
        Huerfano = self.env['dcasa.adjunto.r2.huerfano']
        self.assertEqual(set(Huerfano.search([]).mapped('clave')), {claves['viejo'], claves['reciente']})
        # Corridas diarias: a los 50 días borra solo el viejo.
        for dias in range(49, -1, -1):
            borrados = self._gc(hoy - timedelta(days=dias))
            if dias > 5:
                self.assertEqual(borrados, [], dias)
        self.assertEqual(self.s3.borrados, [claves['viejo']])
        self.assertIn((CONF['bucket'], claves['uso']), self.s3.objetos)
        self.assertIn((CONF['bucket'], claves['reciente']), self.s3.objetos)
        self.assertIn((CONF['bucket'], 'pgbackrest/archive/dcasa/x'), self.s3.objetos)
        self.assertNotIn(claves['viejo'], Huerfano.search([]).mapped('clave'))

    def test_gc_reusar_contenido_lo_salva(self):
        self.icp.set_param(PARAM_GC_ULTIMA, '')
        vuelve, control = self.crear(b'vuelve'), self.crear(b'control')
        claves = [r2.clave_de(a.store_fname) for a in (vuelve, control)]
        (vuelve | control).unlink()
        for clave in claves:
            self.s3.envejecer(clave, 100)
        hoy = fields.Datetime.now()
        for dias in range(60, 15, -1):
            self.assertEqual(self._gc(hoy - timedelta(days=dias)), [], dias)
        # Alguien vuelve a subir lo mismo y lo borra antes del próximo GC: LastModified se
        # renueva y ese contenido puede estar en un respaldo reciente.
        self.crear(b'vuelve').unlink()
        self.assertEqual(self._gc(hoy - timedelta(days=15)), [claves[1]])

    def test_gc_sin_corridas_recientes_reinicia_la_cuenta(self):
        adjunto = self.crear(b'olvidado')
        clave = r2.clave_de(adjunto.store_fname)
        adjunto.unlink()
        self.s3.envejecer(clave, 200)
        hoy = fields.Datetime.now()
        self.icp.set_param(PARAM_GC_ULTIMA, '')
        self._gc(hoy - timedelta(days=100))
        # 100 días sin GC: la marca vieja no vale, se empieza de nuevo.
        self.assertEqual(self._gc(hoy), [])
        marca = self.env['dcasa.adjunto.r2.huerfano'].search([('clave', '=', clave)])
        self.assertEqual(marca.visto_desde, hoy)

    def test_dias_de_retencion(self):
        self.assertEqual(self.Adjunto._dcasa_r2_dias_retencion(), 45)
        self.icp.set_param(PARAM_DIAS, '90')
        self.assertEqual(self.Adjunto._dcasa_r2_dias_retencion(), 90)
        self.icp.set_param(PARAM_DIAS, '3')
        self.assertEqual(self.Adjunto._dcasa_r2_dias_retencion(), 31)

    def test_store_fname_fuera_del_prefijo(self):
        with self.assertRaises(r2.ErrorR2):
            r2.clave_de('r2://pgbackrest/archive/x')
        with self.assertRaises(r2.ErrorR2):
            r2.clave_de('r2://adjuntos/../pgbackrest/x')

    def test_cache_lru_por_bytes(self):
        cache = r2.Cache(maximo_bytes=10, maximo_objeto=6)
        cache.guardar('a', b'12345')
        cache.guardar('b', b'12345')
        cache.obtener('a')
        cache.guardar('c', b'123')
        self.assertIsNone(cache.obtener('b'))
        self.assertEqual(cache.obtener('a'), b'12345')
        cache.guardar('grande', b'1234567')
        self.assertIsNone(cache.obtener('grande'))
