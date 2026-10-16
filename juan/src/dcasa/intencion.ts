// Intenciones del cliente que se resuelven SIN esperar al modelo: son reglas del contrato
// (docs/JUAN.md, reglas 1 y 10) y no pueden depender de que la IA obedezca.

import { normalizar, sinAcentos } from "./texto";

const QUIEN = "(?:persona|vendedora|vendedor|humano|humana|asesor|asesora|agente|ejecutiva|ejecutivo|representante|alguien)";
const ARTICULO = "(?:una |un |la |el )?";
const COLA = "(?: real| de verdad| humana| humano| de carne y hueso)?(?: por favor| porfa| porfavor| ya| ahora| gracias)?";

/** El mensaje ENTERO es la petición: «persona», «quiero una vendedora», «hablar con un humano por favor». */
const SOLO_PETICION = new RegExp(
  `^(?:hola |buenas |buenos dias |buenas tardes |buenas noches )?(?:quiero |quisiera |necesito |puedo |podria |me pueden |me puedes |me podrian |me pasas |me pasan |me pasarias |me comunicas |me comunican |me conectas |me conectan |conectame |conectenme |pasame |pasenme |comunicame |comuniquenme |hablar |atencion |atiendame |de |mejor |prefiero )*(?:con |a )?${ARTICULO}${QUIEN}${COLA}$`,
);

/** La petición va dentro de una frase más larga, pero con un verbo que la hace inequívoca. */
const DENTRO_DE_FRASE = [
  new RegExp(`\\b(?:hablar|conversar|comunicarme|comunicar|pasarme|pasame|pasen|contactarme|contactar|escribir|escribirme)(?: directamente)? (?:con|a) ${ARTICULO}${QUIEN}(?: real| de verdad| humana?)?\\b`),
  new RegExp(`\\bque me (?:atienda|atiendan|responda|respondan|llame|llamen|escriba|escriban) ${ARTICULO}${QUIEN}\\b`),
  new RegExp(`\\b(?:quiero|necesito|prefiero|quisiera|requiero) (?:que me atienda )?${ARTICULO}(?:persona|vendedora|vendedor|humano|humana|asesor|asesora)\\b`),
  new RegExp(`\\b(?:no quiero|no me gusta|no quiero hablar con) (?:un |el )?(?:bot|robot|asistente automatico|asistente virtual|maquina)\\b`),
  new RegExp(`\\bpersona (?:de verdad|real)\\b`),
  new RegExp(`\\bcon alguien (?:real|de verdad)\\b`),
  new RegExp(`\\bun humano\\b`),
];

/** Lo mismo en inglés: Juan atiende en inglés a quien le escribe en inglés (decisión de la dueña, 2026-10-16). */
const QUIEN_EN = "(?:human|person|real person|agent|representative|salesperson|someone|somebody|a real human)";
const EN_INGLES = [
  new RegExp(`^(?:hi |hello |hey )?(?:i want |i need |can i talk to |can i speak to |let me talk to )?(?:a |an )?(?:human|person|real person|agent|representative|salesperson)(?: please| pls)?$`),
  new RegExp(`\\b(?:talk|speak|chat) (?:to|with) (?:a |an )?${QUIEN_EN}\\b`),
  new RegExp(`\\b(?:i want|i need|i d like|i would like|can i get|get me) (?:a |an )?(?:human|real person|agent|representative|salesperson)\\b`),
];

/** «persona», «vendedora» o «humano» pasan SIEMPRE a una vendedora (regla 1). */
export function pideUnaPersona(texto: string): boolean {
  const t = normalizar(texto);
  if (!t || t.length > 140) return false;
  if (SOLO_PETICION.test(t)) return true;
  return DENTRO_DE_FRASE.some((r) => r.test(t)) || EN_INGLES.some((r) => r.test(t));
}

/**
 * ¿Pidió que no le escriban más / dijo que ya no le interesa? Una sola vez basta: no se le
 * vuelve a escribir (regla 10). Conservador a propósito: un seguimiento de menos no molesta.
 */
export function noQuiereSeguimiento(texto: string): boolean {
  const t = sinAcentos(texto);
  return /\b(no (me )?interes|ya no (me )?interes|no estoy interesad|sin interes|no,? gracias|no me (escriba|escriban|escribas|contacte|contacten|contactes|moleste|molesten|molestes|llame|llamen)|dej(e|en|a) de (escribir|mandar|molestar)|no (me )?(vuelva|vuelvan|vuelvas) a (escribir|contactar)|no quiero (nada|mas|recibir)|ya (lo |la |los |las )?compre en otr[oa] (lado|parte|sitio|lugar|tienda)|ya (lo )?consegui|ya no (lo |los |las )?necesito|no necesito nada|borr(e|en|a) mi numero|no me escribas)/.test(t);
}

/** Molestia o reclamo: sube al modelo inteligente. */
export function hayFrustracion(texto: string): boolean {
  const t = sinAcentos(texto);
  return /\b(no sirve|no funciona|horrible|pesim[oa]|mal servicio|molest[oa]|queja|reclamo|estafa|harto|harta|inaceptable|decepcion|me enganaron|es la (segunda|tercera|cuarta) vez|nadie me (contesta|responde)|no me (contestan|responden)|ya les escribi|garantia|devolucion|devolver|defectuos[oa]|danado|dañado|roto|llego mal|llego danado)\b/.test(t);
}
