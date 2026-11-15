import re
from curl_cffi import requests

r = requests.get("https://www.earthcam.com/mapsearch/", impersonate="chrome", timeout=20)
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.S)
for i, sc in enumerate(scripts):
    if any(k in sc for k in ["L.marker", "MarkerCluster", "ajax", "getJSON", "fetch", "cams", "lat"]):
        print(f"=== SCRIPT {i} (len {len(sc)}) ===")
        print(sc[:1000])
