"""Search engine facade: builds queries, previews them in the browser and turns
them into collection jobs. Also offers search inside the local database."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from analytics import statistics as st
from collectors import collection_manager as cm
from search.query_builder import SearchParams, build_queries, describe, search_url


class SearchEngine:
    def preview(self, params: SearchParams) -> list[dict]:
        """Return the X queries and URLs that would be executed (no browser needed)."""
        return [{"query": q, "url": search_url(q, params.sort)} for q in build_queries(params)]

    def open_in_browser(self, params: SearchParams, index: int = 0) -> dict:
        from browser.browser_manager import get_browser_manager
        q = build_queries(params)[index]
        return get_browser_manager().goto(search_url(q, params.sort))

    def create_job(self, name: str, params: SearchParams, max_posts: int | None = None,
                   start: bool = False, created_by: str | None = None) -> int:
        name = name.strip() or describe(params) or "عملية بحث"
        job_id = cm.create_job_from_params(name, params, max_posts=max_posts, created_by=created_by)
        if start:
            cm.start_job(job_id)
        return job_id

    # convenience builders ------------------------------------------------
    @staticmethod
    def hashtags(tags: list[str], mode: str = "any", **kw) -> SearchParams:
        return SearchParams(search_type="hashtag", hashtags=tags, hashtag_mode=mode, **kw)

    @staticmethod
    def users(usernames: list[str], topic: str = "", mode: str = "separate", **kw) -> SearchParams:
        return SearchParams(search_type="user", usernames=usernames, keywords=topic, user_mode=mode, **kw)

    @staticmethod
    def keywords(query: str, **kw) -> SearchParams:
        return SearchParams(search_type="keyword", keywords=query, **kw)

    @staticmethod
    def with_dates(params: SearchParams, since=None, until=None) -> SearchParams:
        return replace(params, since=since, until=until)

    # local database search ------------------------------------------------
    def search_local(self, keyword: str | None = None, **filters) -> pd.DataFrame:
        return st.load_posts(keyword=keyword, **filters)


engine = SearchEngine()
