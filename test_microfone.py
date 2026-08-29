import time
import numpy as np
import sounddevice as sd

from config import AUDIO_DEVICE_INDEX, AUDIO_SAMPLE_RATE


def rms(x):
    x = np.asarray(x, dtype=np.float32)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


print("=" * 70)
print(" TESTE DO MICROFONE - JARVIS")
print("=" * 70)
print(f"Taxa de amostragem: {AUDIO_SAMPLE_RATE} Hz")
print(f"Índice configurado: {AUDIO_DEVICE_INDEX} (-1 = padrão do Windows)")
print("\nDISPOSITIVOS:")

devices = sd.query_devices()
for i, d in enumerate(devices):
    mark = "  <-- CONFIGURADO" if i == AUDIO_DEVICE_INDEX else ""
    if d.get("max_input_channels", 0) > 0:
        print(f"[{i}] ENTRADA: {d['name']} | canais={d['max_input_channels']}{mark}")

default = sd.default.device
print(f"\nDispositivo padrão do PortAudio: {default}")

device = None
if AUDIO_DEVICE_INDEX >= 0 and AUDIO_DEVICE_INDEX < len(devices):
    if devices[AUDIO_DEVICE_INDEX].get("max_input_channels", 0) > 0:
        device = AUDIO_DEVICE_INDEX

if device is None:
    # sounddevice usa None para o dispositivo padrão; não use -1.
    device = None

print(f"Usando entrada: {'microfone padrão do Windows' if device is None else 'índice ' + str(device)}")
print("\nFale normalmente durante 5 segundos...")

values = []
try:
    with sd.InputStream(
        device=device,
        samplerate=AUDIO_SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=int(0.1 * AUDIO_SAMPLE_RATE),
    ) as stream:
        end = time.time() + 5
        while time.time() < end:
            data, overflowed = stream.read(int(0.1 * AUDIO_SAMPLE_RATE))
            level = rms(data[:, 0])
            values.append(level)
            print(f"RMS: {level:8.1f}", end="\r")

    print("\n\nResultado:")
    print(f"RMS mínimo : {min(values):.1f}")
    print(f"RMS máximo : {max(values):.1f}")
    print(f"RMS médio  : {np.mean(values):.1f}")

    if max(values) < 100:
        print("ATENÇÃO: o microfone está captando sinal muito baixo.")
        print("Verifique o microfone selecionado e o volume de entrada do Windows.")
    else:
        print("OK: o microfone está captando áudio.")
except Exception as exc:
    print(f"\nERRO: {exc}")
    print("\nNo Windows, verifique Configurações > Sistema > Som > Entrada.")
