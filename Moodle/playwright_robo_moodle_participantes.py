import argparse
import os
import csv
import time
import re
import json
import getpass
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import sys
sys.stdout.reconfigure(encoding='utf-8')

# ==========================================
# CONFIGURAÇÕES INICIAIS E CREDENCIAIS
# ==========================================
diretorio_script = os.path.dirname(os.path.abspath(__file__))
diretorio_raiz = os.path.dirname(diretorio_script)
caminho_credenciais = os.path.join(diretorio_raiz, "credenciais.json")

if diretorio_raiz not in sys.path:
    sys.path.insert(0, diretorio_raiz)
try:
    from supabase_sync import sync_to_supabase
except ImportError:
    sync_to_supabase = None

config_moodle = {}
if os.path.exists(caminho_credenciais):
    with open(caminho_credenciais, mode="r", encoding="utf-8") as arquivo_config:
        config = json.load(arquivo_config)
        config_moodle = config.get("moodle", {})

USUARIO_MOODLE = str(config_moodle.get("usuario", "")).strip() or os.getenv("MOODLE_USUARIO", "").strip()
SENHA_MOODLE = str(config_moodle.get("senha", "")).strip() or os.getenv("MOODLE_SENHA", "").strip()

URL_LOGIN = str(config_moodle.get("url_login", "")).strip() or "https://moodle.utfpr.edu.br/login/index.php"
URL_CATEGORIA = str(config_moodle.get("url_categoria", "")).strip() or "https://moodle.utfpr.edu.br/course/management.php?categoryid=1536"

if not USUARIO_MOODLE:
    USUARIO_MOODLE = input("Usuário do Moodle: ").strip()

if not SENHA_MOODLE:
    SENHA_MOODLE = getpass.getpass("Senha do Moodle (oculta): ").strip()

if not USUARIO_MOODLE or not SENHA_MOODLE:
    raise ValueError("Usuário e senha do Moodle são obrigatórios.")

print("===============================================")
print("  🤖 ROBÔ DE EXTRAÇÃO DE PARTICIPANTES 🤖  ")
print("===============================================")

def barra_progresso(atual: int, total: int, largura: int = 24) -> str:
    if total <= 0:
        return "[------------------------] 0%"
    percentual = int((atual / total) * 100)
    preenchido = int((atual / total) * largura)
    barra = "█" * preenchido + "-" * (largura - preenchido)
    return f"[{barra}] {percentual}%"

def log_info(msg: str) -> None:
    print(f"ℹ️ {msg}")

def log_ok(msg: str) -> None:
    print(f"✅ {msg}")

def log_warn(msg: str) -> None:
    print(f"⚠️ {msg}")

def log_error(msg: str) -> None:
    print(f"❌ {msg}")

def parse_args():
    parser = argparse.ArgumentParser(description="Extracao de participantes do Moodle (Playwright).")
    parser.add_argument("--modo", choices=["1", "2"], help="1=visual, 2=headless")
    parser.add_argument("--filtro-modo", default="1", help="1=livre, 2=curso, 3=aluno")
    parser.add_argument("--filtro", help="Filtro de disciplinas ou termo de busca.")
    parser.add_argument("--output", help="Caminho completo do CSV de saida.")
    return parser.parse_args()

args = parse_args()

if args.modo:
    modo_headless = args.modo == "2"
else:
    print("\n[ 1. SELECIONE O MODO DE NAVEGAÇÃO ]")
    print("1 - 👁️ Modo Visual")
    print("2 - 🚀 Modo Ultra Turbo")
    while True:
        escolha_modo = input("\nDigite 1 ou 2 e aperte ENTER: ").strip()
        if escolha_modo in ['1', '2']:
            modo_headless = (escolha_modo == '2')
            break
        else:
            log_error("Opcao invalida.")

if args.filtro is not None:
    termo_filtro = args.filtro.strip().lower()
else:
    print("\n[ 2. FILTRO DE DISCIPLINAS ]")
    termo_filtro = input("Digite o filtro (ex: '2026', vazio = TODAS): ").strip().lower()

dados_extraidos = []

log_info("Iniciando instancia limpa do Chromium...")
navegador = None
contexto = None
pagina = None

try:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=modo_headless)
        contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
        pagina = contexto.new_page()
        pagina.set_default_timeout(10000)

        log_info("Navegando para o Login...")
        pagina.goto(URL_LOGIN, wait_until="domcontentloaded")

        pagina.wait_for_selector("#username")
        pagina.fill("#username", USUARIO_MOODLE)
        pagina.fill("#password", SENHA_MOODLE)
        pagina.click("#loginbtn")
        pagina.wait_for_selector(".userbutton")
        log_ok("Login realizado com sucesso!")

        log_info(f"Acessando a lista de cursos: {URL_CATEGORIA}")
        pagina.goto(URL_CATEGORIA, wait_until="domcontentloaded")
        pagina.wait_for_selector(".course-list")
        elementos_cursos = pagina.locator("li.listitem-course")

        lista_cursos = []
        total_cursos = elementos_cursos.count()
        for i in range(total_cursos):
            elemento = elementos_cursos.nth(i)
            try:
                id_curso = elemento.get_attribute("data-id")
                nome_curso = elemento.locator("a.coursename").first.inner_text().strip()

                if id_curso and nome_curso:
                    # ========================================================
                    # LÓGICA DE FILTRAGEM (ATUALIZADA PARA LISTA MULTIPLA)
                    # ========================================================
                    filtro_modo = getattr(args, "filtro_modo", "1")
                    
                    if not termo_filtro:
                        lista_cursos.append({"id": id_curso, "nome": nome_curso})

                    elif filtro_modo == "2":
                        # Modo Lista de Cursos
                        termos_lista = [t.strip().lower() for t in termo_filtro.split("|") if t.strip()]
                        if any(t in nome_curso.lower() or nome_curso.lower() in t for t in termos_lista):
                            lista_cursos.append({"id": id_curso, "nome": nome_curso})

                    elif filtro_modo == "3":
                        # Filtro por aluno: precisamos extrair alunos de todos os cursos mapeados
                        lista_cursos.append({"id": id_curso, "nome": nome_curso})

                    else:
                        # Modo Texto Livre (mantém comportamento original)
                        if termo_filtro.startswith(">="):
                            try:
                                ano_base = int(termo_filtro.replace(">=", "").strip())
                                numeros_no_curso = [int(num) for num in re.findall(r'\d+', nome_curso)]
                                if any(num >= ano_base for num in numeros_no_curso):
                                    lista_cursos.append({"id": id_curso, "nome": nome_curso})
                            except ValueError:
                                pass
                        elif termo_filtro.startswith(">"):
                            try:
                                ano_base = int(termo_filtro.replace(">", "").strip())
                                numeros_no_curso = [int(num) for num in re.findall(r'\d+', nome_curso)]
                                if any(num > ano_base for num in numeros_no_curso):
                                    lista_cursos.append({"id": id_curso, "nome": nome_curso})
                            except ValueError:
                                pass
                        else:
                            if termo_filtro in nome_curso.lower():
                                lista_cursos.append({"id": id_curso, "nome": nome_curso})
                    # ========================================================
            except Exception:
                continue

        log_ok(f"Foram mapeados {len(lista_cursos)} cursos correspondentes ao seu filtro.")

        total_cursos_filtrados = len(lista_cursos)
        for indice_curso, curso in enumerate(lista_cursos, start=1):
            id_curso = curso["id"]
            nome_curso = curso["nome"]

            url_participantes = f"https://moodle.utfpr.edu.br/user/index.php?id={id_curso}"
            print(f"\n👥 Curso {indice_curso}/{total_cursos_filtrados} {barra_progresso(indice_curso, total_cursos_filtrados)}")
            log_info(f"Extraindo Participantes: {nome_curso} (ID: {id_curso})")
            pagina.goto(url_participantes, wait_until="domcontentloaded")

            try:
                # Botão mostrar todos (Ex: "Mostrar todos os 100")
                try:
                    btn_mostrar_todos = pagina.locator("a[data-action='showcount']")
                    # Espera curta de 3 segundos; se não aparecer, é porque a turma é pequena e não precisa do botão.
                    btn_mostrar_todos.first.wait_for(state="visible", timeout=3000)
                    log_info("Clicando em 'Mostrar todos'...")
                    
                    # O Moodle usa AJAX para carregar a tabela, então não há navegação de página.
                    btn_mostrar_todos.first.click()
                    
                    # Aguardar a requisição AJAX finalizar (rede ociosa) e um tempo curto pro DOM renderizar
                    try:
                        pagina.wait_for_load_state("networkidle", timeout=5000)
                    except PlaywrightTimeoutError:
                        pass # Continua mesmo se a rede não ficar ociosa
                    
                    pagina.wait_for_timeout(1000) # Garantir renderização
                    
                    # Wait for table to be visible again just in case
                    pagina.wait_for_selector("#participants", state="visible")
                except PlaywrightTimeoutError:
                    log_info("Botão 'Mostrar todos' indisponível/desnecessário. Prosseguindo...")
                except Exception as e:
                    log_warn(f"Aviso ao tentar clicar em 'Mostrar todos': {e}")
                
                # Aguarda a tabela
                pagina.wait_for_selector("#participants", timeout=8000)
                linhas_alunos = pagina.locator("#participants tbody tr:not(.emptyrow)")
                total_linhas = linhas_alunos.count()

                for j in range(total_linhas):
                    linha = linhas_alunos.nth(j)
                    
                    try:
                        elemento_nome = linha.locator(".c1").first
                        nome_aluno = elemento_nome.inner_text(timeout=1000).strip()
                        if not nome_aluno:
                            nome_aluno = linha.locator("th, td").nth(1).inner_text(timeout=1000).strip()
                    except Exception:
                        nome_aluno = "Nome não encontrado"

                    try:
                        elemento_email = linha.locator(".c2").first
                        email = elemento_email.inner_text(timeout=1000).strip()
                        if not email or "@" not in email:
                            celulas = linha.locator("td").all_inner_texts()
                            email = next((c.strip() for c in celulas if "@" in c), "Email não encontrado")
                    except Exception:
                        email = "Email não encontrado"
                        
                    try:
                        papel = linha.locator(".c3").first.inner_text(timeout=1000).strip()
                        if not papel:
                            papel = "Estudante" # default guess
                    except Exception:
                        papel = ""

                    try:
                        grupos = linha.locator(".c4").first.inner_text(timeout=1000).strip()
                    except Exception:
                        grupos = ""

                    try:
                        ultimo_acesso = linha.locator(".c5").first.inner_text(timeout=1000).strip()
                    except Exception:
                        ultimo_acesso = ""

                    try:
                        situacao_completa = linha.locator(".c6").first.inner_text(timeout=1000).strip()
                        situacao = situacao_completa.split("\n")[0].strip() if situacao_completa else ""
                    except Exception:
                        situacao = ""

                    if nome_aluno:
                        # ========================================================
                        # FILTRO POR ALUNO (MODO 3)
                        # ========================================================
                        if filtro_modo == "3" and termo_filtro:
                            termos_lista = [t.strip().lower() for t in termo_filtro.split("|") if t.strip()]
                            if not any(t in nome_aluno.lower() or nome_aluno.lower() in t for t in termos_lista):
                                continue

                        dados_extraidos.append({
                            "Disciplina": nome_curso,
                            "ID_Curso": id_curso,
                            "Nome_Aluno": nome_aluno,
                            "Email": email,
                            "Papel": papel,
                            "Grupos": grupos,
                            "Ultimo_Acesso": ultimo_acesso,
                            "Situacao": situacao
                        })

            except PlaywrightTimeoutError:
                log_warn(f"Nenhuma tabela de participantes encontrada na disciplina: {nome_curso}")

    if args.output:
        caminho_completo = os.path.abspath(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"participantes_extraidos_{timestamp}.csv"
        pasta_csvs = os.path.join(diretorio_script, "CSVs")
        os.makedirs(pasta_csvs, exist_ok=True)
        caminho_completo = os.path.join(pasta_csvs, nome_arquivo)
    
    log_info(f"Salvando {len(dados_extraidos)} registros em: {caminho_completo}")
    
    with open(caminho_completo, mode="w", newline="", encoding="utf-8-sig") as arquivo_csv:
        data_extracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        escritor_simples = csv.writer(arquivo_csv, delimiter=";")
        escritor_simples.writerow([data_extracao])

        colunas = ["Disciplina", "ID_Curso", "Nome_Aluno", "Email", "Papel", "Grupos", "Ultimo_Acesso", "Situacao"]
        escritor = csv.DictWriter(arquivo_csv, fieldnames=colunas, delimiter=";")
        escritor.writeheader()
        for dado in dados_extraidos:
            escritor.writerow(dado)
            
    if sync_to_supabase:
        sync_to_supabase("moodle_participantes", dados_extraidos, delete_by_col="id_curso")

    log_ok("EXTRACAO FINALIZADA COM SUCESSO!")
    log_info(f"CSV_GERADO: {caminho_completo}")

except Exception as e:
    import traceback
    log_error(f"Ocorreu um erro critico: {e}")
    traceback.print_exc()
    import sys
    sys.exit(1)
finally:
    time.sleep(2)
    log_info("Instancia do navegador encerrada com seguranca.")
