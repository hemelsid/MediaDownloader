// Talks to the Video Downloader app running on this PC (local only: 127.0.0.1).
const API = "http://127.0.0.1:47811";

async function appRunning() {
  try {
    const r = await fetch(API + "/ping", { cache: "no-store" });
    return r.ok;
  } catch (e) {
    return false;
  }
}

async function send(data) {
  try {
    const r = await fetch(API + "/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (r.ok) return { ok: true };
  } catch (e) { /* app not running */ }

  // App is closed: open it through its link handler (videodownloader://), which also passes the video.
  try {
    const link = "videodownloader://add?url=" + encodeURIComponent(data.url) +
      (data.title ? "&title=" + encodeURIComponent(data.title) : "") +
      (data.src ? "&src=" + encodeURIComponent(data.src) : "");
    const tab = await chrome.tabs.create({ url: link, active: true });
    setTimeout(() => chrome.tabs.remove(tab.id).catch(() => {}), 6000);
    return { ok: true, launched: true };
  } catch (e) {
    return { ok: false };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "add") {
    send(msg.data).then(reply);
    return true; // async reply
  }
  if (msg && msg.type === "status") {
    appRunning().then((ok) => reply({ ok }));
    return true;
  }
});

// Right-click menu on any page, link or video
function setupMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "vd-download",
      title: "Download with Video Downloader",
      contexts: ["page", "link", "video", "audio", "frame"],
    });
  });
}
chrome.runtime.onInstalled.addListener(() => { setupMenu(); appRunning(); });
chrome.runtime.onStartup.addListener(() => { setupMenu(); appRunning(); });

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const media = info.srcUrl && /^https?:/.test(info.srcUrl) ? info.srcUrl : "";
  const url = info.linkUrl || info.frameUrl || info.pageUrl || (tab && tab.url) || media;
  if (!url) return;
  send({ url, page: info.pageUrl || "", src: media, title: (tab && tab.title) || "" });
});
