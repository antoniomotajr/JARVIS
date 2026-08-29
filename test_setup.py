import sys
import shutil
import requests
import sounddevice as sd
from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    PIPER_MODEL,
    PIPER_EXECUTABLE,
    AUDIO_DEVICE_INDEX,
    AUDIO_SAMPLE_RATE,
)

print("=" * 60)
print("DIAGNÓSTICO DO JARVIS")
print("=" * 60)
print("Python:", sys.version)
print("Ollama:", OLLAMA_URL)
print("Modelo:", OLLAMA_MODEL)
# Usa o mesmo PIPER_EXECUTABLE configurado no .env (antes o diagnóstico
# checava sempre "piper" fixo, ignorando o executável real do projeto).
print("Piper executável:", shutil.which(PIPER_EXECUTABLE) or f"NÃO ENCONTRADO ({PIPER_EXECUTABLE})")
print("Piper model:", PIPER_MODEL, "| existe:", PIPER_MODEL.exists())
print("\n[DISPOSITIVOS DE ÁUDIO]")
try:
    print(sd.query_devices())
    print("\nDispositivo padrão:", sd.default.device)
    print("AUDIO_DEVICE_INDEX:", AUDIO_DEVICE_INDEX)
    print("AUDIO_SAMPLE_RATE:", AUDIO_SAMPLE_RATE)
except Exception as exc:
    print("Erro:", exc)

print("\n[OLLAMA]")
try:
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
    print("HTTP:", r.status_code)
    if r.ok:
        models = [m.get("name") for m in r.json().get("models", [])]
        print("Modelos:", models)
        print("Modelo configurado existe:", OLLAMA_MODEL in models)
except Exception as exc:
    print("Não conectado:", exc)

print("\n[PIPER]")
print("Modelo existe:", PIPER_MODEL.exists())
print("\nDiagnóstico concluído.")
