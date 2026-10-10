"""Motor de la consolidación: suma las empresas del grupo, elimina lo que es entre ellas y avisa de los descuadres.

Todo sale de los apuntes publicados (``account.move.line`` con ``parent_state = 'posted'``): nada se
guarda aparte. Las reglas de presentación son las de ``dcasa.reporte.contable`` (ingresos, pasivos y
patrimonio en positivo; lo de ejercicios anteriores pasa al patrimonio) para que la columna de cada
empresa coincida con el reporte de esa empresa sola.

Un apunte es **entre empresas** cuando su tercero (``partner_id``) es la ficha (``res.company.partner_id``)
de OTRA empresa del grupo. Se eliminan solo:

* balance: cuentas por cobrar y por pagar;
* resultados: ingresos y gastos.

Si lo que una empresa dice que le deben no es lo que la otra dice que debe (o sus ingresos no son los
gastos de la otra), el motor lo **avisa**; nunca lo esconde ni lo arregla. Lo que necesita criterio del
contador (utilidades no realizadas en inventario, participaciones minoritarias, conversión de monedas)
queda fuera.

Todos los métodos son privados: se llaman desde ``dcasa.consolidacion`` (que comprueba el grupo contable)
o desde los tests; ninguno es invocable por RPC.
"""
from collections import defaultdict

from odoo import api, models
from odoo.addons.dcasa_contabilidad.models.reportes import SECCIONES_BALANCE, SECCIONES_RESULTADOS, TIPOS_RESULTADOS
from odoo.exceptions import UserError
from odoo.fields import Domain

TIPOS_BALANCE = tuple(tipo for _c, _t, _g, tipos in SECCIONES_BALANCE for tipo in tipos)

# Sección -> título, signo con el que se presenta (el de los reportes) y grupo (solo en el balance).
SECCIONES = {
    **{clave: {'titulo': titulo, 'signo': signo, 'grupo': None}
       for clave, titulo, _tipos, signo in SECCIONES_RESULTADOS},
    **{clave: {'titulo': titulo, 'signo': 1 if grupo == 'activo' else -1, 'grupo': grupo}
       for clave, titulo, grupo, _tipos in SECCIONES_BALANCE},
}
SECCION_DE_TIPO = {
    **{tipo: clave for clave, _t, tipos, _s in SECCIONES_RESULTADOS for tipo in tipos},
    **{tipo: clave for clave, _t, _g, tipos in SECCIONES_BALANCE for tipo in tipos},
}
ORDEN_SECCIONES = {
    'resultados': {clave: i for i, (clave, *_) in enumerate(SECCIONES_RESULTADOS)},
    'balance': {clave: i for i, (clave, *_) in enumerate(SECCIONES_BALANCE)},
    'comprobacion': {},  # el balance de comprobación va por código
}

# Qué cuentas se eliminan entre empresas en cada reporte.
ELIMINABLES = {
    'resultados': TIPOS_RESULTADOS,
    'balance': ('asset_receivable', 'liability_payable'),
    'comprobacion': ('asset_receivable', 'liability_payable') + TIPOS_RESULTADOS,
}
CLASES = {'asset_receivable': 'cobrar', 'liability_payable': 'pagar', 'income': 'ingreso', 'income_other': 'ingreso'}

ANTERIORES = 'Resultados de ejercicios anteriores'
DEL_EJERCICIO = 'Resultado del ejercicio'
NO_ASIGNADOS = 'Resultados no asignados de ejercicios anteriores'


class Armado:
    """Va juntando las celdas de cada empresa, lo eliminado y los descuadres mientras se leen los apuntes.

    Una celda es ``[inicial, debe, haber, final]`` con el signo crudo (debe − haber).
    """

    def __init__(self, empresas, tipo, mapa):
        self.empresas = empresas
        self.tipo = tipo
        self.mapa = mapa
        self.posicion = {empresa.id: i for i, empresa in enumerate(empresas)}
        self.filas = {}
        self.celdas = defaultdict(lambda: [0.0] * 4)
        self.eliminado = defaultdict(lambda: [0.0] * 4)
        self.pares = defaultdict(float)
        self.sin_eliminar = defaultdict(float)

    def clave(self, empresa, cuenta):
        """La fila consolidada de una cuenta: el mapa manda sobre el código propio de la cuenta."""
        seccion = SECCION_DE_TIPO[cuenta.account_type]
        entrada = self.mapa.get((empresa.id, cuenta.id))
        codigo_propio = cuenta.code or ''
        codigo = entrada.codigo_consolidado if entrada else codigo_propio
        nombre = entrada.nombre_consolidado if entrada and entrada.nombre_consolidado else cuenta.name
        clave = (seccion, codigo, '' if codigo else nombre)
        # El nombre de la fila: el del mapa, si lo tiene; si no, el de la primera empresa del grupo que la tiene.
        prioridad = (0 if entrada and entrada.nombre_consolidado else 1, self.posicion[empresa.id], codigo_propio)
        actual = self.filas.get(clave)
        if actual is None or prioridad < actual['prioridad']:
            self.filas[clave] = {'seccion': seccion, 'codigo': codigo, 'nombre': nombre,
                                 'tipo_cuenta': cuenta.account_type, 'sintetica': 0, 'prioridad': prioridad}
        return clave

    def sumar(self, empresa, cuenta, vector):
        celda = self.celdas[(empresa.id, self.clave(empresa, cuenta))]
        for i, valor in enumerate(vector):
            celda[i] += valor

    def sintetica(self, empresa, nombre, indice, vector):
        """Filas del patrimonio que no son una cuenta (los resultados que el balance pasa al patrimonio)."""
        clave = ('patrimonio', '', nombre)
        self.filas.setdefault(clave, {'seccion': 'patrimonio', 'codigo': '', 'nombre': nombre,
                                      'tipo_cuenta': 'equity_unaffected', 'sintetica': indice, 'prioridad': (0, 0, '')})
        celda = self.celdas[(empresa.id, clave)]
        for i, valor in enumerate(vector):
            celda[i] += valor

    def eliminar(self, empresa, otra, cuenta, vector):
        """Apunte de ``empresa`` contra ``otra`` (del mismo grupo): se elimina si es de una cuenta eliminable."""
        if cuenta.account_type not in ELIMINABLES[self.tipo]:
            if cuenta.account_type != 'asset_cash':  # el dinero en banco con un tercero no es una deuda
                self.sin_eliminar[(empresa, otra, cuenta)] += vector[3]
            return
        clave = self.clave(empresa, cuenta)
        acumulado = self.eliminado[clave]
        for i, valor in enumerate(vector):
            acumulado[i] += valor
        clase = CLASES.get(cuenta.account_type, 'gasto')
        self.pares[(empresa.id, otra.id, clase)] += SECCIONES[clave[0]]['signo'] * vector[3]

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------

    def _signo(self, seccion):
        return 1 if self.tipo == 'comprobacion' else SECCIONES[seccion]['signo']

    def _se_queda(self, celda):
        """Mismas reglas que los reportes de una empresa: sin saldo (o sin movimiento) la cuenta no sale."""
        return any(celda[:3]) if self.tipo == 'comprobacion' else bool(celda[3])

    def _orden(self, item):
        (seccion, codigo, nombre), meta = item
        return (ORDEN_SECCIONES[self.tipo].get(seccion, 0), meta['sintetica'], codigo, nombre)

    def filas_calculadas(self, moneda):
        """[{seccion, codigo, nombre, tipo_cuenta, celdas: {columna: {inicial, debe, haber, importe}}}]."""
        redondear = moneda.round
        filas = []
        for clave, meta in sorted(self.filas.items(), key=self._orden):
            signo = self._signo(clave[0])

            def celda(vector, signo=signo):
                return {'inicial': vector[0], 'debe': vector[1], 'haber': vector[2],
                        'importe': redondear(signo * vector[3])}

            celdas = {}
            for empresa in self.empresas:
                vector = self.celdas.get((empresa.id, clave))
                if vector is None:
                    continue
                vector = [redondear(v) for v in vector]
                if self._se_queda(vector):
                    celdas[empresa.id] = celda(vector)
            eliminado = self.eliminado.get(clave)
            if eliminado:
                vector = [redondear(-v) for v in eliminado]
                if any(vector) if self.tipo == 'comprobacion' else vector[3]:
                    celdas['eliminaciones'] = celda(vector)
            if not celdas:
                continue
            celdas['consolidado'] = {campo: redondear(sum(c[campo] for c in celdas.values()))
                                     for campo in ('inicial', 'debe', 'haber', 'importe')}
            filas.append({'seccion': clave[0], 'codigo': clave[1], 'nombre': meta['nombre'],
                          'tipo_cuenta': meta['tipo_cuenta'], 'celdas': celdas})
        return filas


class DcasaConsolidacionMotor(models.AbstractModel):
    _name = 'dcasa.consolidacion.motor'
    _description = 'Motor de la consolidación'

    # ------------------------------------------------------------------
    # Lectura de apuntes
    # ------------------------------------------------------------------

    @api.model
    def _dominio_base(self, empresas, tipos):
        return Domain([('parent_state', '=', 'posted'), ('company_id', 'in', empresas.ids),
                       ('account_id.account_type', 'in', tipos)])

    @api.model
    def _sumas(self, dominio, por_tercero=False):
        """[(empresa, cuenta[, tercero], debe, haber, saldo)] en una sola consulta agrupada."""
        grupos = ['company_id', 'account_id'] + (['partner_id'] if por_tercero else [])
        return self.env['account.move.line']._read_group(dominio, grupos, ['debit:sum', 'credit:sum', 'balance:sum'])

    @api.model
    def _saldo_resultados(self, empresa, condiciones):
        """Suma (debe − haber) de las cuentas de resultados de una empresa que cumplen las condiciones."""
        dominio = Domain.AND([self._dominio_base(empresa, TIPOS_RESULTADOS), condiciones])
        grupos = self.env['account.move.line']._read_group(dominio, [], ['balance:sum'])
        return (grupos[0][0] if grupos else 0.0) or 0.0

    @api.model
    def _partes(self, empresas, tipo, desde, hasta):
        """Los pedazos de apuntes que arman cada reporte: [(dominio, 'periodo' | 'inicial' | 'saldo')]."""
        if tipo == 'resultados':
            base = self._dominio_base(empresas, TIPOS_RESULTADOS)
            return [(Domain.AND([base, [('date', '>=', desde), ('date', '<=', hasta)]]), 'periodo')]
        if tipo == 'balance':
            base = self._dominio_base(empresas, TIPOS_BALANCE)
            return [(Domain.AND([base, [('date', '<=', hasta)]]), 'saldo')]
        # Balance de comprobación: lo del periodo y el saldo inicial. En las cuentas de resultados el inicial
        # es solo lo del ejercicio en curso de CADA empresa (cada una puede tener su propio año fiscal).
        del_ejercicio = Domain.OR([
            Domain([('company_id', '=', empresa.id),
                    ('date', '>=', empresa.compute_fiscalyear_dates(desde)['date_from'])])
            for empresa in empresas])
        return [
            (Domain.AND([self._dominio_base(empresas, TIPOS_BALANCE + TIPOS_RESULTADOS),
                         [('date', '>=', desde), ('date', '<=', hasta)]]), 'periodo'),
            (Domain.AND([self._dominio_base(empresas, TIPOS_BALANCE), [('date', '<', desde)]]), 'inicial'),
            (Domain.AND([self._dominio_base(empresas, TIPOS_RESULTADOS), [('date', '<', desde)], del_ejercicio]),
             'inicial'),
        ]

    @api.model
    def _vector(self, destino, debe, haber, saldo):
        if destino == 'periodo':
            return [0.0, debe, haber, saldo]
        if destino == 'inicial':
            return [saldo, 0.0, 0.0, saldo]
        return [0.0, 0.0, 0.0, saldo]

    @api.model
    def _sinteticas(self, armado, empresas, tipo, desde, hasta):
        """Los resultados que pasan al patrimonio (igual que el balance y la comprobación de cada empresa)."""
        for empresa in empresas:
            if tipo == 'balance':
                inicio = empresa.compute_fiscalyear_dates(hasta)['date_from']
                anteriores = self._saldo_resultados(empresa, [('date', '<', inicio)])
                del_ejercicio = self._saldo_resultados(empresa, [('date', '>=', inicio), ('date', '<=', hasta)])
                armado.sintetica(empresa, ANTERIORES, 1, [0.0, 0.0, 0.0, anteriores])
                armado.sintetica(empresa, DEL_EJERCICIO, 2, [0.0, 0.0, 0.0, del_ejercicio])
            elif tipo == 'comprobacion':
                inicio = empresa.compute_fiscalyear_dates(desde)['date_from']
                no_asignado = self._saldo_resultados(empresa, [('date', '<', inicio)])
                armado.sintetica(empresa, NO_ASIGNADOS, 1, [no_asignado, 0.0, 0.0, no_asignado])

    # ------------------------------------------------------------------
    # Avisos
    # ------------------------------------------------------------------

    @api.model
    def _avisos(self, armado, empresas, moneda):
        avisos = []
        redondear, formato = moneda.round, moneda.format
        if len(empresas) == 1:
            avisos.append(self.env._('El grupo tiene una sola empresa: el consolidado es igual a esa empresa. '
                                     'Agrega las demás empresas del grupo para consolidar.'))
        for a in empresas:
            for b in empresas:
                if a == b:
                    continue
                cobrar = redondear(armado.pares.get((a.id, b.id, 'cobrar'), 0.0))
                pagar = redondear(armado.pares.get((b.id, a.id, 'pagar'), 0.0))
                if redondear(cobrar - pagar):
                    avisos.append(self.env._(
                        'Descuadre entre %(a)s y %(b)s de %(dif)s: %(a)s dice que %(b)s le debe %(x)s, pero %(b)s '
                        'dice que le debe %(y)s a %(a)s (por cobrar contra por pagar). Se eliminó cada lado por su '
                        'importe, así que la diferencia queda a la vista: revisa los asientos entre las dos empresas.',
                        a=a.name, b=b.name, dif=formato(abs(redondear(cobrar - pagar))), x=formato(cobrar),
                        y=formato(pagar)))
                ingreso = redondear(armado.pares.get((a.id, b.id, 'ingreso'), 0.0))
                gasto = redondear(armado.pares.get((b.id, a.id, 'gasto'), 0.0))
                if redondear(ingreso - gasto):
                    avisos.append(self.env._(
                        'Descuadre entre %(a)s y %(b)s de %(dif)s: %(a)s registra ingresos con %(b)s por %(x)s, pero '
                        '%(b)s registra gastos con %(a)s por %(y)s. Se eliminó cada lado por su importe. Puede ser '
                        'inventario o activos comprados entre empresas (requiere contador).',
                        a=a.name, b=b.name, dif=formato(abs(redondear(ingreso - gasto))), x=formato(ingreso),
                        y=formato(gasto)))
        secciones = defaultdict(set)
        for seccion, codigo, _nombre in armado.filas:
            if codigo:
                secciones[codigo].add(seccion)
        for codigo, claves in sorted(secciones.items()):
            if len(claves) > 1:
                avisos.append(self.env._(
                    'La cuenta consolidada %(codigo)s cae en secciones distintas (%(secciones)s) según la empresa: '
                    'cada parte se presenta en su sección. Revisa el mapa de cuentas.',
                    codigo=codigo, secciones=', '.join(SECCIONES[c]['titulo'] for c in sorted(claves))))
        for (empresa, otra, cuenta), saldo in sorted(armado.sin_eliminar.items(),
                                                     key=lambda item: (item[0][0].id, item[0][1].id, item[0][2].id)):
            if redondear(saldo):
                avisos.append(self.env._(
                    '%(a)s tiene un saldo %(tipo)s de %(monto)s con %(b)s en la cuenta %(cuenta)s, que no es por '
                    'cobrar ni por pagar: no se elimina. Si es un préstamo, un anticipo o un traspaso entre '
                    'empresas, revísalo con el contador.',
                    a=empresa.name, b=otra.name, monto=formato(abs(redondear(saldo))),
                    tipo=self.env._('deudor') if saldo > 0 else self.env._('acreedor'),
                    cuenta=f'{cuenta.with_company(empresa).code or ""} {cuenta.name}'.strip()))
        return avisos

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------

    @api.model
    def _calcular(self, empresas, tipo, desde, hasta):
        """{'filas': [...], 'advertencias': [...], 'moneda': res.currency} de las empresas del grupo.

        Se lee con los permisos de quien llama (sin sudo): las reglas de registro de cada apunte siguen
        mandando, con las empresas del grupo como empresas activas.
        """
        empresas = empresas.with_context(allowed_company_ids=empresas.ids)
        motor = self.with_context(allowed_company_ids=empresas.ids)
        monedas = empresas.currency_id
        if len(monedas) > 1:
            raise UserError(self.env._(
                'Estas empresas usan monedas distintas (%(monedas)s): todavía no se consolidan monedas distintas. '
                'Consolida solo empresas que lleven la contabilidad en la misma moneda.',
                monedas=', '.join(monedas.mapped('name'))))
        moneda = monedas[:1]
        mapa = {(m.company_id.id, m.account_id.id): m for m in
                motor.env['dcasa.consolidacion.mapa'].search([('company_id', 'in', empresas.ids)])}
        armado = Armado(empresas, tipo, mapa)
        partes = motor._partes(empresas, tipo, desde, hasta)
        for dominio, destino in partes:
            for empresa, cuenta, debe, haber, saldo in motor._sumas(dominio):
                armado.sumar(empresa, cuenta, motor._vector(destino, debe, haber, saldo))
        motor._sinteticas(armado, empresas, tipo, desde, hasta)
        if len(empresas) > 1:
            # Lo que una empresa hizo con otra del grupo: apuntes cuyo tercero es la ficha de la otra empresa.
            fichas = {empresa.partner_id.id: empresa for empresa in empresas}
            for dominio, destino in partes:
                entre_empresas = Domain.AND([dominio, [('partner_id', 'in', list(fichas))]])
                for empresa, cuenta, tercero, debe, haber, saldo in motor._sumas(entre_empresas, por_tercero=True):
                    otra = fichas.get(tercero.id)
                    if otra and otra != empresa:
                        armado.eliminar(empresa, otra, cuenta, motor._vector(destino, debe, haber, saldo))
        return {'filas': armado.filas_calculadas(moneda), 'advertencias': motor._avisos(armado, empresas, moneda),
                'moneda': moneda}
