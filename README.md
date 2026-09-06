# 💧 水分管理Bot (FadeHost 24時間稼働対応)

Discord上で動作するパーソナル水分管理Botです。
自宅PCでのローカル稼働はもちろん、クラウド（FadeHost等）上で24時間常時稼働させることができます。

---

## 🌟 主な特徴

- **24時間常時稼働**: PCがOFFでも常に水分記録・DM通知・計算が動作
- **パーソナル水分計算**: 身体情報（性別・年齢・身長・体重・活動量・就寝時間）から科学的な適量を算出
- **西蒲田の気象連動**: 東京都大田区西蒲田の気温・体感温度・湿度を自動取得して目標値を最適化
- **DM通知対応**: 本人にだけ届くDiscordダイレクトメッセージで水分補給をお知らせ（未受信時はチャンネルフォールバック）
- **Apple Watch / iPhone連携**: 内蔵REST API (aiohttp:8080) & ショートカットからワンタップで記録

---

## 📁 ファイル構成

```text
water_bot/
├── main.py              # 起動エントリポイント
├── requirements.txt     # 必要ライブラリ (discord.py, aiohttp, python-dotenv)
├── .env                 # 環境変数設定 (Botトークン等)
├── .gitignore           # Git除外設定
├── 水分Bot起動.bat       # Windows用起動バッチ
├── 水分Bot起動.vbs       # Windows用バックグラウンド起動スクリプト
├── data/
│   └── water.db         # 水分データベース (SQLite)
├── tests/               # 単体・統合テスト
│   ├── __init__.py
│   └── test_water_bot.py
└── src/
    ├── __init__.py
    ├── bot.py           # Bot本体・コマンド同期
    ├── cog.py           # 水分機能Cog & DM通知・定期監視タスク
    ├── calculator.py    # 水分量計算エンジン
    ├── weather.py       # 西蒲田天気API (Open-Meteo連携)
    ├── analytics.py     # 過去統計・時間帯分析
    ├── db.py            # SQLiteデータベース管理
    ├── models.py        # データモデル & JST共通定義
    ├── panel.py         # パネルEmbed・履歴生成
    ├── parser.py        # テキスト解析 (自然言語・数値)
    ├── ui.py            # インタラクティブUI (ボタン・モーダル)
    ├── api.py           # Apple Watch / iPhone用 REST API
    ├── cloud_db.py      # Supabaseバックアップ (任意連携)
    └── sync.py          # データ同期 & 重複排除
```

---

## 🚀 ローカルでのセットアップ & 起動

### 1. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定 (`.env`)
プロジェクト直下の `.env` ファイルにDiscord Botトークンを設定します：

```env
DISCORD_BOT_TOKEN=your_bot_token_here
WATER_API_PORT=8080
```

### 3. 起動
```bash
# コマンドプロンプト / PowerShell
python main.py

# またはWindows用起動スクリプト
水分Bot起動.bat
```

---

## ☁️ FadeHost デプロイ手順

1. **Discord Developer PortalでBot設定**:
   - `MESSAGE CONTENT INTENT` と `SERVER MEMBERS INTENT` を有効化
   - OAuth2でBotをサーバーに招待（権限: メッセージ送信、埋め込みリンク、メッセージ履歴の閲覧等）
2. **FadeHostにファイルをアップロード**:
   - `main.py`, `requirements.txt`, `src/`, `data/` などをアップロード
   - コントロールパネルで `.env` を作成し `DISCORD_BOT_TOKEN` を入力
3. **起動コマンド設定**:
   - Startup Command: `python main.py`
   - コンソールから **Start** を実行

---

## 📱 Discordでの使い方

1. 水分管理を行いたいチャンネルで `/water-channel` スラッシュコマンドを実行します。
2. チャンネルに常設パネルが設置されます。
3. パネル下の **「⚙️ 設定」** ボタンからプロフィール（表示名、性別、年齢、身長、体重、活動量、就寝時間）を入力します。
4. **「+100ml」「+250ml」「+500ml」** ボタンや、チャット入力（「250」や「10ゴク」）で手軽に水分を記録できます。