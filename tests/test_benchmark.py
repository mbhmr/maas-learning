"""The jury benchmark must fail what is wrong, not only pass what is right."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import benchmark as b  # noqa: E402


def claim(text, quote, publisher="Invezz", date="2026-11-18"):
    return {"kind": "claim", "text": text, "sources": [{"quote": quote, "url": "u", "publisher": publisher,
                                                        "date": date, "articleId": "a"}]}


def brief(lang, *claims):
    return {"profile": {"language": lang, "seconds": 30}, "claims": list(claims), "audioPath": None}


def test_wrong_scale_and_german_reading_of_an_english_decimal_fail():
    assert b.check(brief("de", claim("Umsatz 1,5 Millionen Dollar.", "Revenue was $1.5 billion.")))["figures"][0] is False
    assert b.check(brief("de", claim("Er hält 6.077 Millionen ETH.", "It holds 6.077 million ETH.")))["figures"][0] is False
    assert b.check(brief("de", claim("Er hält 6,077 Millionen ETH.", "It holds 6.077 million ETH.")))["figures"][0]
    assert b.check(brief("nl", claim("Voorraden met 351.000 vaten.", "Stocks rose 351K barrels.")))["figures"][0]


def test_year_only_as_part_of_a_date():
    ok = claim("Prices rose in October 2026.", "Prices rose in October.")
    bad = claim("Prices rose 2026 percent.", "Prices rose in October.")
    assert b.check(brief("en", ok))["figures"][0] and b.check(brief("en", bad))["figures"][0] is False


def test_language_and_advice():
    assert b.language_of("That keeps the dollar in view for you.") == "en"
    assert b.language_of("Dat houdt de dollar in beeld.") == "nl"
    assert b.language_of("NVIDIA stond op de afpersingssite van The Gentlemen.") == "nl"
    assert b.ADVICE.search("You should buy Nvidia now") and not b.ADVICE.search("De verkopen stegen")
