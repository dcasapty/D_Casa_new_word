"""Cada correo sale marcado con su clase (la política de Resend) y los errores temporales se reintentan solos.

Lo que la política no deja salir (apagado, staging, correos automáticos de Odoo) se marca como no enviado ANTES de
intentar mandarlo: así no se llama a Resend y el registro no se llena de errores con su traza por algo que es a
propósito. El transporte vuelve a revisar lo mismo (dos candados).
"""
import ast
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.tools.mail import email_normalize_all

from . import politica, resend

_logger = logging.getLogger(__name__)

# Minutos de espera antes de cada reintento, según cuántos van (desde que falló: write_date).
ESPERAS_MIN = (5, 15, 60, 240, 240)
MAX_INTENTOS = 5


class MailMail(models.Model):
    _inherit = 'mail.mail'

    dcasa_intentos = fields.Integer('Reintentos (Resend)', default=0, copy=False, readonly=True)

    def _dcasa_autor_interno(self):
        """¿Lo escribió una persona del equipo (usuario interno activo, no el sistema)?"""
        self.ensure_one()
        usuarios = self.sudo().author_id.with_context(active_test=False).user_ids
        return bool(usuarios.filtered(lambda u: u.active and not u.share and u.id != SUPERUSER_ID))

    def _dcasa_clase(self):
        """La clase de este correo para la política (ver ``politica.py``)."""
        self.ensure_one()
        try:
            cabeceras = ast.literal_eval(self.headers) if self.headers else {}
        except (ValueError, SyntaxError, TypeError):
            cabeceras = {}
        cabecera = cabeceras.get(politica.CABECERA_CORREO) if isinstance(cabeceras, dict) else None
        return politica.clase_de_correo(self.model, self.message_type, self._dcasa_autor_interno(), cabecera)

    def _dcasa_destinos(self):
        self.ensure_one()
        destinos = email_normalize_all(self.email_to or '') + email_normalize_all(self.email_cc or '')
        for partner in self.sudo().recipient_ids:
            destinos += email_normalize_all(partner.email or '')
        return destinos

    def send(self, auto_commit=False, raise_exception=False, post_send_callback=None):
        """Con la clave de Resend, lo que la política no deja salir se marca «no enviado» sin intentar mandarlo."""
        correo = self.env['dcasa.correo'].sudo()
        Servidor = self.env['ir.mail_server']
        if not correo._hay_clave() or Servidor._disable_send() or Servidor.sudo().search_count([], limit=1):
            return super().send(auto_commit=auto_commit, raise_exception=raise_exception,
                                post_send_callback=post_send_callback)
        activo, entorno, internos = correo._activo_para_clientes(), correo._entorno(), correo._correos_internos()
        frenados = self.browse()
        for mail in self.filtered(lambda m: m.state == 'outgoing' and not m.mail_server_id):
            sale, motivo = politica.puede_salir(mail._dcasa_clase(), activo, entorno, mail._dcasa_destinos(), internos)
            if sale:
                continue
            if raise_exception:
                raise MailDeliveryException(f'{resend.PREFIJO_NO_ENVIADO} {motivo}')
            razon = f'{resend.PREFIJO_NO_ENVIADO} {motivo}'
            mail.write({'state': 'exception', 'failure_reason': razon, 'failure_type': 'unknown'})
            mail._postprocess_sent_message(success_pids=[], success_emails=[], failure_reason=razon,
                                           failure_type='unknown')
            frenados |= mail
        if frenados:
            _logger.info('DCASA_CORREO %s correos no salieron por la política (apagado, staging u Odoo)', len(frenados))
            if post_send_callback:
                post_send_callback(frenados.ids)
        resto = self - frenados
        if not resto:
            return True
        return super(MailMail, resto).send(auto_commit=auto_commit, raise_exception=raise_exception,
                                           post_send_callback=post_send_callback)

    def _prepare_outgoing_list(self, mail_server=False, doc_to_followers=None):
        resultados = super()._prepare_outgoing_list(mail_server=mail_server, doc_to_followers=doc_to_followers)
        if not self.env['dcasa.correo'].sudo()._hay_clave():
            return resultados
        clase = self._dcasa_clase()
        for resultado in resultados:
            cabeceras = dict(resultado.get('headers') or {})
            cabeceras[politica.CABECERA_CLASE] = clase
            resultado['headers'] = cabeceras
        return resultados

    @api.model
    def _dcasa_reintentar(self):
        """Cron: vuelve a poner en la cola los correos que fallaron por algo temporal de Resend (429, 5xx, sin red),
        con espera creciente y hasta 5 veces. Lo que Resend rechazó de verdad, o lo que la política no dejó salir
        (``DCASA_NO_ENVIADO``), no se reintenta nunca."""
        ahora = fields.Datetime.now()
        candidatos = self.sudo().search([
            ('state', '=', 'exception'), ('failure_reason', 'like', resend.PREFIJO_REINTENTAR),
            ('dcasa_intentos', '<', MAX_INTENTOS)], order='id', limit=200)
        listos = candidatos.filtered(
            lambda m: m.write_date and m.write_date <= ahora - timedelta(minutes=ESPERAS_MIN[m.dcasa_intentos]))
        for correo in listos:
            correo.write({'state': 'outgoing', 'dcasa_intentos': correo.dcasa_intentos + 1})
        if listos:
            _logger.info('DCASA_CORREO reintentando %s correos', len(listos))
            self.sudo().process_email_queue(email_ids=listos.ids)
        return len(listos)
