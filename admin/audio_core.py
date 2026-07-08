"""Welsh text-to-speech for inscriptions, via Piper (open source).
Requires: pip3 install piper-tts   (the Welsh voice model, ~65MB, downloads
automatically on first use)."""
import os
import re
import urllib.request

VOICE = "cy_GB-gwryw_gogleddol-medium"   # Welsh (north), male
BASE = ("https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
        "cy/cy_GB/gwryw_gogleddol/medium/")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

_voice = None


def get_voice():
    global _voice
    if _voice is None:
        from piper.voice import PiperVoice
        os.makedirs(MODEL_DIR, exist_ok=True)
        onnx = os.path.join(MODEL_DIR, VOICE + ".onnx")
        for path, name in ((onnx, VOICE + ".onnx"),
                           (onnx + ".json", VOICE + ".onnx.json")):
            if not os.path.exists(path):
                urllib.request.urlretrieve(BASE + name, path)
        _voice = PiperVoice.load(onnx)
    return _voice


WELSH_HINTS = (r"\b(er cof|bu farw|fu farw|ganwyd|mlwydd|flwydd|oed|priod|"
               r"mab|merch|yr hwn|yr hon|hedd|diwrnod|wythnos|hunodd)\b")
ENGLISH_HINTS = (r"\b(in memory|memory of|died|born|aged|wife|son of|daughter|"
                 r"departed|this life|years|months)\b")


def is_welsh(text):
    t = text.lower()
    w = len(re.findall(WELSH_HINTS, t))
    e = len(re.findall(ENGLISH_HINTS, t))
    return w > 0 and w >= e


def clean(text):
    t = re.sub(r"\[DRAFT[^\]]*\]\s*", "", text)
    t = re.sub(r"\[\?\]|\[\.\.\.\]|\[[^\]]*\?\]", " ", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def synth(text, out_wav):
    import wave
    v = get_voice()
    os.makedirs(os.path.dirname(out_wav), exist_ok=True)
    with wave.open(out_wav, "wb") as w:
        v.synthesize(clean(text), w)
