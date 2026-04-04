import yaml
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import logging
import logging.config
from gmail import Email
from config_loader import ConfigLoader
from latest import Latest
from radiko import Radiko, Program, normalize_text
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


script_dir = Path(__file__).resolve().parent


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


def can_record(now: str, record_start: str, program: Program, latest: Latest) -> bool:
    """
    録音可能かどうかを判定する

    Args:
        now (str): 現在時刻
        record_start (str): 録音開始時刻
        program (Program): 番組情報
        latest (Latest): 最新の録音情報

    Returns:
        bool: 録音可能かどうか
    """

    if isinstance(program, list):
        pgs = program[0]
        pge = program[-1]
    else:
        pgs = program
        pge = program
    if pgs.start_time <= latest.get(pgs):
        return False
    if pgs.start_time > now or pge.end_time > record_start:
        return False
    return True


def _program_start_end(program: Program) -> tuple[Program, Program]:
    if isinstance(program, list):
        return program[0], program[-1]
    return program, program


def _format_program_window(start: str, end: str) -> tuple[str, str]:
    s = datetime.strptime(start, '%Y%m%d%H%M%S')
    e = datetime.strptime(end, '%Y%m%d%H%M%S')
    return s.strftime('%Y-%m-%d %H:%M'), e.strftime('%H:%M')


def _show_filename_hint(pg: Program) -> bool:
    if not pg.filename:
        return False
    title_norm = normalize_text(pg.radiko_title)
    filename_norm = normalize_text(Path(pg.filename).stem)
    return title_norm not in filename_norm


def show_upcoming(programs: dict, latest: Latest, now: datetime, days: int) -> None:
    limit = now + timedelta(days=days)
    items = []
    now_str = now.strftime('%Y%m%d%H%M%S')
    limit_str = limit.strftime('%Y%m%d%H%M%S')

    for program in programs.values():
        pgs, pge = _program_start_end(program)
        if pgs.start_time <= now_str:
            continue
        if pgs.start_time > limit_str:
            continue
        if pgs.start_time <= latest.get(pgs):
            continue
        items.append((pgs.start_time, pge.end_time, pgs, program))

    items.sort(key=lambda x: x[0])
    print(f'録音予定件数: {len(items)} (対象期間: {days}日)')
    for start, end, pg, program in items:
        s, e = _format_program_window(start, end)
        print(f'{s}-{e} [{pg.station}] {pg.radiko_title}')
        if _show_filename_hint(pg):
            print(f'  -> 実際のファイル名: {pg.filename}')
        if isinstance(program, list):
            print('  連結対象:')
            for part in program:
                ps, pe = _format_program_window(part.start_time, part.end_time)
                print(f'    - {ps}-{pe} [{part.station}] {part.radiko_title}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--list-upcoming', action='store_true', help='録音予定の番組一覧を表示して終了する')
    parser.add_argument('--list-days', type=int, default=7, help='録音予定の表示対象日数 (既定: 7)')
    parser.add_argument('--since-hours', type=int, default=None, help='N時間以内に開始した番組のみ録音対象にする')
    args = parser.parse_args()

    n = datetime.now()
    now = n.strftime('%Y%m%d%H%M%S')
    record_start = (n - timedelta(minutes=5)).strftime('%Y%m%d%H%M%S')
    since = (n - timedelta(hours=args.since_hours)).strftime('%Y%m%d%H%M%S') if args.since_hours else None
    logger.info(f'now: {now}')

    email = Email(config.gmail_sender, config.gmail_pw, config.gmail_receiver)
    errors: list[str] = []

    try:
        last_record_at_filename = script_dir / 'last_record_at.yaml'
        latest = Latest(last_record_at_filename)
        if len(config.rec_radiko_ts_sh.parts) > 1:
            rec_radiko_ts_sh = config.rec_radiko_ts_sh
        else:
            rec_radiko_ts_sh = script_dir / config.rec_radiko_ts_sh
        radiko = Radiko(rec_radiko_ts_sh, config.radiko_email, config.radiko_pw, script_dir, config.storage_dir)
        programs = radiko.get_programs(load_radio())

        if args.list_upcoming:
            show_upcoming(programs, latest, n, args.list_days)
            return

        for title, program in programs.items():
            if not can_record(now, record_start, program, latest):
                continue
            if since:
                pgs = program[0] if isinstance(program, list) else program
                if pgs.start_time < since:
                    continue

            logger.debug(f'program: {title}')
            try:
                program = radiko.record(program)
            except Exception as e:
                logger.error(f'failed to record {title}: {e}')
                errors.append(str(e))
                continue
            if program.filepath:
                latest.set(program)
                latest.save()
                msg = f'録音完了:{program.title_key}'
                dt = program.start_time[:4] + '-' + program.start_time[4:6] + '-' + program.start_time[6:8]
                body = f'日付: {dt}'
                if program.artist:
                    body += f'<br>出演者: {program.artist}'
                email.send(msg, body)
    except Exception as e:
        logger.exception(e)
        errors.append(str(e))
    finally:
        if errors:
            body = '<br>'.join(errors)
            email.send('録音エラー', body)
        logger.info('done')


if __name__ == '__main__':
    main()
