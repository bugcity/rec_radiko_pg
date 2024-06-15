# ラジオ番組の録音支援

このリポジトリは、rec_radiko_tsを補助するためのスクリプトです。
番組名を元にradikoから録音開始、終了時間を取得して録音します。また、録音ファイルのタグやアートワークの設定や保存先の指定ができるため録音ファイルを使用する際に検索しやすくなります。

## 必要なもの

[rec_radiko_ts](https://github.com/uru2/rec_radiko_ts)


## 使用方法

1. まず、以下のコマンドを実行して必要なパッケージをインストールする。

    ```bash
    poetry install
    ```

1. `config.yaml` ファイルを編集して、録音ファイルの保存先などを指定する。

1. 録音したいラジオ番組の情報を設定する。`radio.yaml` ファイルを編集して、番組のタイトルや放送局の情報を指定する。

1. 以下のコマンドを実行して、ラジオ番組を録音する。

    ```bash
    poetry run python rec_radiko_pg.py
    ```

## 設定

### config.yaml

config.yamlはrec_radiko_pgの設定。
このファイルに記載した内容は同名の環境変数が存在するとき、環境変数が優先される。

#### raikoの認証情報

raikoを契約している場合は、radiko_emailとradiko_pwがrec_radiko_tsに引き渡される。不要な場合は空欄にする。

- radiko_email: <<radikoのメールアドレス>>
- radiko_pw: <<radikoのパスワード>>

#### メール発信

録音が成功するとメールを発信する。gmailで動作確認済み。不要な場合は空欄にする。

- gmail_sender: <<gmailのメールアドレス>>
- gmail_pw: <<gmailのパスワード>>
- gmail_receiver: <<受信者のメールアドレス>>

#### 録音ファイルを保存先

録音ファイルを保存するディレクトリを指定する。

- storage_dir: ./storage

#### rec_radiko_ts.shの設定

rec_radiko_ts.shのパスを指定します。ディレクトリを含まない場合、rec_radiko_pgと同じディレクトリにあるとみなす。

- rec_radiko_ts_sh: ../rec_radiko_ts/rec_radiko_ts.sh

### radiko.yaml

radio.yamlは、録音するラジオ番組の設定。


#### 録音する番組を見つける設定

##### 番組決め打ち

- station  
  radikoのURLに含まれるステーションのコード

- radiko_title  
  radikoの番組名

- radiko_dayw  
  番組の内、録音する曜日。曜日を無視する場合、この設定自体不要

##### ワード検索

- words  
  検索ワードをリストで書きます。番組のタイトルと出演者からワードを検索し、該当すれば録音します。

- stations  
  検索するステーションのコードをリストで書きます。

#### 録音したファイルのタグの設定

各設定には、datetime.strftimeの書式が指定でき、録音開始時間を埋め込める。
また、{artist}のようにして他の値を埋め込めるが、評価順はartist, album, titleの順で固定。
{pfm}でradikoから得られる出演者の値を参照できるが、得られないことがあり、その際は''になる。アートワークはradikoから録音都度取得して設定される。

- artist  
  アーティスト名  

- album  
  アルバム名

- title  
  曲名


#### 録音したファイルの保存先の設定

各設定には、datetime.strftimeの書式が指定でき、録音開始時間を埋め込める。
また、{artist} {album} {title} で他の値を埋め込める。

- filename  
  ファイル名

- storage_dir  
  ディレクトリ。config.yamlのstorege_dir / radio.yamlのstorage_dir が最終のディレクトリになる。


## その他

last_record_at.yamlに番組ごとの最終録音時間を記録しており、それ以降の番組が録音対象になる。

## ライセンス

このプロジェクトは MIT ライセンスのもとで公開されています。詳細は [LICENSE](./LICENSE) ファイルを参照してください。
