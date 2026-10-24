import csv
import argparse
import getpass
import json
import os
import re
import tkinter as tk
import unicodedata
from datetime import datetime
from tkinter import filedialog

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
import sys

try:
    from config import USUARIO_SIORG_CFG as USUARIO_SIORG, SENHA_SIORG_CFG as SENHA_SIORG
except ImportError:
    pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from supabase_sync import get_name_adjustments
except ImportError:
    def get_name_adjustments():
        return {}


# ==========================================
# CONFIGURACOES DE TEMPO (Em milissegundos)
# Ajuste estes valores para acelerar ou estabilizar o robô
# ==========================================
TIMEOUT_PADRAO = 10000            # Espera maxima geral da pagina inteira
TEMPO_ESPERA_SPA = 1000           # Respiro (delay fixo) para o Angular estabilizar rotas
TIMEOUT_CAMPUS_APARECER = 2000    # Tempo limite para a tela de 'Selecionar Campus' aparecer
TIMEOUT_CAMPUS_SUMIR = 2000       # Tempo limite para a tela de Campus fechar apos o clique
TIMEOUT_CAMPO_PESQUISA = 3000     # Tempo limite para achar o campo de aluno a primeira vez
TIMEOUT_VERIFICA_FRAME = 500      # [NOVO] Tempo rapido de checagem para não travar o loop entre alunos
DELAY_ANTES_LIMPAR = 300          # [NOVO] Pausa antes de apagar o nome do aluno anterior
DELAY_APOS_PREENCHER = 500        # Pausa apos colar o nome e antes de apertar a tecla TAB
TIMEOUT_DROPDOWN_NOMES = 6000     # [AJUSTADO] Tempo para o sistema carregar os nomes semelhantes (AJAX)
TIMEOUT_DROPDOWN_VINCULOS = 4000  # [AJUSTADO] Tempo para o dropdown de periodos/vinculos carregar
TIMEOUT_TEXTO_CURSO = 2000        # [AJUSTADO] Tempo de checagem rapida da palavra "Ciencia de Dados"
TIMEOUT_TABELA_HISTORICO = 8000   # [AJUSTADO] Tempo maximo esperando o boletim carregar após clicar em Buscar
TIMEOUT_CABEALUNO = 5000          # [NOVO] Tempo limite para o cabeçalho com os dados do aluno aparecer

# ==========================================
# CONFIGURACOES INICIAIS E CREDENCIAIS
# ==========================================
URL_LOGIN_PADRAO = "https://sistemas2.utfpr.edu.br/home"
URL_PESQUISA_PADRAO = "https://sistemas2.utfpr.edu.br/url/1494"

diretorio_script = os.path.dirname(os.path.abspath(__file__))
diretorio_raiz = os.path.dirname(diretorio_script)
PASTA_DEBUG = os.path.join(diretorio_raiz, "Debug")
os.makedirs(PASTA_DEBUG, exist_ok=True)

caminho_credenciais = os.path.join(diretorio_raiz, "credenciais.json")

if diretorio_raiz not in sys.path:
    sys.path.insert(0, diretorio_raiz)
try:
    from supabase_sync import sync_to_supabase
except ImportError:
    sync_to_supabase = None

config_siorg = {}
if os.path.exists(caminho_credenciais):
    with open(caminho_credenciais, mode="r", encoding="utf-8") as arquivo_config:
        config = json.load(arquivo_config)
        config_siorg = config.get("siorg", {})

USUARIO_SIORG = str(config_siorg.get("usuario", "")).strip() or os.getenv("SIORG_USUARIO", "").strip()
SENHA_SIORG = str(config_siorg.get("senha", "")).strip() or os.getenv("SIORG_SENHA", "").strip()
URL_LOGIN = str(config_siorg.get("url_login", "")).strip() or URL_LOGIN_PADRAO
URL_PESQUISA = str(config_siorg.get("url_pesquisa", "")).strip() or URL_PESQUISA_PADRAO

if not USUARIO_SIORG:
    USUARIO_SIORG = input("Usuario do SIORG: ").strip()

if not SENHA_SIORG:
    SENHA_SIORG = getpass.getpass("Senha do SIORG (oculta): ").strip()

if not USUARIO_SIORG or not SENHA_SIORG:
    raise ValueError("Usuario e senha do SIORG sao obrigatorios.")

print("===============================================")
print("   ROBO DO SIORG - UTFPR (VERSAO PLAYWRIGHT)   ")
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


def log_falha(msg: str) -> None:
    print(f"⛔ {msg}")


def log_error(msg: str) -> None:
    print(f"❌ {msg}")


def parse_args():
    parser = argparse.ArgumentParser(description="Extracao de historico academico SIORG (Playwright).")
    parser.add_argument("--modo", choices=["1", "2"], help="1=visual, 2=headless")
    parser.add_argument("--csv-entrada", help="Caminho do CSV de entrada de alunos (gerado pelo Moodle).")
    parser.add_argument("--filtro-modo", choices=["1", "2", "3"], help="1=todos, 2=curso, 3=aluno")
    parser.add_argument("--termo", default="", help="Termo usado no filtro 2/3.")
    parser.add_argument("--ignorar-estado", action="store_true", help="Ignora o estado salvo e recomeca do zero.")
    return parser.parse_args()


args = parse_args()


def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    texto_normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto_normalizado if unicodedata.category(c) != "Mn")


def preparar_nome_busca(texto: str) -> str:
    texto_sem_acento = remover_acentos(texto)
    texto_sem_abrev = re.sub(r"(?<!\S)[A-Za-z]\.?(?!\S)", "", texto_sem_acento)
    return re.sub(r"\s+", " ", texto_sem_abrev).strip()


def selecionar_e_ler_csv(modo_filtro: str, termo: str, caminho_arquivo: str | None = None) -> list[str]:
    # Se modo_filtro for 3 (Por Aluno) e não houver CSV, usamos diretamente os nomes fornecidos.
    if modo_filtro == "3" and (not caminho_arquivo or not os.path.exists(caminho_arquivo)):
        alunos = [t.strip() for t in termo.split("|") if t.strip()]
        if alunos:
            print(f"Buscando alunos por nome fornecido manualmente (sem CSV): {alunos}")
            return alunos

    if not caminho_arquivo:
        root = tk.Tk()
        root.withdraw()
        print("\nAguardando selecao do arquivo CSV com a lista de alunos...")
        caminho_arquivo = filedialog.askopenfilename(
            title="Selecione o arquivo CSV com a lista de alunos",
            filetypes=[("Arquivos CSV", "*.csv")],
        )
    else:
        caminho_arquivo = os.path.abspath(caminho_arquivo)
        print(f"\nUsando CSV informado via CLI: {caminho_arquivo}")

    if not caminho_arquivo:
        print("Nenhum arquivo selecionado. Operacao cancelada.")
        return []

    alunos_extraidos: list[str] = []
    emails_processados: set[str] = set()

    try:
        with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as arquivo:
            leitor = csv.reader(arquivo, delimiter=";")
            next(leitor, None)  # linha 1
            next(leitor, None)  # linha 2

            for linha in leitor:
                if len(linha) < 4:
                    continue

                nome_curso = linha[0].strip()
                nome_aluno = linha[2].strip()
                email_aluno = linha[3].strip().lower()

                if not nome_aluno or email_aluno in emails_processados:
                    continue

                adicionar = False
                if modo_filtro == "1":
                    adicionar = True
                elif modo_filtro in ["2", "3"]:
                    termos_lista = [t.strip().lower() for t in termo.split("|") if t.strip()]
                    alvo = nome_curso.lower() if modo_filtro == "2" else nome_aluno.lower()
                    if any(t in alvo or alvo in t for t in termos_lista) if termos_lista else True:
                        adicionar = True

                if adicionar:
                    alunos_extraidos.append(nome_aluno)
                    emails_processados.add(email_aluno)

    except Exception as erro:
        print(f"Erro ao ler o CSV: {erro}")
        return []

    print(f"Arquivo carregado! {len(alunos_extraidos)} aluno(s) unicos passaram no filtro.")
    return alunos_extraidos


def encontrar_campo_pessoa(frame_scope, tempo_espera):
    try:
        frame_scope.locator("#p_pessoa").wait_for(state="visible", timeout=tempo_espera)
        return frame_scope, frame_scope.locator("#p_pessoa")
    except PlaywrightTimeoutError:
        return None, None


def selecionar_campus_dois_vizinhos(pagina, obrigatorio: bool = False) -> bool:
    botao_campus = pagina.locator("//button[.//span[normalize-space(text())='Dois Vizinhos']]")
    try:
        botao_campus.wait_for(state="visible", timeout=TIMEOUT_CAMPUS_APARECER)
        log_warn("Tela de campus detectada. Reaplicando selecao de campus...")
        botao_campus.click()
        
        botao_campus.wait_for(state="hidden", timeout=TIMEOUT_CAMPUS_SUMIR)
        pagina.wait_for_timeout(TEMPO_ESPERA_SPA) 
        
        log_ok("Campus Dois Vizinhos selecionado com sucesso!")
        return True
    except PlaywrightTimeoutError:
        if obrigatorio:
            log_warn("Botao de campus nao encontrado nesta etapa. Seguindo...")
        return False


def preparar_tela_pesquisa(pagina, primeiro_acesso=False):
    import time
    for tentativa in range(1, 4):
        try:
            pagina.goto(URL_PESQUISA, wait_until="domcontentloaded")
            if primeiro_acesso:
                pagina.wait_for_timeout(TEMPO_ESPERA_SPA) 
        except Exception as e:
            log_warn(f"Pequeno erro de carregamento ignorado: {e}")

        if primeiro_acesso:
            if selecionar_campus_dois_vizinhos(pagina):
                continue

        timeout_total = 15000 if primeiro_acesso else 10000
        start = time.time()
        active_scope, campo_pessoa = None, None
        
        while time.time() - start < timeout_total / 1000.0:
            # 1. Checa a main page
            try:
                loc_main = pagina.locator("#p_pessoa")
                if loc_main.count() > 0 and loc_main.is_visible():
                    active_scope, campo_pessoa = pagina, loc_main
                    break
            except Exception:
                pass
                
            # 2. Checa todos os frames
            for frame in pagina.frames:
                try:
                    loc_frame = frame.locator("#p_pessoa")
                    if loc_frame.count() > 0 and loc_frame.is_visible():
                        active_scope, campo_pessoa = frame, loc_frame
                        break
                except Exception:
                    pass
            
            if campo_pessoa:
                break
            
            pagina.wait_for_timeout(500)

        if campo_pessoa:
            return active_scope, campo_pessoa
            
        # Se não achou o campo, o sistema pode ter pedido o campus novamente (sessão expirada/renovada)
        if not primeiro_acesso:
            log_warn("Verificando se a tarja de seleção de campus reapareceu...")
            if selecionar_campus_dois_vizinhos(pagina):
                log_warn("Tarja de campus resolvida no meio do processo. Tentando novamente...")
                continue

        log_warn(f"Campo de pesquisa nao encontrado (tentativa {tentativa}/3).")

    return None, None


def registrar_erro_csv(caminho_csv: str, cabecalhos: list[str], aluno: str, mensagem_erro: str, nome_sistema: str = "--") -> None:
    with open(caminho_csv, mode="a", newline="", encoding="utf-8-sig") as arquivo_csv:
        escritor = csv.DictWriter(arquivo_csv, fieldnames=cabecalhos, delimiter=";")
        escritor.writerow(
            {
                "Aluno (CSV)": aluno,
                "Nome (Sistema)": nome_sistema,
                "Codigo": "--",
                "Disciplina": "--",
                "Turma": "--",
                "Media Final": "--",
                "Situacao": "--",
                "Observacoes": f"ERRO: {mensagem_erro}",
            }
        )


print("\n[ 1. SELECIONE O MODO DE NAVEGACAO ]")
print("1 - Modo Visual (janela aberta)")
print("2 - Modo Ultra Turbo (headless)")

if args.modo:
    modo_headless = args.modo == "2"
else:
    while True:
        escolha_modo = input("\nDigite 1 ou 2 e aperte ENTER: ").strip()
        if escolha_modo in ["1", "2"]:
            modo_headless = escolha_modo == "2"
            break
        print("Opcao invalida.")

if args.filtro_modo:
    escolha_filtro = args.filtro_modo
    termo_busca = args.termo.strip().lower()
else:
    print("\n[ 2. SELECIONE O FILTRO DE ALUNOS ]")
    print("1 - Processar TODOS os alunos unicos do CSV")
    print("2 - Filtrar por NOME DO CURSO/DISCIPLINA (Coluna A)")
    print("3 - Filtrar por NOME DO ALUNO (Coluna C)")

    while True:
        escolha_filtro = input("\nDigite 1, 2 ou 3 e aperte ENTER: ").strip()
        if escolha_filtro in ["1", "2", "3"]:
            break
        print("Opcao invalida.")

    termo_busca = ""
    if escolha_filtro == "2":
        termo_busca = input("Digite o termo para filtrar o CURSO: ").strip().lower()
    elif escolha_filtro == "3":
        termo_busca = input("Digite o termo para filtrar o ALUNO: ").strip().lower()

lista_alunos = selecionar_e_ler_csv(escolha_filtro, termo_busca, args.csv_entrada)
if not lista_alunos:
    print("Nenhum aluno encontrado com esses criterios. Encerrando.")
    raise SystemExit(0)

cabecalhos = [
    "Aluno (CSV)",
    "Nome (Sistema)",
    "Codigo",
    "Disciplina",
    "Turma",
    "Media Final",
    "Situacao",
    "Observacoes",
]

state_file = os.path.join(diretorio_script, "state_academico.json")
processed_students = []
csv_retomada = None

if os.path.exists(state_file) and not args.ignorar_estado:
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
            if state.get("csv_entrada") == (args.csv_entrada or "") and state.get("filtro_modo") == escolha_filtro and state.get("termo") == termo_busca:
                processed_students = state.get("processed_students", [])
                csv_retomada = state.get("csv_saida")
                log_info(f"Retomando execucao. {len(processed_students)} alunos ja processados.")
            else:
                log_info("Filtros diferentes detectados. Ignorando estado anterior.")
    except Exception as e:
        log_warn(f"Erro ao ler arquivo de estado: {e}")

if csv_retomada and os.path.exists(csv_retomada):
    caminho_completo_geral = csv_retomada
    log_info(f"Reaproveitando arquivo de consolidacao: {os.path.basename(csv_retomada)}")
else:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo_geral = f"Extracao_Geral_SIORG_{timestamp}.csv"
    pasta_csvs_academico = os.path.join(diretorio_script, "CSVs")
    os.makedirs(pasta_csvs_academico, exist_ok=True)
    caminho_completo_geral = os.path.join(pasta_csvs_academico, nome_arquivo_geral)
    
    log_info(f"Criando arquivo de consolidacao geral: {nome_arquivo_geral}")
    with open(caminho_completo_geral, mode="w", newline="", encoding="utf-8-sig") as arquivo_csv:
        data_extracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        escritor_simples = csv.writer(arquivo_csv, delimiter=";")
        escritor_simples.writerow([data_extracao])
        escritor = csv.DictWriter(arquivo_csv, fieldnames=cabecalhos, delimiter=";")
        escritor.writeheader()

def salvar_estado(aluno):
    if aluno not in processed_students:
        processed_students.append(aluno)
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "csv_entrada": args.csv_entrada or "",
                "filtro_modo": escolha_filtro,
                "termo": termo_busca,
                "csv_saida": caminho_completo_geral,
                "processed_students": processed_students,
                "total_students": len(lista_alunos)
            }, f, ensure_ascii=False, indent=4)
    except Exception as e:
        log_warn(f"Erro ao salvar estado: {e}")

log_info("Buscando ajustes de nomes (Moodle -> SIORG)...")
name_adjustments = get_name_adjustments()
name_adjustments_lower = {k.lower().strip(): v for k, v in name_adjustments.items()} if name_adjustments else {}
if name_adjustments:
    log_info(f"Foram carregados {len(name_adjustments)} ajustes de nomes.")

log_info("Iniciando instancia do Chromium...")

try:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=modo_headless)
        contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
        pagina = contexto.new_page()
        pagina.set_default_timeout(TIMEOUT_PADRAO)

        pagina.on("dialog", lambda d: d.accept())

        log_info(f"Navegando para o Login: {URL_LOGIN}")
        pagina.goto(URL_LOGIN, wait_until="domcontentloaded")

        log_info("Preenchendo credenciais...")
        pagina.locator("input[formcontrolname='username']").fill(USUARIO_SIORG)
        pagina.locator("input[formcontrolname='password']").fill(SENHA_SIORG)
        pagina.locator("button.login-btn").click()
        log_ok("Login concluido!")

        log_info("Selecionando o Campus DOIS VIZINHOS...")
        selecionar_campus_dois_vizinhos(pagina, obrigatorio=True)

        log_info("Acessando a tela de pesquisa inicial...")
        active_scope, campo_pessoa = preparar_tela_pesquisa(pagina, primeiro_acesso=True)

        todos_dados_extraidos = []

        for contador, aluno_alvo in enumerate(lista_alunos, start=1):
            if aluno_alvo in processed_students:
                continue

            aluno_alvo_clean = aluno_alvo.lower().strip()
            
            if aluno_alvo_clean in name_adjustments_lower:
                aluno_busca = name_adjustments_lower[aluno_alvo_clean]
                # Log extra será impresso logo abaixo
            else:
                aluno_busca = preparar_nome_busca(aluno_alvo)
                
            observacao_aluno = ""

            print("\n=======================================================")
            print(f"🧑‍🎓 Aluno {contador}/{len(lista_alunos)} {barra_progresso(contador, len(lista_alunos))}")
            log_info(f"Processando: {aluno_alvo}")
            if aluno_alvo_clean in name_adjustments_lower:
                log_info(f"Usando ajuste de nome customizado: '{aluno_alvo}' -> '{aluno_busca}'")
            log_info(f"Buscando no sistema como: {aluno_busca}")
            print("=======================================================")

            # Recarrega a tela de pesquisa para cada aluno para garantir um estado limpo
            log_info("Carregando tela de pesquisa...")
            active_scope, campo_pessoa = preparar_tela_pesquisa(pagina)

            if not campo_pessoa:
                erro_msg = "Campo de pesquisa nao encontrado para o aluno."
                log_falha(erro_msg)
                registrar_erro_csv(caminho_completo_geral, cabecalhos, aluno_alvo, erro_msg)
                salvar_estado(aluno_alvo)
                continue

            log_info("Injetando dados do aluno...")
            
            pagina.wait_for_timeout(DELAY_ANTES_LIMPAR)
            campo_pessoa.wait_for(state="visible")
            
            try:
                campo_pessoa.click(timeout=5000)
            except Exception:
                log_warn("Overlay bloqueando o campo. Tentando resolver (Campus ou ESC)...")
                selecionar_campus_dois_vizinhos(pagina)
                try:
                    botao_fechar = pagina.locator(".ui-dialog-titlebar-close").first
                    if botao_fechar.is_visible(timeout=500):
                        botao_fechar.click()
                except Exception:
                    pagina.keyboard.press("Escape")
                
                pagina.wait_for_timeout(1000)
                campo_pessoa.click(timeout=5000)
                
            campo_pessoa.fill("")
            
            campo_pessoa.fill(aluno_busca)
            pagina.wait_for_timeout(DELAY_APOS_PREENCHER) 
            campo_pessoa.press("Tab")

            # Espera um instante para que o AJAX principal da pesquisa de nome responda
            pagina.wait_for_timeout(2000)

            encontrou_aluno = False
            try:
                dropdown_nomes = active_scope.locator("#p_pesscodnr")
                tag_name_nomes = dropdown_nomes.evaluate("el => el.tagName.toLowerCase()")

                if tag_name_nomes == "select":
                    # Multiplos homonimos (precisa escolher um)
                    opcoes = dropdown_nomes.locator("option").all()
                    indices_validos = []
                    for i, opcao in enumerate(opcoes):
                        valor = (opcao.get_attribute("value") or "").strip()
                        if valor:
                            indices_validos.append(i)

                    if len(indices_validos) == 1:
                        dropdown_nomes.select_option(index=indices_validos[0])
                        active_scope.evaluate("document.getElementById('p_pesscodnr').onchange();")
                        texto_sel = opcoes[indices_validos[0]].inner_text().strip()
                        log_ok(f"Unico nome retornado no select: '{texto_sel}'")
                        encontrou_aluno = True
                    elif len(indices_validos) > 1:
                        log_info(f"Multiplos nomes retornados ({len(indices_validos)}). Checando Ciencia de Dados...")
                        for idx in indices_validos:
                            dropdown_nomes.select_option(index=idx)
                            active_scope.evaluate("document.getElementById('p_pesscodnr').onchange();")
                            nome_teste = opcoes[idx].inner_text().strip()

                            tem_ciencia_dados = False
                            for _ in range(4):
                                try:
                                    pagina.wait_for_timeout(500)
                                    texto_curso = active_scope.locator("#divcombopessoacurso").inner_text(timeout=TIMEOUT_TEXTO_CURSO)
                                    if texto_curso and "ciencia de dados" in remover_acentos(texto_curso).lower():
                                        tem_ciencia_dados = True
                                        break
                                except PlaywrightTimeoutError:
                                    continue

                            if tem_ciencia_dados:
                                log_ok(f"Vinculo correto identificado: '{nome_teste}'")
                                encontrou_aluno = True
                                break
                            log_warn(f"Opcao ignorada (outro curso): '{nome_teste}'")
                else:
                    # É um input hidden, ou seja, auto-selecionou um único aluno
                    log_info("Resultado unico no AJAX (input hidden).")
                    encontrou_aluno = True
            except Exception as e:
                log_warn(f"Erro ao checar dropdown de nomes: {e}")

            if not encontrou_aluno:
                erro_msg = "Falha ao confirmar o aluno no dropdown."
                registrar_erro_csv(caminho_completo_geral, cabecalhos, aluno_alvo, erro_msg)
                salvar_estado(aluno_alvo)
                continue

            # Agora o aluno está selecionado! Precisamos escolher o curso ANTES do período!
            try:
                campo_curso = active_scope.locator("#p_curscodnr")
                # Esperamos o select de curso popular com opções (além da padrão "Selecione...")
                for _ in range(6):
                    if campo_curso.locator("option").count() > 1:
                        break
                    pagina.wait_for_timeout(500)

                tag_name_curso = campo_curso.evaluate("el => el.tagName.toLowerCase()")
                if tag_name_curso == "select":
                    opcoes_curso = campo_curso.locator("option").all()
                    encontrou_curso = False
                    for op in opcoes_curso:
                        texto = (op.inner_text() or "").strip()
                        valor = (op.get_attribute("value") or "").strip()
                        if "ciencia de dados" in remover_acentos(texto).lower() and valor:
                            campo_curso.select_option(value=valor)
                            active_scope.evaluate("if(document.getElementById('p_curscodnr').onchange) document.getElementById('p_curscodnr').onchange();")
                            log_ok(f"Multi-curso resolvido: '{texto}' selecionado.")
                            encontrou_curso = True
                            break
                    if not encontrou_curso:
                        log_warn("Curso 'Ciencia de Dados' nao encontrado. Mantendo opcao atual.")
            except Exception as e:
                log_warn(f"Aviso no carregamento do curso: {e}")

            # AGORA escolhemos o período, pois as opções de período dependem do curso
            vinculos_para_processar = [{"value": None, "texto": ""}]
            try:
                dropdown_periodo = active_scope.locator("#p_alcuordemnr")
                # Esperamos popular os periodos (além do padrão "Selecione...")
                for _ in range(6):
                    if dropdown_periodo.locator("option").count() > 1:
                        break
                    pagina.wait_for_timeout(500)

                opcoes_periodo = dropdown_periodo.locator("option").all()
                opcoes_validas = []
                for op in opcoes_periodo:
                    valor = (op.get_attribute("value") or "").strip()
                    texto = (op.inner_text() or "").strip()
                    if not valor or not texto or "selecione" in texto.lower():
                        continue
                    opcoes_validas.append({"value": valor, "texto": texto})

                if opcoes_validas:
                    opcoes_regulares = [op for op in opcoes_validas if "regular" in remover_acentos(op["texto"]).lower()]
                    opcoes_demais = [op for op in opcoes_validas if "regular" not in remover_acentos(op["texto"]).lower()]
                    vinculos_para_processar = opcoes_regulares + opcoes_demais
                    if len(vinculos_para_processar) > 1:
                        log_info(f"Multiplos vinculos detectados: {len(vinculos_para_processar)} opcao(oes).")
            except Exception as e:
                log_warn(f"Aviso no carregamento de vinculos: {e}")

            for indice_vinculo, vinculo in enumerate(vinculos_para_processar, start=1):
                observacao_aluno = ""
                texto_vinculo = (vinculo.get("texto") or "").strip()
                valor_vinculo = vinculo.get("value")

                if valor_vinculo:
                    dropdown_periodo = active_scope.locator("#p_alcuordemnr")
                    dropdown_periodo.select_option(value=valor_vinculo)
                    active_scope.evaluate("if(document.getElementById('p_alcuordemnr').onchange) document.getElementById('p_alcuordemnr').onchange();")
                    if "regular" not in remover_acentos(texto_vinculo).lower():
                        observacao_aluno = texto_vinculo
                    log_info(f"Processando vinculo {indice_vinculo}/{len(vinculos_para_processar)}: {texto_vinculo}")

                log_info("Acionando pesquisa...")
                try:
                    active_scope.locator("#btnProcurar1").click(timeout=5000)
                except Exception:
                    log_warn("Erro ao clicar em Procurar. Verificando overlay de campus...")
                    selecionar_campus_dois_vizinhos(pagina)
                    try:
                        botao_fechar = pagina.locator(".ui-dialog-titlebar-close").first
                        if botao_fechar.is_visible(timeout=500):
                            botao_fechar.click()
                    except Exception:
                        pagina.keyboard.press("Escape")
                    
                    pagina.wait_for_timeout(1000)
                    active_scope.locator("#btnProcurar1").click(timeout=5000, force=True)

                # =================================================================
                # Forçamos o código a dormir o suficiente para a requisição antiga sumir
                pagina.wait_for_timeout(TEMPO_ESPERA_SPA)

                # Garantimos que a tela de resposta (com ou sem notas) renderizou
                # Esperamos primeiro o cabeçalho do aluno aparecer
                try:
                    active_scope.locator("table.cabealuno").first.wait_for(state="visible", timeout=TIMEOUT_CABEALUNO)
                except PlaywrightTimeoutError:
                    log_falha("Falha: Cabeçalho com dados do aluno demorou para carregar ou não apareceu.")

                # Agora sim, esperamos o layout da tabela de notas nova renderizar:
                # O seletor tr:has(td:nth-child(15)) garante que ele espere uma tabela válida.
                try:
                    active_scope.locator("table.tbl tr:has(td:nth-child(15))").first.wait_for(state="visible", timeout=TIMEOUT_TABELA_HISTORICO)
                except PlaywrightTimeoutError:
                    log_falha("Falha: Tabela de histórico não visível no tempo limite (pode estar vazia ou sistema lento).")
                    try:
                        nome_limpo = remover_acentos(aluno_alvo).replace(' ', '_')
                        pagina.screenshot(path=os.path.join(PASTA_DEBUG, f"debug_{nome_limpo}.png"))
                        with open(os.path.join(PASTA_DEBUG, f"debug_{nome_limpo}.html"), "w", encoding="utf-8") as html_file:
                            html_file.write(active_scope.evaluate("document.body.innerHTML"))
                    except Exception as e:
                        log_warn(f"Nao foi possivel salvar HTML: {e}")

                log_info("Extraindo dados do historico...")
                nome_sistema = "NAO ENCONTRADO"
                try:
                    try:
                        td_aluno = active_scope.locator("//table[@class='cabealuno']//td[strong[contains(text(), 'Aluno:')]]").first
                        texto_bruto = (td_aluno.inner_text() or "").strip().replace("Aluno:", "").strip()
                        if "-" in texto_bruto:
                            nome_sistema = texto_bruto.split("-", 1)[1].strip()
                        else:
                            nome_sistema = texto_bruto
                    except Exception:
                        pass

                    tabela_disciplinas = None
                    tabelas = active_scope.locator("table.tbl")
                    total_tabelas = tabelas.count()
                    for i in range(total_tabelas):
                        tbl = tabelas.nth(i)
                        # Identifica a tabela correta procurando se ela possui as 15 colunas esperadas
                        if tbl.locator("tr:has(td:nth-child(15))").count() > 0:
                            tabela_disciplinas = tbl
                            break

                    if tabela_disciplinas is None:
                        situacao_texto = "Desconhecida"
                        try:
                            td_situacao = active_scope.locator("//td[strong[contains(text(), 'Situação')]]").first
                            situacao_bruta = (td_situacao.inner_text() or "").strip()
                            if ":" in situacao_bruta:
                                situacao_texto = situacao_bruta.split(":", 1)[1].strip()
                            else:
                                situacao_texto = situacao_bruta.replace("Situação", "").strip()
                        except Exception:
                            situacao_texto = "Nao localizada na pagina"

                        erro_msg = f"Histórico vazio ou não encontrado. (Situação da tela: {situacao_texto})"
                        log_falha(erro_msg)
                        registrar_erro_csv(caminho_completo_geral, cabecalhos, aluno_alvo, erro_msg, nome_sistema=nome_sistema)
                        todos_dados_extraidos.append({
                            "Aluno (CSV)": aluno_alvo,
                            "Nome (Sistema)": nome_sistema,
                            "Codigo": "--",
                            "Disciplina": "--",
                            "Turma": "--",
                            "Media Final": "--",
                            "Situacao": "--",
                            "Observacoes": f"ERRO: {erro_msg}",
                        })
                        salvar_estado(aluno_alvo)
                        continue

                    linhas = tabela_disciplinas.locator("tr")
                    total_linhas = linhas.count()
                    dados_extraidos = []
                    for i in range(total_linhas):
                        linha = linhas.nth(i)
                        colunas = linha.locator("td")
                        if colunas.count() >= 15:
                            codigo = (colunas.nth(1).inner_text() or "").strip()
                            disciplina = (colunas.nth(2).inner_text() or "").strip()
                            turma = (colunas.nth(3).inner_text() or "").strip()
                            media_final = (colunas.nth(13).inner_text() or "").strip()
                            situacao = (colunas.nth(14).inner_text() or "").strip()

                            if codigo and codigo != "--":
                                dados_extraidos.append(
                                    {
                                        "Aluno (CSV)": aluno_alvo,
                                        "Nome (Sistema)": nome_sistema,
                                        "Codigo": codigo,
                                        "Disciplina": disciplina,
                                        "Turma": turma,
                                        "Media Final": media_final,
                                        "Situacao": situacao,
                                        "Observacoes": observacao_aluno,
                                    }
                                )

                    log_ok(f"{len(dados_extraidos)} disciplinas capturadas com sucesso.")
                    todos_dados_extraidos.extend(dados_extraidos)
                    with open(caminho_completo_geral, mode="a", newline="", encoding="utf-8-sig") as arquivo_csv:
                        escritor = csv.DictWriter(arquivo_csv, fieldnames=cabecalhos, delimiter=";")
                        for dado in dados_extraidos:
                            escritor.writerow(dado)

                except Exception as erro_extracao:
                    erro_msg = f"Falha na extracao de dados: {str(erro_extracao)[:80]}"
                    log_error(erro_msg)
                    registrar_erro_csv(caminho_completo_geral, cabecalhos, aluno_alvo, erro_msg, nome_sistema=nome_sistema)
                    todos_dados_extraidos.append({
                        "Aluno (CSV)": aluno_alvo,
                        "Nome (Sistema)": nome_sistema,
                        "Codigo": "--",
                        "Disciplina": "--",
                        "Turma": "--",
                        "Media Final": "--",
                        "Situacao": "--",
                        "Observacoes": f"ERRO: {erro_msg}",
                    })
            
            # Salva o estado ao final de cada aluno processado com ou sem erros.
            salvar_estado(aluno_alvo)

        if sync_to_supabase:
            sync_to_supabase("academico_notas", todos_dados_extraidos, delete_by_col="aluno_csv")

        log_ok("AUTOMACAO FINALIZADA COM SUCESSO!")
        log_info(f"Planilha salva em: {caminho_completo_geral}")
        
        if os.path.exists(state_file):
            os.remove(state_file)

except Exception as erro_geral:
    log_error(f"Ocorreu um erro geral na automacao: {erro_geral}")
raise SystemExit(0)