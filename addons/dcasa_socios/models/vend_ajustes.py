"""La pantalla de Ajustes › Programa de vendedores.

Los campos y la lógica viven en un molde (``dcasa.vend.ajustes.mixin``) que usan DOS pantallas con las mismas cifras:

* ``res.config.settings``: el bloque «Programa de vendedores» dentro de Ajustes (administradores).
* ``dcasa.vend.ajustes``: la misma pantalla para Gerencia (Socios › Configuración), que no entra a Ajustes de Odoo
  y así no ve ni toca ninguna otra configuración del sistema.

La pantalla no decide nada: solo muestra lo que rige hoy (``puntos.json`` más los ajustes de Gerencia) y, al guardar,
le entrega los números a ``dcasa.vend.reglas``, que vuelve a comprobar el permiso, convierte las cifras, las valida y
crea la versión nueva (con su fecha-hora, quién y qué cambió). Nada que venga del navegador es de confianza.
"""

import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import reglas as R
from . import reglas_ajustes as A
from . import reglas_vendedores as RV

_logger = logging.getLogger(__name__)

# Todo lo que, si cambia en la pantalla, hay que volver a calcular: el resumen de costo y de cambios.
DEPENDENCIAS = tuple(f'dcasa_vend_{clave}' for clave in A.CLAVES_DE_PANTALLA)


def _campo(clave):
    """El campo de Odoo de una cifra ajustable: nombre, ayuda y tipo salen de ``reglas_ajustes.CAMPOS``."""
    campo = A.CAMPOS_POR_CLAVE[clave]
    if campo.tipo == 'si_no':
        return fields.Boolean(campo.etiqueta, help=campo.ayuda)
    if campo.tipo == 'entero':
        return fields.Integer(campo.etiqueta, help=campo.ayuda)
    return fields.Float(campo.etiqueta, digits=(16, 2), help=campo.ayuda)


def _escalon(numero, parte):
    texto = {'desde': 'vendido en esos días, desde', 'tasa': 'gana por cada dólar (%)', 'tope': 'tope del mes ($)'}
    return fields.Float(f'Escalón {numero}: {texto[parte]}', digits=(16, 2))


class DcasaVendAjustesMixin(models.AbstractModel):
    _name = 'dcasa.vend.ajustes.mixin'
    _description = 'Campos y lógica de los ajustes del programa de vendedores'

    # --- Programa --------------------------------------------------------------------------------------------------
    dcasa_vend_programa = _campo('programa')
    # --- Comisión y escalera ---------------------------------------------------------------------------------------
    dcasa_vend_comision_base = _campo('comision_base')
    dcasa_vend_compra_minima = _campo('compra_minima')
    dcasa_vend_recompra = _campo('recompra')
    dcasa_vend_existente = _campo('existente')
    dcasa_vend_dias_escalon = _campo('dias_escalon')
    dcasa_vend_vinculo_meses = _campo('vinculo_meses')
    dcasa_vend_tope_base = _campo('tope_base')
    dcasa_vend_esc1_desde = _escalon(1, 'desde')
    dcasa_vend_esc1_tasa = _escalon(1, 'tasa')
    dcasa_vend_esc1_tope = _escalon(1, 'tope')
    dcasa_vend_esc2_desde = _escalon(2, 'desde')
    dcasa_vend_esc2_tasa = _escalon(2, 'tasa')
    dcasa_vend_esc2_tope = _escalon(2, 'tope')
    dcasa_vend_esc3_desde = _escalon(3, 'desde')
    dcasa_vend_esc3_tasa = _escalon(3, 'tasa')
    dcasa_vend_esc3_tope = _escalon(3, 'tope')
    dcasa_vend_esc4_desde = _escalon(4, 'desde')
    dcasa_vend_esc4_tasa = _escalon(4, 'tasa')
    dcasa_vend_esc4_tope = _escalon(4, 'tope')
    dcasa_vend_esc5_desde = _escalon(5, 'desde')
    dcasa_vend_esc5_tasa = _escalon(5, 'tasa')
    dcasa_vend_esc5_tope = _escalon(5, 'tope')
    # --- Patrocinio ------------------------------------------------------------------------------------------------
    dcasa_vend_patrocinio = _campo('patrocinio')
    dcasa_vend_directos = _campo('directos')
    dcasa_vend_ventas_propias = _campo('ventas_propias')
    dcasa_vend_patrocinio_multiplo = _campo('patrocinio_multiplo')
    dcasa_vend_patrocinio_tope = _campo('patrocinio_tope')
    # --- Retención -------------------------------------------------------------------------------------------------
    dcasa_vend_retencion_dias = _campo('retencion_dias')
    dcasa_vend_primeras_ventas = _campo('primeras_ventas')
    dcasa_vend_primeras_dias = _campo('primeras_dias')
    # --- Límites ---------------------------------------------------------------------------------------------------
    dcasa_vend_techo = _campo('techo')
    dcasa_vend_freno = _campo('freno')
    # --- Canjes ----------------------------------------------------------------------------------------------------
    dcasa_vend_canje_minimo = _campo('canje_minimo')
    dcasa_vend_vigencia_horas = _campo('vigencia_horas')
    dcasa_vend_canjes_mes = _campo('canjes_mes')
    dcasa_vend_externos = fields.Boolean(
        'Canje para vendedores de afuera', readonly=True,
        help='Apagado hasta el dictamen del abogado y la contadora. No se enciende desde Ajustes.')
    dcasa_vend_efectivo = fields.Boolean(
        'Canje en efectivo', readonly=True,
        help='Apagado hasta el dictamen del abogado y la contadora. No se enciende desde Ajustes.')
    # --- Lo que acompaña a la pantalla -----------------------------------------------------------------------------
    dcasa_vend_motivo = fields.Char('Motivo del cambio', help='Opcional. Queda escrito en el historial.')
    dcasa_vend_estado = fields.Char('Qué reglas rigen ahora', compute='_compute_dcasa_vend_estado')
    dcasa_vend_resumen = fields.Html('Lo que cuesta y lo que cambia', compute='_compute_dcasa_vend_resumen',
                                     sanitize=False)
    # La pantalla cargó bien las cifras (si no, guardar no toca nada) y con qué versión estaba mirando (si mientras
    # tanto otra persona cambió algo, no se pisa su cambio).
    dcasa_vend_cargado = fields.Boolean()
    dcasa_vend_version_vista = fields.Integer()

    # ------------------------------------------------------------------------
    # Lo que se ve
    # ------------------------------------------------------------------------

    @api.model
    def _dcasa_vend_valores_iniciales(self):
        """Los valores con que se abre la pantalla: lo que rige hoy. Antes de leer nada se comprueba el permiso."""
        Reglas = self.env['dcasa.vend.reglas']
        Reglas._exigir_gerencia()
        _base, actuales, version = Reglas._estado()
        valores = {f'dcasa_vend_{clave}': valor for clave, valor in A.valores_de_pantalla(actuales).items()}
        canje = RV.seccion(actuales).get('canje') or {}
        valores.update(
            dcasa_vend_externos=bool(canje.get('externosHabilitado')),
            dcasa_vend_efectivo=bool(canje.get('efectivoHabilitado')),
            dcasa_vend_cargado=True, dcasa_vend_version_vista=version.get('numero', 0))
        return valores

    def _dcasa_vend_pantalla(self):
        """Lo que hay escrito en la pantalla ahora, ``{cifra: valor}``."""
        self.ensure_one()
        return {clave: self[f'dcasa_vend_{clave}'] for clave in A.CLAVES_DE_PANTALLA}

    def _compute_dcasa_vend_estado(self):
        try:
            texto = self._dcasa_vend_texto_del_estado()
        except (AccessError, R.FaltaConfigurar):
            texto = ''
        for ajustes in self:
            ajustes.dcasa_vend_estado = texto

    @api.model
    def _dcasa_vend_texto_del_estado(self):
        Reglas = self.env['dcasa.vend.reglas']
        Reglas._exigir_gerencia()
        base, _actuales, version = Reglas._estado()
        if not version:
            return self.env._('Rigen los valores de fábrica (puntos.json, versión %s). Todavía no se ha ajustado nada.',
                              base.get('version'))
        desde = fields.Datetime.context_timestamp(self, version['vigente_desde']).strftime('%d/%m/%Y %I:%M %p')
        texto = self.env._(
            'Rige la versión %(numero)s de las reglas, desde el %(desde)s, guardada por %(autor)s.',
            numero=version['numero'], desde=desde, autor=version.get('autor') or '?')
        if version.get('tipo') == 'fabrica':
            texto += ' ' + self.env._('Son los valores de fábrica.')
        if version.get('fabrica_version') and version['fabrica_version'] != base.get('version'):
            texto += ' ' + self.env._(
                'Ojo: las cifras de fábrica (puntos.json) cambiaron a la versión %s después de este ajuste; '
                'revisa que tus cifras sigan siendo las que quieres.', base.get('version'))
        return texto

    @api.depends(*DEPENDENCIAS)
    def _compute_dcasa_vend_resumen(self):
        for ajustes in self:
            try:
                ajustes.dcasa_vend_resumen = ajustes._dcasa_vend_resumen_html()
            except Exception:  # noqa: BLE001  — el resumen es una ayuda: si falla, no se cae la pantalla de Ajustes
                _logger.exception('No se pudo armar el resumen de costo de los ajustes de vendedores.')
                ajustes.dcasa_vend_resumen = Markup('')

    def _dcasa_vend_resumen_html(self):
        """Lo que cuesta con las cifras de la pantalla (aunque todavía no se guarden), lo que no deja guardar y lo
        que se va a cambiar. Se recalcula con cada cifra que se escribe."""
        self.ensure_one()
        Reglas = self.env['dcasa.vend.reglas']
        if not Reglas._puede_ajustar():
            return Markup('')
        base, actuales, version = Reglas._estado()
        try:
            resultado = A.calcular_cambio(base, actuales, version.get('ajustes') or {}, self._dcasa_vend_pantalla())
        except R.FaltaConfigurar as error:
            return Markup('<div class="o_dcasa_vend_resumen o_dcasa_vend_problemas">{}</div>').format(str(error))
        partes = []
        if resultado['problemas']:
            partes.append(Markup(
                '<div class="o_dcasa_vend_problemas"><strong>{}</strong><ul class="mb-0">{}</ul></div>').format(
                    self.env._('Esto no se puede guardar todavía:'),
                    Markup('').join(Markup('<li>{}</li>').format(p) for p in resultado['problemas'])))
        partes.append(self._dcasa_vend_html_del_costo(resultado['candidato']))
        if resultado['cambios']:
            partes.append(Markup(
                '<div class="o_dcasa_vend_cambios"><strong>{}</strong><ul class="mb-0">{}</ul></div>').format(
                    self.env._('Vas a cambiar (rige desde que guardes):'),
                    Markup('').join(Markup('<li>{}: <span class="text-muted">{}</span> → <strong>{}</strong></li>')
                                    .format(c['campo'], c['antes'], c['despues']) for c in resultado['cambios'])))
        else:
            partes.append(Markup('<p class="text-muted mb-0">{}</p>').format(self.env._('Todavía no cambiaste nada.')))
        return Markup('<div class="o_dcasa_vend_resumen">{}</div>').format(Markup('').join(partes))

    def _dcasa_vend_html_del_costo(self, reglas):
        costo = A.costo_del_programa(reglas)
        if not costo:
            return Markup('')
        lineas = [Markup('<p class="mb-1">{}</p>').format(self.env._(
            'Con estas cifras el programa cuesta hasta %(costo)s de la venta neta. Es la venta que más cuesta: un '
            'cliente nuevo, en el escalón más alto, con patrocinio y con los puntos que gana el cliente.',
            costo=f"{costo['peor']:.2f} %"))]
        if costo['equilibrio'] is not None:
            lineas.append(Markup('<p class="mb-1">{}</p>').format(self.env._(
                'Para que se pague solo, al menos %(equilibrio)s de lo vendido con código tiene que ser de clientes '
                'que no habrían comprado (con la ganancia supuesta de %(margen)s).',
                equilibrio=f"{costo['equilibrio']:.1f} %", margen=A.como_porcentaje(costo['margen']))))
        try:
            ppd = A.puntos_por_dolar(reglas)
            lineas.append(Markup('<p class="text-muted small mb-0">{}</p>').format(self.env._(
                'Cada %(ppd)s puntos valen $1. Los topes y mínimos se escriben en dólares.', ppd=f'{ppd:g}')))
        except R.FaltaConfigurar:
            pass
        return Markup('<div class="o_dcasa_vend_costo">{}</div>').format(Markup('').join(lineas))

    # ------------------------------------------------------------------------
    # Guardar
    # ------------------------------------------------------------------------

    def _dcasa_vend_guardar(self, estricto=True):
        """Entrega lo escrito en la pantalla a ``dcasa.vend.reglas``. Devuelve la versión nueva (vacío si no cambió
        nada). ``estricto``: si la pantalla no cargó las cifras, avisa en vez de callar."""
        self.ensure_one()
        Reglas = self.env['dcasa.vend.reglas']
        Reglas._exigir_gerencia()
        if not self.dcasa_vend_cargado:
            if estricto:
                raise UserError(self.env._('La pantalla no cargó las cifras del programa. Ciérrala, ábrela de nuevo '
                                           'y vuelve a intentar.'))
            return Reglas.browse()
        return Reglas._guardar_desde_pantalla(
            self._dcasa_vend_pantalla(), motivo=self.dcasa_vend_motivo, version_vista=self.dcasa_vend_version_vista)

    def action_dcasa_vend_fabrica(self):
        """Botón «Volver a los valores de fábrica»: una versión nueva igual a puntos.json. No borra el historial."""
        self.ensure_one()
        self.env['dcasa.vend.reglas']._volver_a_fabrica(
            motivo=self.dcasa_vend_motivo, version_vista=self.dcasa_vend_version_vista)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_dcasa_vend_historial(self):
        """Botón «Ver los cambios anteriores»."""
        self.env['dcasa.vend.reglas']._exigir_gerencia()
        return self.env['ir.actions.act_window']._for_xml_id('dcasa_socios.action_dcasa_vend_reglas')


class DcasaVendAjustes(models.TransientModel):
    """La pantalla de Gerencia: Socios › Configuración › Ajustes del programa de vendedores."""

    _name = 'dcasa.vend.ajustes'
    _inherit = ['dcasa.vend.ajustes.mixin']
    _description = 'Ajustes del programa de vendedores (pantalla de Gerencia)'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res.update({campo: valor for campo, valor in self._dcasa_vend_valores_iniciales().items()
                    if campo in fields_list})
        return res

    def execute(self):
        """Botón «Guardar»."""
        self.ensure_one()
        self._dcasa_vend_guardar()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def cancel(self):
        """Botón «Descartar»: vuelve a abrir la pantalla con lo que rige."""
        return self.env['ir.actions.act_window']._for_xml_id('dcasa_socios.action_dcasa_vend_ajustes')


class ResConfigSettingsVendedores(models.TransientModel):
    """El mismo bloque dentro de Ajustes (solo administradores del sistema)."""

    _name = 'res.config.settings'
    _inherit = ['res.config.settings', 'dcasa.vend.ajustes.mixin']

    @api.model
    def get_values(self):
        res = super().get_values()
        try:
            res.update(self._dcasa_vend_valores_iniciales())
        except (AccessError, R.FaltaConfigurar):
            # Sin permiso o sin una cifra de puntos.json: la pantalla se abre sin estas cifras y guardar no las toca.
            _logger.warning('Ajustes de vendedores: no se cargaron las cifras del programa.', exc_info=True)
        return res

    def set_values(self):
        super().set_values()
        for ajustes in self:
            ajustes._dcasa_vend_guardar(estricto=False)
