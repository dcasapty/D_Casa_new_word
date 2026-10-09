// Qué modelo contesta, y cómo se corre un turno (el bucle de IA con herramientas, hasta 6 pasos).
//
//   · rápido (Haiku) por defecto; inteligente (Sonnet) si el cliente está molesto, la consulta es larga
//     o enredada, o el turno anterior usó muchas herramientas;
//   · el prompt estable se cachea (bloque `ephemeral`); lo que cambia en cada turno va aparte;
//   · al llegar al tope mensual SIEMPRE se baja al rápido (motor/precios.ts → aplicarTope).

import { createAnthropic } from "@ai-sdk/anthropic";
import { generateText, stepCountIs, type LanguageModel, type ModelMessage, type ToolSet } from "ai";
import { hayFrustracion } from "../dcasa/intencion";
import { usoDelSdk, type Nivel, type Uso } from "./precios";

export type FabricaDeModelos = (modeloId: string) => LanguageModel;

export function fabricaAnthropic(apiKey: string): FabricaDeModelos {
  const anthropic = createAnthropic({ apiKey });
  return (id) => anthropic(id);
}

export interface SenalesDelTurno {
  textoDelCliente: string;
  /** Herramientas que usó el turno anterior. */
  llamadasRecientes: number;
}

/** Fácil por defecto, listo cuando hace falta (el CRM de Baby Caleb hacía lo mismo con su `selectModel`). */
export function elegirNivel(s: SenalesDelTurno): Nivel {
  if (hayFrustracion(s.textoDelCliente)) return "inteligente";
  if (s.llamadasRecientes > 3) return "inteligente";
  const preguntas = (s.textoDelCliente.match(/[?¿]/g) ?? []).length;
  if (preguntas >= 4 || s.textoDelCliente.length > 700) return "inteligente";
  return "rapido";
}

export const PASOS_MAXIMOS = 6;
const TOKENS_DE_SALIDA = 700;

export interface EntradaDelTurno {
  modelo: LanguageModel;
  /** Bloque que se cachea. */
  sistemaEstable: string;
  /** Bloque que cambia en cada turno. */
  sistemaDinamico: string;
  mensajes: ModelMessage[];
  herramientas: ToolSet;
  /** false = no marcar el prompt para caché (los que no se repiten, como el seguimiento). */
  cachear?: boolean;
}

export interface SalidaDelTurno {
  texto: string;
  uso: Uso;
  pasos: number;
  /** El modelo llegó al límite de pasos sin escribir nada: hay que pedirle que responda ya. */
  sinTexto: boolean;
}

export async function correrTurno(e: EntradaDelTurno): Promise<SalidaDelTurno> {
  const r = await generateText({
    model: e.modelo,
    system: [
      {
        role: "system",
        content: e.sistemaEstable,
        // Anthropic cachea todo lo anterior a este punto (herramientas + prompt estable).
        // El caché solo se activa si el bloque supera el mínimo del modelo; si no, no estorba.
        ...(e.cachear === false ? {} : { providerOptions: { anthropic: { cacheControl: { type: "ephemeral" as const } } } }),
      },
      { role: "system", content: e.sistemaDinamico },
    ],
    messages: e.mensajes,
    tools: e.herramientas,
    stopWhen: stepCountIs(PASOS_MAXIMOS),
    maxOutputTokens: TOKENS_DE_SALIDA,
  });
  const texto = r.text.trim();
  return { texto, uso: usoDelSdk(r.totalUsage), pasos: r.steps.length, sinTexto: texto.length === 0 };
}
