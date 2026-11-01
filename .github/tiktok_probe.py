"""Probe how TikTok's web page exposes a video (used to build the phone's TikTok reader)."""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
MUA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"

def probe(p, url, ua):
    print(f"\n===== {url}  [{'mobile' if 'Mobile' in ua else 'desktop'}]", flush=True)
    b = p.chromium.launch()
    ctx = b.new_context(user_agent=ua)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    data = None
    for _ in range(30):
        txt = page.evaluate("() => { const e = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__'); return e ? e.textContent : null }")
        if txt:
            try:
                d = json.loads(txt)["__DEFAULT_SCOPE__"]
                if "webapp.video-detail" in d:
                    data = d["webapp.video-detail"]; break
            except Exception as e:
                print("parse", e)
        page.wait_for_timeout(500)
    print("final url:", page.url, "title:", page.title()[:60])
    if not data:
        print("NO DATA. keys:", page.evaluate("() => [...document.scripts].map(s => s.id).filter(Boolean)"))
    else:
        print("statusCode:", data.get("statusCode"), data.get("statusMsg"))
        it = data.get("itemInfo", {}).get("itemStruct", {})
        v = it.get("video", {})
        print("id", it.get("id"), "| desc", (it.get("desc") or "")[:50], "| author", it.get("author", {}).get("uniqueId"))
        print("video keys:", sorted(v.keys()))
        print("duration", v.get("duration"), "cover", (v.get("cover") or "")[:60])
        print("playAddr", (v.get("playAddr") or "")[:90])
        print("downloadAddr", (v.get("downloadAddr") or "")[:90])
        for bi in v.get("bitrateInfo", [])[:6]:
            pa = bi.get("PlayAddr", {})
            print("  br", bi.get("GearName"), bi.get("QualityType"), bi.get("Bitrate"), bi.get("CodecType"),
                  pa.get("Width"), pa.get("Height"), pa.get("DataSize"), (pa.get("UrlList") or [""])[0][:70])
        m = it.get("music", {})
        print("music", m.get("title"), (m.get("playUrl") or "")[:80])
        print("imagePost", bool(it.get("imagePost")))
        cookies = ctx.cookies()
        print("cookies:", sorted(c["name"] for c in cookies))
        # can a plain HTTP client fetch the video with the browser's cookies + referer?
        jar = "; ".join(f"{c['name']}={c['value']}" for c in cookies if "tiktok" in c["domain"])
        for name, u in (("playAddr", v.get("playAddr")),
                        ("bitrate0", ((v.get("bitrateInfo") or [{}])[0].get("PlayAddr", {}).get("UrlList") or [None])[0]),
                        ("music", m.get("playUrl"))):
            if not u: continue
            for label, hdr in (("ref+cookie", {"Referer": "https://www.tiktok.com/", "Cookie": jar, "User-Agent": ua}),
                               ("ref only", {"Referer": "https://www.tiktok.com/", "User-Agent": ua})):
                try:
                    r = urllib.request.urlopen(urllib.request.Request(u, headers={**hdr, "Range": "bytes=0-"}), timeout=30)
                    n = len(r.read())
                    print(f"  GET {name} [{label}] -> {r.status} {r.headers.get('Content-Type')} {n} bytes")
                except Exception as e:
                    print(f"  GET {name} [{label}] -> FAIL {e}")
    b.close()

def feed(p):
    print("\n===== FEED DOM probe", flush=True)
    b = p.chromium.launch()
    page = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}).new_page()
    page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(9000)
    print("url", page.url, "videos:", page.evaluate("() => document.querySelectorAll('video').length"))
    print(json.dumps(page.evaluate("""() => [...document.querySelectorAll('video')].slice(0,2).map(v => {
        const out = []; let el = v;
        for (let i = 0; i < 14 && el; i++) {
          const a = {tag: el.tagName, id: el.id || undefined, cls: (el.className && el.className.baseVal === undefined ? String(el.className) : '').slice(0,60) || undefined};
          for (const at of el.attributes || []) if (at.name.startsWith('data-')) a[at.name] = at.value.slice(0,60);
          const links = [...el.querySelectorAll('a[href]')].map(x => x.getAttribute('href')).filter(h => /video|photo|@/.test(h)).slice(0,4);
          if (links.length) a.links = links;
          out.push(a); el = el.parentElement;
        }
        return {src: (v.currentSrc||'').slice(0,80), chain: out};
    })"""), indent=1)[:6000])
    b.close()

with sync_playwright() as p:
    for u in sys.argv[1:]:
        for ua in (UA, MUA):
            try: probe(p, u, ua)
            except Exception as e: print("probe error", e)
    try: feed(p)
    except Exception as e: print("feed error", e)
