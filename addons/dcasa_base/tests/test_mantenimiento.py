"""Barandas de costo: depuración y reporte mensuales (ronda 4, costos-y-limpieza §5)."""
import base64
import collections
import json
import os
import shutil
import tempfile
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_base import memoria
from odoo.addons.dcasa_base.models.mantenimiento import CRONS_ODOO, GB, PARAMETROS, DcasaMantenimiento
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL

DATOS = base64.b64encode(b'x' * 1000)
# El método sin parchear (los tests de vigilancia lo sustituyen en setUp).
AVISAR_ORIGINAL = DcasaMantenimiento._avisar_operacion


class _Comun(TransactionCase):

    def _envejecer(self, registro, dias):
        self.env.cr.execute(SQL('UPDATE %s SET create_date = %s WHERE id = %s', SQL.identifier(registro._table),
                                fields.Datetime.now() - timedelta(days=dias), registro.id))
        self.env.invalidate_all()


@tagged('post_install', '-at_install')
class TestDepuracionMensual(_Comun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mant = cls.env['dcasa.mantenimiento']
        cls.adjuntos = cls.env['ir.attachment'].sudo()

    def _adjunto(self, nombre, res_model, res_id, dias=30, **extra):
        adjunto = self.adjuntos.create({'name': nombre, 'datas': DATOS, 'res_model': res_model,
                                        'res_id': res_id, **extra})
        self._envejecer(adjunto, dias)
        return adjunto

    def _borrar_por_sql(self, registro):
        """Como un ON DELETE CASCADE de PostgreSQL: el ORM no se entera y el adjunto queda huérfano."""
        self.env.cr.execute(SQL('DELETE FROM %s WHERE id = %s', SQL.identifier(registro._table), registro.id))
        self.env.invalidate_all()

    def test_borra_huerfanos_y_respeta_lo_demas(self):
        vivo = self.env['res.partner'].create({'name': 'Cliente vivo'})
        muerto = self.env['res.partner'].create({'name': 'Cliente borrado por SQL'})
        con_vivo = self._adjunto('de un cliente vivo', 'res.partner', vivo.id)
        huerfano = self._adjunto('huérfano', 'res.partner', muerto.id)
        reciente = self._adjunto('huérfano reciente', 'res.partner', muerto.id, dias=1)
        binario = self._adjunto('campo binario', 'res.partner', muerto.id, res_field='image_1920')
        referenciado = self._adjunto('en un mensaje', 'res.partner', muerto.id)
        self.env['mail.message'].create({'body': 'con adjunto', 'model': 'res.partner', 'res_id': vivo.id,
                                         'attachment_ids': [(4, referenciado.id)]})
        self._borrar_por_sql(muerto)
        # Contabilidad, Socios, Brian y modelos desconocidos: nunca, aunque el registro no exista.
        factura = self._adjunto('PDF de factura', 'account.move', 2_000_000_000)
        libro = self._adjunto('libro de puntos', 'dcasa.movimiento', 2_000_000_000)
        accion = self._adjunto('acción de Brian', 'brian.accion', 2_000_000_000)
        desconocido = self._adjunto('modelo desinstalado', 'x_modulo.que_no_existe', 2_000_000_000)

        resumen = self.mant._depurar()

        self.assertFalse(huerfano.exists())
        self.assertEqual(resumen['adjuntos_huerfanos'], 1)
        self.assertEqual(resumen['bytes_liberados'], 1000)
        for adjunto in (con_vivo, reciente, binario, referenciado, factura, libro, accion, desconocido):
            self.assertTrue(adjunto.exists(), adjunto.name)

    def test_modelos_protegidos_configurables(self):
        muerto = self.env['res.partner'].create({'name': 'X'})
        huerfano = self._adjunto('huérfano', 'res.partner', muerto.id)
        self._borrar_por_sql(muerto)
        self.env['ir.config_parameter'].sudo().set_param('dcasa.limpieza.modelos_protegidos', 'res.partner, otro')
        self.mant._depurar()
        self.assertTrue(huerfano.exists())

    def test_umbral_de_dias_configurable(self):
        muerto = self.env['res.partner'].create({'name': 'X'})
        huerfano = self._adjunto('huérfano de 3 días', 'res.partner', muerto.id, dias=3)
        self._borrar_por_sql(muerto)
        self.mant._depurar()
        self.assertTrue(huerfano.exists())
        self.env['ir.config_parameter'].sudo().set_param('dcasa.limpieza.adjuntos_dias', '2')
        self.mant._depurar()
        self.assertFalse(huerfano.exists())

    def test_correos_fallidos_viejos(self):
        def correo(asunto, dias, estado='exception', **extra):
            mail = self.env['mail.mail'].sudo().create({'subject': asunto, 'body_html': '<p>x</p>',
                                                        'email_to': 'a@example.com', 'state': estado, **extra})
            self._envejecer(mail, dias)
            return mail

        viejo = correo('fallido viejo', 120)
        reciente = correo('fallido reciente', 10)
        pendiente = correo('pendiente viejo', 120, estado='outgoing')
        asiento = self.env['account.move'].create({'move_type': 'entry'})
        de_factura = correo('fallido de una factura', 120, model='account.move', res_id=asiento.id)

        resumen = self.mant._depurar()

        self.assertEqual(resumen['correos_fallidos'], 1)
        self.assertFalse(viejo.exists())
        for mail in (reciente, pendiente, de_factura):
            self.assertTrue(mail.exists(), mail.subject)

    def test_cron_deja_resumen(self):
        resumen = self.mant._cron_depurar()
        self.assertEqual(set(resumen), {'adjuntos_huerfanos', 'bytes_liberados', 'correos_fallidos'})
        registro = self.env['ir.logging'].sudo().search([('name', '=', 'dcasa.limpieza')], limit=1)
        self.assertIn('DCASA_LIMPIEZA', registro.message)

    def test_crons_mensuales_y_privados(self):
        for xmlid, metodo in (('dcasa_base.ir_cron_dcasa_depurar', '_cron_depurar'),
                              ('dcasa_base.ir_cron_dcasa_reporte_tamanos', '_cron_reporte_tamanos')):
            cron = self.env.ref(xmlid)
            self.assertTrue(cron.active)
            self.assertEqual((cron.interval_number, cron.interval_type), (1, 'months'))
            self.assertIn(metodo, cron.code)
            self.assertTrue(metodo.startswith('_'))


@tagged('post_install', '-at_install')
class TestReporteTamanos(_Comun):

    def test_reporte_sin_alerta(self):
        datos = self.env['dcasa.mantenimiento']._cron_reporte_tamanos()
        self.assertGreater(datos['base_bytes'], 0)
        self.assertLess(datos['base_bytes'], 0.7 * GB)
        self.assertLessEqual(len(datos['tablas_top10']), 10)
        self.assertIn('ir_attachment', datos['tablas_top10'])
        self.assertTrue(datos['adjuntos_por_modelo'])
        self.assertNotIn('alerta', datos)
        self.assertEqual(set(datos['memoria']), {'cgroup', 'procesos'})
        self.assertEqual(set(datos['memoria']['procesos']), {'odoo', 'postgres', 'otros'})
        registro = self.env['ir.logging'].sudo().search([('name', '=', 'dcasa.reporte_tamanos')], limit=1)
        self.assertIn('DCASA_METRICA', registro.message)

    def test_reporte_avisa_al_pasar_el_umbral(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa.reporte.alerta_gb', '0.000001')
        with self.assertLogs('odoo.addons.dcasa_base.models.mantenimiento', 'WARNING') as logs:
            datos = self.env['dcasa.mantenimiento']._cron_reporte_tamanos()
        self.assertIn('DCASA_ALERTA', datos['alerta'])
        self.assertIn('DCASA_ALERTA', logs.output[0])
        self.assertTrue(self.env['ir.logging'].sudo().search(
            [('name', '=', 'dcasa.reporte_tamanos'), ('level', '=', 'WARNING')]))

    def test_parametro_invalido_usa_el_defecto(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa.reporte.alerta_gb', 'mucho')
        datos = self.env['dcasa.mantenimiento']._cron_reporte_tamanos()
        self.assertNotIn('alerta', datos)


# cgroup de mentira: 1 GiB de límite, 0,9 GiB en uso de los que 0,1 GiB son caché → 80 % real.
CGROUP_80 = {'version': 2, 'current': 966367641, 'max': GB, 'anon': 858993459, 'file': 107374182,
             'kernel': 0, 'shmem': 0, 'eventos': {'oom': 0, 'oom_kill': 0, 'max': 0, 'high': 0}}
Uso = collections.namedtuple('usage', 'total used free')


@tagged('post_install', '-at_install')
class TestVigilanciaRecursos(_Comun):
    """Disco, memoria, base y OOM contra sus umbrales; el aviso va a Telegram sin repetirse."""

    def setUp(self):
        super().setUp()
        self.mant = self.env['dcasa.mantenimiento']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.avisos = []
        self.patch(DcasaMantenimiento, '_avisar_operacion', lambda m, texto: self.avisos.append(texto) or True)
        self.cgroup = dict(CGROUP_80)
        self.disco = Uso(100 * GB, 50 * GB, 50 * GB)
        self.patch(memoria, 'medir', lambda: {'cgroup': dict(self.cgroup), 'procesos': {}})
        self.patch(shutil, 'disk_usage', lambda ruta: self.disco)

    def test_sin_pasar_umbrales_no_avisa(self):
        datos = self.mant._cron_vigilar_recursos()
        self.assertEqual(datos['disco']['pct'], 50.0)
        self.assertEqual(datos['memoria_pct'], 80.0)
        self.assertEqual(datos['alertas'], {})
        self.assertEqual(self.avisos, [])

    def test_disco_sobre_el_umbral(self):
        self.disco = Uso(100 * GB, 81 * GB, 19 * GB)
        with self.assertLogs('odoo.addons.dcasa_base.models.mantenimiento', 'WARNING') as logs:
            datos = self.mant._cron_vigilar_recursos()
        self.assertEqual(datos['alertas'], {'disco': True})
        self.assertIn('DCASA_ALERTA el disco del contenedor va al 81 %', logs.output[0])
        self.assertEqual(len(self.avisos), 1)
        self.assertIn('el disco del contenedor va al 81 % (umbral 80 %): quedan 19.00 GB', self.avisos[0])
        self.assertTrue(self.env['ir.logging'].sudo().search(
            [('name', '=', 'dcasa.alerta'), ('level', '=', 'WARNING'), ('message', 'ilike', 'disco')]))

    def test_umbral_de_disco_configurable(self):
        self.disco = Uso(100 * GB, 81 * GB, 19 * GB)
        self.ICP.set_param('dcasa.alerta.disco_pct', '90')
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {})

    def test_memoria_real_descuenta_la_cache(self):
        # 95 % del límite en «current», pero 25 puntos son caché de archivos: 70 % real, sin aviso.
        self.cgroup.update(current=int(0.95 * GB), file=int(0.25 * GB))
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {})
        # Sin caché que descontar: 95 % real → aviso.
        self.cgroup.update(file=0)
        datos = self.mant._cron_vigilar_recursos()
        self.assertEqual(datos['alertas'], {'memoria': True})
        self.assertIn('la memoria en uso va al 95 % del límite (umbral 90 %)', self.avisos[0])

    def test_sin_limite_de_memoria_ni_disco_no_rompe(self):
        self.cgroup.update(max=None)
        self.patch(shutil, 'disk_usage', lambda ruta: (_ for _ in ()).throw(OSError('no hay disco')))
        datos = self.mant._cron_vigilar_recursos()
        self.assertIsNone(datos['memoria_pct'])
        self.assertIsNone(datos['disco']['pct'])
        self.assertEqual(datos['alertas'], {})

    def test_base_sobre_el_umbral_tambien_cada_hora(self):
        self.ICP.set_param('dcasa.reporte.alerta_gb', '0.000001')
        datos = self.mant._cron_vigilar_recursos()
        self.assertEqual(datos['alertas'], {'base': True})
        self.assertIn('la base pesa', self.avisos[0])

    def test_oom_solo_los_nuevos(self):
        self.cgroup['eventos'] = dict(self.cgroup['eventos'], oom_kill=2)
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {'oom': True})
        self.assertIn('mató 2 proceso(s)', self.avisos[0])
        # Mismo contador: nada nuevo. Sube a 3: un proceso más.
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {})
        self.cgroup['eventos'] = dict(self.cgroup['eventos'], oom_kill=3)
        self.ICP.set_param('dcasa.alerta.silencio_h', '0')
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {'oom': True})
        self.assertIn('mató 1 proceso(s)', self.avisos[-1])
        # El contenedor arrancó de nuevo (contador en 0): se olvida lo visto, sin aviso.
        self.cgroup['eventos'] = dict(self.cgroup['eventos'], oom_kill=0)
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {})
        self.assertEqual(self.ICP.get_param('dcasa.alerta.oom_visto'), '0')

    def test_el_mismo_aviso_no_se_repite_en_la_ventana_de_silencio(self):
        self.disco = Uso(100 * GB, 90 * GB, 10 * GB)
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {'disco': True})
        with self.assertLogs('odoo.addons.dcasa_base.models.mantenimiento', 'WARNING'):
            datos = self.mant._cron_vigilar_recursos()
        self.assertEqual(datos['alertas'], {'disco': False})  # registrado, no mandado
        self.assertEqual(len(self.avisos), 1)
        # Otro tipo de aviso sí sale; y pasada la ventana, el de disco vuelve a salir.
        self.cgroup.update(file=0)
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas'], {'disco': False, 'memoria': True})
        self.ICP.set_param('dcasa.alerta.enviada.disco',
                           fields.Datetime.to_string(fields.Datetime.now() - timedelta(hours=25)))
        self.assertEqual(self.mant._cron_vigilar_recursos()['alertas']['disco'], True)
        self.assertEqual(len(self.avisos), 3)

    def test_sin_canal_queda_en_el_log(self):
        self.patch(DcasaMantenimiento, '_avisar_operacion', lambda m, texto: False)
        self.disco = Uso(100 * GB, 90 * GB, 10 * GB)
        with self.assertLogs('odoo.addons.dcasa_base.models.mantenimiento', 'WARNING'):
            datos = self.mant._cron_vigilar_recursos()
        self.assertEqual(datos['alertas'], {'disco': False})
        self.assertFalse(self.ICP.get_param('dcasa.alerta.enviada.disco'))

    def test_canal_es_el_telegram_de_seguridad_si_existe(self):
        Users = self.env.registry['res.users']
        if not hasattr(Users, '_dcasa_avisar_operacion'):  # sin dcasa_seguridad no hay canal
            self.assertFalse(AVISAR_ORIGINAL(self.mant, 'x'))
            return
        recibido = []
        self.patch(Users, '_dcasa_avisar_operacion', lambda m, texto: recibido.append(texto) or True)
        self.assertTrue(AVISAR_ORIGINAL(self.mant, 'hola'))
        self.assertEqual(recibido, ["D'CASA · hola"])
        self.patch(Users, '_dcasa_avisar_operacion', lambda m, texto: False)
        self.assertFalse(AVISAR_ORIGINAL(self.mant, 'hola'))

    def test_reporte_mensual_usa_el_mismo_canal(self):
        self.ICP.set_param('dcasa.reporte.alerta_gb', '0.000001')
        datos = self.mant._cron_reporte_tamanos()
        self.assertIn('DCASA_ALERTA la base pesa', datos['alerta'])
        self.assertEqual(len(self.avisos), 1)

    def test_cron_horario_y_privado(self):
        cron = self.env.ref('dcasa_base.ir_cron_dcasa_vigilar_recursos')
        self.assertTrue(cron.active)
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'hours'))
        self.assertIn('_cron_vigilar_recursos', cron.code)

    def test_defectos_documentados(self):
        self.assertEqual(PARAMETROS['dcasa.alerta.disco_pct'], 80)
        self.assertEqual(PARAMETROS['dcasa.alerta.memoria_pct'], 90)
        self.assertEqual(PARAMETROS['dcasa.alerta.silencio_h'], 24)


@tagged('post_install', '-at_install')
class TestCronsOdoo(TransactionCase):
    """Las acciones planificadas de Odoo que no aplican quedan apagadas o espaciadas, sin tocar las propias."""

    def test_ajuste_idempotente(self):
        mant = self.env['dcasa.mantenimiento']
        mant._ajustar_crons_odoo()
        resultado = mant._ajustar_crons_odoo()
        self.assertEqual(set(resultado), set(CRONS_ODOO))
        # Volver a correrlo no cambia nada.
        self.assertNotIn('ajustado', resultado.values())
        for xmlid, valores in CRONS_ODOO.items():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if cron is None:
                self.assertEqual(resultado[xmlid], 'no existe')
                continue
            self.assertEqual(resultado[xmlid], 'ya estaba', xmlid)
            for campo, valor in valores.items():
                self.assertEqual(cron[campo], valor, f'{xmlid}.{campo}')
        # Si alguien lo vuelve a encender, la próxima actualización lo apaga de nuevo.
        fetchmail = self.env.ref('mail.ir_cron_mail_gateway_action')
        fetchmail.active = True
        self.assertEqual(mant._ajustar_crons_odoo()['mail.ir_cron_mail_gateway_action'], 'ajustado')
        self.assertFalse(fetchmail.active)

    def test_no_toca_los_crons_propios(self):
        for xmlid in CRONS_ODOO:
            self.assertFalse(xmlid.startswith(('dcasa_', 'website_dcasa.')), xmlid)
        for xmlid in ('dcasa_base.ir_cron_dcasa_depurar', 'dcasa_base.ir_cron_dcasa_reporte_tamanos',
                      'dcasa_base.ir_cron_dcasa_vigilar_recursos', 'dcasa_seguridad.cron_purgar_accesos'):
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if cron is not None:
                self.assertTrue(cron.active, xmlid)


@tagged('post_install', '-at_install')
class TestMemoria(TransactionCase):
    """Memoria del contenedor leída de un cgroup y un /proc de mentira (v2 y v1)."""

    def _escribir(self, base, archivos):
        for ruta, texto in archivos.items():
            completa = os.path.join(base, ruta)
            os.makedirs(os.path.dirname(completa), exist_ok=True)
            with open(completa, 'w') as archivo:
                archivo.write(texto)

    def test_cgroup_v2(self):
        with tempfile.TemporaryDirectory() as base:
            self._escribir(base, {
                'memory.current': '838860800\n', 'memory.max': '1073741824\n',
                'memory.stat': 'anon 314572800\nfile 471859200\nkernel 20971520\nshmem 134217728\n',
                'memory.events': 'low 0\nhigh 0\nmax 3\noom 1\noom_kill 1\n',
            })
            datos = memoria.cgroup(base)
        self.assertEqual(datos['version'], 2)
        self.assertEqual((datos['current'], datos['max']), (838860800, 1073741824))
        self.assertEqual((datos['anon'], datos['file'], datos['kernel'], datos['shmem']),
                         (314572800, 471859200, 20971520, 134217728))
        self.assertEqual(datos['eventos']['oom_kill'], 1)

    def test_cgroup_v1_sin_limite(self):
        with tempfile.TemporaryDirectory() as base:
            self._escribir(base, {
                'memory/memory.usage_in_bytes': '1000\n', 'memory/memory.limit_in_bytes': '9223372036854771712\n',
                'memory/memory.stat': 'cache 600\nrss 300\nshmem 50\ntotal_cache 700\ntotal_rss 250\n',
                'memory/memory.oom_control': 'oom_kill_disable 0\nunder_oom 0\noom_kill 2\n',
            })
            datos = memoria.cgroup(base)
        self.assertEqual(datos['version'], 1)
        self.assertIsNone(datos['max'])
        self.assertEqual((datos['anon'], datos['file'], datos['eventos']['oom_kill']), (250, 700, 2))

    def test_procesos_odoo_y_postgres(self):
        with tempfile.TemporaryDirectory() as proc:
            self._escribir(proc, {
                '10/comm': 'python3\n', '10/cmdline': 'python3\x00/opt/odoo/odoo-bin\x00-c\x00x',
                '10/status': 'Name:\tpython3\nVmRSS:\t  200000 kB\n',
                '10/smaps_rollup': 'Rss: 200000 kB\nPss: 190000 kB\n',
                '20/comm': 'postgres\n', '20/cmdline': 'postgres: checkpointer',
                '20/status': 'VmRSS:\t150000 kB\n', '20/smaps_rollup': 'Pss: 40000 kB\n',
                '21/comm': 'postgres\n', '21/cmdline': 'postgres: walwriter',
                '21/status': 'VmRSS:\t150000 kB\n',
                '30/comm': 'kthreadd\n', '30/status': 'Name:\tkthreadd\n',
            })
            datos = memoria.procesos(proc)
        self.assertEqual(datos['odoo'], {'n': 1, 'rss': 200000 * 1024, 'pss': 190000 * 1024})
        self.assertEqual(datos['postgres'], {'n': 2, 'rss': 300000 * 1024, 'pss': 40000 * 1024})
        self.assertEqual(datos['otros']['n'], 0)

    def test_linea_json_para_el_arranque(self):
        linea = json.loads(memoria.linea('arranque'))
        self.assertEqual((linea['evento'], linea['momento']), ('memoria', 'arranque'))
