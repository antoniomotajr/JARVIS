import time
import numpy as np
import sounddevice as sd
from openwakeword.model import Model
from config import AUDIO_DEVICE_INDEX, AUDIO_SAMPLE_RATE, WAKE_THRESHOLD
from .audio import play_wake_ack


class _AGC:
    """Controle automático de ganho leve para o stream da wake word.

    A normalização de core/audio.py só é aplicada depois que a wake word já
    disparou (na gravação do comando). O stream de detecção lia o áudio cru
    do microfone, então um microfone com ganho baixo nunca gerava sinal
    forte o bastante para o modelo pontuar bem (ex.: pico=0.226 quando
    deveria passar de 0.50). Aqui seguimos um envelope de pico com decaimento
    lento: reage rápido a um som alto e amplifica frames fracos até um alvo,
    sem perseguir cada micro-variação de ruído.
    """

    def __init__(self, target_peak: float = 8000.0, max_gain: float = 10.0, decay: float = 0.995):
        self.target_peak = target_peak
        self.max_gain = max_gain
        self.decay = decay
        self.peak_estimate = target_peak  # começa neutro (ganho=1)

    def apply(self, frame: np.ndarray) -> np.ndarray:
        frame_peak = float(np.max(np.abs(frame))) if frame.size else 0.0
        if frame_peak > self.peak_estimate:
            self.peak_estimate = frame_peak
        else:
            self.peak_estimate = max(frame_peak, self.peak_estimate * self.decay)

        if self.peak_estimate < 1:
            return frame

        gain = min(self.max_gain, self.target_peak / self.peak_estimate)
        if gain <= 1.01:
            return frame

        boosted = frame.astype(np.float32) * gain
        np.clip(boosted, -32768, 32767, out=boosted)
        return boosted.astype(np.int16)


class WakeWordDetector:
    def __init__(self):
        print("[JARVIS] Carregando Wake Word...")
        self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        print(f"[WAKE] Limiar configurado: {WAKE_THRESHOLD:.2f}")
        print(f"[WAKE] Modelos: {list(self.model.models.keys())}")

    @staticmethod
    def _device():
        # sounddevice expects None for the default device, not -1.
        if AUDIO_DEVICE_INDEX is None or AUDIO_DEVICE_INDEX < 0:
            return None
        return AUDIO_DEVICE_INDEX

    def wait(self, stop_event=None) -> bool:
        print('[JARVIS] Aguardando "Jarvis"...')
        blocksize = 1280  # 80 ms at 16 kHz
        device = self._device()
        if device is None:
            print("[ÁUDIO] Wake Word usando o microfone padrão do Windows.")

        # The built-in openWakeWord model is named hey_jarvis.
        # Say "Hey Jarvis" for the most reliable detection.
        print('[WAKE] Fale: "Hey Jarvis"')
        last_report = time.monotonic()
        best_score = 0.0

        # O score costuma aparecer como um único pico isolado (0.96, 0.50,
        # 0.42...) que sobe e cai num só frame de 80ms — exigir 2 acertos,
        # mesmo dentro de uma janela, raramente acontecia na prática.
        # Disparamos já no primeiro frame que passar do limiar; o risco de
        # falso positivo é baixo porque o score fica perto de zero fora da
        # wake word (dá pra ver isso nos logs "aguardando...").
        agc = _AGC()

        try:
            with sd.RawInputStream(
                device=device,
                samplerate=AUDIO_SAMPLE_RATE,
                blocksize=blocksize,
                dtype="int16",
                channels=1,
                latency="high",
            ) as stream:
                while True:
                    if stop_event is not None and stop_event.is_set():
                        return False

                    data, overflowed = stream.read(blocksize)
                    if overflowed:
                        continue

                    audio = np.frombuffer(data, dtype=np.int16)
                    if audio.size == 0:
                        continue
                    audio = agc.apply(audio)

                    prediction = self.model.predict(audio)
                    score = max(
                        (float(v) for k, v in prediction.items() if "jarvis" in k.lower()),
                        default=0.0,
                    )
                    best_score = max(best_score, score)

                    if time.monotonic() - last_report >= 2.0:
                        print(f"[WAKE] aguardando... score={score:.3f} | pico={best_score:.3f}")
                        last_report = time.monotonic()

                    if score >= WAKE_THRESHOLD:
                        print(f"[JARVIS] Wake Word detectada! score={score:.3f}")
                        play_wake_ack()
                        return True

        except Exception as exc:
            print(f"[ERRO ÁUDIO] Falha ao acessar microfone: {exc}")
            time.sleep(1)
            return False
