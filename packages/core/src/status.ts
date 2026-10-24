/**
 * Catálogo de status exibidos na matriz. Reproduz a formatação condicional que o
 * `Status.aplicarFormatacaoCondicionalMestre` criava na planilha.
 *
 * `produced: false` marca rótulos previstos mas ainda sem regra que os produza
 * ("Reprovado", "Reinscrever", "Pend. Inscrição", "Reinscrito em:"). Eles já têm cor e
 * prioridade; a definição de quando disparam fica para uma etapa posterior.
 */

export interface StatusDef {
  id: string;
  label: string;
  /** Casamento (sem diferenciar caixa) contra o texto de Observações do bloco. */
  pattern: RegExp;
  background: string;
  foreground: string;
  /** Menor número vence quando mais de um status casa. */
  priority: number;
  produced: boolean;
}

const BLACK = "#000000";
const WHITE = "#ffffff";

export const STATUS_CATALOG: readonly StatusDef[] = [
  {
    id: "recuperacao",
    label: "Inscrito em RECUPERAÇÃO",
    pattern: /RECUPERAÇÃO/i,
    background: "#9fc5e8",
    foreground: BLACK,
    priority: 2,
    produced: true,
  },
  {
    id: "reinscrito",
    label: "Reinscrito em:",
    pattern: /Reinscrito/i,
    background: "#93c47d",
    foreground: BLACK,
    priority: 4,
    produced: false,
  },
  {
    id: "reinscrever",
    label: "Reinscrever",
    pattern: /Reinscrever/i,
    background: "#ff9900",
    foreground: BLACK,
    priority: 4,
    produced: false,
  },
  {
    id: "sem-nota-acad",
    label: "Sem nota Acad.",
    pattern: /Sem nota Acad\./i,
    background: "#ea4335",
    foreground: WHITE,
    priority: 4,
    produced: true,
  },
  {
    id: "reprovado",
    label: "Reprovado",
    pattern: /Reprovado/i,
    background: "#d3d3d3",
    foreground: BLACK,
    priority: 4,
    produced: false,
  },
  {
    id: "finalizado",
    label: "Finalizado",
    pattern: /Finalizado|Cursou anteriormente|ant\. em:/i,
    background: "#b7e1cd",
    foreground: BLACK,
    priority: 4,
    produced: true,
  },
  {
    id: "pend-inscricao",
    label: "Pend. Inscrição",
    pattern: /Pend\. Inscrição/i,
    // Sem cor na planilha original: valor provisório, a definir com o usuário.
    background: "#f9cb9c",
    foreground: BLACK,
    priority: 4,
    produced: false,
  },
] as const;

/** Linha inteira do aluno quando a situação é Desistente (prioridade máxima). */
export const DESISTENTE_STYLE = { background: BLACK, foreground: WHITE } as const;
/** Último acesso há 100 dias ou mais. */
export const ACESSO_ANTIGO_STYLE = { background: "#c7b8ea", foreground: BLACK, dias: 100 } as const;
/** Nota abaixo da média nas colunas de nota. */
export const NOTA_BAIXA_STYLE = { background: "#f4cccc", foreground: BLACK, media: 7 } as const;

/** Status que pinta o bloco: o de menor prioridade numérica entre os que casam. */
export function classifyObservacao(observacoes: string): StatusDef | null {
  let best: StatusDef | null = null;
  for (const def of STATUS_CATALOG) {
    if (!def.pattern.test(observacoes)) continue;
    if (best === null || def.priority < best.priority) best = def;
  }
  return best;
}

export function isDesistente(situacao: string | null | undefined): boolean {
  return /Desistente/i.test(situacao ?? "");
}
