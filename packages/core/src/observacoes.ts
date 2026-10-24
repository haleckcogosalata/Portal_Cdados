/**
 * Monta as variáveis e o texto de `Observações` de um bloco (aluno x disciplina x turma),
 * reproduzindo `Status.processarTodasDisciplinas`.
 */

import { normalizeText } from "./names";
import {
  type EvaluateOptions,
  evaluate,
  type RuleContext,
  type RuleSet,
  type VarValue,
} from "./rules";

/** Uma linha do Moodle para o aluno nesta disciplina (uma por turma em que esteve inscrito). */
export interface MoodleEnrollment {
  /** Ex.: "2025_2", "2026_1_turma_7" ou "RECUPERAÇÃO". */
  turma: string;
  nota0a10: number | null;
  /** Texto "Último acesso" da disciplina nessa turma. */
  ultimoAcesso?: string | null;
}

export interface BlockInput {
  turmaAtual: string;
  disciplina: string;
  /** Valores das três colunas de nota do bloco. */
  avaliacao: VarValue;
  posRec: VarValue;
  sistAcad: VarValue;
  /**
   * Situação do aluno (coluna "SITUAÇÃO"). No script original lia a coluna H (TIPO), que
   * estava vazia, e por isso o rótulo "Desistente" nunca disparava. Aqui vem de quem chama.
   */
  statusG: VarValue;
  historico: MoodleEnrollment[];
  /** `hoje > data final da avaliação` (linha 5 do bloco). */
  provaExpirada: boolean;
  proximasTurmas?: string;
}

export interface BlockContext extends RuleContext {
  inscritoRecuperacao: boolean;
  textoUltimoAcesso: string;
}

const same = (a: string, b: string) => a.trim() === b.trim();

export function buildBlockContext(input: BlockInput): BlockContext {
  const hist = input.historico;
  const passado = hist.filter((m) => !same(m.turma, input.turmaAtual));

  // Math.max trata "sem nota" como 0, como no script. Sem histórico, -1.
  const notaMaxPassado = passado.length > 0 ? Math.max(...passado.map((m) => m.nota0a10 ?? 0)) : -1;
  const inscritoRecuperacao = hist.some((m) => normalizeText(m.turma) === "recuperacao");
  const atual = hist.find((m) => same(m.turma, input.turmaAtual));
  const acesso = atual?.ultimoAcesso?.trim();

  return {
    vars: {
      avaliacao: input.avaliacao,
      posRec: input.posRec,
      sistAcad: input.sistAcad,
      statusG: input.statusG,
      maxPassado: input.provaExpirada ? notaMaxPassado : "",
      inscritoAtual: atual ? "Sim" : "Não",
      // O script fixa "Não": a ideia de turmas futuras nunca foi implementada.
      reinscrito: "Não",
      inscritoRecuperacao: inscritoRecuperacao ? "Sim" : "Não",
    },
    placeholders: {
      passado: [...new Set(passado.map((m) => m.turma))].join(", "),
      futuro: "",
      disciplina: input.disciplina,
      proximas_turmas: input.proximasTurmas ?? "Sem previsão no cronograma",
    },
    provaExpirada: input.provaExpirada,
    inscritoRecuperacao,
    textoUltimoAcesso: acesso ? `Último acesso: ${acesso}` : "",
  };
}

/** Rótulos das regras, depois "Inscrito em RECUPERAÇÃO" e "Último acesso: …" (nunca excluídos). */
export function buildObservacoesLines(
  ruleSet: RuleSet,
  input: BlockInput,
  options?: EvaluateOptions,
): string[] {
  const ctx = buildBlockContext(input);
  const lines = evaluate(ruleSet, ctx, options);
  if (ctx.inscritoRecuperacao) lines.push("Inscrito em RECUPERAÇÃO");
  if (ctx.textoUltimoAcesso) lines.push(ctx.textoUltimoAcesso);
  return lines;
}

/** Texto da célula, com as linhas separadas por uma linha em branco. */
export function buildObservacoes(
  ruleSet: RuleSet,
  input: BlockInput,
  options?: EvaluateOptions,
): string {
  return buildObservacoesLines(ruleSet, input, options).join("\n\n");
}
