"""Importación de productos desde el Excel de un proveedor: vista previa, aplicar y deshacer.

Flujo (herramientas en ``herramientas_importacion.py``):

1. ``proponer_importacion`` lee el Excel (``lector_importacion``) y deja un BORRADOR
   ``brian.importacion`` con una línea por fila: crear / actualizar / omitir, con el antes y
   el después y la foto incrustada de esa fila. No toca ningún producto.
2. ``aplicar_importacion`` (sensible, solo Gerencia) crea y actualiza los productos COMO EL
   USUARIO, línea por línea con savepoint: una línea con error no tumba las demás.
3. ``deshacer_importacion`` (sensible, solo Gerencia): lo creado se borra si nadie lo usó (ni
   ventas, ni inventario, ni facturas, ni está publicado) y si no, se archiva; lo
   actualizado vuelve a su valor anterior solo si nadie lo cambió después.

Reglas:

* Se empareja por código (``default_code``) exacto, sin espacios y sin distinguir mayúsculas.
* Al actualizar solo cambia el precio; medidas y foto se llenan si el producto no tenía. El
  nombre, la categoría, la publicación y todo lo demás no se tocan.
* Precio: ``modo_itbms='mas_itbms'`` (D'CASA, decisión de la dueña 2026-10-01) copia el precio
  del Excel tal cual: es sin ITBMS y el 7 % se suma. ``'incluido'`` lo divide entre 1 + tasa.
* Los productos nuevos nacen SIN publicar en la web (como ``crear_producto``): se publican
  después con ``publicar_producto_web``.
* El registro no lo edita nadie por RPC (ACL solo lectura): lo escribe el sistema con sudo,
  después de comprobar los permisos del usuario. Los productos se escriben sin sudo.
"""
import base64
import hashlib
import json

from odoo import api, fields, models
from odoo.addons.dcasa_base import itbms_de_venta
from odoo.addons.dcasa_catalogo.catalogo import valores_producto_nuevo
from odoo.addons.dcasa_catalogo.reglas import TAMANOS, categoria_de_nombre, tamano_del_nombre
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

from . import lector_importacion as lector
from .registro import BrianError

MODOS_ITBMS = [
    ('mas_itbms', 'Precio + ITBMS (el precio del Excel va tal cual; el 7 % se suma)'),
    ('incluido', 'El precio del Excel ya incluye el ITBMS (se divide entre 1 + tasa)'),
]
ESTADOS = [('borrador', 'Borrador'), ('aplicada', 'Aplicada'), ('deshecha', 'Deshecha')]
ACCIONES = [('crear', 'Crear'), ('actualizar', 'Actualizar'), ('omitir', 'Omitir')]
ESTADOS_LINEA = [
    ('pendiente', 'Pendiente'), ('hecha', 'Hecha'), ('error', 'Error'),
    ('deshecha', 'Deshecha'), ('borrado', 'Producto borrado'), ('archivado', 'Producto archivado'),
    ('conservada', 'Conservada (cambió después)'),
]
CAMBIO_GRANDE = 0.30
MAX_AVISOS = 25
# Dónde se usa un producto: si aparece en alguno, deshacer lo archiva en vez de borrarlo.
MODELOS_USO = ('sale.order.line', 'stock.move', 'account.move.line', 'purchase.order.line',
               'stock.quant')


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, default=str)


def _cargar(texto, defecto):
    try:
        return json.loads(texto) if texto else defecto
    except ValueError:
        return defecto


def _huella(imagen_b64):
    if not imagen_b64:
        return None
    crudo = base64.b64decode(imagen_b64) if isinstance(imagen_b64, (bytes, str)) else b''
    return hashlib.sha1(crudo).hexdigest()


def _moneda(monto):
    return f'${monto:,.2f}' if monto is not None else '—'


def _medidas(valor, encabezado):
    """«228 × 223 × 120 cm» con la etiqueta del encabezado («L × A × Alto: …»). Sin números → None."""
    texto = lector.texto_celda(valor)
    if not texto or not any(c.isdigit() for c in texto):
        return None
    etiqueta = ''
    if '(' in (encabezado or '') and ')' in encabezado:
        etiqueta = encabezado[encabezado.index('(') + 1:encabezado.rindex(')')].strip()
    return f'{etiqueta}: {texto}' if etiqueta else texto


def _tamano(valor, nombre):
    texto = lector.texto_celda(valor).capitalize()
    return texto if texto in TAMANOS else tamano_del_nombre(nombre)


class BrianImportacion(models.Model):
    _name = 'brian.importacion'
    _description = 'Importación de productos desde Excel (Brian)'
    _order = 'id desc'

    name = fields.Char('Importación', compute='_compute_name', store=True)
    archivo = fields.Char(readonly=True)
    adjunto_id = fields.Many2one('ir.attachment', 'Adjunto', readonly=True, ondelete='set null')
    sha256 = fields.Char('Huella del archivo', readonly=True)
    hoja = fields.Char(readonly=True)
    fila_encabezado = fields.Integer('Fila del encabezado', readonly=True)
    mapeo = fields.Text('Columnas (JSON)', readonly=True)
    modo_itbms = fields.Selection(MODOS_ITBMS, 'Precios del Excel', required=True, default='mas_itbms',
                                  readonly=True)
    tasa_itbms = fields.Float('Tasa ITBMS (%)', readonly=True)
    estado = fields.Selection(ESTADOS, default='borrador', required=True, readonly=True, index=True)
    avisos = fields.Text(readonly=True)
    fotos_en_hoja = fields.Integer('Fotos en la hoja', readonly=True)
    linea_ids = fields.One2many('brian.importacion.linea', 'importacion_id', 'Líneas', readonly=True)
    usuario_id = fields.Many2one('res.users', related='create_uid', string='Propuesta por', store=True)
    aplicada_por = fields.Many2one('res.users', readonly=True)
    fecha_aplicada = fields.Datetime(readonly=True)
    deshecha_por = fields.Many2one('res.users', readonly=True)
    fecha_deshecha = fields.Datetime(readonly=True)
    motivo_deshacer = fields.Char(readonly=True)
    n_crear = fields.Integer('Crear', compute='_compute_conteos')
    n_actualizar = fields.Integer('Actualizar', compute='_compute_conteos')
    n_omitir = fields.Integer('Omitir', compute='_compute_conteos')

    @api.depends('archivo')
    def _compute_name(self):
        for imp in self:
            imp.name = f'Importación #{imp.id or "?"} · {imp.archivo or ""}'.strip(' ·')

    @api.depends('linea_ids.accion')
    def _compute_conteos(self):
        for imp in self:
            acciones = imp.linea_ids.mapped('accion')
            imp.n_crear = acciones.count('crear')
            imp.n_actualizar = acciones.count('actualizar')
            imp.n_omitir = acciones.count('omitir')

    # ------------------------------------------------------------------
    # 1. Proponer (borrador)
    # ------------------------------------------------------------------

    @api.model
    def _proponer(self, adjunto, hoja=None, columna_precio=None, modo_itbms='mas_itbms'):
        """Crea el borrador a partir de un ``ir.attachment`` ya validado por quien llama."""
        if modo_itbms not in dict(MODOS_ITBMS):
            raise BrianError('modo_itbms debe ser «mas_itbms» (precio sin ITBMS, el de D\'CASA) o «incluido».')
        crudo = adjunto.sudo().raw or b''
        try:
            tabla = lector.leer_tabla(crudo, hoja=hoja, columna_precio=columna_precio)
        except lector.ErrorImportacion as error:
            raise BrianError(str(error)) from error
        columnas = tabla['columnas']
        if 'precio' not in columnas:
            raise BrianError('No encontré una columna de precio. Dime cuál es con columna_precio '
                             f'(letra o encabezado). Encabezados: {self._encabezados(tabla)}.')
        if 'nombre' not in columnas:
            raise BrianError('No encontré la columna de descripción o nombre del producto. Encabezados: '
                             f'{self._encabezados(tabla)}.')
        impuesto = itbms_de_venta(self.env, self.env.company)
        tasa = impuesto.amount if impuesto and impuesto.amount_type == 'percent' else 7.0
        avisos = list(tabla['avisos'])
        encabezado_precio = columnas['precio']['encabezado']
        norma_precio = lector.normalizar(encabezado_precio)
        if modo_itbms == 'mas_itbms' and 'itbms' in norma_precio and 'sin' not in norma_precio.split():
            avisos.insert(0, f'La columna de precio «{encabezado_precio}» menciona el ITBMS: si ya lo '
                             'incluye, propón de nuevo con modo_itbms «incluido».')
        otras = [c for c in tabla['columnas_precio'] if c['columna'] != columnas['precio']['columna']]
        if otras:
            avisos.append('Usé el precio de la columna {} «{}». Otras columnas de precio: {}.'.format(
                columnas['precio']['columna'], encabezado_precio,
                ', '.join(f'{c["columna"]} «{c["encabezado"]}»' for c in otras)))
        lineas, avisos_lineas = self._lineas(tabla, modo_itbms, tasa)
        importacion = self.sudo().create({
            'archivo': adjunto.name,
            'adjunto_id': adjunto.id,
            'sha256': hashlib.sha256(crudo).hexdigest(),
            'hoja': tabla['hoja'],
            'fila_encabezado': tabla['fila_encabezado'],
            'mapeo': _json({'columnas': columnas, 'columnas_precio': tabla['columnas_precio'],
                            'hojas': tabla['hojas']}),
            'modo_itbms': modo_itbms,
            'tasa_itbms': tasa,
            'avisos': _json(avisos + avisos_lineas),
            'fotos_en_hoja': tabla['fotos_en_hoja'],
            'linea_ids': [(0, 0, linea) for linea in lineas],
        })
        return importacion.sudo(False)

    @api.model
    def _encabezados(self, tabla):
        return ', '.join(f'{col} «{texto}»' for col, texto in tabla['encabezados'].items())

    @api.model
    def _existentes(self, codigo):
        """Productos (también archivados) cuyo código es ``codigo`` sin espacios ni mayúsculas."""
        clave = codigo.strip().lower()
        escapado = codigo.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        candidatos = self.env['product.product'].with_context(active_test=False).search(
            [('default_code', 'ilike', escapado)])
        return candidatos.filtered(lambda p: (p.default_code or '').strip().lower() == clave)

    @api.model
    def _lineas(self, tabla, modo_itbms, tasa):
        """(valores de cada línea, avisos). Decide crear / actualizar / omitir sin escribir nada."""
        repetidos = {}
        for fila in tabla['filas']:
            codigo = lector.texto_celda(fila['valores'].get('codigo'))
            if codigo:
                repetidos.setdefault(codigo.lower(), []).append((fila['fila'], codigo))
        avisos = []
        lineas = [self._linea(tabla, fila, repetidos, modo_itbms, tasa, avisos) for fila in tabla['filas']]
        duplicados = [filas for filas in repetidos.values() if len(filas) > 1]
        if duplicados:
            avisos.insert(0, 'Códigos repetidos (no se importan hasta que los corrijas): ' + '; '.join(
                f'{filas[0][1]} en filas {", ".join(str(f) for f, _c in filas)}' for filas in duplicados))
        sin_foto = [str(li['fila']) for li in lineas if li['accion'] == 'crear' and not li.get('imagen')]
        if sin_foto:
            avisos.append(f'{len(sin_foto)} producto(s) nuevos sin foto en el Excel (filas {", ".join(sin_foto)}).')
        sin_precio = [str(li['fila']) for li in lineas if li.get('motivo', '').startswith('Sin precio')]
        if sin_precio:
            avisos.append(f'Sin precio, no se importan: filas {", ".join(sin_precio)}.')
        avisos += [f'Fila {li["fila"]} ({li["codigo"]}): {li["avisos"]}.' for li in lineas if li.get('avisos')]
        return lineas, avisos

    @api.model
    def _linea(self, tabla, fila, repetidos, modo_itbms, tasa, avisos):
        numero, valores = fila['fila'], fila['valores']
        encabezado_medidas = tabla['columnas'].get('medidas', {}).get('encabezado', '')
        codigo = lector.texto_celda(valores.get('codigo'))
        nombre = lector.texto_celda(valores.get('nombre'))
        precio_excel = lector.precio_de(valores.get('precio'))
        linea = {
            'fila': numero, 'codigo': codigo, 'nombre': nombre, 'precio_excel': precio_excel or 0.0,
            'medidas': _medidas(valores.get('medidas'), encabezado_medidas),
            'tamano': _tamano(valores.get('tamano'), nombre),
            'categoria': categoria_de_nombre(lector.texto_celda(valores.get('categoria')) or nombre),
            'accion': 'omitir', 'estado': 'pendiente',
        }
        foto = tabla['fotos'].get(numero)
        if foto:
            try:
                linea['imagen'] = base64.b64encode(lector.foto_normalizada(foto))
            except (ValueError, UserError):
                avisos.append(f'Fila {numero}: la foto no se pudo abrir (formato raro); va sin foto.')
        if not codigo:
            linea['motivo'] = 'Sin código'
        elif len(repetidos.get(codigo.lower(), [])) > 1:
            linea['motivo'] = 'Código repetido en las filas ' + ', '.join(
                str(f) for f, _c in repetidos[codigo.lower()])
        elif precio_excel is None:
            linea['motivo'] = ('Sin precio: la celda es una fórmula sin valor guardado (abre y guarda el '
                               'archivo en Excel)' if numero in tabla['formulas_sin_valor'] else 'Sin precio')
        elif precio_excel <= 0:
            linea['motivo'] = 'Precio cero o negativo'
        else:
            precio = precio_excel if modo_itbms == 'mas_itbms' else round(precio_excel / (1 + tasa / 100), 2)
            linea['precio'] = precio
            self._decidir(linea, codigo, nombre, precio)
        return linea

    @api.model
    def _decidir(self, linea, codigo, nombre, precio):
        existentes = self._existentes(codigo)
        if len(existentes) > 1:
            linea['motivo'] = f'Hay {len(existentes)} productos con ese código en Odoo: corrígelo a mano'
            return
        if not existentes:
            if not nombre:
                linea['motivo'] = 'Sin descripción'
                return
            linea.update(accion='crear', despues=_json(self._despues_crear(linea)))
            return
        variante = existentes
        plantilla = variante.product_tmpl_id
        linea['product_tmpl_id'] = plantilla.id
        if not variante.active or not plantilla.active:
            linea['motivo'] = f'Existe archivado («{plantilla.display_name}»): reactívalo o cambia el código'
            return
        if plantilla.product_variant_count > 1:
            linea['motivo'] = (f'Es un tamaño de «{plantilla.display_name}», que tiene varios: '
                               'el precio por tamaño se cambia a mano')
            return
        antes, despues = self._cambios(plantilla, precio, linea.get('medidas'), linea.get('imagen'))
        if not despues:
            linea['motivo'] = 'Sin cambios'
            return
        linea.update(accion='actualizar', antes=_json(antes), despues=_json(despues))
        if 'list_price' in despues and antes['list_price'] > 0:
            cambio = (despues['list_price'] - antes['list_price']) / antes['list_price']
            if abs(cambio) > CAMBIO_GRANDE:
                linea['avisos'] = (f'el precio cambia {cambio:+.0%} '
                                   f'({_moneda(antes["list_price"])} → {_moneda(despues["list_price"])})')

    @api.model
    def _despues_crear(self, linea):
        despues = {'default_code': linea['codigo'], 'name': linea['nombre'], 'list_price': linea['precio']}
        if linea.get('medidas'):
            despues['dcasa_medidas'] = linea['medidas']
        return despues

    @api.model
    def _cambios(self, plantilla, precio, medidas, imagen):
        """(antes, después) solo de lo que la importación cambiaría en un producto existente."""
        antes, despues = {}, {}
        if float_compare(plantilla.list_price, precio, precision_digits=2):
            antes['list_price'], despues['list_price'] = plantilla.list_price, precio
        if medidas and not plantilla.dcasa_medidas:
            antes['dcasa_medidas'], despues['dcasa_medidas'] = False, medidas
        if imagen and not plantilla.image_1920:
            antes['image_1920'], despues['image_1920'] = None, 'foto del Excel'
        return antes, despues

    # ------------------------------------------------------------------
    # 2. Aplicar
    # ------------------------------------------------------------------

    def _aplicar(self):
        self.ensure_one()
        if self.estado != 'borrador':
            raise BrianError(f'{self.name} ya está {dict(ESTADOS)[self.estado].lower()}: no se aplica otra vez.')
        Template = self.env['product.template']
        if not (Template.has_access('create') and Template.has_access('write')):
            raise BrianError('No tienes permiso para crear o cambiar productos.')
        impuesto = itbms_de_venta(self.env, self.env.company)
        for linea in self.linea_ids.filtered(lambda li: li.accion in ('crear', 'actualizar')).sorted('fila'):
            try:
                with self.env.cr.savepoint():
                    linea._aplicar(impuesto)
            except (BrianError, UserError, ValidationError, AccessError) as error:
                mensaje = error.args[0] if error.args else str(error)
                linea.sudo().write({'estado': 'error', 'error': mensaje})
        self.sudo().write({'estado': 'aplicada', 'aplicada_por': self.env.uid,
                           'fecha_aplicada': fields.Datetime.now()})
        return True

    # ------------------------------------------------------------------
    # 3. Deshacer
    # ------------------------------------------------------------------

    def _deshacer(self, motivo):
        self.ensure_one()
        if self.estado != 'aplicada':
            raise BrianError(f'{self.name} está {dict(ESTADOS)[self.estado].lower()}: solo se deshace una '
                             'importación aplicada.')
        for linea in self.linea_ids.filtered(lambda li: li.estado == 'hecha').sorted('fila'):
            try:
                with self.env.cr.savepoint():
                    linea._deshacer()
            except (BrianError, UserError, ValidationError, AccessError) as error:
                mensaje = error.args[0] if error.args else str(error)
                linea.sudo().write({'error': f'No se pudo deshacer: {mensaje}'})
        self.sudo().write({'estado': 'deshecha', 'deshecha_por': self.env.uid,
                           'fecha_deshecha': fields.Datetime.now(), 'motivo_deshacer': motivo})
        return True

    # ------------------------------------------------------------------
    # Vista previa y resúmenes (para Brian y la tarjeta de confirmación)
    # ------------------------------------------------------------------

    def _conteos(self):
        self.ensure_one()
        return {'crear': self.n_crear, 'actualizar': self.n_actualizar, 'omitir': self.n_omitir}

    def _avisos(self):
        avisos = _cargar(self.avisos, [])
        if len(avisos) > MAX_AVISOS:
            avisos = avisos[:MAX_AVISOS] + [f'… y {len(avisos) - MAX_AVISOS} avisos más.']
        return avisos

    def _vista_previa(self, max_lineas=15):
        self.ensure_one()
        columnas = _cargar(self.mapeo, {}).get('columnas', {})
        lineas = self.linea_ids.sorted('fila')
        con_foto = len(lineas.filtered('imagen'))
        # Primero lo que cambia, después lo omitido.
        orden = lineas.filtered(lambda li: li.accion != 'omitir') + lineas.filtered(lambda li: li.accion == 'omitir')
        return {
            'importacion_id': self.id,
            'archivo': self.archivo,
            'hoja': self.hoja,
            'encabezado_en_fila': self.fila_encabezado,
            'columnas': {rol: f'{c["columna"]} «{c["encabezado"]}»' for rol, c in columnas.items()},
            'precios': dict(MODOS_ITBMS)[self.modo_itbms],
            'conteo': self._conteos(),
            'fotos': {'en_la_hoja': self.fotos_en_hoja, 'asignadas_a_un_producto': con_foto},
            'avisos': self._avisos(),
            'lineas': [li._resumen() for li in orden[:max_lineas]],
            'lineas_no_mostradas': max(len(orden) - max_lineas, 0),
            'estado': dict(ESTADOS)[self.estado],
        }

    def _texto_confirmacion(self):
        self.ensure_one()
        conteo = self._conteos()
        lineas = [
            f'Aplicar {self.name} (hoja «{self.hoja}»):',
            f'• Crear {conteo["crear"]} producto(s) sin publicar en la web, actualizar {conteo["actualizar"]}, '
            f'omitir {conteo["omitir"]}.',
            f'• Precios: {dict(MODOS_ITBMS)[self.modo_itbms]}.',
        ]
        grandes = self.linea_ids.filtered(lambda li: li.avisos)
        if grandes:
            lineas.append(f'• ⚠ {len(grandes)} precio(s) cambian más de {CAMBIO_GRANDE:.0%}: ' + '; '.join(
                f'{li.codigo} {li.avisos}' for li in grandes[:5]) + ('…' if len(grandes) > 5 else ''))
        return '\n'.join(lineas)


class BrianImportacionLinea(models.Model):
    _name = 'brian.importacion.linea'
    _description = 'Línea de una importación de productos'
    _order = 'importacion_id desc, fila'

    importacion_id = fields.Many2one('brian.importacion', required=True, ondelete='cascade', index=True,
                                     readonly=True)
    fila = fields.Integer(readonly=True)
    codigo = fields.Char(readonly=True)
    nombre = fields.Char(readonly=True)
    precio_excel = fields.Float('Precio en el Excel', digits=(16, 2), readonly=True)
    precio = fields.Float('Precio de venta (sin ITBMS)', digits=(16, 2), readonly=True)
    medidas = fields.Char(readonly=True)
    tamano = fields.Char('Tamaño', readonly=True)
    categoria = fields.Char('Categoría (pista)', readonly=True)
    accion = fields.Selection(ACCIONES, required=True, default='omitir', readonly=True)
    motivo = fields.Char(readonly=True)
    avisos = fields.Char(readonly=True)
    product_tmpl_id = fields.Many2one('product.template', 'Producto', readonly=True, ondelete='set null')
    antes = fields.Text(readonly=True)
    despues = fields.Text('Después', readonly=True)
    estado = fields.Selection(ESTADOS_LINEA, default='pendiente', required=True, readonly=True)
    error = fields.Text(readonly=True)
    imagen = fields.Binary('Foto', attachment=True, readonly=True)

    def _resumen(self):
        self.ensure_one()
        fila = {'fila': self.fila, 'codigo': self.codigo or '', 'accion': self.accion,
                'nombre': self.nombre or '', 'foto': bool(self.imagen)}
        if self.accion == 'omitir':
            fila['motivo'] = self.motivo or ''
            return fila
        antes, despues = _cargar(self.antes, {}), _cargar(self.despues, {})
        if self.accion == 'crear':
            fila['precio'] = _moneda(self.precio)
        else:
            fila['producto'] = self.product_tmpl_id.display_name
            fila['cambios'] = {
                campo: (f'{_moneda(antes.get(campo))} → {_moneda(valor)}' if campo == 'list_price'
                        else f'{antes.get(campo) or "vacío"} → {valor}')
                for campo, valor in despues.items()}
        if self.medidas:
            fila['medidas'] = self.medidas
        if self.avisos:
            fila['aviso'] = self.avisos
        if self.estado not in ('pendiente', 'hecha'):
            fila['estado'] = dict(ESTADOS_LINEA)[self.estado]
        if self.error:
            fila['error'] = self.error
        return fila

    # ------------------------------------------------------------------
    # Aplicar / deshacer una línea (COMO EL USUARIO; el registro se escribe con sudo)
    # ------------------------------------------------------------------

    def _aplicar(self, impuesto):
        self.ensure_one()
        Importacion = self.env['brian.importacion']
        if self.accion == 'crear':
            if Importacion._existentes(self.codigo):
                raise BrianError(f'Ya existe un producto con el código {self.codigo} (se creó después de la '
                                 'vista previa): propón la importación de nuevo.')
            vals = valores_producto_nuevo(self.env, self.nombre, self.precio, impuesto, self.categoria,
                                          self.tamano)
            vals.update({'default_code': self.codigo, 'is_published': False})
            if self.medidas:
                vals['dcasa_medidas'] = self.medidas
            if self.imagen:
                vals['image_1920'] = self.imagen
            plantilla = self.env['product.template'].create(vals)
            despues = Importacion._despues_crear(
                {'codigo': self.codigo, 'nombre': self.nombre, 'precio': self.precio, 'medidas': self.medidas})
            if self.imagen:
                despues['image_1920'] = _huella(plantilla.image_1920)
            self.sudo().write({'product_tmpl_id': plantilla.id, 'estado': 'hecha', 'despues': _json(despues)})
            return
        plantilla = self.product_tmpl_id
        if not plantilla.exists() or not plantilla.active:
            raise BrianError(f'El producto del código {self.codigo} ya no existe o está archivado.')
        antes, despues = Importacion._cambios(plantilla, self.precio, self.medidas, self.imagen)
        if not despues:
            self.sudo().write({'estado': 'hecha', 'antes': _json({}), 'despues': _json({}),
                               'error': 'Ya estaba al día: no hubo nada que cambiar.'})
            return
        vals = {campo: valor for campo, valor in despues.items() if campo != 'image_1920'}
        if 'image_1920' in despues:
            vals['image_1920'] = self.imagen
        plantilla.write(vals)
        if 'image_1920' in despues:
            despues['image_1920'] = _huella(plantilla.image_1920)
        self.sudo().write({'estado': 'hecha', 'antes': _json(antes), 'despues': _json(despues)})

    def _deshacer(self):
        self.ensure_one()
        plantilla = self.product_tmpl_id.with_context(active_test=False).exists()
        if self.accion == 'crear':
            self._deshacer_creado(plantilla)
        elif not plantilla:
            self.sudo().write({'estado': 'conservada', 'error': 'El producto ya no existe.'})
        else:
            self._deshacer_actualizado(plantilla)

    def _deshacer_creado(self, plantilla):
        """Creado por la importación: se borra si nadie lo usó; si no, se archiva."""
        if not plantilla:
            self.sudo().write({'estado': 'deshecha', 'error': 'El producto ya no existía.'})
            return
        if plantilla.is_published or self._en_uso(plantilla):
            plantilla.action_archive()
            self.sudo().write({'estado': 'archivado',
                               'error': 'Tiene movimientos o está publicado: se archivó en vez de borrarlo.'})
            return
        try:
            with self.env.cr.savepoint():
                plantilla.unlink()
        except (UserError, ValidationError, AccessError):
            plantilla.action_archive()
            self.sudo().write({'estado': 'archivado', 'error': 'No se pudo borrar: se archivó.'})
            return
        self.sudo().write({'estado': 'borrado'})

    def _deshacer_actualizado(self, plantilla):
        """Vuelve cada campo a su valor anterior solo si sigue como lo dejó la importación."""
        antes, despues = _cargar(self.antes, {}), _cargar(self.despues, {})
        restaurar, conservados = {}, []
        for campo, valor in despues.items():
            if campo == 'list_price':
                igual = not float_compare(plantilla.list_price, valor, precision_digits=2)
            elif campo == 'image_1920':
                igual = _huella(plantilla.image_1920) == valor
            else:
                igual = (plantilla[campo] or False) == (valor or False)
            if igual:
                restaurar[campo] = antes.get(campo) or False
            else:
                conservados.append(campo)
        if restaurar:
            plantilla.write(restaurar)
        valores = {'estado': 'conservada' if conservados else 'deshecha'}
        if conservados:
            valores['error'] = 'Cambió después de importar; no lo toqué: ' + ', '.join(conservados)
        self.sudo().write(valores)

    def _en_uso(self, plantilla):
        variantes = plantilla.with_context(active_test=False).product_variant_ids
        for modelo in MODELOS_USO:
            if modelo in self.env and self.env[modelo].sudo().search_count(
                    [('product_id', 'in', variantes.ids)], limit=1):
                return True
        return False
