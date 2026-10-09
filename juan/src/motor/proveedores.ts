// Quién pone la IA: Anthropic (Claude), Meta (Muse Spark) u OpenAI. Se elige en Odoo (`proveedor_ia`, con un
// `proveedor_respaldo_ia` opcional) sin tocar código. Si el elegido falla o no tiene clave, contesta el respaldo; si no hay
// ninguno, el cliente recibe «una vendedora te atiende» y /salud lo dice. El bot nunca se queda mudo sin avisar.
//
// Meta usa su API compatible con OpenAI (Chat Completions, base https://api.meta.ai/v1; docs/auditoria/ronda3/brian-agente.md §2):
//   · Muse Spark SIEMPRE razona: `reasoning_effort` ∈ minimal|low|medium|high|xhigh y `"none"` da HTTP 400 → «low» en el nivel
//     rápido y «medium» en el inteligente;
//   · el razonamiento cuenta dentro del tope de tokens de salida → ese tope es mucho más alto que con Claude;
//   · el límite se manda como `max_completion_tokens` (`max_tokens` es un alias deprecado);
//   · solo acepta `tool_choice: "auto"`; admite herramientas en paralelo;
//   · la caché de prompt es automática por prefijo (no hay marcas como en Anthropic).

import { createAnthropic } from "@ai-sdk/anthropic";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import type { LanguageModel } from "ai";
import { MODELOS_POR_DEFECTO, modeloValido, type Config, type ProveedorIa } from "../config";
import type { Env } from "../env";
import type { Nivel } from "./precios";

export type { ProveedorIa };

/** Con qué se pide la IA en una llamada concreta. */
export interface SeleccionDeModelo {
  proveedor: ProveedorIa;
  modelo: string;
  nivel: Nivel;
}

export type FabricaDeModelos = (s: SeleccionDeModelo) => LanguageModel;

export const NOMBRE_DE_LA_CLAVE: Record<ProveedorIa, "ANTHROPIC_API_KEY" | "META_AI_API_KEY" | "OPENAI_API_KEY"> = {
  anthropic: "ANTHROPIC_API_KEY",
  meta: "META_AI_API_KEY",
  openai: "OPENAI_API_KEY",
};

export const BASE_URL_POR_DEFECTO: Record<Exclude<ProveedorIa, "anthropic">, string> = {
  meta: "https://api.meta.ai/v1",
  openai: "https://api.openai.com/v1",
};

export const ESFUERZO_DE_RAZONAMIENTO_META: Record<Nivel, "low" | "medium"> = { rapido: "low", inteligente: "medium" };
const ESFUERZOS_VALIDOS = new Set(["minimal", "low", "medium", "high", "xhigh"]);

/** Tokens máximos de salida. En Meta y OpenAI el razonamiento sale de aquí: con 700 se quedaría sin respuesta. */
export function topeDeSalida(proveedor: ProveedorIa, nivel: Nivel): number {
  if (proveedor === "anthropic") return 700;
  if (proveedor === "meta") return nivel === "inteligente" ? 8000 : 4000;
  return 2500;
}

export function clavePresente(env: Env, p: ProveedorIa): boolean {
  return !!env[NOMBRE_DE_LA_CLAVE[p]];
}

export function proveedoresConClave(env: Env): ProveedorIa[] {
  return (["anthropic", "meta", "openai"] as const).filter((p) => clavePresente(env, p));
}

function baseUrlDe(env: Env, p: Exclude<ProveedorIa, "anthropic">): string {
  const propia = p === "meta" ? env.META_AI_BASE_URL : env.OPENAI_BASE_URL;
  return (propia?.trim() || BASE_URL_POR_DEFECTO[p]).replace(/\/+$/, "");
}

// ── Qué modelos tiene cada papel (principal / respaldo) ─────────────────────

export interface ModelosDeUnProveedor {
  proveedor: ProveedorIa;
  rapido: string;
  inteligente: string;
}

/** Los modelos del proveedor principal o del de respaldo, o null si ese papel no existe o no tiene modelos utilizables. */
export function modelosDelPapel(cfg: Config, papel: "principal" | "respaldo"): ModelosDeUnProveedor | null {
  if (papel === "principal") {
    const rapido = cfg.modelo_rapido;
    const inteligente = cfg.modelo_inteligente || cfg.modelo_rapido;
    return rapido ? { proveedor: cfg.proveedor_ia, rapido, inteligente } : null;
  }
  const p = cfg.proveedor_respaldo_ia;
  if (!p) return null;
  const rapido = cfg.modelo_rapido_respaldo || MODELOS_POR_DEFECTO[p].rapido;
  const inteligente = cfg.modelo_inteligente_respaldo || MODELOS_POR_DEFECTO[p].inteligente || rapido;
  return rapido ? { proveedor: p, rapido, inteligente } : null;
}

/**
 * El orden en que se intenta contestar: el principal (con el nivel pedido, y el rápido si el inteligente falla) y luego el
 * respaldo. Solo entran los proveedores que tienen clave. Vacío = nadie puede contestar.
 */
export function planDeIntentos(cfg: Config, nivel: Nivel, disponibles: readonly ProveedorIa[]): SeleccionDeModelo[] {
  const plan: SeleccionDeModelo[] = [];
  const agregar = (m: ModelosDeUnProveedor | null) => {
    if (!m || !disponibles.includes(m.proveedor)) return;
    const niveles: Nivel[] = nivel === "inteligente" ? ["inteligente", "rapido"] : ["rapido"];
    for (const n of niveles) {
      const modelo = n === "inteligente" ? m.inteligente : m.rapido;
      if (!plan.some((x) => x.proveedor === m.proveedor && x.modelo === modelo && x.nivel === n)) plan.push({ proveedor: m.proveedor, modelo, nivel: n });
    }
  };
  agregar(modelosDelPapel(cfg, "principal"));
  agregar(modelosDelPapel(cfg, "respaldo"));
  return plan;
}

/** Los modelos «contributor» de Meta entrenan con los mensajes: solo se usan si la dueña los escribe a propósito. Se avisa en /salud. */
export function entrenaConLosMensajes(modelo: string): boolean {
  return /contributor/i.test(modelo);
}

// ── La petición a una API compatible con OpenAI (Meta, OpenAI) ───────────────

/**
 * Ajusta el cuerpo de Chat Completions a lo que el proveedor acepta. Es una función pura para poder probarla.
 *   · `max_tokens` (alias deprecado) → `max_completion_tokens`;
 *   · Meta: `reasoning_effort` fijo por nivel (nunca «none», que da 400) y `tool_choice` solo «auto».
 */
export function ajustarCuerpo(proveedor: Exclude<ProveedorIa, "anthropic">, nivel: Nivel, cuerpo: Record<string, unknown>): Record<string, unknown> {
  const b: Record<string, unknown> = { ...cuerpo };
  if ("max_tokens" in b) {
    b.max_completion_tokens ??= b.max_tokens;
    delete b.max_tokens;
  }
  if (proveedor === "meta") {
    const esfuerzo = ESFUERZO_DE_RAZONAMIENTO_META[nivel];
    b.reasoning_effort = ESFUERZOS_VALIDOS.has(esfuerzo) ? esfuerzo : "low";
    // Solo «auto». Ni «none», ni «required», ni una función nombrada: todos dan 400.
    if (Array.isArray(b.tools) && b.tools.length > 0) b.tool_choice = "auto";
    else delete b.tool_choice;
  }
  return b;
}

export interface OpcionesDeFabrica {
  /** Para las pruebas: un servidor falso compatible con OpenAI. */
  fetch?: typeof fetch;
}

/** La fábrica de producción: lee las claves del entorno y arma el modelo del proveedor elegido. */
export function fabricaDeProduccion(env: Env, opciones: OpcionesDeFabrica = {}): FabricaDeModelos {
  return ({ proveedor, modelo, nivel }) => {
    if (proveedor === "anthropic") return createAnthropic({ apiKey: env.ANTHROPIC_API_KEY ?? "", fetch: opciones.fetch })(modelo);
    const compatible = createOpenAICompatible({
      name: proveedor,
      baseURL: baseUrlDe(env, proveedor),
      apiKey: env[NOMBRE_DE_LA_CLAVE[proveedor]] ?? "",
      fetch: opciones.fetch,
      transformRequestBody: (cuerpo) => ajustarCuerpo(proveedor, nivel, cuerpo),
    });
    return compatible.chatModel(modelo);
  };
}

export { modeloValido };
