import { Agent } from "agents";
import { Brian } from "./nucleo/bucle";
import type { Autorizacion, FilaUso, Libro } from "./nucleo/libro";
import { OdooJson2 } from "./nucleo/odoo";
import type { Persona } from "./nucleo/tipos";
import { ProveedorAnthropic } from "./proveedores/anthropic";
import { ProveedorCompat } from "./proveedores/openai_compat";
import { sqlDeDurableObject } from "./sql_do";
import type { Env } from "./env";

interface Estado {
  ultimoCostoMicro: number;
}

/** Libro remoto: llama por RPC al DO único `LibroUso`. */
class LibroRemoto implements Libro {
  constructor(private readonly env: Env) {}
  private stub() {
    return this.env.LIBRO.getByName("dcasa");
  }
  autorizar(p: Persona, prov: string, modelo: string, mes: string): Promise<Autorizacion> {
    return this.stub().autorizar(p, prov, modelo, mes) as unknown as Promise<Autorizacion>;
  }
  registrar(f: FilaUso): Promise<number> {
    return this.stub().registrar(f) as unknown as Promise<number>;
  }
}

/**
 * UN agente (Durable Object con SQLite propio) POR CONVERSACIÓN. Nombre = `<persona>:<conversación>`.
 * El Worker de entrada (index.ts) ya verificó la identidad y la pasa en `x-brian-persona`.
 * Siguiente paso (no prototipado): streaming al panel por WebSocket con `@callable({ streaming: true })`
 * o `AIChatAgent`, y Workflows para tareas largas (importar un Excel de 200 filas).
 */
export class BrianConversacion extends Agent<Env, Estado> {
  initialState: Estado = { ultimoCostoMicro: 0 };

  private brian(): Brian {
    const env = this.env;
    // La clave de Odoo de la PERSONA se guarda cifrada en el DO al vincular (no prototipado aquí).
    const filaClave = this.sql<{ valor: string }>`SELECT valor FROM ajustes WHERE clave = 'clave_odoo'`;
    return new Brian({
      sql: sqlDeDurableObject(this.ctx.storage),
      libro: new LibroRemoto(env),
      proveedores: {
        meta: new ProveedorCompat({ id: "meta", base: `${env.AIG_BASE}/custom-meta/v1`, clave: env.META_API_KEY, gateway: true, permitidos: ["muse-spark-1.3"] }),
        anthropic: new ProveedorAnthropic({ base: `${env.AIG_BASE}/anthropic`, clave: env.ANTHROPIC_API_KEY, gateway: true }),
      },
      odoo: new OdooJson2(env.ODOO_URL, env.ODOO_DB, filaClave[0]?.valor ?? ""),
      reloj: () => Date.now(),
      nuevoId: () => crypto.randomUUID(),
      conversacion: this.name,
    });
  }

  async onRequest(request: Request): Promise<Response> {
    const persona = JSON.parse(request.headers.get("x-brian-persona") ?? "null") as Persona | null;
    if (!persona) return new Response("sin identidad", { status: 401 });
    const url = new URL(request.url);
    const cuerpo = (await request.json()) as Record<string, unknown>;
    if (url.pathname.endsWith("/mensaje")) {
      const r = await this.brian().turno(persona, String(cuerpo.texto ?? ""), cuerpo.pantalla as string | undefined);
      this.setState({ ultimoCostoMicro: r.costoMicro });
      return Response.json(r);
    }
    if (url.pathname.endsWith("/confirmar")) {
      return Response.json(await this.brian().confirmar(persona, String(cuerpo.id), cuerpo.aceptar === true));
    }
    return new Response("no encontrado", { status: 404 });
  }
}
