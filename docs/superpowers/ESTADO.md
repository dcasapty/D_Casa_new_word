# Estado del trabajo: ubicación exacta en D'CASA

Rama `claude/ubicacion-dcasa` (desde `main` `d928a82`). Sin PR, sin unir, sin flujos, sin desplegar. Actualizado: 2026-11-27.

## Hecho
- Diseño y plan (`specs/`, `plans/`); módulo `dcasa_ubicacion` y cambios asociados adaptados a D'CASA (chofer, tuteo, marca, sin corredores, retiro en tienda, privacidad, Guía, borde, Juan, puente).
- Documentos: `docs/UBICACION.md`, prioridades, bitácora, contexto agéntico, Brian, Juan, índice. Capturas antes/después en `docs/capturas/ubicacion/` (celular 390 px y computadora, datos de prueba).
- Revisión adversarial independiente hecha y sus 3 hallazgos útiles arreglados con pruebas.

## Probado (resultado real)
- Odoo (`scripts/test.sh`, todos los módulos, etiquetas §5.4): 3.410 pruebas, 2 fallos, ambos de `website_dcasa` y ambos también en `main` (portada a 390 px; texto de ayuda del buscador a 360 px). Todo lo de `dcasa_ubicacion` pasa, con navegador.
- `ruff check addons` limpio. `edge` 321/321, `juan` 2.091 pasan (40 saltadas de origen), `puente-wa` 678/678; typecheck limpio en los tres.
- Compra de ensayo local a 390 y 1280 px.

## No probado
- El mapa real de Google (claves sin crear), la restricción de la clave a las cinco direcciones, staging y producción.
- Las dos pruebas visuales de `website_dcasa` quedan rojas por un problema que ya estaba en `main`.

## Pendiente (no se puede avanzar sin la persona o Gerencia)
- Claves de Google en `dcasa-staging` y luego `dcasa` (nunca por el chat). El «sí» de Gerencia a las capturas. CI a staging (con «sí» explícito) y comprar en staging.
- Volver a medir los km sin corredores (necesita `envios-dcasa.html` y una clave temporal de Routes API): fuera del encargo, anotado en prioridades.
- Decisiones elegidas por mí, reversibles: avisos encendidos como se aprobó; el cambio automático a domicilio no ocurre con un pago abierto; la guardia de Juan deja pasar las frases fijas con ícono.

## Bloqueos
- Ninguno técnico. Esta sesión no puede escribirle a la sesión orquestadora (permiso): este archivo es el canal.

## Siguiente paso
Con el «sí» de la persona: PR (no se abrió) y CI a staging; comprar en staging con las claves puestas.
