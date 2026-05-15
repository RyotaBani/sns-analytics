"""
SNS投稿文自動生成スクリプト（Gemini 1.5 Flash・無料）
"""

import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv
from google import genai

load_dotenv('/Users/bani/analytics/.env')

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID = "e8f356b4-3d5a-4713-8a4e-b016e49c1d47"
NOTION_API = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

ACCOUNT_STYLES = {
    "nakyatsukuruapp": {
        "concept": "個人開発者・アプリ開発者として「なきゃ自分で作る」精神を発信",
        "themes": ["個人開発", "アプリ開発", "開発ストーリー", "不便を解決", "現場の声", "リリース体験"],
        "styles": ["ポエム型", "開発ストーリー型", "問いかけ型", "共感型"],
        "hashtags": "#個人開発 #アプリ開発 #なきゃ自分で作る",
        "ng": ["スポーツに限定しない", "難しい言葉はNG", "短く読みやすく"],
    },
    "Sirius": {
        "concept": "副業初心者として正直な体験談・感情を発信",
        "themes": ["副業", "副業初心者", "会社員×副業", "収入", "成長", "時間管理", "メンタル"],
        "styles": ["共感型", "エピソード型", "気づき型", "問いかけ型"],
        "hashtags": "#副業 #副業初心者 #副業日記",
        "ng": ["パートナー・家族ネタは避ける", "過度なポジティブはNG", "正直さを大切に"],
    },
}


def get_past_posts(account_name, limit=20):
    res = requests.post(
        f"{NOTION_API}/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={
            "filter": {"and": [
                {"property": "アカウント", "select": {"equals": account_name}},
                {"property": "ステータス", "select": {"equals": "投稿済み"}},
            ]},
            "sorts": [{"property": "いいね数", "direction": "descending"}],
            "page_size": limit,
        }
    )
    posts = []
    for p in res.json().get("results", []):
        props = p["properties"]
        text = "".join(t.get("plain_text", "") for t in props.get("投稿文", {}).get("title", []))
        likes = props.get("いいね数", {}).get("number", 0) or 0
        views = props.get("表示数", {}).get("number", 0) or 0
        cat = (props.get("カテゴリ", {}).get("select", {}) or {}).get("name", "")
        if text:
            posts.append({"text": text, "likes": likes, "views": views, "category": cat})
    return posts


def get_used_themes(account_name):
    thirty_days_ago = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    res = requests.post(
        f"{NOTION_API}/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={
            "filter": {"and": [
                {"property": "アカウント", "select": {"equals": account_name}},
                {"property": "投稿日", "date": {"on_or_after": thirty_days_ago}},
            ]},
            "page_size": 50,
        }
    )
    texts = []
    for p in res.json().get("results", []):
        text = "".join(t.get("plain_text", "") for t in p["properties"].get("投稿文", {}).get("title", []))
        if text:
            texts.append(text[:80])
    return texts


def generate_post(account_key, past_posts, used_themes):
    style = ACCOUNT_STYLES[account_key]

    top_posts_text = "\n\n".join([
        f"【{p['category']}｜いいね:{p['likes']}・表示:{p['views']}】\n{p['text']}"
        for p in past_posts[:5]
    ]) if past_posts else "（まだデータなし）"

    used_summary = "\n".join(used_themes[:15]) if used_themes else "（なし）"

    prompt = f"""あなたはSNS運用の専門家です。{account_key}アカウント用の投稿文を1本作成してください。

## アカウント情報
- コンセプト: {style['concept']}
- テーマ候補: {', '.join(style['themes'])}
- 文体スタイル: {', '.join(style['styles'])}
- ハッシュタグ: {style['hashtags']}
- NG事項: {', '.join(style['ng'])}

## 過去の伸びた投稿（参考・このパターンを真似る）
{top_posts_text}

## 最近30日間に使ったテーマ（絶対に重複しないこと）
{used_summary}

## 投稿文の条件
- 5〜12行程度
- 冒頭1行でスクロールを止める（インパクトのある一文）
- 空行を使って読みやすくする
- 最後にハッシュタグをつける
- 最近使ったテーマと絶対に被らないこと
- 日本語で書く
- 過去の伸びた投稿のパターン・文体を参考にする

投稿文のみ出力。説明・前置き・コメントは一切不要。"""

    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=prompt,
    )
    return response.text.strip()


def save_to_notion(account_key, post_text):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    res = requests.post(
        f"{NOTION_API}/pages",
        headers=NOTION_HEADERS,
        json={
            "parent": {"database_id": NOTION_DB_ID},
            "properties": {
                "投稿文": {"title": [{"text": {"content": post_text}}]},
                "アカウント": {"select": {"name": account_key}},
                "プラットフォーム": {"multi_select": [{"name": "X"}, {"name": "Threads"}]},
                "ステータス": {"select": {"name": "ストック中"}},
                "投稿日": {"date": {"start": tomorrow}},
                "投稿時刻": {"rich_text": [{"text": {"content": "12:00"}}]},
                "カテゴリ": {"select": {"name": "AI生成"}},
            },
        }
    )
    return res.status_code == 200


def main():
    print(f"=== SNS投稿文自動生成 {date.today()} ===")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"翌日（{tomorrow}）分を生成します\n")

    for account_key in ["nakyatsukuruapp", "Sirius"]:
        print(f"--- {account_key} ---")
        past_posts = get_past_posts(account_key)
        print(f"  過去投稿: {len(past_posts)}件")
        used_themes = get_used_themes(account_key)
        print(f"  最近のテーマ: {len(used_themes)}件")
        print(f"  投稿文生成中...")
        try:
            post_text = generate_post(account_key, past_posts, used_themes)
            print(f"\n  【生成された投稿文】\n{post_text}\n")
            ok = save_to_notion(account_key, post_text)
            if ok:
                print(f"  ✅ Notionに保存完了（{tomorrow} 12:00投稿予定）")
            else:
                print(f"  ❌ Notion保存失敗")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
        print()

    print("=== 完了 ===")


if __name__ == "__main__":
    main()
