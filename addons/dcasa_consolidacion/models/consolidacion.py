"""Consolidación: los estados financieros de varias empresas del grupo en uno solo.

La persona de contabilidad elige las empresas, el reporte (estado de resultados, balance general o
balance de comprobación) y las fechas, y pulsa «Calcular». El motor (``dcasa.consolidacion.motor``)
suma cada empresa, elimina lo que es entre ellas y deja las líneas: una columna por empresa, una de
«Eliminaciones» y una de «Consolidado». Nada más se guarda aparte: si hay que rehacerlo, se vuelve a
calcular desde los asientos publicados.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

from .motor import SECCIONES

GRUPO_CONTADOR = 'account.group_account_user'
TIPOS_REPORTE = [('resultados', 'Estado de resultados'), ('balance', 'Balance general'),
                 ('comprobacion', 'Balance de comprobación')]
# Solo los cambian «Calcular» y «Volver a borrador»: así nadie puede dejar una consolidación «calculada» con
# líneas o advertencias a su gusto (por RPC el ``readonly`` de la vista no frena nada).
CAMPOS_DEL_CALCULO = frozenset({'estado', 'advertencias', 'calculada_por', 'calculada_el', 'linea_ids'})
# Con la consolidación calculada, lo que la define no se toca (las líneas dejarían de corresponderle).
CAMPOS_DE_ENTRADA = frozenset({'company_ids', 'tipo_reporte', 'fecha_desde', 'fecha_hasta'})
# Cómo suma cada sección a la utilidad neta: la utilidad es ingresos − costos − gastos.
SIGNO_UTILIDAD = {'ventas': 1, 'costo': -1, 'otros_ingresos': 1, 'gastos': -1, 'depreciacion': -1, 'otros_gastos': -1}


SELECCION_SECCIONES = [(clave, datos['titulo']) for clave, datos in SECCIONES.items()]


class DcasaConsolidacion(models.Model):
    _name = 'dcasa.consolidacion'
    _description = 'Consolidación de estados financieros'
    _inherit = ['mail.thread']
    _order = 'fecha_hasta desc, id desc'

    name = fields.Char('Nombre', required=True, tracking=True,
                       default=lambda self: self.env._('Consolidado del grupo'))
    company_ids = fields.Many2many(
        'res.company', 'dcasa_consolidacion_empresa_rel', 'consolidacion_id', 'company_id',
        string='Empresas del grupo', default=lambda self: self.env.companies, bypass_search_access=True,
        help='Las empresas que se suman. Solo puedes incluir empresas a las que tienes acceso; para elegir otra, '
             'actívala antes en el selector de empresas (arriba a la derecha). Todas deben usar la misma moneda.')
    empresas_resumen = fields.Char('Empresas', compute='_compute_empresas_resumen')
    tipo_reporte = fields.Selection(TIPOS_REPORTE, 'Reporte', required=True, default='resultados', tracking=True)
    fecha_desde = fields.Date('Desde', required=True, tracking=True,
                              default=lambda self: fields.Date.context_today(self).replace(day=1),
                              help='En el balance general no se usa: el balance es «al» último día.')
    fecha_hasta = fields.Date('Hasta', required=True, tracking=True, default=fields.Date.context_today)
    estado = fields.Selection([('borrador', 'Borrador'), ('calculada', 'Calculada')], 'Estado', default='borrador',
                              required=True, readonly=True, copy=False, tracking=True)
    calculada_por = fields.Many2one('res.users', 'Calculada por', readonly=True, copy=False)
    calculada_el = fields.Datetime('Calculada el', readonly=True, copy=False)
    advertencias = fields.Text('Advertencias', readonly=True, copy=False,
                               help='Lo que el cálculo encontró y que alguien debe revisar. Una por línea.')
    linea_ids = fields.One2many('dcasa.consolidacion.linea', 'consolidacion_id', 'Líneas', readonly=True, copy=False)
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True)
    monedas_distintas = fields.Boolean(compute='_compute_avisos_de_empresas')
    una_empresa = fields.Boolean(compute='_compute_avisos_de_empresas')
    utilidad_neta = fields.Monetary('Utilidad neta consolidada', compute='_compute_totales')
    diferencia = fields.Monetary(
        'Diferencia', compute='_compute_totales',
        help='Balance general: activo − (pasivo + patrimonio). Balance de comprobación: debe − haber. '
             'Debe ser cero; si no, mira las advertencias.')
    cuadra = fields.Boolean('Cuadra', compute='_compute_totales')

    _fechas_ordenadas = models.Constraint('CHECK (fecha_desde <= fecha_hasta)',
                                          'La fecha «Desde» debe ser anterior o igual a «Hasta».')

    # ------------------------------------------------------------------
    # Campos calculados
    # ------------------------------------------------------------------

    def _grupo(self):
        """Las empresas del grupo, completas y en orden. Se leen con sudo: la regla de ``res.company`` solo deja
        ver las empresas activas en el selector, y un grupo a medias daría un consolidado a medias."""
        self.ensure_one()
        ids = self.sudo().company_ids.sorted(lambda c: (c.sequence, c.id)).ids
        return self.env['res.company'].browse(ids)

    @api.depends('company_ids')
    def _compute_empresas_resumen(self):
        for consolidacion in self:
            consolidacion.empresas_resumen = ', '.join(consolidacion.sudo().company_ids.sorted('id').mapped('name'))

    @api.depends('company_ids.currency_id')
    def _compute_currency_id(self):
        for consolidacion in self:
            consolidacion.currency_id = consolidacion.sudo().company_ids.sorted('id')[:1].currency_id

    @api.depends('company_ids.currency_id')
    def _compute_avisos_de_empresas(self):
        for consolidacion in self:
            empresas = consolidacion.sudo().company_ids
            consolidacion.monedas_distintas = len(empresas.currency_id) > 1
            consolidacion.una_empresa = len(empresas) == 1

    @api.depends('linea_ids.importe', 'linea_ids.debe', 'linea_ids.haber', 'tipo_reporte', 'currency_id')
    def _compute_totales(self):
        for consolidacion in self:
            lineas = consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'consolidado')
            utilidad = diferencia = 0.0
            if consolidacion.tipo_reporte == 'resultados':
                utilidad = sum(SIGNO_UTILIDAD[ln.seccion] * ln.importe for ln in lineas)
            elif consolidacion.tipo_reporte == 'balance':
                diferencia = sum((1 if SECCIONES[ln.seccion]['grupo'] == 'activo' else -1) * ln.importe
                                 for ln in lineas)
            else:
                diferencia = sum(ln.debe - ln.haber for ln in lineas)
            moneda = consolidacion.currency_id
            consolidacion.utilidad_neta = moneda.round(utilidad) if moneda else utilidad
            consolidacion.diferencia = moneda.round(diferencia) if moneda else diferencia
            consolidacion.cuadra = not consolidacion.diferencia

    # ------------------------------------------------------------------
    # Seguridad
    # ------------------------------------------------------------------

    @api.constrains('company_ids')
    def _check_empresas(self):
        for consolidacion in self:
            if not consolidacion.sudo().company_ids:
                raise ValidationError(self.env._('Elige al menos una empresa del grupo.'))
            consolidacion._comprobar_empresas_permitidas()

    def _comprobar_empresas_permitidas(self):
        """Solo se consolida con empresas a las que la persona tiene acceso."""
        self.ensure_one()
        if self.env.su:
            return
        sin_acceso = self.sudo().company_ids - self.env.user.company_ids
        if sin_acceso:
            raise AccessError(self.env._('No tienes acceso a estas empresas: %s. Quítalas del grupo.',
                                         ', '.join(sin_acceso.mapped('name'))))

    def _exigir_contador(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_CONTADOR):
            raise AccessError(self.env._('Calcular una consolidación es de quien lleva la contabilidad.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                if CAMPOS_DEL_CALCULO.intersection(k for k, v in vals.items() if v and v != 'borrador'):
                    raise AccessError(self.env._('Las líneas, el estado y las advertencias los pone «Calcular».'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if CAMPOS_DEL_CALCULO.intersection(vals):
                raise AccessError(self.env._('Las líneas, el estado y las advertencias solo cambian con «Calcular» '
                                             'y «Volver a borrador».'))
            if CAMPOS_DE_ENTRADA.intersection(vals) and self.filtered(lambda c: c.estado == 'calculada'):
                raise UserError(self.env._('Esta consolidación ya está calculada: pulsa «Volver a borrador» para '
                                           'cambiar las empresas, el reporte o las fechas.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Calcular
    # ------------------------------------------------------------------

    def action_calcular(self):
        """(Re)genera las líneas desde los asientos publicados. Solo contabilidad."""
        self._exigir_contador()
        for consolidacion in self:
            consolidacion._calcular()
        return True

    def action_borrador(self):
        """Suelta las líneas para poder cambiar las empresas, el reporte o las fechas."""
        self._exigir_contador()
        for consolidacion in self:
            consolidacion.check_access('write')
            consolidacion.sudo().write({'estado': 'borrador', 'linea_ids': [Command.clear()], 'advertencias': False,
                                        'calculada_por': False, 'calculada_el': False})
            consolidacion.message_post(body=self.env._('Vuelta a borrador: las líneas calculadas se descartaron.'))
        return True

    def action_ver_pivote(self):
        """Las líneas calculadas en tabla dinámica (filas = cuenta, columnas = empresa/eliminaciones)."""
        self.ensure_one()
        self.check_access('read')
        return {
            'type': 'ir.actions.act_window', 'name': self.name, 'res_model': 'dcasa.consolidacion.linea',
            'view_mode': 'pivot,list', 'domain': [('consolidacion_id', '=', self.id)],
            'context': {'search_default_sin_consolidado': 1},
        }

    def _calcular(self):
        self.ensure_one()
        self.check_access('write')
        empresas = self._grupo()
        self._comprobar_empresas_permitidas()
        resultado = self.env['dcasa.consolidacion.motor']._calcular(
            empresas, self.tipo_reporte, self.fecha_desde, self.fecha_hasta)
        lineas = self._valores_de_lineas(empresas, resultado['filas'])
        advertencias = resultado['advertencias']
        # Las líneas son un resultado, no un dato que se edite: se escriben con sudo, pero solo después de
        # comprobar el grupo contable y de calcular con los permisos de la persona.
        consolidacion = self.sudo()
        consolidacion.linea_ids.unlink()
        consolidacion.write({
            'estado': 'calculada', 'calculada_por': self.env.user.id, 'calculada_el': fields.Datetime.now(),
            'advertencias': '\n'.join(advertencias) or False,
            'linea_ids': [Command.create(valores) for valores in lineas],
        })
        self.message_post(body=self.env._(
            'Calculada por %(usuario)s: %(lineas)s líneas, %(avisos)s advertencias.',
            usuario=self.env.user.name, lineas=len(lineas), avisos=len(advertencias)))

    def _valores_de_lineas(self, empresas, filas):
        columnas = [(empresa.id, empresa.name, 'empresa') for empresa in empresas.sudo()]
        columnas += [('eliminaciones', self.env._('Eliminaciones'), 'eliminaciones'),
                     ('consolidado', self.env._('Consolidado'), 'consolidado')]
        con_detalle = self.tipo_reporte == 'comprobacion'  # inicial, debe y haber solo tienen sentido ahí
        valores = []
        for n, fila in enumerate(filas):
            cuenta = f'{fila["codigo"]} {fila["nombre"]}'.strip()
            for orden, (clave, etiqueta, tipo_columna) in enumerate(columnas):
                celda = fila['celdas'].get(clave)
                if celda is None:
                    continue
                valores.append({
                    'sequence': n * 1000 + orden, 'fila': n, 'seccion': fila['seccion'], 'codigo': fila['codigo'],
                    'nombre': fila['nombre'], 'cuenta': cuenta, 'tipo_cuenta': fila['tipo_cuenta'],
                    'columna': etiqueta, 'tipo_columna': tipo_columna, 'importe': celda['importe'],
                    'inicial': celda['inicial'] if con_detalle else 0.0,
                    'debe': celda['debe'] if con_detalle else 0.0,
                    'haber': celda['haber'] if con_detalle else 0.0,
                })
        return valores

    # ------------------------------------------------------------------
    # Para el PDF
    # ------------------------------------------------------------------

    def _matriz(self):
        """Las líneas calculadas como tabla: columnas, secciones con sus filas y totales, y el resumen."""
        self.ensure_one()
        if self.estado != 'calculada':
            raise UserError(self.env._('Calcula la consolidación antes de imprimirla.'))
        moneda = self.currency_id
        empresas = self._grupo().sudo()
        comprobacion = self.tipo_reporte == 'comprobacion'
        columnas = [{'clave': e.name, 'etiqueta': e.name, 'campo': 'importe'} for e in empresas]
        columnas.append({'clave': 'eliminaciones', 'etiqueta': self.env._('Eliminaciones'), 'campo': 'importe'})
        if comprobacion:
            columnas += [
                {'clave': 'consolidado', 'campo': 'inicial', 'etiqueta': self.env._('Consolidado: saldo inicial')},
                {'clave': 'consolidado', 'campo': 'debe', 'etiqueta': self.env._('Consolidado: debe')},
                {'clave': 'consolidado', 'campo': 'haber', 'etiqueta': self.env._('Consolidado: haber')},
                {'clave': 'consolidado', 'campo': 'importe', 'etiqueta': self.env._('Consolidado: saldo final')},
            ]
        else:
            columnas.append({'clave': 'consolidado', 'etiqueta': self.env._('Consolidado'), 'campo': 'importe'})
        n = len(columnas)

        filas = {}
        for linea in self.linea_ids.sorted(lambda ln: (ln.sequence, ln.id)):
            fila = filas.setdefault(linea.fila, {'seccion': linea.seccion, 'codigo': linea.codigo or '',
                                                 'nombre': linea.nombre, 'celdas': {}})
            fila['celdas'][linea.columna if linea.tipo_columna == 'empresa' else linea.tipo_columna] = linea

        secciones = []
        for fila in filas.values():
            fila['valores'] = [moneda.round(getattr(fila['celdas'][c['clave']], c['campo']))
                               if c['clave'] in fila['celdas'] else 0.0 for c in columnas]
            clave = 'todas' if comprobacion else fila['seccion']
            if not secciones or secciones[-1]['clave'] != clave:
                secciones.append({'clave': clave, 'filas': [],
                                  'titulo': False if comprobacion else SECCIONES[clave]['titulo']})
            secciones[-1]['filas'].append(fila)
        for seccion in secciones:
            seccion['totales'] = [moneda.round(sum(f['valores'][i] for f in seccion['filas'])) for i in range(n)]
        por_clave = {s['clave']: s['totales'] for s in secciones}

        def total(*claves):
            return [moneda.round(sum(por_clave.get(clave, [0.0] * n)[i] for clave in claves)) for i in range(n)]

        def mas(a, b):
            return [moneda.round(x + y) for x, y in zip(a, b, strict=True)]

        def menos(a, b):
            return [moneda.round(x - y) for x, y in zip(a, b, strict=True)]

        if self.tipo_reporte == 'resultados':
            bruta = menos(total('ventas'), total('costo'))
            operativa = menos(menos(bruta, total('gastos')), total('depreciacion'))
            neta = menos(mas(operativa, total('otros_ingresos')), total('otros_gastos'))
            resumen = [{'etiqueta': self.env._('Utilidad bruta'), 'valores': bruta},
                       {'etiqueta': self.env._('Utilidad operativa'), 'valores': operativa},
                       {'etiqueta': self.env._('Utilidad neta'), 'valores': neta}]
        elif self.tipo_reporte == 'balance':
            activo = total('activo_corriente', 'activo_no_corriente')
            pasivo_y_patrimonio = total('pasivo_corriente', 'pasivo_no_corriente', 'patrimonio')
            resumen = [{'etiqueta': self.env._('Total activo'), 'valores': activo},
                       {'etiqueta': self.env._('Total pasivo y patrimonio'), 'valores': pasivo_y_patrimonio},
                       {'etiqueta': self.env._('Diferencia'), 'valores': menos(activo, pasivo_y_patrimonio)}]
        else:
            resumen = [{'etiqueta': self.env._('Totales'), 'valores': por_clave.get('todas', [0.0] * n)}]

        titulos = {'resultados': self.env._('Estado de resultados consolidado'),
                   'balance': self.env._('Balance general consolidado'),
                   'comprobacion': self.env._('Balance de comprobación consolidado')}
        formato = '%d/%m/%Y'
        if self.tipo_reporte == 'balance':
            periodo = self.env._('Al %s', self.fecha_hasta.strftime(formato))
        else:
            periodo = self.env._('Del %(desde)s al %(hasta)s', desde=self.fecha_desde.strftime(formato),
                                 hasta=self.fecha_hasta.strftime(formato))
        return {
            'titulo': titulos[self.tipo_reporte], 'periodo': periodo, 'empresas': ', '.join(empresas.mapped('name')),
            'columnas': columnas, 'ancho': 2 + n, 'secciones': secciones, 'resumen': resumen,
            'advertencias': (self.advertencias or '').splitlines(), 'cuadra': self.cuadra,
            'diferencia': self.diferencia, 'tipo_reporte': self.tipo_reporte,
        }


class DcasaConsolidacionLinea(models.Model):
    _name = 'dcasa.consolidacion.linea'
    _description = 'Línea de consolidación'
    _order = 'sequence, id'

    consolidacion_id = fields.Many2one('dcasa.consolidacion', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer()
    fila = fields.Integer('Fila')
    seccion = fields.Selection(SELECCION_SECCIONES, 'Sección', required=True)
    codigo = fields.Char('Código')
    nombre = fields.Char('Nombre de la cuenta')
    cuenta = fields.Char('Cuenta', help='Código y nombre de la cuenta consolidada.')
    tipo_cuenta = fields.Selection('_selection_tipo_cuenta', 'Tipo de cuenta')
    columna = fields.Char('Columna', required=True, help='Una empresa, «Eliminaciones» o «Consolidado».')
    tipo_columna = fields.Selection([('empresa', 'Empresa'), ('eliminaciones', 'Eliminaciones'),
                                     ('consolidado', 'Consolidado')], 'Tipo de columna', required=True)
    currency_id = fields.Many2one(related='consolidacion_id.currency_id', store=True)
    importe = fields.Monetary('Importe', help='Con los mismos signos que los reportes: ingresos, pasivos y '
                                              'patrimonio en positivo. En el balance de comprobación, debe − haber.')
    inicial = fields.Monetary('Saldo inicial', help='Solo en el balance de comprobación.')
    debe = fields.Monetary('Debe', help='Solo en el balance de comprobación.')
    haber = fields.Monetary('Haber', help='Solo en el balance de comprobación.')

    @api.model
    def _selection_tipo_cuenta(self):
        return self.env['account.account']._fields['account_type']._description_selection(self.env)
