"""Importar el extracto del banco: CSV, OFX/QFX o CAMT.053.

* **CSV** de la banca en línea (Banco General, BAC, Banistmo, Caja de Ahorros, Yappy…): las
  columnas se reconocen por su nombre (fecha, descripción/concepto, monto o débito/crédito,
  referencia), el separador y la codificación se detectan, y el encabezado se busca aunque
  haya filas de título arriba. Si un banco no encaja, se guarda un **formato**
  (``dcasa.formato.extracto``) con sus columnas.
* **OFX / QFX** (Money/Quicken), que ofrecen muchos bancos: trae un identificador único por
  movimiento (FITID) y el saldo final.
* **CAMT.053** (ISO 20022, XML), por si algún banco lo ofrece.

Lo ya importado no se repite (por identificador del banco cuando lo hay; si no, por fecha,
descripción y monto). La vista previa muestra lo que se va a importar ANTES de importarlo.
"""
import base64
import csv
import io
import re
import unicodedata
from collections import Counter

from lxml import etree
from markupsafe import Markup

from odoo import api, fields, models
from odoo.addons.dcasa_contabilidad.models.conciliacion import leer_fecha, leer_monto
from odoo.exceptions import UserError

COLUMNAS = {
    'fecha': ('fecha', 'date', 'fecha transaccion', 'fecha de transaccion', 'fecha valor', 'fecha operacion',
              'fecha de operacion', 'fecha contable'),
    'concepto': ('descripcion', 'concepto', 'detalle', 'description', 'transaccion', 'memo', 'glosa'),
    'monto': ('monto', 'importe', 'amount', 'valor'),
    'debito': ('debito', 'debitos', 'retiro', 'retiros', 'cargo', 'cargos', 'debit'),
    'credito': ('credito', 'creditos', 'deposito', 'depositos', 'abono', 'abonos', 'credit'),
    'referencia': ('referencia', 'ref', 'reference', 'numero', 'no. documento', 'documento', 'no. de referencia'),
}
MAX_FILAS_TITULO = 15  # filas de título que se toleran antes del encabezado


def _normal(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').strip().lower())
    return ''.join(c for c in texto if not unicodedata.combining(c)).replace('.', '. ').replace('  ', ' ').strip()


def _decodificar(contenido, codificacion=None):
    if codificacion:
        return contenido.decode(codificacion, errors='replace')
    try:
        return contenido.decode('utf-8-sig')
    except UnicodeDecodeError:
        return contenido.decode('cp1252', errors='replace')


def _posiciones_auto(encabezado):
    posiciones = {}
    for clave, nombres in COLUMNAS.items():
        for i, nombre in enumerate(encabezado):
            if nombre in nombres or any(nombre.startswith(n) for n in nombres):
                posiciones.setdefault(clave, [i])
    return posiciones


def _posiciones_formato(encabezado, columnas):
    """Columnas de un formato: nombre del encabezado o número (1 = primera); «A + B» une varias."""
    posiciones = {}
    for clave, valor in columnas.items():
        indices = []
        for texto in valor.split('+'):
            parte = texto.strip()
            if parte.isdigit():
                indices.append(int(parte) - 1)
            elif _normal(parte) in encabezado:
                indices.append(encabezado.index(_normal(parte)))
            else:
                raise UserError(f'La columna «{parte}» del formato no está en el archivo. '
                                f'Encabezados: {", ".join(encabezado)}.')
        posiciones[clave] = indices
    return posiciones


def _suficiente(posiciones):
    return 'fecha' in posiciones and ('monto' in posiciones or {'debito', 'credito'} <= posiciones.keys())


def leer_csv(contenido, formato=None):
    """Filas del CSV como dicts {fecha, concepto, monto, referencia, id}.

    ``formato`` es el dict de ``dcasa.formato.extracto._como_dict()``; sin él, todo se detecta.
    """
    formato = formato or {}
    texto = _decodificar(contenido, formato.get('codificacion'))
    muestra = texto[:4096]
    separador = formato.get('separador') or max((';', ',', '\t', '|'), key=muestra.count)
    # Se conservan las filas vacías para contar «filas antes del encabezado» como se ven en el archivo.
    filas = list(csv.reader(io.StringIO(texto), delimiter=separador))
    llenas = [i for i, f in enumerate(filas) if any(c.strip() for c in f)]
    if not llenas:
        raise UserError('El archivo está vacío.')
    columnas = formato.get('columnas')
    if formato.get('omitir'):
        inicio = formato['omitir']
    else:  # el encabezado es la primera fila que tiene fecha y monto reconocibles
        inicio = next((i for i in llenas[:MAX_FILAS_TITULO]
                       if _suficiente(_posiciones_auto([_normal(c) for c in filas[i]]))), llenas[0])
    if inicio >= len(filas):
        raise UserError('El archivo no tiene tantas filas de título como dice el formato.')
    encabezado = [_normal(c) for c in filas[inicio]]
    posiciones = _posiciones_formato(encabezado, columnas) if columnas else _posiciones_auto(encabezado)
    if not _suficiente(posiciones):
        raise UserError(
            'No reconozco las columnas del archivo. Debe tener «Fecha» y «Monto» (o «Débito» y «Crédito»), '
            f'y de preferencia «Descripción». Encontré: {", ".join(filas[inicio])}. '
            'Si tu banco usa otros nombres, crea un formato en Bancos › Formatos de extracto.')
    decimal = formato.get('decimal')
    resultado = []
    for numero, fila in enumerate(filas[inicio + 1:], start=inicio + 2):
        def celda(clave, fila=fila):
            partes = [fila[i].strip() for i in posiciones.get(clave, []) if i < len(fila) and fila[i].strip()]
            return ' '.join(partes)
        if not any(c.strip() for c in fila) or not celda('fecha'):
            continue  # filas de totales o notas al pie
        try:
            fecha = leer_fecha(celda('fecha'), formato.get('formato_fecha'))
            if 'monto' in posiciones:
                monto = leer_monto(celda('monto'), decimal)
            else:
                monto = abs(leer_monto(celda('credito'), decimal)) - abs(leer_monto(celda('debito'), decimal))
        except ValueError as error:
            raise UserError(f'Fila {numero}: no pude leer «{error}». Revisa la fecha o el monto.') from error
        if formato.get('invertir'):
            monto = -monto
        if not monto:
            continue
        resultado.append({'fecha': fecha, 'concepto': celda('concepto') or celda('referencia'),
                          'monto': monto, 'referencia': celda('referencia'), 'id': None})
    return resultado


def _etiqueta(bloque, etiqueta):
    """Valor de <ETIQUETA> en OFX SGML (sin cierre) o XML (con cierre)."""
    encontrado = re.search(rf'<{etiqueta}>\s*([^<\r\n]*)', bloque, re.IGNORECASE)
    return encontrado.group(1).strip() if encontrado else ''


def leer_ofx(contenido):
    """Movimientos de un OFX/QFX (1.x SGML o 2.x XML) y el saldo final si viene."""
    texto = _decodificar(contenido)
    bloques = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', texto, re.IGNORECASE | re.DOTALL)
    filas = []
    for bloque in bloques:
        try:
            fecha = leer_fecha(_etiqueta(bloque, 'DTPOSTED')[:8], '%Y%m%d')
            monto = leer_monto(_etiqueta(bloque, 'TRNAMT'))
        except ValueError as error:
            raise UserError(f'Movimiento OFX ilegible: «{error}».') from error
        if not monto:
            continue
        nombre, memo = _etiqueta(bloque, 'NAME'), _etiqueta(bloque, 'MEMO')
        concepto = nombre if not memo or memo in nombre else f'{nombre} {memo}'.strip()
        filas.append({'fecha': fecha, 'concepto': concepto, 'monto': monto,
                      'referencia': _etiqueta(bloque, 'CHECKNUM') or _etiqueta(bloque, 'REFNUM'),
                      'id': _etiqueta(bloque, 'FITID') or None})
    saldo = re.search(r'<LEDGERBAL>.*?<BALAMT>\s*([^<\r\n]+)', texto, re.IGNORECASE | re.DOTALL)
    return filas, (leer_monto(saldo.group(1)) if saldo else None)


def leer_camt(contenido):
    """Movimientos de un CAMT.053 (ISO 20022) y el saldo de cierre (CLBD) si viene."""
    try:
        raiz = etree.fromstring(contenido, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as error:
        raise UserError('El XML del extracto está dañado.') from error

    def hijos(nodo, ruta):
        return nodo.xpath('/'.join(f"*[local-name()='{p}']" for p in ruta.split('/')))

    def texto(nodo, ruta):
        encontrados = hijos(nodo, ruta)
        return (encontrados[0].text or '').strip() if encontrados else ''

    filas = []
    for entrada in raiz.xpath("//*[local-name()='Ntry']"):
        signo = -1 if texto(entrada, 'CdtDbtInd') == 'DBIT' else 1
        fecha = texto(entrada, 'BookgDt/Dt') or texto(entrada, 'BookgDt/DtTm') or texto(entrada, 'ValDt/Dt')
        conceptos = [n.text.strip() for n in entrada.xpath(".//*[local-name()='Ustrd']") if n.text]
        conceptos = conceptos or [texto(entrada, 'AddtlNtryInf')]
        filas.append({'fecha': leer_fecha(fecha[:10], '%Y-%m-%d'), 'monto': signo * float(texto(entrada, 'Amt')),
                      'concepto': ' '.join(c for c in conceptos if c), 'referencia': texto(entrada, 'NtryRef'),
                      'id': texto(entrada, 'AcctSvcrRef') or None})
    saldo = None
    for balance in raiz.xpath("//*[local-name()='Bal']"):
        if texto(balance, 'Tp/CdOrPrtry/Cd') == 'CLBD':
            saldo = float(texto(balance, 'Amt')) * (-1 if texto(balance, 'CdtDbtInd') == 'DBIT' else 1)
    return filas, saldo


def tipo_de_archivo(contenido, nombre=''):
    cabeza = contenido[:2048].lstrip().upper()
    if cabeza.startswith(b'OFXHEADER') or b'<OFX>' in cabeza or (nombre or '').lower().endswith(('.ofx', '.qfx')):
        return 'ofx'
    if cabeza.startswith(b'<?XML') or b'CAMT.053' in contenido[:4096].upper():
        return 'camt'
    return 'csv'


def leer_extracto(contenido, nombre='', formato=None):
    """{'tipo', 'filas', 'saldo_final'} de cualquier extracto admitido."""
    tipo = tipo_de_archivo(contenido, nombre)
    if tipo == 'ofx':
        filas, saldo = leer_ofx(contenido)
    elif tipo == 'camt':
        filas, saldo = leer_camt(contenido)
    else:
        filas, saldo = leer_csv(contenido, formato), None
    return {'tipo': tipo, 'filas': filas, 'saldo_final': saldo}


class DcasaImportarExtracto(models.TransientModel):
    _name = 'dcasa.importar.extracto'
    _description = 'Importar extracto bancario'

    journal_id = fields.Many2one(
        'account.journal', string='Banco', required=True, domain=[('type', 'in', ('bank', 'cash', 'credit'))],
        default=lambda self: self.env['account.journal'].search([('type', '=', 'bank')], limit=1))
    archivo = fields.Binary(string='Archivo', required=True)
    nombre_archivo = fields.Char()
    formato_id = fields.Many2one(
        'dcasa.formato.extracto', string='Formato del CSV',
        help='Solo para CSV que no se reconocen solos. Vacío = detectar las columnas.')
    vista_previa = fields.Html(compute='_compute_vista_previa', sanitize=False)

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        formato = self.env['dcasa.formato.extracto'].search([('journal_ids', 'in', self.journal_id.ids)], limit=1)
        if formato:
            self.formato_id = formato

    def _leer(self):
        self.ensure_one()
        formato = self.formato_id._como_dict() if self.formato_id else None
        return leer_extracto(base64.b64decode(self.archivo), self.nombre_archivo or '', formato)

    def _separar_nuevas(self, filas):
        """(nuevas, repetidas): lo ya importado se reconoce por el id del banco o por fecha+descripción+monto."""
        if not filas:
            return [], []
        Linea = self.env['account.bank.statement.line']
        ids = [f['id'] for f in filas if f['id']]
        con_id = set(Linea.search([('journal_id', '=', self.journal_id.id), ('dcasa_id_importacion', 'in', ids)])
                     .mapped('dcasa_id_importacion')) if ids else set()
        existentes = Linea.search([
            ('journal_id', '=', self.journal_id.id),
            ('date', '>=', min(f['fecha'] for f in filas)), ('date', '<=', max(f['fecha'] for f in filas)),
        ])
        ya = {(ln.date, ln.payment_ref or '', round(ln.amount, 2)) for ln in existentes}
        nuevas, repetidas = [], []
        for fila in filas:
            repetida = fila['id'] in con_id if fila['id'] else (fila['fecha'], fila['concepto'],
                                                                 round(fila['monto'], 2)) in ya
            (repetidas if repetida else nuevas).append(fila)
        return nuevas, repetidas

    @api.depends('archivo', 'nombre_archivo', 'formato_id', 'journal_id')
    def _compute_vista_previa(self):
        for asistente in self:
            if not asistente.archivo or not asistente.journal_id:
                asistente.vista_previa = False
                continue
            try:
                leido = asistente._leer()
            except (UserError, ValueError) as error:
                mensaje = error.args[0] if error.args else str(error)
                asistente.vista_previa = Markup('<div class="alert alert-warning mb-0">%s</div>') % mensaje
                continue
            asistente.vista_previa = asistente._html_vista_previa(leido)

    def _html_vista_previa(self, leido):
        filas = leido['filas']
        if not filas:
            return Markup('<div class="alert alert-warning mb-0">El archivo no tiene movimientos con monto.</div>')
        nuevas, repetidas = self._separar_nuevas(filas)
        entradas = sum(f['monto'] for f in filas if f['monto'] > 0)
        salidas = -sum(f['monto'] for f in filas if f['monto'] < 0)
        moneda = self.journal_id.currency_id or self.env.company.currency_id
        resumen = (f'{leido["tipo"].upper()} · {len(filas)} movimientos del {min(f["fecha"] for f in filas):%d/%m/%Y} '
                   f'al {max(f["fecha"] for f in filas):%d/%m/%Y} · entradas {moneda.format(entradas)} · '
                   f'salidas {moneda.format(salidas)} · {len(nuevas)} nuevos')
        if repetidas:
            resumen += f' · {len(repetidas)} ya estaban (no se repiten)'
        if leido['saldo_final'] is not None:
            resumen += f' · saldo final del banco {moneda.format(leido["saldo_final"])}'
        cuerpo = Markup('').join(
            Markup('<tr%s><td>%s</td><td>%s</td><td>%s</td><td class="text-end">%s</td></tr>') % (
                Markup(' class="text-muted"') if f in repetidas else '', f['fecha'].strftime('%d/%m/%Y'),
                f['concepto'], f['referencia'], moneda.format(f['monto']))
            for f in filas[:8])
        return Markup(
            '<p class="mb-2"><strong>%s</strong></p><table class="table table-sm mb-0"><thead><tr><th>Fecha</th>'
            '<th>Descripción</th><th>Referencia</th><th class="text-end">Monto</th></tr></thead><tbody>%s</tbody>'
            '</table>%s') % (resumen, cuerpo, Markup('<p class="text-muted mb-0">…y %s más.</p>') % (len(filas) - 8)
                                                if len(filas) > 8 else '')

    def action_importar(self):
        self.ensure_one()
        leido = self._leer()
        filas = leido['filas']
        if not filas:
            raise UserError('El archivo no tiene movimientos con monto.')
        nuevas, repetidas = self._separar_nuevas(filas)
        if not nuevas:
            raise UserError('Todos los movimientos del archivo ya estaban importados.')
        valores = {
            'name': f"{self.journal_id.name} · {min(f['fecha'] for f in nuevas):%d/%m/%Y}–"
                    f"{max(f['fecha'] for f in nuevas):%d/%m/%Y}",
            'journal_id': self.journal_id.id,
            'line_ids': [(0, 0, {
                'date': f['fecha'], 'payment_ref': f['concepto'], 'amount': f['monto'],
                'ref': f['referencia'] or False, 'journal_id': self.journal_id.id,
                'dcasa_id_importacion': f['id'] or False,
            }) for f in sorted(nuevas, key=lambda f: f['fecha'])],
        }
        extracto = self.env['account.bank.statement'].create(valores)
        conciliados = extracto.line_ids.dcasa_conciliar_automatico()
        aviso = f'{len(nuevas)} movimientos importados · {len(conciliados)} conciliados solos'
        if repetidas:
            aviso += f' · {len(repetidas)} ya estaban'
        tipo = 'success'
        # Un movimiento con fecha en un mes cerrado (fecha de bloqueo) Odoo lo registra con otra fecha
        # (la primera abierta / hoy) sin avisar: el contador tiene que saberlo.
        movidos = sum((Counter(f['fecha'] for f in nuevas) - Counter(extracto.line_ids.mapped('date'))).values())
        if movidos:
            tipo = 'warning'
            aviso += (f' · OJO: {movidos} con fecha de un mes ya cerrado quedaron registrados con otra fecha '
                      '(la fecha de bloqueo manda). Si eran de ese mes, la gerencia tiene que reabrirlo con motivo.')
        saldo_banco = leido['saldo_final']
        if saldo_banco is not None and not repetidas:
            extracto.balance_end_real = saldo_banco
            moneda = self.journal_id.currency_id or self.env.company.currency_id
            if moneda.compare_amounts(extracto.balance_end, saldo_banco):
                tipo = 'warning'
                aviso += (f' · OJO: el saldo del banco es {moneda.format(saldo_banco)} y en D\'CASA queda '
                          f'{moneda.format(extracto.balance_end)}: falta algún extracto anterior o hay un '
                          'movimiento de más.')
        return {
            'type': 'ir.actions.client',
            'tag': 'dcasa_conciliacion',
            'params': {'journal_id': self.journal_id.id, 'aviso': aviso, 'aviso_tipo': tipo},
        }
