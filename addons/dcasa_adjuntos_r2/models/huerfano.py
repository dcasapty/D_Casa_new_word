from odoo import fields, models


class AdjuntoR2Huerfano(models.Model):
    """Objetos de R2 que el GC vio sin referencia, y desde cuándo (ver ir.attachment._dcasa_r2_gc).

    Vive en la base a propósito: si la base se restaura a un punto anterior, la tabla vuelve
    con ella y la cuenta de cada objeto se rehace con las referencias de esa base.
    """
    _name = 'dcasa.adjunto.r2.huerfano'
    _description = 'Adjunto en R2 sin referencia (GC)'
    _order = 'visto_desde, id'

    clave = fields.Char(required=True, index=True, readonly=True)
    visto_desde = fields.Datetime(required=True, readonly=True)

    _clave_unica = models.Constraint('UNIQUE(clave)', 'Cada objeto de R2 se marca una sola vez.')
