# Juan — el panel de conversaciones dentro de Odoo

Especificación de la interfaz que usa el equipo de D'CASA para atender con Juan. Sale de lo que
ya funciona y gusta en el CRM de Baby Caleb (su panel `/admin`: 7.167 líneas, `src/admin/views/`),
**mejorado**, y vive **dentro de Odoo**: un solo inicio de sesión (con la verificación en dos
pasos), un solo cliente (la ficha del contacto), y todo conectado con el catálogo, Socios,
el CRM y la contabilidad.

Es una pantalla propia (acción de cliente OWL) del módulo `dcasa_conversaciones`, con el sistema
de diseño de `dcasa_interfaz` (barra lateral, colores, íconos). Mismo patrón técnico que la
conciliación bancaria de `dcasa_contabilidad`.

## De Baby Caleb a D'CASA (qué se conserva)

| Panel de Baby Caleb | Pantalla en Odoo | Cambio |
|---|---|---|
| Resumen (mensajes de hoy, clientes únicos, resueltas sin humano, costo del mes) | **Resumen** | Mismos indicadores, más: oportunidades creadas, ventas atribuidas (facturas pagadas de clientes que hablaron con el bot), tiempo de primera respuesta. |
| Conversaciones (lista + hilo + pausar/continuar/responder/sugerir) | **Conversaciones** (la pantalla principal) | Lo mismo, más adjuntos, etiquetas, fotos del catálogo, respuestas rápidas, notas internas, búsqueda. Abajo. |
| Leads | **Oportunidades** (CRM de Odoo) | Ya existe: el interés se vuelve `crm.lead`; el panel muestra el enlace y el estado. |
| Tickets | Actividades de Odoo | «Pasar a vendedora» crea una actividad con fecha; no hay otro sistema de tickets. |
| Conocimiento (KB) | **Conocimiento del bot** | Mismo flujo: título + contenido; sin vectores (búsqueda por palabras). |
| Mejoras (sugerencias + lecciones) | **Preguntas sin respuesta** + **Lecciones** | Lo que el bot no supo se agrupa; con un botón la dueña lo convierte en conocimiento o lección. |
| Costos | **Costos de IA** | Gasto del mes, tope, proyección «terminarás el mes en…», por modelo y por día. |
| Conexiones (QR, Telegram, Meta, diagnóstico) | **Conexiones** | Estado de cada canal en vivo; QR para vincular; botón «Reiniciar» y «Desvincular» con confirmación; qué clave falta (solo el nombre). |
| Campañas | **No en la Fase 1** | Las masivas quedan fuera a propósito (riesgo de bloqueo del número). |
| Flujo/agente (canvas) | Herramientas activas | Un interruptor por herramienta del bot; el flujo es fijo. |

## Pantalla «Conversaciones» (lo central)

Tres columnas en escritorio, una a la vez en celular (las vendedoras la usarán en el teléfono):

1. **Lista** (izquierda): foto o iniciales, nombre, canal (ícono), último mensaje, hora, etiqueta
   de estado (Bot / Una vendedora / Cerrada / Necesita atención), contador de no leídos, punto
   verde si el bot está atendiendo. Filtros: canal, estado, etiqueta, asignada a mí, sin leer,
   con oportunidad. Búsqueda por nombre, celular o texto. Paginada de 30 en 30 con carga al bajar.
2. **Hilo** (centro): burbujas con hora y autor (cliente / el bot / vendedora con su nombre),
   fotos y documentos dentro del hilo (miniatura, clic para ampliar, descarga), notas internas
   con otro color (el cliente nunca las ve), avisos del sistema («el bot pasó la conversación a
   una vendedora», «se creó la oportunidad»), indicador «escribiendo». Tiempo real con el bus de Odoo.
3. **Ficha** (derecha): cliente (con enlace a su contacto), si es Socio y su saldo de puntos (solo
   lectura), oportunidades abiertas, compras recientes, etiquetas, asignación, notas y «Qué sabe
   el bot de esta persona».

**Caja de respuesta** (la mejora principal):

- **Atender / Devolver al bot**: «Atender» pausa al bot (con vencimiento visible); «Devolver»
  pide una nota opcional para el bot. Si una vendedora escribe desde el teléfono, el panel lo
  muestra y el bot calla.
- **Adjuntar**: foto, documento (PDF, Word, Excel) o varios a la vez, arrastrando, con vista
  previa y límite de tamaño; se envía por el canal como imagen o documento.
- **Foto del catálogo**: botón que abre un buscador de productos (nombre o código, con foto,
  precio «+ ITBMS» y disponibilidad); al elegir, manda la foto con un pie armado (nombre, precio
  + ITBMS, medidas, enlace). Varias fotos del mismo producto (galería) con un clic.
- **Cotización en PDF**: botón que genera la cotización de Odoo del cliente (o crea una borrador
  con líneas del catálogo) y la envía como documento.
- **Respuestas rápidas**: atajos con `/` (p. ej. `/horario`, `/ubicacion`, `/socios`) que la dueña
  edita en un menú; admiten el nombre del cliente.
- **Respuesta sugerida por IA**: botón «Sugerir» que redacta un borrador para la vendedora, con
  el contexto de la conversación y las mismas reglas de marca (la vendedora lo edita y envía).
- **Etiquetas**: de colores, creadas por la dueña («Apartado», «Pidió precio», «Comprobante
  recibido», «Entrega»…); el bot también etiqueta según lo que entiende.
- **Notas internas**: entre vendedoras, con mención (@) y actividad opcional.
- **Comprobantes de pago**: llegan marcados («Comprobante: lo revisa una vendedora»), nunca se
  le muestran a la IA; con un botón se adjuntan a la factura o al pedido.
- **Mensajes programados** y **seguimiento** visibles: «Seguimiento 1 pendiente para el
  jueves 8:00 a. m.», con opción de cancelarlo.

## Rendimiento y calidad

- Cargar la lista en menos de 1 s con 5.000 conversaciones (índices, paginación, sin cargar hilos
  completos): el hilo se trae por tramos de 50 mensajes, hacia atrás.
- Imágenes: miniaturas WebP al ancho justo (el mismo servicio `/dcasa/img` del sitio), carga
  diferida; documentos solo al abrirlos.
- Tiempo real con el bus de Odoo (un solo canal por usuario), sin sondeo.
- Funciona en celular (390 px) y con el pulgar: botones de al menos 44 px, caja de respuesta fija
  abajo, la lista y el hilo como pantallas separadas.
- Accesible (teclado, foco visible, etiquetas), sin degradados ni sombras dramáticas (regla de
  marca: azul `#1340B1`, amarillo `#FED00F` nunca sobre blanco).
- Pruebas: de modelo (rápidas), de controladores y de interfaz con Chrome (como las demás
  pantallas OWL del repo) y contrato visual en celular y escritorio.

## Lo que el bot sabe de cada cliente (para la ficha)

Nombre, celular, canal, si es Socio, productos por los que preguntó, oportunidad abierta, etiquetas,
última vez que habló y si hay seguimiento pendiente. Nada de saldos con detalle ni de datos de
otros clientes.
