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

    def _filter_programs(self, programs: list, radio: list) -> list:
        weekdays = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']
        ret = []
        for pg in programs:
            for cf in radio:
                start_time = datetime.strptime(pg.start_time, '%Y%m%d%H%M%S')
                if 'radiko_dayw' in cf:
                    weekday_num = start_time.weekday()
                    weekday = weekdays[weekday_num]
                    same_weekday = (weekday == cf['radiko_dayw'])
                else:
                    same_weekday = True

                if pg.station == cf['station'] and pg.radiko_title == cf['radiko_title'] and same_weekday:
                    pg.artist = self._replace_tag(pg, start_time, cf['artist'])
                    pg.album = self._replace_tag(pg, start_time, cf['album'])
                    pg.title = self._replace_tag(pg, start_time, cf['title'])
                    pg.filename = self._replace_tag(pg, start_time, cf['filename']) + '.m4a'
                    pg.storage_dir = self._replace_tag(pg, start_time, cf['storage_dir'])
                    ret.append(pg)
        return ret

    def get_programs(self, radio: list) -> list:
        stations = self._station_list(radio)
        programs = []
        for station in stations:
            xml = self._get_programs_xml(station)
            progs = self._parse_programs_xml(xml)
            progs = self._filter_programs(progs, radio)
            programs.extend(progs)
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

    def record(self, program: Program) -> Path:
        logger.info(f'recording {program.radiko_title} ...')

        artwork = self._get_artwork(program)
        filepath = self._rec_radiko_ts_sh(program)
        if not filepath:
            logger.error(f'failed to record {program.radiko_title}')
            return None

        self._set_attr(program, filepath, artwork)
        filepath = self._mv_file(program, filepath)

        logger.info(f'recorded {program.radiko_title} at {filepath}')
        return filepath
