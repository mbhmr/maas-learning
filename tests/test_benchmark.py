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


def _wording(text, quote="annual PPI inflation accelerated from 6.3% to 6.5%."):
    return b.check(brief("en", claim(text, quote)))["wording"][0]


def test_bare_inflation_for_ppi_is_caught_in_its_own_clause():
    # gegenleser 21.11.: "producer" in the clause before must not excuse the bare "annual inflation"
    assert not _wording("US producer prices rose, and annual inflation accelerated to 6.5 percent.")
    assert not _wording("US PPI rose 0.3 percent, with annual inflation at 6.5 percent.")
    assert not _wording("Producer prices rose. Annual inflation accelerated to 6.5 percent.")
    assert _wording("Annual PPI inflation accelerated to 6.5 percent.")
    assert _wording("Inflation in producer prices accelerated to 6.5 percent.")
    assert _wording("US wholesale inflation rose to 6.5 percent.")


def test_month_with_year_before_the_release_date_is_caught():
    q = "The PPI rose 0.3% in October."
    assert not _wording("US PPI rose 0.3 percent in October 2026 on 18 November.", q)
    assert _wording("On 18 November, data showed US PPI rose 0.3 percent in October.", q)


def test_figure_in_a_context_line_is_checked_too():
    c = claim("Producer prices rose 9.9 percent.", "Producer prices rose 0.3% in October.")
    c["kind"] = "context"
    assert not b.check(brief("en", c))["figures"][0]


def test_same_release_after_a_merge_is_a_repeat():
    b.FACT_STORY.update({"s4-f1": "s4", "s5-f1": "s4"})
    one = claim("US retail sales rose 0.2 percent in October.", "Retail sales rose 0.2% in October.")
    two = claim("Retail sales were up 0.2 percent last month.", "US retail sales slowed to 0.2%.")
    one["sources"][0]["factId"], two["sources"][0]["factId"] = "s4-f1", "s5-f1"
    one["sources"][0]["articleId"], two["sources"][0]["articleId"] = "A", "B"
    assert not b.check(brief("en", one, two))["no_repeats"][0]


def test_small_whole_figures_count_take_two_does_not():
    one = claim("Intel shares fell 9 percent and it cut 5 of 8 fabs.", "Shares fell 9% as Intel cut 5 of its 8 fabs.")
    assert not b.check(brief("en", one, dict(one)))["no_repeats"][0]
    a = claim("Take-Two shares rose 5 percent.", "Take-Two shares rose 5%.")
    c = claim("US yields rose to 5 percent.", "Yields rose to 5%.")
    a["sources"][0]["articleId"], c["sources"][0]["articleId"] = "A", "C"
    assert b.check(brief("en", a, c))["no_repeats"][0]


def test_unknown_article_fails_verbatim():
    c = claim("Producer prices rose 0.3 percent.", "Producer prices rose 0.3% in October.")
    c["sources"][0]["articleId"] = "made-up"
    assert not b.check(brief("en", c), articles={"real": "producer prices rose 0.3% in october."})["verbatim"][0]
