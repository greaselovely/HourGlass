"""
Daily narration segments for the TTS intro.

Pulls two sources and has Claude turn both into speech-ready prose:

    Spaceflight News API  ->  "<news sentence> You can read more about this at <site>."
    NASA APOD             ->  "Today from NASA. <fact sentence>"

Both are returned as separate segments so the caller can insert a pause between
them. Every stage degrades rather than fails:

    news + NASA  ->  whichever one succeeded  ->  nothing

An empty list just means the intro is the plain project description, exactly as
it was before this module existed.

Results are cached per-day, so re-running the video build (or a retry after a
crash) never re-spends an API call.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from .utils import message_processor

# SNAPI rejects the default Python-urllib agent with a 403.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

APOD_URL = "https://api.nasa.gov/planetary/apod"
SNAPI_URL = "https://api.spaceflightnewsapi.net/v4/articles/"
CACHE_FILE = Path(__file__).parent.parent / "cache" / "daily_fact.json"

NASA_PREFIX = "Today from NASA."
READ_MORE = "You can read more about this at {site}."

# ============================================================================
# Cache
# ============================================================================

def _read_cache():
    """Return the whole cache dict, or {} if it is missing or unreadable."""
    try:
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        return cached if isinstance(cached, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(date_key, segments):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"date": date_key, "segments": segments}, f)
    except OSError:
        pass


# ============================================================================
# Sources
# ============================================================================

def _error_detail(err):
    """Pull the reason out of an error body. api.data.gov puts the real cause
    (API_KEY_INVALID, OVER_RATE_LIMIT, ...) in the payload, not the status line."""
    try:
        body = json.loads(err.read())
    except Exception:
        return err.reason or "no detail"
    detail = body.get("error", body) if isinstance(body, dict) else body
    if isinstance(detail, dict):
        parts = [str(detail[k]) for k in ("code", "message") if detail.get(k)]
        if parts:
            return " - ".join(parts)
    return str(detail)[:200]


def _get_json(url, timeout=15):
    """Fetch JSON. Returns (data, status); status is None for non-HTTP errors."""
    endpoint = url.split("?")[0]
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except HTTPError as e:
        message_processor(
            f"Fetch failed ({endpoint}): HTTP {e.code} {_error_detail(e)}", "warning")
        return None, e.code
    except Exception as e:
        message_processor(f"Fetch failed ({endpoint}): {e}", "warning")
        return None, None


def _fetch_apod(api_key):
    """Fetch today's APOD. Returns (title, explanation) or (None, None)."""
    key = (api_key or "").strip()
    data, status = _get_json(f"{APOD_URL}?{urlencode({'api_key': key or 'DEMO_KEY'})}")

    if status == 403 and key:
        # api.data.gov only returns 403 when the key itself is bad - rate limits
        # come back as 429. A misconfigured key shouldn't cost us the segment,
        # and DEMO_KEY is good for 30/hr from one address.
        message_processor("NASA key rejected - retrying with DEMO_KEY", "warning")
        data, _ = _get_json(f"{APOD_URL}?{urlencode({'api_key': 'DEMO_KEY'})}")

    if not data:
        return None, None
    return data.get("title"), data.get("explanation")


def _fetch_news():
    """Fetch the most recent spaceflight news article. Returns dict or None."""
    data, _ = _get_json(f"{SNAPI_URL}?{urlencode({'limit': 1, 'ordering': '-published_at'})}")
    results = (data or {}).get("results") or []
    if not results:
        return None
    article = results[0]
    return {
        "title": article.get("title", ""),
        "summary": article.get("summary", ""),
        "news_site": article.get("news_site", ""),
        "published_at": article.get("published_at", ""),
    }


# ============================================================================
# Claude
# ============================================================================

PROMPT = """You are writing narration for the opening of a daily time-lapse video
filmed at the Very Large Array radio observatory. Everything you return is read
aloud by a text-to-speech voice.

For every field: use plain prose, no markdown, quotes, parentheses, brackets or
bullet points, and spell out all numerals, symbols and abbreviations as words
(for example "IFT-13" becomes "the thirteenth integrated flight test").

=== TODAY'S SPACEFLIGHT NEWS ===
Headline: {news_title}
Source: {news_site}
Summary: {news_summary}

=== TODAY'S NASA ASTRONOMY PICTURE OF THE DAY ===
Title: {apod_title}
{apod_explanation}

Return three fields:

1. news - ONE sentence of at most {max_words} words conveying what happened.
   The summary above comes from an RSS feed and may be truncated or padded with
   boilerplate. Ignore any trailing ellipsis, bracketed truncation marker, or
   phrases like "The post ... appeared first on ...". Write a clean sentence
   from the substance that remains; do not restate the headline verbatim.

2. news_site - the source name written the way it should be spoken. Strip domain
   suffixes and split run-together words. For example "SpacePolicyOnline.com"
   becomes "Space Policy Online"; "SpaceNews" becomes "Space News". If it is
   already natural, return it unchanged.

3. fact - ONE sentence of at most {max_words} words drawn from the NASA writeup.

   CRITICAL: this plays over a time-lapse of the Very Large Array. The listener
   never sees the NASA picture. Treat the writeup as raw source material about an
   astronomical subject, and say something true about that subject.

   The photograph itself is entirely off-limits. Not just its vocabulary - its
   whole content. Off-limits means:
   - spatial and pointing words: left, right, upper, lower, foreground, centre,
     this image, pictured, featured, shown here, the photograph
   - the photographer's vantage point and framing
   - coincidental alignments that hold only from where the camera stood
   - how the picture was made: exposures, timing, planning, equipment
   - objects mentioned only because they happen to fall inside the frame

   Write the underlying astronomy or geography instead: what the object is, how
   it formed, how far away it is, how big it is, what makes it unusual. The test
   is whether the sentence would still be true and interesting to someone who has
   never seen this picture and never will.

   Worked example. Given a writeup about a photo in which Barnard's Loop happens
   to line up between two Bolivian volcanoes:
   BAD  "Barnard's Loop is so large it can stretch between two Andean volcanoes
         on the horizon." - that is a fact about one photograph from one spot on
         one evening, not a fact about Barnard's Loop.
   GOOD "Barnard's Loop is a vast arc of glowing hydrogen gas across the
         constellation Orion, a shell swept out by ancient exploding stars."

   Lead with the most striking concrete detail, not with "Today's image shows".
   It is spoken immediately after the words "Today from NASA.", so it must read
   naturally following that phrase.

   Stay on ONE subject. A NASA writeup often covers several unrelated things;
   pick the single most interesting one and drop the rest. Never staple two
   unconnected facts together with "and" - that is worse than a shorter sentence.

4. fact_usable - true if that sentence genuinely stands alone with no picture
   present. Return false when today's writeup is so tied to its image that no
   self-contained fact can be drawn from it. Returning false is correct and
   expected on those days - the segment is simply left out rather than spoken as
   something vague or confusing. Do not force it."""

NARRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "news": {"type": "string"},
        "news_site": {"type": "string"},
        "fact": {"type": "string"},
        "fact_usable": {"type": "boolean"},
    },
    "required": ["news", "news_site", "fact", "fact_usable"],
    "additionalProperties": False,
}

# Phrases that only mean something with the picture in front of you. Claude is
# told to avoid these, but the result is spoken aloud with no chance to correct
# it, so a deterministic backstop is worth the few lines.
IMAGE_DEICTIC = re.compile(
    r"\b(pictured|featured here|shown here|seen here|"
    r"th(?:is|e) (?:image|picture|photo|photograph|scene)|"
    r"foreground|background|"
    r"(?:upper|lower|top|bottom) (?:left|right)|"
    r"(?:on|to) the (?:left|right))\b", re.IGNORECASE)


def _write_narration(article, apod, api_key, model, max_words):
    """Turn the raw sources into narration parts. Returns dict or None."""
    try:
        import anthropic
    except ImportError:
        message_processor(
            "anthropic package not installed - skipping narration "
            "(pip install anthropic)", "warning")
        return None

    apod_title, apod_explanation = apod
    try:
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            # Thinking is on by default on Opus 5 and shares this budget with the
            # response text, so leave real headroom even though the output is short.
            max_tokens=3000,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": NARRATION_SCHEMA},
            },
            messages=[{
                "role": "user",
                "content": PROMPT.format(
                    news_title=(article or {}).get("title", "(none available)"),
                    news_site=(article or {}).get("news_site", ""),
                    news_summary=(article or {}).get("summary", "(none available)"),
                    apod_title=apod_title or "(none available)",
                    apod_explanation=apod_explanation or "",
                    max_words=max_words),
            }],
        )
    except Exception as e:
        message_processor(f"Claude narration failed: {e}", "warning")
        return None

    if response.stop_reason == "refusal":
        message_processor("Claude declined the narration request", "warning")
        return None

    try:
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
    except (StopIteration, ValueError) as e:
        message_processor(f"Could not parse Claude narration: {e}", "warning")
        return None

    parts = {k: (data.get(k) or "").strip().strip('"').strip()
             for k in ("news", "news_site", "fact")}
    parts["fact_usable"] = bool(data.get("fact_usable"))
    return parts


# ============================================================================
# Public entry point
# ============================================================================

def get_daily_segments(config):
    """
    Return the narration segments that follow the project title.

    Each element is spoken as its own segment, separated by a pause. Typically
    two: today's spaceflight news, then the NASA fact. Returns [] to skip the
    whole thing.

    Args:
        config (dict): the full project config dict.
    """
    fact_cfg = (config.get("music", {})
                .get("tts_intro", {}).get("daily_fact", {}))

    if not fact_cfg.get("enabled"):
        return []

    date_key = datetime.now().strftime("%Y-%m-%d")
    cache = _read_cache()

    if cache.get("date") == date_key and cache.get("segments"):
        for segment in cache["segments"]:
            message_processor(f"Daily segment (cached): {segment}", "info")
        return cache["segments"]

    max_words = fact_cfg.get("max_words", 30)
    article = _fetch_news() if fact_cfg.get("news_enabled", True) else None
    apod = _fetch_apod(fact_cfg.get("nasa_api_key", ""))

    segments = []
    if article or apod[0]:
        parts = _write_narration(
            article, apod,
            api_key=fact_cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"),
            model=fact_cfg.get("model", "claude-opus-5"),
            max_words=max_words,
        )
        if parts:
            if article and parts["news"]:
                site = parts["news_site"] or article["news_site"]
                segments.append(f"{parts['news']} {READ_MORE.format(site=site)}")
            if apod[0] and parts["fact"]:
                if not parts["fact_usable"]:
                    message_processor(
                        "NASA writeup too tied to its image - skipping that segment", "info")
                elif IMAGE_DEICTIC.search(parts["fact"]):
                    message_processor(
                        f"NASA fact still referenced the picture - skipping: {parts['fact']}",
                        "warning")
                else:
                    segments.append(f"{NASA_PREFIX} {parts['fact']}")

        # Claude unavailable - the raw headline and APOD title are still real,
        # dated facts worth speaking.
        if not segments and article and article["title"]:
            site = article["news_site"]
            segments.append(f"{article['title']}."
                            + (f" {READ_MORE.format(site=site)}" if site else ""))
        if not segments and apod[0]:
            segments.append(f"{NASA_PREFIX} {apod[0]}.")

    if not segments:
        # Nothing reachable. Say nothing rather than invent something - the intro
        # falls back to the plain project description. Not cached, so a later run
        # today gets a fresh attempt.
        message_processor(
            "No daily segments available - intro will be the plain description", "warning")
        return []

    for segment in segments:
        message_processor(f"Daily segment: {segment}", "info")
    _write_cache(date_key, segments)
    return segments
