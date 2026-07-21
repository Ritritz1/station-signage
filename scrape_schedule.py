#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all

APPROACH: Film titles are in <h1> tags. Dates and times follow each film block.
This completely avoids genre-line false positives.
"""
import re, urllib.request, sys, json
from datetime import datetime
from collections import defaultdict

URL = "https://www.stationcinema.com/whatson/all"
MONTHS = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
          "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

def clean_title(s):
    """Clean up a film title - fix encoding and normalise."""
    s = s.strip()
    # Fix common encoding issues
    replacements = [
        ("\u00e2\u0080\u0099", "'"), ("\u00e2\u0080\u0098", "'"),
        ("\u00e2\u0080\u0093", "-"), ("\u00e2\u0080\u0094", "-"),
        ("\ufffd", "'"), ("\u00ef\u00bf\u00bd", "'"),
        ("\u00c3\u00a9", "\u00e9"), ("\u00c3\u00a8", "\u00e8"),
        ("\u00c3\u00a0", "\u00e0"), ("\u00c2\u00a0", " "),
    ]
    for old, new in replacements:
        s = s.replace(old, new)
    # Remove extra whitespace
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
    # Find the showtimes section
    soldout_idx = html.find('soldOutOverride')
    start = html.find('Showtimes', soldout_idx if soldout_idx > 0 else 0)
    if start == -1:
        print("ERROR: Cannot find Showtimes section")
        return {}
    end = html.find('Check Our Socials', start)
    section = html[start:end if end > start else len(html)]
    print(f"Section: {len(section)} chars")

    # Split on <h1> tags - each film starts with its title in an <h1>
    # Pattern: <h1 ...>FILM TITLE</h1> ... dates/times ... <h1>next film</h1>
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

    for i, h1_match in enumerate(h1_matches):
        raw_title = strip_tags(h1_match.group(1))
        film = clean_title(raw_title)
        if not film or len(film) < 2:
            continue
        print(f"  Film: {film}")

        # Get the block between this h1 and the next h1
        block_start = h1_match.end()
        block_end = h1_matches[i+1].start() if i+1 < len(h1_matches) else len(section)
        block = section[block_start:block_end]
        block_text = strip_tags(block)

        # Find all dates and their following times
        seen = set()
        for dm in DATE_PAT.finditer(block_text):
            month = MONTHS.get(dm.group(3).lower(), 0)
            if not month:
                continue
            date_key = f"{int(dm.group(4)):04d}-{month:02d}-{int(dm.group(2)):02d}"
            # Times follow the date until the next date
            time_start = dm.end()
            next_dm = DATE_PAT.search(block_text, time_start)
            time_end = next_dm.start() if next_dm else len(block_text)
            times = TIME_PAT.findall(block_text[time_start:time_end])
            key = (date_key, tuple(sorted(set(times))))
            if key not in seen and times:
                seen.add(key)
                for t in set(times):
                    schedule[date_key][film].add(t)

    return schedule

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

if __name__ == "__main__":
    today_weekday = datetime.utcnow().weekday()
    if today_weekday == 2 and is_uk_bank_holiday():
        print("Today is a UK bank holiday - skipping Wednesday scrape")
        sys.exit(0)

    print(f"Fetching {URL}")
    html = fetch_page()
    print(f"Page: {len(html)} chars")
    schedule = extract_showtimes(html)
    if not schedule:
        print("WARNING: No schedule data found")
        sys.exit(1)
    total = sum(len(v) for v in schedule.values())
    print(f"Found {total} showings across {len(schedule)} days")
    with open("schedule.js", "w", encoding="utf-8") as f:
        f.write(render_js(schedule))
    print("Done")
