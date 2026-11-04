"""TEST FIXTURES ONLY.

Synthetic records shaped like the JSON the X web client receives, used to test
parsing, storage and the collection loop offline. Accounts are named
``fixture_*`` and texts are marked as test content; they are never written to
the application's real database (tests use a temporary database).
"""
from __future__ import annotations

import json

BASE_ID = 1850000000000000000


def user(n: int, new_layout: bool = True) -> dict:
    screen = f"fixture_user{n}"
    legacy = {"followers_count": 1000 * n, "friends_count": 10 * n, "statuses_count": 500 + n,
              "description": f"حساب اختبار رقم {n}"}
    u = {"__typename": "User", "rest_id": str(9000 + n), "is_blue_verified": n % 2 == 0, "legacy": legacy}
    if new_layout:
        u["core"] = {"name": f"مستخدم اختبار {n}", "screen_name": screen, "created_at": "Tue Mar 10 12:00:00 +0000 2015"}
        u["avatar"] = {"image_url": f"https://pbs.twimg.com/profile_images/{n}.jpg"}
        u["location"] = {"location": "الرياض"}
    else:
        legacy.update({"name": f"مستخدم اختبار {n}", "screen_name": screen, "created_at": "Tue Mar 10 12:00:00 +0000 2015",
                       "profile_image_url_https": f"https://pbs.twimg.com/profile_images/{n}.jpg", "location": "جدة"})
    return u


def tweet(i: int, author: int = 1, text: str | None = None, lang: str = "ar", hashtags=("الذكاء_الاصطناعي",),
          created="Mon Nov 02 08:15:00 +0000 2026", likes=None, reply_to=None, new_layout=True) -> dict:
    pid = str(BASE_ID + i)
    text = text or f"نص اختبار رقم {i} عن #الذكاء_الاصطناعي في المملكة https://t.co/abc{i}"
    legacy = {
        "id_str": pid, "created_at": created, "full_text": text, "lang": lang,
        "favorite_count": likes if likes is not None else 10 * i, "retweet_count": i, "reply_count": i % 3,
        "quote_count": 0, "bookmark_count": 1, "conversation_id_str": pid,
        "entities": {"hashtags": [{"text": h} for h in hashtags], "user_mentions": [{"screen_name": "fixture_mention"}],
                     "urls": [{"url": f"https://t.co/abc{i}", "expanded_url": f"https://example.org/article/{i}"}]},
    }
    if reply_to:
        legacy["in_reply_to_status_id_str"] = str(reply_to)
        legacy["in_reply_to_screen_name"] = "fixture_user9"
    return {"__typename": "Tweet", "rest_id": pid,
            "core": {"user_results": {"result": user(author, new_layout)}},
            "views": {"count": str(100 * i), "state": "EnabledWithCount"},
            "legacy": legacy}


def search_timeline(tweets: list[dict]) -> dict:
    entries = [{"entryId": f"tweet-{t['rest_id']}", "content": {"entryType": "TimelineTimelineItem", "itemContent": {
        "itemType": "TimelineTweet", "tweet_results": {"result": t}}}} for t in tweets]
    entries.append({"entryId": "cursor-bottom-0", "content": {"entryType": "TimelineTimelineCursor", "value": "DAADDAAB",
                                                              "cursorType": "Bottom"}})
    return {"data": {"search_by_raw_query": {"search_timeline": {"timeline": {"instructions": [
        {"type": "TimelineAddEntries", "entries": entries}]}}}}}


def profile_payload(n: int) -> dict:
    return {"data": {"user": {"result": user(n)}}}


FAKE_X_PAGE = """<!doctype html><html lang="ar"><head><meta charset="utf-8"><title>X (test fixture)</title></head>
<body>
<nav><a data-testid="AppTabBar_Profile_Link" href="/fixture_me">Profile</a>
<div data-testid="SideNav_AccountSwitcher_Button">fixture me @fixture_me</div></nav>
<main id="timeline" style="padding-bottom:3000px"></main>
<script>
let page = 0; let loading = false; const MAX = __PAGES__;
function render(items){
  const tl = document.getElementById('timeline');
  for (const it of items){
    const a = document.createElement('article'); a.setAttribute('data-testid','tweet');
    a.style.height = '400px';
    a.innerHTML = `<div data-testid="User-Name"><span>${it.name}</span><a href="/${it.user}">@${it.user}</a></div>
      <a href="/${it.user}/status/${it.id}"><time datetime="${it.dt}">x</time></a>
      <div data-testid="tweetText" lang="ar">${it.text}</div>
      <button data-testid="reply" aria-label="${it.replies} Replies. Reply"></button>
      <button data-testid="retweet" aria-label="${it.reposts} reposts. Repost"></button>
      <button data-testid="like" aria-label="${it.likes} Likes. Like"></button>
      <a href="/${it.user}/status/${it.id}/analytics" aria-label="${it.views} views. View post analytics"></a>`;
    tl.appendChild(a);
  }
}
async function load(){
  if (loading || page >= MAX) return; loading = true;
  const r = await fetch('/i/api/graphql/TESTQID/SearchTimeline?page=' + page);
  const j = await r.json(); page += 1;
  const items = [];
  for (const ins of j.data.search_by_raw_query.search_timeline.timeline.instructions)
    for (const e of ins.entries) { const t = e.content.itemContent && e.content.itemContent.tweet_results.result;
      if (!t) continue; const u = t.core.user_results.result;
      items.push({id: t.rest_id, user: u.core.screen_name, name: u.core.name, dt: new Date(t.legacy.created_at).toISOString(),
        text: t.legacy.full_text, replies: t.legacy.reply_count, reposts: t.legacy.retweet_count,
        likes: t.legacy.favorite_count, views: t.views.count}); }
  render(items); loading = false;
}
window.addEventListener('scroll', () => { if (window.innerHeight + window.scrollY > document.body.scrollHeight - 1500) load(); });
window.addEventListener('wheel', () => setTimeout(load, 50));
load();
</script></body></html>"""


def fake_x_page(pages: int) -> str:
    return FAKE_X_PAGE.replace("__PAGES__", str(pages))


def to_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
