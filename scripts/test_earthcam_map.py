import re
from curl_cffi import requests

HOST = "https://earthcam.com"
s = requests.Session(impersonate="chrome")

r_map = s.get(HOST + "/mapsearch/", timeout=20)
print("Scripts no /mapsearch/:", re.findall(r'src=["\']([^"\']+\.js[^"\']*)', r_map.text))
print("Chamadas ajax/json:", re.findall(r'["\']([^"\']*(?:map|search|json|xml|api)[^"\']*)["\']', r_map.text, re.I)[:15])

r_home = s.get(HOST + "/", timeout=20)
home_links = sorted(set(re.findall(r'href=["\']((?:https?://www\.earthcam\.com)?/(?:world|usa)/[^"\']+)["\']', r_home.text)))
print("\nLinks na Home:", len(home_links))
print("Exemplos:", home_links[:8])
