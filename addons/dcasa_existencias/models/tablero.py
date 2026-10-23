"""El Inicio de Gerencia avisa cuando las mermas del mes pasan del tope (F6: 0.5 % de lo comprado)."""
from odoo import fields, models

from .bitacora import GRUPO_AJUSTA


class DcasaTablero(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    def _atencion(self, datos, hoy):
        resultado = super()._atencion(datos, hoy)
        if not self.env.user.has_group(GRUPO_AJUSTA):
            return resultado
        resumen = self.env['stock.scrap']._dcasa_resumen_mes(self.env.company, hoy or fields.Date.context_today(self))
        if resumen['pasa']:
            datos['atencion'].append({
                'clave': 'mermas_tope', 'icono': 'fa-exclamation-triangle', 'cuenta': resumen['cantidad'],
                'texto': self.env._('Las mermas del mes (%(total)s) pasan del %(tope)s %% de lo comprado',
                                    total=f'${resumen["total"]:,.2f}', tope=f'{resumen["tope"]:g}'),
                'accion': {'name': self.env._('Mermas del mes'), 'res_model': 'stock.scrap',
                           'domain': self.env['stock.scrap']._dcasa_dominio_mes(self.env.company, resumen['mes']),
                           'vista': 'list', 'vista_lista': self.env.ref('dcasa_existencias.merma_list').id},
            })
        return resultado
