/**
 * Mesma normalização do `Status.normalizarTexto` do Apps Script: sem acento, minúsculo,
 * espaços colapsados. Serve para comparar rótulos e chaves; não altera o texto exibido.
 */
export function normalizeText(texto: string | null | undefined): string {
  if (texto === null || texto === undefined) return "";
  return String(texto)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Nome canônico para busca: sem acento, caixa alta, sem prefixo "(Desistente)". */
export function normalizeName(nome: string): string {
  return nome
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/^\s*\((desistente|trancado|cancelado)\)\s*/i, "")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
}

/** Compara nomes ignorando acento, caixa e espaços. */
export function sameName(a: string, b: string): boolean {
  return normalizeName(a) === normalizeName(b);
}
