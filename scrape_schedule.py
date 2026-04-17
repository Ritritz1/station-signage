#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all
"""
import re, urllib.request, urllib.error, sys
from datetime import datetime
from collections import defaultdict

URL = "https://www.stationcinema.com/whatson/all"
MONTHS = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
          "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]
MINOR = {"a","an","the","and","but","or","for","nor","on","at","to","by","in","of","up","as","is"}
TITLE_FIXES = {
    "NT LIVE: ALL MY SONS": "NT Live: All My Sons",
    "NT LIVE: LES LIAISONS DANGEREUSES": "NT Live: Les Liaisons Dangereuses",
    "NT LIVE: THE PLAYBOY OF THE WESTERN WORLD": "NT Live: The Playboy of the Western World",
    "NT LIVE: THE AUDIENCE": "NT Live: The Audience",
    "RBO: THE MAGIC FLUTE": "RBO: The Magic Flute",
    "RBO: SIEGFRIED": "RBO: Siegfried",
    "MET OPERA: EUGENE ONEGIN": "MET Opera: Eugene Onegin",
    "DOG FRIENDLY SCREENING: THE DEVIL WEARS PAW-DA 2": "Dog Friendly Screening: The Devil Wears Paw-da 2",
    "EXHIBITION ON SCREEN : FRIDA KAHLO": "Exhibition On Screen: FRIDA KAHLO",
    "EXHIBITION ON SCREEN: FRIDA KAHLO": "Exhibition On Screen: FRIDA KAHLO",
    "EXHIBITION ON SCREEN: TURNER & CONSTABLE": "Exhibition On Screen: TURNER & CONSTABLE",
    "POWER TO THE PEOPLE: JOHN & YOKO LIVE IN NYC": "Power To The People: John & Yoko Live in NYC",
    "STAR WARS: THE MANDALORIAN AND GROGU": "Star Wars: The Mandalorian and Grogu",
    "A LIBERTY OF CONSCIENCE": "A Liberty of Conscience",
    "EPIC: ELVIS PRESLEY IN CONCERT": "EPiC: Elvis Presley in Concert",
}

def to_title(s):
    if s in TITLE_FIXES:
        return TITLE_FIXES[s]
    words = s.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in MINOR:
            if re.match(r'^[A-Z]{1,3}$', w):
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
        return data.decode("utf-8", errors="replace")

def extract_showtimes(html):
    # The page has "Showtimes" in the nav menu AND in the main content
    # We want the LAST occurrence which is the actual listings
    # Better: use the soldOutOverride CSS class as a reliable marker
    # that only appears in the listings section
    
    # Find all "Showtimes" positions
    positions = [m.start() for m in re.finditer(r'Showtimes', html, re.IGNORECASE)]
    print(f"Found 'Showtimes' at positions: {positions}")
    
    if not positions:
        print("ERROR: No Showtimes marker found")
        return {}
    
    # The listings section Showtimes is after the soldOutOverride CSS
    # Use the LAST occurrence of Showtimes
    start = positions[-1]
    print(f"Using last Showtimes at position {start}")
    
    # Also try to find it after the soldOut CSS block
    soldout_idx = html.find('soldOutOverride')
    if soldout_idx > 0:
        # Find the next Showtimes after the soldOut CSS
        for pos in positions:
            if pos > soldout_idx:
                start = pos
                print(f"Using Showtimes after soldOut CSS at position {start}")
                break
    
    # Strip from this position to "Check Our Socials"
    section = html[start:]
    end = section.find('Check Our Socials')
    if end > 0:
        section = section[:end]
    
    # Strip HTML
    section = re.sub(r'<script[^>]*>.*?</script>', '', section, flags=re.S)
    section = re.sub(r'<style[^>]*>.*?</style>', '', section, flags=re.S)
    section = re.sub(r'<br\s*/?>', '\n', section, flags=re.I)
    section = re.sub(r'<[^>]+>', ' ', section)
    section = re.sub(r'&amp;', '&', section)
    section = re.sub(r'&ndash;|&#8211;|\u2013', '-', section)
    section = re.sub(r'&[a-z#0-9]+;', ' ', section)
    section = re.sub(r'[ \t]+', ' ', section)
    section = re.sub(r' *\n *', '\n', section)
    section = re.sub(r'\n{3,}', '\n\n', section)
    section = section.strip()
    
    print(f"Section length: {len(section)} chars")
    
    lines = [l.strip() for l in section.split('\n') if l.strip()]
    print(f"Lines: {len(lines)}")
    # Print first 20 lines for debug
    for i, l in enumerate(lines[:20]):
        print(f"  L{i}: {repr(l)}")

    DATE_PAT = re.compile(
        r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{4})$', re.IGNORECASE)
    TIME_PAT = re.compile(r'^\d{1,2}:\d{2}$')
    GENRE_WORDS = {'drama','comedy','music','family','adventure','animation','thriller',
                   'romance','documentary','biography','musical','theatre','play','opera',
                   'fantasy','biopic','action','mystery','science','fiction','sci-fi',
                   'teatro','nation','romantic','mins','live'}

    schedule = defaultdict(lambda: defaultdict(set))
    current_film = None
    current_date = None

    for line in lines:
        if not line or re.match(r'^Running time:', line, re.I):
            continue

        dm = DATE_PAT.match(line)
        if dm:
            month = MONTHS.get(dm.group(3).lower(), 0)
            if month:
                current_date = f"{int(dm.group(4)):04d}-{month:02d}-{int(dm.group(2)):02d}"
            continue

        if TIME_PAT.match(line):
            if current_film and current_date:
                schedule[current_date][current_film].add(line)
            continue

        # Skip pure genre lines
        words_lower = set(re.sub(r'[^a-z ]', '', line.lower()).split())
        if words_lower and words_lower.issubset(GENRE_WORDS | {''}):
            continue

        # ALL CAPS = film title
        alpha = re.sub(r'[^a-zA-Z]', '', line)
        if alpha and alpha == alpha.upper() and len(line) > 2:
            new_film = to_title(line)
            if new_film != current_film:
                current_film = new_film
                current_date = None
                print(f"  Film: {current_film}")

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
        lines += ["", "  /* =======================",
                  f"   * {dt.strftime('%A')} {dt.day} {MONTH_NAMES[dt.month-1]} {dt.year}",
                  "   * ======================= */", f'  "{date_key}": [']
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
