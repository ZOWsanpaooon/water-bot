# PC完全オフライン対応 & 24時間常時稼働ガイド ☁️🤖

PCの電源を落としていても、**DiscordのボタンやApple Watchからの水分記録を24時間いつでも稼働させる方法**です。

---

## 方式1: Supabase（無料クラウドDB）を使う場合（一番手軽）

Apple Watch / iPhoneからの記録を無料のクラウドDB（Supabase）に保存し、PC起動時にBotが自動同期します。

### 1. Supabaseプロジェクトの作成 (無料)
1. [supabase.com](https://supabase.com) で無料アカウントを作成し、新しいプロジェクトを作成します。
2. 左メニューの **「SQL Editor」** を開き、以下のSQLを実行してテーブルを作成します：

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    daily_goal_ml INTEGER NOT NULL DEFAULT 2000,
    gulp_ml INTEGER NOT NULL DEFAULT 25,
    reset_time TEXT NOT NULL DEFAULT '06:00',
    notification_enabled BOOLEAN NOT NULL DEFAULT true,
    notification_start TEXT NOT NULL DEFAULT '08:00',
    notification_end TEXT NOT NULL DEFAULT '23:00',
    notification_interval INTEGER NOT NULL DEFAULT 60,
    presets JSONB NOT NULL DEFAULT '[100, 250, 500]',
    visibility TEXT NOT NULL DEFAULT 'all'
);

CREATE TABLE IF NOT EXISTS water_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    amount_ml INTEGER NOT NULL,
    gulp_count INTEGER,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    date_key TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'apple_watch'
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE water_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anon all users" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow anon all logs" ON water_logs FOR ALL USING (true) WITH CHECK (true);
```

### 2. PCの `.env` に設定を追加
プロジェクトの `Project Settings` → `API` から以下をコピーして、PCの `.env` に追記します：
```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJh......(anon public key)
```

### 3. Apple Watch / iPhone から直接SupabaseにPOST
ショートカットの「URLの内容を取得」で：
* **URL:** `https://xxxxxxxxxxxx.supabase.co/rest/v1/water_logs`
* **方法:** POST
* **ヘッダー:**
  * `apikey`: `<anon key>`
  * `Authorization`: `Bearer <anon key>`
  * `Content-Type`: `application/json`
* **本文 (JSON):**
  ```json
  {
    "user_id": "<あなたのDiscord ID>",
    "amount_ml": 250,
    "gulp_count": 10,
    "date_key": "2026-09-05",
    "source": "apple_watch"
  }
  ```

👉 **これでPCが電源OFFでも、Apple WatchからクラウドDBへ直接書き込まれ、PCをつけた瞬間にBotがDiscordパネルへ自動反映します！**

---

## 方式2: Bot本体をクラウド（無料枠）で常時24時間稼働させる場合

PCを起動していなくても、**Discord上のボタンを24時間いつでも押せるようにする**場合は、Render や Railway 等のクラウドにBotを配置できます。

### Render.com での無料ホスティング手順（5分）
1. 本プロジェクト（ゆうゆうじてき）を GitHub のプライベートリポジトリにプッシュします。
2. [Render.com](https://render.com) で無料アカウントを作成し、**「New +」→「Background Worker」**（または Web Service）を選択。
3. GitHubリポジトリを連携し、以下の環境変数を設定します：
   * `DISCORD_BOT_TOKEN`: あなたのBotトークン
   * `SUPABASE_URL` / `SUPABASE_KEY`: （任意：クラウドDBを使う場合）
4. **Deploy** を押すだけで、**PCの電源が完全に切れていても、Discord上の水分管理ボタンが24時間365日常に反応**するようになります！
