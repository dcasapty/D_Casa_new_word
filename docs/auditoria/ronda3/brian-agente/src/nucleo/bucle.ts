import { Acciones, type Pendiente } from "./acciones";
import { Enrutador, SinRuta, type Rutas } from "./enrutador";
import { catalogoPara, esquemas, HERRAMIENTAS, validar, type Herramienta } from "./herramientas";
import type { Libro } from "./libro";
import type { EjecutorOdoo } from "./odoo";
import { contexto, SISTEMA } from "./prompt";
import { esquema, type Sql } from "./sql";
import { ErrorProveedor, type Esfuerzo, type MensajeNeutro, type Persona, type Proveedor } from "./tipos";

export interface Configuracion {
  rutas: Rutas;
  maxPasos: number;
  maxTokens: number;
  esfuerzo: Esfuerzo;
  maxCaracteresResultado: number;
  ttlConfirmacionMs: number;
}

export const CONFIG_POR_DEFECTO: Configuracion = {
  rutas: {
    principal: [
      { proveedor: "meta", modelo: "muse-spark-1.3" },
      { proveedor: "anthropic", modelo: "claude-sonnet-5-5" },
    ],
    economica: [{ proveedor: "anthropic", modelo: "claude-haiku-4-5" }],
  },
  maxPasos: 6,
  maxTokens: 4000,
  esfuerzo: "low",
  maxCaracteresResultado: 12_000,
  ttlConfirmacionMs: 10 * 60 * 1000,
};

export interface Dependencias {
  sql: Sql;
  libro: Libro;
  proveedores: Record<string, Proveedor>;
  odoo: EjecutorOdoo;
  reloj: () => number;
  nuevoId: () => string;
  conversacion: string;
  config?: Partial<Configuracion>;
  herramientas?: Herramienta[];
}

export interface ResultadoTurno {
  texto: string;
  pendientes: Pendiente[];
  pasos: number;
  costoMicro: number;
  modelos: string[];
}

export type ResultadoConfirmacion =
  | { estado: "ejecutada"; resultado: unknown; repetida: boolean }
  | { estado: "cancelada" | "caducada" | "en_curso" | "no_existe" | "no_autorizado" }
  | { estado: "fallida"; error: string };

/**
 * El bucle de Brian. Corre dentro del Durable Object de la conversación (un DO por conversación),
 * con su SQLite propio. Nunca usa sudo: Odoo ejecuta con la clave de la persona.
 */
export class Brian {
  private readonly cfg: Configuracion;
  private readonly acciones: Acciones;
  private readonly enrutador: Enrutador;
  private readonly todas: Herramienta[];

  constructor(private readonly d: Dependencias) {
    this.cfg = { ...CONFIG_POR_DEFECTO, ...(d.config ?? {}) };
    esquema(d.sql);
    this.acciones = new Acciones(d.sql, d.reloj, d.nuevoId, this.cfg.ttlConfirmacionMs);
    this.enrutador = new Enrutador(d.proveedores, this.cfg.rutas, d.libro, d.reloj);
    this.todas = d.herramientas ?? HERRAMIENTAS;
  }

  // -- historial (solo se agrega; nunca se reescribe un turno anterior) ---------------------
  private historial(): MensajeNeutro[] {
    return this.d.sql.ejecutar("SELECT json FROM mensajes ORDER BY n").map((f) => JSON.parse(String(f.json)) as MensajeNeutro);
  }
  private agregar(m: MensajeNeutro): void {
    this.d.sql.ejecutar("INSERT INTO mensajes (json) VALUES (?)", JSON.stringify(m));
  }

  /** Subconjunto de herramientas FIJADO al empezar la conversación (no rompe la caché por mensaje). */
  private herramientasDe(persona: Persona): Herramienta[] {
    const f = this.d.sql.ejecutar("SELECT valor FROM ajustes WHERE clave = 'herramientas'")[0];
    let nombres: string[];
    if (f) nombres = JSON.parse(String(f.valor));
    else {
      nombres = catalogoPara(persona, this.todas).map((h) => h.nombre);
      this.d.sql.ejecutar("INSERT INTO ajustes (clave, valor) VALUES ('herramientas', ?)", JSON.stringify(nombres));
    }
    return nombres.map((n) => this.todas.find((h) => h.nombre === n)).filter((h): h is Herramienta => !!h);
  }

  async turno(persona: Persona, texto: string, pantalla?: string): Promise<ResultadoTurno> {
    const ahora = new Date(this.d.reloj());
    const mes = ahora.toISOString().slice(0, 7);
    const herramientas = this.herramientasDe(persona);
    this.agregar({ rol: "user", texto: `${contexto(persona, ahora, pantalla)}\n${texto}` });
    const res: ResultadoTurno = { texto: "", pendientes: [], pasos: 0, costoMicro: 0, modelos: [] };

    for (let paso = 0; paso < this.cfg.maxPasos; paso++) {
      res.pasos = paso + 1;
      let r;
      try {
        r = await this.enrutador.llamar(
          {
            sistema: SISTEMA,
            herramientas: esquemas(herramientas),
            mensajes: this.historial(),
            maxTokens: this.cfg.maxTokens,
            esfuerzo: this.cfg.esfuerzo,
            metadatos: { persona: persona.id, rol: persona.rol, conversacion: this.d.conversacion },
          },
          persona,
          mes,
        );
      } catch (e) {
        if (e instanceof SinRuta || e instanceof ErrorProveedor) {
          res.texto = e.message.includes("tope")
            ? "Llegaste al tope de gasto de Brian de este mes. Pídele a la gerencia que lo revise."
            : "Ahora mismo no puedo hablar con ningún proveedor de IA. Intenta en un momento.";
          return res;
        }
        throw e;
      }
      const { respuesta, destino } = r;
      res.modelos.push(`${destino.proveedor}/${destino.modelo}`);
      res.costoMicro += await this.d.libro.registrar({
        fecha: ahora.toISOString(), persona, conversacion: this.d.conversacion,
        proveedor: destino.proveedor, modelo: destino.modelo, uso: respuesta.uso,
      });
      this.agregar({
        rol: "assistant", texto: respuesta.texto, llamadas: respuesta.llamadas,
        crudo: respuesta.crudo === undefined ? undefined : { proveedor: destino.proveedor, contenido: respuesta.crudo },
      });
      if (respuesta.llamadas.length === 0) {
        res.texto = respuesta.texto;
        return res;
      }
      for (const llamada of respuesta.llamadas) {
        const salida = await this.ejecutarLlamada(persona, herramientas, llamada.id, llamada.nombre, llamada.argumentos, res);
        this.agregar({ rol: "tool", llamadaId: llamada.id, nombre: llamada.nombre, texto: salida.texto, error: salida.error });
      }
      if (res.pendientes.length > 0) {
        // No se gasta otra llamada al modelo: la tarjeta la arma el borde con el resumen ya resuelto.
        res.texto = [respuesta.texto, ...res.pendientes.map((p) => `Necesito tu confirmación: ${p.resumen}`)]
          .filter(Boolean).join("\n");
        return res;
      }
    }
    res.texto = "Me tomó demasiados pasos. Dime en una frase qué necesitas y lo intento de nuevo.";
    return res;
  }

  private async ejecutarLlamada(
    persona: Persona, herramientas: Herramienta[], id: string, nombre: string, args: Record<string, unknown>, res: ResultadoTurno,
  ): Promise<{ texto: string; error?: boolean }> {
    const previo = this.acciones.resultadoPrevio(id);
    if (previo !== undefined) return { texto: this.recortar(previo) };
    const h = herramientas.find((x) => x.nombre === nombre);
    if (!h) return { texto: `La herramienta «${nombre}» no está disponible para tu perfil.`, error: true };
    const invalido = validar(h, args);
    if (invalido) return { texto: invalido, error: true };
    if (h.nivel === "sensible") {
      const p = this.acciones.crearPendiente(id, h.nombre, args, h.resumir ? h.resumir(args) : `${h.nombre} ${JSON.stringify(args)}`, persona.id);
      res.pendientes.push(p);
      return { texto: `PENDIENTE_DE_CONFIRMACION: ${p.resumen} (caduca en ${Math.round(this.cfg.ttlConfirmacionMs / 60000)} min). No la repitas.` };
    }
    try {
      const valor = await h.ejecutar(args, { odoo: this.d.odoo, persona, idem: id });
      this.acciones.guardarResultado(id, h.nombre, valor);
      return { texto: this.recortar(valor) };
    } catch (e) {
      return { texto: `Error: ${(e as Error).message}`, error: true };
    }
  }

  private recortar(v: unknown): string {
    const s = JSON.stringify(v ?? null);
    return s.length > this.cfg.maxCaracteresResultado
      ? `${s.slice(0, this.cfg.maxCaracteresResultado)}… (recortado: pide un rango más chico)`
      : s;
  }

  /** La persona pulsa Confirmar/Cancelar en el panel o en Telegram. */
  async confirmar(persona: Persona, pendienteId: string, aceptar: boolean): Promise<ResultadoConfirmacion> {
    const p = this.acciones.obtener(pendienteId);
    if (!p) return { estado: "no_existe" };
    if (p.persona !== persona.id) return { estado: "no_autorizado" };
    if (p.estado === "ejecutada") {
      return { estado: "ejecutada", resultado: this.acciones.resultadoPrevio(p.llamadaId), repetida: true };
    }
    if (p.estado === "ejecutando") return { estado: "en_curso" };
    if (p.estado !== "pendiente") return { estado: p.estado as "cancelada" | "caducada" };
    if (this.acciones.vencida(p)) {
      this.acciones.transicion(p.id, "pendiente", "caducada");
      this.agregar({ rol: "user", texto: `<confirmacion>La acción «${p.resumen}» caducó sin confirmarse.</confirmacion>` });
      return { estado: "caducada" };
    }
    if (!aceptar) {
      this.acciones.transicion(p.id, "pendiente", "cancelada");
      this.agregar({ rol: "user", texto: `<confirmacion>La persona canceló: ${p.resumen}</confirmacion>` });
      return { estado: "cancelada" };
    }
    // Se marca ANTES del await: una segunda confirmación concurrente ve «ejecutando» y no repite.
    if (!this.acciones.transicion(p.id, "pendiente", "ejecutando")) return { estado: "en_curso" };
    const h = this.todas.find((x) => x.nombre === p.herramienta);
    try {
      if (!h) throw new Error("herramienta desaparecida");
      const valor = await h.ejecutar(p.argumentos, { odoo: this.d.odoo, persona, idem: p.llamadaId });
      this.acciones.guardarResultado(p.llamadaId, p.herramienta, valor);
      this.acciones.transicion(p.id, "ejecutando", "ejecutada");
      this.agregar({ rol: "user", texto: `<confirmacion>Confirmado y hecho: ${p.resumen}. Resultado: ${this.recortar(valor)}</confirmacion>` });
      return { estado: "ejecutada", resultado: valor, repetida: false };
    } catch (e) {
      this.acciones.transicion(p.id, "ejecutando", "fallida");
      return { estado: "fallida", error: (e as Error).message };
    }
  }
}
