import { describe, expect, it } from "vitest";
import {
  acessoMaisRecente,
  buildObservacoes,
  classifyObservacao,
  courseScale,
  evalCondition,
  evalLogic,
  evaluate,
  isDesistente,
  moodleNota0a10,
  normalizeName,
  normalizeText,
  parseUltimoAcesso,
  type RuleSet,
  STATUS_CATALOG,
  validateLogic,
} from "./index";

describe("courseScale (Aux_Nota_de_0_a_10)", () => {
  it("escala 0-100: vale a maior nota", () => {
    expect(courseScale([100, 98.75, 97.5, 90])).toBe(100);
  });
  it("escala 0-10: vale a maior nota", () => {
    expect(courseScale([10, 9.67, 9.5, 8])).toBe(10);
  });
  it("uma nota fora de escala não vira a escala do curso", () => {
    expect(courseScale([55, 10, 9.5, 8])).toBe(10);
  });
  it("só uma nota ou nenhuma", () => {
    expect(courseScale([7])).toBe(7);
    expect(courseScale([])).toBe(0);
  });
  it("com várias notas acima de 10 mantém a maior", () => {
    expect(courseScale([20, 18, 15, 12, 5])).toBe(20);
  });
});

describe("moodleNota0a10 (Nota_de_0_a_10)", () => {
  it.each([
    ["-", 100, null],
    ["", 100, null],
    [null, 10, null],
    ["Erro", 10, 0],
    ["9,9 Ações da célula Ver feedback", 10, 9.9],
    ["9,67", 10, 9.67],
    [98.75, 100, 9.875],
    [10, 20, 1],
    [70, 70, 7],
  ])("%s com escala %s -> %s", (raw, scale, expected) => {
    expect(moodleNota0a10(raw, scale)).toBe(expected);
  });
});

describe("parseUltimoAcesso", () => {
  it("lê dias e horas", () => {
    expect(parseUltimoAcesso("2025_2: 318 dias 14 horas")).toEqual({
      turma: "2025_2",
      segundos: 318 * 86400 + 14 * 3600,
    });
  });
  it("Nunca -> segundos null", () => {
    expect(parseUltimoAcesso("2026_2_turma_9: Nunca")).toEqual({
      turma: "2026_2_turma_9",
      segundos: null,
    });
  });
  it("escolhe o acesso mais recente e ignora Nunca", () => {
    const r = acessoMaisRecente(["a: Nunca", "b: 29 dias 22 horas", "c: 2 dias 22 horas"]);
    expect(r?.turma).toBe("c");
  });
});

describe("nomes e textos", () => {
  it("normalizeName remove acento, caixa e prefixo (Desistente)", () => {
    expect(normalizeName("(Desistente)  André  Ribeiro de Brito")).toBe("ANDRE RIBEIRO DE BRITO");
  });
  it("normalizeText iguala ao normalizarTexto do script", () => {
    expect(normalizeText("  Inscrito em RECUPERAÇÃO ")).toBe("inscrito em recuperacao");
    expect(normalizeText(null)).toBe("");
  });
});

describe("evalLogic", () => {
  const expr = "((1 OR 2) AND (3 OR 4)) OR (5 AND 6) OR (5 AND 7)";
  const c = (...on: number[]) => Array.from({ length: 7 }, (_, i) => on.includes(i + 1));

  it("respeita parênteses e precedência", () => {
    expect(evalLogic(expr, c(1, 3))).toBe(true);
    expect(evalLogic(expr, c(2, 4))).toBe(true);
    expect(evalLogic(expr, c(1))).toBe(false);
    expect(evalLogic(expr, c(5, 7))).toBe(true);
    expect(evalLogic(expr, c(5))).toBe(false);
  });
  it("AND vence OR sem parênteses; aceita minúsculas", () => {
    expect(evalLogic("1 OR 2 AND 3", [true, false, false])).toBe(true);
    expect(evalLogic("1 or 2 and 3", [false, true, false])).toBe(false);
  });
  it("valida e rejeita expressão inválida", () => {
    expect(validateLogic("1 AND (2 OR 3)", 3)).toBeNull();
    expect(validateLogic("(1 AND", 1)).not.toBeNull();
    expect(validateLogic("1 AND 9", 2)).not.toBeNull();
  });
});

describe("evalCondition (semântica do avaliarCondicao)", () => {
  const cond = (op: Parameters<typeof evalCondition>[0]["op"], val: string) => ({
    var: "x",
    op,
    val,
  });
  const run = (op: Parameters<typeof evalCondition>[0]["op"], val: string, x: unknown) =>
    evalCondition(cond(op, val), { vars: { x: x as string } });

  it("vazio não satisfaz >, <, >=, <=", () => {
    expect(run(">=", "7", "")).toBe(false);
    expect(run("<", "7", null)).toBe(false);
  });
  it("vazio contra '0' é falso em == e !=", () => {
    expect(run("==", "0", "")).toBe(false);
    expect(run("!=", "0", "")).toBe(false);
  });
  it("vazio != valor é verdadeiro; vazio == valor é falso", () => {
    expect(run("!=", "Sim", "")).toBe(true);
    expect(run("==", "Sim", "")).toBe(false);
  });
  it("texto compara sem diferenciar caixa", () => {
    expect(run("==", "sim", "SIM")).toBe(true);
    expect(run("==", "*", "*")).toBe(true);
  });
  it("número com vírgula decimal", () => {
    expect(run(">=", "7", "7,5")).toBe(true);
    expect(run("==", "0", "0.0")).toBe(true);
  });
  it("texto contra número não passa em >=", () => {
    expect(run(">=", "7", "*")).toBe(false);
  });
  it("VAZIO e NAO_VAZIO", () => {
    expect(run("VAZIO", "", "  ")).toBe(true);
    expect(run("NAO_VAZIO", "", 0)).toBe(true);
  });
});

describe("evaluate: ordem, exclusões e Sem nota Acad.", () => {
  const rules: RuleSet = {
    regrasLogicas: [
      {
        retorno: "Finalizado",
        condicoes: [
          { var: "sistAcad", op: ">=", val: "7" },
          { var: "posRec", op: ">=", val: "7" },
        ],
        logica: "1 OR 2",
      },
      { retorno: "Inscrito", condicoes: [{ var: "inscritoAtual", op: "==", val: "Sim" }] },
      {
        retorno: "Aprovado ant. em: {passado}",
        condicoes: [{ var: "maxPassado", op: ">=", val: "7" }],
      },
      {
        retorno: "Abandono?",
        condicoes: [
          { var: "sistAcad", op: "==", val: "*" },
          { var: "avaliacao", op: "==", val: "0" },
        ],
        logica: "1 AND 2",
      },
      {
        retorno: "Sem nota Acad.",
        condicoes: [{ var: "sistAcad", op: "VAZIO", val: "" }],
      },
    ],
    regrasExclusao: [
      { mantem: "Aprovado ant. em:", remove: ["Reinscrever", "Abandono?", "Reinscrito em:"] },
      { mantem: "Inscrito", remove: ["Abandono?"] },
    ],
  };

  it("mantém a ordem das regras", () => {
    const out = evaluate(rules, { vars: { sistAcad: 8, inscritoAtual: "Sim" } });
    expect(out).toEqual(["Finalizado", "Inscrito"]);
  });
  it("exclusão por prefixo só vale para rótulos com 'em:'; os outros por igualdade", () => {
    const out = evaluate(
      {
        regrasLogicas: [
          {
            retorno: "Aprovado ant. em: 2025_1",
            condicoes: [{ var: "a", op: "NAO_VAZIO", val: "" }],
          },
          { retorno: "Reinscrito em: 2026_1", condicoes: [{ var: "a", op: "NAO_VAZIO", val: "" }] },
          { retorno: "Reinscrever agora", condicoes: [{ var: "a", op: "NAO_VAZIO", val: "" }] },
        ],
        regrasExclusao: [
          { mantem: "Aprovado ant. em:", remove: ["Reinscrito em:", "Reinscrever"] },
        ],
      },
      { vars: { a: 1 } },
    );
    // "Reinscrito em:" sai por prefixo; "Reinscrever agora" não é igual a "Reinscrever"
    expect(out).toEqual(["Aprovado ant. em: 2025_1", "Reinscrever agora"]);
  });
  it("comparação da exclusão ignora acento e caixa", () => {
    const out = evaluate(
      {
        regrasLogicas: [
          { retorno: "INSCRITO", condicoes: [{ var: "a", op: "NAO_VAZIO", val: "" }] },
          { retorno: "abandono?", condicoes: [{ var: "a", op: "NAO_VAZIO", val: "" }] },
        ],
        regrasExclusao: [{ mantem: "Inscrito", remove: ["Abandono?"] }],
      },
      { vars: { a: 1 } },
    );
    expect(out).toEqual(["INSCRITO"]);
  });
  it("Sem nota Acad. é suprimido antes de a prova expirar", () => {
    const base = { vars: { sistAcad: "" } };
    expect(evaluate(rules, { ...base, provaExpirada: false })).toEqual([]);
    expect(evaluate(rules, { ...base, provaExpirada: true })).toEqual(["Sem nota Acad."]);
  });
  it("expressão inválida conta como falsa e avisa", () => {
    const errors: string[] = [];
    const out = evaluate(
      {
        regrasLogicas: [
          { retorno: "X", condicoes: [{ var: "a", op: "NAO_VAZIO", val: "" }], logica: "1 AND (" },
        ],
        regrasExclusao: [],
      },
      { vars: { a: 1 } },
      { onError: (_r, e) => errors.push(e.message) },
    );
    expect(out).toEqual([]);
    expect(errors).toHaveLength(1);
  });
});

describe("classifyObservacao (formatação condicional)", () => {
  it("Recuperação tem prioridade sobre os demais status do bloco", () => {
    const texto = "Finalizado\n\nInscrito em RECUPERAÇÃO\n\nÚltimo acesso: 2025_2: 3 dias";
    expect(classifyObservacao(texto)?.id).toBe("recuperacao");
  });
  it("Aprovado ant. em: pinta como finalizado", () => {
    expect(classifyObservacao("Aprovado ant. em: 2025_1")?.id).toBe("finalizado");
  });
  it("Sem nota Acad. é vermelho", () => {
    expect(classifyObservacao("Sem nota Acad.")?.background).toBe("#ea4335");
  });
  it("rótulos previstos já têm cor, mas ainda não são produzidos por regra", () => {
    const reservados = STATUS_CATALOG.filter((s) => !s.produced).map((s) => s.id);
    expect(reservados).toEqual(["reinscrito", "reinscrever", "reprovado", "pend-inscricao"]);
    expect(classifyObservacao("Reprovado")?.id).toBe("reprovado");
  });
  it("texto sem status conhecido não pinta", () => {
    expect(classifyObservacao("Inscrito")).toBeNull();
  });
  it("isDesistente", () => {
    expect(isDesistente("Desistente")).toBe(true);
    expect(isDesistente("")).toBe(false);
  });
});

describe("buildObservacoes (bloco completo)", () => {
  const rules: RuleSet = {
    regrasLogicas: [
      { retorno: "Inscrito", condicoes: [{ var: "inscritoAtual", op: "==", val: "Sim" }] },
      {
        retorno: "Aprovado ant. em: {passado}",
        condicoes: [{ var: "maxPassado", op: ">=", val: "7" }],
      },
      { retorno: "Desistente", condicoes: [{ var: "statusG", op: "==", val: "Desistente" }] },
    ],
    regrasExclusao: [],
  };
  const base = {
    turmaAtual: "2025_2",
    disciplina: "AEBC1",
    avaliacao: 9,
    posRec: "",
    sistAcad: "*",
    statusG: "",
    provaExpirada: true,
    historico: [
      { turma: "2025_2", nota0a10: 9, ultimoAcesso: "2025_2: 3 dias 4 horas" },
      { turma: "2025_1", nota0a10: 8 },
      { turma: "RECUPERAÇÃO", nota0a10: null },
    ],
  };

  it("junta regras, recuperação e último acesso separados por linha em branco", () => {
    expect(buildObservacoes(rules, base)).toBe(
      [
        "Inscrito",
        "Aprovado ant. em: 2025_1, RECUPERAÇÃO",
        "Inscrito em RECUPERAÇÃO",
        "Último acesso: 2025_2: 3 dias 4 horas",
      ].join("\n\n"),
    );
  });
  it("maxPassado fica vazio antes de a prova expirar", () => {
    const out = buildObservacoes(rules, { ...base, provaExpirada: false });
    expect(out).not.toContain("Aprovado ant.");
  });
  it("sem nota no passado conta como 0 e não aprova", () => {
    const out = buildObservacoes(rules, {
      ...base,
      historico: [
        { turma: "2025_2", nota0a10: 9 },
        { turma: "2024_2", nota0a10: null },
      ],
    });
    expect(out).not.toContain("Aprovado ant.");
  });
  it("Desistente dispara quando a situação vem da coluna correta", () => {
    expect(buildObservacoes(rules, { ...base, statusG: "Desistente" })).toContain("Desistente");
  });
});
