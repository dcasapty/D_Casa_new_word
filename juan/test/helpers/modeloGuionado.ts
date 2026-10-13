// Un modelo de IA de mentira que dice lo que el guion le manda, sin llamar a nadie.
// Pasa por el bucle REAL del SDK (herramientas, hasta 6 pasos), así las pruebas ejercitan el mismo camino que producción.
import { MockLanguageModelV3 } from "ai/test";

export interface LlamadaGuionada {
  nombre: string;
  args: Record<string, unknown>;
}

export type PasoDelGuion =
  | { texto: string; entrada?: number; salida?: number; cacheLectura?: number; alGenerar?: () => Promise<void> | void }
  | { llamadas: LlamadaGuionada[]; texto?: string; entrada?: number; salida?: number; alGenerar?: () => Promise<void> | void }
  | { error: Error };

let contador = 0;

export interface ModeloGuionado extends MockLanguageModelV3 {
  /** Los prompts que recibió cada paso (para comprobar qué ve el modelo). */
  prompts(): string[];
}

/** Lo que el modelo recibió, como texto plano (sistema + mensajes + resultados de herramientas). */
export function textoDeLaLlamada(opts: { prompt: unknown }): string {
  return JSON.stringify(opts.prompt);
}

export function modeloGuionado(pasos: PasoDelGuion[], id = "claude-haiku-4-5"): ModeloGuionado {
  let i = 0;
  const m = new MockLanguageModelV3({
    provider: "anthropic",
    modelId: id,
    doGenerate: async () => {
      const paso = pasos[Math.min(i, pasos.length - 1)];
      i++;
      if ("error" in paso) throw paso.error;
      // Para simular que algo ocurre MIENTRAS el modelo piensa (una vendedora que escribe, por ejemplo).
      await paso.alGenerar?.();
      const content: Array<{ type: "text"; text: string } | { type: "tool-call"; toolCallId: string; toolName: string; input: string }> = [];
      if ("texto" in paso && paso.texto !== undefined) content.push({ type: "text", text: paso.texto });
      if ("llamadas" in paso) {
        for (const l of paso.llamadas) {
          content.push({ type: "tool-call", toolCallId: `llamada-${++contador}`, toolName: l.nombre, input: JSON.stringify(l.args) });
        }
      }
      const entrada = "entrada" in paso && paso.entrada !== undefined ? paso.entrada : 100;
      const salida = "salida" in paso && paso.salida !== undefined ? paso.salida : 20;
      const cacheLectura = "cacheLectura" in paso && paso.cacheLectura !== undefined ? paso.cacheLectura : 0;
      return {
        content,
        finishReason: { unified: "llamadas" in paso ? ("tool-calls" as const) : ("stop" as const), raw: undefined },
        usage: {
          inputTokens: { total: entrada + cacheLectura, noCache: entrada, cacheRead: cacheLectura, cacheWrite: 0 },
          outputTokens: { total: salida, text: salida, reasoning: 0 },
        },
        warnings: [],
      };
    },
  }) as ModeloGuionado;
  m.prompts = () => m.doGenerateCalls.map((c) => textoDeLaLlamada(c));
  return m;
}

/** Un modelo que siempre responde lo mismo, sin herramientas. */
export const modeloQueDice = (texto: string, id?: string) => modeloGuionado([{ texto }], id);
