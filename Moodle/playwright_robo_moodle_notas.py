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
print("  🤖 ROBÔ DE EXTRAÇÃO DE NOTAS - UTFPR 🤖  ")
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
    parser = argparse.ArgumentParser(description="Extracao de notas do Moodle (Playwright).")
    parser.add_argument("--modo", choices=["1", "2"], help="1=visual, 2=headless")
    parser.add_argument("--filtro-modo", default="1", help="1=livre, 2=curso, 3=aluno")
    parser.add_argument("--filtro", help="Filtro de disciplinas ou termo de busca.")
    parser.add_argument("--output", help="Caminho completo do CSV de saida.")
    return parser.parse_args()


args = parse_args()

# ==========================================
# FASE 0: ESCOLHA DO MODO DE EXECUÇÃO E FILTROS
# ==========================================
if args.modo:
    modo_headless = args.modo == "2"
else:
    print("\n[ 1. SELECIONE O MODO DE NAVEGAÇÃO ]")
    print("1 - 👁️ Modo Visual (Janela aberta, acompanhamento em tempo real)")
    print("2 - 🚀 Modo Ultra Turbo (Rodar no backend, sem interface gráfica)")
    while True:
        escolha_modo = input("\nDigite 1 ou 2 e aperte ENTER: ").strip()
        if escolha_modo in ['1', '2']:
            modo_headless = (escolha_modo == '2')
            break
        else:
            log_error("Opcao invalida.")

# Solicita o filtro ao usuário
if args.filtro is not None:
    termo_filtro = args.filtro.strip().lower()
    print(f"\n[ 2. FILTRO DE DISCIPLINAS ]\nFiltro recebido via CLI: {termo_filtro or 'TODAS'}")
else:
    print("\n[ 2. FILTRO DE DISCIPLINAS ]")
    termo_filtro = input("Digite o filtro (ex: '2026', 'Turma 7', '>=2025' ou ENTER para TODAS): ").strip().lower()

dados_extraidos = []

# ==========================================
# INÍCIO DO PLAYWRIGHT
# ==========================================
log_info("Iniciando instancia limpa do Chromium...")
navegador = None
contexto = None
pagina = None

try:
    with sync_playwright() as p:
        if modo_headless:
            log_info("Aplicando configuracoes Ultra Turbo (Headless)...")

        navegador = p.chromium.launch(headless=modo_headless)
        contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
        pagina = contexto.new_page()
        pagina.set_default_timeout(10000)

        # ==========================================
        # FASE 1: LOGIN AUTÔNOMO
        # ==========================================
        log_info("Navegando para o Login...")
        pagina.goto(URL_LOGIN, wait_until="domcontentloaded")

        pagina.wait_for_selector("#username")
        pagina.fill("#username", USUARIO_MOODLE)
        pagina.fill("#password", SENHA_MOODLE)
        pagina.click("#loginbtn")

        pagina.wait_for_selector(".userbutton")
        log_ok("Login realizado com sucesso!")

        # ==========================================
        # FASE 2: MAPEAMENTO DOS IDs E NOMES (COM FILTRO AVANÇADO)
        # ==========================================
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
                        # Se for filtro por aluno, precisamos entrar em todos os cursos e buscar os alunos
                        # ou, de preferência, pegamos todos e depois filtramos os alunos
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

        # ==========================================
        # FASE 3: EXTRAÇÃO DE NOTAS POR CURSO
        # ==========================================
        total_cursos_filtrados = len(lista_cursos)
        for indice_curso, curso in enumerate(lista_cursos, start=1):
            id_curso = curso["id"]
            nome_curso = curso["nome"]

            url_notas = f"https://moodle.utfpr.edu.br/grade/report/grader/index.php?id={id_curso}"
            print(f"\n📚 Curso {indice_curso}/{total_cursos_filtrados} {barra_progresso(indice_curso, total_cursos_filtrados)}")
            log_info(f"Extraindo: {nome_curso} (ID: {id_curso})")
            pagina.goto(url_notas, wait_until="domcontentloaded")

            try:
                pagina.wait_for_selector("tr.userrow", timeout=5000)
                linhas_alunos = pagina.locator("tr.userrow")
                total_linhas = linhas_alunos.count()

                for j in range(total_linhas):
                    linha = linhas_alunos.nth(j)

                    # NOME
                    try:
                        elemento_nome = linha.locator(".username, th.user").first
                        nome_cru = elemento_nome.evaluate("""
                            (elemento) => {
                                let texto = '';
                                for (let i = 0; i < elemento.childNodes.length; i++) {
                                    if (elemento.childNodes[i].nodeType === 3) {
                                        texto += elemento.childNodes[i].textContent;
                                    }
                                }
                                return texto;
                            }
                        """)

                        nome_aluno = " ".join(nome_cru.split())

                        if not nome_aluno:
                            nome_completo = elemento_nome.text_content() or ""
                            nome_aluno = nome_completo.strip().split(" Ações da célula")[0].strip()

                    except Exception:
                        nome_aluno = "Nome não encontrado"

                    # EMAIL
                    try:
                        elemento_email = linha.locator("td[data-col='email'], td[class*='email']").first
                        email = (elemento_email.text_content() or "").strip()
                    except Exception:
                        email = "Email não encontrado"

                    # NOTA
                    try:
                        elemento_nota = linha.locator("td.lastcol .gradevalue, td.lastcol").first
                        nota_cru = (elemento_nota.text_content() or "").strip()
                        nota_final = " ".join(nota_cru.split())
                    except Exception:
                        nota_final = "Sem nota"

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
                            "Nota_Final": nota_final
                        })

            except PlaywrightTimeoutError:
                log_warn(f"Nenhuma tabela de notas ou erro na disciplina: {nome_curso}")

    # ==========================================
    # FASE 4: EXPORTAÇÃO PARA CSV
    # ==========================================
    if args.output:
        caminho_completo = os.path.abspath(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"notas_extraidas_{timestamp}.csv"
        pasta_csvs = os.path.join(diretorio_script, "CSVs")
        os.makedirs(pasta_csvs, exist_ok=True)
        caminho_completo = os.path.join(pasta_csvs, nome_arquivo)
    
    log_info(f"Salvando {len(dados_extraidos)} registros em: {caminho_completo}")
    
    with open(caminho_completo, mode="w", newline="", encoding="utf-8-sig") as arquivo_csv:
        data_extracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        escritor_simples = csv.writer(arquivo_csv, delimiter=";")
        escritor_simples.writerow([data_extracao]) 
        
        colunas = ["Disciplina", "ID_Curso", "Nome_Aluno", "Email", "Nota_Final"]
        escritor = csv.DictWriter(arquivo_csv, fieldnames=colunas, delimiter=";")
        
        escritor.writeheader()
        for dado in dados_extraidos:
            escritor.writerow(dado)
            
    if sync_to_supabase:
        sync_to_supabase("moodle_notas", dados_extraidos, delete_by_col="id_curso")

    log_ok("EXTRACAO FINALIZADA COM SUCESSO!")
    log_info("Pode abrir seu Excel.")
    log_info(f"CSV_GERADO: {caminho_completo}")

except Exception as e:
    log_error(f"Ocorreu um erro critico: {e}")

finally:
    time.sleep(2)
    # O bloco "with sync_playwright()" já encerra contexto/navegador automaticamente.
    log_info("Instancia do navegador encerrada com seguranca.")