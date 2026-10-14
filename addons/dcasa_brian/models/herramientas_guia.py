"""Brian conoce la Guía del negocio (módulo dcasa_guia).

Quien administra no siempre sabe qué existe: «tengo que hacer la declaración de renta, ¿por dónde empiezo?». La Guía
(menú «Guía») es un catálogo de tareas en palabras sencillas, cada una con la pantalla a la que lleva y qué se logra
allí. Esta herramienta le da a Brian ese mismo catálogo para que responda con la ruta exacta del menú. Solo devuelve
lo que quien pregunta puede abrir (los mismos permisos del menú). Si el módulo no está instalado, lo dice.
"""
from odoo import api, models

from .registro import BrianError, herramienta


class BrianHerramientasGuia(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    @herramienta(
        nombre='buscar_en_guia',
        descripcion='Busca en la Guía del negocio qué pantalla sirve para lo que la persona quiere hacer '
                    '(declaración de renta, ITBMS, cerrar el mes, planilla, cobrar, conciliar el banco, crear un '
                    'producto…) y dice en qué parte del menú queda y qué se logra allí. Úsala cuando la persona no '
                    'sepa por dónde empezar.',
        parametros={'consulta': {'type': 'string', 'description': 'Lo que quiere hacer, con sus palabras.'}},
        requeridos=['consulta'],
        nivel='lectura',
        categoria='general',
        ejemplos=['¿por dónde empiezo para la declaración de renta?', '¿dónde cierro el mes?',
                  '¿cómo pago la planilla?', 'no sé qué hacer con el ITBMS', '¿dónde veo quién me debe?'],
    )
    def _h_buscar_en_guia(self, consulta):
        guia = self.env.get('dcasa.guia')
        if guia is None:
            raise BrianError('La Guía del negocio no está instalada en este sistema.')
        tareas = guia.buscar(consulta, limite=5)
        if not tareas:
            return {'resultados': [],
                    'nota': 'No encontré una tarea de la Guía para eso. Dile a la persona que abra el menú «Guía» y '
                            'escoja un tema, o pídele que te cuente más.'}
        resultados = []
        for tarea in tareas:
            destino = tarea['destino']
            resultado = {
                'tarea': tarea['titulo'],
                'que_lograras': tarea['logras'],
                'donde': destino['ruta'] if destino else 'No hay una pantalla: es una explicación.',
            }
            if tarea['pasos']:
                resultado['pasos'] = [paso['texto'] for paso in tarea['pasos']]
            if tarea['nota']:
                resultado['nota'] = tarea['nota']
            abrir = self._abrir_de_guia(destino, tarea['titulo'])
            if abrir:
                resultado['abrir'] = abrir
            resultados.append(resultado)
        return {'resultados': resultados,
                'nota': 'Las fechas límite de impuestos las confirma el contador; no las inventes.'}

    @api.model
    def _abrir_de_guia(self, destino, titulo):
        """El botón «abrir» de Brian para un menú de la Guía que abre la lista de un modelo (las pantallas a medida
        no tienen: Brian dice la ruta del menú)."""
        if not destino or destino['tipo'] != 'menu':
            return None
        accion = self.env['ir.ui.menu'].browse(destino['menu_id']).sudo().action
        if accion and accion._name == 'ir.actions.act_window' and accion.res_model:
            return {'modelo': accion.res_model, 'titulo': titulo}
        return None
