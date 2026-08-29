import sys
from datetime import datetime

from config import AUDIO_DIR, SAVE_AUDIO
from core.audio import record_command, save_wav, play_session_end
from core.wakeword import WakeWordDetector
from core.stt import STT
from core.llm import LLM
from core.tts import TTS
from core import executor


def _handle_command(cmd: executor.Command, respond, listen) -> str:
    """Executa um Command reconhecido e retorna a fala de resposta.

    respond(texto) fala/mostra a resposta; listen() grava+transcreve a
    próxima fala do usuário (usado só para confirmar um "fechar").
    """
    if cmd.action == "open":
        return executor.open_app(cmd.app)

    # "close": ação destrutiva, sempre confirma antes de executar.
    if executor.needs_close_confirmation(cmd.app):
        nome = cmd.app.get("nome", cmd.app_key)
        respond(f"Tem certeza que quer encerrar {nome}? Diga sim ou não.")
        confirm_text = listen()
        decision = executor.is_confirmation(confirm_text)
        if decision is True:
            return executor.close_app(cmd.app)
        if decision is False:
            return "Ok, cancelado."
        return "Não entendi a confirmação, então não vou encerrar por segurança."

    return executor.close_app(cmd.app)


def _process_utterance(text: str, llm, respond, listen) -> str:
    """Interpreta uma fala/mensagem: se for 'abrir/fechar <app>' reconhecido
    em apps.json, executa direto; senão segue pro papo normal com o LLM."""
    cmd = executor.parse_command(text)
    if cmd:
        return _handle_command(cmd, respond, listen)
    return llm.chat(text)


def text_mode(llm, tts):
    print("\n=== MODO TEXTO ===")
    print("Digite uma mensagem. Enter vazio encerra.")

    def respond(msg):
        print(f"Jarvis: {msg}")
        tts.speak(msg)

    def listen():
        return input("Você (confirmação): ").strip()

    while True:
        text = input("\nVocê: ").strip()
        if not text:
            return

        answer = _process_utterance(text, llm, respond, listen)
        print(f"Jarvis: {answer}")
        tts.speak(answer)


def _voice_conversation(llm, stt, respond, capture_command):
    """Depois de ouvir 'Hey Jarvis' uma vez, continua a conversa: escuta o
    próximo comando/pergunta direto, sem precisar do wake word de novo.

    Só volta a dormir (e espera 'Hey Jarvis' outra vez) quando o usuário
    fica em silêncio — o que é sinalizado com um bipe grave descendo, pra
    dar pra perceber sem olhar pro terminal.
    """

    def listen_confirm() -> str:
        confirm_audio = capture_command()
        return stt.transcribe(confirm_audio)

    while True:
        audio = capture_command()

        if len(audio) < 1000:
            print('[JARVIS] Silêncio — voltando a aguardar "Hey Jarvis".')
            play_session_end()
            return

        text = stt.transcribe(audio)
        if not text:
            print("[JARVIS] Não consegui entender. Ainda ouvindo, pode repetir.")
            continue

        answer = _process_utterance(text, llm, respond, listen_confirm)
        respond(answer)
        # não volta pro wake.wait(): o próximo capture_command() já começa
        # com o bipe de "pode falar" — a conversa continua automaticamente.


def main():
    print("=" * 60)
    print(" JARVIS - FASE 1 / MVP DE VOZ")
    print("=" * 60)

    llm = LLM()
    print(f"[EXECUTOR] {len(executor.APPS)} aplicativo(s) configurados em apps.json")

    if "--text" in sys.argv:
        tts = TTS()
        text_mode(llm, tts)
        return

    try:
        stt = STT()
        tts = TTS()
        wake = WakeWordDetector()
    except Exception as exc:
        print(f"\n[ERRO] Falha ao inicializar: {exc}")
        print("Execute: python test_setup.py")
        sys.exit(1)

    print("[OLLAMA]", "OK" if llm.healthcheck() else "NÃO CONECTADO")
    print("[PIPER]", "OK" if tts.available() else "NÃO CONFIGURADO")
    print('\n[JARVIS] Sistema pronto. Diga "Hey Jarvis".\n')

    def respond(msg):
        print(f"\nJarvis: {msg}\n")
        tts.speak(msg)

    def capture_command():
        audio = record_command()
        if SAVE_AUDIO and len(audio) >= 1000:
            path = AUDIO_DIR / f"command_{datetime.now():%Y%m%d_%H%M%S}.wav"
            save_wav(path, audio)
        return audio

    respond("Sou Jarvis, seu assistente. Por onde você quer começar?")

    try:
        while True:
            if not wake.wait():
                continue

            # A partir daqui o bipe de reconhecimento ("Hey Jarvis" ouvido)
            # já tocou dentro do wake.wait(). Entra direto na conversa —
            # cada gravação subsequente já avisa sozinha, por bipe, quando
            # começa e quando termina de ouvir.
            _voice_conversation(llm, stt, respond, capture_command)

    except KeyboardInterrupt:
        print("\n[JARVIS] Encerrado.")


if __name__ == "__main__":
    main()
