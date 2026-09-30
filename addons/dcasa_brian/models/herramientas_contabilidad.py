"""Herramientas de contabilidad: reportes, facturas, pagos, conciliación y cierre de mes.

Las cifras las calcula Odoo (``dcasa.reporte.contable`` y ``dcasa.conciliacion``); aquí solo
se compactan para el chat. Una factura publicada o pagada NUNCA se edita desde Brian: se
corrige con nota de crédito, y eso lo hace una persona.
"""
from datetime import timedelta

from odoo import Command, api, models

from . import herramientas_comun as c
from .registro import BrianError, herramienta

FACTURACION = ('account.group_account_invoice',)
LECTOR_CONTABLE = ('account.group_account_readonly',)
CONTADOR = ('account.group_account_user',)
PARAM_FACTURA = {'type': 'string', 'description': 'Número («INV/2026/00012»), borrador («#45») o cliente/proveedor.'}
PARAM_PRODUCTO = {'type': 'string', 'description': 'Producto (nombre o código). En facturas de proveedor puede ser '
                                                    'un concepto libre, p. ej. «Flete de septiembre».'}
PARAM_CANTIDAD = {'type': 'number', 'description': 'Cantidad. Por defecto 1.'}
PARAM_PRECIO = {'type': 'number', 'description': 'Precio unitario. Si no lo das, el del producto.'}
REPORTES = ['estado_resultados', 'balance_general', 'balance_comprobacion', 'libro_mayor', 'itbms', 'analitica']
CAMPOS_FACTURA = {'fecha': 'invoice_date', 'vencimiento': 'invoice_date_due', 'referencia': 'ref',
                  'tercero': 'partner_id'}


class BrianHerramientasContabilidad(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _b_resumen_factura(self, factura):
        return {
            'factura': self._b_numero_factura(factura),
            'tipo': self._b_tipo_factura(factura),
            'tercero': factura.partner_id.display_name or '',
            'estado': self._b_estado_factura(factura),
            'fecha': c.fecha(factura.invoice_date),
            'vence': c.fecha(factura.invoice_date_due),
            'lineas': [{
                'concepto': linea.product_id.display_name or linea.name or '',
                'cantidad': c.cantidad(linea.quantity),
                'precio': c.moneda(linea.price_unit),
                'total': c.moneda(linea.price_total),
            } for linea in factura.invoice_line_ids.filtered(lambda ln: ln.display_type == 'product')][:c.MAX_FILAS],
            'subtotal': c.moneda(factura.amount_untaxed),
            'itbms': c.moneda(factura.amount_tax),
            'total': c.moneda(factura.amount_total),
            'pendiente': c.moneda(factura.amount_residual),
        }

    @api.model
    def _b_valores_linea(self, factura, producto, cantidad, precio):
        if cantidad is not None and cantidad <= 0:
            raise BrianError('La cantidad tiene que ser mayor que cero.')
        if precio is not None and precio < 0:
            raise BrianError('El precio no puede ser negativo.')
        valores = {'quantity': cantidad or 1}
        proveedor = factura.move_type in ('in_invoice', 'in_refund') if factura else False
        texto = str(producto or '').strip()
        hay = self.env['product.product'].search_count(
            ['|', '|', ('default_code', '=ilike', texto), ('barcode', '=ilike', texto),
             ('display_name', 'ilike', texto)], limit=1)
        if hay or not proveedor:
            valores['product_id'] = self._b_producto(texto).id
        else:
            if precio is None:
                raise BrianError(f'«{texto}» no es un producto del catálogo: para un concepto libre dime el precio.')
            valores['name'] = texto
        if precio is not None:
            valores['price_unit'] = precio
        return valores

    @api.model
    def _b_diario_pago(self, texto):
        dominio = [('type', 'in', ('bank', 'cash')), ('company_id', 'in', self.env.companies.ids)]
        diarios = self.env['account.journal'].search(dominio)
        if texto:
            return self._b_resolver('account.journal', texto, 'forma de pago', exactos=('code', 'name'),
                                    dominio=dominio)
        if len(diarios) == 1:
            return diarios
        raise BrianError('¿Con qué se pagó? Opciones: ' + '; '.join(diarios.mapped('name')) + '.')

    @api.model
    def _b_movimiento_banco(self, texto):
        texto = str(texto or '').strip()
        Linea = self.env['account.bank.statement.line']
        encontrados = Linea.search([('move_id.name', '=ilike', texto)], limit=2)
        if len(encontrados) == 1:
            return encontrados
        return self._b_resolver(
            'account.bank.statement.line', texto, 'movimiento bancario', dominio=[('is_reconciled', '=', False)],
            buscar=['|', ('payment_ref', 'ilike', texto), ('partner_id', 'ilike', texto)],
            describir=lambda ln: f'{ln.move_id.name} — {c.fecha(ln.date)} — {ln.payment_ref or ""} — '
                                 f'{c.moneda(ln.amount)}')

    # ------------------------------------------------------------------
    # Reportes
    # ------------------------------------------------------------------

    @herramienta(
        nombre='reporte_contable',
        descripcion='Reportes contables: estado de resultados, balance general, balance de comprobación, libro mayor '
                    'de una cuenta, resumen de ITBMS o rentabilidad analítica.',
        parametros={
            'reporte': {'type': 'string', 'enum': REPORTES, 'description': 'Cuál reporte.'},
            'periodo': c.PARAM_PERIODO, 'desde': c.PARAM_DESDE, 'hasta': c.PARAM_HASTA,
            'cuenta': {'type': 'string', 'description': 'Solo para libro_mayor: código o nombre de la cuenta, '
                                                        'p. ej. «Caja» o «101».'},
        },
        requeridos=['reporte'],
        nivel='lectura', categoria='contabilidad', grupos=LECTOR_CONTABLE,
        ejemplos=['utilidad del mes pasado → estado_resultados, mes_pasado', 'ITBMS a pagar este mes → itbms'],
    )
    def _h_reporte_contable(self, reporte, periodo=None, desde=None, hasta=None, cuenta=None):
        if reporte not in REPORTES:
            raise BrianError(f'Reporte desconocido. Usa uno de: {", ".join(REPORTES)}.')
        inicio, fin, etiqueta = self._b_rango(periodo, desde, hasta)
        cuenta_ids = None
        if reporte == 'libro_mayor':
            if not cuenta:
                raise BrianError('Para el libro mayor dime la cuenta (código o nombre), p. ej. «Caja».')
            cuenta_ids = self._b_resolver('account.account', cuenta, 'cuenta', exactos=('code',),
                                          dominio=[('company_ids', 'in', self.env.company.ids)]).ids
        datos = self.env['dcasa.reporte.contable'].obtener(reporte, desde=str(inicio), hasta=str(fin),
                                                           cuenta_ids=cuenta_ids)
        salida = {'reporte': datos['titulo'], 'periodo': f'{etiqueta} ({c.fecha(datos["desde"])} al '
                                                         f'{c.fecha(datos["hasta"])})'}
        return {**salida, **getattr(self, f'_b_compactar_{reporte}')(datos)}

    @staticmethod
    def _b_cuenta_txt(fila):
        return f'{fila["codigo"]} {fila["nombre"]}'.strip()

    def _b_compactar_estado_resultados(self, datos):
        r = datos['resumen']
        return {
            'secciones': [{'seccion': s['titulo'], 'total': c.moneda(s['total']),
                           'cuentas': [{'cuenta': self._b_cuenta_txt(f), 'monto': c.moneda(f['monto'])}
                                       for f in s['filas'][:5]]}
                          for s in datos['secciones'] if s['filas']],
            'utilidad_bruta': c.moneda(r['utilidad_bruta']),
            'utilidad_operativa': c.moneda(r['utilidad_operativa']),
            'utilidad_neta': c.moneda(r['utilidad_neta']),
            'margen_bruto': f'{r["margen_bruto"]} %' if r['margen_bruto'] is not None else 'sin ventas',
        }

    def _b_compactar_balance_general(self, datos):
        t = datos['totales']
        return {
            'secciones': [{'seccion': s['titulo'], 'total': c.moneda(s['total'])} for s in datos['secciones']],
            'activo': c.moneda(t['activo']), 'pasivo': c.moneda(t['pasivo']),
            'patrimonio': c.moneda(t['patrimonio']), 'pasivo_y_patrimonio': c.moneda(t['pasivo_y_patrimonio']),
            'cuadra': 'sí' if datos['cuadra'] else 'NO: revisar',
        }

    def _b_compactar_balance_comprobacion(self, datos):
        filas = datos['filas']
        return {
            'cuentas': len(filas),
            'filas': [{'cuenta': self._b_cuenta_txt(f), 'inicial': c.moneda(f['inicial']), 'debe': c.moneda(f['debe']),
                       'haber': c.moneda(f['haber']), 'final': c.moneda(f['final'])} for f in filas[:c.MAX_FILAS]],
            'mostradas': min(len(filas), c.MAX_FILAS),
            'totales': {k: c.moneda(v) for k, v in datos['totales'].items()},
            'cuadra': 'sí' if datos['cuadra'] else 'NO: revisar',
        }

    def _b_compactar_libro_mayor(self, datos):
        cuentas = []
        for cuenta in datos['cuentas']:
            lineas = cuenta['lineas']
            cuentas.append({
                'cuenta': self._b_cuenta_txt(cuenta), 'saldo_inicial': c.moneda(cuenta['inicial']),
                'debe': c.moneda(cuenta['debe']), 'haber': c.moneda(cuenta['haber']),
                'saldo_final': c.moneda(cuenta['final']), 'movimientos': len(lineas),
                'ultimos': [{'fecha': c.fecha(ln['fecha']), 'asiento': ln['asiento'], 'tercero': ln['tercero'],
                             'concepto': ln['concepto'][:60], 'debe': c.moneda(ln['debe']),
                             'haber': c.moneda(ln['haber']), 'saldo': c.moneda(ln['saldo'])}
                            for ln in lineas[-c.MAX_FILAS:]],
            })
        return {'cuentas': cuentas}

    def _b_compactar_itbms(self, datos):
        r = datos['resumen']
        return {
            'impuestos': [{'impuesto': f['nombre'], 'tipo': f['tipo'], 'base': c.moneda(f['base']),
                           'itbms': c.moneda(f['impuesto'])} for f in datos['filas']],
            'debito_fiscal_ventas': c.moneda(r['debito_fiscal']),
            'credito_fiscal_compras': c.moneda(r['credito_fiscal']),
            'a_pagar': c.moneda(r['a_pagar']),
        }

    def _b_compactar_analitica(self, datos):
        return {'cuentas': [{'plan': f['plan'], 'cuenta': f['nombre'], 'ingresos': c.moneda(f['ingresos']),
                             'costos': c.moneda(f['costos']), 'margen': c.moneda(f['margen'])}
                            for f in datos['filas'][:c.MAX_FILAS]]}

    # ------------------------------------------------------------------
    # Facturas: lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='facturas_pendientes',
        descripcion='Facturas por cobrar (de clientes) o por pagar (a proveedores) que siguen abiertas.',
        parametros={
            'tipo': {'type': 'string', 'enum': ['por_cobrar', 'por_pagar'], 'description': 'Por defecto por_cobrar.'},
            'solo_vencidas': {'type': 'boolean', 'description': 'true = solo las vencidas. Por defecto false.'},
            'tercero': {'type': 'string', 'description': 'Filtrar por cliente o proveedor. Opcional.'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['¿qué facturas debemos a proveedores? → por_pagar', 'facturas vencidas de clientes'],
    )
    def _h_facturas_pendientes(self, tipo='por_cobrar', solo_vencidas=False, tercero=None, limite=10):
        dominio = [('move_type', '=', 'in_invoice' if tipo == 'por_pagar' else 'out_invoice'),
                   ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]
        if solo_vencidas:
            dominio.append(('invoice_date_due', '<', self._b_hoy()))
        if tercero:
            dominio.append(('commercial_partner_id', '=', self._b_contacto(tercero, 'tercero').id))
        Move = self.env['account.move']
        facturas = Move.search(dominio, order='invoice_date_due, id')
        hoy = self._b_hoy()
        return {
            'tipo': 'por pagar' if tipo == 'por_pagar' else 'por cobrar',
            'facturas_abiertas': len(facturas),
            'total_pendiente': c.moneda(sum(facturas.mapped('amount_residual'))),
            'facturas': [{
                'factura': f.name, 'tercero': f.partner_id.display_name, 'fecha': c.fecha(f.invoice_date),
                'vence': c.fecha(f.invoice_date_due), 'total': c.moneda(f.amount_total),
                'pendiente': c.moneda(f.amount_residual),
                'vencida': bool(f.invoice_date_due and f.invoice_date_due < hoy),
            } for f in facturas[:c.limite(limite)]],
        }

    @herramienta(
        nombre='ver_factura',
        descripcion='Detalle de una factura de cliente o proveedor: estado, líneas, ITBMS, total y lo pendiente.',
        parametros={'factura': PARAM_FACTURA}, requeridos=['factura'],
        nivel='lectura', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['ver INV/2026/00012'],
    )
    def _h_ver_factura(self, factura):
        return self._b_resumen_factura(self._b_factura(factura))

    # ------------------------------------------------------------------
    # Facturas: construcción (solo en borrador)
    # ------------------------------------------------------------------

    @herramienta(
        nombre='crear_factura',
        descripcion='Crea una factura EN BORRADOR, de cliente o de proveedor, con una primera línea. '
                    'Más líneas con agregar_linea_factura; publicarla es aparte.',
        parametros={
            'tipo': {'type': 'string', 'enum': ['cliente', 'proveedor'], 'description': 'De cliente o de proveedor.'},
            'tercero': {'type': 'string', 'description': 'Cliente o proveedor (nombre, celular o RUC).'},
            'producto': PARAM_PRODUCTO, 'cantidad': PARAM_CANTIDAD, 'precio': PARAM_PRECIO,
        },
        requeridos=['tipo', 'tercero', 'producto'],
        nivel='construccion', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['factura de proveedor de Colchones S.A. por «Flete» $80'],
    )
    def _h_crear_factura(self, tipo, tercero, producto, cantidad=1, precio=None):
        if tipo not in ('cliente', 'proveedor'):
            raise BrianError('El tipo es «cliente» o «proveedor».')
        partner = self._b_contacto(tercero, 'proveedor' if tipo == 'proveedor' else 'cliente')
        tipo_mov = 'in_invoice' if tipo == 'proveedor' else 'out_invoice'
        valores = self._b_valores_linea(self.env['account.move'].new({'move_type': tipo_mov}), producto,
                                        cantidad, precio)
        factura = self.env['account.move'].create({
            'move_type': tipo_mov, 'partner_id': partner.id, 'invoice_date': self._b_hoy(),
            'invoice_line_ids': [Command.create(valores)],
        })
        return {'mensaje': f'Factura creada en borrador ({self._b_numero_factura(factura)}). Revísala y publícala '
                           'cuando esté lista.', **self._b_resumen_factura(factura)}

    @herramienta(
        nombre='agregar_linea_factura',
        descripcion='Agrega una línea a una factura que está en borrador.',
        parametros={'factura': PARAM_FACTURA, 'producto': PARAM_PRODUCTO, 'cantidad': PARAM_CANTIDAD,
                    'precio': PARAM_PRECIO},
        requeridos=['factura', 'producto'],
        nivel='construccion', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['agrega 2 SIL-010 a la factura #45'],
    )
    def _h_agregar_linea_factura(self, factura, producto, cantidad=1, precio=None):
        movimiento = self._b_factura(factura)
        self._b_exigir_factura_borrador(movimiento)
        movimiento.write({'invoice_line_ids': [
            Command.create(self._b_valores_linea(movimiento, producto, cantidad, precio))]})
        return {'mensaje': 'Línea agregada.', **self._b_resumen_factura(movimiento)}

    @herramienta(
        nombre='quitar_linea_factura',
        descripcion='Quita una línea (por producto o concepto) de una factura en borrador.',
        parametros={'factura': PARAM_FACTURA, 'producto': PARAM_PRODUCTO},
        requeridos=['factura', 'producto'],
        nivel='construccion', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['quita el flete de la factura #45'],
    )
    def _h_quitar_linea_factura(self, factura, producto):
        movimiento = self._b_factura(factura)
        self._b_exigir_factura_borrador(movimiento)
        texto = c.normalizar_texto(producto)
        lineas = movimiento.invoice_line_ids.filtered(lambda ln: ln.display_type == 'product')
        coinciden = lineas.filtered(lambda ln: texto in c.normalizar_texto(ln.product_id.display_name or ln.name))
        if len(coinciden) != 1:
            conceptos = '; '.join(ln.product_id.display_name or ln.name or '' for ln in lineas)
            raise BrianError(('Varias líneas coinciden' if coinciden else f'No hay una línea con «{producto}»')
                             + f'. La factura lleva: {conceptos}.')
        movimiento.write({'invoice_line_ids': [Command.delete(coinciden.id)]})
        return {'mensaje': 'Línea quitada.', **self._b_resumen_factura(movimiento)}

    @herramienta(
        nombre='editar_factura',
        descripcion='Cambia la fecha, el vencimiento, la referencia o el cliente/proveedor de una factura EN '
                    'BORRADOR. Una factura publicada o pagada no se edita.',
        parametros={
            'factura': PARAM_FACTURA,
            'campo': {'type': 'string', 'enum': list(CAMPOS_FACTURA), 'description': 'Qué cambiar.'},
            'valor': {'type': 'string', 'description': 'Nuevo valor: fecha dd/mm/aaaa, texto o nombre del tercero.'},
        },
        requeridos=['factura', 'campo', 'valor'],
        nivel='construccion', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['la factura #45 vence el 15/10/2026 → campo=vencimiento'],
    )
    def _h_editar_factura(self, factura, campo, valor):
        if campo not in CAMPOS_FACTURA:
            raise BrianError(f'Solo puedo cambiar: {", ".join(CAMPOS_FACTURA)}.')
        movimiento = self._b_factura(factura)
        self._b_exigir_factura_borrador(movimiento)
        if campo in ('fecha', 'vencimiento'):
            nuevo = c.leer_fecha(valor, campo)
            if campo == 'vencimiento':
                movimiento.invoice_payment_term_id = False
        elif campo == 'tercero':
            nuevo = self._b_contacto(valor, 'tercero').id
        else:
            nuevo = (valor or '').strip() or False
        movimiento.write({CAMPOS_FACTURA[campo]: nuevo})
        return {'mensaje': f'Actualicé {campo}.', **self._b_resumen_factura(movimiento)}

    # ------------------------------------------------------------------
    # Facturas y pagos: sensibles
    # ------------------------------------------------------------------

    @herramienta(
        nombre='publicar_factura',
        descripcion='Publica (valida) una factura en borrador: le da número y la registra en la contabilidad.',
        parametros={'factura': PARAM_FACTURA}, requeridos=['factura'],
        nivel='sensible', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['publica la factura #45'],
    )
    def _h_publicar_factura(self, factura):
        movimiento = self._b_factura(factura)
        if movimiento.state != 'draft':
            raise BrianError(f'{self._b_numero_factura(movimiento)} ya está {self._b_estado_factura(movimiento)}.')
        if not movimiento.invoice_line_ids.filtered(lambda ln: ln.display_type == 'product'):
            raise BrianError('La factura no tiene líneas: agrega al menos una antes de publicarla.')
        movimiento.action_post()
        return {'mensaje': f'Factura {movimiento.name} publicada.', **self._b_resumen_factura(movimiento)}

    @herramienta(
        nombre='registrar_pago',
        descripcion='Registra un cobro o pago de una factura publicada (total o parcial) con su forma de pago.',
        parametros={
            'factura': PARAM_FACTURA,
            'monto': {'type': 'number', 'description': 'Monto pagado. Si no lo das, el saldo pendiente completo.'},
            'forma_pago': {'type': 'string', 'description': 'Diario: «Efectivo», «Yappy», «Tarjeta», banco…'},
            'fecha': {'type': 'string', 'description': 'Fecha del pago dd/mm/aaaa. Por defecto hoy.'},
        },
        requeridos=['factura'],
        nivel='sensible', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['Ana pagó INV/2026/00012 por Yappy'],
    )
    def _h_registrar_pago(self, factura, monto=None, forma_pago=None, fecha=None):
        movimiento = self._b_factura(factura)
        if movimiento.state != 'posted':
            raise BrianError(f'{self._b_numero_factura(movimiento)} está {self._b_estado_factura(movimiento)}: '
                             'solo se pagan facturas publicadas.')
        pendiente = movimiento.amount_residual
        if movimiento.currency_id.is_zero(pendiente):
            raise BrianError(f'{movimiento.name} ya está pagada.')
        monto = pendiente if monto is None else monto
        if monto <= 0 or movimiento.currency_id.compare_amounts(monto, pendiente) > 0:
            raise BrianError(f'El monto tiene que ser mayor que cero y hasta {c.moneda(pendiente)} (lo pendiente).')
        diario = self._b_diario_pago(forma_pago)
        asistente = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=movimiento.ids).create({
                'amount': monto, 'journal_id': diario.id,
                'payment_date': c.leer_fecha(fecha, 'fecha del pago') or self._b_hoy(),
            })
        asistente._create_payments()
        return {'mensaje': f'Pago de {c.moneda(monto)} por {diario.name} registrado en {movimiento.name}.',
                'estado': self._b_estado_factura(movimiento), 'pendiente': c.moneda(movimiento.amount_residual)}

    # ------------------------------------------------------------------
    # Conciliación bancaria
    # ------------------------------------------------------------------

    @herramienta(
        nombre='movimientos_por_conciliar',
        descripcion='Movimientos del banco (o Yappy, caja) que faltan por conciliar, con la sugerencia de factura o '
                    'pago cuando hay una clara.',
        parametros={'banco': {'type': 'string', 'description': 'Nombre del banco o diario. Opcional: todos.'},
                    'limite': c.PARAM_LIMITE},
        nivel='lectura', categoria='contabilidad', grupos=CONTADOR,
        ejemplos=['¿qué falta conciliar en el banco?'],
    )
    def _h_movimientos_por_conciliar(self, banco=None, limite=10):
        Conciliacion = self.env['dcasa.conciliacion']
        diarios = Conciliacion.diarios()
        if banco:
            elegido = self._b_diario_pago(banco)
            diarios = [d for d in diarios if d['id'] == elegido.id]
        dominio = [('journal_id', 'in', [d['id'] for d in diarios]), ('is_reconciled', '=', False)]
        Linea = self.env['account.bank.statement.line']
        lineas = Linea.search(dominio, order='date desc, id desc', limit=c.limite(limite))
        filas = []
        for linea in lineas:
            sugeridos = [x for x in Conciliacion.candidatos(linea.id) if x['sugerido']]
            filas.append({
                'movimiento': linea.move_id.name, 'banco': linea.journal_id.name, 'fecha': c.fecha(linea.date),
                'concepto': linea.payment_ref or '', 'monto': c.moneda(linea.amount),
                'sugerencia': (f'{sugeridos[0]["asiento"]} — {sugeridos[0]["tercero"]} — '
                               f'{c.moneda(sugeridos[0]["pendiente"])}') if len(sugeridos) == 1 else '',
            })
        return {'por_conciliar': sum(d['pendientes'] for d in diarios),
                'por_banco': [{'banco': d['nombre'], 'pendientes': d['pendientes']} for d in diarios],
                'movimientos': filas}

    @herramienta(
        nombre='conciliar_movimiento',
        descripcion='Concilia un movimiento del banco con una factura o pago abierto. Sin «con», usa la sugerencia '
                    'si hay una sola clara.',
        parametros={
            'movimiento': {'type': 'string', 'description': 'Número del movimiento («BNK1/2026/00012») o su concepto.'},
            'con': {'type': 'string', 'description': 'Factura o pago que lo explica, p. ej. «INV/2026/00012». '
                                                     'Opcional.'},
        },
        requeridos=['movimiento'],
        nivel='sensible', categoria='contabilidad', grupos=CONTADOR,
        ejemplos=['concilia BNK1/2026/00012 con INV/2026/00012'],
    )
    def _h_conciliar_movimiento(self, movimiento, con=None):
        linea = self._b_movimiento_banco(movimiento)
        if linea.is_reconciled:
            raise BrianError(f'{linea.move_id.name} ya está conciliado.')
        Conciliacion = self.env['dcasa.conciliacion']
        candidatos = Conciliacion.candidatos(linea.id, busqueda=con or None)
        if con:
            texto = c.normalizar_texto(con)
            elegidos = [x for x in candidatos if texto == c.normalizar_texto(x['asiento'])] or candidatos
        else:
            elegidos = [x for x in candidatos if x['sugerido']]
        if len(elegidos) != 1:
            opciones = '; '.join(f'{x["asiento"]} — {x["tercero"]} — {c.moneda(x["pendiente"])}'
                                 for x in candidatos[:5]) or 'ninguna factura o pago abierto coincide'
            raise BrianError(f'No hay una única coincidencia clara para {linea.move_id.name} '
                             f'({c.moneda(linea.amount)}). Opciones: {opciones}. Dime con cuál conciliarlo.')
        elegido = elegidos[0]
        resultado = Conciliacion.conciliar(linea.id, apunte_ids=[elegido['id']])
        return {'mensaje': f'{linea.move_id.name} conciliado con {elegido["asiento"]}.' if resultado['conciliado']
                else f'{linea.move_id.name} quedó conciliado en parte con {elegido["asiento"]}; el resto sigue '
                     'pendiente.', 'conciliado_completo': resultado['conciliado']}

    # ------------------------------------------------------------------
    # Cierre de mes
    # ------------------------------------------------------------------

    @herramienta(
        nombre='guia_cierre_mes',
        descripcion='Lista de chequeo del cierre de mes con datos reales: conciliación bancaria, borradores, '
                    'ventas por facturar, cobros vencidos, ITBMS del mes y si el balance cuadra.',
        parametros={'mes': {'type': 'string', 'description': 'Mes a cerrar «mm/aaaa», p. ej. «09/2026». '
                                                            'Por defecto el mes pasado.'}},
        nivel='lectura', categoria='contabilidad', grupos=CONTADOR,
        ejemplos=['¿qué me falta para cerrar septiembre? → mes=09/2026'],
    )
    def _h_guia_cierre_mes(self, mes=None):
        if mes:
            try:
                numero, anio = (int(x) for x in mes.replace('-', '/').split('/'))
                inicio = self._b_hoy().replace(year=anio, month=numero, day=1)
            except ValueError as error:
                raise BrianError('Escribe el mes como mm/aaaa, p. ej. 09/2026.') from error
        else:
            inicio = (self._b_hoy().replace(day=1) - timedelta(days=1)).replace(day=1)
        fin = (inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        Move = self.env['account.move']
        pasos = []

        def paso(tarea, pendientes, detalle, como):
            pasos.append({'paso': len(pasos) + 1, 'tarea': tarea,
                          'estado': 'pendiente' if pendientes else 'listo', 'detalle': detalle,
                          **({'como': como} if pendientes else {})})

        sin_conciliar = self.env['account.bank.statement.line'].search(
            [('is_reconciled', '=', False), ('date', '<=', fin)])
        por_banco = {}
        for linea in sin_conciliar:
            por_banco[linea.journal_id.name] = por_banco.get(linea.journal_id.name, 0) + 1
        paso('Conciliar bancos, Yappy y caja', len(sin_conciliar),
             ', '.join(f'{b}: {n}' for b, n in por_banco.items()) or 'Todo conciliado',
             'movimientos_por_conciliar y conciliar_movimiento')
        for tipo, nombre in (('out_invoice', 'Facturas de cliente en borrador'),
                             ('in_invoice', 'Facturas de proveedor en borrador')):
            borradores = Move.search_count([('move_type', '=', tipo), ('state', '=', 'draft'),
                                            '|', ('invoice_date', '=', False), ('invoice_date', '<=', fin)])
            paso(nombre, borradores, c.plural(borradores, 'borrador', 'borradores'),
                 'Revísalas y publícalas (publicar_factura) o elimínalas desde Contabilidad.')
        asientos = Move.search_count([('move_type', '=', 'entry'), ('state', '=', 'draft'), ('date', '<=', fin)])
        paso('Asientos manuales en borrador', asientos, c.plural(asientos, 'asiento'),
             'Publícalos o descártalos desde Contabilidad › Asientos.')
        if self.env['sale.order'].has_access('read'):
            d_inicio, d_fin = self._b_limites(inicio, fin)
            por_facturar = self.env['sale.order'].search_count(
                [('invoice_status', '=', 'to invoice'), ('date_order', '<', d_fin)])
            paso('Ventas confirmadas por facturar', por_facturar, c.plural(por_facturar, 'venta'),
                 'Factúralas desde Ventas › Por facturar.')
        vencidas = Move.search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                                ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<=', fin)])
        paso('Revisar cobros vencidos', len(vencidas),
             f'{c.plural(len(vencidas), "factura")} por {c.moneda(sum(vencidas.mapped("amount_residual")))}',
             'clientes_que_deben; gestiona el cobro o registra los pagos recibidos.')
        Reporte = self.env['dcasa.reporte.contable']
        itbms = Reporte.itbms(desde=inicio, hasta=fin)['resumen']
        pasos.append({'paso': len(pasos) + 1, 'tarea': 'Declarar ITBMS del mes', 'estado': 'revisar',
                      'detalle': f'Débito {c.moneda(itbms["debito_fiscal"])} − crédito '
                                 f'{c.moneda(itbms["credito_fiscal"])} = a pagar {c.moneda(itbms["a_pagar"])}',
                      'como': 'reporte_contable con reporte=itbms para el detalle.'})
        balance = Reporte.balance_general(hasta=fin)
        paso('Balance general cuadra', not balance['cuadra'],
             'Activo = pasivo + patrimonio' if balance['cuadra'] else 'El balance NO cuadra',
             'Revisa el balance de comprobación con tu contador.')
        return {'mes': f'{inicio.month:02d}/{inicio.year}', 'desde': c.fecha(inicio), 'hasta': c.fecha(fin),
                'pendientes': sum(1 for p in pasos if p['estado'] == 'pendiente'), 'pasos': pasos}

