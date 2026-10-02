# Factura electrónica DGI (Panamá): preparación

Módulo: `addons/dcasa_fe_pa`. Estado al 2 de octubre de 2026: **listo para conectar un PAC,
apagado por defecto**. Mientras no se active y no haya un PAC configurado, Odoo factura
exactamente igual que hoy.

## Cómo leer este documento

Cada dato lleva una etiqueta:

| Etiqueta | Qué significa |
|---|---|
| **VERIFICADO** | Comprobado contra un dato real de la DGI (p. ej. un CUFE publicado por su portal). |
| **SEGÚN FUENTE OFICIAL** | Lo dice una página de la DGI o del MEF (leída en el resultado de búsqueda, no completa). |
| **SEGÚN FUENTE SECUNDARIA** | Lo dicen implementaciones abiertas o guías de terceros que citan la Ficha Técnica. |
| **NO VERIFICADO** | No se pudo confirmar. Hay que preguntarlo al PAC o leerlo en la Ficha Técnica. |

**Limitación de esta investigación:** desde el entorno de desarrollo el acceso a
`dgi.mef.gob.pa` (y a la mayoría de los sitios de terceros) estaba bloqueado por la red. La
Ficha Técnica y el XSD oficiales **no se pudieron descargar ni leer completos**. Lo
oficial se tomó de los resultados de búsqueda (título, fragmento y URL) y la estructura del
XML de tres repositorios públicos en GitHub. Antes de encender en producción, hay que
contrastarlo con la Ficha vigente y validarlo contra el XSD (ver «Qué falta»).

## Fuentes (consultadas el 2026-10-02)

Oficiales (DGI / MEF):

1. Ficha Técnica de la FE para los PAC, V1.00, revisión de abril de 2025 (PDF):
   https://dgi.mef.gob.pa/_7facturaelectronica/source/F-T%C3%A9cnica%20de%20Factura%20Electr%C3%B3nica%20para%20los%20Proveedores%20de%20Autorizaci%C3%B3n%20Calificados%20V1.00-Abril2025.pdf
2. Página «Ficha Técnica PAC» (esquemas, paquete `PS_FE_1.00.zip` con `FE_v1.00.xsd`):
   https://dgi.mef.gob.pa/_7facturaelectronica/ftPAC
3. Listado de Proveedores Autorizados Calificados (PAC): https://dgi.mef.gob.pa/_7FacturaElectronica/Proveedorespac
4. Base legal de la factura electrónica: https://dgi.mef.gob.pa/_7FacturaElectronica/Blegales
5. Modalidad Facturador Gratuito: https://dgi.mef.gob.pa/_7FacturaElectronica/f-Gratuito
6. Preguntas frecuentes FE: https://dgi.mef.gob.pa/_7FacturaElectronica/fpreguntas
7. MEF, «La DGI establece normas para la adopción de la factura electrónica» (Decreto Ejecutivo 766):
   https://www.mef.gob.pa/2021/01/la-dgi-establece-normas-para-la-adopcion-de-la-factura-electronica/
8. Portal de consultas (CUFE y QR reales usados para verificar el algoritmo):
   - https://dgi-fep.mef.gob.pa/Consultas/FacturasPorCUFE/FE01200000045400-2-299934-0900002022050500000000389990117686690628
   - https://dgi-fep.mef.gob.pa/Consultas/FacturasPorQR?chFE=FE0120000000138-289-35920-0489172020090301000861280010117979798825&iAmb=1&digestValue=…&jwt=…

Secundarias:

9. `Electronic-Signatures-Industries/dgi-fe` (TypeScript; CUFE, catálogos, modelos del XSD):
   https://github.com/Electronic-Signatures-Industries/dgi-fe
10. `nomadic-coding/dgi` (Odoo 18, `l10n_pa_edi` para el PAC The Factory HKA; catálogos y reglas):
    https://github.com/nomadic-coding/dgi
11. `Factura-Facil/estandar-fe-retail-fer` (ejemplo de rFE con el orden de `gDGen` y `gItem`):
    https://github.com/Factura-Facil/estandar-fe-retail-fer
12. Cambios a la Ficha Técnica vigentes desde el 22-04-2025: https://www.prospectiva.com.mx/?p=17823
13. Resolución 201-6299 de 2025 (umbral del Facturador Gratuito):
    https://enlaceglobal.com.pa/resolucion-201-6299-en-panama/ ·
    https://www.gosocket.net/centro-de-recursos/nuevos-obligados-a-implementar-sistema-pac-2026/ ·
    https://blog.alegra.com/panama/facturador-gratuito-dgi/
14. Contingencia (72 h): https://cuenti.com.pa/factura-contingencia-panama/
15. Validar FE (CUFE, CAFE, QR): https://blog.alegra.com/panama/validar-factura-electronica-en-panama/

## Marco legal y el papel del PAC

- **Ley 256 de 26 de noviembre de 2021**: crea el Sistema de Factura Electrónica de Panamá
  (SFEP) y su obligatoriedad progresiva. SEGÚN FUENTE SECUNDARIA (13, 7).
- **Decreto Ejecutivo 766 de 29 de diciembre de 2020**: normas de adopción y figura del
  Proveedor Autorizado Calificado (PAC). SEGÚN FUENTE OFICIAL (7).
- **Resolución 201-6299 de 2025**, vigente desde el **1 de enero de 2026**: el Facturador
  Gratuito de la DGI solo puede usarlo quien tenga ingresos brutos anuales de hasta
  B/.36,000 **y** emita como máximo 100 documentos al mes; quien supere cualquiera de los dos
  debe contratar un PAC. SEGÚN FUENTE SECUNDARIA (13).
- **PAC vs. Facturador Gratuito**: el PAC recibe el documento del sistema del contribuyente
  (este módulo), lo valida, lo transmite a la DGI y devuelve la **autorización de uso**
  (protocolo) con el CUFE y el QR. El Facturador Gratuito es la aplicación web/móvil de la
  DGI para pequeños contribuyentes y no se integra con Odoo. SEGÚN FUENTE OFICIAL (5) y
  SECUNDARIA (13). Por volumen, D'CASA casi seguro necesita PAC (NO VERIFICADO: depende de
  sus ingresos declarados; confirmarlo con el contador).
- El PAC guarda copia del documento y su autorización por 60 días continuos a disposición
  del emisor y de la DGI. SEGÚN FUENTE SECUNDARIA (búsqueda sobre el DE 766).

### PAC autorizados (listado DGI, fuente 3; leído en el resultado de búsqueda)

| PAC | Resolución |
|---|---|
| Sistema de Producción Desarrollo y Administración STK Panamá, S.A. | 201-9718 |
| The Factory HKA Corp | 201-9719 |
| Electronic Business Intelligence, Corp (EBI) | 201-9721 |
| Hypernova Labs, S.A. | 201-0039 |
| Satcomla S.A. | 201-0040 |
| Gurusoft, S.A. | 201-0528 |
| eMagic S.A. | 201-1305 |
| Infile, S.A. | 201-3670 |
| Digifact Servicios, S.A. | 201-4219 |

También aparecen Soluciones de Punto de Venta S.A., TopManage de Panamá S.A. e Ideati S.A.
(sin número de resolución en el fragmento). **El listado cambia: confirmarlo en la página de la
DGI el día que se contrate.**

## El documento electrónico (rFE)

- Formato **rFE versión 1.00** (`dVerForm = 1.00`), Ficha Técnica V1.00 con la revisión
  vigente desde el 22-04-2025 (nombres de emisor/receptor hasta 200 caracteres, campo de
  «otros gastos», formato de teléfonos B309/B408, correo del receptor hasta 100). SEGÚN
  FUENTE SECUNDARIA (12).
- Esquema: `FE_v1.00.xsd`, dentro de `PS_FE_1.00.zip`. SEGÚN FUENTE OFICIAL (2). **No
  descargado.** Lugar previsto: `addons/dcasa_fe_pa/xsd/FE_v1.00.xsd`; al copiarlo ahí, cada
  documento se valida al generarse (`validacion_xsd`) y se activa el test `test_xsd`.
- Espacio de nombres: `http://dgi-fep.mef.gob.pa`. NO VERIFICADO contra el XSD (un ejemplo
  de terceros usa `http://dgi-fep.mef.gob.pa/wsdl/FeSimple`).
- Firma XMLDSig: la exige el formato; no la hace este módulo. Según el PAC, firma el PAC o
  el emisor con su certificado. Pregunta abierta para el PAC.

Estructura que genera `models/generador.py`:

```
rFE
├─ dVerForm, dId (= CUFE)
├─ gDGen: iAmb, iTpEmis, [dFechaCont, dMotCont], iDoc, dNroDF, dPtoFacDF, dSeg, dFechaEm,
│         iNatOp, iTipoOp, iDest, iFormCAFE, iEntCAFE, dEnvFE, iProGen, [iTipoTranVenta], [dInfEmFE]
│  ├─ gEmis: gRucEmi(dTipoRuc, dRuc, dDV), dNombEm, dSucEm, [dCoordEm], dDirecEm,
│  │         gUbiEm(dCodUbi, dCorreg, dDistr, dProv), dTfnEm*, dCorElectEmi*
│  ├─ gDatRec: iTipoRec, [gRucRec], [dNombRec], [dDirecRec], [gUbiRec], [gIdExt(dIdExt, dPaisExt)],
│  │           dTfnRec*, dCorElectRec*, cPaisRec
│  └─ gDFRef* (notas de crédito 04): gRucEmDFRef, dNombEmRef, dFechaDFRef, gDFRefNum/gDFRefFE/dCUFERef
├─ gItem*: dSecItem, dDescProd, [dCodProd], dCantCodInt, [dCodCPBSabr, dCodCPBScmp],
│          gPrecios(dPrUnit, [dPrUnitDesc], dPrItem, dValTotItem), gITBMSItem(dTasaITBMS, dValITBMS)
└─ gTot: dTotNeto, dTotITBMS, dTotGravado, [dTotDesc], dVTot, dTotRec, dVuelto, iPzPag, dNroItems,
         dVTotItems, gFormaPago*(iFormaPago, [dFormaPagoDesc], dVlrCuota), [gPagPlazo*]
```

- El orden de `gDGen` (salvo `dSeg` e `iTipoTranVenta`) y de los primeros campos de `gItem`
  y `gTot` coincide en dos fuentes independientes (9, 11). SEGÚN FUENTE SECUNDARIA.
- El resto del orden, los nombres de `gDFRef`, `gIdExt`, `gFormaPago` y `gPagPlazo`, y los
  formatos (decimales, teléfonos, fechas) son NO VERIFICADOS hasta validar contra el XSD.
- Fechas: `AAAA-MM-DDThh:mm:ss-05:00` (Panamá no tiene horario de verano). SEGÚN FUENTE
  SECUNDARIA (9, 10, 11).

### CUFE — VERIFICADO

66 caracteres. Se comprobó contra los dos CUFE reales de la fuente 8; el test
`test_cufe_reconstruye_los_reales` arma ambos desde sus campos y obtiene exactamente el mismo
texto, dígito incluido.

```
'FE' + iDoc(2) + dTipoRuc(1) + dRuc rellenado con ceros a la izquierda a 20 + '-' + dDV(2)
     + dSucEm(4) + fecha de emisión AAAAMMDD(8) + dNroDF(10) + dPtoFacDF(3) + iTpEmis(2)
     + iAmb(1) + dSeg(9) + dígito verificador(1)
```

Dígito verificador: Luhn (módulo 10) sobre todo lo anterior **sin** «FE», cambiando cada
carácter no numérico por el segundo dígito de su código ASCII (`-` = 45 → `5`). El emisor
puede calcularlo; si el PAC devuelve otro, manda el del PAC.

### QR — formato VERIFICADO, contenido lo da el PAC

`https://dgi-fep.mef.gob.pa/Consultas/FacturasPorQR?chFE=<CUFE>&iAmb=<1|2>&digestValue=<…>&jwt=<…>`
(producción; en pruebas `dgi-fepst.mef.gob.pa`). `digestValue` sale de la firma y `jwt` de la
DGI: el QR completo lo devuelve el PAC y el módulo lo guarda tal cual. El CAFE (comprobante
auxiliar impreso) lleva CUFE y QR.

### Catálogos (en `models/catalogos.py`)

| Campo | Valores | Estado |
|---|---|---|
| iAmb (ambiente) | 1 producción, 2 pruebas | SEGÚN FUENTE SECUNDARIA; el QR real lleva iAmb=1 |
| iTpEmis (emisión) | 01 previa normal, 02 previa contingencia, 03 posterior normal, 04 posterior contingencia | SEGÚN FUENTE SECUNDARIA |
| iDoc (documento) | 01 factura interna, 02 importación, 03 exportación, 04 NC referente a FE, 05 ND referente a FE, 06 NC genérica, 07 ND genérica, 08 zona franca, 09 reembolso | SEGÚN FUENTE SECUNDARIA (9, 10 coinciden; 10 agrega «10 operación extranjera») |
| iNatOp | 01 venta, 02 exportación, 11 devolución (NC) … | SEGÚN FUENTE SECUNDARIA |
| iTipoRec (receptor) | 01 contribuyente, 02 consumidor final, 03 gobierno, 04 extranjero | SEGÚN FUENTE SECUNDARIA (9, 10) |
| dTipoRuc | 1 natural, 2 jurídico | VERIFICADO (posición en el CUFE) |
| dTasaITBMS | 00 exento, 01 7 %, 02 10 %, 03 15 % | SEGÚN FUENTE SECUNDARIA (9, 10) |
| iFormaPago | 01 crédito, 02 contado/efectivo, 03 tarjeta crédito, 04 tarjeta débito, 05 fidelización, 06 vale, 07 tarjeta regalo, 08 transferencia/ACH, 09 cheque, 99 otro | 01–08 y 99 SEGÚN FUENTE SECUNDARIA; 09 solo en una fuente |
| iPzPag | 1 inmediato, 2 a plazo, 3 mixto | SEGÚN FUENTE SECUNDARIA |
| iFormCAFE / iEntCAFE | 1 sin CAFE, 2 cinta/papel, 3 carta/electrónico | SEGÚN FUENTE SECUNDARIA |
| CPBS (Codificación Panameña de Bienes y Servicios) | 4 dígitos (abreviado: 2) | obligatorio con receptor Gobierno: SEGÚN FUENTE SECUNDARIA (10) |
| Ubicación (dCodUbi) | catálogo de provincia-distrito-corregimiento de la DGI | NO VERIFICADO el formato exacto |

### Contingencia y anulación

- Contingencia: se emite con `iTpEmis = 02`, `dFechaCont` (inicio) y `dMotCont` (15 a 150
  caracteres) y se transmite al volver la conexión. Plazo de **72 horas**: SEGÚN FUENTE
  SECUNDARIA (14), NO VERIFICADO en la norma. El módulo solo **avisa** pasado ese plazo.
- Anulación: evento sobre una FE autorizada, solo si la operación no ocurrió; no se puede
  revertir; anular una venta real puede ser sancionado. SEGÚN FUENTE SECUNDARIA (búsqueda
  sobre la Ficha). Plazo máximo para anular: NO VERIFICADO.
- Notas de crédito: la 04 referencia el CUFE de la FE original; la 06 es genérica.

## Qué hace el módulo `dcasa_fe_pa`

**Apagado por defecto.** Se enciende en Ajustes → Facturación → «Factura electrónica DGI»
(o Ajustes → Empresas → pestaña «Factura electrónica (DGI)»): `l10n_pa_fe_activo` y un PAC en
`l10n_pa_fe_adaptador`. Sin las dos cosas no se valida, no se crea nada y no se imprime nada
nuevo (tests `TestApagado`).

Datos fiscales (todos opcionales mientras esté apagado):

| Dónde | Campos |
|---|---|
| Empresa | tipo de contribuyente, sucursal (4 dígitos, 0000), coordenadas, ubicación DGI, formato y entrega del CAFE, forma de pago por defecto, reintentos, modo contingencia (inicio y motivo), ambiente (pruebas/producción). RUC y DV: los de `dcasa_base`. |
| Cliente | tipo de receptor y de contribuyente (si están vacíos se deducen: extranjero si el país no es Panamá; contribuyente si tiene RUC con DV; si no, consumidor final), ubicación DGI. RUC/cédula y DV: los de `dcasa_base`. |
| Producto | código CPBS (4 dígitos). |
| Impuesto | código DGI de la tasa ITBMS (vacío: se deduce de 0/7/10/15 %). |
| Diario de ventas | punto de facturación (001–999). La numeración DGI (10 dígitos) es propia por punto y tipo de documento, sin huecos y sin reinicio anual (`ir.sequence` *no_gap*). |
| Diario de banco/caja | forma de pago DGI con que se informa un pago hecho por ese diario. |

Flujo:

1. Al **publicar** una factura o nota de crédito de un diario de ventas, se validan los datos
   y, si falta algo, **no se publica** y se lista en español lo que falta (RUC, DV, dirección,
   ubicación, ITBMS por línea, CPBS para Gobierno, moneda USD…).
2. Nace su `dcasa.fe.documento` (número, CUFE, XML) en `por_enviar`, o en `contingencia` si la
   empresa está en modo contingencia.
3. El cron «cola de factura electrónica» (cada 5 min) envía lo pendiente y consulta lo que el
   PAC recibió (`enviado`). Fallo de comunicación: espera creciente (5, 10, 20… hasta 120 min);
   tras N fallos seguidos (6 por defecto) pasa a **contingencia**, se reemite con `iTpEmis=02`
   y se sigue intentando cada hora.
4. `autorizado`: guarda CUFE, QR, protocolo y fecha; la factura impresa de `dcasa_invoice`
   agrega un bloque con QR, número DGI, CUFE, protocolo y la URL de consulta. En contingencia
   imprime el CUFE con la leyenda «pendiente de autorización».
5. `rechazado`: se muestra el error; la factura puede volver a borrador, corregirse y
   publicarse de nuevo (o botón «Regenerar»): se reemite con **el mismo número**.
6. Una factura con documento vivo no vuelve a borrador ni se cancela: se corrige con nota de
   crédito (04, referencia el CUFE) o se **anula ante la DGI** (asistente con motivo); ya
   anulada, Odoo permite cancelarla.

Inmutabilidad: el documento no se borra; número, punto, tipo y factura no cambian; un
autorizado solo pasa a anulado. Cada operación con el PAC queda en `dcasa.fe.intento`, que no
se edita ni se borra.

Seguridad: Facturación y el lector contable solo **leen**; los botones exigen
`account.group_account_invoice` antes de trabajar con sudo (lista blanca en
`dcasa_base/tests/test_superficie_rpc.py`). Los adaptadores de PAC no exponen nada por RPC.

Brian: herramienta de solo lectura `estado_factura_electronica` (en
`dcasa_brian/models/herramientas_fe.py`): conteo por estado y lo que pide atención
(rechazados y contingencias de más de 72 h).

### PAC simulado (pruebas y staging)

`l10n_pa_fe_adaptador = simulado` no sale a internet. Comprueba que el XML se lea y que el
CUFE cuadre, y responde según el parámetro de sistema `dcasa_fe_pa.simulado_modo`:
`autorizar` (por defecto), `rechazar`, `caido` o `pendiente`. Su QR apunta al ambiente de
pruebas de la DGI y dice `SIMULADO`.

### Cómo enchufar un PAC real

```python
# addons/dcasa_fe_pa/models/pac_hka.py   (ejemplo de nombre)
class DcasaFePacHka(models.AbstractModel):
    _name = 'dcasa.fe.pac.hka'
    _inherit = 'dcasa.fe.pac'
    _description = 'PAC The Factory HKA'

    def _enviar(self, documento):      # documento.payload = rFE sin firmar
        ...  # firmar si el contrato lo pide, POST al PAC con timeout
        return {'resultado': 'autorizado', 'cufe': ..., 'qr': ..., 'protocolo': ..., 'fecha': ...,
                'respuesta': texto_crudo}
        # o {'resultado': 'recibido'} (asíncrono), {'resultado': 'rechazado', 'mensaje': ...},
        #   {'resultado': 'error_comunicacion', 'mensaje': ...} (la cola reintenta)
    def _consultar(self, documento): ...
    def _anular(self, documento, motivo): ...   # → {'resultado': 'anulado', 'fecha': ...}
    def _descargar(self, documento, tipo): ...  # 'xml' | 'cafe' → bytes

# y en res.company:
l10n_pa_fe_adaptador = fields.Selection(selection_add=[('hka', 'The Factory HKA')],
                                        ondelete={'hka': 'set null'})
```

- Credenciales del PAC en variables de entorno del contenedor (`DCASA_FE_PAC_USUARIO`,
  `DCASA_FE_PAC_CLAVE`, …), nunca en git ni en la base sin cifrar.
- Si el PAC no recibe el rFE en XML sino su propio JSON (HKA usa su API `Enviar`), el
  adaptador traduce desde el XML o desde `account.move._l10n_pa_fe_datos()`.
- Errores de red o tiempo de espera: cualquier excepción del adaptador se trata como falla de
  comunicación y no tumba la cola.

## Qué falta para encender (con PAC)

1. **Contratar el PAC** y obtener: ambiente de pruebas, credenciales, documentación de su API,
   ejemplos de respuesta (autorizado, rechazado, contingencia, anulación) y si firma él.
2. Descargar el **paquete de esquemas oficial** (`PS_FE_1.00.zip`) desde la fuente 2 y copiar
   `FE_v1.00.xsd` (y sus `include`) en `addons/dcasa_fe_pa/xsd/`; correr los tests y corregir
   el orden/nombres que el XSD marque.
3. Escribir el adaptador real (sección anterior) con sus tests contra respuestas grabadas.
4. Cargar los datos fiscales: ubicación DGI de la empresa (código, corregimiento, distrito,
   provincia), sucursal y punto de facturación; tipo de receptor y ubicación de los clientes
   empresa; forma de pago DGI en cada diario de cobro (Efectivo, Yappy, Tarjeta…).
5. Agregar `dcasa_fe_pa` a `ODOO_MODULES` en `docker/entrypoint.sh` (queda apagado al
   instalarse), probar en staging con el ambiente de pruebas (iAmb=2) y luego producción.
6. Revisar con el PAC/contador si la factura impresa de D'CASA sirve como CAFE o si hay que
   imprimir el CAFE del PAC (`_descargar(..., 'cafe')`).

## Preguntas para la dueña y el contador

1. ¿Los ingresos brutos de D'CASA superan B/.36,000 al año o se emiten más de 100 documentos al
   mes? (Si sí, el PAC es obligatorio desde el 1-1-2026 según la Res. 201-6299.) ¿Hoy se usa
   impresora fiscal o el Facturador Gratuito? ¿Desde qué fecha debe estar emitiendo FE?
2. ¿Qué PAC prefieren (precio por documento, soporte, integración con Odoo)?
3. Código de ubicación DGI del local (provincia-distrito-corregimiento) y si hay más de una
   sucursal o caja (cada caja puede ser un punto de facturación).
4. Forma de pago DGI de **Yappy** (¿08 transferencia o 99 otro?) y de los abonos/apartados.
5. ¿Las facturas a plazo/crédito existen? ¿Se venden productos exentos o al Gobierno (CPBS)?
6. ¿El cliente recibe el comprobante en papel, por correo o por WhatsApp? (iEntCAFE)
7. ¿Se factura en dólares siempre? (El módulo solo emite en USD.)

## Qué pedirle al PAC al contratarlo

- Resolución vigente de la DGI que lo autoriza y SLA (disponibilidad, tiempos de respuesta).
- API (REST/SOAP) con ambiente de pruebas, credenciales, límites y ejemplos; si acepta el rFE
  en XML de la Ficha o solo su formato propio.
- Quién firma el documento (certificado del emisor o del PAC) y cómo se gestiona el certificado.
- Cómo devuelve CUFE, QR, protocolo y fecha de autorización; consulta de estado; anulación
  (plazo máximo); notas de crédito/débito; descarga del XML autorizado y del CAFE en PDF.
- Reglas de contingencia que aplica (plazo, iTpEmis 02 vs 04) y qué hace si su servicio cae.
- Catálogos que valida (ubicaciones, CPBS, formas de pago, unidades) y su versión de la Ficha.
- Conservación de documentos (la norma pide 60 días al PAC; D'CASA debe guardar más tiempo).
- Precio por documento, mínimos y costo de anulaciones/reenvíos.
