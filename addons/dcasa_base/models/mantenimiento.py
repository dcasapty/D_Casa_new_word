"""Barandas de costo: depuración y reporte de tamaños mensuales (ronda 4, costos-y-limpieza §5).

Dos acciones planificadas (``data/ir_cron_data.xml``), ambas el día 1 de madrugada:

* ``_cron_depurar``: borra lo que nadie va a volver a mirar y que hace crecer la base
  (la base pesa = el contenedor ``basic`` deja de alcanzar):

  - **adjuntos huérfanos**: ``ir.attachment`` con ``res_model``/``res_id`` cuyo registro
    ya no existe (padres borrados por ``ON DELETE CASCADE`` de PostgreSQL o por SQL
    directo: el ORM no ve a los hijos y sus archivos se quedan). Nunca toca los de campos
    binarios (``res_field``), los de modelos protegidos (contabilidad, localización,
    libro de Socios, registro de Brian), los de modelos que ya no están instalados (no
    se puede saber si el registro existe) ni los que alguna tabla referencia por llave
    foránea (``message_main_attachment_id``, PDF de factura, relaciones de mensajes…);
  - **correos fallidos** (``mail.mail`` en excepción) de más de N días, salvo los de
    documentos protegidos.

  Lo que Odoo ya depura solo NO se repite aquí: visitantes del sitio
  (``website.visitor``, ``website.visitor.live.days`` = 60), sesiones (``dcasa_sesiones``,
  7 días), bus, notificaciones leídas, adjuntos del compositor de correo, bundles viejos.

* ``_cron_reporte_tamanos``: tamaño de la base, las 10 tablas más grandes, los bytes de
  adjuntos por modelo y la memoria real del contenedor (``dcasa_base/memoria.py``). Lo
  escribe en el log (``DCASA_METRICA``) y en ``ir.logging``
  (Ajustes → Técnico → Registros), y avisa (``DCASA_ALERTA``) si la base pasa del umbral:
  con ~1 GB el disco de 4 GB de ``basic`` ya no alcanza.

Umbrales en ``ir.config_parameter`` (ver ``PARAMETROS``). Todos los métodos son privados
(``_``): no se pueden llamar por RPC (test_superficie_rpc).
"""
import json
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import SQL

from .. import memoria

_logger = logging.getLogger(__name__)

# Parámetro → valor por defecto. Se leen en cada ejecución: cambiarlos no exige reiniciar.
PARAMETROS = {
    # Un adjunto huérfano más nuevo que esto se deja (puede ser una subida a medias).
    'dcasa.limpieza.adjuntos_dias': 7,
    # Correos en excepción más viejos que esto se borran.
    'dcasa.limpieza.correos_fallidos_dias': 90,
    # Modelos extra que la depuración no toca nunca (separados por coma).
    'dcasa.limpieza.modelos_protegidos': '',
    # Aviso cuando la base pasa de esto (GB). El límite práctico de basic es ~1 GB.
    'dcasa.reporte.alerta_gb': 0.7,
}

# Nunca se depura nada de estos modelos (legal / reglas del programa de Socios / auditoría).
MODELOS_PROTEGIDOS = frozenset({
    'dcasa.movimiento',  # libro de puntos: no se borra (regla 3 de Socios)
    'dcasa.compra',
    'dcasa.canje',
    'brian.accion',  # registro de auditoría de Brian
})
PREFIJOS_PROTEGIDOS = ('account.', 'l10n_')

TAMANO_LOTE = 1000
GB = 1024 ** 3


class DcasaMantenimiento(models.AbstractModel):
    _name = 'dcasa.mantenimiento'
    _description = "D'CASA: depuración y reporte de tamaños mensuales"

    # ------------------------------------------------------------------ parámetros

    def _parametro(self, clave, tipo=int):
        valor = self.env['ir.config_parameter'].sudo().get_param(clave)
        defecto = PARAMETROS[clave]
        if valor in (None, False, ''):
            return defecto
        try:
            return tipo(valor)
        except (TypeError, ValueError):
            _logger.warning('Parámetro %s inválido (%r): uso %r', clave, valor, defecto)
            return defecto

    def _modelos_protegidos(self):
        extra = self._parametro('dcasa.limpieza.modelos_protegidos', str)
        return MODELOS_PROTEGIDOS | {m.strip() for m in extra.split(',') if m.strip()}

    def _es_protegido(self, modelo, protegidos):
        return modelo in protegidos or modelo.startswith(PREFIJOS_PROTEGIDOS)

    # ------------------------------------------------------------------ depuración

    @api.model
    def _cron_depurar(self):
        resumen = self._depurar()
        mensaje = 'DCASA_LIMPIEZA ' + ' '.join(f'{k}={v}' for k, v in resumen.items())
        _logger.info(mensaje)
        self._registrar('dcasa.limpieza', 'INFO', mensaje, '_cron_depurar')
        return resumen

    @api.model
    def _depurar(self):
        adjuntos, bytes_liberados = self._depurar_adjuntos_huerfanos()
        correos = self._depurar_correos_fallidos()
        return {
            'adjuntos_huerfanos': adjuntos,
            'bytes_liberados': bytes_liberados,
            'correos_fallidos': correos,
        }

    @api.model
    def _adjuntos_huerfanos(self):
        """Ids de ``ir.attachment`` que apuntan a un registro que ya no existe."""
        cr = self.env.cr
        corte = fields.Datetime.now() - timedelta(days=self._parametro('dcasa.limpieza.adjuntos_dias'))
        protegidos = self._modelos_protegidos()
        cr.execute("""
            SELECT DISTINCT res_model FROM ir_attachment
             WHERE res_model IS NOT NULL AND res_id IS NOT NULL AND res_id <> 0 AND res_field IS NULL
        """)
        huerfanos = []
        for (nombre,) in cr.fetchall():
            if self._es_protegido(nombre, protegidos):
                continue
            modelo = self.env.registry.get(nombre)
            # Sin modelo (módulo desinstalado), abstracto o vista SQL: no se puede comprobar.
            if modelo is None or modelo._abstract or not modelo._auto or not modelo._table:
                continue
            cr.execute(SQL(
                """
                SELECT a.id FROM ir_attachment a
                 WHERE a.res_model = %s AND a.res_id IS NOT NULL AND a.res_id <> 0
                   AND a.res_field IS NULL AND a.create_date < %s
                   AND NOT EXISTS (SELECT 1 FROM %s r WHERE r.id = a.res_id)
                """,
                nombre, corte, SQL.identifier(modelo._table),
            ))
            huerfanos.extend(fila[0] for fila in cr.fetchall())
        return self._sin_referencias(huerfanos)

    @api.model
    def _sin_referencias(self, ids):
        """Quita los ids que alguna tabla referencia por llave foránea (p. ej. el PDF de una factura)."""
        if not ids:
            return []
        cr = self.env.cr
        cr.execute("""
            SELECT cl.relname, att.attname
              FROM pg_constraint c
              JOIN pg_class cl ON cl.oid = c.conrelid
              JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
             WHERE c.contype = 'f' AND c.confrelid = 'ir_attachment'::regclass
               AND array_length(c.conkey, 1) = 1
        """)
        referenciados = set()
        for tabla, columna in cr.fetchall():
            cr.execute(SQL(
                'SELECT DISTINCT %s FROM %s WHERE %s = ANY(%s)',
                SQL.identifier(columna), SQL.identifier(tabla), SQL.identifier(columna), ids,
            ))
            referenciados.update(fila[0] for fila in cr.fetchall())
        return [i for i in ids if i not in referenciados]

    @api.model
    def _depurar_adjuntos_huerfanos(self):
        ids = self._adjuntos_huerfanos()
        total = bytes_liberados = 0
        adjuntos = self.env['ir.attachment'].sudo()
        for inicio in range(0, len(ids), TAMANO_LOTE):
            lote = adjuntos.browse(ids[inicio:inicio + TAMANO_LOTE]).exists()
            bytes_liberados += sum(lote.mapped('file_size'))
            total += len(lote)
            lote.unlink()
        return total, bytes_liberados

    @api.model
    def _depurar_correos_fallidos(self):
        if 'mail.mail' not in self.env:
            return 0
        dias = self._parametro('dcasa.limpieza.correos_fallidos_dias')
        corte = fields.Datetime.now() - timedelta(days=dias)
        protegidos = self._modelos_protegidos()
        correos = self.env['mail.mail'].sudo().search([
            ('state', '=', 'exception'),
            ('create_date', '<', corte),
        ])
        correos = correos.filtered(lambda m: not (m.model and self._es_protegido(m.model, protegidos)))
        cantidad = len(correos)
        correos.unlink()
        return cantidad

    # ------------------------------------------------------------------ reporte

    @api.model
    def _cron_reporte_tamanos(self):
        datos = self._medir_tamanos()
        # Memoria real del contenedor (anónima vs caché, RSS/PSS de Odoo y PostgreSQL, OOM):
        # el panel de Cloudflare no distingue la caché de páginas (ver dcasa_base/memoria.py).
        datos['memoria'] = memoria.medir()
        mensaje = 'DCASA_METRICA ' + json.dumps(datos, ensure_ascii=False, sort_keys=True)
        _logger.info(mensaje)
        self._registrar('dcasa.reporte_tamanos', 'INFO', mensaje, '_cron_reporte_tamanos')
        umbral = self._parametro('dcasa.reporte.alerta_gb', float)
        if datos['base_bytes'] > umbral * GB:
            alerta = (f'DCASA_ALERTA la base pesa {datos["base_bytes"] / GB:.2f} GB (umbral {umbral} GB): '
                      'sacar adjuntos a R2 o subir de tipo de contenedor (basic ≈ 1 GB máx.)')
            _logger.warning(alerta)
            self._registrar('dcasa.reporte_tamanos', 'WARNING', alerta, '_cron_reporte_tamanos')
            datos['alerta'] = alerta
        oom = (datos['memoria']['cgroup'].get('eventos') or {}).get('oom_kill')
        if oom:
            alerta = (f'DCASA_ALERTA el kernel mató {oom} proceso(s) por falta de memoria (oom_kill) '
                      'desde que arrancó el contenedor')
            _logger.warning(alerta)
            self._registrar('dcasa.reporte_tamanos', 'WARNING', alerta, '_cron_reporte_tamanos')
        return datos

    @api.model
    def _medir_tamanos(self):
        cr = self.env.cr
        cr.execute('SELECT pg_database_size(current_database())')
        base = cr.fetchone()[0]
        cr.execute("""
            SELECT c.relname, pg_total_relation_size(c.oid)
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r' AND n.nspname = current_schema()
             ORDER BY 2 DESC LIMIT 10
        """)
        tablas = dict(cr.fetchall())
        cr.execute("""
            SELECT COALESCE(res_model, '(sin modelo)'), COUNT(*), COALESCE(SUM(file_size), 0)
              FROM ir_attachment GROUP BY 1 ORDER BY 3 DESC
        """)
        adjuntos = {modelo: {'n': n, 'bytes': int(b)} for modelo, n, b in cr.fetchall()}
        return {'base_bytes': base, 'tablas_top10': tablas, 'adjuntos_por_modelo': adjuntos}

    # ------------------------------------------------------------------ registro

    @api.model
    def _registrar(self, nombre, nivel, mensaje, funcion):
        """Deja la línea en ir.logging (Ajustes → Técnico → Registros) para verla sin la consola."""
        self.env['ir.logging'].sudo().create({
            'name': nombre,
            'type': 'server',
            'dbname': self.env.cr.dbname,
            'level': nivel,
            'message': mensaje,
            'path': __name__,
            'func': funcion,
            'line': '0',
        })
