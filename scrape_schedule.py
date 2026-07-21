#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all

KEY INSIGHT: In the raw HTML, each film block looks like:
  <element>FILM TITLE</element>
  <element>Running time: N mins</element>
  <element>Genre, Genre</element>  <- optional, ignored
  <element>Day DD Month YYYY</element>
  <element>HH:MM</element>
  ...repeated dates/times...

We use regex on the raw HTML to extract (title, running_time) pairs,
then find dates and times in the HTML block that follows each film.
This completely avoids the genre-line problem.
"""
import re, urllib.request, sys, json
from datetime import datetime
from collections import defaultdict

URL = "https://www.stationcinema.com/whatson/all"
MONTHS = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
          "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

TITLE_FIXES = {
    "NT LIVE: ALL MY SONS": "NT Live: All My Sons",
    "NT LIVE: LES LIAISONS DANGEREUSES": "NT Live: Les Liaisons Dangereuses",
    "NT LIVE: THE PLAYBOY OF THE WESTERN WORLD": "NT Live: The Playboy of the Western World",
    "NT LIVE: THE AUDIENCE": "NT Live: The Audience",
    "NT LIVE: THE MISANTHROPE": "NT Live: The Misanthrope",
    "RBO: THE MAGIC FLUTE": "RBO: The Magic Flute",
    "RBO: SIEGFRIED": "RBO: Siegfried",
    "MET OPERA: EUGENE ONEGIN": "MET Opera: Eugene Onegin",
    "MET OPERA 26/27: COSI FAN TUTTE": "Met Opera 26/27: Cosi Fan Tutte",
    "DOG FRIENDLY SCREENING: MOANA": "Dog Friendly Screening: Moana",
    "DOG FRIENDLY SCREENING: THE DEVIL WEARS PAW-DA 2": "Dog Friendly Screening: The Devil Wears Paw-da 2",
    "EXHIBITION ON SCREEN : FRIDA KAHLO": "Exhibition On Screen: FRIDA KAHLO",
    "EXHIBITION ON SCREEN: FRIDA KAHLO": "Exhibition On Screen: FRIDA KAHLO",
    "EXHIBITION ON SCREEN: TURNER & CONSTABLE": "Exhibition On Screen: TURNER & CONSTABLE",
    "EXHIBITION ON SCREEN: JAMES MCNEIL WHISTLER": "Exhibition On Screen: James McNeil Whistler",
    "POWER TO THE PEOPLE: JOHN & YOKO LIVE IN NYC": "Power To The People: John & Yoko Live in NYC",
    "STAR WARS: THE MANDALORIAN AND GROGU": "Star Wars: The Mandalorian and Grogu",
    "SPIDER-MAN: BRAND NEW DAY": "Spider-Man: Brand New Day",
    "WHAM! 10 DAYS IN CHINA": "WHAM! 10 Days in China",
    "SHARE A CAN FOR SHREK": "Share a Can for Shrek",
    "COSI FAN TUTTE  MOZART": "Cosi Fan Tutte - Mozart",
    "ANDRE RIEU'S 2026 SUMMER CONCERT: VIVA MAASTRICHT!": "Andre Rieu's 2026 Summer Concert: Viva Maastricht!",
    "ANDRE RIEU\u2019S 2026 SUMMER CONCERT: VIVA MAASTRICHT!": "Andre Rieu's 2026 Summer Concert: Viva Maastricht!",
}
MINOR = {"a","an","the","and","but","or","for","nor","on","at","to","by","in","of","up","as","is","de","van","la","le"}

def to_title(s):
    s = s.strip()
    if s in TITLE_FIXES:
        return TITLE_FIXES[s]
    words = s.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in MINOR:
            if re.match(r'^[A-Z]{1,3}[!]?$', w):
                result.append(w)
            else:
                result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)

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

    # Split section on "Running time:" — each split gives us:
    # [0] = preamble with film title at the end
    # [1..] = genre + dates/times block
    parts = re.split(r'Running time:[^<]*', section)
    print(f"Film blocks: {len(parts)-1}")

    # Date+time pattern in raw HTML (dates and times are separate tags)
    DATE_PAT = re.compile(
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{4})',
        re.IGNORECASE
    )
    TIME_PAT = re.compile(r'\b(\d{1,2}:\d{2})\b')

    # HTML tag strip
    def strip(s):
        s = re.sub(r'<[^>]+>', ' ', s)
        s = re.sub(r'&amp;', '&', s)
        s = re.sub(r'&ndash;|&#8211;|\u2013', '-', s)
        s = re.sub(r'&[a-z#0-9]+;', ' ', s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    schedule = defaultdict(lambda: defaultdict(set))

    for i, part in enumerate(parts):
        if i == 0:
            continue  # preamble before first film

        # Film title: last non-empty text node in the PREVIOUS part
        prev = parts[i-1]
        # Strip HTML tags from previous part to get text
        prev_text = strip(prev)
        # The film title is the last meaningful chunk
        # Split by newlines/sentences and take the last non-trivial one
        candidates = [c.strip() for c in re.split(r'[\n\r]+|(?<=[.!?])\s+', prev_text) if c.strip()]
        film_raw = None
        for c in reversed(candidates):
            if len(c) < 2:
                continue
            film_raw = c
            break

        if not film_raw:
            continue

        # Clean up: remove any trailing numbers or short fragments
        film_raw = re.sub(r'\s+\d+\s*$', '', film_raw).strip()
        if len(film_raw) < 2:
            continue

        film = to_title(film_raw)
        print(f"  Film: {film}")

        # Dates and times are in the current part (after Running time:)
        # The page duplicates each date block twice — use a set to deduplicate
        block_text = strip(part)
        seen_dates = set()
        current_date = None

        # Parse line by line
        block_lines = [l.strip() for l in block_text.split() if l.strip()]
        # Reconstruct into date/time chunks
        # Find all dates in this block
        for dm in DATE_PAT.finditer(block_text):
            month = MONTHS.get(dm.group(3).lower(), 0)
            if not month:
                continue
            date_key = f"{int(dm.group(4)):04d}-{month:02d}-{int(dm.group(2)):02d}"
            # Find times that follow this date (before next date)
            date_end = dm.end()
            next_date = DATE_PAT.search(block_text, date_end)
            next_pos = next_date.start() if next_date else len(block_text)
            time_chunk = block_text[date_end:next_pos]
            times = TIME_PAT.findall(time_chunk)
            key = (date_key, frozenset(times))
            if key not in seen_dates and times:
                seen_dates.add(key)
                for t in times:
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
