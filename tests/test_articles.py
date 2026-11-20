"""Own data: any file names, the feed comes from the record."""
import json

from src.articles import load_articles


def rec(i, pub, lang):
    return {"$id": i, "publication": {"name": pub}, "language": lang, "date": "2026-11-17T08:00:00+00:00",
            "headline": "H", "text_content": "Body.", "permalink": f"https://x/{i}", "source": "A"}


def test_any_file_names_and_feed_from_record(tmp_path):
    lines = [rec("1", "Invezz - German", "de"), rec("2", "IBTimes UK", "en"), {**rec("3", "Zacks", "en"), "permalink": ""}]
    (tmp_path / "my-export.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n\n", encoding="utf-8")
    got = load_articles(data=tmp_path)
    assert set(got) == {"1", "2"}  # no link: skipped
    assert got["1"]["feed"] == "invezz_de" and got["2"]["feed"] == "ibtimes_uk"
