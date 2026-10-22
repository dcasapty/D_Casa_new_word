"""Alertas diarias por Telegram a Gerencia (etapa 4): stock bajo, ajustes grandes, cierre de mes y mermas del mes.

Apagadas de fábrica. Cada una sale solo si la dueña la enciende y pone su umbral en Ajustes de bodega; si no hay nada
que avisar, no se manda nada (sin «todo bien» diario). Van por el bot de Brian a cada persona de Gerencia que vinculó
su Telegram (``brian.telegram.enlace``), respetando la lista de chats permitidos de Brian. Nunca hacen fallar nada:
un error queda en el log.
"""
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MAX_LISTA = 10
GRUPO_GERENCIA = 'dcasa_base.group_gerencia'


def _cantidad(valor):
    valor = float(valor or 0.0)
    return f'{int(valor)}' if valor.is_integer() else f'{valor:.2f}'


class DcasaExistenciasAlertas(models.AbstractModel):
    _name = 'dcasa.existencias.alertas'
    _description = 'Alertas diarias de bodega por Telegram'

    @api.model
    def _stock_bajo(self, config):
        if not config.alerta_stock_bajo:
            return []
        umbral = config.alerta_stock_bajo_unidades
        Producto = self.env['product.product'].sudo().with_company(config.company_id)
        bajos = Producto.search([('is_storable', '=', True), ('sale_ok', '=', True), ('active', '=', True),
                                 ('qty_available', '<=', umbral)])
        bajos = bajos.sorted(lambda p: (p.qty_available, p.default_code or '', p.id))
        if not bajos:
            return []
        lineas = [self.env._('📦 %(n)s producto(s) con %(u)s unidad(es) o menos:', n=len(bajos), u=umbral)]
        lineas += [f'• {p.display_name}: {_cantidad(p.qty_available)}' for p in bajos[:MAX_LISTA]]
        if len(bajos) > MAX_LISTA:
            lineas.append(self.env._('• … y %s más (Inicio › productos por agotarse).', len(bajos) - MAX_LISTA))
        return lineas

    @api.model
    def _ajustes_grandes(self, config, desde):
        if not config.alerta_ajustes:
            return []
        filas = self.env['dcasa.bitacora.bodega'].sudo().search([
            ('company_id', '=', config.company_id.id), ('fecha', '>=', desde)], order='fecha')
        grandes = filas.filtered(lambda f: (config.alerta_ajustes_unidades and abs(f.diferencia)
                                            >= config.alerta_ajustes_unidades)
                                 or (config.alerta_ajustes_monto and abs(f.valor) >= config.alerta_ajustes_monto))
        if not grandes:
            return []
        lineas = [self.env._('⚖️ %s ajuste(s) grande(s) de existencias desde la última revisión:', len(grandes))]
        for fila in grandes[:MAX_LISTA]:
            lineas.append(self.env._(
                '• %(producto)s: %(antes)s → %(despues)s (%(valor)s) por %(quien)s. Motivo: %(motivo)s',
                producto=fila.producto_id.display_name, antes=_cantidad(fila.antes), despues=_cantidad(fila.despues),
                valor=f'${fila.valor:,.2f}', quien=fila.usuario_id.name, motivo=fila.motivo))
        if len(grandes) > MAX_LISTA:
            lineas.append(self.env._('• … y %s más (Inventario › Reportes › Bitácora de bodega).',
                                     len(grandes) - MAX_LISTA))
        return lineas

    @api.model
    def _cierre(self, config, hoy):
        if not config.alerta_cierre or hoy.day < config.alerta_cierre_dia:
            return []
        anterior = hoy.replace(day=1) - relativedelta(months=1)
        cerrado = self.env['dcasa.cierre.mes'].sudo().search_count([
            ('company_id', '=', config.company_id.id), ('mes', '=', anterior), ('estado', '=', 'cerrado')])
        bloqueado = config.company_id.sudo().fiscalyear_lock_date
        fin = hoy.replace(day=1) - timedelta(days=1)
        if cerrado or (bloqueado and bloqueado >= fin):
            return []
        meses = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
                 'octubre', 'noviembre', 'diciembre')
        return [self.env._('🗓️ El mes de %(mes)s de %(anio)s sigue sin cerrar (Facturación › Cierre de mes).',
                           mes=meses[anterior.month - 1], anio=anterior.year)]

    @api.model
    def _mermas(self, config, hoy):
        if not config.alerta_mermas:
            return []
        resumen = self.env['stock.scrap']._dcasa_resumen_mes(config.company_id, hoy)
        if not resumen['pasa']:
            return []
        porcentaje = f' ({resumen["pct"]:g} %)' if resumen['pct'] is not None else ''
        return [self.env._(
            '🧾 Las mermas, daños, muestras y regalos del mes suman %(total)s%(pct)s y pasan del %(tope)s %% de lo '
            'comprado (%(compras)s). Inventario › Reportes › Mermas del mes.',
            total=f'${resumen["total"]:,.2f}', pct=porcentaje, tope=f'{resumen["tope"]:g}',
            compras=f'${resumen["compras"]:,.2f}')]

    @api.model
    def _mensaje(self, config, ahora=None):
        """El texto de la alerta del día (``''`` si no hay nada que avisar o si están apagadas)."""
        if not config.alertas_activas:
            return ''
        ahora = ahora or fields.Datetime.now()
        hoy = fields.Date.context_today(self, ahora)
        desde = config.alertas_ultima or (ahora - timedelta(days=1))
        bloques = [b for b in (self._stock_bajo(config), self._ajustes_grandes(config, desde),
                               self._cierre(config, hoy), self._mermas(config, hoy)) if b]
        if not bloques:
            return ''
        partes = [self.env._("D'CASA · alertas de bodega del %s", hoy.strftime('%d/%m/%Y'))]
        partes += ['\n'.join(b) for b in bloques]
        return '\n\n'.join(partes)

    @api.model
    def _destinatarios(self, company):
        """Los chats de Telegram (Brian) de las personas de Gerencia vinculadas."""
        Enlace = self.env['brian.telegram.enlace'].sudo()
        gerencia = self.env.ref(GRUPO_GERENCIA)
        return Enlace.search([('activo', '=', True), ('user_id.all_group_ids', 'in', gerencia.ids),
                              ('user_id.company_ids', 'in', company.ids)])

    @api.model
    def _enviar(self, config, texto):
        enviados = 0
        Enlace = self.env['brian.telegram.enlace'].sudo()
        for enlace in self._destinatarios(config.company_id):
            try:
                with self.env.cr.savepoint():
                    Enlace._enviar(enlace.chat_id, texto)
                    enviados += 1
            except Exception:   # noqa: BLE001 — una alerta nunca rompe nada
                _logger.exception('Bodega: no se pudo mandar la alerta por Telegram')
        return enviados

    @api.model
    def _cron_alertas_diarias(self):
        ahora = fields.Datetime.now()
        for config in self.env['dcasa.existencias.config'].sudo().search([('alertas_activas', '=', True)]):
            try:
                texto = self._mensaje(config, ahora)
                if texto:
                    self._enviar(config, texto)
                    config.alertas_ultimo_envio = texto
                config.alertas_ultima = ahora
            except Exception:   # noqa: BLE001
                _logger.exception('Bodega: falló la revisión de alertas de %s', config.company_id.name)
        return True
