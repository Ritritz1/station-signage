/* ============================================================
   Slideshow carousel logic.
   Cycles through: base videos (from Supabase "base/" folder) ->
   new-this-week film posters (TMDB) -> uploaded videos (from
   Supabase "uploads/" folder) -> loop.
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

function lookupImages(title, cb) {
  tmdbFetch("/search/movie", { query: title, include_adult: false, region: "GB" }, function (s) {
    if (!s || !s.results || !s.results.length) return cb(null);
    var r = s.results[0];
    var today = new Date().toISOString().slice(0, 10);
    var isComingSoon = !!(r.release_date && r.release_date > today);
    cb({
      backdrop: r.backdrop_path || null,
      poster: r.poster_path || null,
      releaseDate: r.release_date || null,
      comingSoon: isComingSoon
    });
  });
}

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

async function loadNewFilmPosters() {
  var res = await fetch("new_this_week.json?_=" + Date.now()).catch(function () { return null; });
  if (!res || !res.ok) return [];
  var data = await res.json().catch(function () { return null; });
  if (!data || !data.films || !data.films.length) return [];

  var slides = [];
  for (var i = 0; i < data.films.length; i++) {
    var title = data.films[i];
    var images = await new Promise(function (resolve) { lookupImages(title, resolve); });
    if (images && (images.backdrop || images.poster)) {
      slides.push({
        type: "poster",
        title: title,
        backdropUrl: tmdbImageUrl(images.backdrop, 1280),
        posterUrl: tmdbImageUrl(images.poster, 500),
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

    var bg = document.createElement("img");
    bg.src = slide.backdropUrl || slide.posterUrl;
    bg.className = "slide-backdrop";
    wrap.appendChild(bg);

    var scrim = document.createElement("div");
    scrim.className = "slide-scrim";
    wrap.appendChild(scrim);

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

    if (slide.posterUrl) {
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
    var slide = slides[i];
    var vidEl = renderSlide(slide, container);
    if (slide.type === "video" && vidEl) {
      vidEl.onended = advance;
      vidEl.onerror = function () { setTimeout(advance, 3000); };
    } else {
      setTimeout(advance, window.SLIDE_DURATION_MS.poster || 10000);
    }
  }

  showCurrent();

  setInterval(async function () {
    var fresh = await buildSlideList();
    if (fresh.length) slides = fresh;
  }, 15 * 60 * 1000);
}

window.addEventListener("DOMContentLoaded", startSlideshow);
