// Quality picker shown on the page itself (like IDM): pick a quality, the PC app downloads it in the
// background, progress shows here, and Windows shows a notification when it's done.
(() => {
  if (window.__vdPanel || window.top !== window) return;   // only on the main page, not inside frames

  const LOGO = `<svg viewBox="0 0 108 108" width="22" height="22"><rect x="4" y="4" width="100" height="100" rx="24" fill="#FF6A13"/>
    <path fill="#fff" d="M47 22h14v28h12L54 71 35 50h12zM27 66h9v10h36V66h9v20H27z"/></svg>`;
  const DL = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M10.5 3h3v8.5h3.2L12 17l-4.7-5.5h3.2zM4 17h2.5v2.5h11V17H20v5H4z"/></svg>`;

  const host = document.createElement("div");
  host.style.cssText = "all:initial;position:fixed;z-index:2147483647;top:72px;right:18px;display:none;";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
  <style>
    *{box-sizing:border-box}
    .p{width:min(370px,calc(100vw - 36px));max-height:calc(100vh - 100px);display:flex;flex-direction:column;
       background:#18181B;color:#F4F4F5;border:1px solid #2C2C32;border-radius:16px;overflow:hidden;
       box-shadow:0 18px 48px rgba(0,0,0,.45);font:13px/1.4 "Segoe UI",system-ui,-apple-system,sans-serif;
       animation:in .18s ease-out}
    @keyframes in{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
    .hd{display:flex;align-items:center;gap:10px;padding:12px 12px 12px 16px;border-bottom:1px solid #2C2C32}
    .hd b{flex:1;font-size:14px}
    .ib{border:0;background:#26262B;color:#F4F4F5;width:30px;height:30px;border-radius:15px;cursor:pointer;font:15px/1 inherit}
    .ib:hover{background:#5A1F1F}
    .bd{overflow:auto;padding:14px 16px 16px}
    .bd::-webkit-scrollbar{width:8px}.bd::-webkit-scrollbar-thumb{background:#2C2C32;border-radius:4px}
    .muted{color:#A1A1AA}.dim{color:#71717A}.good{color:#34D399}.bad{color:#F87171}
    .center{text-align:center;padding:26px 6px}
    .spin{width:34px;height:34px;border:3px solid #2C2C32;border-top-color:#FF6A13;border-radius:50%;margin:0 auto 14px;
          animation:sp 0.8s linear infinite}
    @keyframes sp{to{transform:rotate(360deg)}}
    .top{display:flex;gap:12px;margin-bottom:12px}
    .thumb{width:120px;height:68px;border-radius:10px;background:#26262B center/cover no-repeat;flex:none;position:relative}
    .dur{position:absolute;right:5px;bottom:5px;background:rgba(0,0,0,.8);color:#fff;font-size:11px;padding:1px 5px;border-radius:5px}
    .t{font-weight:600;font-size:13.5px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
    .tabs{display:flex;background:#1F1F23;border-radius:10px;padding:3px;margin:4px 0 10px}
    .tab{flex:1;border:0;background:transparent;color:#A1A1AA;padding:7px;border-radius:8px;cursor:pointer;font:600 13px inherit}
    .tab.on{background:#FF6A13;color:#fff}
    .q{display:flex;align-items:center;gap:10px;width:100%;border:1px solid #2C2C32;background:transparent;color:#F4F4F5;
       border-radius:10px;padding:10px 12px;margin-bottom:6px;cursor:pointer;font:inherit;text-align:left}
    .q:hover{border-color:#FF6A13;background:#3A1E0C}
    .q .l{flex:1;font-weight:600}.q .s{color:#A1A1AA;font-size:12px}
    .q .d{color:#FF6A13;display:flex}
    .chk{display:flex;align-items:center;gap:8px;margin:2px 0 10px;color:#D4D4D8;cursor:pointer}
    .chk input{accent-color:#FF6A13;width:15px;height:15px}
    .sec{font-weight:700;font-size:12px;color:#A1A1AA;text-transform:uppercase;letter-spacing:.04em;margin:14px 0 8px}
    .job{background:#1F1F23;border-radius:12px;padding:10px 12px;margin-bottom:8px}
    .job .row{display:flex;align-items:center;gap:8px}
    .job .n{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .bar{height:6px;background:#2C2C32;border-radius:3px;margin:8px 0 6px;overflow:hidden}
    .bar i{display:block;height:100%;width:0;background:#FF6A13;border-radius:3px;transition:width .4s}
    .bar.done i{background:#34D399}
    .acts{display:flex;gap:6px;margin-top:8px}
    .btn{border:0;border-radius:9px;padding:8px 12px;cursor:pointer;font:600 12.5px inherit;background:#26262B;color:#F4F4F5}
    .btn:hover{background:#34343B}
    .btn.pr{background:#FF6A13;color:#fff}.btn.pr:hover{background:#E85D0C}
    .ft{padding:10px 16px;border-top:1px solid #2C2C32;display:flex;justify-content:space-between;align-items:center}
    .lnk{border:0;background:none;color:#FF6A13;cursor:pointer;font:inherit;padding:0}
    .lnk:hover{text-decoration:underline}
  </style>
  <div class="p">
    <div class="hd">${LOGO}<b>Video Downloader</b><button class="ib" id="x" title="Close (downloads keep going)">✕</button></div>
    <div class="bd" id="bd"></div>
    <div class="ft"><span class="dim" id="ftl">Saved by the app on your PC</span><button class="lnk" id="app">Open in app</button></div>
  </div>`;
  (document.body || document.documentElement).appendChild(host);
  const $ = (id) => root.getElementById(id);
  const bd = $("bd");

  let current = null;    // {data, info}
  let tab = "video";
  const jobs = [];       // {id, label, title, st}
  let poll = null;

  const esc = (s) => String(s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const size = (n) => !n ? "" : n >= 1073741824 ? (n / 1073741824).toFixed(2) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.round(n / 1024) + " KB";
  const time = (s) => { s = Math.round(s || 0); if (!s) return ""; const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
  const send = (msg) => new Promise((res) => {
    try { chrome.runtime.sendMessage(msg, (r) => res(chrome.runtime.lastError ? { ok: false, error: chrome.runtime.lastError.message } : (r || { ok: false }))); }
    catch (e) { res({ ok: false, error: String(e) }); }
  });

  function show() { host.style.display = "block"; }
  function hide() { host.style.display = "none"; }
  $("x").addEventListener("click", hide);
  addEventListener("keydown", (e) => { if (e.key === "Escape" && host.style.display === "block") hide(); }, true);
  $("app").addEventListener("click", () => { if (current) send({ type: "add", data: current.data }); hide(); });

  function loading(text, sub) {
    bd.innerHTML = `<div class="center"><div class="spin"></div><div style="font-weight:600">${esc(text)}</div>
      <div class="dim">${esc(sub || "")}</div></div>`;
  }

  function error(msg, retry) {
    bd.innerHTML = `<div class="center"><div style="font-size:30px" class="bad">⚠</div>
      <div style="margin:8px 0 14px">${esc(msg)}</div>
      ${retry ? '<button class="btn pr" id="retry">Try again</button>' : ""}</div>`;
    if (retry) root.getElementById("retry").addEventListener("click", retry);
  }

  function notRunning(data) {
    bd.innerHTML = `<div class="center"><div style="font-size:30px" class="bad">⚠</div>
      <div style="margin:8px 0 6px;font-weight:600">The Video Downloader app isn't running</div>
      <div class="muted" style="margin-bottom:14px">Start it once — after that it starts with Windows and stays in the tray,
        so this button always works.</div>
      <button class="btn pr" id="start">Start the app</button></div>`;
    root.getElementById("start").addEventListener("click", async () => {
      loading("Starting Video Downloader…", "If your browser asks, choose Open");
      const r = await send({ type: "launch" });
      if (r && r.ok) open(data);
      else error("Couldn't start the app. Open Video Downloader from the Start menu, then try again.", () => open(data));
    });
  }

  async function open(data) {
    current = { data, info: null };
    show();
    loading("Finding video…", (() => { try { return new URL(data.url).hostname.replace(/^www\./, ""); } catch (e) { return ""; } })());
    const r = await send({ type: "info", data });
    if (current.data !== data) return;              // another video was opened meanwhile
    if (!r || !r.ok) {
      if (r && r.notRunning) return notRunning(data);
      return error((r && r.error) || "Couldn't get this video.", r && r.drm ? null : () => open(data));
    }
    if (r.mode === "app") { hide(); return; }
    if (r.mode === "started") { current.info = { title: r.title || data.title, video: [], audio: [] }; addJob(r.id, "Best quality"); return render(); }
    current.info = r;
    tab = r.video && r.video.length ? "video" : "audio";
    render();
    if (r.thumbnail) {
      const t = await send({ type: "thumb", url: r.thumbnail });
      const el = root.getElementById("th");
      if (t && t.data && el) el.style.backgroundImage = `url("${t.data}")`;
    }
  }

  function render() {
    const info = current.info;
    const list = (tab === "video" ? info.video : info.audio) || [];
    const meta = [info.uploader, info.site, info.views ? Intl.NumberFormat("en", { notation: "compact" }).format(info.views) + " views" : "",
      info.is_playlist ? `${info.count} videos` : ""].filter(Boolean).join(" • ");
    const thumbStyle = root.getElementById("th") ? root.getElementById("th").style.backgroundImage : "";
    let h = "";
    if (info.video.length || info.audio.length) {
      h += `<div class="top"><div class="thumb" id="th">${info.duration ? `<span class="dur">${time(info.duration)}</span>` : ""}</div>
        <div><div class="t">${esc(info.title)}</div><div class="dim" style="margin-top:4px;font-size:12px">${esc(meta)}</div></div></div>
        <div class="tabs"><button class="tab ${tab === "video" ? "on" : ""}" data-tab="video">Video</button>
        <button class="tab ${tab === "audio" ? "on" : ""}" data-tab="audio">Audio</button></div>`;
      if (info.is_playlist) h += `<label class="chk"><input type="checkbox" id="pl" checked> Whole playlist (${info.count} videos)</label>`;
      if (!list.length) h += `<div class="dim" style="padding:8px 2px">No video in this link — see the Audio tab.</div>`;
      list.forEach((q, i) => {
        h += `<button class="q" data-i="${i}"><span class="l">${esc(q.label)}</span>
          <span class="s">${q.size ? "≈ " + size(q.size) : (info.is_playlist ? "" : "size unknown")}</span><span class="d">${DL}</span></button>`;
      });
    }
    if (jobs.length) {
      h += `<div class="sec">Downloads</div>`;
      jobs.slice().reverse().forEach((j) => { h += jobHtml(j); });
    }
    bd.innerHTML = h;
    if (thumbStyle && root.getElementById("th")) root.getElementById("th").style.backgroundImage = thumbStyle;
    bd.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.tab; render(); }));
    bd.querySelectorAll(".q").forEach((b) => b.addEventListener("click", () => start(tab, +b.dataset.i, list[+b.dataset.i].label)));
    bd.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act, b.dataset.id)));
  }

  function jobHtml(j) {
    const s = j.st || {};
    let line = "Starting…", cls = "dim", bar = 0, acts = "";
    if (s.status === "Downloading") { bar = s.pct || 0; cls = "muted";
      line = [Math.round(s.pct || 0) + "%", size(s.total), s.speed ? size(s.speed) + "/s" : "", s.eta ? time(s.eta) + " left" : ""].filter(Boolean).join(" • "); }
    else if (s.status === "Processing") { bar = 100; line = "Converting…"; }
    else if (s.status === "Queued" || s.status === "Starting") { line = "Waiting…"; }
    else if (s.status === "Done") { bar = 100; cls = "good"; line = "✓ Downloaded" + (s.total ? " • " + size(s.total) : "");
      acts = `<div class="acts"><button class="btn pr" data-act="play" data-id="${j.id}">Play</button>
        <button class="btn" data-act="folder" data-id="${j.id}">Show in folder</button></div>`; }
    else if (s.status === "Failed") { cls = "bad"; line = s.error || "Failed"; }
    else if (s.status === "Cancelled") { cls = "dim"; line = "Cancelled"; }
    const active = !s.status || ["Queued", "Starting", "Downloading", "Processing"].includes(s.status);
    if (active) acts = `<div class="acts"><button class="btn" data-act="cancel" data-id="${j.id}">Cancel</button></div>`;
    return `<div class="job"><div class="row"><span class="n" title="${esc(j.title)}">${esc(j.label)}</span></div>
      ${s.status === "Failed" || s.status === "Cancelled" ? "" : `<div class="bar ${s.status === "Done" ? "done" : ""}"><i style="width:${bar}%"></i></div>`}
      <div class="${cls}" style="font-size:12px">${esc(line)}</div>${acts}</div>`;
  }

  async function start(kind, index, label) {
    const pl = root.getElementById("pl");
    const r = await send({ type: "download", data: { token: current.info.token, kind, index, playlist: pl ? pl.checked : false } });
    if (!r || !r.ok) return error((r && r.error) || "Couldn't start the download.", () => render());
    addJob(r.id, label);
    render();
  }

  function addJob(id, label) {
    jobs.push({ id, label: (label || "") + " — " + (current.info.title || ""), title: current.info.title || "", st: null });
    if (!poll) poll = setInterval(refresh, 1000);
  }

  async function refresh() {
    let active = 0;
    for (const j of jobs) {
      if (j.st && ["Done", "Failed", "Cancelled"].includes(j.st.status)) continue;
      const r = await send({ type: "status", id: j.id });
      if (r && r.ok) j.st = r;
      active++;
    }
    if (host.style.display === "block" && current && current.info) {
      // update only the job cards to keep the page calm
      const sec = bd.querySelector(".sec");
      if (sec) {
        bd.querySelectorAll(".job").forEach((n) => n.remove());
        let html = "";
        jobs.slice().reverse().forEach((j) => { html += jobHtml(j); });
        sec.insertAdjacentHTML("afterend", html);
        bd.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act, b.dataset.id)));
      }
    }
    if (!active) { clearInterval(poll); poll = null; }
  }

  function act(what, id) {
    if (what === "cancel") send({ type: "cancel", data: { id } });
    else send({ type: "open", data: { id, action: what === "folder" ? "folder" : "play" } });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "open-panel") open(msg.data);
  });

  window.__vdPanel = { open };
})();
