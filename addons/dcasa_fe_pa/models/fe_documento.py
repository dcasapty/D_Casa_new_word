"""El documento electrónico de una factura y su histórico inmutable de intentos.

Un ``dcasa.fe.documento`` por factura o nota de crédito publicada con la FE encendida. Sus
datos fiscales (número, punto, tipo, CUFE autorizado) no se reescriben y el documento no se
borra; cada conversación con el PAC queda en ``dcasa.fe.intento``, que tampoco se edita ni
se borra. Una corrección es una nota de crédito o una anulación registrada, nunca un borrado.

Estados::

    borrador ──► por_enviar ──► enviado (el PAC lo recibió, en proceso) ──► autorizado ──► anulado
                    │  ▲             │
                    │  └─ rechazado ◄┘ (se corrige la factura y se regenera con el mismo número)
                    └──► contingencia (sin PAC tras N intentos o modo contingencia) ──► autorizado
"""
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import catalogos as C
from . import generador
from . import pac as P

ESTADOS = [
    ('borrador', 'Borrador'),
    ('por_enviar', 'Por enviar'),
    ('enviado', 'Enviado (en proceso)'),
    ('autorizado', 'Autorizado'),
    ('rechazado', 'Rechazado'),
    ('anulado', 'Anulado'),
    ('contingencia', 'Contingencia'),
]
PENDIENTES = ('por_enviar', 'contingencia')
GRUPO_FACTURACION = 'account.group_account_invoice'
# Campos que identifican el documento ante la DGI: una vez puestos no cambian.
INMUTABLES = ('move_id', 'company_id', 'tipo_documento', 'punto', 'numero')
# Lo único que se escribe en un documento autorizado: su anulación.
EDITABLES_AUTORIZADO = {'estado', 'fecha_anulacion', 'motivo_anulacion', 'error'}
ESPERA_MAXIMA_MIN = 120
ESPERA_CONTINGENCIA_MIN = 60


class DcasaFeDocumento(models.Model):
    _name = 'dcasa.fe.documento'
    _description = 'Documento electrónico (DGI)'
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(string='Documento', compute='_compute_name', store=True)
    move_id = fields.Many2one('account.move', string='Factura', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, index=True)
    partner_id = fields.Many2one(related='move_id.partner_id', string='Cliente')
    estado = fields.Selection(ESTADOS, string='Estado', default='borrador', required=True, index=True)
    tipo_documento = fields.Selection(C.TIPOS_DOCUMENTO, string='Tipo de documento', required=True)
    tipo_emision = fields.Selection(C.TIPOS_EMISION, string='Tipo de emisión', default=C.EMISION_NORMAL)
    ambiente = fields.Selection(C.AMBIENTES, string='Ambiente')
    punto = fields.Char(string='Punto de facturación', size=3)
    numero = fields.Char(string='Número DGI', size=10, index=True)
    seguridad = fields.Char(string='Código de seguridad', size=9, groups='account.group_account_manager')
    fecha_emision = fields.Datetime(string='Emitido')
    cufe = fields.Char(string='CUFE', size=66, index=True)
    qr = fields.Char(string='Contenido del QR')
    protocolo = fields.Char(string='Protocolo de autorización')
    fecha_autorizacion = fields.Datetime(string='Autorizado el')
    payload = fields.Text(string='Documento (XML)')
    validacion_xsd = fields.Selection(
        [('sin_xsd', 'Sin XSD oficial cargado'), ('valido', 'Válido según XSD'), ('invalido', 'No valida')],
        string='Validación XSD')
    respuesta = fields.Text(string='Última respuesta del PAC')
    error = fields.Text(string='Error')
    intentos = fields.Integer(string='Fallos de comunicación seguidos', default=0)
    proximo_intento = fields.Datetime(string='Próximo intento', index=True)
    contingencia_inicio = fields.Datetime(string='Contingencia desde')
    contingencia_motivo = fields.Char(string='Motivo de la contingencia')
    contingencia_vencida = fields.Boolean(
        string='Contingencia pasada de plazo', compute='_compute_contingencia_vencida',
        help=f'Lleva más de {C.HORAS_AVISO_CONTINGENCIA} h en contingencia sin autorizarse '
             '(plazo SEGÚN FUENTE SECUNDARIA: confírmalo con el PAC).')
    referencia_id = fields.Many2one('dcasa.fe.documento', string='FE que corrige', ondelete='restrict')
    adaptador = fields.Char(string='PAC usado')
    fecha_anulacion = fields.Datetime(string='Anulado el')
    motivo_anulacion = fields.Char(string='Motivo de la anulación')
    intento_ids = fields.One2many('dcasa.fe.intento', 'documento_id', string='Intentos')

    _numero_unico = models.Constraint(
        'UNIQUE(company_id, punto, tipo_documento, numero)',
        'Ese número DGI ya existe en este punto de facturación.')
    _una_por_factura = models.Constraint('UNIQUE(move_id)', 'La factura ya tiene su documento electrónico.')

    @api.depends('tipo_documento', 'punto', 'numero', 'move_id.name')
    def _compute_name(self):
        for doc in self:
            doc.name = f'FE {doc.tipo_documento or ""}-{doc.punto or ""}-{doc.numero or ""} ({doc.move_id.name or ""})'

    @api.depends('estado', 'contingencia_inicio')
    def _compute_contingencia_vencida(self):
        limite = fields.Datetime.now() - timedelta(hours=C.HORAS_AVISO_CONTINGENCIA)
        for doc in self:
            doc.contingencia_vencida = bool(
                doc.estado == 'contingencia' and doc.contingencia_inicio and doc.contingencia_inicio < limite)

    # ------------------------------------------------------------------
    # Inmutabilidad
    # ------------------------------------------------------------------

    def write(self, vals):
        for doc in self:
            if any(campo in vals and doc._valor(campo) and doc._valor(campo) != vals[campo] for campo in INMUTABLES):
                raise UserError(self.env._('El número, punto, tipo y factura de un documento electrónico no cambian.'))
            if doc.estado == 'anulado':
                raise UserError(self.env._('Un documento electrónico anulado ya no se modifica.'))
            if doc.estado == 'autorizado' and set(vals) - EDITABLES_AUTORIZADO:
                raise UserError(self.env._('Un documento autorizado por la DGI no se modifica: '
                                           'se corrige con una nota de crédito o se anula.'))
        return super().write(vals)

    def _valor(self, campo):
        valor = self[campo]
        return valor.id if isinstance(valor, models.BaseModel) else valor

    def unlink(self):
        raise UserError(self.env._('Los documentos electrónicos no se borran: se anulan o se corrigen '
                                   'con una nota de crédito.'))

    # ------------------------------------------------------------------
    # Botones (comprueban el grupo ANTES de trabajar con sudo)
    # ------------------------------------------------------------------

    def _exigir_facturacion(self):
        if not self.env.user.has_group(GRUPO_FACTURACION):
            raise AccessError(self.env._('Solo Facturación puede enviar o corregir documentos electrónicos.'))

    def action_procesar(self):
        """Botón «Enviar / consultar ahora»."""
        self._exigir_facturacion()
        for doc in self.sudo():
            doc._procesar()
        return True

    def action_reintentar(self):
        """Botón de un rechazado: vuelve a generar con los datos corregidos (mismo número) y lo encola."""
        self._exigir_facturacion()
        for doc in self.sudo():
            if doc.estado not in ('rechazado', 'borrador'):
                raise UserError(self.env._('Solo se regenera un documento rechazado o en borrador.'))
            doc._generar()
            doc._registrar('generar', 'ok', self.env._('Regenerado tras corregir los datos.'))
        return True

    def action_anular(self):
        """Abre el asistente de anulación (el asistente comprueba el grupo)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'dcasa.fe.anular.wizard', 'view_mode': 'form',
            'target': 'new', 'name': self.env._('Anular factura electrónica'),
            'context': {'default_documento_id': self.id},
        }

    # ------------------------------------------------------------------
    # Servicio (privado; se llama ya con sudo)
    # ------------------------------------------------------------------

    @api.model
    def _crear_para(self, move):
        """Crea (o regenera, si fue rechazado) el documento de una factura recién publicada."""
        existente = self.sudo().search([('move_id', '=', move.id)], limit=1)
        if existente:
            if existente.estado in ('rechazado', 'borrador'):
                existente._generar()
                existente._registrar('generar', 'ok', self.env._('Regenerado al volver a publicar.'))
            return existente
        tipo, referencia = move._l10n_pa_fe_tipo_documento()
        doc = self.sudo().create({
            'move_id': move.id, 'company_id': move.company_id.id, 'tipo_documento': tipo,
            'punto': move.journal_id.l10n_pa_fe_punto, 'referencia_id': referencia.id,
        })
        doc.numero = move.journal_id._l10n_pa_fe_siguiente_numero(tipo)
        doc._generar()
        doc._registrar('generar', 'ok', self.env._('Documento generado.'))
        return doc

    def _generar(self):
        """Arma el XML, el CUFE y lo deja listo para enviar (o en contingencia)."""
        self.ensure_one()
        company = self.company_id
        en_contingencia = company.l10n_pa_fe_contingencia or self.estado == 'contingencia'
        valores = {
            'ambiente': company.l10n_pa_fe_ambiente,
            'seguridad': str(secrets.randbelow(900_000_000) + 100_000_000),
            'fecha_emision': self.fecha_emision or fields.Datetime.now(),
            'tipo_emision': C.EMISION_CONTINGENCIA if en_contingencia else C.EMISION_NORMAL,
            'estado': 'contingencia' if en_contingencia else 'por_enviar',
            'error': False, 'intentos': 0, 'proximo_intento': False,
            'adaptador': company.l10n_pa_fe_adaptador,
        }
        if en_contingencia and not self.contingencia_inicio:
            valores['contingencia_inicio'] = company.l10n_pa_fe_contingencia_inicio or fields.Datetime.now()
            valores['contingencia_motivo'] = company.l10n_pa_fe_contingencia_motivo or self.env._(
                'Sin comunicación con el proveedor autorizado (PAC).')
        self.write(valores)
        datos = self.move_id._l10n_pa_fe_datos(self)
        xml = generador.generar_xml(datos)
        errores_xsd = generador.validar_xsd(xml)
        self.write({
            'cufe': datos['cufe'], 'payload': xml.decode(),
            'validacion_xsd': 'sin_xsd' if errores_xsd is None else ('invalido' if errores_xsd else 'valido'),
        })
        if errores_xsd:
            self.write({'estado': 'rechazado', 'error': self.env._('No valida contra el XSD de la DGI:\n%s',
                                                                   '\n'.join(errores_xsd[:20]))})

    def _pac(self):
        nombre = self.company_id.l10n_pa_fe_adaptador
        if not nombre:
            raise UserError(self.env._('No hay PAC configurado.'))
        return self.env[f'dcasa.fe.pac.{nombre}'].sudo()

    def _procesar(self):
        """Un paso de la cola: envía lo pendiente o consulta lo que está en proceso."""
        self.ensure_one()
        if self.estado in PENDIENTES:
            self._aplicar('enviar', self._llamar(lambda pac: pac._enviar(self)))
        elif self.estado == 'enviado':
            self._aplicar('consultar', self._llamar(lambda pac: pac._consultar(self)))

    def _llamar(self, operacion):
        """Llama al PAC; cualquier excepción del adaptador se trata como falla de comunicación."""
        try:
            return operacion(self._pac())
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001 — un PAC caído no tumba la cola
            return {'resultado': P.ERROR_COMUNICACION, 'mensaje': f'{type(error).__name__}: {error}'}

    def _aplicar(self, operacion, respuesta):
        resultado = respuesta.get('resultado')
        mensaje = respuesta.get('mensaje') or ''
        self._registrar(operacion, resultado, mensaje, respuesta.get('respuesta'))
        valores = {'respuesta': respuesta.get('respuesta') or mensaje}
        if resultado == P.AUTORIZADO:
            valores.update({
                'estado': 'autorizado', 'error': False, 'intentos': 0, 'proximo_intento': False,
                'cufe': respuesta.get('cufe') or self.cufe, 'qr': respuesta.get('qr'),
                'protocolo': respuesta.get('protocolo'),
                'fecha_autorizacion': respuesta.get('fecha') or fields.Datetime.now(),
            })
        elif resultado == P.RECIBIDO:
            valores.update({'estado': 'enviado', 'error': False, 'intentos': 0,
                            'proximo_intento': fields.Datetime.now() + timedelta(minutes=5)})
        elif resultado == P.RECHAZADO:
            valores.update({'estado': 'rechazado', 'error': mensaje, 'proximo_intento': False})
        else:
            valores.update(self._valores_fallo(mensaje))
        self.write(valores)
        if valores.get('estado') == 'contingencia' and self.tipo_emision != C.EMISION_CONTINGENCIA:
            # Nunca se autorizó: se vuelve a emitir como contingencia (cambia iTpEmis y, con él, el CUFE).
            self._generar()
            self.write({'proximo_intento': valores['proximo_intento'], 'error': mensaje})
            self._registrar('generar', 'ok', self.env._('Regenerado para emisión en contingencia.'))

    def _valores_fallo(self, mensaje):
        """Falla de comunicación: espera creciente; tras N fallos seguidos, contingencia."""
        intentos = self.intentos + 1
        ahora = fields.Datetime.now()
        if self.estado == 'contingencia' or intentos >= max(self.company_id.l10n_pa_fe_reintentos, 1):
            return {'estado': 'contingencia', 'intentos': intentos, 'error': mensaje,
                    'contingencia_inicio': self.contingencia_inicio or ahora,
                    'contingencia_motivo': self.contingencia_motivo or self.env._(
                        'Sin comunicación con el proveedor autorizado (PAC): %s', mensaje)[:C.MOTIVO_MAX],
                    'proximo_intento': ahora + timedelta(minutes=ESPERA_CONTINGENCIA_MIN)}
        espera = min(5 * 2 ** (intentos - 1), ESPERA_MAXIMA_MIN)
        return {'intentos': intentos, 'error': mensaje, 'proximo_intento': ahora + timedelta(minutes=espera)}

    def _anular_en_pac(self, motivo):
        self.ensure_one()
        if self.estado != 'autorizado':
            raise UserError(self.env._('Solo se anula un documento autorizado por la DGI.'))
        respuesta = self._llamar(lambda pac: pac._anular(self, motivo))
        self._registrar('anular', respuesta.get('resultado'), respuesta.get('mensaje') or '',
                        respuesta.get('respuesta'))
        if respuesta.get('resultado') != P.ANULADO:
            raise UserError(self.env._('El PAC no registró la anulación: %s', respuesta.get('mensaje') or ''))
        self.write({'estado': 'anulado', 'motivo_anulacion': motivo,
                    'fecha_anulacion': respuesta.get('fecha') or fields.Datetime.now()})

    def _registrar(self, operacion, resultado, mensaje, respuesta=None):
        self.env['dcasa.fe.intento'].sudo().create({
            'documento_id': self.id, 'operacion': operacion, 'resultado': resultado or 'desconocido',
            'mensaje': mensaje, 'respuesta': respuesta, 'cufe': self.cufe, 'estado': self.estado,
        })

    @api.model
    def _cron_procesar(self, limite=50):
        """Cola: lo pendiente cuyo turno llegó, en orden de llegada. Solo empresas con la FE operando."""
        ahora = fields.Datetime.now()
        companias = self.env['res.company'].sudo().search([('l10n_pa_fe_activo', '=', True),
                                                           ('l10n_pa_fe_adaptador', '!=', False)])
        if not companias:
            return
        docs = self.sudo().search([
            ('company_id', 'in', companias.ids), ('estado', 'in', PENDIENTES + ('enviado',)),
            '|', ('proximo_intento', '=', False), ('proximo_intento', '<=', ahora),
        ], order='id', limit=limite)
        for doc in docs:
            doc._procesar()


    @api.model
    def _resumen(self, dias=30):
        """Solo lectura (Brian y tablero): conteo por estado y lo que pide atención. Corre como el usuario."""
        docs = self.search([('create_date', '>=', fields.Datetime.now() - timedelta(days=dias))])
        conteo = dict.fromkeys((codigo for codigo, _etiqueta in ESTADOS), 0)
        for doc in docs:
            conteo[doc.estado] += 1
        atencion = docs.filtered(lambda d: d.estado == 'rechazado' or d.contingencia_vencida)
        return {'conteo': conteo, 'atencion': atencion}


class DcasaFeIntento(models.Model):
    """Histórico de cada operación con el PAC. Solo se agrega: no se edita ni se borra."""
    _name = 'dcasa.fe.intento'
    _description = 'Intento con el PAC (histórico)'
    _order = 'id desc'

    documento_id = fields.Many2one('dcasa.fe.documento', required=True, ondelete='restrict', index=True)
    move_id = fields.Many2one(related='documento_id.move_id', string='Factura')
    fecha = fields.Datetime(default=fields.Datetime.now, required=True)
    usuario_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user)
    operacion = fields.Selection([('generar', 'Generar'), ('enviar', 'Enviar'), ('consultar', 'Consultar'),
                                  ('anular', 'Anular')], required=True)
    resultado = fields.Char(required=True)
    estado = fields.Char(string='Estado antes')
    cufe = fields.Char(string='CUFE')
    mensaje = fields.Text()
    respuesta = fields.Text()

    def write(self, vals):
        raise UserError(self.env._('El histórico de la factura electrónica no se edita.'))

    def unlink(self):
        raise UserError(self.env._('El histórico de la factura electrónica no se borra.'))
