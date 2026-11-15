import re
from curl_cffi import requests

HOST = "https://liveworldwebcams.com"
s = requests.Session(impersonate="chrome")

mapa_html = s.get(HOST + "/live-webcam-map/", timeout=20).text
nonces = re.findall(r'nonce["\':\s=]+([a-f0-9]{10})', mapa_html, re.I)
print("Nonces:", nonces)

headers = {
    "Referer": HOST + "/live-webcam-map/",
    "Accept": "application/json",
}
if nonces:
    headers["X-WP-Nonce"] = nonces[0]

r = s.get(HOST + "/wp-json/wwm/v1/webcams", headers=headers, timeout=25)
print("Status:", r.status_code, "| Type:", r.headers.get("content-type"), "| Tamanho:", len(r.text))
print("Amostra:", r.text[:600])
