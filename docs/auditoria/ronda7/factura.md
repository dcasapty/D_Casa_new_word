# Ronda 7 — Factura impresa (`dcasa_invoice`)

Fecha: 2026-10-03. Rediseño del reporte de factura, cotización y pedido tomando como
referencia `up media/factura-sistema-anterior-INV_2026_00858.pdf`. **Nada se desplegó.**

## Muestras (datos ficticios, generadas en una base de prueba)

| Archivo | Qué enseña |
| --- | --- |
| `factura-muestra-completa.pdf` / `.html` / `.webp` | Cliente con RUC y DV, teléfono, correo, dirección de facturación y de entrega; fechas, pedido, vendedora, condiciones y medio de pago; código en su columna; descuento; bloque **Flete y envío**; abono parcial, pagado y por pagar; total en letras; invitación a Socios D'CASA con el código de la socia que invitó. |
| `factura-muestra-socia-pagada.pdf` / `.html` / `.webp` | Socia que paga completo: «Pagada el …», código de socio, puntos de esta compra, saldo, línea «Premio Socios D'CASA» y el premio cobrado. |
| `factura-muestra-con-textos-de-la-empresa.pdf` / `.html` | La misma factura con los tres textos de la empresa puestos como **marcadores** («PENDIENTE DE REDACTAR POR LA DUEÑA…»): muestra dónde caen Garantía, Cambios y devoluciones y Términos. En producción están vacíos y no se imprimen. |
| `cotizacion-muestra.html` | La cotización comparte rejilla, columna de código y bloque de flete. |

Los nombres, cédulas, teléfonos, precios y puntos de las muestras son inventados a propósito y
dicen «(datos ficticios)». Las cifras de Socios salen del libro (`dcasa.movimiento`) y de
`puntos.json`, no están escritas a mano.

El PDF se generó con wkhtmltopdf **0.12.6.1 (Qt parchado)**: el paquete `wkhtmltopdf` de Ubuntu
(Qt sin parchar) ignora `--header-html` y `--footer-html`, y la factura sale sin cabecera ni pie.
El contenedor de producción debe llevar la versión parchada (es la que Odoo recomienda).

## Lo que la dueña tiene que redactar (hoy está vacío y no se imprime)

En **Ajustes → Empresas → D'CASA Panamá → pestaña «Documentos D'CASA»**:

1. **Garantía (factura)** — cuánto dura la garantía de cada tipo de producto y qué cubre.
2. **Cambios y devoluciones (factura)** — en qué plazo y en qué condiciones se cambia un
   producto (empaque, factura, estado).
3. **Términos (factura)** — condiciones de apartado, entrega y pago (por ejemplo, qué pasa con
   un apartado que no se completa, cuándo y dónde se entrega el flete).

Y, aparte de la factura:

4. **Términos y condiciones de la empresa** (`https://dcasapty.com/terms`): hoy el enlace
   sale al pie de la factura porque Odoo lo trae por defecto; la página tiene que existir y
   decir lo que ella decida.
5. **Lema del pie** (`Tu casa, bien amueblada.` en Ajustes → Empresas → «Lema del reporte»):
   confirmar o cambiar.

Mientras estos campos estén vacíos la factura no inventa nada: el bloque simplemente no sale.
