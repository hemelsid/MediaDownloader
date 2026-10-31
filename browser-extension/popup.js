const statusBox = document.getElementById("status");
const statusText = document.getElementById("statusText");

chrome.runtime.sendMessage({ type: "status" }, (res) => {
  const ok = res && res.ok;
  statusBox.className = "status " + (ok ? "ok" : "bad");
  statusText.textContent = ok ? "Connected to the app" : "App is closed — it will open when you download";
});

document.getElementById("send").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:/.test(tab.url || "")) return;
  chrome.runtime.sendMessage({ type: "add", data: { url: tab.url, page: tab.url, src: "", title: tab.title || "" } },
    () => window.close());
});
