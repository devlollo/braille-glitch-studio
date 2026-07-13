"""Microphone level input for audio-reactive glitching.

A background sounddevice stream tracks a smoothed 0..1 loudness envelope —
fast attack, slow release, so hits punch the glitch up and it decays
musically. The studio multiplies this by the "audio gain" knob and feeds it
into the engine's glitch target.

Everything degrades gracefully: if sounddevice/PortAudio is missing or the
mic can't open (no permission, no device), `start()` returns False and the
studio just shows audio as unavailable.
"""
import numpy as np

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None


class MicLevel:
    def __init__(self, samplerate=None, blocksize=512):
        # samplerate=None -> the device's default rate; forcing one (e.g.
        # 22050) makes stream-open fail on mics that don't support it.
        self.level = 0.0                    # smoothed envelope, ~0..1
        self.available = sd is not None
        self._samplerate = samplerate
        self._blocksize = blocksize
        self._stream = None

    @property
    def running(self):
        return self._stream is not None

    def start(self):
        if not self.available:
            return False
        if self._stream is not None:
            return True
        try:
            self._stream = sd.InputStream(channels=1, samplerate=self._samplerate,
                                          blocksize=self._blocksize, callback=self._callback)
            self._stream.start()
            return True
        except Exception:
            # transient failure (mic busy, device switching, permission not
            # yet granted) — stay available so the user can just retry
            self._stream = None
            return False

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.level = 0.0

    def _callback(self, indata, frames, time_info, status):
        if frames == 0:
            return
        rms = float(np.sqrt(np.mean(indata[:, 0] ** 2)))
        x = min(1.0, rms * 8.0)             # speech/music RMS is roughly 0.02-0.3
        if not np.isfinite(x):
            return                          # a nan here would stick in the envelope forever
        if x > self.level:
            self.level = self.level * 0.4 + x * 0.6    # fast attack
        else:
            self.level = self.level * 0.92 + x * 0.08  # slow release
