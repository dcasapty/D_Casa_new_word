# Inventario del sistema anterior (capturas, 2026-10-02)

7 capturas de Inventario → Productos del Odoo anterior de D'CASA: 535 productos en total.
Columnas: nombre, referencia interna, precio de venta, costo, a la mano, pronosticado.
Suma «A la mano» por página (para verificar la transcripción): 565 · 490 · 627 · 125 · 806 · 832 · 664.

Pendiente (ronda 7): transcribir con doble lectura, cruzar por código con el catálogo actual,
convertir los «COMBO … + COLCHÓN» en el campo combo del producto, existencias negativas → 0 con
aviso, y lista de fotos faltantes para la dueña. La factura del sistema anterior está en
`../factura-sistema-anterior-INV_2026_00858.pdf` (referencia para el rediseño de dcasa_invoice).

## Reglas de la dueña para la carga (2026-10-02, confirmadas)

- La llave es el **código** (referencia interna). Mismo código = mismo producto: solo se actualizan
  existencias (y costo/precio si cambiaron), sin tocar nombre ni fotos. Código nuevo = producto nuevo.
- Mismo nombre con códigos distintos = artículos distintos.
- «A la mano» es el stock.
- Sin código: la llave es el nombre exacto.
- Existencias negativas (8): entran en 0 y se listan para conteo físico.
- «COMBO … + COLCHÓN» (sin código, costo $0): entran como productos **sin publicar** en la web.
- No se importan «Descuento», «Propinas» ni «X COLCHÓN … PARA COMBO» ($0).
- Fotos: las existentes se asignan por código; el resto va a una lista de faltantes (Excel) para la dueña.
