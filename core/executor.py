"""Executor de comandos do sistema (abrir/fechar aplicativos e sites).

Deliberadamente NÃO deixa o LLM decidir o que executar. Só uma lista
branca fixa em apps.json é reconhecida, e "fechar" sempre pede
confirmação por voz antes de agir — abrir é considerado seguro e roda
direto. Isso evita que uma transcrição errada do Whisper ou uma
alucinação do LLM derrube um processo do usuário sem querer.

Fluxo de navegador + aba:
    1. "abrir chrome" (ou edge/firefox) abre o navegador e o Jarvis
       passa a lembrar, nesta sessão, qual foi o último navegador
       aberto por ele (módulo `_current_browser`).
    2. "abrir youtube" / "abrir linkedin" depois disso não abre uma
       janela nova solta: chama o executável desse mesmo navegador
       passando a URL como argumento, o que faz o Chrome/Edge/Firefox
       abrirem a página numa aba nova da janela já aberta.
    3. Se nenhum navegador foi aberto pelo Jarvis ainda, cai no
       comportamento padrão (abre no navegador padrão do sistema).
"""
import json
import re
import shutil
import subprocess
import threading
import unicodedata
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from config import BASE_DIR

APPS_FILE = BASE_DIR / "apps.json"

# Usado apenas se apps.json não existir ou estiver corrompido.
_FALLBACK_APPS = {
    "firefox": {"nome": "Firefox", "aliases": ["firefox"], "type": "browser", "exe": "firefox.exe", "open_cmd": "firefox"},
    "chrome": {"nome": "Google Chrome", "aliases": ["chrome", "google chrome"], "type": "browser", "exe": "chrome.exe", "open_cmd": "chrome"},
}

OPEN_VERBS = ["abrir", "abra", "abre", "abri", "iniciar", "inicie", "inicia", "executar", "execute", "executa", "lancar", "lance"]
CLOSE_VERBS = ["fechar", "feche", "fecha", "fechei", "encerrar", "encerre", "encerra", "finalizar", "finalize", "matar", "mate"]

CONFIRM_YES = {"sim", "isso", "confirmo", "pode", "afirmativo", "claro", "com certeza"}
CONFIRM_NO = {"nao", "cancela", "cancelar", "negativo", "para", "pare"}

# Guarda o último app do tipo "browser" aberto pelo Jarvis nesta sessão,
# para que "abrir youtube/linkedin" depois abra em aba nova dele.
_current_browser: dict | None = None

# Protege leituras/escritas concorrentes de apps.json (o painel web e o
# reconhecimento de voz rodam em threads diferentes).
_apps_lock = threading.Lock()


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return text


def _load_apps() -> dict:
    try:
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[EXEC] apps.json não encontrado em {APPS_FILE}, usando lista mínima padrão.")
        return _FALLBACK_APPS
    except Exception as exc:
        print(f"[EXEC] Erro ao ler apps.json ({exc}), usando lista mínima padrão.")
        return _FALLBACK_APPS


APPS = _load_apps()


def _slugify(nome: str) -> str:
    base = _normalize(nome)
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return base or "app"


def _unique_key(base: str) -> str:
    if base not in APPS:
        return base
    i = 2
    while f"{base}_{i}" in APPS:
        i += 1
    return f"{base}_{i}"


def _save_apps_locked() -> None:
    """Grava o dict APPS inteiro em apps.json de forma atômica (escreve
    num arquivo temporário e só troca no final), pra nunca deixar o
    arquivo corrompido se o processo cair no meio da escrita. Chame só
    com _apps_lock já adquirido."""
    tmp_path = APPS_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(APPS, f, ensure_ascii=False, indent=2)
    tmp_path.replace(APPS_FILE)


def add_entry(nome: str, entry: dict) -> str:
    """Adiciona uma entrada nova (navegador, app ou site) a apps.json e
    já deixa disponível tanto pro reconhecimento de voz (parse_command)
    quanto pro painel web, sem precisar reiniciar o Jarvis. Retorna a
    chave (slug) gerada para a entrada."""
    with _apps_lock:
        key = _unique_key(_slugify(nome))
        APPS[key] = entry
        _save_apps_locked()
    return key


@dataclass
class Command:
    action: str  # "open" ou "close"
    app_key: str
    app: dict


def _match_any(norm_text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", norm_text) for w in words)


def parse_command(text: str) -> "Command | None":
    """Tenta reconhecer 'abrir/fechar <app>' no texto transcrito.

    Retorna None se não reconhecer — nesse caso o texto segue o fluxo
    normal de conversa com o LLM.
    """
    if not text:
        return None

    norm = _normalize(text)

    if _match_any(norm, OPEN_VERBS):
        action = "open"
    elif _match_any(norm, CLOSE_VERBS):
        action = "close"
    else:
        return None

    for key, app in APPS.items():
        aliases = [_normalize(a) for a in app.get("aliases", [key])]
        if _match_any(norm, aliases):
            return Command(action=action, app_key=key, app=app)

    return None


def needs_close_confirmation(app: dict) -> bool:
    return bool(app.get("confirm_close", True))


def is_confirmation(text: str):
    """True = confirmou, False = negou, None = não reconheceu a resposta."""
    norm = _normalize(text or "")
    if not norm:
        return None
    if any(w in norm for w in CONFIRM_NO):
        return False
    if any(w in norm for w in CONFIRM_YES):
        return True
    return None


def _resolve(exe: str | None, open_cmd: str | None) -> str | None:
    """Tenta achar um caminho executável real via PATH."""
    return shutil.which(exe or "") or shutil.which(open_cmd or "")


def _start_via_shell(name: str, *extra_args: str) -> None:
    """Usa o comando 'start' do Windows, que também resolve nomes pelo
    registro 'App Paths' (funciona para programas como Word, Excel,
    Chrome etc. mesmo quando não estão no PATH)."""
    args = " ".join(f'"{a}"' for a in extra_args)
    subprocess.Popen(f'start "" "{name}" {args}'.strip(), shell=True)


def open_app(app: dict) -> str:
    global _current_browser

    nome = app.get("nome", app.get("open_cmd", "aplicativo"))
    open_cmd = app.get("open_cmd")
    exe = app.get("exe")
    url = app.get("url") or app.get("target")

    # 1. Trata o comando como link web se houver campo 'url'/'target',
    #    'type' == 'url', ou 'exe' apontando para um link http.
    if app.get("type") == "url" or url or (exe and exe.startswith("http")):
        target_url = url or exe
        if not target_url:
            return f"Não sei o endereço de {nome}: falta 'url' em apps.json."

        # Se o Jarvis já abriu um navegador nesta sessão, abre o link
        # como aba nova NESSE navegador, em vez do padrão do sistema.
        if _current_browser:
            browser_nome = _current_browser.get("nome", "navegador")
            browser_exe = _current_browser.get("exe")
            browser_cmd = _current_browser.get("open_cmd")
            resolved_browser = _resolve(browser_exe, browser_cmd)
            try:
                if resolved_browser:
                    subprocess.Popen([resolved_browser, target_url])
                elif browser_exe:
                    _start_via_shell(browser_exe, target_url)
                else:
                    raise RuntimeError("navegador sem 'exe' configurado")
                return f"{nome} aberto em uma nova aba do {browser_nome}."
            except Exception:
                pass  # cai no fallback abaixo (navegador padrão do sistema)

        try:
            webbrowser.open(target_url)
            return f"{nome} aberto no seu navegador."
        except Exception as exc:
            return f"Não consegui abrir o site {nome}: {exc}"

    # 2. Lógica para executáveis do sistema.
    resolved = _resolve(exe, open_cmd)
    try:
        if resolved:
            subprocess.Popen([resolved])
        elif exe:
            # 'exe' costuma bater exatamente com a chave do registro
            # 'App Paths' do Windows (ex.: WINWORD.EXE, EXCEL.EXE),
            # então tenta primeiro por ele.
            _start_via_shell(exe)
        elif open_cmd:
            _start_via_shell(open_cmd)
        else:
            return f"Não sei como abrir {nome}: falta 'exe' ou 'open_cmd' em apps.json."

        if app.get("type") == "browser":
            _current_browser = app

        return f"{nome} aberto."
    except Exception as exc:
        return f"Não consegui abrir {nome}: {exc}"


def open_url_in_browser(app: dict, browser_app: dict) -> str:
    """Abre o site de 'app' especificamente no navegador 'browser_app',
    independente de qual foi o último navegador aberto na sessão de voz
    (_current_browser). Usado pelo painel web quando o usuário clica um
    site dentro do accordion de um navegador específico — a intenção ali
    é explícita ("abrir ESSE site NESSE navegador"), então não faz
    sentido depender do estado de sessão."""
    global _current_browser

    nome = app.get("nome", "site")
    target_url = app.get("url") or app.get("target")
    if not target_url:
        return f"Não sei o endereço de {nome}: falta 'url' em apps.json."

    browser_nome = browser_app.get("nome", "navegador")
    browser_exe = browser_app.get("exe")
    resolved_browser = _resolve(browser_exe, browser_app.get("open_cmd"))
    try:
        if resolved_browser:
            subprocess.Popen([resolved_browser, target_url])
        elif browser_exe:
            _start_via_shell(browser_exe, target_url)
        else:
            raise RuntimeError("navegador sem 'exe' configurado")
        _current_browser = browser_app
        return f"{nome} aberto em uma nova aba do {browser_nome}."
    except Exception:
        try:
            webbrowser.open(target_url)
            return f"{nome} aberto no seu navegador (não consegui usar {browser_nome} especificamente)."
        except Exception as exc:
            return f"Não consegui abrir o site {nome}: {exc}"


# Processos que fazem parte do shell do Windows: nunca podem ser
# encerrados via taskkill, porque matar eles derruba a área de trabalho,
# a barra de tarefas e o menu Iniciar inteiros — não fecham "uma janela".
# Fica bloqueado aqui, no código, e não como config em apps.json, porque
# precisa valer sempre, mesmo se alguém recadastrar isso pelo painel web.
_SHELL_CRITICAL_EXE = {"explorer.exe"}


def close_app(app: dict) -> str:
    global _current_browser

    nome = app.get("nome", app.get("exe", "aplicativo"))
    exe = app.get("exe")

    # Se for site/url não faz sentido dar taskkill.
    if app.get("type") == "url" or (exe and exe.startswith("http")):
        return f"Não é possível encerrar o site {nome} diretamente por aqui."

    if exe and exe.lower() in _SHELL_CRITICAL_EXE:
        return (
            f"Não vou encerrar {nome}: {exe} é o processo do shell do "
            "Windows (área de trabalho, barra de tarefas, menu Iniciar) — "
            "matar ele derruba tudo isso junto, não fecha só uma janela. "
            "Pra fechar uma janela do Explorador de Arquivos, feche ela "
            "direto na tela (clique no X ou Alt+F4 com ela em foco)."
        )

    if not exe:
        return f"Não sei o processo de {nome} para encerrar (falta 'exe' em apps.json)."

    try:
        result = subprocess.run(
            ["taskkill", "/IM", exe, "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            if _current_browser is app or (_current_browser and _current_browser.get("exe") == exe):
                _current_browser = None
            return f"{nome} encerrado."

        combined = f"{result.stdout} {result.stderr}".lower()
        if "não foi encontrado" in combined or "not found" in combined:
            return f"{nome} não estava aberto."
        return f"Não consegui encerrar {nome}: {result.stderr.strip() or 'erro desconhecido'}"
    except FileNotFoundError:
        return "Comando taskkill não encontrado (esse recurso só funciona no Windows)."
    except subprocess.TimeoutExpired:
        return f"Tempo esgotado tentando encerrar {nome}."
    except Exception as exc:
        return f"Erro ao encerrar {nome}: {exc}"
