import tempfile
from pathlib import Path
import numpy as np
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
from config import AUDIO_SAMPLE_RATE, WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_LANGUAGE
from . import executor


def _build_vocab_prompt() -> str:
    """Monta uma frase de contexto com o vocabulário que o Jarvis realmente
    usa (verbos de comando + nomes/apelidos de apps.json). Passada como
    'initial_prompt' pro Whisper, isso funciona como uma dica de vocabulário
    e reduz bastante confusões em nomes como 'YouTube', 'LinkedIn',
    'WordPad', que sem contexto às vezes saem tortos na transcrição.
    """
    palavras = set(executor.OPEN_VERBS) | set(executor.CLOSE_VERBS) | {"sim", "não"}
    for app in executor.APPS.values():
        nome = app.get("nome")
        if nome:
            palavras.add(nome)
        palavras.update(app.get("aliases", []))
    palavras.discard("")
    return "Comandos de voz em português para um assistente: " + ", ".join(sorted(palavras)) + "."


class STT:
    def __init__(self):
        print(f"[JARVIS] Carregando Whisper: {WHISPER_MODEL}")
        self.model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE,
                                  compute_type=WHISPER_COMPUTE_TYPE)
        self.initial_prompt = _build_vocab_prompt()

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) == 0:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = Path(tmp.name)

        try:
            write(str(path), AUDIO_SAMPLE_RATE, audio.astype(np.int16))
            segments, _ = self.model.transcribe(
                str(path),
                language=WHISPER_LANGUAGE,
                vad_filter=True,
                beam_size=5,
                initial_prompt=self.initial_prompt,
                condition_on_previous_text=False,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            print(f"[JARVIS] Você disse: {text}")
            return text
        finally:
            path.unlink(missing_ok=True)
