"""Formatos de extracto bancario: cómo leer el CSV de cada banco.

Cada banco exporta su CSV a su manera (filas de título arriba, columnas con otro nombre,
coma decimal, cargos en positivo…). Un formato se configura UNA vez con un archivo real
del banco y la vista previa del asistente de importación; después se elige y listo. Sin
formato, el asistente reconoce solo las columnas comunes (fecha, descripción, monto o
débito/crédito, referencia).

No se trae ningún formato «de fábrica» de Banco General, Banistmo, BAC, Caja de Ahorros o
Yappy: cada uno se arma con un extracto real descargado por D'CASA (no se adivina el
formato de un banco).
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Clave legible (los xmlid de la selección no distinguen mayúsculas: %Y y %y chocarían) → strptime.
STRPTIME = {
    'dd/mm/aaaa': '%d/%m/%Y', 'dd/mm/aa': '%d/%m/%y', 'dd-mm-aaaa': '%d-%m-%Y', 'aaaa-mm-dd': '%Y-%m-%d',
    'mm/dd/aaaa': '%m/%d/%Y', 'dd/mmm/aaaa': '%d/%b/%Y', 'aaaammdd': '%Y%m%d',
}
SEPARADORES = {'coma': ',', 'punto_coma': ';', 'tabulador': '\t', 'barra': '|'}
FORMATOS_FECHA = [
    ('auto', 'Detectar sola'),
    ('dd/mm/aaaa', 'dd/mm/aaaa (31/12/2026)'),
    ('dd/mm/aa', 'dd/mm/aa (31/12/26)'),
    ('dd-mm-aaaa', 'dd-mm-aaaa (31-12-2026)'),
    ('aaaa-mm-dd', 'aaaa-mm-dd (2026-12-31)'),
    ('mm/dd/aaaa', 'mm/dd/aaaa (12/31/2026)'),
    ('dd/mmm/aaaa', 'dd/mmm/aaaa (31/Dec/2026)'),
    ('aaaammdd', 'aaaammdd (20261231)'),
]


class DcasaFormatoExtracto(models.Model):
    _name = 'dcasa.formato.extracto'
    _description = 'Formato de extracto bancario (CSV)'
    _order = 'sequence, name'

    name = fields.Char('Nombre', required=True, help='Por ejemplo «Banco General — cuenta corriente».')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    journal_ids = fields.Many2many(
        'account.journal', string='Bancos', domain=[('type', 'in', ('bank', 'cash', 'credit'))],
        help='Bancos que usan este formato. Al importar en uno de ellos se elige solo.')
    separador = fields.Selection(
        [('auto', 'Detectar solo'), ('coma', 'Coma ( , )'), ('punto_coma', 'Punto y coma ( ; )'),
         ('tabulador', 'Tabulador'), ('barra', 'Barra ( | )')], default='auto', required=True)
    codificacion = fields.Selection(
        [('auto', 'Detectar sola'), ('utf-8-sig', 'UTF-8'), ('cp1252', 'Windows (latin-1)')],
        default='auto', required=True, help='Si ves «Ã©» en vez de «é», elige «Windows».')
    filas_omitir = fields.Integer(
        'Filas antes del encabezado', default=0,
        help='Filas de título (nombre del banco, número de cuenta…) que hay ANTES de la fila con los nombres de '
             'las columnas. 0 = buscar el encabezado solo.')
    col_fecha = fields.Char('Columna de fecha', required=True, default='Fecha',
                            help='Nombre exacto del encabezado o número de columna (1 = la primera).')
    col_concepto = fields.Char('Columna de descripción', help='Nombre o número. Puedes poner varias separadas '
                                                             'por «+» para unirlas, p. ej. «Descripción + Detalle».')
    col_referencia = fields.Char('Columna de referencia')
    col_monto = fields.Char('Columna de monto', help='Un solo monto con signo (entradas +, salidas −).')
    col_debito = fields.Char('Columna de débitos (salidas)')
    col_credito = fields.Char('Columna de créditos (entradas)')
    formato_fecha = fields.Selection(FORMATOS_FECHA, default='auto', required=True)
    decimal = fields.Selection([('auto', 'Detectar'), ('punto', 'Punto (1,234.56)'), ('coma', 'Coma (1.234,56)')],
                               default='auto', required=True)
    invertir_signo = fields.Boolean(
        help='Para extractos donde los cargos vienen en positivo (algunas tarjetas de crédito).')
    notas = fields.Text()

    @api.constrains('col_monto', 'col_debito', 'col_credito')
    def _check_columnas(self):
        for formato in self:
            if not formato.col_monto and not (formato.col_debito and formato.col_credito):
                raise ValidationError(self.env._(
                    'Indica la columna de monto, o las dos de débitos y créditos.'))

    def _como_dict(self):
        """El formato como dict simple para el lector de CSV (que no depende del ORM)."""
        self.ensure_one()
        return {
            'separador': SEPARADORES.get(self.separador),
            'codificacion': None if self.codificacion == 'auto' else self.codificacion,
            'omitir': self.filas_omitir or 0,
            'columnas': {clave: valor.strip() for clave, valor in (
                ('fecha', self.col_fecha), ('concepto', self.col_concepto), ('referencia', self.col_referencia),
                ('monto', self.col_monto), ('debito', self.col_debito), ('credito', self.col_credito),
            ) if valor and valor.strip()},
            'formato_fecha': STRPTIME.get(self.formato_fecha),
            'decimal': {'punto': '.', 'coma': ','}.get(self.decimal),
            'invertir': self.invertir_signo,
        }
