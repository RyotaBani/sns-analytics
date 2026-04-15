import json, re, asyncio, urllib.parse
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

class _User:
    def __init__(self, followers=0, following=0):
        self.followers_count = followers
        self.following_count = following

class XClient:
    def __init__(self, cookies):
        self.cookies = cookies

    async def init(self): pass

    async def get_user(self, username):
        return await self.get_profile(username)

    async def get_profile(self, username):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox"])
            ctx = await browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":800})
            await ctx.add_cookies([{"name":k,"value":str(v),"domain":".x.com","path":"/","secure":True} for k,v in self.cookies.items()])
            page = await ctx.new_page()
            try:
                await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(6)
                content = await page.content()
                followers = 0
                following = 0
                m = re.search(r'"followers_count":(\d+)', content)
                if m:
                    followers = int(m.group(1))
                m2 = re.search(r'"friends_count":(\d+)', content)
                if m2:
                    following = int(m2.group(1))
                if followers == 0:
                    for el in await page.query_selector_all("a[href*='/followers']"):
                        txt = await el.inner_text()
                        m3 = re.search(r'[\d,]+', txt)
                        if m3:
                            followers = int(m3.group().replace(",",""))
                            break
                return _User(followers, following)
            except Exception as e:
                print(f"    [WARN] X error ({username}): {e}")
                return _User(0, 0)
            finally:
                await browser.close()

    async def get_recent_tweets(self, username, limit=10, count=10):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox"])
            ctx = await browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":800})
            await ctx.add_cookies([{"name":k,"value":str(v),"domain":".x.com","path":"/","secure":True} for k,v in self.cookies.items()])
            page = await ctx.new_page()
            try:
                await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                tweets = []
                today = datetime.now(JST).strftime("%Y-%m-%d")
                for article in (await page.query_selector_all('article[data-testid="tweet"]'))[:limit]:
                    try:
                        te = await article.query_selector('[data-testid="tweetText"]')
                        text = await te.inner_text() if te else ""
                        le = await article.query_selector('[data-testid="like"] span')
                        likes = _p(await le.inner_text() if le else "0")
                        re_ = await article.query_selector('[data-testid="retweet"] span')
                        rts = _p(await re_.inner_text() if re_ else "0")
                        rep = await article.query_selector('[data-testid="reply"] span')
                        replies = _p(await rep.inner_text() if rep else "0")
                        ve = await article.query_selector('a[href*="/analytics"] span')
                        views = _p(await ve.inner_text()) if ve else 0
                        if text:
                            tweets.append({"date":today,"account":username,"text":text[:100],"views":views,"likes":likes,"retweets":rts,"replies":replies})
                    except: continue
                return tweets
            finally:
                await browser.close()

def _p(text):
    if not text: return 0
    text = text.strip().replace(",","")
    try:
        if "万" in text: return int(float(text.replace("万",""))*10000)
        if text.upper().endswith("K"): return int(float(text[:-1])*1000)
        if text.upper().endswith("M"): return int(float(text[:-1])*1000000)
        return int(float(text))
    except: return 0
