"""Posibles duplicados: lo que ya estaba repetido antes del candado, para limpiarlo con calma.

Vista de solo lectura (SQL) con una fila por cada celular, correo o RUC/cédula que comparten dos o más FICHAS
(contactos sin padre que no son usuario, empleado ni la empresa propia). Desde la fila se abren las fichas y se fusionan
con el asistente de Odoo (Acción › Fusionar).
"""
from odoo import fields, models, tools
from odoo.exceptions import UserError

FICHA = """
    p.parent_id IS NULL
    AND NOT EXISTS (SELECT 1 FROM res_users u WHERE u.partner_id = p.id)
    AND NOT EXISTS (SELECT 1 FROM hr_employee e WHERE e.work_contact_id = p.id)
    AND NOT EXISTS (SELECT 1 FROM res_company c WHERE c.partner_id = p.id)
"""


class DcasaContactoDuplicado(models.Model):
    _name = 'dcasa.contacto.duplicado'
    _description = 'Posible duplicado de contacto'
    _auto = False
    _order = 'tipo, cantidad desc, valor'
    _rec_name = 'valor'
    _depends = {'res.partner': ['name', 'parent_id', 'dcasa_celular', 'dcasa_telefono_llave', 'email_normalized',
                                'dcasa_vat_llave']}
    # El id sale del dato (tipo + valor), no de la posición: una fila no cambia de id cuando otras se arreglan, así
    # un clic en «Fusionar» nunca cae en otra fila.

    tipo = fields.Selection([('celular', 'Celular'), ('correo', 'Correo'), ('ruc', 'RUC o cédula')], readonly=True)
    valor = fields.Char('Dato repetido', readonly=True)
    cantidad = fields.Integer('Fichas', readonly=True)
    nombres = fields.Char('Quiénes son', readonly=True)
    ids_fichas = fields.Char('Ids de las fichas', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT ('x' || substr(md5(tipo || '|' || valor), 1, 13))::bit(52)::bigint AS id, tipo, valor,
                       count(*) AS cantidad,
                       string_agg(nombre, ' · ' ORDER BY ficha) AS nombres,
                       string_agg(ficha::text, ',' ORDER BY ficha) AS ids_fichas
                FROM (
                    SELECT DISTINCT 'celular' AS tipo, p.dcasa_telefono_llave AS valor, p.id AS ficha, p.name AS nombre
                      FROM res_partner p WHERE {FICHA} AND p.dcasa_telefono_llave IS NOT NULL
                    UNION
                    SELECT 'celular', 'pa:' || p.dcasa_celular, p.id, p.name
                      FROM res_partner p WHERE {FICHA} AND p.dcasa_celular IS NOT NULL
                    UNION
                    SELECT 'correo', p.email_normalized, p.id, p.name
                      FROM res_partner p WHERE {FICHA} AND p.email_normalized IS NOT NULL
                    UNION
                    SELECT 'ruc', p.dcasa_vat_llave, p.id, p.name
                      FROM res_partner p WHERE {FICHA} AND p.dcasa_vat_llave IS NOT NULL
                ) t
                GROUP BY tipo, valor
                HAVING count(*) > 1
            )""")

    def _fichas(self):
        self.ensure_one()
        self.env['res.partner'].flush_model(self._depends['res.partner'])
        if not self.exists():  # alguien ya arregló ese dato: la fila (su id sale del dato) desapareció
            raise UserError(self.env._('Ya no quedan dos fichas con ese dato: actualiza la lista.'))
        return self.env['res.partner'].browse([int(i) for i in (self.ids_fichas or '').split(',') if i]).exists()

    def action_ver(self):
        """Abre las fichas que comparten ese dato."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'res.partner', 'view_mode': 'list,form',
            'name': self.env._('Fichas con el mismo dato'),
            'domain': [('id', 'in', self._fichas().ids)], 'context': {'active_test': False},
        }

    def action_fusionar(self):
        """Abre el asistente de fusión de Odoo con esas fichas (hasta 3 a la vez; la ficha de más movimiento queda)."""
        self.ensure_one()
        fichas = self._fichas()
        if len(fichas) < 2:
            raise UserError(self.env._('Ya no quedan dos fichas con ese dato: actualiza la lista.'))
        if len(fichas) > 3:
            raise UserError(self.env._(
                'Son %s fichas: Odoo fusiona hasta 3 a la vez. Ábrelas con «Ver las fichas», elige 3 y usa '
                'Acción › Fusionar; repite para el resto.', len(fichas)))
        accion = self.env['ir.actions.actions']._for_xml_id('base.action_partner_merge')
        accion['context'] = {'active_model': 'res.partner', 'active_ids': fichas.ids, 'active_id': fichas[0].id}
        return accion
