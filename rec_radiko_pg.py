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
from radiko import Radiko


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

    for program in radiko.get_programs(load_radio()):
        if program.start_time <= lastest.get(program):
            continue
        if program.start_time > now or program.end_time > record_start:
            continue
        logger.debug(f'program: {program}')
        filepath = radiko.record(program)
        if filepath:
            lastest.set(program)
            msg = f'録音完了:{program.radiko_title}'
            body = ''
            email.send(msg, body)
    lastest.save()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.exception(e)
