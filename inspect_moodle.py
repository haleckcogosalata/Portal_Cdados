import os
import json
from playwright.sync_api import sync_playwright

diretorio_script = os.path.dirname(os.path.abspath(__file__))
caminho_credenciais = os.path.join(diretorio_script, "credenciais.json")

config_moodle = {}
if os.path.exists(caminho_credenciais):
    with open(caminho_credenciais, mode="r", encoding="utf-8") as arquivo_config:
        config = json.load(arquivo_config)
        config_moodle = config.get("moodle", {})

USUARIO_MOODLE = config_moodle.get("usuario", "").strip()
SENHA_MOODLE = config_moodle.get("senha", "").strip()
URL_LOGIN = config_moodle.get("url_login", "https://moodle.utfpr.edu.br/login/index.php")

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True)
    contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
    pagina = contexto.new_page()
    pagina.set_default_timeout(15000)

    print("Login...")
    pagina.goto(URL_LOGIN)
    pagina.fill("#username", USUARIO_MOODLE)
    pagina.fill("#password", SENHA_MOODLE)
    pagina.click("#loginbtn")
    pagina.wait_for_selector(".userbutton")

    print("Indo para Participantes ID: 34918")
    pagina.goto("https://moodle.utfpr.edu.br/user/index.php?id=34918")
    
    print("Salvando tela inicial...")
    pagina.screenshot(path="debug_moodle_participantes_antes.png")
    with open("debug_moodle_participantes_antes.html", "w", encoding="utf-8") as f:
        f.write(pagina.content())

    print("Buscando Mostrar Todos...")
    btn = pagina.locator("a[data-action='showcount']")
    if btn.count() > 0:
        print(f"Botão encontrado! Visível: {btn.first.is_visible()}, InnerText: {btn.first.inner_text()}")
        try:
            btn.first.click(timeout=5000)
            print("Clicou!")
            pagina.wait_for_timeout(3000)
            pagina.screenshot(path="debug_moodle_participantes_depois.png")
        except Exception as e:
            print("Erro no clique:", e)
    else:
        print("Botão Mostrar Todos não encontrado.")

    navegador.close()
