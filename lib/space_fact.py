"""
Daily narration segments for the TTS intro.

Two segments are spoken after the project title, each written by Claude from
real source material:

    1. a radio-astronomy segment, rotated daily across four sources
    2. NASA APOD  ->  "Today from NASA. <fact sentence>"

Rotation keeps the intro from going stale and keeps any one feed from being
drained. The order advances by date, and a source that is unreachable or has
nothing new simply hands off to the next one in the rotation:

    nrao -> config -> arxiv -> solar -> nrao ...

The four sources, all verified reachable without credentials:

    nrao    NRAO science news RSS. Full article bodies, every item radio
            astronomy and most of them this array. Paginated, so once the
            recent stories are spoken it walks back through the archive.
    config  The VLA reconfigures three or four times a year, hauling antennas
            between one and thirty-six kilometres apart. This is the only
            source that describes what is actually on screen.
    arxiv   Four to eight fresh radio-astronomy papers a day.
    solar   NOAA 10.7 cm solar flux - a radio measurement of the Sun taken
            daily since 1947.

Every stage degrades rather than fails. An empty list just means the intro is
the plain project description, exactly as it was before this module existed.

Results are cached per-day, so re-running the video build (or a retry after a
crash) never re-spends an API call. The cache also remembers which articles and
papers have already been spoken, so they are never repeated.
"""

import html
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from .utils import message_processor

# SNAPI rejects the default Python-urllib agent with a 403, and the NRAO science
# site is no friendlier. A browser agent keeps every source happy.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

APOD_URL = "https://api.nasa.gov/planetary/apod"
NRAO_FEED_URL = "https://public.nrao.edu/news/feed/"
NRAO_CONFIG_URL = "https://science.nrao.edu/facilities/vla/proposing/configpropdeadlines"
ARXIV_URL = "https://export.arxiv.org/api/query"
SOLAR_URL = "https://services.swpc.noaa.gov/products/10cm-flux-30-day.json"

CACHE_FILE = Path(__file__).parent.parent / "cache" / "daily_fact.json"

NASA_PREFIX = "Today from NASA."

# Rotation order. Advances by date; a dud source falls through to the next.
SOURCES = ("nrao", "config", "arxiv", "solar")

# How far back through the NRAO archive to look for an unspoken story. Ten
# articles per page, so this is roughly 250 stories - years of material.
NRAO_MAX_PAGES = 25

# Remembering every id forever would grow the cache without bound, and an
# article that fell off the back of this list is old enough to be worth hearing
# again anyway.
SEEN_LIMIT = 400

# arXiv gets a radio-specific filter; the plain astro-ph firehose is mostly
# optical and would defeat the point.
ARXIV_QUERY = (
    '(cat:astro-ph.GA OR cat:astro-ph.HE OR cat:astro-ph.CO OR cat:astro-ph.SR) AND '
    '(abs:"radio telescope" OR abs:"Very Large Array" OR abs:"radio observations" OR '
    'abs:"fast radio burst" OR abs:pulsar OR abs:VLBI OR abs:"radio emission")'
)

# A large share of radio papers are about technique rather than about the sky,
# and they narrate terribly - "classifiers work best when images are cropped to
# a fixed number of beams" is true, on topic, and worthless to a listener. Skip
# them in favour of a paper that found something.
ARXIV_METHODS = re.compile(
    r"\b(pipeline|software|algorithm|classif\w*|machine learning|deep learning|"
    r"neural network|calibrat\w*|data reduction|imaging technique|benchmark|"
    r"toolkit|framework|method(?:s|ology)?|simulat\w*)\b", re.IGNORECASE)

# Published NRAO figures for each array configuration, so the narration can be
# concrete about what the antennas on screen are currently doing.
CONFIG_FACTS = {
    "A": "the most spread out arrangement, antennas out to thirty-six kilometres apart, "
         "giving the sharpest possible detail but the least sensitivity to faint extended glow",
    "B": "a middling arrangement, antennas out to eleven kilometres apart",
    "C": "a fairly compact arrangement, antennas out to three point four kilometres apart",
    "D": "the most compact arrangement, all antennas within about one kilometre of the centre, "
         "best for seeing faint extended structure but with the least fine detail",
}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


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


def _seen(cache, kind):
    """Ids already spoken for one source. Always a list, even on a fresh cache."""
    seen = cache.get("seen")
    if not isinstance(seen, dict):
        return []
    got = seen.get(kind)
    return got if isinstance(got, list) else []


def _write_cache(cache, date_key, segments, spoken_kind=None, spoken_id=None):
    """Persist today's segments, carrying the seen-id history forward."""
    seen = cache.get("seen")
    seen = dict(seen) if isinstance(seen, dict) else {}
    if spoken_kind and spoken_id:
        ids = [i for i in _seen(cache, spoken_kind) if i != spoken_id]
        ids.append(spoken_id)
        seen[spoken_kind] = ids[-SEEN_LIMIT:]
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"date": date_key, "segments": segments, "seen": seen}, f)
    except OSError:
        pass


# ============================================================================
# Fetch helpers
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


def _get(url, timeout=15):
    """Fetch a URL as text. Returns (text, status); status is None for non-HTTP errors."""
    endpoint = url.split("?")[0]
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), resp.status
    except HTTPError as e:
        message_processor(
            f"Fetch failed ({endpoint}): HTTP {e.code} {_error_detail(e)}", "warning")
        return None, e.code
    except Exception as e:
        message_processor(f"Fetch failed ({endpoint}): {e}", "warning")
        return None, None


def _get_json(url, timeout=15):
    """Fetch JSON. Returns (data, status); status is None for non-HTTP errors."""
    text, status = _get(url, timeout)
    if text is None:
        return None, status
    try:
        return json.loads(text), status
    except ValueError as e:
        message_processor(f"Bad JSON ({url.split('?')[0]}): {e}", "warning")
        return None, status


def _strip_html(markup):
    """Turn a chunk of feed HTML into plain prose for the prompt."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _tag(markup, name):
    """First value of an XML tag, CDATA unwrapped. '' when absent."""
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", markup, re.S)
    if not m:
        return ""
    value = m.group(1).strip()
    cdata = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", value, re.S)
    return (cdata.group(1) if cdata else value).strip()


# ============================================================================
# Sources
# ============================================================================

def _fetch_nrao(seen_ids):
    """Newest NRAO science story not yet spoken, walking back through the archive."""
    skipped = 0
    for page in range(1, NRAO_MAX_PAGES + 1):
        url = NRAO_FEED_URL if page == 1 else f"{NRAO_FEED_URL}?paged={page}"
        text, _ = _get(url, timeout=20)
        if not text:
            break
        items = re.findall(r"<item>(.*?)</item>", text, re.S)
        if not items:
            break
        for item in items:
            guid = _tag(item, "guid") or _tag(item, "link")
            title = _strip_html(_tag(item, "title"))
            if not guid or not title:
                continue
            if guid in seen_ids:
                skipped += 1
                continue
            body = _strip_html(_tag(item, "content:encoded") or _tag(item, "description"))
            if len(body) < 200:
                continue
            if skipped:
                message_processor(
                    f"NRAO: skipped {skipped} already-spoken stories", "info")
            return {
                "kind": "nrao",
                "id": guid,
                "label": "NRAO radio astronomy news",
                "material": f"Headline: {title}\n\nArticle: {body[:4000]}",
            }
    message_processor("NRAO: no unspoken story found", "warning")
    return None


def _parse_config_rows(markup):
    """Every (start, end, configuration) row of the VLA configuration table."""
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", markup, re.S):
        cells = [_strip_html(c) for c in
                 re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 3 or not re.fullmatch(r"[ABCD]", cells[2]) or "-" not in cells[1]:
            continue
        start, _, end = cells[1].partition("-")
        start, end = _parse_day(start), _parse_day(end)
        if start and end:
            rows.append((start, end, cells[2]))
    rows.sort()
    return rows


def _parse_day(value):
    """'2026 July 10' / '2026 Jul 10' -> date. None if it does not parse."""
    m = re.match(r"(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})", value.strip())
    if not m:
        return None
    month = MONTHS.get(m.group(2)[:3].lower())
    if not month:
        return None
    try:
        return date(int(m.group(1)), month, int(m.group(3)))
    except ValueError:
        return None


def _fetch_config(_seen_ids=None):
    """Which configuration the array is in today, and what changes next."""
    text, _ = _get(NRAO_CONFIG_URL, timeout=25)
    if not text:
        return None
    rows = _parse_config_rows(text)
    if not rows:
        message_processor("VLA config: could not parse the schedule table", "warning")
        return None

    today = date.today()
    current = next(((s, e, c) for s, e, c in rows if s <= today <= e), None)
    upcoming = next(((s, e, c) for s, e, c in rows if s > today), None)

    if current:
        start, end, cfg = current
        state = (f"The array is in its {cfg} configuration, which is "
                 f"{CONFIG_FACTS.get(cfg, 'one of its four antenna arrangements')}. "
                 f"It has been in this arrangement since {start:%B %-d} and holds it "
                 f"until {end:%B %-d}.")
    elif upcoming:
        start, _, cfg = upcoming
        state = (f"The antennas are being moved between configurations right now. "
                 f"The next arrangement is {cfg} configuration, "
                 f"{CONFIG_FACTS.get(cfg, 'one of four')}, starting {start:%B %-d}.")
    else:
        return None

    if upcoming:
        state += (f" Next it moves to {upcoming[2]} configuration on "
                  f"{upcoming[0]:%B %-d}, which is "
                  f"{CONFIG_FACTS.get(upcoming[2], 'a different spacing')}.")

    return {
        "kind": "config",
        "id": None,  # deliberately not deduped - it is a status, not a story
        "label": "the current physical configuration of this array",
        "material": state,
    }


def _fetch_arxiv(seen_ids):
    """Most recent radio-astronomy preprint not yet spoken."""
    query = urlencode({
        "search_query": ARXIV_QUERY,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 40,
    })
    text, _ = _get(f"{ARXIV_URL}?{query}", timeout=25)
    if not text:
        return None

    def candidates():
        for entry in re.findall(r"<entry>(.*?)</entry>", text, re.S):
            paper_id = _tag(entry, "id")
            title = _strip_html(_tag(entry, "title"))
            summary = _strip_html(_tag(entry, "summary"))
            if not paper_id or not title or len(summary) < 200:
                continue
            if paper_id in seen_ids:
                continue
            yield paper_id, title, summary

    # Prefer a paper that found something. Fall back to a methods paper only if
    # the whole batch is technique - Claude still gets to reject it downstream.
    picks = list(candidates())
    chosen = next((p for p in picks if not ARXIV_METHODS.search(p[1])), None)
    if not chosen and picks:
        message_processor("arXiv: only methods papers available today", "info")
        chosen = picks[0]
    if not chosen:
        message_processor("arXiv: no unspoken paper found", "warning")
        return None

    paper_id, title, summary = chosen
    return {
        "kind": "arxiv",
        "id": paper_id,
        "label": "a brand new radio astronomy research paper",
        "material": f"Title: {title}\n\nAbstract: {summary[:3000]}",
    }


def _fetch_solar(_seen_ids=None):
    """Today's 10.7 cm solar radio flux, with a month of context."""
    data, _ = _get_json(SOLAR_URL, timeout=20)
    if not isinstance(data, list) or not data:
        return None
    try:
        values = [float(d["flux"]) for d in data if d.get("flux") is not None]
        latest = values[-1]
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if not values:
        return None

    average = sum(values) / len(values)
    trend = ("above" if latest > average * 1.1 else
             "below" if latest < average * 0.9 else "close to")
    return {
        "kind": "solar",
        "id": None,  # a daily measurement, not a one-off story
        "label": "today's solar radio flux measurement",
        "material": (
            f"The ten point seven centimetre solar radio flux measured today is "
            f"{latest:.0f} solar flux units. Over the past thirty days it has ranged "
            f"from {min(values):.0f} to {max(values):.0f}, averaging {average:.0f}, so "
            f"today's reading is {trend} the recent average. This number is itself a "
            f"radio astronomy measurement: a radio telescope has measured the Sun's "
            f"output at a wavelength of ten point seven centimetres every day since "
            f"1947, and it tracks how active the Sun currently is."),
    }


FETCHERS = {
    "nrao": _fetch_nrao,
    "config": _fetch_config,
    "arxiv": _fetch_arxiv,
    "solar": _fetch_solar,
}


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


def _pick_source(rotation, seen_lookup):
    """Walk the rotation from today's starting point until a source yields material."""
    start = date.today().toordinal() % len(rotation)
    for offset in range(len(rotation)):
        kind = rotation[(start + offset) % len(rotation)]
        fetcher = FETCHERS.get(kind)
        if not fetcher:
            continue
        try:
            found = fetcher(seen_lookup(kind))
        except Exception as e:
            message_processor(f"Source '{kind}' failed: {e}", "warning")
            continue
        if found:
            if offset:
                message_processor(
                    f"Source '{kind}' used after {offset} in the rotation came up empty",
                    "info")
            return found
    return None


# ============================================================================
# Claude
# ============================================================================

PROMPT = """You are writing narration for the opening of a daily time-lapse video
filmed at the Very Large Array radio observatory in New Mexico. Everything you
return is read aloud by a text-to-speech voice, over footage of the array's
radio antennas.

For every field: use plain prose, no markdown, quotes, parentheses, brackets or
bullet points, and spell out all numerals, symbols and abbreviations as words
(for example "VLBI" becomes "very long baseline interferometry", and "36 km"
becomes "thirty-six kilometres").

=== TODAY'S RADIO ASTRONOMY SOURCE: {source_label} ===
{source_material}

=== TODAY'S NASA ASTRONOMY PICTURE OF THE DAY ===
Title: {apod_title}
{apod_explanation}

Return three fields:

1. segment - ONE sentence of at most {max_words} words carrying the single most
   interesting thing in the radio astronomy source above.

   This must be worth listening to on its own. The listener gets no link, no
   follow-up and no picture, so a sentence that only announces that something
   exists is a failure. These are the ways it fails:
   - reporting that nothing has happened, or that something is still unknown,
     unscheduled, delayed or awaiting a decision
   - restating a headline instead of saying what was actually found
   - telling the listener where to read more, or naming the publication
   - vague scale words with no content: major, significant, groundbreaking
   - a statement about technique rather than about the sky. How data was
     processed, cropped, smoothed, calibrated or classified is not interesting
     to a listener watching antennas at dusk; what the sky turned out to be
     doing is.
   Say the finding, the number, or the physical thing. If a team measured
   something, say what they measured and what it turned out to be.

   Never mention the source, the publication, the authors, or that this is news
   or a paper. Just state the astronomy.

2. segment_usable - true if that sentence genuinely stands alone and is worth
   hearing. Return false when today's source has no real substance in it - a
   procedural announcement, a staffing item, an outreach event, a paper whose
   result cannot be stated without heavy jargon. Returning false is correct and
   expected on those days; the segment is simply left out rather than spoken as
   something hollow. In particular, return false when the only result on offer
   is about method or data processing and nothing can be said about the sky
   itself. Do not force it.

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
   expected on those days. Do not force it."""

NARRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "segment": {"type": "string"},
        "segment_usable": {"type": "boolean"},
        "fact": {"type": "string"},
        "fact_usable": {"type": "boolean"},
    },
    "required": ["segment", "segment_usable", "fact", "fact_usable"],
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

# The exact failure that killed the old spaceflight-news feed: a sentence whose
# entire content is that nothing has happened yet, or that points elsewhere.
HOLLOW = re.compile(
    r"\b(no (?:launch )?date|not yet been (?:set|announced|scheduled)|"
    r"remains? (?:unclear|unknown|undecided|to be seen)|"
    r"has (?:not|n't) (?:yet )?been (?:set|announced|determined)|"
    r"you can read more|read more about|for more information|"
    r"according to (?:the )?(?:report|article|paper|study))\b", re.IGNORECASE)


def _write_narration(source, apod, api_key, model, max_words):
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
                    source_label=(source or {}).get("label", "(none available)"),
                    source_material=(source or {}).get("material", "(none available)"),
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
             for k in ("segment", "fact")}
    parts["segment_usable"] = bool(data.get("segment_usable"))
    parts["fact_usable"] = bool(data.get("fact_usable"))
    return parts


# ============================================================================
# Public entry point
# ============================================================================

def get_daily_segments(config):
    """
    Return the narration segments that follow the project title.

    Each element is spoken as its own segment, separated by a pause. At most two:
    today's rotated radio-astronomy segment, then the NASA fact. Returns [] to
    skip the whole thing.

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
    rotation = tuple(s for s in fact_cfg.get("sources", SOURCES) if s in FETCHERS)
    source = _pick_source(rotation, lambda k: _seen(cache, k)) if rotation else None
    if source:
        message_processor(f"Radio segment source today: {source['kind']}", "info")
    apod = _fetch_apod(fact_cfg.get("nasa_api_key", ""))

    segments = []
    spoken_id = None
    if source or apod[0]:
        parts = _write_narration(
            source, apod,
            api_key=fact_cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"),
            model=fact_cfg.get("model", "claude-opus-5"),
            max_words=max_words,
        )
        if parts:
            if source and parts["segment"]:
                if not parts["segment_usable"]:
                    message_processor(
                        f"Source '{source['kind']}' had no substance today - skipping "
                        f"that segment", "info")
                elif HOLLOW.search(parts["segment"]):
                    message_processor(
                        f"Segment said nothing worth hearing - skipping: {parts['segment']}",
                        "warning")
                else:
                    segments.append(parts["segment"])
                    spoken_id = source.get("id")
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

        # Claude unavailable. The APOD title is still a real, dated fact worth
        # speaking; the raw source material is not - it is a whole article.
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
    _write_cache(cache, date_key, segments,
                 spoken_kind=source["kind"] if source and spoken_id else None,
                 spoken_id=spoken_id)
    return segments
