/* ============================================================
Slideshow carousel logic.
Cycles through: base videos (from Supabase "base/" folder) ->
new-this-week film posters (TMDB, falling back to the cinema's own
website poster if TMDB has nothing OR its top match isn't confirmed
as the right film) -> uploaded videos (from Supabase "uploads/"
folder) -> loop.
============================================================ */

var supabaseClient = null;
function getSupabase() {
  if (supabaseClient) return supabaseClient;
  if (!window.supabase) return null;
  if (!window.SUPABASE_URL || window.SUPABASE_URL.indexOf("PASTE_YOUR") === 0) return null;
  supabaseClient = window.supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);
  return supabaseClient;
}

function tmdbImageUrl(path, w) {
  return path ? ("https://image.tmdb.org/t/p/w" + (w || 1280) + path) : "";
}

function tmdbFetch(pathSuffix, params, cb) {
  try {
    var key = window.TMDB_API_KEY || "";
    if (!key) return cb(null);
    var url = new URL("https://api.themoviedb.org/3" + pathSuffix);
    url.searchParams.set("api_key", key);
    if (window.TMDB_LANG) url.searchParams.set("language", window.TMDB_LANG);
    for (var k in (params || {})) url.searchParams.set(k, params[k]);
    fetch(url).then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) { cb(j); }).catch(function () { cb(null); });
  } catch (e) { cb(null); }
}

// Generic one-word titles (e.g. "Lady") can collide with a completely
// different film of the same name - there really are two unrelated
// 2025/2026 films both called "Lady". TMDb's top search hit is not
// guaranteed to be the one Station is actually showing, so when we know
// the real runtime (from the listings page), we check TMDb's candidates
// in order and only trust the first one whose runtime is close enough.
// Without a known runtime we fall back to the old "just trust the top
// hit" behaviour, since that's the best information available.
var RUNTIME_TOLERANCE_MINS = 3;

function lookupImages(title, expectedRuntimeMins, cb) {
  tmdbFetch("/search/movie", { query: title, include_adult: false, region: "GB" }, function (s) {
    if (!s || !s.results || !s.results.length) return cb(null);

    if (!expectedRuntimeMins) {
      return cb(resultToImages(s.results[0]));
    }

    var candidates = s.results.slice(0, 5);
    var idx = 0;
    function tryNext() {
      if (idx >= candidates.length) return cb(null); // no confirmed match - let caller fall back
      var candidate = candidates[idx++];
      tmdbFetch("/movie/" + candidate.id, {}, function (details) {
        var runtime = details && details.runtime;
        if (runtime && Math.abs(runtime - expectedRuntimeMins) <= RUNTIME_TOLERANCE_MINS) {
          cb(resultToImages(candidate));
        } else {
          tryNext();
        }
      });
    }
    tryNext();
  });
}

function resultToImages(r) {
  var today = new Date().toISOString().slice(0, 10);
  var isComingSoon = !!(r.release_date && r.release_date > today);
  return {
    backdrop: r.backdrop_path || null,
    poster: r.poster_path || null,
    releaseDate: r.release_date || null,
    comingSoon: isComingSoon
  };
}

/* ---- fallback poster source (the cinema's own website) ----
   event_codes.json (name kept for compatibility) maps
   {title: full poster image URL}, captured directly from the listings
   page by scrape_schedule.py - no URL-pattern guessing needed here. */

var _posterUrlsCache = null;

async function getStationPosterUrls() {
  if (_posterUrlsCache) return _posterUrlsCache;
  try {
    var res = await fetch("event_codes.json?_=" + Date.now(), { cache: "no-store" });
    _posterUrlsCache = res.ok ? await res.json().catch(function () { return {}; }) : {};
  } catch (e) {
    _posterUrlsCache = {};
  }
  return _posterUrlsCache;
}

// Confirms a URL actually loads as an image before we commit to using it as
// a slide (cheap - it's just an <img> load, not a fetch() call, so no CORS
// issues even though the image lives on another origin).
function verifyImageLoads(url) {
  return new Promise(function (resolve) {
    var img = new Image();
    img.onload = function () { resolve(url); };
    img.onerror = function () { resolve(null); };
    img.src = url;
  });
}

async function lookupStationFallback(title) {
  var urls = await getStationPosterUrls();
  var url = urls[title];
  if (!url) return null;
  var verified = await verifyImageLoads(url);
  if (!verified) return null;
  // Station website only gives us one image size/crop, so we use it as
  // both "backdrop" and "poster" - renderSlide() already handles a
  // poster-only slide gracefully (blurred full-bleed + no thumb).
  return { backdrop: null, poster: verified, isFallbackUrl: true, comingSoon: false };
}

/* ---- end fallback ---- */

async function listBucketFiles(folder) {
  var sb = getSupabase();
  if (!sb) return [];
  try {
    var { data, error } = await sb.storage.from(window.SUPABASE_BUCKET).list(folder, {
      sortBy: { column: "created_at", order: "desc" }
    });
    if (error || !data) return [];
    return data
      .filter(function (f) { return f.name && !f.name.startsWith("."); })
      .map(function (f) {
        var path = folder + "/" + f.name;
        var { data: pub } = sb.storage.from(window.SUPABASE_BUCKET).getPublicUrl(path);
        return pub.publicUrl;
      });
  } catch (e) {
    console.error("Supabase list error", e);
    return [];
  }
}

async function getExcludedTitles() {
  var sb = getSupabase();
  if (!sb) return [];
  try {
    var { data: pub } = sb.storage.from(window.SUPABASE_BUCKET).getPublicUrl("config/excluded_films.json");
    var res = await fetch(pub.publicUrl + "?_=" + Date.now(), { cache: "no-store" });
    if (!res.ok) return [];
    var json = await res.json().catch(function () { return null; });
    return (json && json.excluded) ? json.excluded.map(function (t) { return t.toLowerCase(); }) : [];
  } catch (e) {
    return [];
  }
}

async function loadNewFilmPosters() {
  var res = await fetch("new_this_week.json?_=" + Date.now()).catch(function () { return null; });
  if (!res || !res.ok) return [];
  var data = await res.json().catch(function () { return null; });
  if (!data || !data.films || !data.films.length) return [];

  var excluded = await getExcludedTitles();
  var titles = data.films.filter(function (t) { return excluded.indexOf(t.toLowerCase()) === -1; });
  var runtimes = data.runtimes || {};

  var slides = [];
  for (var i = 0; i < titles.length; i++) {
    var title = titles[i];
    var expectedRuntime = runtimes[title] || null;
    var images = await new Promise(function (resolve) {
      lookupImages(title, expectedRuntime, resolve);
    });

    // if TMDb had nothing usable (or nothing we could confirm was the
    // right film), try the cinema's own website poster
    if (!images || (!images.backdrop && !images.poster)) {
      images = await lookupStationFallback(title);
    }

    if (images && (images.backdrop || images.poster)) {
      slides.push({
        type: "poster",
        title: title,
        backdropUrl: images.isFallbackUrl ? "" : tmdbImageUrl(images.backdrop, 1280),
        posterUrl: images.isFallbackUrl ? images.poster : tmdbImageUrl(images.poster, 500),
        comingSoon: images.comingSoon
      });
    }
  }
  return slides;
}

async function buildSlideList() {
  var slides = [];

  var baseVideos = await listBucketFiles("base");
  baseVideos.forEach(function (url) { slides.push({ type: "video", url: url }); });

  var posterSlides = await loadNewFilmPosters();
  slides = slides.concat(posterSlides);

  var uploadedVideos = await listBucketFiles("uploads");
  uploadedVideos.forEach(function (url) { slides.push({ type: "video", url: url }); });

  return slides;
}

function renderSlide(slide, container) {
  container.innerHTML = "";
  if (slide.type === "video") {
    var vid = document.createElement("video");
    vid.src = slide.url;
    vid.autoplay = true;
    vid.muted = true;
    vid.playsInline = true;
    vid.className = "slide-video";
    container.appendChild(vid);
    return vid;
  } else {
    var wrap = document.createElement("div");
    wrap.className = "slide-poster-wrap";

    var hasBackdrop = !!slide.backdropUrl;
    var bgSrc = slide.backdropUrl || slide.posterUrl;

    var bg = document.createElement("img");
    bg.src = bgSrc;
    bg.className = "slide-backdrop" + (hasBackdrop ? "" : " blurred");
    wrap.appendChild(bg);

    var scrim = document.createElement("div");
    scrim.className = "slide-scrim";
    wrap.appendChild(scrim);

    if (!hasBackdrop && slide.posterUrl) {
      var centerPoster = document.createElement("img");
      centerPoster.src = slide.posterUrl;
      centerPoster.className = "slide-center-poster";
      wrap.appendChild(centerPoster);
    }

    var logo = document.createElement("img");
    logo.src = "logo.png";
    logo.className = "slide-logo";
    wrap.appendChild(logo);

    var label = document.createElement("div");
    label.className = "slide-new-badge" + (slide.comingSoon ? " coming-soon" : "");
    label.textContent = slide.comingSoon ? "COMING SOON" : "NEW THIS WEEK";
    wrap.appendChild(label);

    var footer = document.createElement("div");
    footer.className = "slide-footer";

    if (hasBackdrop && slide.posterUrl) {
      var thumb = document.createElement("img");
      thumb.src = slide.posterUrl;
      thumb.className = "slide-poster-thumb";
      footer.appendChild(thumb);
    }

    var title = document.createElement("div");
    title.className = "slide-title";
    title.textContent = slide.title;
    footer.appendChild(title);

    wrap.appendChild(footer);
    container.appendChild(wrap);
    return null;
  }
}

async function startSlideshow() {
  var container = document.getElementById("slide-container");
  var slides = await buildSlideList();

  if (!slides.length) {
    container.innerHTML = '<div class="slide-empty">No slides configured yet.<br>Add a base video in Supabase or check back once films are listed.</div>';
    return;
  }

  var i = 0;

  function advance() {
    i = (i + 1) % slides.length;
    showCurrent();
  }

  function showCurrent() {
    try {
      var slide = slides[i];
      if (!slide) { setTimeout(advance, 1000); return; }
      var vidEl = renderSlide(slide, container);
      if (slide.type === "video" && vidEl) {
        var advanced = false;
        var doAdvance = function () {
          if (advanced) return;
          advanced = true;
          advance();
        };
        vidEl.onended = doAdvance;
        vidEl.onerror = function () { setTimeout(doAdvance, 3000); };
        vidEl.addEventListener("loadedmetadata", function () {
          var ms = (isFinite(vidEl.duration) ? vidEl.duration : 180) * 1000 + 4000;
          setTimeout(doAdvance, ms);
        });
        setTimeout(doAdvance, 5 * 60 * 1000);
      } else {
        setTimeout(advance, window.SLIDE_DURATION_MS.poster || 10000);
      }
    } catch (e) {
      console.error("Slideshow render error, advancing anyway", e);
      setTimeout(advance, 2000);
    }
  }

  showCurrent();

  setInterval(async function () {
    var fresh = await buildSlideList();
    if (fresh.length) {
      slides = fresh;
      if (i >= slides.length) i = 0;
    }
  }, 15 * 60 * 1000);
}

window.addEventListener("DOMContentLoaded", startSlideshow);
