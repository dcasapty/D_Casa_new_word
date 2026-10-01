"""Almacén de sesiones HTTP de Odoo en PostgreSQL.

Odoo 19 guarda las sesiones en disco (``odoo.http.FilesystemSessionStore``, creado por la
propiedad ``Application.session_store`` de ``odoo/http.py``). En el contenedor de Cloudflare el
disco se borra en cada reinicio o despliegue, así que este módulo cambia ese almacén por uno
en la base, sin tocar ``vendor/odoo``:

* ``Application.session_store`` es un ``functools.cached_property`` (sin ``__set__``): asignar
  ``odoo.http.root.session_store = ...`` lo sustituye en la instancia de forma limpia, sin
  parchear clases ni funciones de Odoo. Lo hace ``instalar()`` desde el ``post_load``.
* ``PostgresSessionStore`` hereda del almacén de Odoo y solo cambia DÓNDE se guarda (get, save,
  delete, vacuum y la búsqueda por identificador). La rotación, el formato del ``sid``, la
  validación de llaves y el borrado de sesiones viejas siguen siendo los de Odoo.

Tabla ``dcasa_http_session`` (SQL directo, sin ORM: el almacén se usa antes de cargar el
registro, incluso en peticiones sin base):

* ``sid_hash``: SHA-256 del ``sid`` completo (84 caracteres). Es la llave: quien lee la base no
  obtiene sesiones usables. Odoo en disco usa el ``sid`` en claro como nombre de archivo.
* ``identifier``: los primeros 42 caracteres del ``sid`` (``STORED_SESSION_BYTES``). Odoo ya los
  guarda en claro en ``res_device_log.session_identifier``; sirven para cerrar sesiones desde
  «Dispositivos» y para la limpieza tras una rotación. Con ellos solos no se abre una sesión.
* ``data``: el JSON de la sesión, igual que el archivo de Odoo.
* ``mtime``: segundos epoch de la última escritura (el ``mtime`` del archivo en Odoo); el
  autovacuum diario (``ir.http._gc_sessions``) borra lo que pase de
  ``sessions.max_inactivity_seconds`` (7 días por defecto), igual que en disco.

Base que se usa (la primera que haya):

1. variable de entorno ``DCASA_SESIONES_DB``;
2. opción ``dcasa_sesiones_db`` en ``odoo.conf``;
3. ``db_name`` de la configuración, si es UNA sola base (producción: ``db_name = dcasa``).

Sin base clara (varias bases, ninguna configurada) se queda el almacén de Odoo en disco y se
avisa en el log.

Producción (``odoo.conf``)::

    server_wide_modules = base,web,dcasa_sesiones
    db_name = dcasa
"""

import hashlib
import json
import logging
import os
import threading
import time

import psycopg2

from odoo import http, sql_db
from odoo.http import (
    SESSION_DELETION_TIMER,
    SESSION_LIFETIME,
    STORED_SESSION_BYTES,
    FilesystemSessionStore,
    Session,
    _session_identifier_re,
)
from odoo.tools import config

_logger = logging.getLogger(__name__)

TABLA = 'dcasa_http_session'
VARIABLE_BASE = 'DCASA_SESIONES_DB'
OPCION_BASE = 'dcasa_sesiones_db'

_CREAR_TABLA = f"""
    CREATE TABLE IF NOT EXISTS {TABLA} (
        sid_hash varchar(64) PRIMARY KEY,
        identifier varchar({STORED_SESSION_BYTES}) NOT NULL,
        data text NOT NULL,
        mtime double precision NOT NULL
    );
    CREATE INDEX IF NOT EXISTS {TABLA}_identifier_idx ON {TABLA} (identifier);
    CREATE INDEX IF NOT EXISTS {TABLA}_mtime_idx ON {TABLA} (mtime);
"""


def nombre_base():
    """La base donde viven las sesiones, o ``None`` si no hay una sola clara."""
    nombre = os.environ.get(VARIABLE_BASE) or config.get(OPCION_BASE)
    if nombre:
        return nombre.strip()
    bases = config.get('db_name') or []
    if isinstance(bases, str):
        bases = [b for b in bases.split(',') if b.strip()]
    if len(bases) == 1:
        return bases[0].strip()
    return None


def huella(sid):
    """SHA-256 del ``sid``: la llave de la fila (el ``sid`` no se guarda en claro)."""
    return hashlib.sha256(sid.encode()).hexdigest()


class PostgresSessionStore(FilesystemSessionStore):
    """El almacén de sesiones de Odoo, con las sesiones en una tabla de PostgreSQL."""

    def __init__(self, dbname, session_class=Session):
        # ``path`` no se usa: se pasa None para no crear directorios en disco.
        super().__init__(None, session_class=session_class, renew_missing=True)
        self.dbname = dbname
        self._tabla_lista = False
        self._candado = threading.Lock()

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def _cursor(self):
        """Cursor propio (del pool de Odoo), en su propia transacción: ``with`` la confirma."""
        cr = sql_db.db_connect(self.dbname).cursor()
        if not self._tabla_lista:
            try:
                with self._candado:
                    if not self._tabla_lista:
                        cr.execute(_CREAR_TABLA, log_exceptions=False)
                        cr.commit()
                        self._tabla_lista = True
            except Exception:
                cr.close()
                raise
        return cr

    def _fallo(self, accion, error):
        # Sin base no hay sesión que valga: se avisa y la petición sigue (como sin cookie).
        self._tabla_lista = False
        _logger.warning('Sesiones: no se pudo %s en la base %r: %s', accion, self.dbname, error)

    # ------------------------------------------------------------------
    # API de odoo.http.FilesystemSessionStore
    # ------------------------------------------------------------------

    def get_session_filename(self, sid):
        raise NotImplementedError('Las sesiones de D\'CASA viven en la base, no en disco.')

    def save(self, session):
        if not self.is_valid_key(session.sid):
            raise ValueError('Identificador de sesión inválido')
        datos = json.dumps(dict(session))
        try:
            with self._cursor() as cr:
                cr.execute(f"""
                    INSERT INTO {TABLA} (sid_hash, identifier, data, mtime)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (sid_hash) DO UPDATE
                       SET data = EXCLUDED.data, mtime = EXCLUDED.mtime
                """, (huella(session.sid), session.sid[:STORED_SESSION_BYTES], datos, time.time()),
                    log_exceptions=False)
        except psycopg2.Error as error:
            self._fallo('guardar la sesión', error)

    def get(self, sid):
        if not self.is_valid_key(sid):
            return self.new()
        try:
            with self._cursor() as cr:
                cr.execute(f'SELECT data FROM {TABLA} WHERE sid_hash = %s', (huella(sid),),
                           log_exceptions=False)
                fila = cr.fetchone()
        except psycopg2.Error as error:
            self._fallo('leer la sesión', error)
            fila = None
        if not fila:
            return self.new()  # renew_missing, como Odoo
        try:
            datos = json.loads(fila[0])
        except ValueError:
            _logger.debug('Sesión ilegible en la base; se usa una vacía.', exc_info=True)
            datos = {}
        return self.session_class(datos, sid, False)

    def delete(self, session):
        if not self.is_valid_key(session.sid):
            return
        try:
            with self._cursor() as cr:
                cr.execute(f'DELETE FROM {TABLA} WHERE sid_hash = %s', (huella(session.sid),),
                           log_exceptions=False)
        except psycopg2.Error as error:
            self._fallo('borrar la sesión', error)

    def delete_old_sessions(self, session):
        """Tras una rotación suave, borra las sesiones anteriores del mismo identificador.

        Odoo borra TODAS las del identificador (también la actual) y la vuelve a escribir; aquí
        se borran todas menos la actual en una sola sentencia, sin el hueco en que la sesión
        vigente no existe (una petición simultánea quedaría como visitante).
        """
        if 'gc_previous_sessions' not in session or not self.is_valid_key(session.sid):
            return
        if session['create_time'] + SESSION_DELETION_TIMER >= time.time():
            return
        try:
            with self._cursor() as cr:
                cr.execute(f'DELETE FROM {TABLA} WHERE identifier = %s AND sid_hash <> %s',
                           (session.sid[:STORED_SESSION_BYTES], huella(session.sid)), log_exceptions=False)
        except psycopg2.Error as error:
            self._fallo('borrar sesiones rotadas', error)
            return
        del session['gc_previous_sessions']
        self.save(session)

    def vacuum(self, max_lifetime=SESSION_LIFETIME):
        """Borra las sesiones sin escribir en ``max_lifetime`` segundos. Devuelve cuántas."""
        try:
            with self._cursor() as cr:
                cr.execute(f'DELETE FROM {TABLA} WHERE mtime < %s', (time.time() - max_lifetime,),
                           log_exceptions=False)
                borradas = cr.rowcount
        except psycopg2.Error as error:
            self._fallo('limpiar sesiones vencidas', error)
            return 0
        if borradas:
            _logger.info('Sesiones: %s vencidas borradas.', borradas)
        return borradas

    def get_missing_session_identifiers(self, identifiers):
        identificadores = set(identifiers)
        if not identificadores:
            return identificadores
        try:
            with self._cursor() as cr:
                cr.execute(f'SELECT DISTINCT identifier FROM {TABLA} WHERE identifier = ANY(%s)',
                           (list(identificadores),), log_exceptions=False)
                presentes = {fila[0] for fila in cr.fetchall()}
        except psycopg2.Error as error:
            # Ante la duda no se da por cerrada ninguna sesión (no se revocan dispositivos).
            self._fallo('consultar sesiones', error)
            return set()
        return identificadores - presentes

    def delete_from_identifiers(self, identifiers: list):
        for identificador in identifiers:
            # Igual que Odoo: un identificador mal formado es un error de quien llama.
            if not isinstance(identificador, str) or not _session_identifier_re.match(identificador):
                raise ValueError("Identifier format incorrect, did you pass in a string instead of a list?")
        if not identifiers:
            return
        try:
            with self._cursor() as cr:
                cr.execute(f'DELETE FROM {TABLA} WHERE identifier = ANY(%s)', (list(identifiers),),
                           log_exceptions=False)
        except psycopg2.Error as error:
            self._fallo('cerrar sesiones', error)

    def list(self):
        """Los ``sid`` no se guardan en claro: no se pueden listar."""
        return []


def instalar():
    """Pone el almacén en la base en ``odoo.http.root``. Idempotente."""
    actual = http.root.__dict__.get('session_store')
    if isinstance(actual, PostgresSessionStore):
        return actual
    dbname = nombre_base()
    if not dbname:
        _logger.warning('Sesiones: sin una base única (%s, %s o db_name); quedan en disco.',
                        VARIABLE_BASE, OPCION_BASE)
        return None
    almacen = PostgresSessionStore(dbname)
    http.root.session_store = almacen
    _logger.info('Sesiones HTTP en PostgreSQL (base %r, tabla %s).', dbname, TABLA)
    return almacen
