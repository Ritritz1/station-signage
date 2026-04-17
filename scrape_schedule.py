#!/usr/bin/env python3
"""
Scrapes https://www.stationcinema.com/whatson/all
Film titles appear in ALL CAPS. Dates and times are on separate lines.
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
        core = re.sub(r'[^A-Z]', '', w)
        if i == 0 or w.lower() not in MINOR:
            if len(core) <= 3 and w == w.upper() and w.isalpha():
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
        "Accept-Language": "en-GB,en;q=0.5",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            print(f"HTTP status: {resp.status}, bytes: {len(data)}")
            return data.decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"ERROR fetching page: {e}")
        return ""

def strip_to_text(html):
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&amp;', '&', html)
    html = re.sub(r'&ndash;|&#8211;', '-', html)
    html = re.sub(r'&[a-z#0-9]+;', ' ', html)
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r' *\n *', '\n', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()

def extract_showtimes(html):
    if not html:
        print("ERROR: Empty page")
        return {}

    text = strip_to_text(html)
    print(f"Stripped text length: {len(text)}")

    # Find the SHOWTIMES section - the page renders it as "SHOWTIMES" in all caps
    # Try multiple possible markers
    body = None
    for marker in ['SHOWTIMES\n', 'Showtimes\n', 'SHOWTIMES ', 'Showtimes ']:
        idx = text.find(marker)
        if idx != -1:
            print(f"Found marker '{marker.strip()}' at position {idx}")
            body = text[idx:]
            break

    if body is None:
        # Try to find by looking for the first "Running time:" occurrence
        idx = text.find('Running time:')
        if idx != -1:
            print(f"Using 'Running time:' as start marker at position {idx}")
            # Go back to find the film title before it
            body = text[max(0, idx-500):]
        else:
            print("ERROR: Cannot find SHOWTIMES or Running time: in page")
            print("Text sample (first 1000 chars):")
            print(text[:1000])
            return {}

    end = body.find('Check Our Socials')
    if end != -1:
        body = body[:end]
    print(f"Body section: {len(body)} chars")

    lines = [l.strip() for l in body.split('\n')]
    print(f"Total lines: {len(lines)}")

    DATE_PAT = re.compile(
        r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{4})$', re.IGNORECASE)
    TIME_PAT = re.compile(r'^\d{1,2}:\d{2}$')
    RT_PAT = re.compile(r'Running time:', re.IGNORECASE)
    SKIP_PAT = re.compile(
        r'^(Running time|SHOWTIMES|Showtimes|Now Showing|Coming Soon|Live Events|Senior|'
        r'Subtitled|Latest News|Membership|Private Hire|Gaming|Contact|Gift|'
        r'Get in Touch|Stay connected|About|FAQ|Telephone|Restoration|Charity|'
        r'RECEIVE|TikTok|Check Our)$', re.IGNORECASE)
    # Pure genre lines (no dates or times)
    GENRE_WORDS = {'drama','comedy','music','family','adventure','animation','thriller',
                   'romance','documentary','biography','musical','theatre','play','opera',
                   'fantasy','biopic','nation','teatro','action','mystery','science'}

    schedule = defaultdict(lambda: defaultdict(set))
    current_film = None
    current_date = None

    for line in lines:
        if not line:
            continue
        if RT_PAT.search(line):
            continue
        if SKIP_PAT.match(line):
            continue

        # Date line
        dm = DATE_PAT.match(line)
        if dm:
            month = MONTHS.get(dm.group(3).lower(), 0)
            if month:
                current_date = f"{int(dm.group(4)):04d}-{month:02d}-{int(dm.group(2)):02d}"
            continue

        # Time line
        if TIME_PAT.match(line):
            if current_film and current_date:
                schedule[current_date][current_film].add(line)
            continue

        # Genre line — skip lines that are pure genre words
        words_lower = set(line.lower().replace(',', ' ').split())
        if words_lower and words_lower.issubset(GENRE_WORDS | {'','fiction','sci-fi'}):
            continue

        # ALL CAPS line = new film title
        # Check: mostly uppercase letters (allow punctuation, &, numbers, spaces)
        alpha_chars = re.sub(r'[^a-zA-Z]', '', line)
        if alpha_chars and alpha_chars == alpha_chars.upper() and len(line) > 2:
            new_film = to_title(line)
            if new_film != current_film:
                current_film = new_film
                current_date = None
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
    if not html:
        print("WARNING: No schedule data found — keeping existing schedule.js")
        sys.exit(1)
    print(f"Page fetched: {len(html)} chars")
    schedule = extract_showtimes(html)
    if not schedule:
        print("WARNING: No schedule data found — keeping existing schedule.js")
        sys.exit(1)
    total = sum(len(v) for v in schedule.values())
    print(f"Found {total} film/day combinations across {len(schedule)} days")
    output = render_js(schedule)
    with open("schedule.js", "w", encoding="utf-8") as f:
        f.write(output)
    print("schedule.js written successfully")
