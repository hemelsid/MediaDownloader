const statusBox = document.getElementById("status");
const statusText = document.getElementById("statusText");

chrome.runtime.sendMessage({ type: "ping" }, (res) => {
  const ok = res && res.ok;
  statusBox.className = "status " + (ok ? "ok" : "bad");
  statusText.textContent = ok ? "Connected to the app" : "App is closed — it starts when you download";
});

document.getElementById("send").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:/.test(tab.url || "")) return;
  const data = { url: tab.url, page: tab.url, src: "", title: tab.title || "" };
  chrome.tabs.sendMessage(tab.id, { type: "open-panel", data }, { frameId: 0 })
    .then(() => window.close())
    .catch(() => chrome.runtime.sendMessage({ type: "add", data }, () => window.close()));
});
