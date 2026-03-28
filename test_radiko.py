import unittest
from pathlib import Path
from unittest.mock import patch
from radiko import Radiko, Program


def make_radiko() -> Radiko:
    return Radiko(Path('rec.sh'), '', '', Path('/tmp'), Path('/tmp/storage'))


def make_program(**kwargs) -> Program:
    defaults = dict(
        station='LFR',
        radiko_title='テスト番組',
        start_time='20260328100000',
        end_time='20260328120000',
        img='',
        pfm='テスト出演者',
        title_key='テスト番組',
        series_key='テスト番組',
        duration=7200,
    )
    defaults.update(kwargs)
    return Program(**defaults)


WORDS_CF = {
    'words_by_mode': {'contains': ['テスト']},
    'stations': ['LFR'],
}

TITLE_CF = {
    'station': 'LFR',
    'radiko_title': 'テスト番組',
    'title_match_mode': 'contains',
    'artist': 'テスト出演者',
    'album': 'テストアルバム',
    'title': '%Y-%m-%d',
    'filename': 'テスト番組_%Y%m%d',
    'storage_dir': '{album}/%Y',
    'series_key': 'テスト番組',
}


class TestRecordingByWords(unittest.TestCase):
    def setUp(self):
        self.r = make_radiko()

    def test_returns_copy_not_original(self):
        pg = make_program()
        result = self.r._recording_by_words(pg, WORDS_CF)
        self.assertIsNotNone(result)
        self.assertIsNot(result, pg)

    def test_does_not_mutate_original(self):
        pg = make_program()
        original_artist = pg.artist
        original_found_by = pg.found_by
        self.r._recording_by_words(pg, WORDS_CF)
        self.assertEqual(pg.artist, original_artist)
        self.assertEqual(pg.found_by, original_found_by)

    def test_found_by_words(self):
        pg = make_program()
        result = self.r._recording_by_words(pg, WORDS_CF)
        self.assertEqual(result.found_by, 'words')

    def test_filename_format(self):
        pg = make_program()
        result = self.r._recording_by_words(pg, WORDS_CF)
        self.assertEqual(result.filename, 'テスト番組_20260328.m4a')

    def test_no_match_returns_none(self):
        pg = make_program(radiko_title='全然違う番組', pfm='')
        result = self.r._recording_by_words(pg, WORDS_CF)
        self.assertIsNone(result)

    def test_pfm_match(self):
        pg = make_program(radiko_title='全然違う番組', pfm='テスト太郎')
        result = self.r._recording_by_words(pg, WORDS_CF)
        self.assertIsNotNone(result)
        self.assertEqual(result.found_by, 'words')


class TestRecordingByTitle(unittest.TestCase):
    def setUp(self):
        self.r = make_radiko()

    def test_returns_copy_not_original(self):
        pg = make_program()
        result = self.r._recording_by_title(pg, TITLE_CF)
        self.assertIsNotNone(result)
        self.assertIsNot(result, pg)

    def test_does_not_mutate_original(self):
        pg = make_program()
        original_album = pg.album
        self.r._recording_by_title(pg, TITLE_CF)
        self.assertEqual(pg.album, original_album)

    def test_found_by_title(self):
        pg = make_program()
        result = self.r._recording_by_title(pg, TITLE_CF)
        self.assertEqual(result.found_by, 'title')

    def test_album_tag_expanded_in_storage_dir(self):
        pg = make_program()
        result = self.r._recording_by_title(pg, TITLE_CF)
        # storage_dir: '{album}/%Y' → 'テストアルバム/2026'
        self.assertEqual(result.storage_dir, 'テストアルバム/2026')

    def test_artist_tag_expanded_in_storage_dir(self):
        cf = dict(TITLE_CF, storage_dir='{artist}/%Y')
        pg = make_program()
        result = self.r._recording_by_title(pg, cf)
        self.assertEqual(result.storage_dir, 'テスト出演者/2026')

    def test_station_mismatch_returns_none(self):
        pg = make_program(station='TBS')
        result = self.r._recording_by_title(pg, TITLE_CF)
        self.assertIsNone(result)

    def test_title_mismatch_returns_none(self):
        pg = make_program(radiko_title='全然違う番組')
        result = self.r._recording_by_title(pg, TITLE_CF)
        self.assertIsNone(result)


class TestFilterPrograms(unittest.TestCase):
    def setUp(self):
        self.r = make_radiko()

    def test_words_only_match(self):
        pg = make_program()
        result = self.r._filter_programs([pg], [WORDS_CF])
        self.assertEqual(len(result), 1)
        pg_out = list(result.values())[0]
        self.assertEqual(pg_out.found_by, 'words')

    def test_title_only_match(self):
        pg = make_program()
        result = self.r._filter_programs([pg], [TITLE_CF])
        self.assertEqual(len(result), 1)
        pg_out = list(result.values())[0]
        self.assertEqual(pg_out.found_by, 'title')

    def test_title_wins_over_words_when_both_match(self):
        pg = make_program()
        radio = [WORDS_CF, TITLE_CF]
        result = self.r._filter_programs([pg], radio)
        self.assertEqual(len(result), 1)
        pg_out = list(result.values())[0]
        self.assertEqual(pg_out.found_by, 'title')

    def test_title_wins_over_words_regardless_of_order(self):
        pg = make_program()
        radio = [TITLE_CF, WORDS_CF]
        result = self.r._filter_programs([pg], radio)
        self.assertEqual(len(result), 1)
        pg_out = list(result.values())[0]
        self.assertEqual(pg_out.found_by, 'title')

    def test_no_match_excluded(self):
        pg = make_program(radiko_title='全然違う番組', pfm='')
        result = self.r._filter_programs([pg], [WORDS_CF, TITLE_CF])
        self.assertEqual(len(result), 0)


class TestDedupeKey(unittest.TestCase):
    def setUp(self):
        self.r = make_radiko()

    def test_same_day_different_time_same_key(self):
        pg1 = make_program(station='LFR', start_time='20260328100000')
        pg2 = make_program(station='TBS', start_time='20260328150000')
        word_rules = [('テスト', 'contains')]
        key1 = self.r._dedupe_key(pg1, word_rules)
        key2 = self.r._dedupe_key(pg2, word_rules)
        self.assertEqual(key1, key2)

    def test_different_day_different_key(self):
        pg1 = make_program(start_time='20260328100000')
        pg2 = make_program(start_time='20260329100000')
        word_rules = [('テスト', 'contains')]
        key1 = self.r._dedupe_key(pg1, word_rules)
        key2 = self.r._dedupe_key(pg2, word_rules)
        self.assertNotEqual(key1, key2)

    def test_word_key_takes_priority_over_series_key(self):
        pg = make_program(series_key='別のキー')
        word_rules = [('テスト', 'contains')]
        key = self.r._dedupe_key(pg, word_rules)
        self.assertIn('テスト', key)
        self.assertNotIn('別のキー', key)

    def test_uses_radiko_title_not_series_key_when_no_word(self):
        pg = make_program(radiko_title='テスト番組', series_key='config定義キー')
        word_rules = []
        key = self.r._dedupe_key(pg, word_rules)
        # series_key ではなく _series_key(radiko_title) を使う
        expected_title = self.r._series_key('テスト番組')
        self.assertIn(expected_title, key)
        self.assertNotIn('config定義キー', key)


class TestGetProgramsDedup(unittest.TestCase):
    def setUp(self):
        self.r = make_radiko()

    def _make_filter_result(self, programs: list[Program]) -> dict:
        return {f'key_{i}': pg for i, pg in enumerate(programs)}

    def test_longer_duration_wins(self):
        pg_short = make_program(station='LFR', start_time='20260328100000',
                                end_time='20260328110000', duration=3600, found_by='words')
        pg_long = make_program(station='TBS', start_time='20260328150000',
                               end_time='20260328170000', duration=7200, found_by='words')
        word_rules = [('テスト', 'contains')]

        with patch.object(self.r, '_get_programs_xml', return_value=''), \
             patch.object(self.r, '_parse_programs_xml', return_value=[]):
            # 直接 dedup ロジックをシミュレート
            programs = {}
            for pg in [pg_short, pg_long]:
                key = self.r._dedupe_key(pg, word_rules)
                if key in programs:
                    d1 = self.r._duration(programs[key])
                    d2 = self.r._duration(pg)
                    if d2 > d1:
                        programs[key] = pg
                else:
                    programs[key] = pg

        self.assertEqual(len(programs), 1)
        self.assertEqual(list(programs.values())[0].duration, 7200)

    def test_same_duration_title_wins_over_words(self):
        pg_words = make_program(station='LFR', duration=3600, found_by='words')
        pg_title = make_program(station='TBS', duration=3600, found_by='title')
        word_rules = [('テスト', 'contains')]

        programs = {}
        for pg in [pg_words, pg_title]:
            key = self.r._dedupe_key(pg, word_rules)
            if key in programs:
                d1 = self.r._duration(programs[key])
                d2 = self.r._duration(pg)
                if d2 > d1:
                    programs[key] = pg
                elif d2 == d1:
                    existing_found_by = self.r._program_start(programs[key]).found_by
                    new_found_by = self.r._program_start(pg).found_by
                    if existing_found_by == 'words' and new_found_by == 'title':
                        programs[key] = pg
            else:
                programs[key] = pg

        self.assertEqual(list(programs.values())[0].found_by, 'title')


if __name__ == '__main__':
    unittest.main()
