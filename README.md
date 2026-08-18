# Slot Scraper（PC版）

Androidアプリ「Slot Scraper」のうち、データ取得（スクレイピング）と結果の確認をPC上で行うための移植版です。

**現在のバージョンでできること**

- みんレポ（MinRepo）/ あなスロ（AnaSlo）/ スロナビ（SloNavi）のいずれかの「まとめサイト」からのデータ取得（あなスロ・スロナビは未検証です）
- 取得したデータをCSVで保存
- 生データを一覧できるだけの、シンプルなHTMLレポートの生成
- GitHub Pagesへの自動公開（外出先からiPhoneでも閲覧可能）
- Windowsタスクスケジューラでの毎日自動実行

**まだできないこと（今後追加予定）**

- PS(pscube)・S7の取得（店舗情報が未登録のため）
- ジャグラー分析・穴分析・月次差分析などの集計機能（元アプリのCsvCalculationActivity.kt相当）

**動作環境について**

サイト側が自動操作されたブラウザを検知してブロックすることがあるため、Google Chromeがインストールされている場合はそちらを優先的に使う作りにしています。まだChromeを入れていない場合は https://www.google.com/chrome/ からインストールしておくことをおすすめします（無くてもPlaywright付属のブラウザで動作しますが、ブロックされやすくなります）。

---

## 初回セットアップ

### 1. Python をインストール（未インストールの場合）

https://www.python.org/downloads/ から最新版をダウンロードしてインストールしてください。インストーラーの最初の画面で **「Add python.exe to PATH」に必ずチェック** を入れてください。

### 2. セットアップスクリプトを実行

このフォルダの `setup_windows.bat` をダブルクリックしてください。必要なパッケージ（Playwright）と、操作用のブラウザが自動でインストールされます。数分かかります。

### 3. GitHubリポジトリを作成

GitHub（https://github.com）にログインし、右上の「+」→「New repository」から新しいリポジトリを作成してください。

- Repository name: 好きな名前（例: `slot-scraper-report`）
- Public / Private: **Private推奨**（公開ページ自体はURLを知っていれば誰でも見られますが、Privateにするとリポジトリの中身・設定ファイルは他人から見えなくなります）
- 「Add a README file」などのオプションは **すべてチェックを外したまま** 作成してください

作成すると `https://github.com/あなたのユーザー名/リポジトリ名.git` のようなURLが表示されます（Code ボタン→HTTPS）。

### 4. publish.bat を編集

`publish.bat` をメモ帳などで開き、`set REPO_URL=` の行を、3で作成したリポジトリのURLに書き換えて保存してください。

### 5. 初回実行

`publish.bat` をダブルクリックしてください。データ取得後、GitHubへの初回送信が行われます。初回はブラウザが開いてGitHubへのサインインを求められることがあるので、指示に従ってサインインしてください（一度サインインすれば、次回からは自動で送信されます）。

うまくいかない場合は、表示されたエラーメッセージをそのままClaudeに伝えてください。一緒に解決します。

### 6. GitHub Pagesを有効化

GitHubのリポジトリページで Settings → Pages を開き、Source を **Branch: `main` / Folder: `/docs`** に設定して Save してください。数分後、`https://あなたのユーザー名.github.io/リポジトリ名/` でレポートが見られるようになります。このURLをiPhoneのホーム画面に追加しておくと便利です。

### 7. 毎日自動実行を登録

`schedule_task.ps1` を右クリック→「PowerShellで実行」してください。エラーが出て実行できない場合は、PowerShellを開いて次のコマンドを実行してください。

```
powershell -ExecutionPolicy Bypass -File "このフォルダのパス\schedule_task.ps1"
```

デフォルトでは毎日9:00に自動実行されます。時間を変えたい場合は `schedule_task.ps1` 内の `$runTime` を書き換えて再実行してください。

---

## 店舗を追加・変更する

`config/stores.json` をテキストエディタで開いて編集してください。

```json
{
  "stores": [
    {
      "name": "表示用の店舗名（何でもOK）",
      "slug": "ファイル保存用の半角英数字の名前（他と重複しないように）",
      "source_type": "MR",
      "url": "店舗の「過去レポート一覧」ページのURL",
      "start_days_ago": 30,
      "end_days_ago": 1,
      "fetch_bonus_data": false
    }
  ]
}
```

- `source_type`: `MR`(みんレポ) / `AS`(あなスロ) / `SN`(スロナビ)
- `start_days_ago` / `end_days_ago`: 何日前から何日前まで取得するか
- 一度取得した日付のCSVは自動的にスキップされるので、`start_days_ago` を大きくしても毎回全部取り直すことはありません

保存したら、次の `publish.bat` 実行時（または明日の自動実行時）から反映されます。

---

## うまく動かないとき

`python src\run_all.py` を手動実行すると、コンソールに詳しいログが表示されます。エラーメッセージをコピーしてClaudeに貼り付けてください。サイトの構造が変わった場合など、スクレイピング側の修正が必要になることがあります。
