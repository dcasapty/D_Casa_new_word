# Plan de trabajo: ubicación exacta y envíos en D'CASA

Diseño aprobado: [../specs/2026-11-26-ubicacion-dcasa-diseno.md](../specs/2026-11-26-ubicacion-dcasa-diseno.md).
Fuente (solo lectura): `System-Baby-Cale`, cambios `34c81a0^..` de su `main` (a 2026-11-27: `277852bf`), que son los de la
guía más los commits posteriores (punto de salida, dominio) que **no** se traen.

## Método

1. Clasificar cada archivo que Baby Caleb cambió: **nuevo** (se copia), **igual al de D'CASA antes del trabajo** (se copia lo
   que quedó), **distinto en D'CASA** (se aplica solo el diff de la ubicación con `patch`, y lo que no entre se hace a mano).
2. No se trae: `dcasa_correo`, `docker/negocio.env`, `edge/wrangler.jsonc`, dominios de Baby Caleb, `docs/BABY_CALEB.md`,
   y **todo `dcasa_envios`** (punto de salida propio y límite de km). `dcasa_ubicacion` no lee el punto de salida ni el
   límite: solo usa lugares, tarifa, promoción, buscador, choferes (límite por IP) y `set_delivery_line`, que D'CASA ya tiene.
3. Adaptar: «chofer» (nada de moto), «Ruta sin corredores» sin afirmar que Waze/Google evitan peajes, marca D'CASA, tuteo,
   retiro en tienda, privacidad, Guía, claves de Google con las cinco direcciones.
4. Pruebas: ajustar los textos que fijan pruebas (nunca saltarlas).

## Pasos (con commit y push después de cada uno)

1. Documentos de diseño y plan.
2. Módulo `dcasa_ubicacion` + `dcasa_base/whatsapp.py` + auditoría tapada de Brian + autor «bot» + enlaces de WhatsApp.
3. Archivos distintos de Odoo (Brian tienda, conversaciones, website, guía, privacidad, entrypoint, pruebas de superficie RPC).
4. Adaptación de voz y marca (chofer, sin corredores, tuteo, colores) y retiro en tienda → a domicilio al marcar la casa.
5. Borde (`edge/`), Juan (`juan/`) y puente (`puente-wa/`) con sus pruebas.
6. Pruebas de Odoo con todos los módulos y las etiquetas de la guía §5.4; `ruff`; `npm test` y `typecheck` en los tres.
7. Compra de ensayo local a 390 px y capturas antes/después (computadora y celular, datos de prueba).
8. Documentos: `docs/UBICACION.md` (adaptado), Guía, privacidad, `PRIORIDADES.md` (incluye volver a medir km sin corredores),
   bitácora de `LEEME_PRIMERO.md`, `CONTEXTO_AGENTICO.md`.

## Qué no se puede probar sin las claves de Google

El mapa real (carga con la clave restringida, `gm_authFailure`, geocodificación inversa de la calle) y el cambio de las
direcciones de la restricción. Con el código se prueba que sin claves todo sigue funcionando. Queda anotado como «no probado».
