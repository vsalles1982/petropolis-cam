import re
from curl_cffi import requests

HOST = "https://earthcam.com"
s = requests.Session(impersonate="chrome")

r = s.get(HOST + "/world/ireland/dublin/?cam=dublinpub", timeout=20)
print("Status câmera:", r.status_code, "| Tamanho:", len(r.text))

m3u8 = re.findall(r'https?://[^\s\'"\\<>]+\.m3u8[^\s\'"\\<>]*', r.text)
json_vars = re.findall(r'(?:json_base|cam_data|html5_streamingdomain|livestreaming)\s*[:=]\s*([^\n;]+)', r.text)
coords = re.findall(r'(?:latitude|longitude|lat|lng)["\']?\s*[:=]\s*(-?\d+\.\d+)', r.text, re.I)

print("M3U8 direto:", m3u8[:2])
print("Vars JS:", json_vars[:5])
print("Coords:", coords[:4])
