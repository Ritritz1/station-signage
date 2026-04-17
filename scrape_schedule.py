#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all
The page renders film titles in ALL CAPS, with dates and times on separate lines.

Structure per film:
  FILM TITLE (all caps)
  [blank]
   Running time: N mins
  [blank]
  [optional genre]
  [blank]
  Day DD Month YYYY
  HH:MM
  HH:MM
  Day DD Month YYYY
  HH:MM
  ...

Runs every Wednesday via GitHub Actions.
"""
import re, urllib.request
from datetime import datetime
from collections import defaultdict

URL = "https://www.stationcinema.com/whatson/all"

MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12
}
MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

# Title case mapping for known films (ALL CAPS -> proper case)
# Films where simple title-case doesn't work well
TITLE_FIXES = {
    "NT LIVE: ALL MY SONS": "NT Live: All My Sons",
    "NT LIVE: LES LIAISONS DANGEREUSES": "NT Live: Les Liaisons Dangereuses",
    "NT LIVE: THE PLAYBOY OF THE WESTERN WORLD": "NT Live: The Playboy of the Western World",
    "NT LIVE: THE AUDIENCE": "NT Live: The Audience",
    "RBO: THE MAGIC FLUTE": "RBO: The Magic Flute",
    "RBO: SIEGFRIED": "RBO: Siegfried",
    "MET OPERA: EUGENE ONEGIN": "MET Opera: Eugene Onegin",
    "EVGENIJ ONEGIN – TCHAIKOVSKY": "EVGENIJ ONEGIN – Tchaikovsky",
    "LOHENGRIN – WAGNER": "LOHENGRIN – Wagner",
    "COSI FAN TUTTE – MOZART": "Cosi Fan Tutte – Mozart",
    "EPIC: ELVIS PRESLEY IN CONCERT": "EPiC: Elvis Presley in Concert",
    "DOG FRIENDLY SCREENING: THE DEVIL WEARS PAW-DA 2": "Dog Friendly Screening: The Devil Wears Paw-da 2",
    "EXHIBITION ON SCREEN : FRIDA KAHLO": "Exhibition On Screen: FRIDA KAHLO",
    "EXHIBITION ON SCREEN: TURNER & CONSTABLE": "Exhibition On Screen: TURNER & CONSTABLE",
    "POWER TO THE PEOPLE: JOHN & YOKO LIVE IN NYC": "Power To The People: John & Yoko Live in NYC",
    "STAR WARS: THE MANDALORIAN AND GROGU": "Star Wars: The Mandalorian and Grogu",
    "A LIBERTY OF CONSCIENCE": "A Liberty of Conscience",
}

# Minor words that should stay lowercase in title case
MINOR = {"a","an","the","and","but","or","for","nor","on","at","to","by","in","of","up","as","is"}

def to_title(s):
    """Convert ALL CAPS film title to proper title case."""
    if s in TITLE_FIXES:
        return TITLE_FIXES[s]
    words = s.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in MINOR:
            # Preserve all-caps abbreviations like "NT", "RBO", "MET"
            if len(w) <= 3 and w.isupper() and w.isalpha():
                result.append(w)
            else:
                result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)

def fetch_page():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def strip_to_text(html):
    """Strip HTML to plain text."""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&amp;', '&', html)
    html = re.sub(r'&ndash;', '–', html)
    html = re.sub(r'&[a-z#0-9]+;', ' ', html)
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r' *\n *', '\n', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()

def extract_showtimes(html):
    text = strip_to_text(html)
    
    # Find the SHOWTIMES section (rendered page has it in all caps)
    start = text.upper().find('SHOWTIMES')
    end = text.find('Check Our Socials')
    if start == -1:
        print("ERROR: Could not find SHOWTIMES marker")
        print("First 500 chars of text:", text[:500])
        return {}
    body = text[start:end if end > start else len(text)]
    print(f"Showtimes section: {len(body)} chars")

    lines = [l.strip() for l in body.split('\n')]

    DATE_PAT = re.compile(
        r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|'
        r'August|September|October|November|December)'
        r'\s+(\d{4})$', re.IGNORECASE
    )
    TIME_PAT = re.compile(r'^\d{1,2}:\d{2}$')
    RT_PAT = re.compile(r'^Running time:', re.IGNORECASE)

    # Words/lines to skip that are not film titles
    SKIP = re.compile(
        r'^(Running time|SHOWTIMES|Now Showing|Coming Soon|Live Events|Senior|'
        r'Subtitled|Latest News|Membership|Private Hire|Gaming|Contact|Gift|'
        r'Get in Touch|Stay connected|About|FAQ|Telephone|Restoration|Charity|'
        r'RECEIVE|TikTok|Drama|Comedy|Music|Family|Adventure|Animation|Thriller|'
        r'Romance|Documentary|Biography|Musical|Theatre|Play|Opera|Nation|'
        r'Biopic|Science Fiction|Romantic|Fantasy|Teatro|Mins)',
        re.IGNORECASE
    )

    schedule = defaultdict(lambda: defaultdict(set))
    current_film = None
    current_date = None
    after_runtime = False

    for line in lines:
        if not line:
            continue

        # Running time line — marks end of title block, start of dates
        if RT_PAT.match(line):
            after_runtime = True
            continue

        # Date line
        dm = DATE_PAT.match(line)
        if dm:
            after_runtime = True
            day = int(dm.group(2))
            month = MONTHS.get(dm.group(3).lower(), 0)
            year = int(dm.group(4))
            if month:
                current_date = f"{year:04d}-{month:02d}-{day:02d}"
            continue

        # Time line
        if TIME_PAT.match(line) and current_film and current_date:
            schedule[current_date][current_film].add(line)
            continue

        # Skip known non-title lines
        if SKIP.match(line):
            after_runtime = False
            continue

        # If we hit a line that's ALL CAPS and not a date/time/genre,
        # it's a new film title
        if line == line.upper() and len(line) > 3 and not TIME_PAT.match(line) and not dm:
            # Reset state for new film
            current_film = to_title(line)
            current_date = None
            after_runtime = False
            print(f"  Film: {current_film}")
            continue

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
    print(f"Page fetched: {len(html)} chars")
    schedule = extract_showtimes(html)
    if not schedule:
        print("WARNING: No schedule data found — keeping existing schedule.js")
        raise SystemExit(1)
    total = sum(len(v) for v in schedule.values())
    print(f"Found {total} film/day combinations across {len(schedule)} days")
    output = render_js(schedule)
    with open("schedule.js", "w", encoding="utf-8") as f:
        f.write(output)
    print("schedule.js written successfully")
