import os
import yaml
from pathlib import Path
from dataclasses import fields
from logging import getLogger


logger = getLogger(__name__)


class ConfigLoader:
    @staticmethod
    def load(config_yml: Path, Config) -> dict:
        with open(config_yml, encoding='utf-8') as file:
            config = Config(**yaml.safe_load(file))
            for member in fields(Config):
                if member.name in os.environ:
                    setattr(config, member.name, os.environ[member.name])
                if member.name.upper() in os.environ:
                    setattr(config, member.name, os.environ[member.name.upper()])
                if member.type == Path:
                    setattr(config, member.name, Path(getattr(config, member.name)))

        return config
