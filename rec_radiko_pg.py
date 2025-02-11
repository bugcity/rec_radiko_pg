import yaml
from dataclasses import dataclass
import os
from pathlib import Path
from datetime import datetime, timedelta
import logging
import logging.config
from gmail import Email
from config_loader import ConfigLoader
from lastest import Lastest
from radiko import Radiko, Program
import warnings


warnings.filterwarnings("ignore", category=SyntaxWarning, module='pydub.utils')


@dataclass
class Config:
    radiko_email: str
    radiko_pw: str
    gmail_sender: str
    gmail_pw: str
    gmail_receiver: str
    storage_dir: Path
    rec_radiko_ts_sh: Path


script_path = os.path.abspath(__file__)
script_dir = Path(os.path.dirname(script_path))


def setup_logging():
    logger_yml = script_dir / 'logger.yaml'
    with open(logger_yml, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)


setup_logging()
logger = logging.getLogger('rec_radiko_pg')
config = ConfigLoader.load(script_dir / 'config.yaml', Config)


def load_radio() -> list:
    radio_yml = script_dir / 'radio.yaml'
    with open(radio_yml, encoding='utf-8') as file:
        return yaml.safe_load(file)


def can_record(now: str, record_start: str, program: Program, lastest: Lastest) -> bool:
    """
    録音可能かどうかを判定する

    Args:
        now (str): 現在時刻
        record_start (str): 録音開始時刻
        program (Program): 番組情報
        lastest (Latest): 最新の録音情報

    Returns:
        bool: 録音可能かどうか
    """

    if type(program) is list:
        pgs = program[0]
        pge = program[-1]
    else:
        pgs = program
        pge = program
    if pgs.start_time <= lastest.get(pgs):
        return False
    if pgs.start_time > now or pge.end_time > record_start:
        return False
    return True


def main():
    n = datetime.now()
    now = n.strftime('%Y%m%d%H%M%S')
    record_start = (n - timedelta(minutes=5)).strftime('%Y%m%d%H%M%S')
    logger.info(f'now: {now}')

    last_record_at_filename = script_dir / 'last_record_at.yaml'
    lastest = Lastest(last_record_at_filename)
    email = Email(config.gmail_sender, config.gmail_pw, config.gmail_receiver)

    if len(config.rec_radiko_ts_sh.parts) > 1:
        rec_radiko_ts_sh = config.rec_radiko_ts_sh
    else:
        rec_radiko_ts_sh = script_dir / config.rec_radiko_ts_sh
    radiko = Radiko(rec_radiko_ts_sh, config.radiko_email, config.radiko_pw, script_dir, config.storage_dir)

    for title, program in radiko.get_programs(load_radio()).items():
        if not can_record(now, record_start, program, lastest):
            continue

        logger.debug(f'program: {title}')
        program = radiko.record(program)
        if program.filepath:
            lastest.set(program)
            lastest.save()
            msg = f'録音完了:{program.title_key}'
            dt = program.start_time[:4] + '-' + program.start_time[4:6] + '-' + program.start_time[6:8]
            body = f'日付: {dt}'
            if program.artist:
                body += f'<br>出演者: {program.artist}'
            email.send(msg, body)
    logger.info('done')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.exception(e)
