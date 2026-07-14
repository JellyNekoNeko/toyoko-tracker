# 東横INN 空室トラッカー — WebUI & デスクトップ版

*[Toyoko Inn](https://www.toyoko-inn.com/) の空室情報を自動で確認する、かわいいクロスプラットフォーム対応ツールです。Python WebUI と macOS・Windows・Linux 用デスクトップ版を提供します。*

- 🌏 [📖 English Guide](https://github.com/JellyNekoNeko/toyoko-tracker/blob/main/README.md)
- 🌏 [📖 中文说明书](https://github.com/JellyNekoNeko/toyoko-tracker/blob/main/README_zh.md)
- 🌏 [📖 한국어 안내서](https://github.com/JellyNekoNeko/toyoko-tracker/blob/main/README_ko.md)

---

## 主な機能

- 🌐 ローカル WebUI で空室情報をリアルタイム表示
- 🖥 macOS・Windows・Linux 向けデスクトップアプリ
- ⚡ 軽量な HTTP/API 検索エンジン
- 🧭 互換性のための Playwright エンジン（オプション）
- 🏨 地域または半径からホテルを選択
- 🛏 シングル・ダブル・ツインの部屋タイプ絞り込み
- 💳 会員価格と一般価格の表示
- 🔔 デスクトップ通知
- 🤖 Telegram、📱 Bark、💬 Server Chan、📧 SMTP メール通知
- 🚀 複数ホテルを効率的に検索するスマート並列処理

## 必要環境

- Python **3.9 以上**（Python 3.10〜3.14 推奨）
- インターネット接続
- Playwright は互換エンジンを使う場合のみ必要

## PyPI からインストール

### macOS

Homebrew の Python では PEP 668 によりシステム全体への `pip install`
が制限されるため、`pipx` を推奨します。

```bash
brew install pipx
pipx ensurepath
pipx install toyoko-tracker
```

ターミナルを開き直し、次のコマンドで起動します。

```bash
toyoko-tracker
```

### Linux

ディストリビューションのパッケージマネージャーで `pipx` を
インストールしてから実行します。

```bash
pipx ensurepath
pipx install toyoko-tracker
toyoko-tracker
```

### Windows

PowerShell またはコマンドプロンプトで実行します。

```powershell
py -m pip install --upgrade toyoko-tracker
toyoko-tracker
```

### 仮想環境を使う場合

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip toyoko-tracker
toyoko-tracker
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip toyoko-tracker
toyoko-tracker
```

## デスクトップ版

[GitHub Releases](https://github.com/JellyNekoNeko/toyoko-tracker/releases)
からシステムに合うファイルをダウンロードしてください。

| OS | アーキテクチャ | ファイル |
|---|---|---|
| macOS | Apple Silicon | `ToyokoTracker-macos-arm64.zip` |
| macOS | Intel | `ToyokoTracker-macos-x64.zip` |
| Windows | ARM64 | `ToyokoTracker-windows-arm64.zip` |
| Windows | x86-64 | `ToyokoTracker-windows-x64.zip` |
| Linux | ARM64 | `ToyokoTracker-linux-arm64.tar.gz` |
| Linux | x86-64 | `ToyokoTracker-linux-x64.tar.gz` |

macOS では ZIP を展開し、`ToyokoTracker.app` を Applications フォルダに
移動して起動します。初回起動時に保護警告が表示された場合は、
システム設定の「プライバシーとセキュリティ」から開いてください。

## Playwright エンジン（オプション）

仮想環境内で次を実行します。

```bash
python -m pip install --upgrade "toyoko-tracker[playwright]"
python -m playwright install chromium
```

通常の HTTP/API エンジンでは Playwright は不要です。

## 基本的な使い方

1. `toyoko-tracker` を起動する。
2. ブラウザで表示された WebUI を開く。
3. 地域、ホテル、チェックイン日、泊数、人数、部屋タイプを選択する。
4. 「検索」または「スキャン開始」を押す。
5. 必要に応じて Telegram、Bark、Server Chan、SMTP 通知を設定する。

デフォルトでは `127.0.0.1` のみで待ち受けます。スマートフォンや LAN から
アクセスする場合は、WebUI のモバイル/LAN アクセス設定を使ってください。

## 通知

WebUI の設定画面で以下を設定できます。

- **Telegram**: BotFather で Bot Token を作成し、Chat ID と一緒に登録
- **Bark**: iPhone/iPad の Bark キーまたは URL を登録
- **Server Chan**: SendKey を登録
- **SMTP**: SMTP ホスト、ポート、ユーザー名、アプリパスワード、送信先を登録
- **ローカル通知**: OS の通知権限を有効化

## 設定ファイル

| OS | 既定のフォルダ |
|---|---|
| macOS | `~/Library/Application Support/ToyokoTracker/` |
| Windows | `%APPDATA%\ToyokoTracker\` |
| Linux | `~/.config/toyoko-tracker/` |

保存先は環境変数で変更できます。

```bash
TOYOKO_TRACKER_CONFIG_DIR=/path/to/config toyoko-tracker
```

## アップデート

PyPI / pipx 版:

```bash
pipx upgrade toyoko-tracker
```

`pip` 版は対象環境を有効化してから実行します。

```bash
python -m pip install --upgrade toyoko-tracker
```

デスクトップ版は GitHub Releases の `desktop-v*` リリースを確認します。
WebUI 版とデスクトップ版は同じ主要バージョン番号を使いますが、
それぞれ PyPI と GitHub Releases から更新されます。

## トラブルシューティング

### `toyoko-tracker` が見つからない

```bash
pipx ensurepath
pipx reinstall toyoko-tracker
```

ターミナルを開き直してください。仮想環境の場合は、環境を有効化して
`python -m toyoko_tracker` を実行できます。

### macOS で通知が表示されない

```bash
brew install terminal-notifier
```

「システム設定 → 通知」で通知を許可してください。

## ライセンスとリンク

- ライセンス: **MIT**
- 作者: JellyNeko / bilibili @果冻猫猫丶
- [GitHub](https://github.com/JellyNekoNeko/toyoko-tracker)
- [PyPI](https://pypi.org/project/toyoko-tracker/)

