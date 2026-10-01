"""Barandas de costo: depuración y reporte mensuales (ronda 4, costos-y-limpieza §5)."""
import base64
import json
import os
import tempfile
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_base import memoria
from odoo.addons.dcasa_base.models.mantenimiento import GB
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL

DATOS = base64.b64encode(b'x' * 1000)


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
