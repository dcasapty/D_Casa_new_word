"""Las versiones de las reglas del programa de vendedores: lo que Gerencia ajusta desde Ajustes.

``puntos.json`` sigue siendo la fábrica. Cada cambio guardado crea UNA FILA AQUÍ con su fecha-hora de vigencia: desde
entonces, y solo desde entonces, se paga con esas cifras. La fila no se edita ni se borra (mismo espíritu del libro de
puntos): un error se corrige guardando un cambio nuevo, y «Volver a los valores de fábrica» es otro cambio más.

Quién llama a ``_vigentes()``: todo lo que antes leía ``cargar_reglas()`` para vendedores (la comisión, el canje, el
panel del vendedor, los términos). Nunca falla: si algo está dañado, rigen la versión anterior o la fábrica, y se
escribe en el registro; una venta jamás se frena por esto.
"""

import json
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import reglas as R
from . import reglas_ajustes as A
from . import reglas_vendedores as RV

_logger = logging.getLogger(__name__)

GRUPOS_QUE_AJUSTAN = ('dcasa_base.group_gerencia', 'base.group_system')
TIPOS_DE_VERSION = [('ajuste', 'Ajuste de Gerencia'), ('fabrica', 'Vuelta a los valores de fábrica')]
# Candado para que dos personas que guardan a la vez no saquen el mismo número de versión.
LLAVE_DE_NUMERACION = 731_900_001
# Cuántas versiones recientes se miran para encontrar la que rige (más de las que haría falta; es solo un tope).
VERSIONES_A_MIRAR = 25


class DcasaVendReglas(models.Model):
    _name = 'dcasa.vend.reglas'
    _description = 'Versión de las reglas del programa de vendedores (ajustes de Gerencia)'
    _order = 'vigente_desde desc, numero desc'
    _rec_name = 'nombre'

    numero = fields.Integer(string='Versión', required=True, readonly=True, index=True)
    nombre = fields.Char(compute='_compute_nombre')
    vigente_desde = fields.Datetime(
        string='Rige desde', required=True, readonly=True, index=True,
        help='Desde este momento, y solo desde entonces, se paga con estas cifras. Lo ya acreditado no se recalcula.')
    rige_ahora = fields.Boolean(string='Rige ahora', compute='_compute_rige_ahora')
    tipo = fields.Selection(TIPOS_DE_VERSION, required=True, readonly=True, default='ajuste')
    autor = fields.Char(string='Quién lo cambió', required=True, readonly=True)
    motivo = fields.Char(readonly=True, help='Por qué se cambió (lo escribe quien guarda; es opcional).')
    fabrica_version = fields.Integer(
        string='Versión de puntos.json', readonly=True,
        help='La versión de las cifras de fábrica (puntos.json) que había cuando se guardó este cambio.')
    ajustes = fields.Text(
        readonly=True,
        help='Técnico: todo lo que está cambiado frente a la fábrica (ruta → valor), acumulado hasta esta versión.')
    cambios = fields.Text(readonly=True, help='Técnico: lo que cambió en esta versión, con el antes y el nuevo.')
    cambios_html = fields.Html(string='Qué cambió', compute='_compute_cambios', sanitize=False)
    resumen = fields.Char(string='Qué cambió (resumen)', compute='_compute_cambios')

    _numero_unico = models.Constraint('UNIQUE(numero)', 'Ya existe una versión con ese número.')

    # ------------------------------------------------------------------------
    # Cómputos
    # ------------------------------------------------------------------------

    @api.depends('numero')
    def _compute_nombre(self):
        for version in self:
            version.nombre = self.env._('Versión %s', version.numero)

    def _compute_rige_ahora(self):
        vigente = self.sudo().search(
            [('vigente_desde', '<=', fields.Datetime.now())], order='vigente_desde desc, numero desc', limit=1)
        for version in self:
            version.rige_ahora = bool(vigente) and version.numero == vigente.numero

    @api.depends('cambios', 'tipo')
    def _compute_cambios(self):
        for version in self:
            try:
                cambios = json.loads(version.cambios or '[]')
            except ValueError:
                cambios = []
            filas = Markup('').join(
                Markup('<tr><td>{}</td><td class="text-muted">{}</td><td><strong>{}</strong></td></tr>').format(
                    c.get('campo', ''), c.get('antes', ''), c.get('despues', '')) for c in cambios)
            version.cambios_html = Markup(
                '<table class="table table-sm o_dcasa_vend_historial"><thead><tr><th>Qué</th><th>Antes</th>'
                '<th>Ahora</th></tr></thead><tbody>{}</tbody></table>').format(filas) if cambios else Markup('')
            if version.tipo == 'fabrica':
                version.resumen = self.env._('Volvieron los valores de fábrica')
            else:
                version.resumen = ', '.join(c.get('campo', '') for c in cambios)

    # ------------------------------------------------------------------------
    # El historial no se edita ni se borra
    # ------------------------------------------------------------------------

    def write(self, vals):
        raise UserError(self.env._(
            'El historial de reglas no se edita: un cambio se hace guardando una versión nueva en Ajustes.'))

    def unlink(self):
        raise UserError(self.env._(
            'El historial de reglas no se borra: un error se corrige guardando una versión nueva en Ajustes.'))

    @api.model_create_multi
    def create(self, vals_list):
        """Numera la versión y cuida que los cambios solo rijan hacia adelante: ni con fecha del pasado ni antes de
        una versión que ya está programada."""
        ahora = fields.Datetime.now()
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [LLAVE_DE_NUMERACION])
        self.env.cr.execute('SELECT COALESCE(MAX(numero), 0), MAX(vigente_desde) FROM dcasa_vend_reglas')
        ultimo_numero, ultima_vigencia = self.env.cr.fetchone()
        for vals in vals_list:
            desde = fields.Datetime.to_datetime(vals.get('vigente_desde')) or ahora
            if desde < ahora - timedelta(minutes=1):
                raise UserError(self.env._(
                    'Un cambio solo rige hacia adelante: no se puede poner una fecha que ya pasó.'))
            if ultima_vigencia and desde < ultima_vigencia:
                raise UserError(self.env._(
                    'Ya hay un cambio programado para más adelante. No se puede guardar uno que empiece antes.'))
            ultimo_numero += 1
            vals.update(numero=ultimo_numero, vigente_desde=desde)
            ultima_vigencia = desde
        return super().create(vals_list)

    # ------------------------------------------------------------------------
    # Permisos: solo Gerencia y los administradores
    # ------------------------------------------------------------------------

    @api.model
    def _puede_ajustar(self):
        return self.env.su or any(self.env.user.has_group(grupo) for grupo in GRUPOS_QUE_AJUSTAN)

    @api.model
    def _exigir_gerencia(self):
        """Se comprueba en el servidor ANTES de leer o cambiar nada con ``sudo()``: la pantalla no es de confianza."""
        if not self._puede_ajustar():
            raise AccessError(self.env._('Solo Gerencia y los administradores ven y cambian las reglas del programa '
                                         'de vendedores.'))

    # ------------------------------------------------------------------------
    # Las reglas que rigen
    # ------------------------------------------------------------------------

    @api.model
    def _versiones(self, ahora=None):
        """Las versiones que ya empezaron, listas para ``reglas_efectivas``. Una fila dañada se salta (y queda en el
        registro): la anterior sigue rigiendo."""
        ahora = ahora or fields.Datetime.now()
        filas = self.sudo().search_read(
            [('vigente_desde', '<=', ahora)],
            ['numero', 'vigente_desde', 'ajustes', 'tipo', 'autor', 'fabrica_version'],
            order='vigente_desde desc, numero desc', limit=VERSIONES_A_MIRAR)
        versiones = []
        for fila in filas:
            try:
                ajustes = json.loads(fila['ajustes'] or '{}')
                if not isinstance(ajustes, dict):
                    raise ValueError('no es un diccionario')
            except ValueError:
                _logger.error('Las reglas de vendedores (versión %s) están dañadas: se usa la versión anterior.',
                              fila['numero'])
                continue
            versiones.append({'id': fila['id'], 'numero': fila['numero'], 'vigente_desde': fila['vigente_desde'],
                              'ajustes': ajustes, 'tipo': fila['tipo'], 'autor': fila['autor'],
                              'fabrica_version': fila['fabrica_version']})
        return versiones

    @api.model
    def _vigentes(self, ahora=None):
        """Las reglas con que se paga ahora (o en ``ahora``): ``puntos.json`` más los ajustes de Gerencia que ya
        rigen. Sin ajustes devuelve ``puntos.json`` tal cual. NUNCA falla: ante cualquier problema rige la fábrica."""
        base = R.cargar_reglas()
        ahora = ahora or fields.Datetime.now()
        try:
            return A.reglas_efectivas(base, self._versiones(ahora), ahora)
        except Exception:  # noqa: BLE001  — una venta no se frena por no poder leer un ajuste
            _logger.exception('No se pudieron leer los ajustes de las reglas de vendedores: rigen los valores de '
                              'fábrica.')
            return base

    @api.model
    def _estado(self):
        """``(fábrica, reglas efectivas, versión que rige)``; la versión es un diccionario vacío si rige la fábrica."""
        ahora = fields.Datetime.now()
        base = R.cargar_reglas()
        versiones = self._versiones(ahora)
        return base, A.reglas_efectivas(base, versiones, ahora), A.version_vigente(versiones, ahora) or {}

    @api.model
    def _numero_vigente(self):
        """Número de la versión que rige (0 = valores de fábrica)."""
        return RV.ajuste_aplicado(self._vigentes())

    # ------------------------------------------------------------------------
    # Guardar un cambio
    # ------------------------------------------------------------------------

    @api.model
    def _registrar(self, tipo, ajustes, cambios, motivo, base):
        return self.sudo().create({
            'tipo': tipo,
            'ajustes': json.dumps(ajustes, ensure_ascii=False, sort_keys=True),
            'cambios': json.dumps(cambios, ensure_ascii=False),
            'motivo': (motivo or '').strip()[:200] or False,
            'autor': self.env.user.name,
            'fabrica_version': base.get('version') or 0,
        })

    def _exigir_version_vista(self, version_vista, numero_actual):
        if version_vista is not None and version_vista != numero_actual:
            raise UserError(self.env._(
                'Alguien cambió las reglas mientras tenías esta pantalla abierta. No se guardó nada: cierra la '
                'pantalla, ábrela de nuevo para ver lo que rige ahora y vuelve a hacer tu cambio.'))

    @api.model
    def _guardar_desde_pantalla(self, pantalla, motivo=None, version_vista=None):
        """Guarda lo que quedó en la pantalla como una versión nueva. Devuelve la versión, o vacío si no cambió nada.

        El servidor decide todo: vuelve a comprobar el permiso, reconvierte las cifras y las valida. Si algo no
        cumple, NO se guarda nada y el mensaje dice qué corregir."""
        self._exigir_gerencia()
        base, actuales, version = self._estado()
        self._exigir_version_vista(version_vista, version.get('numero', 0))
        try:
            resultado = A.calcular_cambio(base, actuales, version.get('ajustes') or {}, pantalla)
        except R.FaltaConfigurar as error:
            raise UserError(str(error)) from error
        if resultado['problemas'] and (resultado['cambios'] or resultado['problemas_de_pantalla']):
            raise UserError(self.env._('No se guardó nada. Corrige esto y vuelve a guardar:') + '\n'
                            + '\n'.join(f'• {problema}' for problema in resultado['problemas']))
        if not resultado['cambios']:
            return self.browse()
        _logger.info('Reglas de vendedores: %s cambió %s', self.env.user.login,
                     ', '.join(c['campo'] for c in resultado['cambios']))
        return self._registrar('ajuste', resultado['ajustes'], resultado['cambios'], motivo, base)

    @api.model
    def _volver_a_fabrica(self, motivo=None, version_vista=None):
        """Crea una versión nueva igual a ``puntos.json`` (ningún ajuste). No borra nada del historial."""
        self._exigir_gerencia()
        base, actuales, version = self._estado()
        self._exigir_version_vista(version_vista, version.get('numero', 0))
        try:
            cambios = A.cambios_contra_fabrica(base, actuales)
        except R.FaltaConfigurar as error:
            raise UserError(str(error)) from error
        if not cambios:
            raise UserError(self.env._('Ya están los valores de fábrica: no hay nada que devolver.'))
        _logger.info('Reglas de vendedores: %s volvió a los valores de fábrica', self.env.user.login)
        return self._registrar('fabrica', {}, cambios, motivo, base)
