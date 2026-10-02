"""Herramientas para importar productos desde el Excel de un proveedor (ver ``importacion.py``).

* ``proponer_importacion`` (construcción, vendedoras y Gerencia): solo deja un borrador con la
  vista previa; no toca productos.
* ``aplicar_importacion`` y ``deshacer_importacion`` (sensibles, solo Gerencia): la persona
  confirma con un clic viendo los conteos y los cambios de precio grandes. Desde MCP nunca se
  ejecutan (regla de las sensibles).
"""
from odoo import api, models

from .registro import BrianError, herramienta

VENDEDORA = ('sales_team.group_sale_salesman',)
GERENCIA = ('dcasa_base.group_gerencia',)
MODELOS_ADJUNTOS = ('brian.conversacion', 'brian.mensaje')
PARAM_IMPORTACION = {'type': 'integer', 'description': 'El número de la importación que dio proponer_importacion.'}


class BrianHerramientasImportacion(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_adjunto(self, texto):
        """El Excel que la persona le mandó a Brian: por id o por nombre (el más reciente)."""
        Adjunto = self.env['ir.attachment'].sudo()
        conversaciones = self.env['brian.conversacion'].search([('usuario_id', '=', self.env.uid)])
        dominio = [('res_model', 'in', MODELOS_ADJUNTOS), '|', ('create_uid', '=', self.env.uid),
                   '&', ('res_model', '=', 'brian.conversacion'), ('res_id', 'in', conversaciones.ids)]
        texto = str(texto or '').strip()
        if texto.isdigit():
            adjunto = Adjunto.search([('id', '=', int(texto))] + dominio, limit=1)
        else:
            adjunto = Adjunto.search([('name', '=ilike', texto)] + dominio, order='id desc', limit=1) or \
                Adjunto.search([('name', 'ilike', texto)] + dominio, order='id desc', limit=1)
        if not adjunto:
            raise BrianError(f'No encuentro el archivo «{texto}» entre los que me mandaste. Adjúntalo en el chat '
                             '(o en Telegram) y dime su nombre.')
        return adjunto

    @api.model
    def _b_importacion(self, importacion_id):
        importacion = self.env['brian.importacion'].browse(int(importacion_id or 0)).exists()
        if not importacion or not importacion.has_access('read'):
            raise BrianError(f'No encuentro la importación #{importacion_id}.')
        return importacion

    @herramienta(
        nombre='proponer_importacion',
        descripcion='Lee el Excel de productos de un proveedor (con sus fotos incrustadas) y prepara una vista '
                    'previa: qué productos se crean, cuáles cambian de precio y cuáles se omiten. No cambia '
                    'nada: para aplicarla, Gerencia usa aplicar_importacion.',
        parametros={
            'adjunto': {'type': 'string', 'description': 'Nombre o número del Excel que te mandaron, '
                                                         'p. ej. «Catalogo_LTSC-07.xlsx».'},
            'hoja': {'type': 'string', 'description': 'Hoja del Excel. Opcional: por defecto la de los productos.'},
            'columna_precio': {'type': 'string', 'description': 'Columna con el precio de venta, por letra o '
                                                                'encabezado, p. ej. «E» o «Precio cama sola». '
                                                                'Opcional: por defecto la primera que dice «precio».'},
            'modo_itbms': {'type': 'string', 'enum': ['mas_itbms', 'incluido'],
                           'description': 'mas_itbms (D\'CASA, por defecto): el precio del Excel es sin ITBMS y va '
                                          'tal cual. incluido: el precio ya trae el ITBMS y se le quita.'},
        },
        requeridos=['adjunto'],
        nivel='construccion', categoria='catalogo', grupos=VENDEDORA,
        ejemplos=['carga los productos de este Excel → adjunto=«Catalogo_LTSC-07.xlsx»',
                  'usa el precio de la columna E → columna_precio=E'],
    )
    def _h_proponer_importacion(self, adjunto, hoja=None, columna_precio=None, modo_itbms='mas_itbms'):
        archivo = self._b_adjunto(adjunto)
        importacion = self.env['brian.importacion']._proponer(
            archivo, hoja=hoja, columna_precio=columna_precio, modo_itbms=modo_itbms or 'mas_itbms')
        datos = importacion._vista_previa()
        conteo = datos['conteo']
        datos['mensaje'] = (f'Vista previa lista (importación #{importacion.id}): crear {conteo["crear"]}, '
                            f'actualizar {conteo["actualizar"]}, omitir {conteo["omitir"]}. No he cambiado nada.')
        datos['siguiente'] = ('Revisa los avisos con la persona. Para aplicarla: aplicar_importacion con '
                              f'importacion_id={importacion.id} (lo confirma Gerencia).')
        datos['abrir'] = {'modelo': 'brian.importacion', 'res_id': importacion.id, 'titulo': importacion.name}
        return datos

    @herramienta(
        nombre='aplicar_importacion',
        descripcion='Aplica una importación de productos ya revisada: crea los productos nuevos (sin publicar en '
                    'la web) y actualiza los precios. Pide confirmación.',
        parametros={'importacion_id': PARAM_IMPORTACION},
        requeridos=['importacion_id'],
        nivel='sensible', categoria='catalogo', grupos=GERENCIA,
        ejemplos=['sí, aplica la importación 3 → importacion_id=3'],
    )
    def _h_aplicar_importacion(self, importacion_id):
        importacion = self._b_importacion(importacion_id)
        importacion._aplicar()
        lineas = importacion.linea_ids
        hechas = lineas.filtered(lambda li: li.estado == 'hecha')
        errores = lineas.filtered(lambda li: li.estado == 'error')
        productos = hechas.mapped('product_tmpl_id')
        return {
            'mensaje': f'{importacion.name} aplicada: {len(hechas.filtered(lambda li: li.accion == "crear"))} '
                       f'producto(s) creados (sin publicar) y '
                       f'{len(hechas.filtered(lambda li: li.accion == "actualizar"))} actualizados.',
            'errores': [{'fila': li.fila, 'codigo': li.codigo, 'error': li.error} for li in errores[:20]],
            'siguiente': 'Para publicarlos en la web: publicar_producto_web. Para revertir: deshacer_importacion.',
            'abrir': {'modelo': 'product.template', 'dominio': [['id', 'in', productos.ids]],
                      'titulo': 'Productos importados'},
        }

    @herramienta(
        nombre='deshacer_importacion',
        descripcion='Revierte una importación aplicada: borra los productos que creó si nadie los usó (si no, los '
                    'archiva) y devuelve los precios anteriores si nadie los cambió después. Pide confirmación.',
        parametros={'importacion_id': PARAM_IMPORTACION,
                    'motivo': {'type': 'string', 'description': 'Por qué se deshace, p. ej. «precios equivocados».'}},
        requeridos=['importacion_id', 'motivo'],
        nivel='sensible', categoria='catalogo', grupos=GERENCIA,
        ejemplos=['deshaz la importación 3, los precios venían mal → importacion_id=3, motivo=precios equivocados'],
    )
    def _h_deshacer_importacion(self, importacion_id, motivo):
        importacion = self._b_importacion(importacion_id)
        importacion._deshacer((motivo or '').strip()[:200])
        lineas = importacion.linea_ids
        conteo = {estado: len(lineas.filtered(lambda li, e=estado: li.estado == e))
                  for estado in ('borrado', 'archivado', 'deshecha', 'conservada')}
        conservadas = lineas.filtered(lambda li: li.estado == 'conservada')
        return {
            'mensaje': f'{importacion.name} deshecha: {conteo["borrado"]} producto(s) borrados, '
                       f'{conteo["archivado"]} archivados (ya tenían movimientos o estaban publicados), '
                       f'{conteo["deshecha"]} vueltos a su valor anterior.',
            'conservados': [{'codigo': li.codigo, 'nota': li.error} for li in conservadas[:20]],
        }


class BrianPoliticaImportacion(models.AbstractModel):
    _inherit = 'brian.politica'

    @api.model
    def _importacion(self, argumentos):
        return self.env['brian.herramientas']._b_importacion(argumentos.get('importacion_id'))

    @api.model
    def _verificar_aplicar_importacion(self, argumentos):
        importacion = self._importacion(argumentos)
        if importacion.estado != 'borrador':
            raise BrianError(f'{importacion.name} ya no está en borrador: no se aplica otra vez.')

    @api.model
    def _verificar_deshacer_importacion(self, argumentos):
        importacion = self._importacion(argumentos)
        if importacion.estado != 'aplicada':
            raise BrianError(f'{importacion.name} no está aplicada: no hay nada que deshacer.')

    @api.model
    def _resumir_aplicar_importacion(self, argumentos):
        return self._importacion(argumentos)._texto_confirmacion()

    @api.model
    def _resumir_deshacer_importacion(self, argumentos):
        importacion = self._importacion(argumentos)
        conteo = importacion._conteos()
        return (f'Deshacer {importacion.name}: los {conteo["crear"]} productos creados se borran si nadie los '
                f'usó (si no, se archivan) y los {conteo["actualizar"]} actualizados vuelven a su valor anterior '
                f'si nadie los cambió después.\n• Motivo: {argumentos.get("motivo") or "—"}')
