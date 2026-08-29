"""Servidor web do Jarvis.

Substitui o modo terminal por um painel gráfico (baseado no jarvis.html
enviado) servido localmente em http://127.0.0.1:5000. Toda a lógica de
execução de comandos continua em core/executor.py; este arquivo só
orquestra:

  - status/log em tempo real pro painel (polling em /api/state)
  - abrir/fechar apps e sites a partir de cliques no painel
  - cadastro de novos navegadores/apps/sites, sempre persistido em
    apps.json (nunca só em memória)
  - o loop de voz (wake word + conversa contínua), rodando numa thread
    separada, ligado/desligado pelo botão "INICIAR/DESATIVAR J.A.R.V.I.S"
    do painel — sem precisar olhar pra nenhum terminal.
"""
import threading
from datetime import datetime

from flask import Flask, jsonify, request, render_template, send_file

from config import AUDIO_DIR, SAVE_AUDIO
from core.audio import record_command, save_wav, play_session_end
from core.wakeword import WakeWordDetector
from core.stt import STT
from core.llm import LLM
from core.tts import TTS
from core import executor
from main import _process_utterance  # reaproveita a lógica de comando/LLM já existente

# O servidor embutido do Flask (Werkzeug) loga TODA requisição HTTP como
# uma linha "GET /api/state ... 200 -". Como o painel faz polling de
# /api/state a cada ~600ms, isso inunda o terminal e esconde as mensagens
# que realmente importam (as que passam por emit_log, prefixadas com
# "[JARVIS] "). Sobe o nível do logger do werkzeug pra só mostrar
# avisos/erros reais (ex.: uma rota que quebrou com 500).
import logging

logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__, template_folder="templates")

# ============================================================
# ESTADO COMPARTILHADO (painel web <-> loop de voz em background)
# ============================================================
_state_lock = threading.Lock()
_log: list[dict] = []  # [{"seq": int, "time": str, "msg": str}]
_log_seq = 0
_state = {
    "active": False,
    "status": "standby",
    "label": "STANDBY",
    "text": "AGUARDANDO ATIVAÇÃO",
}

_stop_event = threading.Event()
_voice_thread: threading.Thread | None = None

# ============================================================
# SERVIÇOS (carregados uma vez, na subida do servidor)
# ============================================================
_llm = LLM()
try:
    _stt = STT()
    _tts = TTS()
    _wake = WakeWordDetector()
    _init_error: str | None = None
except Exception as exc:  # microfone/modelo ausente etc. — painel ainda sobe
    _stt = _tts = _wake = None
    _init_error = str(exc)
    print(f"[WEB] Voz indisponível ({exc}); o painel funciona, mas sem o botão de voz.")


def emit_log(msg: str) -> None:
    global _log_seq
    with _state_lock:
        _log_seq += 1
        _log.append({"seq": _log_seq, "time": datetime.now().strftime("%H:%M:%S"), "msg": msg})
        if len(_log) > 300:
            del _log[: len(_log) - 300]
    print(f"[JARVIS] {msg}")


def set_state(status: str, label: str, text: str, active: bool | None = None) -> None:
    with _state_lock:
        _state["status"] = status
        _state["label"] = label
        _state["text"] = text
        if active is not None:
            _state["active"] = active


# ============================================================
# LOOP DE VOZ (roda numa thread separada; controlado por _stop_event)
# ============================================================
def _respond(msg: str) -> str:
    set_state("falando", "FALANDO", (msg or "")[:70])
    emit_log(f"Jarvis: {msg}")
    if _tts:
        _tts.speak(msg)
    set_state("ouvindo", "OUVINDO", "SISTEMA OPERACIONAL — OUVINDO")
    return msg


def _on_ready_to_speak() -> None:
    """Chamado no exato momento em que o bipe de 'pode falar' toca —
    mostra o mesmo aviso no log do painel, pra não depender só do som."""
    set_state("ouvindo", "OUVINDO", "🎙️ PODE FALAR...")
    emit_log("🎙️ Pode falar...")


def _listen_confirm() -> str:
    set_state("ouvindo", "OUVINDO", "AGUARDANDO CONFIRMAÇÃO (SIM/NÃO)")
    audio = record_command(stop_event=_stop_event, on_ready=_on_ready_to_speak)
    if len(audio) < 1000:
        return ""
    text = _stt.transcribe(audio)
    if text:
        emit_log(f'Você disse: "{text}"')
    return text


def _capture_command():
    audio = record_command(stop_event=_stop_event, on_ready=_on_ready_to_speak)
    if SAVE_AUDIO and len(audio) >= 1000:
        path = AUDIO_DIR / f"command_{datetime.now():%Y%m%d_%H%M%S}.wav"
        save_wav(path, audio)
    return audio


def _voice_worker() -> None:
    emit_log("J.A.R.V.I.S iniciado. Todos os sistemas online.")
    set_state("ouvindo", "ONLINE", 'AGUARDANDO "HEY JARVIS"', active=True)
    _respond("Sou Jarvis, seu assistente. Por onde você quer começar?")

    try:
        while not _stop_event.is_set():
            set_state("ouvindo", "ONLINE", 'AGUARDANDO "HEY JARVIS"')
            heard = _wake.wait(stop_event=_stop_event)
            if _stop_event.is_set():
                break
            if not heard:
                continue

            emit_log('Wake word "Hey Jarvis" detectada.')
            set_state("ouvindo", "OUVINDO", "SISTEMA OPERACIONAL — OUVINDO")

            # Conversa contínua: depois do wake word, não precisa repetir
            # "Hey Jarvis" a cada comando — só volta a dormir em silêncio.
            while not _stop_event.is_set():
                audio = _capture_command()
                if _stop_event.is_set() or len(audio) < 1000:
                    if not _stop_event.is_set():
                        emit_log('Silêncio — voltando a aguardar "Hey Jarvis".')
                        play_session_end()
                    break

                set_state("processando", "PROCESSANDO", "TRANSCREVENDO ÁUDIO...")
                text = _stt.transcribe(audio)
                if not text:
                    emit_log("Não consegui entender. Ainda ouvindo, pode repetir.")
                    set_state("ouvindo", "OUVINDO", "SISTEMA OPERACIONAL — OUVINDO")
                    continue

                emit_log(f'Você disse: "{text}"')
                set_state("processando", "PROCESSANDO", "PENSANDO...")
                answer = _process_utterance(text, _llm, _respond, _listen_confirm)
                _respond(answer)
    finally:
        set_state("standby", "STANDBY", "AGUARDANDO ATIVAÇÃO", active=False)
        emit_log("J.A.R.V.I.S desativado.")


# ============================================================
# ROTAS
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    try:
        since = int(request.args.get("since", 0))
    except (TypeError, ValueError):
        since = 0
    with _state_lock:
        entries = [e for e in _log if e["seq"] > since]
        payload = dict(_state)
        payload["log"] = entries
    return jsonify(payload)


@app.route("/api/start", methods=["POST"])
def api_start():
    global _voice_thread
    if _wake is None or _stt is None:
        return jsonify({"error": f"Voz indisponível: {_init_error}"}), 503
    with _state_lock:
        already_active = _state["active"]
    if already_active:
        return jsonify(dict(_state))
    _stop_event.clear()
    _voice_thread = threading.Thread(target=_voice_worker, daemon=True)
    _voice_thread.start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    _stop_event.set()
    set_state("standby", "PARANDO...", "ENCERRANDO SESSÃO DE VOZ...")
    return jsonify({"ok": True})


def _entry_summary(key: str, entry: dict) -> dict:
    return {"key": key, "nome": entry.get("nome", key)}


@app.route("/api/apps")
def api_apps():
    browsers, sites, apps = [], [], []
    for key, entry in executor.APPS.items():
        if entry.get("type") == "browser":
            browsers.append(_entry_summary(key, entry))
        elif entry.get("type") == "url":
            sites.append(
                {
                    "key": key,
                    "nome": entry.get("nome", key),
                    "url": entry.get("url") or entry.get("target") or "",
                    "browser": entry.get("browser"),
                }
            )
        else:
            apps.append(_entry_summary(key, entry))
    return jsonify({"browsers": browsers, "sites": sites, "apps": apps})


@app.route("/api/apps/export")
def api_apps_export():
    return send_file(executor.APPS_FILE, as_attachment=True, download_name="apps.json")


@app.route("/api/apps", methods=["POST"])
def api_apps_add():
    body = request.get_json(force=True, silent=True) or {}
    kind = body.get("kind")
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify({"error": "Informe um nome."}), 400

    if kind == "browser":
        comando = (body.get("comando") or "").strip()
        if not comando:
            return jsonify({"error": "Informe o comando/executável do navegador (ex: chrome, msedge, firefox)."}), 400
        entry = {
            "nome": nome,
            "aliases": [nome.lower()],
            "type": "browser",
            "exe": comando,
            "open_cmd": comando,
        }
    elif kind == "app":
        comando = (body.get("comando") or "").strip()
        if not comando:
            return jsonify({"error": "Informe o comando/executável do aplicativo (ex: notepad, calc, WINWORD.EXE)."}), 400
        entry = {
            "nome": nome,
            "aliases": [nome.lower()],
            "exe": comando,
            "open_cmd": comando,
        }
    elif kind == "site":
        url = (body.get("url") or "").strip()
        if not url:
            return jsonify({"error": "Informe a URL do site."}), 400
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        entry = {"nome": nome, "aliases": [nome.lower()], "type": "url", "url": url}
        browser_key = body.get("browser")
        if browser_key and executor.APPS.get(browser_key, {}).get("type") == "browser":
            entry["browser"] = browser_key
    else:
        return jsonify({"error": "Tipo de cadastro inválido."}), 400

    key = executor.add_entry(nome, entry)
    emit_log(f'"{nome}" adicionado ao apps.json.')
    return jsonify({"ok": True, "key": key})


@app.route("/api/open", methods=["POST"])
def api_open():
    body = request.get_json(force=True, silent=True) or {}
    entry = executor.APPS.get(body.get("key"))
    if not entry:
        return jsonify({"error": "Aplicativo não encontrado."}), 404
    msg = executor.open_app(entry)
    emit_log(msg)
    return jsonify({"ok": True, "message": msg})


@app.route("/api/open-site", methods=["POST"])
def api_open_site():
    body = request.get_json(force=True, silent=True) or {}
    site = executor.APPS.get(body.get("key"))
    if not site:
        return jsonify({"error": "Site não encontrado."}), 404
    browser_entry = executor.APPS.get(body.get("browser"))
    if browser_entry and browser_entry.get("type") == "browser":
        msg = executor.open_url_in_browser(site, browser_entry)
    else:
        msg = executor.open_app(site)
    emit_log(msg)
    return jsonify({"ok": True, "message": msg})


@app.route("/api/close", methods=["POST"])
def api_close():
    body = request.get_json(force=True, silent=True) or {}
    entry = executor.APPS.get(body.get("key"))
    if not entry:
        return jsonify({"error": "Aplicativo não encontrado."}), 404
    msg = executor.close_app(entry)
    emit_log(msg)
    return jsonify({"ok": True, "message": msg})
