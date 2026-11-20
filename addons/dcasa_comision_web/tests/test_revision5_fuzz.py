"""Quinta revisión adversarial, parte D: fuzz con oraculo ESTRICTO para el pago con fecha futura y las versiones en desorden.
Acciones aleatorias (con semilla): pagar (fecha de hoy -3 a +8), abonar, cancelar el pago, avanzar el reloj, barrer,
poner al dia, guardar una version HOY, una version futura o anular una programada, devolver. Al final (tras un barrido):
 * si el cobro sigue con fecha futura: la version de la venta es la que rige HOY y el libro es el de esa version;
 * si el cobro fue de fecha futura y ya llego el dia: la version es la que rige el dia de cobro;
 * en cualquier otro caso: el libro coincide con la version que regia el dia de cobro o la de hoy (lo que sea legitimo).
Y correr todo otra vez no anota nada. Datos de PRUEBA."""
# ruff: noqa: E501, PLR0912, PLR0915
import logging
import os
import random
from datetime import date, timedelta

from odoo import fields
from odoo.addons.dcasa_comision_web.models import calculo
from odoo.addons.dcasa_comision_web.models.movimiento import dia_de_panama
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_revision5_cobro import CobroBase

_logger = logging.getLogger(__name__)
PRIMER_DIA = date(2030, 3, 4)
PORCENTAJES = [3.0, 7.5, 12.0, 15.0, 25.0, 30.0]


class _Deshacer(Exception):
    pass


@tagged('post_install', '-at_install')
class TestFuzzDePagosYVersiones(CobroBase):

    def hoy_panama(self):
        return fields.Date.context_today(self.env['dcasa.web.venta'].with_context(tz='America/Panama'))

    def versiones_guardadas(self):
        return self.env['dcasa.web.reglas'].sudo().search([('company_id', '=', self.company.id)])

    def version_independiente(self, dia):
        """La ultima guardada (no anulada) entre las que ya empezaron ese dia."""
        cand = [v for v in self.versiones_guardadas() if not v.anulada and dia_de_panama(v.rige_desde) <= dia]
        return max(cand, key=lambda v: v.numero) if cand else None

    def libro_esperado(self, version, nc):
        if version is None:
            return {self.ana.id: 0, self.beto.id: 0}
        base = 100000 - nc
        debe = calculo.porcentaje_de(base, version.porcentaje)
        partes = calculo.repartir(debe, [(self.ana.id, 60.0), (self.beto.id, 40.0)])
        return {self.ana.id: partes.get(self.ana.id, 0), self.beto.id: partes.get(self.beto.id, 0)}

    def secuencia(self, semilla):
        rng = random.Random(semilla)
        self.avanzar('2030-03-04 15:00:00')
        self.version(10.0)
        orden = self.orden(vendedora=self.u_vendedora)
        factura = self.facturar(orden, '2030-03-04')
        nc = 0
        historial_hoy = [self.hoy_panama()]
        bit = []
        for _paso in range(rng.randint(4, 12)):
            hoy = self.hoy_panama()
            accion = rng.choice(['pagar', 'pagar', 'pagar_futuro', 'abonar', 'cancelar', 'avanzar', 'avanzar', 'barrido', 'poner_al_dia',
                                 'version_hoy', 'version_futura', 'anular', 'nota'])
            if accion == 'avanzar':
                self.avanzar((fields.Datetime.now() + timedelta(days=rng.randint(1, 6))).strftime('%Y-%m-%d %H:%M:%S'))
                historial_hoy.append(self.hoy_panama())
            elif accion in ('pagar', 'pagar_futuro') and factura.payment_state not in ('paid', 'in_payment'):
                delta = rng.randint(-3, 3) if accion == 'pagar' else rng.randint(1, 8)
                d = max(PRIMER_DIA, hoy + timedelta(days=delta))
                self.pagar(factura, d.isoformat())
            elif accion == 'abonar' and factura.payment_state in ('not_paid',):
                d = max(PRIMER_DIA, hoy + timedelta(days=rng.randint(-2, 4)))
                self.pagar(factura, d.isoformat(), monto=300.0)
            elif accion == 'cancelar' and factura._get_reconciled_payments():
                factura._get_reconciled_payments().sorted('id')[-1].action_cancel()
            elif accion == 'barrido':
                self.env['dcasa.web.venta']._barrido()
            elif accion == 'poner_al_dia':
                self.env['dcasa.web.venta']._poner_al_dia()
            elif accion == 'version_hoy':
                self.version(rng.choice(PORCENTAJES))
            elif accion == 'version_futura':
                self.version(rng.choice(PORCENTAJES), rige_desde=fields.Datetime.now() + timedelta(days=rng.randint(1, 10)))
            elif accion == 'anular':
                prog = self.versiones_guardadas().filtered(lambda v: v.estado in ('programada', 'tapada') and not v.anulada)
                prog = prog.filtered(lambda v: not self.env['dcasa.web.venta'].sudo().search_count([('reglas_id', '=', v.id)]))
                if prog:
                    v = rng.choice(prog.ids)
                    v = prog.browse(v)
                    v.motivo_anulacion = 'prueba'
                    try:
                        with self.env.cr.savepoint():
                            v.with_user(self.u_nomina).action_anular()
                    except UserError:
                        pass
            elif accion == 'nota' and nc == 0 and factura.payment_state in ('paid', 'in_payment'):
                self.nota(factura, 200.0, fecha=max(PRIMER_DIA, hoy).isoformat())
                nc = 20000
            bit.append((accion, str(hoy), factura.payment_state))
        self.env['dcasa.web.venta']._barrido()
        return factura, nc, bit, historial_hoy

    def evaluar(self, factura, nc):
        """``(ok, motivo)`` de una factura al final de una secuencia, contra el oráculo estricto."""
        venta = self.venta(factura)
        hoy = self.hoy_panama()
        dias, _notas = self.env['dcasa.nomina.meta.bono']._dias_de_cobro(factura)
        pagada = factura.state == 'posted' and factura.payment_state in ('paid', 'in_payment')
        en_cero = {self.ana.id: 0, self.beto.id: 0}
        real = {e.id: self.neto(venta, e) for e in (self.ana, self.beto)} if venta else en_cero
        if not pagada:
            return real == en_cero, 'no pagada debe tener neto 0'
        dia = dias.get(factura.id)
        regia = self.version_independiente(min(dia, hoy))
        if not (venta and venta.reglas_id):
            # sin versión: solo puede ser que no haya ninguna que rija ese día para el cobro
            return (regia is None or not venta) and real == en_cero, f'sin version: deberia regir {getattr(regia, "numero", None)}'
        if dia > hoy or venta.cobro_adelantado:
            ok = venta.reglas_id == regia and real == self.libro_esperado(venta.reglas_id, nc)
            return ok, f'estricto: version={venta.reglas_id.numero} esperada={getattr(regia, "numero", None)}'
        # Cualquier versión que pudo regir ese día en algún momento de la secuencia (un cambio de versión el mismo día
        # deja las ventas ya anotadas con la anterior: decisión de diseño, ver «Por decidir»).
        opciones = {v for v in self.versiones_guardadas() if not v.anulada and dia_de_panama(v.rige_desde) <= dia}
        ok = real in [self.libro_esperado(v, nc) for v in opciones] and venta.reglas_id in opciones
        return ok, f'lenient: version={venta.reglas_id.numero} opciones={[v.numero for v in opciones]}'

    def comprobar_semilla(self, semilla):
        """Corre la secuencia de ``semilla`` y devuelve ``None`` si todo cuadra o el motivo si no. Todo queda deshecho."""
        try:
            with self.env.cr.savepoint():
                factura, nc, bit, _historial = self.secuencia(semilla)
                venta = self.venta(factura)
                ok, motivo = self.evaluar(factura, nc)
                # idempotencia (y que la foto del libro no cambie)
                antes = self.foto_libro()
                if venta:
                    venta._reconciliar()
                self.env['dcasa.web.venta']._barrido()
                self.env['dcasa.web.venta']._poner_al_dia()
                if antes != self.foto_libro():
                    ok, motivo = False, 'NO IDEMPOTENTE'
                resultado = None if ok else f'{motivo}; pago={factura.payment_state}; bitacora={bit}'
                raise _Deshacer(resultado)
        except _Deshacer as fin:
            return fin.args[0]

    def test_revision5_d01_fuzz_estricto(self):
        """24 secuencias por defecto (``FUZZ_N`` y ``FUZZ_DESDE`` por variable de entorno: las 201 de la revisión pasan).
        Con el código de la cuarta ronda caen varias (2001, 2004, 2011, 2012, 2016 y 2021 entre ellas)."""
        desde = int(os.environ.get('FUZZ_DESDE', '2000'))
        n = int(os.environ.get('FUZZ_N', '24'))
        malas = {}
        for semilla in range(desde, desde + n):
            with self.subTest(semilla=semilla):
                motivo = self.comprobar_semilla(semilla)
                if motivo:
                    malas[semilla] = motivo
        self.assertFalse(malas, list(malas.items())[:3])
