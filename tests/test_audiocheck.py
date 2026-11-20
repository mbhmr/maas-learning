

def test_spelled_numbers_from_speech_recognition():
    from src.audiocheck import _heard_numbers as heard, _missing
    assert {0.3, 0.4, 13.0} <= heard("On thirteen November prices rose zero point three percent, below zero point four", "en")
    assert {130.0, 125.25} <= heard("one hundred and thirty billion, above one hundred and twenty-five point two five billion", "en")
    assert not _missing({2022.0}, heard("since November twenty-twenty-two", "en"))
    assert {83.0, 825.0, 0.3} <= heard("auf dreiundachtzig Dollar, achthundertfünfundzwanzig Millionen, null Komma drei", "de")
    assert {83.0, 825.0, 1.5} <= heard("drieëntachtig dollar, achthonderdvijfentwintig miljoen, anderhalf biljoen", "nl")
    assert 4.0 in heard("Die Inflation lag bei 4,0 Prozent", "de")


def test_ordinal_digits_stay_one_number():
    from src.audiocheck import _heard_numbers
    assert _heard_numbers("on November 16th, and 4.0 percent", "en") >= {16.0, 4.0}
    assert 1.0 not in _heard_numbers("on November 16th", "en")
