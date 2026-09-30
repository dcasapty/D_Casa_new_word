"""Importar el extracto del banco en CSV.

Sirve para Banco General, BAC, Banistmo, Caja de Ahorros o el reporte de Yappy: se
descarga el movimiento en CSV desde la banca en línea y se sube aquí. Las columnas se
reconocen por su nombre (fecha, descripción/concepto, monto o débito/crédito,
referencia); el separador (coma o punto y coma) se detecta solo.
"""
import base64
import csv
import io
import unicodedata

from odoo import fields, models
from odoo.addons.dcasa_contabilidad.models.conciliacion import leer_fecha, leer_monto
from odoo.exceptions import UserError

COLUMNAS = {
    'fecha': ('fecha', 'date', 'fecha transaccion', 'fecha de transaccion', 'fecha valor'),
    'concepto': ('descripcion', 'concepto', 'detalle', 'description', 'transaccion', 'memo'),
    'monto': ('monto', 'importe', 'amount', 'valor'),
    'debito': ('debito', 'debitos', 'retiro', 'retiros', 'cargo', 'cargos', 'debit'),
    'credito': ('credito', 'creditos', 'deposito', 'depositos', 'abono', 'abonos', 'credit'),
    'referencia': ('referencia', 'ref', 'reference', 'numero', 'no. documento', 'documento'),
}


def _normal(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').strip().lower())
    return ''.join(c for c in texto if not unicodedata.combining(c)).replace('.', '. ').replace('  ', ' ').strip()


def leer_csv(contenido):
    """Filas del CSV como dicts {fecha, concepto, monto, referencia}."""
    texto = contenido.decode('utf-8-sig', errors='replace')
    muestra = texto[:2048]
    separador = ';' if muestra.count(';') > muestra.count(',') else ','
    lector = csv.reader(io.StringIO(texto), delimiter=separador)
    filas = [f for f in lector if any(c.strip() for c in f)]
    if not filas:
        raise UserError('El archivo está vacío.')
    encabezado = [_normal(c) for c in filas[0]]
    posiciones = {}
    for clave, nombres in COLUMNAS.items():
        for i, nombre in enumerate(encabezado):
            if nombre in nombres or any(nombre.startswith(n) for n in nombres):
                posiciones.setdefault(clave, i)
    if 'fecha' not in posiciones or not ({'monto'} & posiciones.keys() or {'debito', 'credito'} <= posiciones.keys()):
        raise UserError(
            'No reconozco las columnas del archivo. Debe tener «Fecha» y «Monto» (o «Débito» y «Crédito»), '
            f'y de preferencia «Descripción». Encontré: {", ".join(filas[0])}.')
    resultado = []
    for numero, fila in enumerate(filas[1:], start=2):
        def celda(clave, fila=fila):
            i = posiciones.get(clave)
            return fila[i] if i is not None and i < len(fila) else ''
        try:
            fecha = leer_fecha(celda('fecha'))
            if 'monto' in posiciones:
                monto = leer_monto(celda('monto'))
            else:
                monto = abs(leer_monto(celda('credito'))) - abs(leer_monto(celda('debito')))
        except ValueError as error:
            raise UserError(f'Fila {numero}: no pude leer «{error}». Revisa la fecha o el monto.') from error
        if not monto:
            continue
        resultado.append({'fecha': fecha, 'concepto': celda('concepto').strip() or celda('referencia').strip(),
                          'monto': monto, 'referencia': celda('referencia').strip()})
    return resultado


class DcasaImportarExtracto(models.TransientModel):
    _name = 'dcasa.importar.extracto'
    _description = 'Importar extracto bancario'

    journal_id = fields.Many2one(
        'account.journal', string='Banco', required=True, domain=[('type', 'in', ('bank', 'cash'))],
        default=lambda self: self.env['account.journal'].search([('type', '=', 'bank')], limit=1))
    archivo = fields.Binary(string='Archivo CSV', required=True)
    nombre_archivo = fields.Char()

    def action_importar(self):
        self.ensure_one()
        filas = leer_csv(base64.b64decode(self.archivo))
        if not filas:
            raise UserError('El archivo no tiene movimientos con monto.')
        existentes = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id),
            ('date', '>=', min(f['fecha'] for f in filas)), ('date', '<=', max(f['fecha'] for f in filas)),
        ])
        ya = {(ln.date, ln.payment_ref or '', round(ln.amount, 2)) for ln in existentes}
        nuevas = [f for f in filas if (f['fecha'], f['concepto'], round(f['monto'], 2)) not in ya]
        if not nuevas:
            raise UserError('Todos los movimientos del archivo ya estaban importados.')
        extracto = self.env['account.bank.statement'].create({
            'name': f"{self.journal_id.name} · {min(f['fecha'] for f in nuevas):%d/%m/%Y}–"
                    f"{max(f['fecha'] for f in nuevas):%d/%m/%Y}",
            'journal_id': self.journal_id.id,
            'line_ids': [(0, 0, {
                'date': f['fecha'], 'payment_ref': f['concepto'], 'amount': f['monto'],
                'ref': f['referencia'] or False, 'journal_id': self.journal_id.id,
            }) for f in sorted(nuevas, key=lambda f: f['fecha'])],
        })
        conciliados = extracto.line_ids.dcasa_conciliar_automatico()
        return {
            'type': 'ir.actions.client',
            'tag': 'dcasa_conciliacion',
            'params': {'journal_id': self.journal_id.id,
                       'aviso': f'{len(nuevas)} movimientos importados · {len(conciliados)} conciliados solos'
                                + (f' · {len(filas) - len(nuevas)} ya estaban' if len(filas) > len(nuevas) else '')},
        }
