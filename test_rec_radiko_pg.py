import sys
import unittest
from unittest.mock import MagicMock, patch

import rec_radiko_pg
from radiko import Program


def make_program(start: str) -> Program:
    return Program(
        station='LFR', radiko_title=f'番組{start}', start_time=start, end_time=start,
        img='', pfm='', title_key=f'番組{start}', series_key=f'番組{start}',
    )


class TestMainNotificationFailure(unittest.TestCase):
    def test_notification_failure_does_not_stop_remaining_recordings(self):
        programs = {
            'a': make_program('20200101100000'),
            'b': make_program('20200101110000'),
        }
        radiko = MagicMock()
        radiko.get_programs.return_value = programs
        radiko.fetch_errors = []
        radiko.record.side_effect = lambda pg: Program(**{**pg.__dict__, 'filepath': '/tmp/x.m4a'})
        email = MagicMock()
        email.send.side_effect = OSError('smtp down')
        latest = MagicMock()
        latest.get.return_value = ''

        with patch.object(sys, 'argv', ['rec_radiko_pg.py']), \
                patch.object(rec_radiko_pg, 'Radiko', return_value=radiko), \
                patch.object(rec_radiko_pg, 'Email', return_value=email), \
                patch.object(rec_radiko_pg, 'Latest', return_value=latest), \
                patch.object(rec_radiko_pg, 'load_radio', return_value=[]):
            rec_radiko_pg.main()

        self.assertEqual(radiko.record.call_count, 2)
        self.assertEqual(latest.save.call_count, 2)


if __name__ == '__main__':
    unittest.main()
