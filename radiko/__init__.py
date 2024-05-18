import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass
import subprocess
from logging import getLogger
from pathlib import Path
from mutagen.mp4 import MP4, MP4Cover
import os
import shutil
from pydub import AudioSegment


logger = getLogger(__name__)


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
    filepath: Path = None


class Radiko:
    def __init__(self, rec_radiko_ts_sh: Path, radiko_email: str, radiko_pw: str, tmp_dir: Path, storage_dir: Path):
        self.rec_radiko_ts_sh = rec_radiko_ts_sh
        self.radiko_email = radiko_email
        self.radiko_pw = radiko_pw
        self.tmp_dir = tmp_dir
        self.storage_dir = storage_dir

    def _station_list(self, radio: list) -> list:
        return list(set([pg['station'] for pg in radio]))

    def _get_programs_xml(self, station: str) -> str:
        url = f'http://radiko.jp/v3/program/station/weekly/{station}.xml'
        response = requests.get(url)
        return response.text

    def _parse_programs_xml(self, xml: str) -> list:
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
            progs.append(
                Program(
                    station=station,
                    radiko_title=title,
                    start_time=ft,
                    end_time=to,
                    img=img,
                    pfm=pfm,
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

    def _filter_programs(self, programs: list, radio: list) -> dict:
        weekdays = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']
        ret = {}
        for pg in programs:
            for cf in radio:
                start_time = datetime.strptime(pg.start_time, '%Y%m%d%H%M%S')
                if 'radiko_dayw' in cf:
                    weekday_num = start_time.weekday()
                    weekday = weekdays[weekday_num]
                    same_weekday = (weekday == cf['radiko_dayw'])
                else:
                    same_weekday = True

                station = cf['station']
                title = cf['radiko_title']
                if pg.station == station and pg.radiko_title.startswith(title) and same_weekday:
                    pg.artist = self._replace_tag(pg, start_time, cf['artist'])
                    pg.album = self._replace_tag(pg, start_time, cf['album'])
                    pg.title = self._replace_tag(pg, start_time, cf['title'])
                    pg.filename = self._replace_tag(pg, start_time, cf['filename']) + '.m4a'
                    pg.storage_dir = self._replace_tag(pg, start_time, cf['storage_dir'])
                    title += ('_' + pg.start_time[:8])
                    if title in ret:
                        if type(ret[title]) is list:
                            ret[title].append(pg)
                        else:
                            ret[title] = [ret[title], pg]
                    else:
                        ret[title] = pg
        return ret

    def get_programs(self, radio: list) -> dict:
        stations = self._station_list(radio)
        programs = {}
        for station in stations:
            xml = self._get_programs_xml(station)
            progs = self._parse_programs_xml(xml)
            progs = self._filter_programs(progs, radio)
            programs.update(progs)
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
        result = subprocess.run(
            param,
            capture_output=True,
            text=True,
        )

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
        shutil.move(src, dst)
        return dst

    def _concatenate_m4a(self, files: list, output_path: Path) -> None:
        combined = AudioSegment.from_file(files[0], format='m4a')

        for file in files[1:]:
            next_segment = AudioSegment.from_file(file, format='m4a')
            combined += next_segment

        combined.export(output_path, format='mp4', bitrate='46k')

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
