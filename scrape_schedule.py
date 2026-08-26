#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all

APPROACH: Film titles are in <h1> tags. Dates and times follow each film block.
This completely avoids genre-line false positives.

CHANGE: also captures each film's poster image URL (the <img src="..."> that
appears immediately before its <h1> on the listings page) and writes it to
event_codes.json (kept that filename for compatibility, but it now stores
{title: full_poster_image_url} rather than a code).

FIX (v2): the listings page does NOT use /event/{code} links anywhere - that
pattern only exists on individual event detail pages. The actual poster image
is embedded directly, in one of two URL shapes depending on the film:
  https://stationcinema.admit-one.eu//sites/STATIONCINEMA/STATIONCINEMA/eventImages/{code}_{n}.jpg
  https://images.admit-one.eu//filmimages/small/{code}.jpg
(the eventImages suffix is a variable index like _0 or _1, not always _0).
We now match either shape directly and store the real, working image URL, so
slideshow.js doesn't need to guess/try multiple constructed URL patterns.
"""
import re, urllib.request, sys, json
from datetime import datetime
from collections import defaultdict

URL = "https://www.stationcinema.com/whatson/all"
MONTHS = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
MONTH_NAMES = ["January","February","March","April","May","June",
"July","August","September","October","November","December"]

# Matches the poster <img src="..."> in either of the two shapes the site uses.
POSTER_IMG_PAT = re.compile(
    r'src="([^"]*(?:eventImages/\d+_\d+\.jpg|filmimages/small/\d+\.jpg))"'
)
EVENT_LOOKBACK_CHARS = 1200  # how far before each <h1> to search for its poster image


def clean_title(s):
    """Clean up a film title - fix encoding and normalise."""
    s = s.strip()
    replacements = [
        ("\u00e2\u0080\u0099", "'"), ("\u00e2\u0080\u0098", "'"),
        ("\u00e2\u0080\u0093", "-"), ("\u00e2\u0080\u0094", "-"),
        ("\ufffd", "'"), ("\u00ef\u00bf\u00bd", "'"),
        ("\u00c3\u00a9", "\u00e9"), ("\u00c3\u00a8", "\u00e8"),
        ("\u00c3\u00a0", "\u00e0"), ("\u00c2\u00a0", " "),
    ]
    for old, new in replacements:
        s = s.replace(old, new)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def fetch_page():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    print(f"HTTP {resp.status}, {len(data)} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def extract_showtimes(html):
    soldout_idx = html.find('soldOutOverride')
    start = html.find('Showtimes', soldout_idx if soldout_idx > 0 else 0)
    if start == -1:
        print("ERROR: Cannot find Showtimes section")
        return {}, {}
    end = html.find('Check Our Socials', start)
    section = html[start:end if end > start else len(html)]
    print(f"Section: {len(section)} chars")

    h1_pat = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
    h1_matches = list(h1_pat.finditer(section))
    print(f"Found {len(h1_matches)} film titles (h1 tags)")

    DATE_PAT = re.compile(
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{4})',
        re.IGNORECASE
    )
    TIME_PAT = re.compile(r'\b(\d{1,2}:\d{2})\b')

    def strip_tags(s):
        s = re.sub(r'<[^>]+>', ' ', s)
        s = re.sub(r'&amp;', '&', s)
        s = re.sub(r'&ndash;|&#8211;', '-', s)
        s = re.sub(r'&[a-z#0-9]+;', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    schedule = defaultdict(lambda: defaultdict(set))
    poster_urls = {}

    for i, h1_match in enumerate(h1_matches):
        raw_title = strip_tags(h1_match.group(1))
        film = clean_title(raw_title)
        if not film or len(film) < 2:
            continue
        print(f"  Film: {film}")

        # --- find this film's poster image URL ---
        # The poster <img> sits immediately before this film's <h1> in the
        # listings markup. Take the last match in the lookback window (i.e.
        # the one closest to this h1), so we don't accidentally grab the
        # previous film's poster.
        lookback_start = max(0, h1_match.start() - EVENT_LOOKBACK_CHARS)
        lookback_chunk = section[lookback_start:h1_match.start()]
        img_matches = POSTER_IMG_PAT.findall(lookback_chunk)
        if img_matches and film not in poster_urls:
            url = img_matches[-1]
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = "https://www.stationcinema.com" + url
            poster_urls[film] = url
        # --- end ---

        block_start = h1_match.end()
        block_end = h1_matches[i+1].start() if i+1 < len(h1_matches) else len(section)
        block = section[block_start:block_end]
        block_text = strip_tags(block)

        seen = set()
        for dm in DATE_PAT.finditer(block_text):
            month = MONTHS.get(dm.group(3).lower(), 0)
            if not month:
                continue
            date_key = f"{int(dm.group(4)):04d}-{month:02d}-{int(dm.group(2)):02d}"
            time_start = dm.end()
            next_dm = DATE_PAT.search(block_text, time_start)
            time_end = next_dm.start() if next_dm else len(block_text)
            times = TIME_PAT.findall(block_text[time_start:time_end])
            key = (date_key, tuple(sorted(set(times))))
            if key not in seen and times:
                seen.add(key)
                for t in set(times):
                    schedule[date_key][film].add(t)

    return schedule, poster_urls


def is_uk_bank_holiday():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        req = urllib.request.Request(
            "https://www.gov.uk/bank-holidays.json",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        holidays = [e["date"] for e in data.get("england-and-wales", {}).get("events", [])]
        return today in holidays
    except Exception as e:
        print(f"Could not check bank holidays: {e}")
        return False


def render_js(schedule):
    lines = [
        "/* Auto-generated by scrape_schedule.py */",
        f"/* Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} */",
        "",
        "window.TMDB_OVERRIDES = window.TMDB_OVERRIDES || {};",
        'window.TMDB_OVERRIDES["The Stranger"] = { id: 1429348 };',
        'window.TMDB_OVERRIDES["The North"] = { id: 1434113 };',
        "",
        "window.SCHEDULE = {"
    ]
    for date_key in sorted(schedule.keys()):
        dt = datetime.strptime(date_key, "%Y-%m-%d")
        lines += [
            "", "  /* =======================",
            f"   * {dt.strftime('%A')} {dt.day} {MONTH_NAMES[dt.month-1]} {dt.year}",
            "   * ======================= */", f'  "{date_key}": ['
        ]
        for film, times_set in sorted(schedule[date_key].items()):
            ts = ", ".join(f'"{t}"' for t in sorted(times_set))
            lines.append(f'    {{ film: "{film}", times: [{ts}] }},')
        lines.append("  ],")
    lines += ["};", ""]
    return "\n".join(lines)


def update_new_this_week(schedule, seen_path="seen_films.json", new_path="new_this_week.json"):
    try:
        with open(seen_path, "r", encoding="utf-8") as f:
            seen = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        seen = {}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    all_titles = sorted({film for day in schedule.values() for film in day.keys()})

    for title in all_titles:
        if title not in seen:
            seen[title] = today

    with open(seen_path, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)

    cutoff = datetime.utcnow().timestamp() - 7 * 86400
    new_titles = [
        t for t, first_seen in seen.items()
        if t in all_titles and datetime.strptime(first_seen, "%Y-%m-%d").timestamp() >= cutoff
    ]

    with open(new_path, "w", encoding="utf-8") as f:
        json.dump({"generated": today, "films": sorted(new_titles)}, f, indent=2, ensure_ascii=False)

    print(f"New this week: {new_titles}")


def write_event_codes(poster_urls, path="event_codes.json"):
    """Writes {title: poster_image_url} for slideshow.js's TMDb-fallback poster."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(poster_urls, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(poster_urls)} poster URLs to {path}")


if __name__ == "__main__":
    today_weekday = datetime.utcnow().weekday()
    if today_weekday == 2 and is_uk_bank_holiday():
        print("Today is a UK bank holiday - skipping Wednesday scrape")
        sys.exit(0)

    print(f"Fetching {URL}")
    html = fetch_page()
    print(f"Page: {len(html)} chars")
    schedule, poster_urls = extract_showtimes(html)
    if not schedule:
        print("WARNING: No schedule data found")
        sys.exit(1)
    total = sum(len(v) for v in schedule.values())
    print(f"Found {total} showings across {len(schedule)} days")
    with open("schedule.js", "w", encoding="utf-8") as f:
        f.write(render_js(schedule))
    update_new_this_week(schedule)
    write_event_codes(poster_urls)
    print("Done")
