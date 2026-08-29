"""Ponto de entrada do painel web do Jarvis.

    python web_app.py

Sobe o servidor local em http://127.0.0.1:5000 e já abre o painel no
navegador padrão — não é mais preciso ficar de olho num terminal pra
saber o que o Jarvis está fazendo: status, log de ações e cadastro de
apps/navegadores/sites agora vivem no painel gráfico.
"""
import threading
import webbrowser

from web.server import app

HOST = "127.0.0.1"
PORT = 5000


def _abrir_navegador():
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    print("=" * 60)
    print(" JARVIS - PAINEL WEB")
    print("=" * 60)
    print(f"[JARVIS] Painel disponível em http://{HOST}:{PORT}")
    print("[JARVIS] Abrindo o navegador...")

    threading.Timer(1.2, _abrir_navegador).start()
    app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)
