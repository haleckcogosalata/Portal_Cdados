# =============================================================================
# config.py — Configurações da integração com Google Sheets e Supabase
# =============================================================================
# Segredos ficam no arquivo .env (não versionado). Copie .env.example para .env.
# Após implantar o Apps Script como Web App, cole a URL gerada em SHEETS_WEB_APP_URL no .env.
# Consulte o arquivo "Google_Apps_Script_Code.gs" para as instruções de implantação.
# =============================================================================
import os
from pathlib import Path


def _carregar_env() -> None:
    arquivo = Path(__file__).resolve().parent / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()

# URL do Web App gerada após a implantação no Google Apps Script.
# Exemplo: "https://script.google.com/macros/s/AKfycb.../exec"
SHEETS_WEB_APP_URL = os.environ.get("SHEETS_WEB_APP_URL", "")

# Token de segurança: deve ser IGUAL ao definido no Apps Script (variável SECRET_TOKEN).
SHEETS_TOKEN = os.environ.get("SHEETS_TOKEN", "")

# Nomes das abas na planilha Google Sheets (não altere sem ajustar a planilha também).
SHEET_NAME_MOODLE = "Moodle_DB"
SHEET_NAME_ACADEMICO = "Acadêmico_DB"
SHEET_NAME_PARTICIPANTES = "Moodle_acessos_DB"

# =============================================================================
# Configurações do Supabase
# =============================================================================
# Os robôs gravam com a service_role (ignora o RLS). A chave fica no arquivo .env, que não
# vai para o Git. Copie .env.example para .env e preencha SUPABASE_SERVICE_ROLE_KEY.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fxttktzaftptzsyjexiq.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
