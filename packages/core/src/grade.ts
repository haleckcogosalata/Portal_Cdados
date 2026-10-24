/**
 * Notas do Moodle -> escala 0-10. Porta das fórmulas `Aux_Nota_de_0_a_10` (G) e
 * `Nota_de_0_a_10` (H) da aba `Moodle_Aux` da planilha Notas_DB.
 */

/**
 * Escala do curso (um valor por par turma + curso). Recebe apenas as notas que o Moodle
 * entregou como número (a planilha usa `ISNUMBER`).
 *
 * Ordena em ordem decrescente. A escala só é tratada como 0-10 quando a maior nota passa
 * de 10 e uma das três seguintes é <= 10 (isto é, a maior é um valor fora de escala).
 * Nesse caso vale a maior nota <= 10; senão vale a maior nota. Sem notas, 0.
 */
export function courseScale(grades: number[]): number {
  const sorted = [...grades].sort((a, b) => b - a);
  const count = sorted.length;
  const max1 = sorted[0] ?? 0;
  const max2 = count >= 2 ? (sorted[1] as number) : max1;
  const max3 = count >= 3 ? (sorted[2] as number) : max2;
  const max4 = count >= 4 ? (sorted[3] as number) : max3;
  const isScale10 = max1 > 10 && (max2 <= 10 || max3 <= 10 || max4 <= 10);
  if (!isScale10) return max1;
  return Math.max(0, ...sorted.filter((g) => g <= 10));
}

/**
 * Nota crua do Moodle -> 0-10.
 * - vazio ou "-" -> null (sem nota);
 * - usa a primeira palavra do texto ("9,9 Ações da célula Ver feedback" -> 9,9);
 * - texto não numérico (ex.: "Erro") vira 0, como na planilha;
 * - se a escala do curso passa de 10, divide por 10.
 */
export function moodleNota0a10(
  raw: string | number | null | undefined,
  scale: number,
): number | null {
  if (raw === null || raw === undefined) return null;
  const text = String(raw).trim();
  if (text === "" || text === "-") return null;
  const token = text.split(/\s+/)[0] ?? "";
  const value = /^-?\d+(?:[.,]\d+)?$/.test(token) ? Number(token.replace(",", ".")) : 0;
  return scale > 10 ? value / 10 : value;
}
