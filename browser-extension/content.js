// Shows an IDM-style "Download this video" button on the video you are watching.
(() => {
  if (window.__vdInjected) return;
  window.__vdInjected = true;

  const MIN_W = 200, MIN_H = 112;
  let target = null;           // the <video> the button is attached to
  let hovered = null;          // video under the mouse
  const dismissed = new WeakSet();

  // ---- the button lives in a shadow root so page styles can't break it
  const host = document.createElement("div");
  host.style.cssText = "all:initial;position:fixed;z-index:2147483647;top:0;left:0;display:none;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      .wrap{display:flex;align-items:center;gap:2px;font:600 13px/1 "Segoe UI",system-ui,-apple-system,sans-serif}
      .b{display:flex;align-items:center;gap:7px;background:#FF6A13;color:#fff;border:0;border-radius:9px 0 0 9px;
         padding:8px 11px 8px 9px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);font:inherit}
      .b:hover{background:#E85D0C}
      .x{background:#FF6A13;color:#fff;border:0;border-radius:0 9px 9px 0;padding:8px 8px;cursor:pointer;
         box-shadow:0 4px 14px rgba(0,0,0,.35);font:inherit;opacity:.9}
      .x:hover{background:#c94c06}
      svg{width:16px;height:16px;flex:none}
    </style>
    <div class="wrap">
      <button class="b" title="Choose a quality and download">
        <svg viewBox="0 0 24 24" fill="#fff"><path d="M10.5 3h3v8.5h3.2L12 17l-4.7-5.5h3.2zM4 17h2.5v2.5h11V17H20v5H4z"/></svg>
        <span>Download this video</span>
      </button>
      <button class="x" title="Hide for this video">✕</button>
    </div>`;
  const btn = root.querySelector(".b");
  const close = root.querySelector(".x");
  (document.body || document.documentElement).appendChild(host);

  // small message in the bottom-right corner (separate element: the button host moves around)
  const toastHost = document.createElement("div");
  toastHost.style.cssText = "all:initial;position:fixed;z-index:2147483647;right:20px;bottom:24px;display:none;";
  const troot = toastHost.attachShadow({ mode: "closed" });
  troot.innerHTML = `<style>.t{background:#1F1F23;color:#F4F4F5;border-left:4px solid #FF6A13;padding:12px 16px;
      border-radius:10px;font:500 13px/1.45 "Segoe UI",system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.4);
      width:max-content;max-width:340px}</style><div class="t"></div>`;
  (document.body || document.documentElement).appendChild(toastHost);
  function toast(msg) {
    troot.querySelector(".t").textContent = msg;
    toastHost.style.display = "block";
    clearTimeout(toast.t);
    toast.t = setTimeout(() => { toastHost.style.display = "none"; }, 3500);
  }

  function visibleArea(r) {
    const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    return w * h;
  }

  function pick() {
    let best = null, score = 0;
    for (const v of document.querySelectorAll("video")) {
      if (dismissed.has(v)) continue;
      const r = v.getBoundingClientRect();
      if (r.width < MIN_W || r.height < MIN_H) continue;
      let s = visibleArea(r);
      if (s < MIN_W * MIN_H * 0.5) continue;
      if (!v.paused && !v.ended) s += 1e9;          // playing wins
      else if (v === hovered) s += 1e8;             // then the one under the mouse
      else if (v.currentTime > 0) s += 1e6;         // then one that has played
      if (s > score) { score = s; best = v; }
    }
    return best;
  }

  function place() {
    if (document.fullscreenElement) { host.style.display = "none"; return; }
    target = pick();
    if (!target) {
      host.style.display = "none";
      return;
    }
    const r = target.getBoundingClientRect();
    const wrap = root.querySelector(".wrap");
    wrap.style.display = "flex";
    host.style.display = "block";
    const bw = wrap.offsetWidth || 190;
    const top = Math.max(8, Math.min(r.top + 12, innerHeight - 50));
    const left = Math.max(8, Math.min(r.right - bw - 12, innerWidth - bw - 8));
    host.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
  }

  // ---- work out the link of the video being watched
  const STRONG = /\/(reel|reels)\/|\/videos\/|\/watch\/?\?v=|[?&]v=|\/status\/|\/video\/|\/p\/|\/tv\/|\/shorts\//;
  const WEAK = /story\.php|story_fbid|\/permalink|\/posts\//;
  function videoLink(v) {
    const here = location.href;
    if (/youtube\.com\/(watch|shorts\/|live\/|embed\/)|youtu\.be\//.test(here)) return here;
    // Look for the post's own link close to the video (feeds: Facebook, Instagram, X…).
    // Stop before reaching containers much bigger than the video, so we never grab a neighbour's link.
    const vr = v.getBoundingClientRect();
    let el = v, weak = "";
    for (let i = 0; i < 25 && el; i++) {
      el = el.parentElement;
      if (!el || el === document.body) break;
      const r = el.getBoundingClientRect();
      if (r.height > vr.height * 3.2 || r.width > vr.width * 2.6) break;
      for (const a of el.querySelectorAll("a[href]")) {
        const h = a.href || "";
        if (/\/hashtag\/|\/photo|\/groups\/[^/]+\/?$/.test(h)) continue;
        if (STRONG.test(h)) return h;
        if (!weak && WEAK.test(h)) weak = h;
      }
    }
    return weak || here;
  }

  function caption(v) {
    let el = v;
    for (let i = 0; i < 12 && el; i++) {
      el = el.parentElement;
      if (!el) break;
      const t = el.querySelector('[dir="auto"], h1, h2, h3, [data-ad-preview="message"]');
      if (t && t.innerText && t.innerText.trim().length > 8) return t.innerText.trim().split("\n")[0].slice(0, 120);
    }
    return document.title;
  }

  btn.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    if (!target) return;
    const src = target.currentSrc && /^https?:/.test(target.currentSrc) ? target.currentSrc : "";
    const data = { url: videoLink(target), page: location.href, src, title: caption(target) };
    if (window.top === window && window.__vdPanel) {
      window.__vdPanel.open(data);                     // quality picker right here on the page
    } else {
      chrome.runtime.sendMessage({ type: "to-top", data }, () => void chrome.runtime.lastError);
    }
  }, true);

  close.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    if (target) dismissed.add(target);
    place();
  }, true);

  document.addEventListener("mouseover", (e) => {
    const x = e.clientX, y = e.clientY;
    hovered = null;
    for (const v of document.querySelectorAll("video")) {
      const r = v.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) { hovered = v; break; }
    }
  }, { passive: true, capture: true });

  addEventListener("scroll", place, { passive: true, capture: true });
  addEventListener("resize", place, { passive: true });
  document.addEventListener("play", place, true);
  document.addEventListener("fullscreenchange", place);
  setInterval(place, 700);
  place();
})();
