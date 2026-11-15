import re
from curl_cffi import requests

HOST = "https://liveworldwebcams.com"
s = requests.Session(impersonate="chrome")
mapa_html = s.get(HOST + "/live-webcam-map/", timeout=20).text
nonces = re.findall(r'nonce["\':\s=]+([a-f0-9]{10})', mapa_html, re.I)

headers = {"Referer": HOST + "/live-webcam-map/", "Accept": "application/json"}
if nonces:
    headers["X-WP-Nonce"] = nonces[0]

data = s.get(HOST + "/wp-json/wwm/v1/webcams", headers=headers, timeout=25).json()
webcams = data.get("webcams", [])
nor = [w for w in webcams if w.get("country") in ("Norway", "Finland", "Sweden", "Iceland", "Faroe Islands")]
print(f"Total Nórdicos no JSON: {len(nor)}")

if nor:
    cam = next(iter(nor))
    print("Testando:", cam["title"], "|", cam["url"])
    html = s.get(cam["url"], timeout=20).text
    # Procura scripts inline ou URLs de mídia/embed
    for m in re.findall(r'.{0,60}(?:youtube|youtu\.be|m3u8|mp4|embed|player|stream|windy|skyline|feratel).{0,80}', html, re.I):
        if not any(x in m.lower() for x in ["og:image", "schema.org", "wp-content/themes", "embed-a-webcam", "/embed/"]):
            print("  MATCH:", m.strip())
