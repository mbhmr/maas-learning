"""The learning loop: blocked-line reasons become writer rules; off unless switched on."""
import json

from src import lessons


def test_category_strips_retry_and_rewrite_marks():
    assert lessons.category("context line with a figure (rewrite tried)") == "context line with a figure"
    assert lessons.category("rewrite blocked: numbers not in sources: [3.0]") == "numbers not in sources"
    assert lessons.category("content check: says rose, quote says fell") == "content check"
    assert lessons.detail("content check: says rose, quote says fell") == "says rose, quote says fell"


def test_length_cut_is_not_a_lesson():
    assert lessons.category("over the requested length") is None
    assert lessons.category("context for a story whose news was not spoken") is None


def test_learn_counts_and_keeps_two_examples(tmp_path):
    drops = [{"text": f"line {n}", "why": "numbers not in sources: [1.0]"} for n in range(3)]
    drops += [{"text": "x", "why": "over the requested length"}, {"text": "y", "why": "content check: invented cause"}]
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "briefing.json").write_text(json.dumps({"dropped": drops}), encoding="utf-8")
    got = lessons.learn(lessons.briefing_files(tmp_path))
    assert got["briefings"] == 1 and got["blocked"] == 4
    top = got["lessons"][0]
    assert top["reason"] == "numbers not in sources" and top["count"] == 3 and len(top["examples"]) == 2
    assert got["lessons"][1]["examples"][0]["why"] == "invented cause"


def test_prompt_block_off_by_default_and_on_when_forced(monkeypatch):
    data = {"briefings": 3, "lessons": [{"reason": "no source", "count": 2, "rule": lessons.RULES["no source"],
                                         "examples": [{"text": "A line.", "why": ""}]}]}
    monkeypatch.setattr(lessons, "ENABLED", False)
    assert lessons.prompt_block(data) == ""
    block = lessons.prompt_block(data, force=True)
    assert "3 earlier briefings" in block and lessons.RULES["no source"] in block and '"A line."' in block


def test_prompt_block_without_file(monkeypatch, tmp_path):
    monkeypatch.setattr(lessons, "LESSONS", tmp_path / "missing.json")
    assert lessons.prompt_block(force=True) == ""
