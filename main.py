import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

from config import SHEET_NAME_ACADEMICO, SHEET_NAME_MOODLE
from upload_to_sheets import upload_csv_to_sheet


BASE_DIR = Path(__file__).resolve().parent
SCRIPT_MOODLE = BASE_DIR / "Moodle" / "playwright_robo_moodle_notas.py"
SCRIPT_ACADEMICO = BASE_DIR / "Acadêmico" / "playwright_robo_academico_notas.py"


def executar_script(caminho_script: Path, nome: str, args: list[str] | None = None) -> bool:
    if not caminho_script.exists():
        print(f"\n[ERRO] Script nao encontrado: {caminho_script}")
        return False

    print("\n" + "=" * 60)
    print(f"Iniciando extracao: {nome}")
    print("=" * 60)

    try:
        comando = [sys.executable, str(caminho_script)]
        if args:
            comando.extend(args)
            
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        resultado = subprocess.run(comando, check=False, env=env)
        if resultado.returncode == 0:
            print(f"\n[OK] Extracao finalizada: {nome}")
            return True

        print(f"\n[ERRO] {nome} finalizou com codigo {resultado.returncode}.")
        return False

    except KeyboardInterrupt:
        print(f"\n[INTERROMPIDO] Execucao de {nome} cancelada pelo usuario.")
        return False
    except Exception as erro:
        print(f"\n[ERRO] Falha ao executar {nome}: {erro}")
        return False


def selecionar_csv(titulo: str, pasta_inicial: Path | None = None) -> Path | None:
    """Abre um diálogo para o usuário selecionar um arquivo CSV. Retorna Path ou None."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # garante que a janela aparece na frente
    caminho = filedialog.askopenfilename(
        title=titulo,
        initialdir=str(pasta_inicial) if pasta_inicial else str(BASE_DIR),
        filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")],
    )
    root.destroy()
    return Path(caminho) if caminho else None


def exibir_menu() -> None:
    print("\n" + "=" * 60)
    print("CENTRAL DE EXECUCAO - AUTOMACAO POS CDADOS")
    print("=" * 60)
    print("[ EXTRACAO ]")
    print("  1 - Extrair somente Moodle")
    print("  2 - Extrair somente Academico")
    print("  3 - Extrair Moodle e Academico em sequencia (headless)")
    print("  4 - Extrair Moodle e Academico em sequencia (visual)")
    print("")
    print("[ UPLOAD PARA GOOGLE SHEETS ]")
    print("  5 - Enviar CSV do Moodle para a planilha (selecionar arquivo)")
    print("  6 - Enviar CSV do Academico para a planilha (selecionar arquivo)")
    print("")
    print("  0 - Sair")


def main() -> None:
    while True:
        exibir_menu()
        opcao = input("\nEscolha uma opcao e pressione ENTER: ").strip()

        if opcao == "1":
            executar_script(SCRIPT_MOODLE, "Moodle")
        elif opcao == "2":
            executar_script(SCRIPT_ACADEMICO, "Academico")
        elif opcao in {"3", "4"}:
            modo_execucao = "2" if opcao == "3" else "1"
            rotulo_modo = "headless" if opcao == "3" else "visual"
            print(f"\nFluxo automatico Moodle -> Academico ({rotulo_modo})")
            filtro = input(
                "Digite o filtro do Moodle (ex: '2026', '>=2025', 'Big Data' ou ENTER para TODAS): "
            ).strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_moodle = BASE_DIR / "Moodle" / f"notas_extraidas_pipeline_{timestamp}.csv"

            args_moodle = ["--modo", modo_execucao, "--filtro", filtro, "--output", str(csv_moodle)]
            ok_moodle = executar_script(SCRIPT_MOODLE, "Moodle", args_moodle)
            if not ok_moodle:
                print("\nFluxo em sequencia interrompido apos falha no Moodle.")
                continue
            if not csv_moodle.exists():
                print(f"\n[ERRO] CSV esperado nao foi gerado: {csv_moodle}")
                continue

            # --- Upload Moodle → Google Sheets ---
            upload_csv_to_sheet(csv_moodle, SHEET_NAME_MOODLE)

            # --- Localiza o CSV do Acadêmico gerado mais recentemente ---
            csv_academico_antes = set(
                (BASE_DIR / "Acadêmico").glob("Extracao_Geral_SIORG_*.csv")
            )

            args_academico = [
                "--modo",
                modo_execucao,
                "--csv-entrada",
                str(csv_moodle),
                "--filtro-modo",
                "1",
            ]
            executar_script(SCRIPT_ACADEMICO, "Academico", args_academico)

            # --- Upload Acadêmico → Google Sheets ---
            csv_academico_depois = set(
                (BASE_DIR / "Acadêmico").glob("Extracao_Geral_SIORG_*.csv")
            )
            novos_csvs = csv_academico_depois - csv_academico_antes
            if novos_csvs:
                csv_academico = max(novos_csvs, key=lambda p: p.stat().st_mtime)
                upload_csv_to_sheet(csv_academico, SHEET_NAME_ACADEMICO)
            else:
                print("\n[SHEETS] ⚠️  CSV do Acadêmico nao encontrado. Upload pulado.")
        elif opcao == "5":
            print("\n[ UPLOAD MOODLE → GOOGLE SHEETS ]")
            print("Selecione o CSV do Moodle na janela que vai abrir...")
            csv_path = selecionar_csv(
                titulo="Selecione o CSV do Moodle",
                pasta_inicial=BASE_DIR / "Moodle",
            )
            if csv_path:
                upload_csv_to_sheet(csv_path, SHEET_NAME_MOODLE)
            else:
                print("\n[CANCELADO] Nenhum arquivo selecionado.")
        elif opcao == "6":
            print("\n[ UPLOAD ACADEMICO → GOOGLE SHEETS ]")
            print("Selecione o CSV do Academico na janela que vai abrir...")
            csv_path = selecionar_csv(
                titulo="Selecione o CSV do Academico (Extracao_Geral_SIORG)",
                pasta_inicial=BASE_DIR / "Acadêmico",
            )
            if csv_path:
                upload_csv_to_sheet(csv_path, SHEET_NAME_ACADEMICO)
            else:
                print("\n[CANCELADO] Nenhum arquivo selecionado.")
        elif opcao == "0":
            print("\nEncerrando central de execucao.")
            break
        else:
            print("\nOpcao invalida. Tente novamente.")


if __name__ == "__main__":
    main()
