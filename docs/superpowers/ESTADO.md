# Estado del trabajo: ubicación exacta en D'CASA

Rama `claude/ubicacion-dcasa` (desde `main` `d928a82`). Sin PR, sin unir, sin flujos, sin desplegar. Actualizado: 2026-11-27 (madrugada).

## Hecho
- Diseño aprobado y plan: `specs/2026-11-26-ubicacion-dcasa-diseno.md`, `plans/2026-11-26-ubicacion-dcasa-plan.md`.
- Módulo `addons/dcasa_ubicacion` y cambios asociados copiados de Baby Caleb (sin `dcasa_correo`, sin `dcasa_envios`, sin dominios ni marca de Baby Caleb).
  `dcasa_ubicacion` no necesita el punto de salida propio ni el límite de km de `dcasa_envios` (solo usa lugares, tarifa, promoción, buscador y límite por IP, que D'CASA ya tiene).
- «chofer» en vez de «motorizado», sin ícono de moto; «cliente» en vez de «clienta»; enlaces de WhatsApp `api.whatsapp.com/send`.
- Retiro en tienda: al marcar la casa en el mapa se elige sola la entrega a domicilio (`_dcasa_ubic_elegir_domicilio`), con prueba.
- Privacidad (línea en la política), Guía (6 entradas, una de «Ruta sin corredores»), `docker/entrypoint.sh`.
- Juan: la guardia sin emojis conserva los íconos de las frases escritas por Odoo (con pruebas).
- Borde y puente: sin errores de tipos; pruebas verdes tras copiar (borde 321, puente 678).

## En curso
- Dos ayudantes pasan los textos de usted a tú (Odoo: `addons/dcasa_ubicacion`; Juan/puente/borde) y agregan «Ruta sin corredores» en la página del chofer.

## Probado (resultado real)
- `juan`: salvaguardas 132/132; `puente-wa` 678/678 y tsc limpio; `edge` 321/321 y tsc limpio (antes del paso de voz).
- Odoo: aún no corrido (entorno listo: Python 3.12 venv, PostgreSQL, Odoo 19 submódulo).

## No probado / pendiente
- Mapa real de Google y claves (`GOOGLE_MAPS_CLAVE_NAVEGADOR`, `GOOGLE_MAPS_CLAVE_SERVIDOR`): se crean después; PENDIENTE.
- Volver a medir los km sin corredores (necesita `envios-dcasa.html` de Gerencia y clave temporal de Routes API): PENDIENTE, fuera del encargo.
- Capturas antes/después, compra de ensayo a 390 px, `scripts/test.sh` completo, `ruff`, revisión adversarial.

## Bloqueos
- Ninguno. Mensajes a la otra sesión no salen (sin permiso de esta sesión para escribirle).

## Siguiente paso
Pruebas completas de Odoo (todos los módulos y etiquetas de la guía §5.4), ruff, compra de ensayo, capturas, documentos y bitácora, revisión adversarial.
