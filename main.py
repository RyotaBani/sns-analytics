"""
SNS Analytics Collector
X (twikit) + Threads (公式API) + Note (Playwright) → Google Sheets
"""

import asyncio
import sys
import json
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from x_client import XClient
from threads_client import ThreadsClient
from note_client import NoteClient
from sheets_writer import SheetsWriter
from config import ACCOUNTS
from notion_writer import NotionWriter


async def main():
    today = date.today().isoformat()
    print(f"=== Analytics Collection: {today} ===")

    sheets = SheetsWriter(
        credentials_json=json.loads(os.environ["GOOGLE_CREDENTIALS"]),
        spreadsheet_id=os.environ["SPREADSHEET_ID"],
    )

    x_followers = {}
    threads_followers = {}

    for account_key, account_cfg in ACCOUNTS.items():
        print(f"\n--- {account_key} ---")

        # ── X ───────────────────────────────────────────
        if account_cfg.get("x_username"):
            try:
                cookies = json.loads(os.environ[f"X_COOKIES_{account_key.upper()}"])
                x = XClient(cookies=cookies)
                await x.init()

                user = await x.get_user(account_cfg["x_username"])
                sheets.append("X_アカウント", {
                    "date": today,
                    "account": account_key,
                    "followers": user.followers_count,
                    "following": user.following_count,
                })
                x_followers[account_key] = user.followers_count
                print(f"  X followers: {user.followers_count}")

                tweets = await x.get_recent_tweets(account_cfg["x_username"], count=20)
                tweet_rows = [{
                    "date": today,
                    "account": account_key,
                    "tweet_id": tw.get("id", ""),
                    "created_at": tw.get("date", ""),
                    "text": tw.get("text", "")[:100],
                    "views": tw.get("views", 0),
                    "likes": tw.get("likes", 0),
                    "retweets": tw.get("retweets", 0),
                    "replies": tw.get("replies", 0),
                    "quotes": 0,
                    "bookmarks": 0,
                } for tw in tweets]
                sheets.append_batch("X_ツイート", tweet_rows)
                print(f"  X tweets logged: {len(tweet_rows)}")

            except Exception as e:
                print(f"  [ERROR] X ({account_key}): {e}")

        # ── Threads ─────────────────────────────────────
        if account_cfg.get("threads_username"):
            th = None
            try:
                cookies = json.loads(os.environ.get(f"THREADS_COOKIES_{account_key.upper()}", "{}"))
                if not cookies:
                    cookies = json.loads(os.environ.get(f"NOTE_COOKIES_{account_key.upper()}", "{}"))
                th = ThreadsClient(cookies=cookies, username=account_cfg["threads_username"])
                await th.init()

                profile = await th.get_profile()
                sheets.append("Threads_アカウント", {
                    "date": today,
                    "account": account_key,
                    **profile,
                })
                threads_followers[account_key] = profile['followers']
                print(f"  Threads followers: {profile['followers']}")

                posts = await th.get_posts(limit=10)
                post_rows = [{
                    "date": today,
                    "account": account_key,
                    **p,
                } for p in posts]
                sheets.append_batch("Threads_投稿", post_rows)
                print(f"  Threads posts logged: {len(post_rows)}")

            except Exception as e:
                print(f"  [ERROR] Threads ({account_key}): {e}")
            finally:
                if th:
                    await th.close()

        # ── Note ────────────────────────────────────────
        if account_cfg.get("note_username"):
            note = None
            try:
                cookies = json.loads(os.environ[f"NOTE_COOKIES_{account_key.upper()}"])
                note = NoteClient(cookies=cookies)
                await note.init()

                profile = await note.get_profile(account_cfg["note_username"])
                sheets.append("Note_アカウント", {
                    "date": today,
                    "account": account_key,
                    **profile,
                })
                print(f"  Note followers: {profile['followers']}")

                articles = await note.get_articles(account_cfg["note_username"], limit=20)
                article_rows = [{
                    "date": today,
                    "account": account_key,
                    **a,
                } for a in articles]
                sheets.append_batch("Note_記事", article_rows)
                print(f"  Note articles logged: {len(article_rows)}")

            except Exception as e:
                print(f"  [ERROR] Note ({account_key}): {e}")
            finally:
                if note:
                    await note.close()

    # ── Notion フォロワー数更新 ──────────────────────
    try:
        notion = NotionWriter()
        notion.update_followers({
            "nakyatsukuruapp_x": x_followers.get("nakyatsukuruapp", 0),
            "nakyatsukuruapp_threads": threads_followers.get("nakyatsukuruapp", 0),
            "sirius_x": x_followers.get("sirius", 0),
            "sirius_threads": threads_followers.get("sirius", 0),
        })
    except Exception as e:
        print(f"  [ERROR] Notion: {e}")

    print("\n=== Done ===")


async def run_posters():
    """X・Threads自動投稿（時刻指定対応）"""
    try:
        from x_poster import main as x_main
        await x_main()
    except Exception as e:
        print(f"  [ERROR] X poster: {e}")
    try:
        from threads_poster import main as threads_main
        await threads_main()
    except Exception as e:
        print(f"  [ERROR] Threads poster: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
    asyncio.run(run_posters())
    # 毎日7時のみ投稿文を自動生成
    import datetime as _dt
    if _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).hour == 7:
        from content_generator import main as gen_main
        gen_main()
