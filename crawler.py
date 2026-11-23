"""
🔥 Autonomous 24/7 Web & News Discovery Engine
Ultra-lightweight crawler designed for serverless execution.
Fetches breaking national/global news and trending tech launches,
then ingests into TiDB Cloud Serverless index with sub-second execution.
"""

import os
import sys
import ssl
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import pymysql

# Auto-load .env file if present (Zero external dependencies)
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# Read connection settings from Environment (Local .env or GitHub Secrets)
TIDB_HOST = os.environ.get("TIDB_HOST", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com")
TIDB_PORT = int(os.environ.get("TIDB_PORT", 4000))
TIDB_USER = os.environ.get("TIDB_USER", "2yosQ4Mw9AHbs15.root")
TIDB_PASSWORD = os.environ.get("TIDB_PASSWORD", "")
TIDB_DATABASE = os.environ.get("TIDB_DATABASE", "agnisearch")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'AgniSearchBot/2.0 (+https://search.jayanticybernetics.in; PublicWebCrawler)'
}

NEWS_FEEDS = [
    ("https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en", "India News"),
    ("https://pib.gov.in/RssMain.aspx?ModId=6&LangId=1", "Government of India"),
    ("https://techcrunch.com/feed/", "Technology"),
    ("https://www.theverge.com/rss/index.xml", "Tech & Gadgets"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "World News"),
    ("https://www.livemint.com/rss/news", "Business & Markets"),
    ("https://feeds.feedburner.com/ndtvnews-top-stories", "National News"),
    ("https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "Top Stories")
]

def get_db_connection():
    if not TIDB_PASSWORD:
        raise ValueError("TIDB_PASSWORD is not set in environment or .env file!")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return pymysql.connect(
        host=TIDB_HOST,
        port=TIDB_PORT,
        user=TIDB_USER,
        password=TIDB_PASSWORD,
        database=TIDB_DATABASE,
        ssl=ctx,
        autocommit=True,
        charset='utf8mb4',
        connect_timeout=6,
        read_timeout=6
    )

def clean_text(text: str) -> str:
    if not text:
        return ""
    import re, html
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def fetch_feed_items(feed_url: str, category: str) -> list:
    items = []
    try:
        req = urllib.request.Request(feed_url, headers=HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=6) as resp:
            content = resp.read()
            root = ET.fromstring(content)
            for item in root.findall('.//item')[:15]:
                title = clean_text(item.findtext('title') or '')
                link = (item.findtext('link') or '').strip()
                desc = clean_text(item.findtext('description') or '')
                if not title or not link or not link.startswith('http'):
                    continue
                parsed = urllib.parse.urlparse(link)
                domain = parsed.netloc.lower().replace('www.', '')
                if ':' in domain:
                    domain = domain.split(':')[0]
                if not domain:
                    continue
                items.append((link[:760], title[:950], desc[:350], category[:100], domain[:250]))
    except Exception:
        pass
    return items

def fetch_hackernews_launches() -> list:
    items = []
    try:
        req = urllib.request.Request("https://hacker-news.firebaseio.com/v0/newstories.json", headers=HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=5) as resp:
            story_ids = json.loads(resp.read().decode('utf-8'))[:20]
        
        for sid in story_ids:
            try:
                s_req = urllib.request.Request(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", headers=HEADERS)
                with urllib.request.urlopen(s_req, context=SSL_CTX, timeout=3) as s_resp:
                    data = json.loads(s_resp.read().decode('utf-8'))
                    title = data.get('title', '').strip()
                    url = data.get('url', '').strip()
                    if not title or not url or not url.startswith('http'):
                        continue
                    parsed = urllib.parse.urlparse(url)
                    domain = parsed.netloc.lower().replace('www.', '')
                    if ':' in domain:
                        domain = domain.split(':')[0]
                    desc = f"Latest tech launch and discussion: {title} on {domain}."
                    items.append((url[:760], title[:950], desc[:350], "Tech & Startups", domain[:250]))
            except Exception:
                continue
    except Exception:
        pass
    return items

def run():
    print("=" * 65, flush=True)
    print("🚀 24/7 AUTONOMOUS WEB & NEWS CRAWLER CYCLE START", flush=True)
    print("=" * 65, flush=True)
    start_time = time.time()
    all_items = []

    # 1. Fetch live breaking feeds
    for feed_url, cat in NEWS_FEEDS:
        items = fetch_feed_items(feed_url, cat)
        all_items.extend(items)
        print(f"📡 Fetched {len(items)} items from {cat}", flush=True)

    # 2. Fetch tech launches
    hn_items = fetch_hackernews_launches()
    all_items.extend(hn_items)
    print(f"🎯 Fetched {len(hn_items)} items from Hacker News", flush=True)

    # 3. Deduplicate
    seen = set()
    unique = []
    for it in all_items:
        if it[0] not in seen:
            seen.add(it[0])
            unique.append(it)

    print(f"📦 Total Unique Fresh Items to Ingest: {len(unique)}", flush=True)

    # 4. Insert into TiDB Cloud Serverless
    inserted = 0
    if unique:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                sql = """
                INSERT IGNORE INTO documents (url, title, description, category, domain)
                VALUES (%s, %s, %s, %s, %s)
                """
                cur.executemany(sql, unique)
                inserted = cur.rowcount
            conn.close()
            print(f"✅ Successfully Ingested {inserted} New Fresh Records into TiDB Cloud!", flush=True)
        except Exception as e:
            print(f"❌ Database Ingestion Error: {e}", flush=True)

    elapsed = time.time() - start_time
    print(f"🏁 Crawler Cycle Finished in {elapsed:.2f}s", flush=True)

if __name__ == '__main__':
    run()
