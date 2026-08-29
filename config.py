import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return (
        os.getenv(name, str(default)).strip().lower()
        in {"1", "true", "yes", "sim", "on"}
    )


def env_int(name: str, default: int) -> int:
    try:
        val = os.getenv(name, "").strip()
        return int(val) if val else default
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        val = os.getenv(name, "").strip()
        return float(val) if val else default
    except ValueError:
        return default


# ============================================================
# OLLAMA (Modelo de Linguagem)
# ============================================================
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

# ============================================================
# WHISPER (Transcrição de Voz)
# ============================================================
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")

# ============================================================
# WAKE WORD & DISPOSITIVO DE ÁUDIO
# ============================================================
WAKE_WORD = os.getenv("WAKE_WORD", "jarvis").lower()
WAKE_THRESHOLD = env_float("WAKE_THRESHOLD", 0.25)
AUDIO_DEVICE_INDEX = env_int("AUDIO_DEVICE_INDEX", -1)
# -1 = microfone padrão do Windows; informe o índice somente se necessário.
AUDIO_SAMPLE_RATE = env_int("AUDIO_SAMPLE_RATE", 16000)

# ============================================================
# GRAVAÇÃO E SILÊNCIO
# ============================================================
MAX_RECORD_SECONDS = env_float("MAX_RECORD_SECONDS", 12.0)
SILENCE_SECONDS = env_float("SILENCE_SECONDS", 2.0)
SILENCE_THRESHOLD = env_int("SILENCE_THRESHOLD", 100)
MIN_SPEECH_SECONDS = env_float("MIN_SPEECH_SECONDS", 0.35)
PRE_ROLL_SECONDS = env_float("PRE_ROLL_SECONDS", 0.35)
# Quantas vezes acima do ruído ambiente (RMS) um som precisa estar pra
# contar como fala. Baixe (ex.: 1.6) se estiver cortando fala baixinha;
# suba (ex.: 3.0) se o silêncio de fundo estiver disparando gravação.
SILENCE_MULTIPLIER = env_float("SILENCE_MULTIPLIER", 2.2)
SAVE_AUDIO = env_bool("SAVE_AUDIO", True)

# ============================================================
# PIPER (Síntese de Voz / TTS)
# ============================================================
PIPER_MODEL = BASE_DIR / os.getenv(
    "PIPER_MODEL", "models/piper/pt_BR-faber-medium.onnx"
)

_piper_exec_raw = os.getenv("PIPER_EXECUTABLE", "models/piper/piper.exe")
# Se for apenas um nome de comando (ex.: "piper", sem barra), deixamos como
# string para ser resolvido no PATH do sistema via shutil.which(). Antes
# isso era sempre transformado em BASE_DIR/"piper", um caminho inexistente
# que nunca era encontrado — quebrando quem configurasse PIPER_EXECUTABLE=piper.
if "/" in _piper_exec_raw or "\\" in _piper_exec_raw:
    PIPER_EXECUTABLE = BASE_DIR / _piper_exec_raw
else:
    PIPER_EXECUTABLE = _piper_exec_raw

# ============================================================
# PASTA DE ÁUDIOS
# ============================================================
AUDIO_DIR = BASE_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)