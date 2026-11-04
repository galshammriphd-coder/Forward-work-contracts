"""JavaScript executed inside the X page to read the posts that are rendered.

Used as a fallback (and cross-check) for the GraphQL responses: it only reads what
is visible in the page the user is looking at. Selectors use X's stable
``data-testid`` attributes; counters are read from the aria-labels, which also
works with the Arabic interface.
"""

EXTRACT_JS = r"""
() => {
  const out = [];
  const textOf = (el) => {
    if (!el) return "";
    let s = "";
    el.childNodes.forEach((n) => {
      if (n.nodeType === Node.TEXT_NODE) s += n.textContent;
      else if (n.tagName === "IMG") s += n.getAttribute("alt") || "";
      else if (n.tagName === "BR") s += "\n";
      else s += textOf(n);
    });
    return s;
  };
  const firstNumber = (label) => {
    if (!label) return null;
    const m = label.match(/[\d٠-٩][\d٠-٩,.٫٬]*\s*(K|M|B|ألف|مليون|مليار)?/i);
    return m ? m[0] : null;
  };
  const metric = (art, ids) => {
    for (const id of ids) {
      const b = art.querySelector(`[data-testid="${id}"]`);
      if (b) {
        const n = firstNumber(b.getAttribute("aria-label"));
        if (n) return n;
        const t = (b.innerText || "").trim();
        return t || "0";
      }
    }
    return null;
  };
  document.querySelectorAll('article[data-testid="tweet"]').forEach((art) => {
    try {
      const time = art.querySelector("time");
      const link = time ? time.closest('a[href*="/status/"]') : art.querySelector('a[href*="/status/"]');
      if (!link) return;
      const href = link.getAttribute("href");
      const m = href.match(/^\/([A-Za-z0-9_]{1,15})\/status\/(\d+)/);
      if (!m) return;
      const nameBlock = art.querySelector('[data-testid="User-Name"]');
      let display = "";
      if (nameBlock) {
        const span = nameBlock.querySelector("span");
        display = span ? textOf(span).trim() : "";
      }
      const textEl = art.querySelector('[data-testid="tweetText"]');
      const social = art.querySelector('[data-testid="socialContext"]');
      const socialText = social ? (social.innerText || "") : "";
      let postType = "original";
      if (/repost|retweet|أعاد|إعادة/i.test(socialText)) postType = "repost";
      else if (/Replying to|ردًا على|رداً على|الرد على/.test((art.innerText || "").slice(0, 400))) postType = "reply";
      else if (art.querySelectorAll("time").length > 1) postType = "quote";
      const views = art.querySelector('a[href$="/analytics"]');
      const links = Array.from(art.querySelectorAll('[data-testid="tweetText"] a[href^="http"], [data-testid="card.wrapper"] a[href^="http"]')).map(a => a.href);
      const images = Array.from(art.querySelectorAll('[data-testid="tweetPhoto"] img')).map(i => i.src);
      out.push({
        post_id: m[2],
        username: m[1],
        display_name: display,
        post_url: "https://x.com" + href.split("?")[0].replace(/\/(analytics|photo\/\d+|video\/\d+)$/, ""),
        datetime: time ? time.getAttribute("datetime") : null,
        text: textOf(textEl).trim(),
        lang: textEl ? textEl.getAttribute("lang") : null,
        replies: metric(art, ["reply"]),
        reposts: metric(art, ["retweet", "unretweet"]),
        likes: metric(art, ["like", "unlike"]),
        views: views ? firstNumber(views.getAttribute("aria-label")) : null,
        links: links,
        images: images,
        has_video: !!art.querySelector('[data-testid="videoPlayer"], video'),
        post_type: postType,
      });
    } catch (e) { /* skip malformed article */ }
  });
  return out;
}
"""

PAGE_STATE_JS = r"""
() => {
  const q = (s) => !!document.querySelector(s);
  const body = (document.body && document.body.innerText) || "";
  let handle = null;
  const sw = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
  if (sw) {
    const m = (sw.innerText || "").match(/@([A-Za-z0-9_]{1,15})/);
    if (m) handle = m[1];
  }
  if (!handle) {
    const prof = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    if (prof) handle = (prof.getAttribute("href") || "").replace("/", "") || null;
  }
  return {
    url: location.href,
    logged_in_ui: q('[data-testid="SideNav_AccountSwitcher_Button"]') || q('a[data-testid="AppTabBar_Profile_Link"]'),
    login_form: q('input[autocomplete="username"]') || q('[data-testid="loginButton"]') || location.pathname.startsWith("/i/flow/login"),
    handle: handle,
    articles: document.querySelectorAll('article[data-testid="tweet"]').length,
    empty_state: q('[data-testid="emptyState"]'),
    retry_button: Array.from(document.querySelectorAll('[role="button"]')).some(b => /^(Retry|إعادة المحاولة)$/.test((b.innerText||"").trim())),
    rate_limited: /rate limit|Something went wrong|حدث خطأ ما|تجاوزت/i.test(body.slice(0, 5000)),
    locked: /Your account is (locked|suspended)|تم قفل حسابك|تم تعليق/i.test(body.slice(0, 5000)),
  };
}
"""

CLICK_RETRY_JS = r"""
() => {
  const b = Array.from(document.querySelectorAll('[role="button"]')).find(b => /^(Retry|إعادة المحاولة)$/.test((b.innerText||"").trim()));
  if (b) { b.click(); return true; }
  return false;
}
"""
