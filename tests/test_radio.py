"""The cuisine to radio mapping covers every cuisine and picks playable stations."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "culina"))

from cuisines import CUISINES  # noqa: E402
from radio import CUISINE_COUNTRY, CUISINE_TAGS, first_playable, looks_like_mp3  # noqa: E402


def station(**kwargs):
    base = dict(url="http://x", url_resolved="http://x", hls=False, codec="MP3", tags=[])
    return SimpleNamespace(**{**base, **kwargs})


class MappingTest(unittest.TestCase):
    def test_every_cuisine_has_a_country(self):
        self.assertEqual(set(CUISINES) - set(CUISINE_COUNTRY), set())

    def test_tags_only_for_known_cuisines(self):
        self.assertEqual(set(CUISINE_TAGS) - set(CUISINES), set())


class PlayableTest(unittest.TestCase):
    def test_skips_hls_and_odd_codecs(self):
        picked = first_playable([station(hls=True), station(codec="OGG"), station(url_resolved=""), station(codec="AAC+")])
        self.assertEqual(picked.codec, "AAC+")

    def test_skips_talk_only_when_asked(self):
        stations = [station(tags=["news", "public radio"]), station(tags="pop, hits")]
        self.assertEqual(first_playable(stations).tags, ["news", "public radio"])
        self.assertEqual(first_playable(stations, skip_talk=True).tags, "pop, hits")

    def test_mp3_before_aac(self):
        picked = first_playable([station(codec="AAC+", tags=["a"]), station(codec="MP3", tags=["b"])])
        self.assertEqual(picked.tags, ["b"])

    def test_skips_mms(self):
        self.assertIsNone(first_playable([station(url_resolved="mms://x")]))
        self.assertIsNone(first_playable([station(url="mms://x")]))

    def test_talk_matches_fragments(self):
        self.assertIsNone(first_playable([station(tags=["talk news"]), station(tags=["islamic"])], skip_talk=True))

    def test_none_when_nothing_fits(self):
        self.assertIsNone(first_playable([station(hls=True)]))


if __name__ == "__main__":
    unittest.main()


class Mp3SniffTest(unittest.TestCase):
    def test_mp3_frame(self):
        self.assertTrue(looks_like_mp3(b"\xff\xfb\x90\x00" + b"\x00" * 20))

    def test_adts_aac_on_mp3_url(self):
        self.assertFalse(looks_like_mp3(b"\xff\xf1\x50\x80\x44\x1f\xfc" + b"\x00" * 20))

    def test_id3_then_mp3(self):
        id3 = b"ID3\x04\x00\x00\x00\x00\x00\x05" + b"\x00" * 5
        self.assertTrue(looks_like_mp3(id3 + b"\xff\xfb\x90\x00"))

    def test_garbage(self):
        self.assertFalse(looks_like_mp3(b"<html>not audio</html>"))
