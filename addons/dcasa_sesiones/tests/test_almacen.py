import os
import time
from unittest.mock import patch

from odoo import http
from odoo.http import SESSION_DELETION_TIMER, STORED_SESSION_BYTES, get_default_session
from odoo.tests import TransactionCase, tagged

from .. import almacen
from ..almacen import TABLA, PostgresSessionStore, huella


@tagged('post_install', '-at_install')
class TestAlmacenSesiones(TransactionCase):
    """El almacén en PostgreSQL. Escribe en su propia conexión (como en producción): cada test
    borra sus filas al terminar."""

    def setUp(self):
        super().setUp()
        self.store = PostgresSessionStore(self.env.cr.dbname)
        self.addCleanup(self._limpiar)
        self._identificadores = set()

    def _limpiar(self):
        if self._identificadores:
            self.store.delete_from_identifiers(sorted(self._identificadores))

    def nueva(self, **datos):
        sesion = self.store.new()
        sesion.update(get_default_session(), **datos)
        self._identificadores.add(sesion.sid[:STORED_SESSION_BYTES])
        return sesion

    def fila(self, sid):
        with self.store._cursor() as cr:
            cr.execute(f'SELECT identifier, data, mtime FROM {TABLA} WHERE sid_hash = %s', (huella(sid),))
            return cr.fetchone()

    def reiniciar(self):
        """Un almacén nuevo, como tras reiniciar el contenedor (no comparte nada en memoria)."""
        return PostgresSessionStore(self.env.cr.dbname)

    # ------------------------------------------------------------------

    def test_guardar_reiniciar_y_recuperar(self):
        sesion = self.nueva(login='vendedora', context={'lang': 'es_419', 'tz': 'America/Panama'})
        sesion['carrito'] = {'pedido': 7}
        self.store.save(sesion)
        recuperada = self.reiniciar().get(sesion.sid)
        self.assertEqual(recuperada.sid, sesion.sid)
        self.assertFalse(recuperada.is_new)
        self.assertEqual(dict(recuperada), dict(sesion))
        # Guardar de nuevo actualiza la misma fila.
        recuperada['carrito'] = {'pedido': 8}
        self.store.save(recuperada)
        self.assertEqual(self.reiniciar().get(sesion.sid)['carrito'], {'pedido': 8})

    def test_el_sid_no_queda_en_claro(self):
        sesion = self.nueva(login='socio')
        self.store.save(sesion)
        identificador, datos, _mtime = self.fila(sesion.sid)
        self.assertEqual(identificador, sesion.sid[:STORED_SESSION_BYTES], 'Solo la mitad pública')
        with self.store._cursor() as cr:
            cr.execute(f"SELECT count(*) FROM {TABLA} WHERE sid_hash = %s OR identifier = %s "
                       f"OR data LIKE %s OR sid_hash LIKE %s",
                       (sesion.sid, sesion.sid, f'%{sesion.sid[STORED_SESSION_BYTES:]}%',
                        f'%{sesion.sid[STORED_SESSION_BYTES:]}%'))
            self.assertEqual(cr.fetchone()[0], 0, 'La mitad secreta del sid no está en la base')
        self.assertNotIn(sesion.sid, datos)

    def test_sin_fuga_entre_sesiones(self):
        ana = self.nueva(login='ana')
        luis = self.nueva(login='luis')
        self.store.save(ana)
        self.store.save(luis)
        self.assertEqual(self.store.get(ana.sid)['login'], 'ana')
        self.assertEqual(self.store.get(luis.sid)['login'], 'luis')
        # Mitad pública de Ana + mitad secreta de Luis: no abre ninguna de las dos.
        falsa = ana.sid[:STORED_SESSION_BYTES] + luis.sid[STORED_SESSION_BYTES:]
        intento = self.store.get(falsa)
        self.assertTrue(intento.is_new)
        self.assertNotEqual(intento.sid, falsa, 'Sesión que no existe: sid nuevo, como Odoo')
        self.assertNotIn('login', intento)
        # Llaves mal formadas o desconocidas: sesión nueva y vacía.
        for llave in ('', '../etc/passwd', ana.sid[:STORED_SESSION_BYTES], self.store.generate_key()):
            self.assertTrue(self.store.get(llave).is_new, llave)
        with self.assertRaises(ValueError):
            sesion = self.store.new()
            sesion.sid = 'corto'
            self.store.save(sesion)

    def test_rotacion_suave(self):
        sesion = self.nueva(login='vendedora')
        self.store.save(sesion)
        vieja = sesion.sid
        self.store.rotate(sesion, None, soft=True)
        self.assertNotEqual(sesion.sid, vieja)
        self.assertEqual(sesion.sid[:STORED_SESSION_BYTES], vieja[:STORED_SESSION_BYTES],
                         'La rotación suave conserva la mitad del CSRF')
        anterior = self.reiniciar().get(vieja)
        self.assertEqual(anterior['next_sid'], sesion.sid, 'La vieja apunta a la nueva un rato')
        nueva = self.reiniciar().get(sesion.sid)
        self.assertEqual(nueva['login'], 'vendedora')
        self.assertTrue(nueva['gc_previous_sessions'])
        # Una petición simultánea con la cookie vieja reusa la misma sesión nueva.
        concurrente = self.store.get(vieja)
        self.store.rotate(concurrente, None, soft=True)
        self.assertEqual(concurrente.sid, sesion.sid)
        # Pasado el margen, la vieja se borra y la nueva sigue.
        nueva['create_time'] = time.time() - SESSION_DELETION_TIMER - 1
        self.store.delete_old_sessions(nueva)
        self.assertTrue(self.store.get(vieja).is_new, 'La vieja ya no abre')
        vigente = self.reiniciar().get(sesion.sid)
        self.assertFalse(vigente.is_new)
        self.assertNotIn('gc_previous_sessions', vigente)

    def test_rotacion_dura_con_usuario(self):
        sesion = self.nueva(login=self.env.user.login, uid=self.env.uid)
        self.store.save(sesion)
        vieja = sesion.sid
        self.store.rotate(sesion, self.env)
        self.assertNotEqual(sesion.sid[:STORED_SESSION_BYTES], vieja[:STORED_SESSION_BYTES])
        self._identificadores.add(sesion.sid[:STORED_SESSION_BYTES])
        self.assertTrue(self.store.get(vieja).is_new, 'La sesión anterior ya no existe')
        recuperada = self.reiniciar().get(sesion.sid)
        self.assertEqual(recuperada.uid, self.env.uid)
        self.assertTrue(recuperada.session_token)

    def test_vencimiento_y_limpieza(self):
        vieja = self.nueva(login='vieja')
        fresca = self.nueva(login='fresca')
        self.store.save(vieja)
        self.store.save(fresca)
        with self.store._cursor() as cr:
            cr.execute(f'UPDATE {TABLA} SET mtime = %s WHERE sid_hash = %s',
                       (time.time() - 2 * 3600, huella(vieja.sid)))
        self.assertEqual(self.store.vacuum(max_lifetime=3600), 1)
        self.assertTrue(self.store.get(vieja.sid).is_new)
        self.assertFalse(self.store.get(fresca.sid).is_new)

    def test_autovacuum_de_odoo_usa_la_base(self):
        """``ir.http._gc_sessions`` (autovacuum diario) limpia la tabla con el plazo de Odoo."""
        self.assertIsInstance(http.root.session_store, PostgresSessionStore)
        sesion = self.nueva(login='olvidada')
        self.store.save(sesion)
        with self.store._cursor() as cr:
            cr.execute(f'UPDATE {TABLA} SET mtime = %s WHERE sid_hash = %s',
                       (time.time() - 8 * 24 * 3600, huella(sesion.sid)))
        entorno = {k: v for k, v in os.environ.items() if k != 'ODOO_SKIP_GC_SESSIONS'}
        with patch.dict(os.environ, entorno, clear=True):
            self.env['ir.http']._gc_sessions()
        self.assertIsNone(self.fila(sesion.sid))

    def test_dispositivos_cerrar_por_identificador(self):
        """«Dispositivos» (res.device) consulta y cierra sesiones por su mitad pública."""
        abierta = self.nueva(login='abierta')
        self.store.save(abierta)
        cerrada = self.store.generate_key()[:STORED_SESSION_BYTES]
        presente = abierta.sid[:STORED_SESSION_BYTES]
        self.assertEqual(self.store.get_missing_session_identifiers([presente, cerrada]), {cerrada})
        self.store.delete_from_identifiers([presente])
        self.assertTrue(self.store.get(abierta.sid).is_new)
        self.assertEqual(self.store.get_missing_session_identifiers([presente]), {presente})
        with self.assertRaises(ValueError):
            self.store.delete_from_identifiers(presente)  # un str, no una lista
        with self.assertRaises(ValueError):
            self.store.delete_from_identifiers(["' OR 1=1 --"])

    def test_instalado_en_odoo(self):
        actual = http.root.session_store
        self.assertIsInstance(actual, PostgresSessionStore)
        self.assertEqual(actual.dbname, self.env.cr.dbname)
        self.assertIs(almacen.instalar(), actual, 'Instalar dos veces no cambia nada')

    def test_nombre_de_la_base(self):
        sin_variable = {k: v for k, v in os.environ.items() if k != almacen.VARIABLE_BASE}
        with patch.dict(os.environ, sin_variable, clear=True):
            with patch.dict(almacen.config.options, {'db_name': ['dcasa'], almacen.OPCION_BASE: None}):
                self.assertEqual(almacen.nombre_base(), 'dcasa')
            with patch.dict(almacen.config.options, {'db_name': ['a', 'b'], almacen.OPCION_BASE: None}):
                self.assertIsNone(almacen.nombre_base(), 'Varias bases: no se adivina')
            with patch.dict(almacen.config.options, {'db_name': ['a', 'b'], almacen.OPCION_BASE: 'b'}):
                self.assertEqual(almacen.nombre_base(), 'b')
        with patch.dict(os.environ, {almacen.VARIABLE_BASE: 'sesiones'}):
            self.assertEqual(almacen.nombre_base(), 'sesiones')

    def test_base_caida_no_tumba_la_peticion(self):
        caida = PostgresSessionStore('dcasa_base_que_no_existe')
        sesion = caida.new()
        sesion['login'] = 'x'
        with self.assertLogs('odoo.addons.dcasa_sesiones.almacen', 'WARNING'):
            caida.save(sesion)
            self.assertTrue(caida.get(sesion.sid).is_new)
            self.assertEqual(caida.vacuum(), 0)
            self.assertEqual(caida.get_missing_session_identifiers([sesion.sid[:STORED_SESSION_BYTES]]), set(),
                             'Ante la duda no se revoca ningún dispositivo')
