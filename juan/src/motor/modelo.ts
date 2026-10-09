// Qué modelo contesta, y cómo se corre un turno (el bucle de IA con herramientas, hasta 6 pasos).
//
//   · rápido (barato) por defecto; inteligente si el cliente está molesto, la consulta es larga o enredada, el turno anterior usó
//     muchas herramientas o la búsqueda en la base de conocimiento salió floja;
//   · con Claude el prompt estable se cachea (bloque `ephemeral`); Meta y OpenAI cachean solos por prefijo, así que el prompt
//     estable va PRIMERO y lo que cambia en cada turno al final;
//   · al llegar al tope mensual SIEMPRE se baja al rápido (motor/precios.ts → aplicarTope).

import { generateText, stepCountIs, type LanguageModel, type ModelMessage, type ToolSet } from "ai";
import { hayFrustracion } from "../dcasa/intencion";
import type { ProveedorIa } from "../config";
import { topeDeSalida } from "./proveedores";
import { usoDelSdk, type Nivel, type Uso } from "./precios";

export interface SenalesDelTurno {
  textoDelCliente: string;
  /** Herramientas usadas en los dos turnos anteriores (suma). */
  llamadasRecientes: number;
  /** El turno anterior buscó en la base de conocimiento y no encontró respuesta (o quedó una pregunta sin respuesta). */
  busquedaFloja?: boolean;
}

/** Barato por defecto, listo cuando hace falta (el CRM de Baby Caleb hacía lo mismo con su `selectModel`). */
export function elegirNivel(s: SenalesDelTurno): Nivel {
  if (hayFrustracion(s.textoDelCliente)) return "inteligente";
  if (s.llamadasRecientes > 5) return "inteligente";
  if (s.busquedaFloja) return "inteligente";
  const preguntas = (s.textoDelCliente.match(/[?¿]/g) ?? []).length;
  if (preguntas >= 4 || s.textoDelCliente.length > 700) return "inteligente";
  return "rapido";
}

export const PASOS_MAXIMOS = 6;

export interface EntradaDelTurno {
  modelo: LanguageModel;
  proveedor: ProveedorIa;
  nivel: Nivel;
  /** Bloque que casi nunca cambia (se cachea). */
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
  /** El modelo llegó al límite de pasos o de tokens sin escribir nada: hay que pedirle que responda ya. */
  sinTexto: boolean;
}

export async function correrTurno(e: EntradaDelTurno): Promise<SalidaDelTurno> {
  const conMarcaDeCache = e.proveedor === "anthropic" && e.cachear !== false;
  const r = await generateText({
    model: e.modelo,
    // Claude: dos bloques y el primero marcado (todo lo anterior a la marca se cachea: herramientas + prompt estable).
    // Meta/OpenAI: un solo mensaje de sistema (algunos servidores no aceptan dos) y caché automática por prefijo.
    system:
      e.proveedor === "anthropic"
        ? [
            {
              role: "system",
              content: e.sistemaEstable,
              ...(conMarcaDeCache ? { providerOptions: { anthropic: { cacheControl: { type: "ephemeral" as const } } } } : {}),
            },
            { role: "system", content: e.sistemaDinamico },
          ]
        : `${e.sistemaEstable}\n\n${e.sistemaDinamico}`,
    messages: e.mensajes,
    tools: e.herramientas,
    stopWhen: stepCountIs(PASOS_MAXIMOS),
    maxOutputTokens: topeDeSalida(e.proveedor, e.nivel),
    // Los reintentos y el respaldo los maneja el motor (motor/conversacion.ts → correrConRespaldo): el SDK no debe esperar segundos
    // por su cuenta antes de pasar al otro proveedor.
    maxRetries: 0,
  });
  const texto = r.text.trim();
  return { texto, uso: usoDelSdk(r.totalUsage), pasos: r.steps.length, sinTexto: texto.length === 0 };
}
