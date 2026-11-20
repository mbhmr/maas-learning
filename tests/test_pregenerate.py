"""Every shared edition of a day is one key: 3 languages x 6 lengths x 3 depths x 6 segments."""
import pregenerate
from src import editions


def test_all_keys_are_the_keys_listeners_map_to():
    keys = pregenerate.all_keys()
    assert len(keys) == 3 * len(editions.LENGTHS) * len(editions.DEPTHS) * len(editions.SEGMENTS) == 324
    key, parts = keys[0]
    profile = {"language": parts["language"], "seconds": parts["seconds"], "depth": editions.DEPTHS[parts["depth"]]}
    assert editions.edition_key(profile, parts["segment"])[0] == key
