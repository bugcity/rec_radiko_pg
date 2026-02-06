import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass
import subprocess
from logging import getLogger
from pathlib import Path
from mutagen.mp4 import MP4, MP4Cover
import os
from .audio_concatenator import AudioConcatenator
import jaconv
import re
from typing import Union
import unicodedata


logger = getLogger(__name__)


@dataclass
class Words:
    words: list
    stations: list


@dataclass
class Program:
    station: str
    radiko_title: str
    start_time: str
    end_time: str
    img: str
    pfm: str
    filename: str = ''
    artwork: str = ''
    album: str = ''
    artist: str = ''
    title: str = ''
    storage_dir: str = ''
    title_key: str = ''
    series_key: str = ''
    found_by: str = ''
    dulation: int = 0
    filepath: str = ''


class Radiko:
    MULTI_PART_MAX_GAP_SECONDS = 10 * 60
    DEFAULT_SERIES_KEY_STRIP_REGEX = [
        r'第?\d+回$',
        r'\d+時台$',
        r'エンディング$',
    ]

    def __init__(self, rec_radiko_ts_sh: Path, radiko_email: str, radiko_pw: str, tmp_dir: Path, storage_dir: Path):
        self.rec_radiko_ts_sh = rec_radiko_ts_sh
        self.radiko_email = radiko_email
        self.radiko_pw = radiko_pw
        self.tmp_dir = tmp_dir
        self.storage_dir = storage_dir
        self.series_key_strip_regex = list(self.DEFAULT_SERIES_KEY_STRIP_REGEX)

    def _station_list(self, radio: list) -> list:
        stations = set()
        for pg in radio:
            if 'station' in pg:
                stations.add(pg['station'])
            if 'stations' in pg:
                stations.update(pg['stations'])
        return list(stations)

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ''
        text = unicodedata.normalize('NFKC', text)
        text = jaconv.z2h(text, kana=False, ascii=True, digit=True)
        text = text.lower()
        text = re.sub(r'\s+', '', text)
        text = re.sub(r'[!！?？・･:：\-ー~〜_/／\(\)\[\]【】「」『』<>＜＞☆★♪＊*\.、。,]', '', text)
        return text

    def _series_key(self, title: str) -> str:
        key = self._normalize_text(title)
        for pattern in self.series_key_strip_regex:
            try:
                key = re.sub(pattern, '', key)
            except re.error:
                logger.warning(f'invalid regex in series_key_strip_regex: {pattern}')
        return key

    def _series_key_strip_regex_config(self, radio: list) -> list[str]:
        for pg in radio:
            if 'series_key_strip_regex' in pg:
                return pg['series_key_strip_regex']
        return list(self.DEFAULT_SERIES_KEY_STRIP_REGEX)

    def _title_matched(self, title: str, words: list[str], mode: str) -> bool:
        if mode == 'regex':
            return any(re.search(word, title, re.IGNORECASE) for word in words)

        normalized_title = self._normalize_text(title)
        for word in words:
            normalized_word = self._normalize_text(word)
            if not normalized_word:
                continue
            if mode == 'exact' and normalized_title == normalized_word:
                return True
            if mode == 'contains' and normalized_word in normalized_title:
                return True
            if mode == 'prefix' and normalized_title.startswith(normalized_word):
                return True
        return False

    def _replace_config(self, radio: list) -> dict:
        replace_config = {}
        for pg in radio:
            if 'words_by_mode' in pg:
                if 'replace' in pg:
                    replace_config = pg['replace']
                break
        return replace_config

    def _word_match_rules(self, cf: dict) -> list[tuple[str, str]]:
        rules = []
        # words_by_mode: {contains: [...], exact: [...]}
        for mode, words in cf.get('words_by_mode', {}).items():
            for word in words:
                rules.append((word, mode))

        return rules

    def _get_programs_xml(self, station: str) -> str:
        url = f'http://radiko.jp/v3/program/station/weekly/{station}.xml'
        response = requests.get(url)
        return response.text

    def _parse_programs_xml(self, xml: str, replace_config: dict) -> list:
        progs = []
        root = ET.fromstring(xml)
        for stat in root.findall('.//station'):
            station = stat.attrib['id']
            break

        for prog in root.findall('.//prog'):
            ft = prog.attrib['ft']
            to = prog.attrib['to']
            title = prog.find('title').text
            img = prog.find('img').text
            pfm = prog.find('pfm').text
            if not pfm:
                pfm = ''

            if not title:
                continue

            for key, value in replace_config.items():
                title = title.replace(key, value)

            title_key = title
            title_key = jaconv.z2h(title_key, kana=False, ascii=True, digit=True)
            title_key = re.sub(r' \(\d+\)$', '', title_key)
            title_key = re.sub(r'\(\d+時台\)$', '', title_key)
            title_key = re.sub(r'\(エンディング\)$', '', title_key)

            ft_dt = datetime.strptime(ft, '%Y%m%d%H%M%S')
            to_dt = datetime.strptime(to, '%Y%m%d%H%M%S')
            dulation = (to_dt - ft_dt).seconds

            progs.append(
                Program(
                    station=station,
                    radiko_title=title,
                    start_time=ft,
                    end_time=to,
                    img=img,
                    pfm=pfm.replace('\u3000', ' '),
                    title_key=title_key,
                    series_key=self._series_key(title),
                    dulation=dulation
                )
            )

        return progs

    def _replace_tag(self, pg: Program, start_time: datetime, init_val: str) -> str:

        val = datetime.strftime(start_time, init_val)

        val = val.replace('{pfm}', pg.pfm if pg.pfm else '')
        if pg.album:
            val = val.replace('{album}', pg.album)
        if pg.title:
            val = val.replace('{title}', pg.title)
        if pg.artist:
            val = val.replace('{artist}', pg.artist)
        return val

    def _recording_by_words(self, pg: Program, cf: dict) -> Program:
        start_time = datetime.strptime(pg.start_time, '%Y%m%d%H%M%S')
        rules = self._word_match_rules(cf)
        for word, mode in rules:
            if self._title_matched(pg.radiko_title, [word], mode) or self._title_matched(pg.pfm, [word], mode):
                pg.artist = pg.pfm
                pg.album = pg.title_key
                pg.title = pg.title_key
                pg.filename = self._replace_tag(pg, start_time, pg.title_key + '_%Y%m%d') + '.m4a'
                pg.storage_dir = pg.title_key
                pg.found_by = 'words'
                return pg
        return None

    def _recording_by_title(self, pg: Program, cf: dict) -> Program:
        start_time = datetime.strptime(pg.start_time, '%Y%m%d%H%M%S')
        weekdays = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']

        if 'radiko_dayw' in cf:
            weekday_num = start_time.weekday()
            weekday = weekdays[weekday_num]
            same_weekday = (weekday == cf['radiko_dayw'])
        else:
            same_weekday = True

        station = cf['station']
        match_mode = cf.get('title_match_mode', 'prefix')
        match_titles = [cf['radiko_title']] + cf.get('radiko_aliases', [])
        if pg.station == station and self._title_matched(pg.radiko_title, match_titles, match_mode) and same_weekday:
            pg.artist = self._replace_tag(pg, start_time, cf['artist'])
            pg.album = self._replace_tag(pg, start_time, cf['album'])
            pg.title = self._replace_tag(pg, start_time, cf['title'])
            pg.filename = self._replace_tag(pg, start_time, cf['filename']) + '.m4a'
            pg.storage_dir = self._replace_tag(pg, start_time, cf['storage_dir'])
            pg.series_key = self._series_key(cf.get('series_key', cf['radiko_title']))
            pg.found_by = 'title'
            return pg
        return None

    def _filter_programs(self, programs: list, radio: list) -> dict:
        found_programs = {}
        for pg in programs:
            for cf in radio:
                if 'words' in cf:
                    rec_pg = self._recording_by_words(pg, cf)
                else:
                    rec_pg = self._recording_by_title(pg, cf)

                if rec_pg:
                    # 重複排除
                    key = '_'.join([rec_pg.station, rec_pg.radiko_title, rec_pg.start_time])
                    if key in found_programs:
                        if found_programs[key].found_by == 'words':
                            found_programs[key] = rec_pg
                    else:
                        found_programs[key] = rec_pg

        grouped = {}
        for title_key in sorted(found_programs.keys()):
            pg = found_programs[title_key]
            logger.info(f'{pg.found_by} {title_key}')
            day_key = (pg.series_key or pg.title_key) + pg.start_time[:8]
            grouped.setdefault(day_key, []).append(pg)

        ret = {}
        for day_key, pgs in grouped.items():
            chunks = self._split_programs_by_gap(pgs)
            selected = max(chunks, key=lambda chunk: self._dulation(chunk))
            if len(selected) == 1:
                ret[day_key] = selected[0]
            else:
                ret[day_key] = selected
        return ret

    def _dulation(self, program: Union[Program, list[Program]]) -> int:
        if type(program) is list:
            return sum([pg.dulation for pg in program])
        else:
            return program.dulation

    def _split_programs_by_gap(self, programs: list[Program]) -> list[list[Program]]:
        if not programs:
            return []

        sorted_programs = sorted(programs, key=lambda pg: pg.start_time)
        chunks = [[sorted_programs[0]]]
        for pg in sorted_programs[1:]:
            prev = chunks[-1][-1]
            prev_end = datetime.strptime(prev.end_time, '%Y%m%d%H%M%S')
            current_start = datetime.strptime(pg.start_time, '%Y%m%d%H%M%S')
            gap = (current_start - prev_end).total_seconds()
            if 0 <= gap <= self.MULTI_PART_MAX_GAP_SECONDS:
                chunks[-1].append(pg)
            else:
                chunks.append([pg])
        return chunks

    def get_programs(self, radio: list) -> dict:
        self.series_key_strip_regex = self._series_key_strip_regex_config(radio)
        replace_config = self._replace_config(radio)
        stations = self._station_list(radio)
        programs = {}
        for station in stations:
            xml = self._get_programs_xml(station)
            progs = self._parse_programs_xml(xml, replace_config)
            progs = self._filter_programs(progs, radio)
            # 同じ番組がある場合、長い方を採用
            for title, program in progs.items():
                if title in programs:
                    program1 = programs[title]
                    if type(program) is list:
                        p1 = program[0]
                    else:
                        p1 = program
                    found_by = p1.found_by

                    if found_by == 'title':
                        programs[title] = program
                    else:
                        dulation1 = self._dulation(program1)
                        dulation2 = self._dulation(program)
                        if dulation2 > dulation1:
                            programs[title] = program
                else:
                    programs[title] = program
        logger.info(f'found {len(programs)} programs')
        for program in programs.values():
            if type(program) is list:
                program = program[0]
            logger.info(f'{program.found_by} {program.station} {program.radiko_title} {program.start_time} {program.end_time}')
        return programs

    def _get_artwork(self, program: Program) -> bytes:
        response = requests.get(program.img)
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(f'Failed to download JPEG file. Status code: {response.status_code}')

    def _rec_radiko_ts_sh(self, program: Program) -> Path:
        url = f'https://radiko.jp/#!/ts/{program.station}/{program.start_time}'
        filepath = self.tmp_dir / program.filename
        param = [self.rec_radiko_ts_sh,
                 '-u', url,
                 '-o', filepath]
        if self.radiko_email and self.radiko_pw:
            param.extend(['-m', self.radiko_email, '-p', self.radiko_pw])

        logger.debug(param)
        try:
            result = subprocess.run(
                param,
                capture_output=True,
                text=True,
                timeout=45 * 60,
            )
        except subprocess.TimeoutExpired:
            return None

        if result.returncode == 0:
            return filepath
        else:
            return None

    def _set_attr(self, program: Program, filepath: Path, artwork: bytes) -> None:

        mp4 = MP4(filepath)
        tags = mp4.tags
        prm = {
            '\xa9alb': program.album,
            '\xa9nam': program.title,
            '\xa9ART': program.artist,
            'covr': [MP4Cover(artwork)]}

        changed = False
        for name, value in prm.items():
            if tags.get(name, '') != value:
                tags[name] = value
                changed = True

        if changed:
            tags.save(filepath)

    def _mv_file(self, program: Program, src: Path) -> Path:
        dst = self.storage_dir / program.storage_dir / program.filename
        if not os.path.exists(dst.parent):
            os.makedirs(dst.parent)

        param = ['cp', src, dst]
        subprocess.run(param, check=True)
        os.remove(src)
        return dst

    def _concatenate_m4a(self, files: list, output_path: Path) -> None:
        ac = AudioConcatenator(output_path)
        for file in files:
            ac.add_file(file)
        ac.concatenate()

    def _record_one(self, program: Program) -> Path:
        logger.info(f'recording {program.radiko_title} ...')

        filepath = self._rec_radiko_ts_sh(program)
        if not filepath:
            logger.error(f'failed to record {program.radiko_title}')
            return None

        logger.info(f'recorded {program.radiko_title} at {filepath}')
        return filepath

    def record(self, program) -> Program:

        if type(program) is list:
            artwork = self._get_artwork(program[0])
            concat_filepath = None
            filepaths = []
            for index, pg in enumerate(program):
                filepath = self._record_one(pg)
                if not concat_filepath:
                    concat_filepath = filepath
                new_filepath = filepath.with_suffix('.' + str(index) + '.m4a')
                if new_filepath.exists():
                    new_filepath.unlink()
                filepath.rename(new_filepath)
                filepaths.append(new_filepath)
            logger.info(f'concatenating {len(filepaths)} files ...')
            self._concatenate_m4a(filepaths, concat_filepath)
            logger.info(f'concatenated {len(filepaths)} files to {concat_filepath}')
            for filepath in filepaths:
                filepath.unlink()
            filepath = concat_filepath
            program = program[0]
        else:
            artwork = self._get_artwork(program)
            filepath = self._record_one(program)

        self._set_attr(program, filepath, artwork)
        filepath = self._mv_file(program, filepath)
        logger.info(f'file move to {filepath}')
        program.filepath = filepath
        return program
