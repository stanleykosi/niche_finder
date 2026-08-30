"""Local YouTube-shaped fixture site for Playwright and API smoke tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent
SCENARIO = os.environ.get("FIXTURE_SCENARIO", "strong")
payload_path = ROOT / f"{SCENARIO}.json"
if not payload_path.exists():
    payload_path = ROOT / "strong.json"
DATA = json.loads(payload_path.read_text())

app = FastAPI(title="YouTube fixture server")


def _card(item: dict, position: int) -> str:
    kind = "Short" if item.get("presented_as_short") else "Video"
    return f'''<article data-testid="search-result" data-video-id="{item['video_id']}">
      <a href="/watch?v={item['video_id']}" title="{item['title']}">{item['title']}</a>
      <span data-testid="channel">{item.get('channel_title', '')}</span>
      <span data-testid="views">{item.get('visible_views_text', '')}</span>
      <span data-testid="age">{item.get('visible_age_text', '')}</span>
      <span data-testid="presentation">{kind}</span>
    </article>'''


@app.get("/results", response_class=HTMLResponse)
def search(search_query: str = "") -> str:
    cards = "\n".join(_card(item, index) for index, item in enumerate(DATA.get("search", []), start=1))
    return f'''<!doctype html><html><head><title>Search - fixture</title></head><body>
      <header><a href="/" aria-label="YouTube home">NicheTube fixture</a><form><input name="search_query" value="{search_query}" aria-label="Search" /></form></header>
      <main data-page="search"><h1>Search results for {search_query}</h1><section id="results">{cards}</section><div data-testid="lazy-loaded">More results are available in the bounded fixture.</div></main>
    </body></html>'''


@app.get("/watch", response_class=HTMLResponse)
def watch(v: str) -> str:
    videos = DATA.get("videos", {})
    item = videos.get(v, {}) if isinstance(videos, dict) else next((item for item in videos if item.get("id") == v), {})
    transcript = item.get("visible_transcript")
    transcript_html = f'<section data-testid="transcript"><h2>Transcript</h2><p>{transcript}</p></section>' if transcript else '<section data-testid="transcript-missing">Transcript unavailable</section>'
    related = "".join(f'<a data-testid="related-video" href="/watch?v={entry.get("video_id", entry.get("id", ""))}">{entry.get("title", "Related fixture")}</a>' for entry in DATA.get("search", [])[:3])
    return f'''<!doctype html><html><head><title>{item.get('title', 'Fixture video')}</title></head><body>
      <main data-page="video" data-video-id="{v}"><h1>{item.get('title', 'Fixture video')}</h1><div data-testid="opening-visual">{item.get('opening_visual_summary', 'Visible proof fixture')}</div>
      <span data-testid="short-presentation">{'Shorts' if item.get('is_short_presentation') else 'Long-form'}</span>{transcript_html}
      <section data-testid="related">{related}</section></main></body></html>'''


@app.get("/shorts", response_class=HTMLResponse)
def shorts(v: str = "") -> str:
    return watch(v).replace('data-page="video"', 'data-page="shorts"')


@app.get("/channel/{channel_id}", response_class=HTMLResponse)
def channel(channel_id: str) -> str:
    channel_data = DATA.get("channels", {})
    if isinstance(channel_data, list):
        channel_data = next((item for item in channel_data if item.get("id") == channel_id), {})
        title = channel_data.get("title", channel_id)
        uploads = channel_data.get("uploads", [])
    else:
        channel_data = channel_data.get(channel_id, {})
        title = channel_data.get("title", channel_id)
        uploads = channel_data.get("videos", [])
    cards = "".join(f'<a data-testid="channel-video" href="/watch?v={video_id}">{video_id}</a>' for video_id in uploads)
    return f'''<!doctype html><html><body><main data-page="channel"><h1>{title}</h1><p data-testid="channel-description">Fixture channel page</p><section>{cards}</section></main></body></html>'''


@app.get("/api/fixture/search")
def fixture_search(q: str = "") -> JSONResponse:
    return JSONResponse({"scenario": SCENARIO, "query": q, "items": DATA.get("search", [])})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "scenario": SCENARIO}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)

