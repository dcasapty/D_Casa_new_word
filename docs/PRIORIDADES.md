# Prioridades vigentes

Puesto al día el **2026-10-16**, a partir de la tanda de pedidos que hizo el jefe ese día. Este es el orden en que se
trabaja; cada sesión lo revisa al empezar y lo actualiza al terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). El
documento para leer con la dueña y el jefe (con explicaciones y decisiones) está en Claude Docs: «Plan de mejoras del
jefe» (<https://claude.ai/code/artifact/8ffcbb80-6521-4e46-a2a7-8ddc59cb20b2>). Aquí queda el resumen para quien retome el trabajo.

Cada etapa sale a staging para que la dueña la vea; a producción solo con su «sí» explícito (por cada etapa).

## Lo que solo la dueña y el jefe pueden empezar hoy

Son los trámites largos; empiezan ya aunque el código llegue después.

1. **Verificación del negocio en Meta** (Messenger, Instagram y el plan B de WhatsApp): no se puede acelerar.
2. **Cinco preguntas para la contadora** (ver «Las ~1000 facturas…» en el documento del plan): desbloquean la carga de las
   facturas viejas y el cálculo del costo de ventas.
3. **Qué trae impreso una caja de mueble** (código de barras, referencia, nada): decide cómo el Escáner verifica el
   despacho. Y encender el QR de la nota de entrega (Ajustes › Empresas › Documentos D'CASA).
4. **Decisiones de diseño**: paleta de colores de los íconos del menú, umbral de «stock bajo» (2 o 5), quién ve la
   bitácora de bodega, si la Contabilidad la ve solo Gerencia.

## Orden de trabajo

| # | Etapa | Qué incluye | Depende de |
|---|---|---|---|
| 1 | **Seguridad y control primero** | Cerrar los huecos hallados el 2026-10-16: tope de descuento también para el descuento global y el de importe fijo (y al quitar o cambiar líneas después); fusión de contactos segura; que la Vendedora no ajuste existencias a mano sin motivo; topes de dinero de Brian (#26); permisos de escritura de Conversaciones (#25). Más protecciones: pruebas de humo después de producción, revisión adversarial obligatoria si el cambio toca dinero, permisos, contabilidad o Socios, una prueba por cada hueco, revisión de secretos. **Las pruebas se mantienen completas: no se recortan ni se aceleran a costa de cobertura** | Decisiones 6, 8 y 9 |
| 2 | **Inicio nuevo con utilidad** | Costo guardado al confirmar la venta y ganancia (solo Gerencia); selector Hoy / Semana / Mes / rango; ITBMS claro por mejor práctica contable (ventas, costo y ganancia sin ITBMS; dinero que se mueve con ITBMS; cada etiqueta lo dice y trae el desglose); Cotizaciones y Entregas lado a lado; botones azules (quitar «Nueva factura» y «Ver en el celular»); franja de atención; Estadísticas del negocio; íconos del menú con color; categoría «Envíos — En desarrollo»; **cerrar el hueco del tope de descuento** (el botón Descuento global y de importe fijo no pasa por el tope de la vendedora una vez que existe el producto de descuento; verificado el 2026-10-16) | Costos cargados; paleta de colores |
| 3 | **Clientes y proveedores limpios** (los usuarios y empleados del sistema no se tocan) | Encontrar por qué una misma persona aparece 5 veces al cotizar, con el mismo correo y celular, pese a los candados (el candado no cuenta usuarios, empleados ni direcciones hijas; hay que mirar «Posibles duplicados»); **arreglar la fusión** (Gerencia no tiene permiso para el asistente; no copia los datos de Socios de la ficha que se borra; destino = la más vieja); avisar al cotizar cuando hay otros contactos con el mismo correo o celular y mostrarlos en el selector; buscar antes de crear una ficha desde una conversación o Telegram | Mirar los datos reales |
| 4 | **Bodega** | Escáner › Despachar (QR de la nota → verificar cada artículo); Bitácora de bodega (antes → después, motivo); alertas diarias por Telegram (stock bajo, ajustes grandes, cierre de mes); cerrar el hueco del Inventario físico para la Vendedora | Etiquetas o códigos en cajas; umbral |
| 5 | **Contabilidad propia** | Menú raíz «Contabilidad» (reportes, bancos, cierre de mes), tablero, arqueo de diarios con comprobantes, toma de inventario, ITBMS claro en todos los resúmenes | Respuestas de la contadora |
| 6 | **Conversaciones** | Encender Messenger e Instagram (el código ya existe), probar en staging con mensajes reales; después las ideas de CRM fase 2 que elijan | Meta: verificación, app y tres secretos |
| 7 | **Facturas del sistema anterior** | Informe de cuadre por mes (archivo contra lo cargado); carga en staging con la contadora | Respuesta 1 de la contadora |
| 8 | **Brian sin huecos** | Descuentos (% por línea, global, importe fijo), facturar desde una cotización, fusionar contactos, margen por producto, recibir compras; archivo de cobertura que obligue a que toda función nueva tenga su herramienta | Etapas 2 a 4 |

## Pedidos del jefe del 2026-10-16 y su estado

| Pedido | Estado | Etapa |
|---|---|---|
| Utilidad en el Inicio (Hoy / Semana / Mes con rango) | Por construir | 2 |
| Rediseño del Inicio | Por construir | 2 |
| Contabilidad con menú y tablero propios | Por construir | 5 |
| Que el contexto no se pierda entre sesiones | Hecho (este archivo y `LEEME_PRIMERO.md`) | 0 |
| Estado de los issues y prioridades | Hecho (ver abajo) | 0 |
| Conversaciones: Instagram, Messenger, WhatsApp | Código listo; falta Meta | 6 |
| Error de despacho en bodega (verificar con escáner) | Por construir | 4 |
| Contactos duplicados | Causas probables halladas; la herramienta de fusión tiene dos fallas (permiso y datos de Socios) | 3 |
| ~1000 facturas del sistema anterior | Importador listo; falta la contadora | 7 |
| Alertas de fin de mes y de mercancía agotándose | Por construir | 4 |
| Bitácora de bodega | Por construir | 4 |
| Brian sin limitaciones | Auditado; huecos listados | 8 |
| Menos fallas y más seguridad (la velocidad de las pruebas no es prioridad) | Por construir | 1 |
| Descuentos (por línea, global, importe fijo) | Revisado: por línea y «a todas las líneas» funcionan y respetan el tope; global e importe fijo calculan bien el ITBMS pero se saltan el tope (hueco a cerrar) | 2 |
| ITBMS claro en los resúmenes | Decidido por mejor práctica contable (ver arriba); por construir | 2 y 5 |
| Estadísticas del negocio (menú) | Por construir | 2 |
| Íconos del menú con color | Por construir (falta paleta) | 2 |
| Categoría «Envíos — En desarrollo» | Por construir | 2 |

## Issues abiertos (revisados el 2026-10-16: 16 abiertos, 3 cerrados)

| Issues | Qué son | Prioridad |
|---|---|---|
| #9, #10, #12 | Lectores y etiquetas de códigos de barras: faltan las pruebas con los aparatos y las etiquetas del proveedor | Alta: sin esto el despacho no se puede verificar (etapa 4) |
| #27 | Puerta del equipo: que el personal entre por `/master`; futuro | Media; antes de traspasar el dominio |
| #25 | Conversaciones: permisos de escritura y seguimiento por persona | Media-alta (seguridad, antes de abrir al público) |
| #26 | Brian: topes de dinero (`ajustar_puntos`, `crear_factura`, `ajustar_existencias` sin tope). El tope de gasto de IA ya existe pero de fábrica está en 0, o sea sin tope | Media-alta; poner las cifras |
| #23, #22 | Privacidad (Ley 81): lo que «Eliminar conversación» no borra | Media; antes de abrir al público |
| #24 | Hallazgos de Juan que quedaron para después | Media |
| #15 y sus hijos #16 a #21 | CRM fase 2: seguimiento de cotizaciones sin respuesta (#16), cotizaciones fuera de la conversación (#21), posventa (#18), invitar a la tienda (#17), perder oportunidades (#20), Brian y oportunidades (#19) | Se eligen con la dueña en la etapa 6; #16 y #21 son los de más valor |

Cerrados: #11, #13 y #14 (códigos de barras, conteo con lector, pantalla de bodega).

## Pendientes viejos que siguen en pie

- **#92** (antes de traspasar el dominio): que `/master` funcione y que «Iniciar sesión» de la web no lleve al panel.
- **#97**: por qué el primer despliegue de una versión deja la base sin actualizar.
- Estudio de envíos para La Chorrera: entregado; esperan sus respuestas (ver el documento en Claude Docs).
- Lo que le toca a la dueña: [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md).
