from pathlib import Path
import shutil
import subprocess
import tempfile
from config import PIPER_EXECUTABLE, PIPER_MODEL
from .audio import play_wav

class TTS:
    def __init__(self):
        self.executable = shutil.which(PIPER_EXECUTABLE) or PIPER_EXECUTABLE
        self.model = Path(PIPER_MODEL)

    def available(self) -> bool:
        return self.model.exists() and shutil.which(self.executable) is not None

    def speak(self, text: str):
        if not text:
            return

        if not self.model.exists():
            print(f"[TTS] Modelo Piper não encontrado: {self.model}")
            return

        if shutil.which(self.executable) is None:
            print("[TTS] Executável 'piper' não encontrado.")
            return

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "response.wav"
            command = [self.executable, "--model", str(self.model), "--output_file", str(output)]
            try:
                subprocess.run(command, input=text, text=True, check=True, capture_output=True)
                play_wav(output)
            except subprocess.CalledProcessError as exc:
                print("[TTS] Erro no Piper:", exc.stderr)
