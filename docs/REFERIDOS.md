# Programa de referidos (`dcasa_referral`)

> Versión inicial hecha a partir de la factura real y del flujo de venta de D'CASA.
> **Falta alinear con el repositorio `abrinay1997-stack/DCasa-Referidos`** (privado,
> sin acceso). El módulo es configurable para ajustar reglas sin reescribirlo.

## Cómo funciona

1. **Código**: cada cliente puede tener un código tipo `DC7K3M9Q` (sin 0/O ni 1/I
   para dictarlo por WhatsApp sin errores). Se genera desde la ficha del cliente
   (pestaña *Referidos*) o el cliente lo genera en su portal (`/my/referidos`).
2. **Link**: `https://dcasapty.com/r/DC7K3M9Q` (o cualquier URL con `?ref=DC7K3M9Q`)
   guarda el código en la sesión; el carrito web queda asignado a ese referidor.
3. **Tienda física / WhatsApp**: en la orden de venta, campo **Referido por**:
   se escribe el código o el nombre.
4. La **primera venta confirmada** fija el referidor del cliente; sus compras
   siguientes lo heredan.
5. **Recompensa** (Ventas → Referidos → Recompensas):

| Evento de la factura del referido | Estado de la recompensa |
|---|---|
| Se publica | Pendiente de pago |
| Queda pagada (o en proceso de pago) | **Ganada** — se le debe al referidor |
| Se anula o se revierte con nota de crédito | Anulada |
| La gerente marca «Marcar como pagada» | Pagada al referidor (con fecha y nota) |

## Reglas y configuración

Ventas → Configuración → Ajustes → *Programa de referidos*:

- **Tipo**: porcentaje del subtotal **sin ITBMS** (por defecto **5 %**) o monto fijo.
- **Compra mínima** para generar recompensa.
- **Solo la primera compra** de cada referido.

Siempre: nadie se refiere a sí mismo, dos clientes no pueden referirse
mutuamente, una factura genera como máximo una recompensa, las notas de crédito
no generan recompensa.

Ejemplo (factura INV/2026/00821): subtotal $329,99 → recompensa 5 % = **$16,50**.

## Permisos

- Vendedoras: ven recompensas y asignan referidor en la venta.
- Gerente de ventas: marca recompensas como pagadas o deshace el pago.
- Clientes (portal): ven solo sus propias recompensas.

## Por definir con Abrinay / D'CASA

- Porcentaje o monto definitivo y si hay tope.
- ¿El referido también recibe beneficio (descuento en su primera compra)? Se puede
  resolver con un programa de *Promociones* de Odoo ligado al código.
- Forma de pago al referidor (efectivo, transferencia, crédito en tienda).
