// =============================================================================
// Google_Apps_Script_Code.gs
// =============================================================================
// INSTRUÇÕES DE IMPLANTAÇÃO:
//
//  1. Abra a planilha: https://docs.google.com/spreadsheets/d/1dXhuDILe81LBim6R8KJn6sCvQhZ1FhzyK_FeDiocZDA/
//  2. Menu: Extensões → Apps Script
//  3. Delete todo o conteúdo do editor e cole ESTE arquivo inteiro
//  4. Salve (Ctrl+S)
//  5. Clique em "Implantar" → "Nova implantação"
//  6. Tipo: "App da Web"
//  7. Configurações:
//       - Descrição: "Upload CSV Robô CDADOS"
//       - Executar como: "Eu (seu e-mail)"
//       - Quem pode acessar: "Qualquer pessoa"
//  8. Clique em "Implantar" e autorize as permissões quando solicitado
//  9. COPIE a URL gerada (começa com https://script.google.com/macros/s/...)
// 10. Cole essa URL no arquivo config.py → variável SHEETS_WEB_APP_URL
// =============================================================================

// Token de segurança — deve ser IGUAL ao SHEETS_TOKEN definido em config.py
const SECRET_TOKEN = "TROQUE_PELO_SEU_TOKEN"; // o mesmo valor de SHEETS_TOKEN no .env

/**
 * Recebe uma requisição HTTP POST do script Python e grava os dados CSV
 * na aba correta da planilha, limpando os dados anteriores.
 *
 * Parâmetros esperados no POST (application/x-www-form-urlencoded):
 *   token       — token de segurança
 *   sheet_name  — nome da aba ("Moodle_DB" ou "Acadêmico_DB")
 *   csv_content — conteúdo completo do arquivo CSV (texto)
 */
function doPost(e) {
  try {
    const params = e.parameter;

    // --- Validação do token ---
    if (!params.token || params.token !== SECRET_TOKEN) {
      return resposta(403, "Token inválido ou ausente.");
    }

    const sheetName   = params.sheet_name   || "";
    const csvContent  = params.csv_content  || "";

    if (!sheetName) {
      return resposta(400, "Parâmetro 'sheet_name' ausente.");
    }
    if (!csvContent) {
      return resposta(400, "Parâmetro 'csv_content' está vazio.");
    }

    // --- Localiza a aba de destino ---
    const ss    = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      return resposta(404, "Aba '" + sheetName + "' não encontrada na planilha.");
    }

    // --- Parse do CSV ---
    // Linha 1: data de extração → incluída na planilha
    // Linha 2: cabeçalho
    // Linha 3+: dados
    const linhas = csvContent
      .replace(/\r\n/g, "\n")   // normaliza quebras Windows → Unix
      .replace(/\r/g, "\n")
      .split("\n")
      .filter(function(l) { return l.trim() !== ""; });

    if (linhas.length === 0) {
      return resposta(400, "CSV vazio ou sem conteúdo válido.");
    }

    // Separa por ponto-e-vírgula (padrão dos robôs)
    const dados = linhas.map(function(linha) {
      return linha.split(";");
    });

    // --- Limpa a aba e grava ---
    sheet.clearContents();

    const numLinhas  = dados.length;
    const numColunas = Math.max.apply(null, dados.map(function(r) { return r.length; }));

    // Preenche linhas mais curtas com strings vazias para evitar erro de range
    const dadosPadded = dados.map(function(row) {
      while (row.length < numColunas) row.push("");
      return row;
    });

    sheet.getRange(1, 1, numLinhas, numColunas).setValues(dadosPadded);

    const msg = "OK: " + numLinhas + " linhas gravadas em '" + sheetName + "' (incluindo data e cabeçalho).";
    return resposta(200, msg);

  } catch (err) {
    return resposta(500, "Erro interno no Apps Script: " + err.message);
  }
}

/**
 * Retorna uma resposta JSON padronizada.
 */
function resposta(codigo, msg) {
  return ContentService
    .createTextOutput(JSON.stringify({ status: codigo, message: msg }))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Função de teste manual — rode no editor para verificar se o script acessa
 * a planilha corretamente antes de implantar como Web App.
 */
function testeConexao() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const abas = ss.getSheets().map(function(s) { return s.getName(); });
  Logger.log("Abas encontradas: " + abas.join(", "));
  Logger.log("Título da planilha: " + ss.getName());
}
