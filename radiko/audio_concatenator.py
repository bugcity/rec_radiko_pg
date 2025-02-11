import subprocess
import os
from pathlib import Path
import tempfile


class AudioConcatenator:
    def __init__(self, output_file: Path = 'output.m4a'):
        self.output_file = output_file
        self.file_list = []

    def add_file(self, file_path: Path) -> None:
        """結合するファイルを追加"""
        if file_path.exists():
            self.file_list.append(file_path)
        else:
            raise FileNotFoundError(f'ファイルが見つかりません: {file_path}')

    def concatenate(self) -> None:
        """ファイルを結合"""
        if len(self.file_list) < 2:
            raise ValueError('結合するには2つ以上のファイルが必要です。')

        # 一時ファイルを作成（自動削除される） Windowsではdelete=Falseが必要、Linuxでは不要、Windowsのせいでだるい実装になってしまった
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_file:
            for file in self.file_list:
                temp_file.write(f"file '{file}'\n")
            temp_file_path = temp_file.name

        try:
            # ffmpeg で結合
            subprocess.run(
                ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', temp_file_path, '-c', 'copy', self.output_file],
                check=True
            )

        except subprocess.CalledProcessError as e:
            raise ValueError(f'ffmpeg でエラーが発生しました: {e}')

        finally:
            # 一時ファイルを削除
            os.remove(temp_file_path)
