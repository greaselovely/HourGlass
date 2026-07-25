"""
Daily narration segments for the TTS intro.

Pulls two sources and has Claude turn both into speech-ready prose:

    Spaceflight News API  ->  "<news sentence> You can read more about this at <site>."
    NASA APOD             ->  "Today from NASA. <fact sentence>"

Both are returned as separate segments so the caller can insert a pause between
them. Every stage degrades rather than fails:

    news + NASA  ->  whichever one succeeded  ->  static curated pool  ->  nothing

An empty list just means the intro is the plain project description, exactly as
it was before this module existed.

Results are cached per-day, so re-running the video build (or a retry after a
crash) never re-spends an API call.
"""

import json
import os
import random
from datetime import datetime
from pathlib import Path
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

# Neutral framings that fit any of the fallback facts below.
FALLBACK_LEAD_INS = [
    "Something worth knowing about the sky above us.",
    "A note about the array you're watching.",
    "Here's what's remarkable about this place.",
    "One thought before the sun moves on.",
]

# Used when the network path fails, or before an Anthropic key is configured.
FALLBACK_FACTS = [
    "The Very Large Array's twenty-seven dishes ride on rails, spreading up to "
    "twenty-two miles across the desert to act as one enormous telescope.",
    "Each VLA antenna weighs about two hundred thirty tons, yet the array aligns "
    "them to within a fraction of a millimeter.",
    "At its widest configuration, the VLA can resolve detail fine enough to read "
    "a newspaper headline from nearly five hundred miles away.",
    "Radio telescopes like the VLA see through dust clouds that block visible "
    "light entirely, revealing stars still forming inside them.",
    "The VLA sits on the Plains of San Agustin at seven thousand feet, in a basin "
    "ringed by mountains that shield it from stray radio noise.",
    "It takes the VLA's antennas about an hour and a half to be moved into a new "
    "configuration, a task done roughly four times a year.",
    "The faint hiss of the cosmic microwave background is radiation left over from "
    "the universe's first four hundred thousand years.",
    "Jupiter is a powerful radio source, its magnetic field generating emissions "
    "strong enough to be detected from Earth with modest equipment.",
    "Fast radio bursts release more energy in a millisecond than the Sun does in "
    "three days, and most of their sources remain unidentified.",
    "The VLA helped confirm that the Milky Way's center hosts a supermassive black "
    "hole, now known as Sagittarius A-star.",
    "Pulsars spin so regularly that early observers half-seriously labeled the "
    "first one LGM-1, for Little Green Men.",
    "Because radio waves are far longer than light waves, radio telescopes must be "
    "enormous to match the sharpness of an optical one.",
    "Interstellar space contains complex molecules including alcohol and sugars, "
    "identified by the distinct radio frequencies they emit.",
    "The VLA appeared in the film Contact, though in reality it has never been "
    "used to search for extraterrestrial signals full-time.",
    "Combining the VLA with antennas across continents forms a virtual telescope "
    "effectively as wide as the Earth itself.",
]


# ============================================================================
# Cache
# ============================================================================

def _read_cache(date_key):
    try:
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        if cached.get("date") == date_key and cached.get("segments"):
            return cached["segments"]
    except (OSError, ValueError):
        pass
    return None


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

def _get_json(url, timeout=15):
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        message_processor(f"Fetch failed ({url.split('?')[0]}): {e}", "warning")
        return None


def _fetch_apod(api_key):
    """Fetch today's APOD. Returns (title, explanation) or (None, None)."""
    data = _get_json(f"{APOD_URL}?{urlencode({'api_key': api_key or 'DEMO_KEY'})}")
    if not data:
        return None, None
    return data.get("title"), data.get("explanation")


def _fetch_news():
    """Fetch the most recent spaceflight news article. Returns dict or None."""
    data = _get_json(f"{SNAPI_URL}?{urlencode({'limit': 1, 'ordering': '-published_at'})}")
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
   Lead with the most striking concrete detail, not with "Today's image shows".
   This sentence is spoken immediately after the words "Today from NASA.", so it
   must read naturally following that phrase."""

NARRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "news": {"type": "string"},
        "news_site": {"type": "string"},
        "fact": {"type": "string"},
    },
    "required": ["news", "news_site", "fact"],
    "additionalProperties": False,
}


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

    return {k: (data.get(k) or "").strip().strip('"').strip()
            for k in ("news", "news_site", "fact")}


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

    cached = _read_cache(date_key)
    if cached:
        for segment in cached:
            message_processor(f"Daily segment (cached): {segment}", "info")
        return cached

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
                segments.append(f"{NASA_PREFIX} {parts['fact']}")
        elif apod[0]:
            # Claude unavailable - the APOD title alone is still a real, dated fact.
            segments.append(f"{NASA_PREFIX} {apod[0]}.")

    if not segments:
        segments = [f"{random.choice(FALLBACK_LEAD_INS)} {random.choice(FALLBACK_FACTS)}"]
        message_processor("Using fallback fact (sources unavailable)", "warning")

    for segment in segments:
        message_processor(f"Daily segment: {segment}", "info")
    _write_cache(date_key, segments)
    return segments
