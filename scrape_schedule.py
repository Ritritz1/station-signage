#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all

Raw HTML structure (after stripping tags):
  Showtimes
  Film Title (mixed case, exact)
  Running time: N mins
  [optional genre]
  Day DD Month YYYY HH:MM HH:MM Day DD Month YYYY HH:MM ...  <- all on ONE line
  [duplicate of above line]
  Next Film Title
  ...
"""
import re, urllib.request, sys
from datetime import datetime
from collections import defaultdict

URL = "https://www.stationcinema.com/whatson/all"
MONTHS = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
          "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

def fetch_page():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        print(f"HTTP {resp.status}, {len(data)} bytes")
        return data.decode("utf-8", errors="replace")

def strip_html(html):
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S)
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.S)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&amp;', '&', html)
    html = re.sub(r'&ndash;|&#8211;', '-', html)
    html = re.sub(r'&[a-z#0-9]+;', ' ', html)
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'[ ]*[\r\n]+[ ]*', '\n', html)
    html = re.sub(r'\n{2,}', '\n', html)
    return html.strip()

def parse_date_time_line(line):
    """
    Parse a line like:
    'Friday 17 April 2026 13:30 19:30 Saturday 18 April 2026 16:30 19:30'
    Returns dict: {date_key: [times]}
    """
    result = defaultdict(set)
    # Split by day names to get chunks per date
    day_pat = re.compile(
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{4})'
        r'((?:\s+\d{1,2}:\d{2})*)',
        re.IGNORECASE
    )
    for m in day_pat.finditer(line):
        month = MONTHS.get(m.group(3).lower(), 0)
        if not month:
            continue
        date_key = f"{int(m.group(4)):04d}-{month:02d}-{int(m.group(2)):02d}"
        times = re.findall(r'\d{1,2}:\d{2}', m.group(5))
        for t in times:
            result[date_key].add(t)
    return result

def extract_showtimes(html):
    # Find the showtimes section - after soldOutOverride CSS
    soldout_idx = html.find('soldOutOverride')
    showtimes_idx = html.find('Showtimes', soldout_idx if soldout_idx > 0 else 0)
    if showtimes_idx == -1:
        print("ERROR: Cannot find Showtimes section")
        return {}

    # End at footer
    end_markers = ['Check Our Socials', 'About Us', 'Restoration Levy']
    end_idx = len(html)
    for marker in end_markers:
        idx = html.find(marker, showtimes_idx)
        if idx > 0:
            end_idx = min(end_idx, idx)

    section = html[showtimes_idx:end_idx]
    text = strip_html(section)
    print(f"Section: {len(text)} chars")

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print(f"Lines: {len(lines)}")

    # Patterns
    RT_PAT = re.compile(r'^Running time:', re.I)
    DATE_LINE_PAT = re.compile(
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+\d{1,2}\s+'
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d{4}',
        re.I
    )
    GENRE_WORDS = {
        'drama','comedy','music','family','adventure','animation','thriller',
        'romance','documentary','biography','musical','theatre','play','opera',
        'fantasy','biopic','action','mystery','science','fiction','romantic',
        'teatro','nation','live','mins','running'
    }
    SKIP_LINES = {'showtimes','check our socials','about us','stay connected','tiktok'}

    schedule = defaultdict(lambda: defaultdict(set))
    current_film = None
    seen_date_lines = set()  # to deduplicate the repeated blocks

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip known non-film lines
        if line.lower() in SKIP_LINES:
            i += 1
            continue

        # Skip Running time lines
        if RT_PAT.match(line):
            i += 1
            continue

        # Date+time line
        if DATE_LINE_PAT.search(line):
            # Deduplicate - page repeats each date block twice
            if line not in seen_date_lines and current_film:
                seen_date_lines.add(line)
                date_times = parse_date_time_line(line)
                for date_key, times in date_times.items():
                    for t in times:
                        schedule[date_key][current_film].add(t)
            i += 1
            continue

        # Skip pure genre lines
        words = set(re.sub(r'[^a-z, ]', '', line.lower()).split())
        words.discard('')
        if words and words.issubset(GENRE_WORDS):
            i += 1
            continue

        # Skip very short fragments
        if len(line) < 3:
            i += 1
            continue

        # Must be a film title
        current_film = line
        seen_date_lines = set()  # reset dedup for new film
        print(f"  Film: {current_film}")
        i += 1

    return schedule

def render_js(schedule):
    lines = [
        "/* Auto-generated by scrape_schedule.py */",
        f"/* Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} */",
        "",
        "window.TMDB_OVERRIDES = window.TMDB_OVERRIDES || {};",
        'window.TMDB_OVERRIDES["The Stranger"] = { id: 1429348 };',
        "",
        "window.SCHEDULE = {"
    ]
    for date_key in sorted(schedule.keys()):
        dt = datetime.strptime(date_key, "%Y-%m-%d")
        lines += [
            "",
            "  /* =======================",
            f"   * {dt.strftime('%A')} {dt.day} {MONTH_NAMES[dt.month-1]} {dt.year}",
            "   * ======================= */",
            f'  "{date_key}": ['
        ]
        for film, times_set in sorted(schedule[date_key].items()):
            ts = ", ".join(f'"{t}"' for t in sorted(times_set))
            lines.append(f'    {{ film: "{film}", times: [{ts}] }},')
        lines.append("  ],")
    lines += ["};", ""]
    return "\n".join(lines)

if __name__ == "__main__":
    print(f"Fetching {URL}")
    html = fetch_page()
    print(f"Page: {len(html)} chars")
    schedule = extract_showtimes(html)
    if not schedule:
        print("WARNING: No schedule data found — keeping existing schedule.js")
        sys.exit(1)
    total = sum(len(v) for v in schedule.values())
    print(f"Found {total} showings across {len(schedule)} days")
    with open("schedule.js", "w", encoding="utf-8") as f:
        f.write(render_js(schedule))
    print("Done")
