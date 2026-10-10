// Un Odoo de mentira que cumple el contrato de docs/JUAN.md y registra todo lo que se le pide.
import type { CanalId } from "../../src/canales/tipos";
import {
  OdooError,
  type CuerpoMensaje,
  type CuerpoSeguimientoHecho,
  type DefHerramienta,
  type EstadoOdoo,
  type OdooApi,
  type RespuestaMensaje,
  type ResultadoHerramienta,
} from "../../src/odoo/cliente";

/** Odoo contestó 422 con una explicación pensada para el modelo (lo que lanza un `BrianError`). */
export class RechazoDeOdoo extends Error {}

const objeto = (propiedades: Record<string, unknown>, requeridas: string[] = []) => ({ type: "object", properties: propiedades, required: requeridas });
const texto = (description: string) => ({ type: "string", description });

export const HERRAMIENTAS_DE_PRUEBA: DefHerramienta[] = [
  { nombre: "buscar_productos", descripcion: "Busca productos publicados por nombre, medida o categoría.", parametros: objeto({ consulta: texto("Qué busca"), categoria: texto("Categoría"), limite: { type: "number" } }, ["consulta"]) },
  { nombre: "ver_producto", descripcion: "Detalle de un producto por código.", parametros: objeto({ codigo: texto("Código") }, ["codigo"]) },
  { nombre: "listar_categorias", descripcion: "Categorías públicas.", parametros: objeto({}) },
  { nombre: "reglas_socios", descripcion: "Reglas del programa Socios D'CASA.", parametros: objeto({}) },
  { nombre: "horario_y_tienda", descripcion: "Dirección, horario y WhatsApp.", parametros: objeto({}) },
  { nombre: "saldo_puntos", descripcion: "Saldo de puntos de un socio (con PIN).", parametros: objeto({ celular: texto("Celular"), pin: texto("PIN") }, ["celular", "pin"]) },
  { nombre: "crear_oportunidad", descripcion: "Registra una oportunidad para las vendedoras.", parametros: objeto({ resumen: texto("Resumen"), interes: texto("Interés"), presupuesto: { type: "number" }, zona: texto("Zona de entrega"), cuando: texto("Para cuándo") }, ["resumen"]) },
  { nombre: "anotar_conversacion", descripcion: "Nota interna.", parametros: objeto({ nota: texto("Nota") }, ["nota"]) },
  { nombre: "pasar_a_vendedora", descripcion: "Pasa la conversación a una vendedora.", parametros: objeto({ motivo: texto("Motivo"), urgencia: { type: "string", enum: ["normal", "alta"] } }, ["motivo"]) },
  { nombre: "buscar_conocimiento", descripcion: "Busca en la base de conocimiento de la tienda (políticas, garantía, pagos...).", parametros: objeto({ consulta: texto("La pregunta") }, ["consulta"]) },
  {
    nombre: "cotizar",
    descripcion: "Arma la cotización del cliente y deja listo el PDF.",
    parametros: objeto({ lineas: { type: "array", items: objeto({ codigo: texto("Código"), cantidad: { type: "integer" }, opcion: texto("Tamaño o color") }, ["codigo"]) } }, ["lineas"]),
  },
  { nombre: "registrar_pregunta_sin_respuesta", descripcion: "Deja anotada una pregunta que la base de conocimiento no supo contestar.", parametros: objeto({ pregunta: texto("Lo que preguntó el cliente"), resumen: texto("Resumen") }, ["pregunta"]) },
];

/** La base de conocimiento de prueba: cada entrada responde a ciertas palabras. */
export const CONOCIMIENTO = [
  { titulo: "Garantía y cambios", texto: "Los cambios se aceptan dentro de 8 días con la factura y el producto sin uso.", score: 0.82, palabras: ["garantia", "cambio", "cambios", "devolucion", "devolver"] },
  { titulo: "Formas de pago", texto: "Aceptamos efectivo, Yappy, transferencia y tarjeta.", score: 0.77, palabras: ["pago", "pagar", "yappy", "tarjeta", "efectivo", "transferencia"] },
];

export const CATALOGO = [
  { codigo: "CAMA-Q-001", nombre: "Cama Queen Milán", precio: 499, mas_itbms: true, disponibilidad: "disponible", medidas: "160 x 200 cm", url: "/shop/cama-queen-milan", foto: "/web/image/product.template/1/image_1024" },
  { codigo: "SOFA-3P-002", nombre: "Sofá de 3 puestos Roma", precio: 799.5, mas_itbms: true, disponibilidad: "pocas", medidas: "210 x 90 cm", url: "/shop/sofa-roma", foto: "https://dcasapty.com/web/image/product.template/2/image_1024" },
  { codigo: "MESA-C-003", nombre: "Mesa de centro Nórdica", precio: 129, mas_itbms: true, disponibilidad: "agotado", medidas: "100 x 60 cm", url: "/shop/mesa-nordica", foto: "/web/image/product.template/3/image_1024" },
];

/** Odoo siempre manda `nota_para_el_bot` en /mensaje y /estado (`null` si no hay). */
export const ESTADO_INICIAL = { estado: "bot", bot_activo: true, pausada_hasta: null as string | number | null, dentro_de_horario: true, nota_para_el_bot: null as string | null };

type Manejador = (args: Record<string, unknown>, odoo: OdooFalso) => unknown;

const MANEJADORES: Record<string, Manejador> = {
  buscar_productos: (a) => {
    const q = String(a.consulta ?? "").toLowerCase();
    const productos = CATALOGO.filter((p) => !q || p.nombre.toLowerCase().includes(q) || p.codigo.toLowerCase().includes(q) || q.includes("cama") && p.nombre.includes("Cama"));
    return { productos: productos.map(({ foto, ...p }) => ({ ...p, foto })) };
  },
  ver_producto: (a) => {
    const p = CATALOGO.find((x) => x.codigo === String(a.codigo));
    if (!p) throw new Error("producto no encontrado");
    return { producto: { ...p, descripcion: "Estructura de madera maciza.", galeria: [p.foto] } };
  },
  listar_categorias: () => ({ categorias: ["Camas", "Sofás", "Comedores"] }),
  reglas_socios: () => ({
    texto: "Ganas 1 punto por cada dólar pagado. Compra mínima de $20. 100 puntos equivalen a $1. El canje mínimo es de 500 puntos.",
    puntos_por_dolar: 1,
    compra_minima_usd: 20,
    puntos_por_dolar_de_descuento: 100,
    canje_minimo_puntos: 500,
  }),
  horario_y_tienda: () => ({
    direccion: "Frente al Parque Libertadores, diagonal a la Discoteca Seven, La Chorrera, Panamá Oeste",
    horario: "8:00 a. m. a 5:00 p. m., todos los días",
    whatsapp: "+507 6026-1919",
  }),
  saldo_puntos: (a) => {
    if (a.pin !== "1234") throw new Error("PIN inválido");
    return { saldo_puntos: 1250 };
  },
  crear_oportunidad: () => ({ oportunidad_id: 301 }),
  anotar_conversacion: () => ({ ok: true }),
  buscar_conocimiento: (a) => {
    const q = String(a.consulta ?? "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
    const hallados = CONOCIMIENTO.filter((c) => c.palabras.some((p) => q.includes(p)));
    return { resultados: hallados.map(({ titulo, texto, score }) => ({ titulo, texto, score })) };
  },
  cotizar: (a, odoo) => {
    // Como Odoo (`_juan_cotizar`): apagada = un «no» con el motivo; si no, arma la cotización y devuelve el PDF firmado.
    if (!odoo.cotizacionAutomatica) return { creada: false, motivo: "apagada", mensaje: "Las cotizaciones las prepara una vendedora. Una vendedora se la prepara: llama a pasar_a_vendedora." };
    const lineas = (Array.isArray(a.lineas) ? a.lineas : []) as { codigo?: string; cantidad?: number }[];
    const armadas = lineas.map((l) => {
      const p = CATALOGO.find((x) => x.codigo.toLowerCase() === String(l.codigo ?? "").toLowerCase());
      if (!p) throw new RechazoDeOdoo(`No encuentro el código «${String(l.codigo)}» entre los productos de la tienda. Búscalo por nombre con buscar_productos; si no aparece, no lo manejamos: no lo cotices.`);
      return { p, cantidad: l.cantidad ?? 1 };
    });
    const subtotal = Math.round(armadas.reduce((t, x) => t + x.p.precio * x.cantidad, 0) * 100) / 100;
    const itbms = Math.round(subtotal * 7) / 100;
    const total = Math.round((subtotal + itbms) * 100) / 100;
    const dinero = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    odoo.cotizacionesArmadas++;
    const numero = `S${String(7 + odoo.cotizacionesArmadas).padStart(5, "0")}`;
    return {
      creada: true,
      reutilizada: false,
      cotizacion: {
        numero,
        lineas: armadas.map((x) => ({ codigo: x.p.codigo, producto: x.p.nombre, cantidad: x.cantidad, precio_unitario_texto: `${dinero(x.p.precio)} + ITBMS`, subtotal_texto: dinero(x.p.precio * x.cantidad), disponibilidad: x.p.disponibilidad })),
        subtotal,
        subtotal_texto: dinero(subtotal),
        itbms,
        itbms_texto: dinero(itbms),
        total,
        total_texto: dinero(total),
        valida_hasta: null,
      },
      documento: { tipo: "documento", url: `https://dcasa.example/dcasa/adjunto/${40 + odoo.cotizacionesArmadas}/1790000000/${"a".repeat(64)}/Cotizacion-${numero}.pdf`, nombre: `Cotizacion-${numero}.pdf`, mime: "application/pdf" },
      nota: "Es una cotización: no es una venta ni reserva nada.",
    };
  },
  registrar_pregunta_sin_respuesta: (a, odoo) => {
    odoo.preguntasSinRespuesta.push(a);
    return { ok: true, id: odoo.preguntasSinRespuesta.length };
  },
  pasar_a_vendedora: (_a, odoo) => {
    // Como Odoo: pausa al bot y devuelve el texto según el horario.
    odoo.estadoActual = { ...odoo.estadoActual, estado: "humano", bot_activo: false };
    // La forma REAL de Odoo (`_pasar_a_vendedora`): el texto viene en `texto_para_el_cliente`.
    return {
      texto_para_el_cliente: odoo.estadoActual.dentro_de_horario
        ? "Listo, ya avisé a una vendedora. Te escribe por aquí en unos minutos."
        : "Ya dejé tu solicitud. Una vendedora te escribe por aquí cuando abramos, a las 8:00 a. m.",
      dentro_de_horario: odoo.estadoActual.dentro_de_horario,
      urgente: false,
    };
  },
};

export class OdooFalso implements OdooApi {
  mensajes: CuerpoMensaje[] = [];
  llamadas: { nombre: string; args: Record<string, unknown>; conversacion_id: number | null }[] = [];
  hechos: CuerpoSeguimientoHecho[] = [];
  /** Las señales de «escribiendo» que el motor mandó a Odoo (true = empezó, false = terminó). */
  escribiendos: boolean[] = [];
  /** Las fotos de perfil que el motor le mandó a Odoo (o el error que debe lanzar). */
  fotosPerfil: { canal: string; id_externo: string; mime: string; base64: string }[] = [];
  falloFotoPerfil: Error | null = null;
  estadoActual = { ...ESTADO_INICIAL };
  pedidosDeEstado = 0;
  caido = false;
  conversacionId = 12;
  /** El interruptor de Ajustes de Juan: false = `cotizar` contesta que las cotizaciones las prepara una vendedora. */
  cotizacionAutomatica = true;
  cotizacionesArmadas = 0;
  rawConfig: unknown = { nombre_publico: "el equipo de D'CASA" };
  defs: DefHerramienta[] = HERRAMIENTAS_DE_PRUEBA;
  manejadores: Record<string, Manejador> = { ...MANEJADORES };
  /** Cuántas veces se pidió config (para probar la caché). */
  pedidosDeConfig = 0;
  /** Lo que el bot dejó anotado como pregunta sin respuesta. */
  preguntasSinRespuesta: Record<string, unknown>[] = [];
  /** Cuánto tarda cada herramienta (ms reales), para probar que las de un mismo paso corren juntas. */
  retardoMs = 0;
  enCurso = 0;
  maxEnCurso = 0;

  private revisar() {
    if (this.caido) throw new OdooError("Odoo no contesta", 0, true);
  }

  /** Si no es null, `mensaje()` lanza esto (p. ej. un 4xx de Odoo) en lugar de guardar. */
  falloDeMensaje: Error | null = null;

  async mensaje(cuerpo: CuerpoMensaje): Promise<RespuestaMensaje> {
    this.revisar();
    if (this.falloDeMensaje) throw this.falloDeMensaje;
    if (!this.mensajes.some((m) => m.id_mensaje === cuerpo.id_mensaje)) this.mensajes.push(cuerpo);
    return { ok: true, conversacion_id: this.conversacionId, partner_id: 55, ...this.estadoActual };
  }

  async estado(_canal: CanalId, _id: string): Promise<EstadoOdoo> {
    this.revisar();
    this.pedidosDeEstado++;
    return { ...this.estadoActual };
  }

  async config(): Promise<unknown> {
    this.revisar();
    this.pedidosDeConfig++;
    return this.rawConfig;
  }

  async herramientas(): Promise<DefHerramienta[]> {
    this.revisar();
    return this.defs;
  }

  async herramienta(nombre: string, args: Record<string, unknown>, conversacion_id: number | null): Promise<ResultadoHerramienta> {
    if (this.caido) return { ok: false, error: "Odoo no contesta", transitorio: true };
    this.llamadas.push({ nombre, args, conversacion_id });
    if (this.retardoMs > 0) {
      this.enCurso++;
      this.maxEnCurso = Math.max(this.maxEnCurso, this.enCurso);
      await new Promise((r) => setTimeout(r, this.retardoMs));
      this.enCurso--;
    }
    const f = this.manejadores[nombre];
    if (!f) return { ok: false, error: `herramienta desconocida: ${nombre}`, transitorio: false };
    try {
      return { ok: true, resultado: f(args, this) };
    } catch (e) {
      const rechazo = e instanceof RechazoDeOdoo ? e.message : undefined;
      return { ok: false, error: e instanceof Error ? e.message : String(e), transitorio: false, ...(rechazo ? { rechazo } : {}) };
    }
  }

  async seguimientoHecho(cuerpo: CuerpoSeguimientoHecho): Promise<void> {
    this.revisar();
    this.hechos.push(cuerpo);
  }

  async fotoPerfil(cuerpo: { canal: string; id_externo: string; mime: string; base64: string }): Promise<{ guardada: boolean }> {
    this.revisar();
    if (this.falloFotoPerfil) throw this.falloFotoPerfil;
    this.fotosPerfil.push(cuerpo);
    return { guardada: true };
  }

  async escribiendo(cuerpo: { activo: boolean }): Promise<void> {
    this.revisar();
    this.escribiendos.push(cuerpo.activo);
  }

  /** Llamadas a una herramienta, para afirmar en las pruebas. */
  de(nombre: string) {
    return this.llamadas.filter((l) => l.nombre === nombre);
  }
}
