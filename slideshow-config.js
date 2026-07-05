/* ============================================================
   Fill these in once you've created your Supabase project.
   Settings -> API in the Supabase dashboard gives you both.
   The anon/public key is safe to expose in client-side code -
   that's what it's designed for, as long as your bucket policies
   are set correctly (public read, and we lock writes down in
   upload.html with a passcode).
   ============================================================ */
window.SUPABASE_URL = "https://tavagotcasshxxepsmhb.supabase.co";
window.SUPABASE_ANON_KEY = "sb_publishable_5N1Wb8-jWL5lUBTVyWb6yg_YCHP6hQi";
window.SUPABASE_BUCKET = "slideshow-videos";

/* Reused from the existing Cinema Board */
window.TMDB_API_KEY = "1ac6070606f4a415fccbfbcbb78fe224";
window.TMDB_LANG = "en-GB";

/* How long each slide stays on screen (ms) */
window.SLIDE_DURATION_MS = {
  video: null,   // videos play to completion, then advance
  poster: 10000  // film poster slides show for 10s each
};

/* Simple passcode gate for the upload page - NOT real security,
   just stops randoms from finding the page and uploading junk.
   Change this to whatever you like. */
window.UPLOAD_PASSCODE = "station2026";
