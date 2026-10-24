export interface UltimoAcesso {
  turma: string;
  /** null quando o aluno nunca acessou. */
  segundos: number | null;
}

const UNIDADES: Array<[RegExp, number]> = [
  [/(\d+)\s*anos?/i, 365 * 86400],
  [/(\d+)\s*dias?/i, 86400],
  [/(\d+)\s*horas?/i, 3600],
  [/(\d+)\s*min(?:uto)?s?/i, 60],
  [/(\d+)\s*seg(?:undo)?s?/i, 1],
];

/** "2025_2: 318 dias 14 horas" -> { turma: "2025_2", segundos: 27468000 }. "Nunca" -> null. */
export function parseUltimoAcesso(texto: string | null | undefined): UltimoAcesso | null {
  if (!texto) return null;
  const sep = texto.indexOf(":");
  if (sep < 0) return null;
  const turma = texto.slice(0, sep).trim();
  const resto = texto.slice(sep + 1).trim();
  if (/^nunca$/i.test(resto)) return { turma, segundos: null };
  let total = 0;
  let achou = false;
  for (const [re, fator] of UNIDADES) {
    const m = resto.match(re);
    if (m?.[1]) {
      total += Number(m[1]) * fator;
      achou = true;
    }
  }
  return achou ? { turma, segundos: total } : null;
}

/** Acesso mais recente entre vários (menor tempo decorrido). Ignora "Nunca". */
export function acessoMaisRecente(textos: Array<string | null | undefined>): UltimoAcesso | null {
  let melhor: UltimoAcesso | null = null;
  for (const t of textos) {
    const a = parseUltimoAcesso(t);
    if (a?.segundos == null) continue;
    if (melhor === null || a.segundos < (melhor.segundos ?? Number.POSITIVE_INFINITY)) melhor = a;
  }
  return melhor;
}
