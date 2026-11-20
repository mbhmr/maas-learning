"""src/tts.py: spoken_form and the time mapping in speak(), with a fake httpx response (no network)."""
import base64

import pytest

from src import tts
from src.tts import spoken_form


@pytest.mark.parametrize("lang,text,expect", [
    ("en", "Rose 0.3% m/m", "Rose 0.3 percent month on month"),
    ("en", "USD/JPY and Q3 and CEO", "dollar yen and third quarter and C E O"),
    ("de", "Plus 0,3% im Q2", "Plus 0,3 Prozent im 2. Quartal"),
    ("nl", "Q4 en 5%", "kwartaal 4 en 5 procent"),
    ("fr", "Q3 5%", "Q3 5%"),  # unknown language: unchanged
])
def test_spoken_form(lang, text, expect):
    assert spoken_form(text, lang) == expect


def test_spoken_form_has_no_double_spaces():
    assert "  " not in spoken_form("5 % and 6%", "en")


class FakeResp:
    status_code = 200
    text = ""

    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


@pytest.fixture
def fake_tts(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(tts, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(tts, "log_usage", lambda e: None)
    sent = {}

    def install(parts_text_len, status=200, short=False, lang_parts=None):
        def post(url, **kw):
            sent.update(kw)
            n = parts_text_len(kw["json"]["text"])
            starts = [i * 0.1 for i in range(n - (1 if short else 0))]
            ends = [i * 0.1 + 0.1 for i in range(n - (1 if short else 0))]
            return FakeResp({"audio_base64": base64.b64encode(b"MP3").decode(),
                             "alignment": {"character_start_times_seconds": starts,
                                           "character_end_times_seconds": ends}}, status)
        monkeypatch.setattr(tts.httpx, "post", post)
    return install, sent, tmp_path / "out.mp3"


def test_speak_maps_parts_to_times(fake_tts):
    install, sent, path = fake_tts
    install(len)
    spans = tts.speak(["Hello", "World"], path)
    # text = "Hello\n\nWorld": Hello = chars 0..5, World = chars 7..12, char i starts at i * 0.1
    assert spans == [(0.0, 0.5), (0.7, 1.2)]
    assert sent["json"]["text"] == "Hello\n\nWorld"
    assert path.read_bytes() == b"MP3"


def test_speak_times_follow_spoken_form_not_written(fake_tts):
    install, sent, path = fake_tts
    install(len)
    spans = tts.speak(["Up 5%", "Done"], path)
    assert sent["json"]["text"] == "Up 5 percent\n\nDone"
    assert spans[0] == (0.0, 1.2) and spans[1][0] == 1.4


def test_speak_unusable_alignment_gives_none(fake_tts):
    install, _, path = fake_tts
    install(len, short=True)
    assert tts.speak(["A", "B"], path) == [None, None]


def test_speak_empty_part_has_no_span(fake_tts):
    install, _, path = fake_tts
    install(len)
    spans = tts.speak(["Hi", "", "There"], path)
    assert spans[1] is None and spans[0] is not None and spans[2] is not None


def test_speak_error_status_raises(fake_tts):
    install, _, path = fake_tts
    install(len, status=401)
    with pytest.raises(RuntimeError, match="401"):
        tts.speak(["A"], path)


def test_speak_without_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(tts, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(tts.httpx, "post", lambda *a, **k: pytest.fail("no call without key"))
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        tts.speak(["A"], tmp_path / "x.mp3")


# ---------------------------------------------------------------- voice and audio tags
def test_default_voice_is_jessica_and_v3_natural(fake_tts, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    install, sent, path = fake_tts
    seen = {}
    real_post = None

    def post(url, **kw):
        seen["url"] = url
        return real_post(url, **kw)
    install(len)
    real_post = tts.httpx.post
    monkeypatch.setattr(tts.httpx, "post", post)
    tts.speak(["Hi"], path)
    assert "cgSgspJ2msm6clMCkdW9" in seen["url"]
    assert sent["json"]["model_id"] == "eleven_v3" and sent["json"]["voice_settings"]["stability"] == 0.5


def test_tags_only_in_speech_and_spans_skip_them(fake_tts, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    install, sent, path = fake_tts
    install(len)  # alignment covers every character sent, tags included
    spans = tts.speak(["Hello", "Up 5%", "Bye"], path, tags=["excited", "", "cheerful"])
    text = sent["json"]["text"]
    assert text == "[excited] Hello\n\nUp 5 percent\n\n[cheerfully] Bye"
    # char i starts at i * 0.1: "Hello" = chars 10..15, "Up 5 percent" = 17..29, "Bye" = 44..47
    assert spans == [(1.0, 1.5), (1.7, 2.9), (4.4, 4.7)]
    assert text[10:15] == "Hello" and text[44:47] == "Bye"


def test_alignment_without_tags_still_maps(fake_tts, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    install, sent, path = fake_tts
    install(lambda t: len(t.replace("[excited] ", "")))  # the service leaves the tags out of its alignment
    spans = tts.speak(["Hello", "World"], path, tags=["excited"])
    assert sent["json"]["text"].startswith("[excited] Hello")
    assert spans == [(0.0, 0.5), (0.7, 1.2)]


def test_no_tags_for_other_models(fake_tts, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    install, sent, path = fake_tts
    install(len)
    tts.speak(["Hello"], path, tags=["excited"])
    assert sent["json"]["text"] == "Hello"
