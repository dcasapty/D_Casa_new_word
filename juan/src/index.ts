// Worker `dcasa-juan`: el motor del bot de atención a clientes de D'CASA (docs/JUAN.md, docs/JUAN_WORKER.md).
// Aquí solo se conecta Cloudflare con las rutas y el cron; la lógica está en rutas.ts, salud.ts y motor/.

import { ADAPTADORES } from "./canales";
import { mesDelNegocio } from "./config";
import type { Env } from "./env";
import { Conversacion } from "./motor/do";
import { Global } from "./motor/global";
import { obtenerConfig } from "./odoo/fabrica";
import { manejar, type ConversacionApi, type DepsRutas } from "./rutas";
import { avisarPorTelegram } from "./canales/telegram";
import { decidirAvisos, informeDeSalud, type EstadoDeAvisos } from "./salud";

export { Conversacion, Global };

function depsDeRutas(env: Env, ctx: ExecutionContext): DepsRutas {
  const global = () => env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
  return {
    adaptadores: ADAPTADORES,
    config: () => obtenerConfig(env),
    conversacion: (canal, id) => {
      const stub = env.CONVERSACION.get(env.CONVERSACION.idFromName(`${canal}:${id}`));
      return stub as unknown as ConversacionApi;
    },
    gastoMes: async (mes) => (await global().gastoMes(mes)).usd,
    modelosSinPrecio: async (mes) => (await global().gastoMes(mes)).modelosSinPrecio,
    leerSalud: async (clave) => global().leerSalud(clave),
    ahora: () => Date.now(),
    esperarDespues: (trabajo) => ctx.waitUntil(trabajo),
  };
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    try {
      return await manejar(req, env, depsDeRutas(env, ctx));
    } catch (e) {
      console.error("[juan] error no controlado:", e instanceof Error ? (e.stack ?? e.message) : String(e));
      return new Response("error", { status: 500 });
    }
  },

  /** Cron de salud: ¿sigue conectado el puente? ¿se alcanzó el tope de IA? Avisa a la dueña una vez por problema. */
  async scheduled(_evento: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(revisarSalud(env));
  },
} satisfies ExportedHandler<Env>;

export async function revisarSalud(env: Env): Promise<void> {
  const global = env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
  const cfg = await obtenerConfig(env);
  const informe = await informeDeSalud({
    env,
    adaptadores: ADAPTADORES,
    config: () => obtenerConfig(env),
    gastoMes: async (mes) => (await global.gastoMes(mes)).usd,
    modelosSinPrecio: async (mes) => (await global.gastoMes(mes)).modelosSinPrecio,
    leerSalud: async (clave) => global.leerSalud(clave),
    ahora: () => Date.now(),
  });
  const mes = mesDelNegocio(cfg.horario.zona, Date.now());
  const problemas = [...informe.problemas, ...informe.avisos];
  if (informe.tope_alcanzado) {
    problemas.push(`se alcanzó el tope de IA de ${mes} ($${informe.gasto_ia_mes_usd} de $${informe.tope_usd}); el bot sigue contestando con el modelo económico`);
  }
  const guardado = await global.leerSalud("avisos");
  const previo: EstadoDeAvisos = guardado ? (JSON.parse(guardado.json) as EstadoDeAvisos) : { avisados: [] };
  // El aviso del tope vale por mes: el mes siguiente vuelve a avisar.
  const filtrado: EstadoDeAvisos = { avisados: previo.avisados.filter((p) => !p.startsWith("se alcanzó el tope") || p.includes(mes)) };
  const { mensajes, nuevo } = decidirAvisos(problemas, filtrado);
  await global.guardarSalud("avisos", JSON.stringify(nuevo));
  await global.guardarSalud("ultimo_informe", JSON.stringify(informe));

  const chat = env.ALERTA_TELEGRAM_CHAT_ID;
  for (const m of mensajes) {
    console.warn(`[juan] salud: ${m}`);
    if (chat) await avisarPorTelegram(env, chat, m);
  }
}
