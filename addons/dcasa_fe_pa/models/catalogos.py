"""Catálogos del documento electrónico de la DGI (rFE) y cálculo del CUFE.

Python puro, sin Odoo: se prueba solo. Cada tabla dice de dónde sale. Las fuentes y su
grado de verificación están en ``docs/FACTURA_ELECTRONICA.md``:

* VERIFICADO: comprobado contra un dato real de la DGI (p. ej. el CUFE contra dos CUFE
  publicados por el portal de consultas de la DGI).
* SEGÚN FUENTE SECUNDARIA: lo dicen implementaciones abiertas y guías de terceros que
  citan la Ficha Técnica; no se pudo leer la Ficha oficial desde este entorno.

Si la Ficha Técnica vigente o el XSD contradicen algo de aquí, manda la Ficha.
"""

# Versión del formato (A01 dVerForm). SEGÚN FUENTE SECUNDARIA: «1.00» (Ficha V1.00, rev. abril 2025).
VERSION_FORMATO = '1.00'

# Espacio de nombres del rFE. NO VERIFICADO contra el XSD: las fuentes muestran
# «http://dgi-fep.mef.gob.pa» (servicios de recepción) y lo usan los ejemplos públicos.
NAMESPACE = 'http://dgi-fep.mef.gob.pa'

# B02 iAmb — ambiente de destino. SEGÚN FUENTE SECUNDARIA (y el QR real lleva iAmb=1 en producción).
AMBIENTES = [('2', 'Pruebas'), ('1', 'Producción')]

# B03 iTpEmis — tipo de emisión. SEGÚN FUENTE SECUNDARIA.
TIPOS_EMISION = [
    ('01', 'Autorización previa, operación normal'),
    ('02', 'Autorización previa, operación en contingencia'),
    ('03', 'Autorización posterior, operación normal'),
    ('04', 'Autorización posterior, operación en contingencia'),
]
EMISION_NORMAL = '01'
EMISION_CONTINGENCIA = '02'

# B06 iDoc — tipo de documento. SEGÚN FUENTE SECUNDARIA (dos implementaciones coinciden en 01–09;
# una agrega 10 «Factura de operación extranjera», que no se usa aquí).
TIPOS_DOCUMENTO = [
    ('01', 'Factura de operación interna'),
    ('02', 'Factura de importación'),
    ('03', 'Factura de exportación'),
    ('04', 'Nota de crédito referente a una o varias FE'),
    ('05', 'Nota de débito referente a una o varias FE'),
    ('06', 'Nota de crédito genérica'),
    ('07', 'Nota de débito genérica'),
    ('08', 'Factura de zona franca'),
    ('09', 'Reembolso'),
]
DOC_FACTURA = '01'
DOC_EXPORTACION = '03'
DOC_NC_REFERENCIA = '04'
DOC_NC_GENERICA = '06'
DOC_CON_REFERENCIA = ('04', '05')

# B12 iNatOp — naturaleza de la operación. SEGÚN FUENTE SECUNDARIA.
NATURALEZA = {'venta': '01', 'exportacion': '02', 'devolucion': '11'}

# B401 iTipoRec — tipo de receptor. SEGÚN FUENTE SECUNDARIA (coinciden dos implementaciones).
TIPOS_RECEPTOR = [
    ('01', 'Contribuyente'),
    ('02', 'Consumidor final'),
    ('03', 'Gobierno'),
    ('04', 'Extranjero'),
]
RECEPTOR_CONTRIBUYENTE = '01'
RECEPTOR_CONSUMIDOR_FINAL = '02'
RECEPTOR_GOBIERNO = '03'
RECEPTOR_EXTRANJERO = '04'

# dTipoRuc — tipo de contribuyente. SEGÚN FUENTE SECUNDARIA y VERIFICADO en el CUFE (posición 5).
TIPOS_RUC = [('1', 'Persona natural'), ('2', 'Persona jurídica')]

# dTasaITBMS (grupo gITBMSItem del ítem) — tasa del ITBMS. SEGÚN FUENTE SECUNDARIA (coinciden dos implementaciones).
TASAS_ITBMS = [('00', '0 % (exento)'), ('01', '7 %'), ('02', '10 %'), ('03', '15 %')]
TASA_POR_PORCENTAJE = {0.0: '00', 7.0: '01', 10.0: '02', 15.0: '03'}
PORCENTAJE_POR_TASA = {codigo: porcentaje for porcentaje, codigo in TASA_POR_PORCENTAJE.items()}

# iFormaPago — forma de pago. SEGÚN FUENTE SECUNDARIA: 01–08 y 99 coinciden en dos fuentes;
# 09 «Cheque» solo aparece en la más reciente (marcado para confirmar con el PAC).
FORMAS_PAGO = [
    ('01', 'Crédito'),
    ('02', 'Contado / efectivo'),
    ('03', 'Tarjeta de crédito'),
    ('04', 'Tarjeta de débito'),
    ('05', 'Tarjeta de fidelización'),
    ('06', 'Vale'),
    ('07', 'Tarjeta de regalo'),
    ('08', 'Transferencia / depósito a cuenta bancaria (ACH)'),
    ('09', 'Cheque (confirmar con el PAC)'),
    ('99', 'Otro'),
]
FORMA_PAGO_CREDITO = '01'
FORMA_PAGO_OTRO = '99'

# iPzPag — tiempo de pago. SEGÚN FUENTE SECUNDARIA.
PAGO_INMEDIATO = '1'
PAGO_A_PLAZO = '2'

# Contingencia: plazo para transmitir lo emitido en contingencia. SEGÚN FUENTE SECUNDARIA (72 h),
# NO VERIFICADO en la Ficha / resolución: se usa solo para avisar, nunca para bloquear.
HORAS_AVISO_CONTINGENCIA = 72
# dMotCont: SEGÚN FUENTE SECUNDARIA, entre 15 y 150 caracteres.
MOTIVO_MIN, MOTIVO_MAX = 15, 150

# Consulta pública por QR. VERIFICADO: así son los QR reales (producción y staging de la DGI).
URL_QR = {'1': 'https://dgi-fep.mef.gob.pa/Consultas/FacturasPorQR',
          '2': 'https://dgi-fepst.mef.gob.pa/Consultas/FacturasPorQR'}
URL_CUFE = {'1': 'https://dgi-fep.mef.gob.pa/Consultas/FacturasPorCUFE/',
            '2': 'https://dgi-fepst.mef.gob.pa/Consultas/FacturasPorCUFE/'}


def codigo_tasa(porcentaje):
    """7.0 → '01'. None si el porcentaje no es una tasa de ITBMS conocida."""
    return TASA_POR_PORCENTAJE.get(round(float(porcentaje or 0.0), 4))


def solo_digitos(texto):
    return ''.join(c for c in str(texto or '') if c.isdigit())


# ----------------------------------------------------------------------------
# CUFE
# ----------------------------------------------------------------------------
# Estructura VERIFICADA contra dos CUFE reales publicados por la DGI (66 caracteres):
#   FE01200000045400-2-299934-0900002022050500000000389990117686690628
#   FE0120000000138-289-35920-0489172020090301000861280010117979798825
#
#   'FE' + iDoc(2) + dTipoRuc(1) + dRuc rellenado con ceros a 20 + '-' + dDV(2) + dSucEm(4)
#   + fecha AAAAMMDD(8) + dNroDF(10) + dPtoFacDF(3) + iTpEmis(2) + iAmb(1) + dSeg(9)
#   + dígito verificador(1)
#
# Dígito verificador: Luhn (módulo 10) sobre todo lo anterior SIN el prefijo «FE», donde cada
# carácter no numérico se cambia por el segundo dígito de su código ASCII ('-' = 45 → '5').
# Así lo hace la librería abierta dgi-fe y da el dígito correcto en los dos CUFE reales.

LARGO_CUFE = 66


def _a_digitos(texto):
    return ''.join(c if c.isdigit() else str(ord(c))[1] for c in texto)


def luhn(numero):
    total = 0
    for posicion, caracter in enumerate(reversed(numero)):
        digito = int(caracter)
        if posicion % 2 == 0:
            digito *= 2
            if digito > 9:
                digito -= 9
        total += digito
    return str((10 - total % 10) % 10)


def cufe(tipo_documento, tipo_ruc, ruc, dv, sucursal, fecha, numero, punto, tipo_emision, ambiente, seguridad):
    """Arma el CUFE. ``fecha`` es un date/datetime; el resto, textos."""
    cuerpo = ''.join([
        str(tipo_documento).zfill(2),
        str(tipo_ruc),
        str(ruc).strip().rjust(20, '0'),
        '-' + solo_digitos(dv).zfill(2),
        str(sucursal).zfill(4),
        fecha.strftime('%Y%m%d'),
        str(numero).zfill(10),
        str(punto).zfill(3),
        str(tipo_emision).zfill(2),
        str(ambiente),
        str(seguridad).zfill(9),
    ])
    return 'FE' + cuerpo + luhn(_a_digitos(cuerpo))


def cufe_valido(texto):
    """True si el CUFE tiene el largo y el dígito verificador correctos."""
    texto = str(texto or '')
    if len(texto) != LARGO_CUFE or not texto.startswith('FE'):
        return False
    return luhn(_a_digitos(texto[2:-1])) == texto[-1]
