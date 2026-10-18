/* MovieList frontend helpers.
   All Kodi-sourced strings are inserted via textContent (never innerHTML). */
(function () {
  "use strict";

  var MovieList = window.MovieList || (window.MovieList = {});

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function buildCard(item, kind) {
    var col = el("div", "col-6 col-sm-4 col-md-3 col-lg-2 mb-4");
    var a = el("a", "media-card d-block text-decoration-none");
    a.href = item.url;
    var img = el("img");
    img.src = item.poster;
    img.alt = item.title || "";
    img.loading = "lazy";
    img.width = 300;
    img.height = 450;
    a.appendChild(img);
    var body = el("div", "p-2 text-center");
    var h6 = el("h6", "mb-0 text-truncate", item.title);
    h6.title = item.title || "";
    body.appendChild(h6);
    var meta = el("div", "small-text");
    var parts = [];
    if (item.year) parts.push(String(item.year));
    if (item.rating) parts.push("★ " + Number(item.rating).toFixed(1));
    if (kind === "show") {
      parts.push(item.season_count + " season" + (item.season_count === 1 ? "" : "s"));
      parts.push(item.episode_count + " ep" + (item.episode_count === 1 ? "" : "s"));
    }
    meta.textContent = parts.join(" · ");
    if (item.rating) meta.className = "small-text";
    body.appendChild(meta);
    a.appendChild(body);
    col.appendChild(a);
    return col;
  }

  MovieList.initGrid = function () {
    var grid = document.getElementById("media-grid");
    if (!grid) return;
    var sentinel = document.getElementById("scroll-sentinel");
    var api = grid.dataset.api;
    var kind = grid.dataset.kind || "movie";
    var nextPage = parseInt(grid.dataset.nextPage || "", 10);
    if (!api || !nextPage) return;
    var loading = false;

    function loadMore() {
      if (loading || !nextPage) return;
      loading = true;
      if (sentinel) sentinel.classList.add("loading");
      var params = new URLSearchParams();
      if (grid.dataset.q) params.set("q", grid.dataset.q);
      if (grid.dataset.genre) params.set("genre", grid.dataset.genre);
      if (grid.dataset.sort) params.set("sort", grid.dataset.sort);
      params.set("page", String(nextPage));
      fetch(api + "?" + params.toString())
        .then(function (resp) {
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          return resp.json();
        })
        .then(function (data) {
          (data.items || []).forEach(function (item) {
            grid.appendChild(buildCard(item, kind));
          });
          if (data.has_next) {
            nextPage = data.page + 1;
            grid.dataset.nextPage = String(nextPage);
          } else {
            nextPage = null;
            grid.dataset.nextPage = "";
            if (observer) observer.disconnect();
          }
        })
        .catch(function () { /* leave remaining pages for a manual reload */ })
        .then(function () {
          loading = false;
          if (sentinel) sentinel.classList.remove("loading");
        });
    }

    var observer = null;
    if ("IntersectionObserver" in window && sentinel) {
      observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) loadMore();
        });
      }, { rootMargin: "400px" });
      observer.observe(sentinel);
    }
  };

  function buildEpisode(ep, root) {
    var li = el("li", "episode-item row g-3");
    var thumbCol = el("div", "col-4 col-sm-3 col-md-2");
    var img = el("img", "episode-thumb img-fluid");
    img.src = root + "/art/episode/" + ep.id + "/thumb";
    img.alt = "";
    img.loading = "lazy";
    thumbCol.appendChild(img);
    li.appendChild(thumbCol);

    var body = el("div", "col-8 col-sm-9 col-md-10");
    var head = el("div", "episode-head");
    if (ep.season != null && ep.episode != null) {
      var pad = function (n) { return n < 10 ? "0" + n : String(n); };
      head.appendChild(el("span", "badge bg-secondary me-2",
        "S" + pad(ep.season) + "E" + pad(ep.episode)));
    }
    head.appendChild(el("strong", null, ep.title));
    if (ep.rating) {
      head.appendChild(el("span", "rating small", " ★ " + Number(ep.rating).toFixed(1)));
    }
    body.appendChild(head);
    if (ep.firstaired) {
      body.appendChild(el("div", "small-text mb-1", "Aired " + ep.firstaired));
    }
    if (ep.plot) {
      body.appendChild(el("p", "episode-plot mb-0", ep.plot));
    }
    li.appendChild(body);
    return li;
  }

  MovieList.initSeasons = function () {
    var pills = document.getElementById("season-pills");
    var list = document.getElementById("episode-list");
    if (!pills || !list) return;
    var apiBase = pills.dataset.apiBase;
    var root = list.dataset.root || "";

    pills.addEventListener("click", function (event) {
      var button = event.target.closest(".season-pill");
      if (!button) return;
      var season = button.dataset.season;
      pills.querySelectorAll(".season-pill").forEach(function (btn) {
        btn.classList.remove("btn-primary");
        btn.classList.add("btn-outline-secondary");
      });
      button.classList.add("btn-primary");
      button.classList.remove("btn-outline-secondary");
      list.innerHTML = "";
      list.appendChild(el("p", "text-secondary", "Loading…"));
      fetch(apiBase + "/" + encodeURIComponent(season))
        .then(function (resp) {
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          return resp.json();
        })
        .then(function (data) {
          list.innerHTML = "";
          var episodes = data.episodes || [];
          if (!episodes.length) {
            list.appendChild(el("p", "text-secondary mb-0",
              "No episodes are cataloged for this season."));
            return;
          }
          var ol = el("ol", "list-unstyled episode-list");
          episodes.forEach(function (ep) { ol.appendChild(buildEpisode(ep, root)); });
          list.appendChild(ol);
        })
        .catch(function () {
          list.innerHTML = "";
          list.appendChild(el("p", "text-secondary mb-0",
            "Could not load episodes. Please try again."));
        });
    });
  };
})();
