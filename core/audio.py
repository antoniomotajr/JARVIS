from pathlib import Path
import time
import wave
import numpy as np
import sounddevice as sd

try:
    import winsound  # só existe no Windows — API do SO, não usa PortAudio
    _HAS_WINSOUND = True
except ImportError:
    winsound = None
    _HAS_WINSOUND = False

from config import (
    AUDIO_DEVICE_INDEX,
    AUDIO_SAMPLE_RATE,
    MAX_RECORD_SECONDS,
    SILENCE_SECONDS,
    SILENCE_THRESHOLD,
    SILENCE_MULTIPLIER,
    MIN_SPEECH_SECONDS,
    PRE_ROLL_SECONDS,
)


def save_wav(path: Path, audio: np.ndarray):
    audio = np.asarray(audio, dtype=np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(AUDIO_SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


def _rms(chunk: np.ndarray) -> float:
    x = chunk.astype(np.float32)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def _input_device():
    """Resolve o dispositivo de entrada sem passar -1 ao PortAudio.

    sounddevice usa device=None para o dispositivo padrão. Passar -1
    explicitamente causa "Error querying device -1" em algumas versões.
    """
    if AUDIO_DEVICE_INDEX is None or AUDIO_DEVICE_INDEX < 0:
        print("[ÁUDIO] Usando o microfone padrão do Windows.")
        return None

    try:
        devices = sd.query_devices()
        if AUDIO_DEVICE_INDEX < len(devices):
            d = devices[AUDIO_DEVICE_INDEX]
            if d.get("max_input_channels", 0) > 0:
                print(f"[ÁUDIO] Usando microfone índice {AUDIO_DEVICE_INDEX}: {d['name']}")
                return AUDIO_DEVICE_INDEX
            print(f"[ÁUDIO] Dispositivo {AUDIO_DEVICE_INDEX} não possui entrada.")
    except Exception as exc:
        print(f"[ÁUDIO] Não foi possível validar o dispositivo: {exc}")

    print("[ÁUDIO] Voltando para o microfone padrão do Windows.")
    return None


def _normalize(audio: np.ndarray, target_peak: float = 0.7) -> np.ndarray:
    """Normaliza o pico do áudio para melhorar a transcrição de microfones fracos.

    Microfones com ganho baixo geram sinal com RMS pequeno, o que prejudica a
    precisão do Whisper. Normalizamos pelo pico (não pelo RMS) para não
    amplificar ruído de fundo mais do que a fala, e evitamos amplificar
    além de um teto seguro para não estourar clipping.
    """
    if audio.size == 0:
        return audio

    peak = float(np.max(np.abs(audio.astype(np.float32)))) / 32768.0
    if peak <= 0.0:
        return audio

    gain = (target_peak / peak) if peak < target_peak else 1.0
    # Nunca amplifica mais que 6x: acima disso é ruído/silêncio, não fala fraca.
    gain = min(gain, 6.0)
    if gain <= 1.0:
        return audio

    boosted = audio.astype(np.float32) * gain
    np.clip(boosted, -32768, 32767, out=boosted)
    return boosted.astype(np.int16)


def _calibrate_noise(stream, block, seconds=0.8):
    """Estimate ambient noise while the user is not speaking."""
    samples = []
    blocks = max(1, int(seconds / 0.10))
    for _ in range(blocks):
        data, overflowed = stream.read(block)
        if overflowed:
            continue
        chunk = data[:, 0].copy()
        samples.append(_rms(chunk))

    if not samples:
        return 100.0

    # Median is robust against a short accidental sound during calibration.
    return float(np.median(samples))


def _tone(freq: float, duration: float, volume: float = 0.35) -> np.ndarray:
    """Gera um bipe curto (sem depender de arquivo nenhum) para dar pistas
    sonoras de quando falar — assim não é preciso ficar olhando o terminal."""
    n = max(1, int(AUDIO_SAMPLE_RATE * duration))
    t = np.linspace(0, duration, n, endpoint=False)
    wave_ = np.sin(2 * np.pi * freq * t)

    # fade in/out curtinho pra não estalar (clique) no alto-falante
    fade = min(n // 4, int(0.01 * AUDIO_SAMPLE_RATE))
    if fade > 0:
        ramp = np.linspace(0, 1, fade)
        wave_[:fade] *= ramp
        wave_[-fade:] *= ramp[::-1]

    return (wave_ * volume * 32767).astype(np.int16)


def play_tone(freq: float = 880.0, duration: float = 0.12, volume: float = 0.35):
    """Toca um bipe curto. Nunca derruba o programa se o alto-falante falhar.

    No Windows usa winsound.Beep(), que é uma API do sistema operacional
    totalmente separada do PortAudio — por isso funciona mesmo com o
    microfone (sd.InputStream) já aberto e gravando ao mesmo tempo. Antes
    o bipe usava sd.play(), que às vezes falhava nesse cenário (disputa
    de recurso de áudio) sem avisar em lugar nenhum visível — daí o "pode
    falar" aparecia no painel, mas o som não tocava.
    """
    if _HAS_WINSOUND:
        try:
            winsound.Beep(max(37, min(32767, int(freq))), max(1, int(duration * 1000)))
            return
        except Exception as exc:
            print(f"[ÁUDIO] winsound falhou ({exc}), tentando o alto-falante padrão...")

    try:
        sd.play(_tone(freq, duration, volume), AUDIO_SAMPLE_RATE)
        sd.wait()
    except Exception as exc:
        print(f"[ÁUDIO] Não consegui tocar o aviso sonoro: {exc}")


def play_wake_ack():
    """Bipe (dois tons subindo) tocado assim que o Jarvis reconhece 'Hey Jarvis' —
    avisa que ele ouviu e já vai começar a escutar o comando."""
    play_tone(700, 0.08)
    play_tone(1050, 0.10)


def play_listen_start():
    """Bipe único tocado bem antes de começar a gravar — o sinal de 'pode falar'."""
    play_tone(950, 0.10)


def play_listen_end():
    """Bipe tocado quando o Jarvis para de ouvir e vai processar o que foi dito."""
    play_tone(520, 0.09)


def play_session_end():
    """Dois tons descendo — toca quando a sessão de conversa acaba por
    silêncio e o Jarvis volta a esperar 'Hey Jarvis'."""
    play_tone(700, 0.09)
    play_tone(450, 0.12)


def record_command(output_path: Path | None = None, stop_event=None, on_ready=None) -> np.ndarray:
    print("[JARVIS] Prepare-se para falar...")
    print("[JARVIS] Calibrando ruído do microfone (não fale por ~1 segundo)...")

    block = max(256, int(0.10 * AUDIO_SAMPLE_RATE))
    max_frames = int(MAX_RECORD_SECONDS * AUDIO_SAMPLE_RATE)
    min_speech_frames = int(MIN_SPEECH_SECONDS * AUDIO_SAMPLE_RATE)
    pre_roll_blocks = max(1, int(PRE_ROLL_SECONDS / 0.10))

    chunks = []
    pre_roll = []
    total = 0
    speech_started = False
    silent_blocks = 0
    start = time.monotonic()

    device = _input_device()

    try:
        with sd.InputStream(
            device=device,
            samplerate=AUDIO_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=block,
            latency="high",
        ) as stream:

            noise_rms = _calibrate_noise(stream, block)
            # Adaptive threshold: never lower than configured floor.
            # This fixes the old problem where a room's background RMS (~180)
            # was above SILENCE_THRESHOLD=60, causing every recording to last 6s.
            threshold = max(float(SILENCE_THRESHOLD), noise_rms * SILENCE_MULTIPLIER)

            print(
                f"[ÁUDIO] Ruído ambiente RMS={noise_rms:.1f} | "
                f"limiar de voz={threshold:.1f}"
            )
            print("[JARVIS] Pode falar agora.")
            play_listen_start()
            if on_ready is not None:
                try:
                    on_ready()
                except Exception as exc:
                    print(f"[ÁUDIO] Callback on_ready falhou: {exc}")

            while total < max_frames:
                if stop_event is not None and stop_event.is_set():
                    break

                if time.monotonic() - start > MAX_RECORD_SECONDS + 2.0:
                    break

                data, overflowed = stream.read(block)
                if overflowed:
                    print("[ÁUDIO] Aviso: buffer do microfone sobrecarregou.")
                    continue

                chunk = data[:, 0].copy()
                level = _rms(chunk)

                if not speech_started:
                    pre_roll.append(chunk)
                    if len(pre_roll) > pre_roll_blocks:
                        pre_roll.pop(0)

                    if level >= threshold:
                        speech_started = True
                        chunks.extend(pre_roll)
                        total += sum(len(c) for c in pre_roll)
                        pre_roll.clear()
                        silent_blocks = 0
                    continue

                chunks.append(chunk)
                total += len(chunk)

                if level < threshold:
                    silent_blocks += 1
                    if (
                        total >= min_speech_frames
                        and silent_blocks >= max(1, int(SILENCE_SECONDS / 0.10))
                    ):
                        break
                else:
                    silent_blocks = 0

    except Exception as exc:
        print(f"[ERRO ÁUDIO] Falha ao acessar o microfone: {exc}")
        return np.zeros(0, dtype=np.int16)

    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    audio = _normalize(audio)

    # Só bipa "fim de fala" se realmente capturou alguma coisa — se ficou em
    # silêncio total, quem chamou decide o aviso sonoro (ex.: encerrar sessão).
    if speech_started:
        play_listen_end()

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak >= 32760:
        print("[ÁUDIO] Aviso: sinal próximo do clipping (volume muito alto).")

    if output_path:
        save_wav(output_path, audio)

    print(f"[JARVIS] Áudio capturado: {len(audio)/AUDIO_SAMPLE_RATE:.2f}s")
    return audio


def play_wav(path: Path):
    from scipy.io.wavfile import read
    rate, data = read(str(path))
    sd.play(data, rate)
    sd.wait()
