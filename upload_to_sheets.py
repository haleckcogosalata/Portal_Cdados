"""
upload_to_sheets.py — Módulo de upload de CSV para Google Sheets via Apps Script Web App.

Uso:
    from upload_to_sheets import upload_csv_to_sheet

    sucesso = upload_csv_to_sheet(
        csv_path="caminho/para/arquivo.csv",
        sheet_name="Moodle_DB"
    )
"""

import sys
from pathlib import Path

import requests

# Garante que config.py seja encontrado a partir de qualquer subdiretório
_BASE_DIR = Path(__file__).resolve().parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from config import SHEETS_TOKEN, SHEETS_WEB_APP_URL  # noqa: E402


def upload_csv_to_sheet(
    csv_path: str | Path,
    sheet_name: str,
    web_app_url: str = SHEETS_WEB_APP_URL,
    token: str = SHEETS_TOKEN,
    timeout: int = 120,
) -> bool:
    """
    Lê um arquivo CSV e envia para a aba correta na planilha Google Sheets.

    O Apps Script espera:
        - Linha 1 do CSV: data de extração → ignorada (não vai para a planilha)
        - Linha 2 em diante: cabeçalho + dados → gravados na aba

    Args:
        csv_path:    Caminho do arquivo CSV gerado pelo robô.
        sheet_name:  Nome da aba de destino na planilha (ex: "Moodle_DB").
        web_app_url: URL do Web App do Apps Script (padrão: lido do config.py).
        token:       Token de segurança (padrão: lido do config.py).
        timeout:     Tempo máximo de espera pela resposta HTTP em segundos.

    Returns:
        True se o upload foi bem-sucedido, False caso contrário.
    """
    csv_path = Path(csv_path)

    # Validações pré-envio
    if not web_app_url:
        print(
            "[SHEETS] ⚠️  SHEETS_WEB_APP_URL não configurada em config.py. "
            "Upload pulado."
        )
        return False

    if not csv_path.exists():
        print(f"[SHEETS] ❌ Arquivo CSV não encontrado: {csv_path}")
        return False

    print(f"\n[SHEETS] Enviando '{csv_path.name}' → aba '{sheet_name}'...")

    try:
        csv_content = csv_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        print(f"[SHEETS] ❌ Erro ao ler o CSV: {e}")
        return False

    payload = {
        "token": token,
        "sheet_name": sheet_name,
        "csv_content": csv_content,
    }

    try:
        response = requests.post(web_app_url, data=payload, timeout=timeout)
        response.raise_for_status()

        resultado = response.json()
        status = resultado.get("status", 0)
        mensagem = resultado.get("message", "")

        if status == 200:
            print(f"[SHEETS] ✅ Upload concluído: {mensagem}")
            return True
        else:
            print(f"[SHEETS] ❌ Falha no servidor (status {status}): {mensagem}")
            return False

    except requests.exceptions.Timeout:
        print(
            f"[SHEETS] ⚠️  Timeout após {timeout}s. O Apps Script pode ter "
            "demorado mais do que o esperado (arquivos grandes). "
            "Verifique a planilha manualmente."
        )
        return False
    except requests.exceptions.ConnectionError:
        print("[SHEETS] ❌ Erro de conexão. Verifique a URL e acesso à internet.")
        return False
    except Exception as e:
        print(f"[SHEETS] ❌ Erro inesperado no upload: {e}")
        return False
