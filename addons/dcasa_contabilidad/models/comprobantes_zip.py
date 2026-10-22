"""Todos los comprobantes de un año fiscal (o de un rango) en un ZIP, ordenados por carpetas y con un índice (I6).

La DGI pide guardar los comprobantes 5 años: la gerencia decidió mandarlos todos en un ZIP de respaldo al cerrar el
año (DECISIONES_CONTABLES I6). Lo pide Gerencia o contabilidad; se prepara en segundo plano (puede tardar: cada
factura se vuelve PDF) y avisa cuando está listo.

Qué lleva (solo lo publicado, por fecha contable):

* ``01 Facturas de clientes``: el PDF de cada factura (el que se guardó al enviarla o, si no hay, se genera).
* ``02 Notas de credito``: el PDF de cada nota de crédito de cliente.
* ``03 Recibos de cobros y abonos``: el recibo de cada cobro de cliente.
* ``04 Compras``: los documentos que se adjuntaron a cada factura o nota de proveedor (la factura del proveedor).
* ``05 Pagos a proveedores``: lo adjuntado a cada pago a proveedores (la transferencia, el cheque).
* ``06 Gastos``: lo adjuntado a los asientos de gastos y las fotos de los recibos de los reembolsos de la nómina.
* ``INDICE.csv`` (se abre con Excel) con cada archivo, y ``LEEME.txt``.

Sin cargar todo en memoria: cada documento se lee (los adjuntos viven en R2, ``dcasa_adjuntos_r2``) o se genera de
uno en uno y se escribe al ZIP en el disco; el ZIP se parte en piezas de ``MAX_PARTE`` y cada pieza se guarda como
adjunto (en R2) en cuanto se llena. El trabajo avanza por tandas (cron) y, si el servidor se reinicia a media pieza,
esa pieza se rehace.
"""
import csv
import io
import json
import logging
import os
import re
import tempfile
import unicodedata
import zipfile
from datetime import date

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

MAX_PARTE = 40 * 1024 * 1024        # bytes por pieza del ZIP (lo que se lee de una vez al guardarla)
CAMPOS_EDITABLES = frozenset({'periodo', 'anio', 'desde', 'hasta', 'company_id'})
MODELOS = ('account.move', 'account.payment', 'dcasa.nomina.reembolso')
GRUPOS = ('account.group_account_user', 'dcasa_base.group_gerencia', 'base.group_system')
CARPETAS = {
    'factura': '01 Facturas de clientes',
    'nota': '02 Notas de credito',
    'cobro': '03 Recibos de cobros y abonos',
    'compra': '04 Compras',
    'pago': '05 Pagos a proveedores',
    'gasto': '06 Gastos',
}
TIPOS = {
    'factura': 'Factura de cliente', 'nota': 'Nota de crédito', 'cobro': 'Recibo de cobro o abono',
    'compra': 'Factura o nota de proveedor', 'pago': 'Pago a proveedor', 'gasto': 'Gasto',
}
LEEME = """COMPROBANTES DE D'CASA
=====================

Periodo: {periodo}
Preparado el {fecha} por {quien}.

La DGI pide guardar los comprobantes durante 5 años. Guarda este archivo (y sus partes, si tiene varias) en un lugar
seguro y con copia: un disco externo y la nube.

Carpetas:
  01 Facturas de clientes          el PDF de cada factura publicada
  02 Notas de credito              el PDF de cada nota de crédito de cliente
  03 Recibos de cobros y abonos    el recibo de cada cobro de cliente
  04 Compras                       los documentos adjuntos a cada factura o nota de proveedor
  05 Pagos a proveedores           lo adjuntado a cada pago a proveedores
  06 Gastos                        lo adjuntado a los asientos de gastos y los recibos de los reembolsos

INDICE.csv (se abre con Excel) dice qué hay en cada carpeta, de qué documento es y en qué parte del ZIP quedó; también
dice qué documento no tenía nada adjunto, para buscarlo en papel.
"""


def nombre_seguro(texto, largo=80):
    """Un nombre de archivo que abre en Windows, Mac y el celular: sin tildes raras, barras ni caracteres prohibidos."""
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    texto = re.sub(r'[^A-Za-z0-9._ -]+', '_', texto).strip(' ._')
    return (texto or 'documento')[:largo]


class DcasaComprobantesPaquete(models.Model):
    _name = 'dcasa.comprobantes.paquete'
    _description = 'ZIP de comprobantes (respaldo para la DGI)'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    periodo = fields.Selection([('anio', 'Un año fiscal'), ('rango', 'Un rango de fechas')], required=True,
                               default='anio')
    anio = fields.Integer('Año', default=lambda self: fields.Date.context_today(self).year - 1)
    desde = fields.Date('Desde')
    hasta = fields.Date('Hasta')
    estado = fields.Selection([('borrador', 'Por preparar'), ('preparando', 'Preparándose'), ('listo', 'Listo'),
                               ('error', 'No se pudo')], default='borrador', required=True, readonly=True,
                              tracking=True, copy=False)
    documentos = fields.Text(readonly=True, copy=False, help='Lo que falta meter al ZIP (uso interno).')
    total = fields.Integer('Documentos', readonly=True, copy=False)
    hechos = fields.Integer('Listos', readonly=True, copy=False)
    progreso = fields.Float('Avance (%)', compute='_compute_progreso')
    inicio_parte = fields.Integer(readonly=True, copy=False)
    parte = fields.Integer(readonly=True, copy=False, default=1)
    linea_ids = fields.One2many('dcasa.comprobantes.paquete.linea', 'paquete_id', 'Índice', readonly=True)
    adjunto_ids = fields.Many2many('ir.attachment', 'dcasa_comprobantes_paquete_adjunto_rel', 'paquete_id',
                                   'adjunto_id', 'Archivos ZIP', readonly=True, copy=False)
    resumen = fields.Text('Qué lleva', readonly=True, copy=False)
    error = fields.Text(readonly=True, copy=False)

    @api.depends('periodo', 'anio', 'desde', 'hasta')
    def _compute_name(self):
        for paquete in self:
            desde, hasta = paquete._limites()
            if paquete.periodo == 'anio' and paquete.anio:
                paquete.name = self.env._('Comprobantes del año %s', paquete.anio)
            elif desde and hasta:
                paquete.name = self.env._('Comprobantes del %(d)s al %(h)s', d=desde.strftime('%d/%m/%Y'),
                                          h=hasta.strftime('%d/%m/%Y'))
            else:
                paquete.name = self.env._('Comprobantes')

    @api.depends('total', 'hechos')
    def _compute_progreso(self):
        for paquete in self:
            paquete.progreso = round(100.0 * paquete.hechos / paquete.total, 1) if paquete.total else 0.0

    def _limites(self):
        self.ensure_one()
        if self.periodo == 'anio':
            if not self.anio:
                return False, False
            # I2: el año fiscal termina el 31 de diciembre.
            return date(self.anio, 1, 1), date(self.anio, 12, 31)
        return self.desde, self.hasta

    # ------------------------------------------------------------------
    # Quién y qué
    # ------------------------------------------------------------------

    def _exigir(self):
        if not self.env.su and not any(self.env.user.has_group(g) for g in GRUPOS):
            raise AccessError(self.env._('Los comprobantes los descarga Gerencia o contabilidad.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._exigir()
        if not self.env.su and any(set(vals) - CAMPOS_EDITABLES for vals in vals_list):
            raise AccessError(self.env._('Ese dato lo pone el sistema.'))
        return super().create(vals_list)

    def write(self, vals):
        # La lista de documentos, el avance y los archivos los escribe solo el sistema: si se pudieran escribir por
        # RPC, alguien metería en el ZIP documentos que no puede ver.
        if not self.env.su:
            self._exigir()
            if set(vals) - CAMPOS_EDITABLES - {'message_main_attachment_id'}:
                raise AccessError(self.env._('Ese dato lo pone el sistema.'))
            if any(p.estado == 'preparando' for p in self):
                raise UserError(self.env._('Se está preparando: espera a que termine para cambiar el periodo.'))
        return super().write(vals)

    def _documentos(self):
        """La lista ``[clave, modelo, id]`` de lo que va al ZIP, con los permisos de quien lo pide."""
        self.ensure_one()
        desde, hasta = self._limites()
        Move = self.env['account.move']
        base = [('company_id', '=', self.company_id.id), ('state', '=', 'posted'), ('date', '>=', desde),
                ('date', '<=', hasta)]
        filas = []
        orden = 'date, name, id'
        for clave, tipos in (('factura', ('out_invoice',)), ('nota', ('out_refund',)),
                             ('compra', ('in_invoice', 'in_refund', 'in_receipt'))):
            filas += [[clave, 'account.move', i] for i in Move.search(base + [('move_type', 'in', tipos)],
                                                                      order=orden).ids]
        Pago = self.env['account.payment']
        pagos = [('company_id', '=', self.company_id.id), ('state', 'in', ('in_process', 'paid')),
                 ('date', '>=', desde), ('date', '<=', hasta)]
        filas += [['cobro', 'account.payment', i] for i in Pago.search(
            pagos + [('payment_type', '=', 'inbound'), ('partner_type', '=', 'customer')], order='date, id').ids]
        salientes = Pago.search(pagos + [('payment_type', '=', 'outbound')], order='date, id')
        filas += [['pago', 'account.payment', i] for i in self._con_adjuntos(salientes).ids]
        asientos = Move.search(base + [('move_type', '=', 'entry')], order=orden)
        filas += [['gasto', 'account.move', i] for i in self._con_adjuntos(asientos).ids]
        Reembolso = self.env.get('dcasa.nomina.reembolso')
        if Reembolso is not None and Reembolso.has_access('read'):
            reembolsos = Reembolso.search([('company_id', '=', self.company_id.id), ('fecha', '>=', desde),
                                           ('fecha', '<=', hasta), ('recibo_ids', '!=', False),
                                           ('estado', 'in', ('aprobado', 'en_planilla', 'contabilizado'))],
                                          order='fecha, id')
            filas += [['gasto', 'dcasa.nomina.reembolso', i] for i in reembolsos.ids]
        return filas

    def _con_adjuntos(self, registros):
        if not registros:
            return registros
        con = self.env['ir.attachment'].sudo()._read_group(
            [('res_model', '=', registros._name), ('res_id', 'in', registros.ids)], ['res_id'])
        ids = {res_id for (res_id,) in con}
        return registros.filtered(lambda r: r.id in ids)

    def action_preparar(self):
        """Arma la lista de documentos y deja el ZIP preparándose en segundo plano."""
        self._exigir()
        for paquete in self:
            desde, hasta = paquete._limites()
            if not desde or not hasta or hasta < desde:
                raise UserError(self.env._('Elige el año o un rango de fechas válido.'))
            if paquete.estado == 'preparando':
                raise UserError(self.env._('Ya se está preparando: te avisamos cuando esté listo.'))
            documentos = paquete._documentos()
            if not documentos:
                raise UserError(self.env._('No hay comprobantes publicados en ese periodo.'))
            paquete.adjunto_ids.sudo().unlink()
            paquete.linea_ids.sudo().unlink()
            paquete.sudo().write({
                'documentos': json.dumps(documentos), 'total': len(documentos), 'hechos': 0, 'inicio_parte': 0,
                'parte': 1, 'estado': 'preparando', 'error': False, 'resumen': False})
            paquete._borrar_temporal()
            paquete.message_post(body=self.env._(
                '%(quien)s pidió el ZIP: %(n)s documentos. Se prepara en segundo plano; llega un aviso cuando esté.',
                quien=self.env.user.name, n=len(documentos)))
        cron = self.env.ref('dcasa_contabilidad.cron_comprobantes_zip', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return True

    # ------------------------------------------------------------------
    # El trabajo (por tandas)
    # ------------------------------------------------------------------

    def _ruta_temporal(self):
        self.ensure_one()
        carpeta = os.path.join(tempfile.gettempdir(), 'dcasa_comprobantes')
        os.makedirs(carpeta, exist_ok=True)
        return os.path.join(carpeta, f'{self.env.cr.dbname}_{self.id}_{self.parte}.zip')

    def _borrar_temporal(self):
        for paquete in self:
            try:
                os.remove(paquete._ruta_temporal())
            except FileNotFoundError:
                pass

    def _archivos_de(self, clave, registro):
        """``[(nombre, bytes)]`` de un documento, y una nota si no tiene nada. Lee un archivo a la vez."""
        reporte = self.env['ir.actions.report'].sudo()
        if clave in ('factura', 'nota'):
            guardado = registro.invoice_pdf_report_id
            if guardado:
                return [(guardado.name, guardado.raw)], ''
            pdf, _tipo = reporte._render_qweb_pdf('account.account_invoices', [registro.id])
            return [(f'{registro.name}.pdf', pdf)], ''
        if clave == 'cobro':
            pdf, _tipo = reporte._render_qweb_pdf('account.action_report_payment_receipt', [registro.id])
            return [(f'{registro.name}.pdf', pdf)], ''
        if registro._name == 'dcasa.nomina.reembolso':
            adjuntos = registro.sudo().recibo_ids
        else:
            adjuntos = self.env['ir.attachment'].sudo().search(
                [('res_model', '=', registro._name), ('res_id', '=', registro.id), ('res_field', '=', False)],
                order='id')
        archivos = [(a.name, a.raw) for a in adjuntos if a.type == 'binary']
        return archivos, ('' if archivos else self.env._('Sin documento adjunto: búscalo en papel.'))

    def _datos_de(self, clave, registro):
        """``(número, fecha, tercero, total)`` para el índice."""
        if registro._name == 'account.move':
            return registro.name, registro.date, registro.partner_id.name or '', registro.amount_total_signed
        if registro._name == 'account.payment':
            signo = -1 if registro.payment_type == 'outbound' else 1
            return registro.name, registro.date, registro.partner_id.name or '', signo * registro.amount
        return registro.name, registro.fecha, registro.empleado_id.name or '', registro.monto

    def _procesar(self, tiempo_disponible=None):
        """Mete documentos al ZIP hasta terminar o hasta que ``tiempo_disponible()`` diga que se acabó el tiempo.
        Devuelve True si terminó."""
        self.ensure_one()
        documentos = json.loads(self.documentos or '[]')
        ruta = self._ruta_temporal()
        if self.hechos > self.inicio_parte and not os.path.exists(ruta):
            # El servidor se reinició a media pieza: se rehace desde el principio de esa pieza.
            self.linea_ids.filtered(lambda ln: ln.parte == self.parte).sudo().unlink()
            self.sudo().hechos = self.inicio_parte
        while self.hechos < len(documentos):
            ruta = self._ruta_temporal()        # cambia al empezar otra pieza
            clave, modelo, res_id = documentos[self.hechos]
            if modelo not in MODELOS or clave not in CARPETAS:
                raise UserError(self.env._('Documento desconocido en la lista del ZIP.'))
            registro = self.env[modelo].sudo().browse(int(res_id)).exists()
            numero = fecha = tercero = ''
            total = 0.0
            filas = []
            if registro:
                numero, fecha, tercero, total = self._datos_de(clave, registro)
                try:
                    archivos, nota = self._archivos_de(clave, registro)
                except Exception as error:   # noqa: BLE001 — un documento malo no detiene el ZIP
                    _logger.exception('ZIP de comprobantes: no se pudo leer %s %s', modelo, res_id)
                    archivos, nota = [], self.env._('No se pudo generar: %s', str(error)[:200])
            else:
                archivos, nota = [], self.env._('El documento ya no existe.')
            carpeta = CARPETAS[clave]
            prefijo = nombre_seguro(f'{fecha or ""} {numero}', 60)
            with zipfile.ZipFile(ruta, 'a', compression=zipfile.ZIP_STORED) as zip_:
                usados = set(zip_.namelist())
                for indice, (nombre, contenido) in enumerate(archivos, 1):
                    base, extension = os.path.splitext(nombre or '')
                    extension = (extension or '.pdf').lower()[:8]
                    sufijo = f'_{indice}' if len(archivos) > 1 else ''
                    archivo = f'{carpeta}/{prefijo}{sufijo}{extension}'
                    while archivo in usados:
                        archivo = f'{carpeta}/{prefijo}_{len(usados)}{extension}'
                    usados.add(archivo)
                    zip_.writestr(archivo, contenido or b'')
                    filas.append(archivo)
            self.env['dcasa.comprobantes.paquete.linea'].sudo().create([{
                'paquete_id': self.id, 'carpeta': carpeta, 'archivo': archivo, 'tipo': TIPOS[clave],
                'numero': numero, 'fecha': fecha or False, 'tercero': tercero, 'total': total,
                'parte': self.parte, 'nota': nota} for archivo in (filas or [''])])
            self.sudo().hechos = self.hechos + 1
            if os.path.getsize(ruta) >= MAX_PARTE and self.hechos < len(documentos):
                self._guardar_parte(ultima=False)
            if tiempo_disponible and tiempo_disponible() <= 0 and self.hechos < len(documentos):
                return False
        self._guardar_parte(ultima=True)
        return True

    def _guardar_parte(self, ultima):
        """Sube la pieza llena como adjunto (en R2) y empieza otra. La última lleva el índice y el LEÉME."""
        self.ensure_one()
        ruta = self._ruta_temporal()
        if ultima:
            with zipfile.ZipFile(ruta, 'a', compression=zipfile.ZIP_DEFLATED) as zip_:
                zip_.writestr('INDICE.csv', self._indice_csv())
                desde, hasta = self._limites()
                zip_.writestr('LEEME.txt', LEEME.format(
                    periodo=f'{desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}',
                    fecha=fields.Date.context_today(self).strftime('%d/%m/%Y'),
                    quien=self.create_uid.name or ''))
        with open(ruta, 'rb') as archivo:
            contenido = archivo.read()
        nombre = nombre_seguro(self.name, 60).replace(' ', '_')
        if ultima and self.parte == 1:
            nombre_zip = f'{nombre}.zip'
        else:
            nombre_zip = f'{nombre}_parte_{self.parte}.zip'
        adjunto = self.env['ir.attachment'].sudo().create({
            'name': nombre_zip, 'raw': contenido, 'mimetype': 'application/zip',
            'res_model': self._name, 'res_id': self.id})
        del contenido
        self._borrar_temporal()
        valores = {'adjunto_ids': [(4, adjunto.id)]}
        if ultima:
            valores.update(estado='listo', resumen=self._texto_resumen(), documentos=False)
        else:
            valores.update(parte=self.parte + 1, inicio_parte=self.hechos)
        self.sudo().write(valores)
        if ultima:
            self.message_post(
                body=Markup('%s') % self.env._('Tu ZIP de comprobantes está listo: descárgalo desde esta pantalla '
                                               '(%s archivo(s)).', len(self.adjunto_ids)),
                partner_ids=self.create_uid.partner_id.ids, subtype_xmlid='mail.mt_comment')

    def _indice_csv(self):
        salida = io.StringIO()
        escritor = csv.writer(salida)
        escritor.writerow(['Carpeta', 'Archivo', 'Tipo', 'Número', 'Fecha', 'Cliente, proveedor o colaborador',
                           'Total', 'Parte del ZIP', 'Nota'])
        for linea in self.linea_ids.sorted(lambda ln: (ln.carpeta, ln.fecha or date.min, ln.id)):
            escritor.writerow([linea.carpeta, linea.archivo.split('/', 1)[-1] if linea.archivo else '', linea.tipo,
                               linea.numero or '', linea.fecha.strftime('%d/%m/%Y') if linea.fecha else '',
                               linea.tercero or '', f'{linea.total:.2f}', linea.parte, linea.nota or ''])
        # Con BOM: Excel lo abre con las tildes bien.
        return '﻿' + salida.getvalue()

    def _texto_resumen(self):
        cuentas = {}
        for linea in self.linea_ids:
            cuentas.setdefault(linea.carpeta, set()).add((linea.numero, linea.tipo))
        sin = len(self.linea_ids.filtered(lambda ln: not ln.archivo))
        partes = [f'{carpeta}: {len(docs)} documento(s)' for carpeta, docs in sorted(cuentas.items())]
        if sin:
            partes.append(self.env._('%s sin documento adjunto (están en el índice).', sin))
        return '\n'.join(partes)

    @api.model
    def _cron_preparar(self):
        Cron = self.env['ir.cron']
        pendientes = self.sudo().search([('estado', '=', 'preparando')], order='id')
        for paquete in pendientes:
            try:
                terminado = paquete._procesar(tiempo_disponible=lambda: Cron._commit_progress(1) - 30)
            except Exception as error:   # noqa: BLE001
                self.env.cr.rollback()
                _logger.exception('ZIP de comprobantes %s: falló', paquete.id)
                paquete.sudo().write({'estado': 'error', 'error': str(error)[:500]})
                paquete._borrar_temporal()
                Cron._commit_progress(0)
                continue
            if not terminado:
                Cron._commit_progress(0, remaining=1)
                return
            Cron._commit_progress(1)


class DcasaComprobantesPaqueteLinea(models.Model):
    _name = 'dcasa.comprobantes.paquete.linea'
    _description = 'Índice del ZIP de comprobantes'
    _order = 'carpeta, fecha, id'

    paquete_id = fields.Many2one('dcasa.comprobantes.paquete', required=True, ondelete='cascade', index=True)
    carpeta = fields.Char()
    archivo = fields.Char()
    tipo = fields.Char()
    numero = fields.Char('Número')
    fecha = fields.Date()
    tercero = fields.Char('Cliente, proveedor o colaborador')
    total = fields.Float()
    parte = fields.Integer('Parte del ZIP')
    nota = fields.Char()
