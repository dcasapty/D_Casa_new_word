# Diseño aprobado: ubicación exacta y envíos en D'CASA (Fase 1)

Aprobado por la persona responsable el **2026-11-26**. Origen: el módulo `dcasa_ubicacion` de Baby Caleb
(`juanarrietabusiness-pixel/System-Baby-Cale`, plan en su `docs/UBICACION_PARA_DCASA.md`, diseño en su `docs/UBICACION.md`).
Meta de la fase: dejar D'CASA al nivel de Baby Caleb en ubicación y envíos, para cerrar la brecha de envíos inexactos.

## Enfoque

Copiar el módulo y aplicar los cambios asociados **archivo por archivo** (con `git diff 34c81a0^ <final>` de Baby Caleb para
los archivos que en D'CASA son distintos). Se descartó copiar Baby Caleb encima y repetir su historial.
Rama: `claude/ubicacion-dcasa`, desde `main` de D'CASA (`d928a82`).

## Decisiones aprobadas

1. **Privacidad.** Se guarda el punto exacto de la casa (cambia la regla del issue #25). Se agrega la línea a la política de
   privacidad. El modelo de IA **no** recibe el punto; Google sí (mapa y búsqueda de dirección).
2. **Chofer, no motorizado.** D'CASA no trabaja con motorizados: todos los textos dicen «chofer», sin ícono ni palabra de moto.
3. **Sin corredores.** Los choferes no usan corredores (autopistas de peaje). **No se afirma** que los enlaces de Waze o Google Maps
   evitan peajes (no se confirmó): cada chofer activa «Evitar peajes» en su teléfono, la página del chofer muestra «Ruta sin
   corredores» y la Guía lo explica.
4. **Avisos encendidos:** pedir la ubicación al confirmar una venta a domicilio y «Sale hoy».
5. **Retiro en tienda.** Si el cliente marca su casa, se elige solo el envío a domicilio. «Retiro en tienda» sigue disponible y
   no pide mapa ni saca QR.
6. **Marca de D'CASA**: azul `#1340B1`, amarillo `#FED00F` (nunca sobre blanco), Anton/Oswald/Inter, plano, tuteo, ITBMS,
   tienda física. Nada de la marca ni de `docker/negocio.env` de Baby Caleb. Tampoco `dcasa_correo` de Baby Caleb.
7. **Claves de Google:** `GOOGLE_MAPS_CLAVE_NAVEGADOR` y `GOOGLE_MAPS_CLAVE_SERVIDOR`, guardadas solo en el Worker
   `dcasa-staging` (y luego `dcasa`), nunca por el chat ni en el repositorio. La restricción de la clave del navegador lleva:
   `dcasapty.com/*`, `www.dcasapty.com/*`, `staging.dcasapty.com/*`, `dcasa.dcasapty.workers.dev/*` y
   `dcasa-staging.dcasapty.workers.dev/*` (la guía de Baby Caleb olvidaba las dos últimas). **Sin claves todo sigue funcionando**
   (GPS, buscador de barriadas, dirección escrita), sin mapa para afinar el pin.
   *Actualización 2026-11-27:* las claves se crean más tarde; todo lo que dependa del mapa real queda «no probado».

## Fuera de este encargo

- Volver a medir los km de la tabla sin corredores (la actual se midió en carro, por corredores): necesita el archivo
  `envios-dcasa.html` de Gerencia y una clave temporal de Routes API (método en `docs/ENVIOS.md` de Baby Caleb, «Medir el
  archivo para otro punto de salida»). Queda anotado en `PRIORIDADES.md`.
- No se cambian precios ni se aprueba la tarifa (hoy «en revisión»: el mapa dirá «por cotizar»).
- `dcasa_envios` de Baby Caleb cambió después de la guía (punto de salida propio, límite de km): no se trae salvo que
  `dcasa_ubicacion` lo necesite (ver el plan).

## Límites

Sin PR a `main`, sin unir, sin lanzar flujos de GitHub, sin desplegar a staging ni producción sin un «sí» explícito en el chat;
antes de staging, capturas antes/después (computadora y celular, datos de prueba) para Gerencia. El repositorio es público:
ni claves, ni datos de personas, ni el archivo de envíos.

## Hecho significa

Módulo portado y adaptado; pruebas de la guía §5.4 (`scripts/test.sh` con todos los módulos y las etiquetas indicadas,
`ruff check addons`, `npm test && npm run typecheck` en `edge/`, `juan/`, `puente-wa/`); compra de ensayo local a 390 px;
capturas listas; documentos y bitácora al día; rama subida. Se dice con claridad qué no se pudo probar.
