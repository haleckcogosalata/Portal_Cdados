/**
 * Motor de regras. Porta fiel do `Status.gs` (Apps Script) sem `eval`.
 *
 * - `logica` combina as condições (numeradas a partir de 1) com AND/OR e parênteses;
 *   AND tem precedência sobre OR; vazio = todas com AND.
 * - As regras valem na ordem da lista; essa ordem é a ordem dos rótulos no resultado.
 * - Comparações de texto ignoram caixa e espaços nas pontas.
 */

import { normalizeText } from "./names";

export type Operator = "==" | "!=" | ">" | ">=" | "<" | "<=" | "VAZIO" | "NAO_VAZIO";

export interface Condition {
  var: string;
  op: Operator;
  val: string;
}

export interface Rule {
  retorno: string;
  condicoes: Condition[];
  logica?: string;
}

export interface ExclusionRule {
  mantem: string;
  remove: string[];
}

export interface RuleSet {
  regrasLogicas: Rule[];
  regrasExclusao: ExclusionRule[];
}

export type VarValue = string | number | null | undefined;

export interface RuleContext {
  vars: Record<string, VarValue>;
  /** Valores de `{passado}`, `{futuro}`, `{disciplina}`, `{proximas_turmas}`. */
  placeholders?: Record<string, string>;
  /**
   * Regra especial do script: o rótulo "Sem nota Acad." só vale depois que a data final da
   * avaliação passou. Quando não informado, o rótulo nunca é suprimido.
   */
  provaExpirada?: boolean;
}

// ---------------------------------------------------------------------------
// Expressão lógica
// ---------------------------------------------------------------------------

type Token = "(" | ")" | "AND" | "OR" | number;

function tokenize(expr: string): Token[] {
  const tokens: Token[] = [];
  const re = /\s*(\(|\)|AND|OR|\d+)/y;
  let pos = 0;
  while (pos < expr.length) {
    re.lastIndex = pos;
    const m = re.exec(expr);
    if (!m?.[1]) {
      if (expr.slice(pos).trim() === "") break;
      throw new Error(`Expressão inválida em "${expr.slice(pos)}"`);
    }
    const t = m[1];
    tokens.push(/^\d+$/.test(t) ? Number(t) : (t as Token));
    pos = re.lastIndex;
  }
  return tokens;
}

/** Avalia a expressão. `conds[i]` é o resultado da condição i+1. */
export function evalLogic(expr: string, conds: boolean[]): boolean {
  const tokens = tokenize(expr.toUpperCase());
  let i = 0;

  const parseOr = (): boolean => {
    let left = parseAnd();
    while (tokens[i] === "OR") {
      i++;
      const right = parseAnd();
      left = left || right;
    }
    return left;
  };
  const parseAnd = (): boolean => {
    let left = parseAtom();
    while (tokens[i] === "AND") {
      i++;
      const right = parseAtom();
      left = left && right;
    }
    return left;
  };
  const parseAtom = (): boolean => {
    const t = tokens[i++];
    if (t === "(") {
      const v = parseOr();
      if (tokens[i++] !== ")") throw new Error("Parêntese não fechado");
      return v;
    }
    if (typeof t === "number") {
      if (t < 1 || t > conds.length) throw new Error(`Condição ${t} não existe`);
      return conds[t - 1] as boolean;
    }
    throw new Error(`Token inesperado: ${String(t)}`);
  };

  const result = parseOr();
  if (i !== tokens.length) throw new Error("Expressão com sobra de tokens");
  return result;
}

// ---------------------------------------------------------------------------
// Condições
// ---------------------------------------------------------------------------

const isBlank = (v: unknown) => v === null || v === undefined || String(v).trim() === "";

/** `parseNumero` do script: texto numérico vira número, o resto fica como texto. */
function parseNumero(v: VarValue): number | string {
  if (typeof v === "number") return v;
  if (v === null || v === undefined) return "";
  const s = String(v).trim();
  if (s === "") return "";
  return /^-?\d+([.,]\d+)?$/.test(s) ? Number.parseFloat(s.replace(",", ".")) : s;
}

/** Comparação ordenada com a coerção do JavaScript usada no script original. */
function ordered(a: number | string, b: number | string, op: ">" | ">=" | "<" | "<="): boolean {
  const x = typeof a === "string" && typeof b === "string" ? a : Number(a);
  const y = typeof a === "string" && typeof b === "string" ? b : Number(b);
  if (op === ">") return x > y;
  if (op === ">=") return x >= y;
  if (op === "<") return x < y;
  return x <= y;
}

export function evalCondition(c: Condition, ctx: RuleContext): boolean {
  const raw = ctx.vars[c.var];
  const valBlank = isBlank(raw);

  if (c.op === "VAZIO") return valBlank;
  if (c.op === "NAO_VAZIO") return !valBlank;
  if ((valBlank || isBlank(c.val)) && [">", "<", ">=", "<="].includes(c.op)) return false;
  if (valBlank && c.val.trim() === "0") return false;

  const val = parseNumero(raw);
  const comp = parseNumero(c.val);
  const bothNumbers = typeof val === "number" && typeof comp === "number";
  const sameText = String(val).trim().toLowerCase() === String(comp).trim().toLowerCase();

  switch (c.op) {
    case "==":
      return bothNumbers ? val === comp : sameText;
    case "!=":
      return bothNumbers ? val !== comp : !sameText;
    default:
      return ordered(val, comp, c.op);
  }
}

export function evalRule(rule: Rule, ctx: RuleContext): boolean {
  if (rule.condicoes.length === 0) return false;
  const results = rule.condicoes.map((c) => evalCondition(c, ctx));
  const logica = rule.logica?.trim();
  return logica ? evalLogic(logica, results) : results.every(Boolean);
}

/** Valida a expressão sem avaliar dados reais. Devolve a mensagem de erro, ou null se válida. */
export function validateLogic(expr: string, conditionCount: number): string | null {
  try {
    evalLogic(expr, new Array<boolean>(conditionCount).fill(true));
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}

// ---------------------------------------------------------------------------
// Avaliação do conjunto de regras
// ---------------------------------------------------------------------------

function fillPlaceholders(text: string, ph: Record<string, string> = {}): string {
  return text.replace(/\{(\w+)\}/g, (_, k: string) => ph[k] ?? "");
}

export interface EvaluateOptions {
  /** Chamado quando uma regra tem expressão inválida; a regra conta como falsa. */
  onError?: (rule: Rule, error: Error) => void;
}

/**
 * Rótulos que disparam, na ordem das regras, já depois das exclusões.
 *
 * Exclusão: se algum rótulo começa com `mantem` (sem acento e sem caixa), cada item de
 * `remove` sai da lista. Item com "em:" sai por prefixo; os demais só saem por igualdade exata.
 * As exclusões são aplicadas em sequência, na ordem da configuração.
 */
export function evaluate(
  ruleSet: RuleSet,
  ctx: RuleContext,
  options: EvaluateOptions = {},
): string[] {
  let labels: string[] = [];

  for (const rule of ruleSet.regrasLogicas) {
    let fired = false;
    try {
      fired = evalRule(rule, ctx);
    } catch (e) {
      options.onError?.(rule, e instanceof Error ? e : new Error(String(e)));
    }
    if (!fired) continue;

    const text = fillPlaceholders(rule.retorno, ctx.placeholders);
    if (text.includes("Sem nota Acad.") && ctx.provaExpirada === false) continue;
    labels.push(text);
  }

  for (const ex of ruleSet.regrasExclusao) {
    const keep = normalizeText(ex.mantem);
    if (!labels.some((l) => normalizeText(l).startsWith(keep))) continue;
    for (const rm of ex.remove) {
      const rmNorm = normalizeText(rm);
      labels = labels.filter((l) => {
        const n = normalizeText(l);
        return rmNorm.includes("em:") ? !n.startsWith(rmNorm) : n !== rmNorm;
      });
    }
  }
  return labels;
}
