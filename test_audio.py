"""Grava 5s do microfone configurado e salva em WAV para inspeção manual.

Reescrito para usar sounddevice + config.py, como o resto do projeto.
A versão anterior dependia de pyaudio (não listado em requirements.txt)
e do módulo audioop (removido no Python 3.13), além de fixar o índice
do microfone em 1 em vez de respeitar AUDIO_DEVICE_INDEX do .env.
"""
import numpy as np
import sounddevice as sd

from config import AUDIO_DEVICE_INDEX, AUDIO_SAMPLE_RATE
from core.audio import save_wav

RECORD_SECONDS = 5
OUTPUT_FILENAME = "teste_mic.wav"


def _rms(chunk: np.ndarray) -> float:
    x = chunk.astype(np.float32)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


device = None if AUDIO_DEVICE_INDEX is None or AUDIO_DEVICE_INDEX < 0 else AUDIO_DEVICE_INDEX
print(f"Gravando {RECORD_SECONDS}s do microfone "
      f"[{'padrão do Windows' if device is None else device}]...")

recording = sd.rec(
    int(RECORD_SECONDS * AUDIO_SAMPLE_RATE),
    samplerate=AUDIO_SAMPLE_RATE,
    channels=1,
    dtype="int16",
    device=device,
)
sd.wait()

audio = recording[:, 0]
max_rms = _rms(audio)

print("Gravação finalizada!")
print(f"Pico de volume detectado (RMS): {max_rms:.1f}")

if max_rms < 100:
    print("⚠️ ALERTA: o volume do microfone está MUITO BAIXO ou MUTE. "
          "O Whisper não conseguirá transcrever.")
else:
    print("✅ O microfone captou sinal de áudio. Verifique a gravação gerada.")

save_wav(OUTPUT_FILENAME, audio)
print(f"Arquivo '{OUTPUT_FILENAME}' salvo com sucesso na pasta do projeto.")
