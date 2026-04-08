"""
X (Twitter) クライアント
Playwright でクッキーを使って直接スクレイピング
"""

import asyncio
import re
from playwright.async_api import async_playwright


class XClient:
    def __init__(self, cookies: dict):
        self._cookies = cookies
        self._browser = None
        self._ctx = None
        self._page = None

    async def init(self):
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=True)
        self._ctx = await self._browser.new_context()
        await self._ctx.add_cookies([
            {"name": k, "value": v, "domain": ".x.com", "path": "/"}
            for k, v in self._cookies.items()
        ])
        self._page = await self._ctx.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()

    async def get_user(self, username: str):
        """ユーザー情報取得（フォロワー数）"""
        await self._page.goto(
            f"https://x.com/{username}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)

        followers = 0
        following = 0
        try:
            # フォロワー数
            follower_links = await self._page.query_selector_all(
                f'a[href*="verified_followers"], a[href*="/followers"]'
            )
            for el in follower_links:
                text = await el.inner_text()
                nums = re.findall(r"[\d,\.]+", text)
                if nums:
                    n = nums[0].replace(",", "")
                    if "万" in text:
                        followers = int(float(n) * 10000)
                    else:
                        followers = int(float(n))
                    break

            # フォロー数
            following_links = await self._page.query_selector_all(
                f'a[href*="/following"]'
            )
            for el in following_links:
                text = await el.inner_text()
                nums = re.findall(r"[\d,\.]+", text)
                if nums:
                    following = int(nums[0].replace(",", ""))
                    break
        except Exception as e:
            print(f"    [WARN] X profile error: {e}")

        # ダミーオブジェクトを返す
        return _UserInfo(username=username, followers_count=followers, following_count=following)

    async def get_recent_tweets(self, user_id: str, count: int = 20):
        """最新ツイートのメトリクスを取得"""
        username = user_id  # user_id の代わりに username を渡す
        await self._page.goto(
            f"https://x.com/{username}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)

        # スクロールしてツイートを読み込む
        for _ in range(2):
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

        # ツイートのリンクを収集
        tweet_links = await self._page.query_selector_all('a[href*="/status/"]')
        tweet_ids = []
        seen = set()
        for el in tweet_links:
            href = await el.get_attribute("href")
            if href and "/status/" in href and username.lower() in href.lower():
                m = re.search(r"/status/(\d+)", href)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    tweet_ids.append(m.group(1))
            if len(tweet_ids) >= count:
                break

        tweets = []
        for tweet_id in tweet_ids[:count]:
            tweet = await self._get_tweet_stats(username, tweet_id)
            if tweet:
                tweets.append(tweet)
            await asyncio.sleep(1)

        return tweets

    async def _get_tweet_stats(self, username: str, tweet_id: str):
        """ツイート単体のメトリクス取得"""
        try:
            await self._page.goto(
                f"https://x.com/{username}/status/{tweet_id}",
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(2)

            # テキスト取得
            text = ""
            text_el = await self._page.query_selector('[data-testid="tweetText"]')
            if text_el:
                text = await text_el.inner_text()

            # ビュー数
            views = 0
            view_els = await self._page.query_selector_all('a[href*="/analytics"]')
            for el in view_els:
                t = await el.inner_text()
                if t:
                    n = re.sub(r"[^\d]", "", t)
                    if n:
                        views = int(n)
                        break

            # いいね・RT・返信
            likes = retweets = replies = quotes = bookmarks = 0
            stat_els = await self._page.query_selector_all('[data-testid$="-count"]')
            for el in stat_els:
                testid = await el.get_attribute("data-testid")
                t = await el.inner_text()
                n = int(re.sub(r"[^\d]", "", t) or "0")
                if "like" in testid:
                    likes = n
                elif "retweet" in testid:
                    retweets = n
                elif "reply" in testid:
                    replies = n

            return _TweetInfo(
                id=tweet_id,
                created_at="",
                text=text[:100],
                view_count=views,
                favorite_count=likes,
                retweet_count=retweets,
                reply_count=replies,
                quote_count=quotes,
                bookmark_count=bookmarks,
            )
        except Exception as e:
            print(f"    [WARN] tweet error ({tweet_id}): {e}")
            return None


class _UserInfo:
    def __init__(self, username, followers_count, following_count):
        self.id = username
        self.followers_count = followers_count
        self.following_count = following_count


class _TweetInfo:
    def __init__(self, id, created_at, text, view_count,
                 favorite_count, retweet_count, reply_count,
                 quote_count, bookmark_count):
        self.id = id
        self.created_at = created_at
        self.text = text
        self.view_count = view_count
        self.favorite_count = favorite_count
        self.retweet_count = retweet_count
        self.reply_count = reply_count
        self.quote_count = quote_count
        self.bookmark_count = bookmark_count
