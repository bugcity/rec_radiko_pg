from math import e
import yaml
from pathlib import Path
from radiko import Program


class Lastest:
    def __init__(self, last_record_at_filename: Path):
        self.last_record_at_filename = last_record_at_filename
        self.last_record_at = {}
        self.load()

    def load(self) -> None:
        global last_record_at
        try:
            with open(self.last_record_at_filename, 'r', encoding='utf-8') as file:
                self.last_record_at = yaml.safe_load(file)
        except FileNotFoundError:
            pass
        if not self.last_record_at:
            self.last_record_at = {}

    def save(self) -> None:
        with open(self.last_record_at_filename, 'w', encoding='utf-8') as file:
            yaml.dump(self.last_record_at, file, allow_unicode=True)

    def set(self, program: Program) -> None:
        self.last_record_at[program.radiko_title] = program.start_time

    def get(self, program: Program) -> str:
        return self.last_record_at.get(program.radiko_title, '')
