# Capturas antes / después: ubicación exacta de entrega

Para Gerencia (2026-11-27). **Datos de prueba** (cliente «Ana Prueba», un «Sofá de prueba», lugares inventados con precios de juguete);
nada de personas ni de la tabla real de envíos. Hechas en una copia local, a 390 px (celular) y 1280 px (computadora).
**Sin las claves de Google**: el mapa no sale (el cliente usa «Mi ubicación», el buscador de barriadas o escribe la dirección);
con las claves se agrega el mapa con el pin. La tarifa real sigue «en revisión»: en un sistema real el mapa diría «por cotizar».
En estas capturas el envío sale «Gratis» en el método de entrega por la promoción de ejemplo del archivo de prueba.

| Pantalla | Antes (hoy en producción) | Después |
|---|---|---|
| Dirección: bloque nuevo «¿Dónde te entregamos?» | `antes-*-2-direccion`, `antes-*-3-bloque-inicial` | `despues-*-2-direccion`, `despues-*-3-bloque-inicial` |
| Marcar la casa con «Mi ubicación» (zona y envío sale solo) | `antes-*-4-formulario-lleno` (solo escribir) | `despues-*-4-con-ubicacion` |
| «Sí, aquí es» y el número de casa | — | `despues-*-5-confirmada` |
| Método de entrega: se elige solo «Entrega a domicilio»; «Retiro en tienda» sigue ahí | `antes-*-6-metodo-de-entrega` | `despues-*-6-metodo-de-entrega` |
| Página del chofer (el QR del comprobante): «Ruta sin corredores», Waze, Google Maps, quién recibe | — | `despues-*-7-pagina-del-chofer` |
| Enlace que se manda por el chat | — | `despues-*-8-enlace-del-cliente` |
| Venta en el panel (botón «Ruta del chofer», avisos) | — | `despues-pc-9-venta-panel` |
| Ficha del cliente, pestaña «Ubicación de entrega» | — | `despues-pc-10-ficha-cliente` |

`*` = `cel` (celular) o `pc` (computadora). Colores de la marca (azul `#1340B1`, amarillo `#FED00F` solo sobre azul), Anton, Oswald e Inter, diseño plano.
