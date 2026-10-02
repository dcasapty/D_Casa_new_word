# Ronda 6 · Brian: qué le falta para ser más potente, inteligente y útil

Agente: `brian` · Fecha: 2026-10-02 · Pedido de la dueña: «revisa qué le falta a Brian para
hacerlo más potente, poderoso, inteligente y útil».

Método: lectura completa de `addons/dcasa_brian` (modelos, controladores, vistas, tests) y de
`docs/BRIAN.md`, cruzada con las auditorías anteriores (`docs/auditoria/brian.md`, ronda 2
`brian-modelos`/`brian-evals`, ronda 3 `brian-habilidades`/`brian-agente`, ronda 4
`brian-historial`) para no repetir lo que ya se cerró. Medición con la suite real en una base
limpia (Odoo 19, PostgreSQL 16 local), sin llamar a ninguna IA: proveedor `prueba` (guion fijo) y
`requests.post` simulado para Anthropic/OpenAI.

## 1. Resumen ejecutivo

1. **La base es sólida y segura**: un catálogo único para chat, Telegram y MCP; todo corre con
   los permisos de la persona; política dura (`politica.py`) con lo prohibido; confirmación
   humana de lo sensible re-verificada al confirmar; auditoría inmutable (`brian.accion`);
   superficie RPC cerrada (Fase 0, `test_superficie_rpc`); lectura de Excel/Word/PDF/fotos;
   importación de catálogo de proveedor con vista previa y deshacer. 114 tests verdes al empezar
   (54,6 s).
2. **Lo que más le faltaba para el día a día** era la mitad «trastienda» de una mueblería:
   **compras a proveedores** (0 herramientas con `purchase` instalado), **qué reponer** (solo
   «existencias bajas» por umbral fijo, sin mirar ventas), **una lista de pendientes del día**,
   **revisar el catálogo incompleto** (sin foto/precio/categoría) y **acciones en bloque** (publicar
   20 productos = 20 confirmaciones). Además, cotizar varios productos costaba un paso por
   producto (límite de 8 pasos por turno).
3. **Lo que más le faltaba para ser barato y medible**: no había **caché de prompts** (cada paso
   del bucle pagaba completas las ~7 600 fichas de herramientas y el sistema), y el **consumo de
   tokens se descartaba**: no se sabía cuánto gasta Brian, ni por quién, ni con qué modelo.
4. **Seguridad ante adjuntos**: la defensa contra inyección era solo «el texto va marcado como
   DATO». Un archivo podía cerrar el bloque escribiendo `<<FIN DE LOS DATOS>>` y, sobre todo, una
   instrucción escondida en una foto o un Excel podía disparar una herramienta de **construcción**
   (crear factura, cambiar precio, crear cliente) sin ningún clic humano.

**Implementado en esta ronda** (sección 4): 7 herramientas nuevas, cotización con varias líneas,
caché de prompts de Anthropic, registro de consumo con costo estimado, confirmación obligatoria
de lo que se construye a partir de adjuntos, neutralización de marcas en adjuntos, tipos tolerantes
para modelos pequeños, errores que enseñan los parámetros correctos, tope de tiempo por turno,
aviso de respuesta cortada, duración en la auditoría y un prompt de sistema más útil.
Resultado de la suite: ver sección 6.

## 2. Inventario (antes de esta ronda)

48 herramientas de negocio (+ 3 de MCP): ventas 10, catálogo 8, clientes 7, contabilidad 12,
usuarios 4, generales 4, importación 3. 19 de lectura, 16 de construcción, 13 sensibles.

| Área de la mueblería | Cobertura | Comentario |
|---|---|---|
| Ventas y cotizaciones | Buena | buscar/ver/crear/editar/confirmar/cancelar, WhatsApp, reporte del día, resumen por periodo. Una línea por llamada. |
| Clientes y socios | Buena | celular como llave, sin duplicar; saldo = suma del libro; ajuste solo por el asistente de Socios (sensible). |
| Inventario | Débil | `existencias_bajas` (umbral fijo) y `ajustar_existencias` (sensible, de a uno). Sin ventas ni entrantes. |
| Reabastecimiento y compras | **Nula** | `purchase` y `purchase_stock` instalados, ninguna herramienta. |
| Productos / fotos / precios | Media | crear/editar de a uno, publicar de a uno. Nadie revisa qué falta (foto, precio, categoría). |
| Importación de catálogo | Muy buena | Excel con fotos, vista previa, aplicar/deshacer con confirmación. No lee la columna de combos. |
| Web | Mínima | publicar/despublicar de a uno. |
| Contabilidad | Buena | 12 herramientas (las extiende el agente de contabilidad). |
| Reportes | Media | reporte del día y de ventas; sin «pendientes», sin compras, sin consumo de IA. |
| Usuarios | Buena | con protección del admin y de uno mismo. |

## 3. Hallazgos

Severidad: A = alto, M = medio, B = bajo. Estado: ✅ hecho en esta ronda · ⏳ en el plan.

### 3.1 Utilidad (herramientas)

| # | Sev | Hallazgo | Estado |
|---|---|---|---|
| U-01 | A | Sin compras: no se puede crear ni consultar un pedido a proveedor. | ✅ `crear_pedido_compra`, `buscar_compras` |
| U-02 | A | «¿Qué pido?» no mira ventas ni lo que viene en camino. | ✅ `sugerir_reabastecimiento` (cálculo visible) |
| U-03 | A | No hay lista de pendientes del día (entregas, cotizaciones dormidas, compras por recibir, vencidas). | ✅ `pendientes_de_hoy` |
| U-04 | M | Nadie detecta productos sin foto, sin precio, sin categoría, sin medidas o sin código. | ✅ `productos_incompletos`; `ver_producto` dice `tiene_foto` |
| U-05 | M | Publicar o retirar muchos productos = una confirmación por producto. | ✅ `publicar_productos_en_bloque` (una tarjeta que lista cuáles y cuáles se saltan) |
| U-06 | M | Cotizar 5 productos = 5 pasos; con 8 pasos por turno, las cotizaciones grandes no caben (H-09 de la ronda 3). | ✅ `lineas` en `crear_cotizacion`/`agregar_linea_cotizacion` |
| U-07 | M | La importación de Excel ignora la columna «Combo» (`dcasa_combo`, que usa Black Weekend). | ⏳ P-04 |
| U-08 | M | Entregas: no se programan ni se marcan desde Brian (solo se cuentan). | ⏳ P-05 |
| U-09 | M | Confirmar/recibir una compra y registrar la factura del proveedor desde la compra. | ⏳ P-05 (sensibles) |
| U-10 | B | `enviar_cotizacion_whatsapp` marca «enviada» aunque nadie abra el enlace (H-04 ronda 3). | ⏳ P-09 |
| U-11 | — | Tope de descuento por precio libre en cotizaciones (H-02 ronda 3). | Ya cerrado por `dcasa_base` (`_dcasa_validar_tope_descuento` revisa `price_unit` como la persona). |

### 3.2 Inteligencia: prompt, contexto y memoria

| # | Sev | Hallazgo | Estado |
|---|---|---|---|
| I-01 | M | El sistema mezclaba fecha/hora, persona y reglas en un solo texto: imposible de cachear. | ✅ `_sistema_fijo()` (cacheable) + parte variable |
| I-02 | M | El prompt no decía cómo trabajar con fotos de facturas, ni «busca antes de crear», ni qué hacer tras un error repetido o una confirmación pendiente, ni la regla de puntos. | ✅ reglas nuevas, cortas |
| I-03 | M | Sin memoria entre conversaciones (preferencias, hechos del negocio, plantillas de proveedor). | ⏳ P-07 (con compuerta de aprobación, diseño ronda 3 §5) |
| I-04 | M | Historial recortado por ventana deslizante: con Sonnet 5.5 editar turnos previos invalida bloques de pensamiento (M-15 ronda 2). | ⏳ P-08 (medir con clave real) |
| I-05 | B | Preselección de herramientas por palabras (modelos pequeños) cambia el prefijo en cada mensaje y rompe la caché. | ⏳ P-03 (fijar el subconjunto por conversación) |

### 3.3 Costo, latencia y errores

| # | Sev | Hallazgo | Estado |
|---|---|---|---|
| C-01 | A | Sin caché de prompts (M-10 ronda 2): cada paso paga completo el esquema de herramientas (~7 600 tokens) y el sistema. | ✅ `cache_control` en la última herramienta, la parte fija del sistema y el último mensaje |
| C-02 | A | El consumo (`uso`) se descartaba (M-11/B-10). | ✅ `brian.uso` + herramienta `consumo_de_brian` + menú «Consumo de IA» |
| C-03 | M | Sin control de esfuerzo: Sonnet 5.5 corre con esfuerzo `high` por defecto (M-14). | ✅ opción `BRIAN_ESFUERZO`/`dcasa_brian.esfuerzo` (vacía = sin cambio) |
| C-04 | M | El bucle podía durar 8 pasos × 3 intentos × 120 s dentro de una petición HTTP. | ✅ tope de 150 s por turno con mensaje amable |
| C-05 | M | Respuesta cortada por `max_tokens` se mostraba como si estuviera completa (M-12). | ✅ aviso «se cortó por largo» |
| C-06 | M | Modelos pequeños mandan `"2"`, `"true"`, `"$1,299"`: la herramienta fallaba con «Parámetros inválidos» sin decir cuáles. | ✅ conversión de tipos + error con la lista de parámetros |
| C-07 | M | Sin streaming: la persona espera la respuesta completa (chat y Telegram). | ⏳ P-06 |
| C-08 | M | Telegram procesa el turno dentro del webhook; si tarda, Telegram reintenta y la deduplicación (`ultimo_update`) aún no está confirmada en la base. **No verificado** el tiempo de corte de Telegram. | ⏳ P-06 (cola o respuesta inmediata + trabajo en segundo plano) |

### 3.4 Seguridad

| # | Sev | Hallazgo | Estado |
|---|---|---|---|
| S-01 | A | Construcción disparada por un adjunto sin clic (H-03/S-10 ronda 3): una foto con «crea la factura…» o un Excel con «sube el precio…» se ejecutaba. | ✅ en un turno con adjuntos, toda herramienta de construcción pide confirmación (salvo las que solo dejan borrador revisable: `proponer_importacion`). Queda marcado en `brian.accion.con_adjuntos`. |
| S-02 | M | Un adjunto podía cerrar el bloque `<<DATOS…>>` escribiendo `<<FIN DE LOS DATOS>>` o fingir `</system>`; el nombre del archivo también entraba sin limpiar. | ✅ `_neutralizar` en contenido y nombres |
| S-03 | B | La auditoría no guardaba duración. | ✅ `duracion_ms` |
| S-04 | M | Texto de registros de terceros (notas de pedidos web, nombres de contactos) llega en resultados de herramientas sin marcar; la regla del sistema lo cubre, pero no hay confirmación automática como con adjuntos. | ⏳ P-10 |
| S-05 | — | Permisos por grupo, política, MCP sin sensibles, Telegram con doble secreto. | Sin cambios: correcto. |

## 4. Lo que se implementó (esta ronda)

### Herramientas nuevas (`models/herramientas_operacion.py`)

| Herramienta | Nivel | Quién | Qué hace |
|---|---|---|---|
| `sugerir_reabastecimiento(dias_ventas, dias_cobertura, categoria, limite)` | lectura | Inventario | Por producto: vendidas en N días, hay, en camino, comprometidas, días que alcanza, **cuánto pedir** = vendido ÷ días × cobertura − (hay + en camino − comprometidas); proveedor y costo si están cargados; devuelve `lineas_para_compra` listas para el siguiente paso. |
| `crear_pedido_compra(proveedor, lineas, referencia)` | construcción | Compras | Solicitud de compra **en borrador** con varias líneas; avisa las que quedaron sin costo. No confirma ni envía. |
| `buscar_compras(texto, estado, limite)` | lectura | Compras | Borradores, confirmadas y por recibir. |
| `pendientes_de_hoy()` | lectura | Interno | Entregas por despachar, cotizaciones sin respuesta hace 7 días, compras por recibir, facturas vencidas, publicados agotados, acciones de Brian por confirmar (cada bloque solo si la persona puede verlo). |
| `productos_incompletos(problema, solo_publicados, limite)` | lectura | Interno | Sin foto, sin precio, sin categoría, sin medidas, sin código: conteos y ejemplos. |
| `publicar_productos_en_bloque(productos, categoria, publicar)` | **sensible** | Gerencia de ventas | Una tarjeta que dice cuántos y cuáles; al publicar se saltan los que no tienen foto o precio (regla de marca: nada sin foto en la tienda). Máx. 200. |
| `consumo_de_brian(periodo)` | lectura | Administrador | Llamadas y tokens por modelo y por persona, % leído de caché y costo estimado con la tarifa pública (modelos sin tarifa: «sin tarifa registrada», nunca inventada). |

Cambiadas: `crear_cotizacion` y `agregar_linea_cotizacion` aceptan `lineas`
(«SOF-001 x 2; MES-003 x 1 @ 99»; si una línea no existe no se crea nada y se listan todas las
que fallan); `ver_producto` dice `tiene_foto`.

### Núcleo

* **Caché de prompts (Anthropic)**: marca `cache_control` en la última herramienta, en la parte
  fija del sistema y en el último bloque del último mensaje (3 de 4 marcas permitidas). La
  fecha/hora, la persona y la pantalla van después de la marca. Se apaga con `dcasa_brian.cache=0`.
  **Estimado** (no medido con clave real): un turno de 3 pasos con ~9 000 tokens de prefijo pasa
  de 27 000 tokens de entrada a ~13 000 equivalentes (−50 %); más si los turnos siguen dentro de 5
  minutos. Se verifica con `consumo_de_brian` («leído de caché»).
* **Consumo** (`brian.uso`): una fila por llamada al modelo, con entrada, salida, caché leída y
  escrita. Solo lectura para administradores; la escribe el sistema; sobrevive al borrado de la
  conversación (como la auditoría).
* **Esfuerzo**: `BRIAN_ESFUERZO` / `dcasa_brian.esfuerzo` (`low`…`max`). Vacío = sin cambio (no
  cambia el comportamiento configurado). Haiku 4.5 no lo recibe (lo rechaza).
* **Adjuntos**: confirmación de lo que se construye en ese turno + neutralización de marcas.
* **Robustez**: tipos tolerantes (`coercer`), errores con los parámetros válidos, tope de 150 s por
  turno, aviso de respuesta cortada, `duracion_ms` y `con_adjuntos` en la auditoría.
* **Prompt**: parte fija con reglas nuevas (buscar antes de crear, fotos de facturas: leer,
  mostrar y preguntar; no insistir tras pedir confirmación; reintentar una vez; puntos solo de las
  herramientas).

## 5. Brechas priorizadas y plan

Impacto (I) y esfuerzo (E): A/M/B.

| # | Qué | I | E | Notas |
|---|---|---|---|---|
| P-01 | **Medir con la clave real** una semana: % de caché, costo por turno, errores por herramienta (con `brian.uso` y `brian.accion`). Decidir esfuerzo y modelo con datos. | A | B | Solo configuración; requiere decisión D-02. |
| P-02 | **Ruteo de modelo**: Haiku 4.5 para consultas cortas, Sonnet 5.5 para fotos/Excel y acciones. | A | M | Diseño en ronda 2 §4.3; la caché es por modelo. |
| P-03 | Fijar el subconjunto de herramientas por conversación (modelos pequeños) para no romper la caché. | M | B | |
| P-04 | Importar **combos** desde el Excel del proveedor (`dcasa_combo`), con aviso si el texto no trae su cifra. | M | M | Mismo patrón que `medidas` en `importacion.py`. |
| P-05 | Compras y entregas completas: `confirmar_compra`, `recibir_compra` (sensibles), `programar_entrega`, `marcar_entregada`, factura de proveedor desde la compra (con el agente de contabilidad). | A | M | |
| P-06 | **Streaming** en el chat y Telegram asíncrono (responder al webhook al instante y trabajar en cola). | M | A | Arregla C-07 y C-08. |
| P-07 | **Memoria con compuerta**: hechos del negocio y plantillas de proveedor aprobadas por gerencia; preferencias personales. Nunca como instrucción del sistema. | A | A | Diseño ronda 3 §5. |
| P-08 | Historial «solo agregar» (sin editar turnos previos) para Sonnet 5.5; compactación en vez de ventana deslizante. | M | M | Probar con clave real. |
| P-09 | `preparar_cotizacion_whatsapp` sin marcar «enviada»; mensajes de cobro y entrega con la voz de marca. | M | B | |
| P-10 | «Turno contaminado» también por texto de terceros en resultados (notas web, correos). | M | M | |
| P-11 | Evals: correr los casos dorados de la ronda 2 contra el proveedor real antes de cambiar de modelo. | A | M | |
| P-12 | Niveles de ayuda por rol configurables (ronda 3 §4). | M | A | |

## 6. Medición

* Suite `dcasa_brian` antes: **114 tests, 0 fallos, 54,6 s** (base limpia).
* Suite después: `dcasa_brian` + `dcasa_base` (incluye `test_superficie_rpc`): **184 tests, 0
  fallos** (83 s); 25 nuevos en `tests/test_ronda6.py`, más el de formato Anthropic actualizado.
* Nota: `sugerir_reabastecimiento` cuenta las ventas que la persona puede ver (corre sin sudo). Con
  el rol Vendedora (ve todas las ventas) cuadra; un usuario «solo mis documentos» vería menos.
* Catálogo: 48 → 55 herramientas de negocio (+7); `crear_cotizacion` sigue con ≤ 5 parámetros de
  tipos simples (contrato para modelos pequeños, `test_contrato_para_modelos_pequenos`).
* No medido (sin clave de IA en este entorno): latencia real, % de caché real, costo real.

## 7. Decisiones que necesita la dueña

* **D-01 Confirmar lo que viene de adjuntos.** Ahora, si mandas una foto o un Excel, todo lo que
  Brian cree o cambie en ese turno (cliente, cotización, factura, precio) pide un clic. Es más
  seguro y un poco más lento. ¿Se queda así? (Recomendado: sí.)
* **D-02 Modelo y esfuerzo.** Sigue Sonnet 5.5 sin tocar el esfuerzo. Propuesta: una semana
  midiendo con `consumo_de_brian` y luego decidir entre `dcasa_brian.esfuerzo=medium` y ruteo
  con Haiku 4.5 para consultas.
* **D-03 Publicar sin foto.** La publicación en bloque se salta los productos sin foto o sin
  precio. ¿Se permite publicar sin foto en algún caso?
* **D-04 Reabastecimiento.** La sugerencia mira 30 días de ventas y cubre 30 días. ¿Otros
  números por categoría (p. ej. colchones vs. salas, o por tiempo de entrega del proveedor)?
* **D-05 Memoria.** ¿Brian puede recordar hechos del negocio entre conversaciones (con tu
  aprobación de cada uno)?
* **D-06 Quién ve el consumo de IA.** Hoy solo administradores. ¿También Gerencia?

## 8. Notas para otros agentes

* **Contabilidad** (`herramientas_contabilidad.py`, no tocado): las herramientas de construcción
  que crean facturas desde una foto ahora piden confirmación cuando el turno trae adjuntos (regla
  general de `registro.py`); no hace falta cambiar nada allá. Para P-05 hará falta `crear_factura`
  de proveedor a partir de un pedido de compra.
* **Factura electrónica** (`herramientas_fe.py`): igual; si alguna herramienta suya solo deja
  borradores revisables, puede marcarse `segura_con_adjuntos=True`.
* **dcasa_base**: sin cambios en `test_superficie_rpc` (no se agregaron métodos públicos).
