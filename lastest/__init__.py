import yaml
from pathlib import Path
from radiko import Program
import jaconv


class Lastest:
    def __init__(self, last_record_at_filename: Path):
        self.last_record_at_filename = last_record_at_filename
        self.last_record_at = {}
        self.load()

    def load(self) -> None:
        data = {}
        try:
            with open(self.last_record_at_filename, 'r', encoding='utf-8') as file:
                preload = yaml.safe_load(file)
                if preload:
                    data = {jaconv.z2h(key, kana=False, ascii=True, digit=True): value for key, value in preload.items()}
        except FileNotFoundError:
            pass
        self.last_record_at = data

    def save(self) -> None:
        with open(self.last_record_at_filename, 'w', encoding='utf-8') as file:
            yaml.dump(self.last_record_at, file, allow_unicode=True)

    def set(self, program: Program) -> None:
        self.last_record_at[program.title_key] = program.start_time

    def get(self, program: Program) -> str:
        return self.last_record_at.get(program.title_key, '')
