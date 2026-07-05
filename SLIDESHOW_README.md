# Station Cinema Slideshow - Setup

## What's new here
- `slideshow.html` - the actual slideshow to put on the second screen
- `slideshow.js` / `slideshow-config.js` - the logic and settings
- `upload.html` - passcode-gated page to upload videos from any device
- `scrape_schedule.py` - now also tracks which films are new this week
  (writes `seen_films.json` and `new_this_week.json` automatically)

## One-time setup tonight

1. **Create Supabase project** (done - "Station Video" project, bucket
   `slideshow-videos`, public, with an anon-upload policy in place)

2. **slideshow-config.js** is already filled in with the live Supabase
   URL and key. Passcode for uploads is `station2026` - change it in
   that file whenever you like.

3. **Base video** - `base-loop-v2.mp4` is already uploaded to the
   `base` folder in Supabase Storage. Swap it out any time via
   `upload.html` (choose "Replace the standing price list video").

4. **Deploy** `slideshow.html` and `upload.html` the same way as
   `index.html` (GitHub Pages / Netlify).

5. **Point the second screen's browser at `slideshow.html`.**

## Weekly - you do nothing
The existing GitHub Action already scrapes the schedule twice a week.
It now also updates `new_this_week.json`, which `slideshow.html` reads
to pull posters (via TMDB, same as the main board) for anything newly
listed in the last 7 days. Those poster slides just appear and disappear
on their own as films roll on/off the "new" window.

## Occasional - special event videos
Anyone with the passcode can go to `upload.html` on their phone or laptop,
choose "One-off / special event (uploads)", and drop a video in. It'll
show up in the slideshow rotation within 15 minutes (or immediately on
a manual refresh of the display).

## Notes
- Supabase free tier caps uploads at 50MB per file and 1GB total storage.
  The base loop was compressed to fit under that. Keep future uploads
  compressed too, and clear out old ones from the Supabase dashboard
  when they're no longer needed.
- The TMDB API key is reused from the existing Cinema Board setup.
