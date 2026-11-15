import re
import sqlite3
from datetime import datetime, timezone
from curl_cffi import requests

DB_PATH = "data/cameras.db"
SLASH = chr(47)
PROTO = "https:" + SLASH + SLASH
BASE = PROTO + "maaxcam.com.br"
FN = "fb4e84860f7bc65c17b932c658b18aa7050a6f470ce3fd23a5b0b9f05b160a4d"

def obter_hls(slug: str):
    hdr = {
        "Accept": "application/json",
        "x-tsr-serverFn": "true",
        "Origin": BASE,
        "Referer": BASE + "/camera/" + slug,
    }
    payload = {
        "t": {
            "t": 10,
            "i": 0,
            "p": {
                "k": ["data"],
                "v": [{
                    "t": 10,
                    "i": 1,
                    "p": {"k": ["slug"], "v": [{"t": 1, "s": slug}]},
                }],
            },
        },
        "f": 63,
        "m": [],
    }
    r = requests.post(BASE + "/_serverFn/" + FN, json=payload, headers=hdr, impersonate="chrome", timeout=15)
    m = re.search(r'"s":"(https?:[^"]+\.m3u8[^"]*)"', r.text)
    if not m:
        return None
    hls_url = m.group(1).replace("\\/", "/")
    r2 = requests.get(hls_url, headers={"Referer": BASE + "/", "Origin": BASE}, impersonate="chrome", timeout=15)
    if r2.status_code == 200 and "#EXTM3U" in r2.text:
        return hls_url
    return None

def main():
    print("🏖️ Conectando ao catálogo do Maaxcam...")
    html = requests.get(BASE + "/cameras", impersonate="chrome", timeout=15).text
    js_path = re.search(r'src="(/assets/index-[^"]+\.js)"', html).group(1)
    js = requests.get(BASE + js_path, impersonate="chrome", timeout=15).text

    sb_url = re.search(r"https?://[a-z0-9]+\.supabase\.co", js).group(0)
    anon = re.search(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", js).group(0)

    r = requests.get(
        sb_url + "/rest/v1/cameras?select=*&order=sort_order.asc",
        headers={"apikey": anon, "Authorization": "Bearer " + anon},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    print(f"📦 Total no Supabase Maaxcam: {len(rows)}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    inseridas = 0

    for cam in rows:
        if not cam.get("visible", True) or cam.get("premium"):
            continue
        slug = str(cam.get("slug") or "").strip()
        lat = cam.get("latitude")
        lon = cam.get("longitude")
        if not slug or lat is None or lon is None:
            continue

        hls_real = obter_hls(slug)
        if not hls_real:
            print(f"  ⚠️ Offline/sem m3u8: {cam.get('title')} ({slug})")
            continue

        nome = str(cam.get("title") or slug).strip()
        loc = str(cam.get("location") or "Brasil").strip()
        cidade = loc.split(",")[0].split("-")[0].strip() or "Florianópolis"
        proxy_url = f"/api/maaxcam/stream.m3u8?slug={slug}"
        pagina = BASE + "/camera/" + slug

        cur.execute(
            """
            INSERT OR REPLACE INTO cameras (
                slug, nome, cidade, bairro, latitude, longitude,
                categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                autorizada, pode_retransmitir, online, ultima_verificacao,
                regiao, status, url_stream, pais, codigo_pais,
                origem, origem_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'Praias', 'Maaxcam', ?, ?, 'hls', 1, 1, 1, ?, 'Brasil', 'ativo', ?, 'Brasil', 'BR', 'maaxcam', ?)
            """,
            (
                f"mc-{slug}", nome, cidade, loc,
                float(lat), float(lon), pagina,
                proxy_url, agora, proxy_url, slug,
            ),
        )
        inseridas += 1
        print(f"  ✅ [{loc}] {nome}")

    conn.commit()
    conn.close()
    print(f"\n🎉 Concluído! {inseridas} câmeras do Maaxcam adicionadas na categoria 'Praias' com proxy anti-bloqueio!")

if __name__ == "__main__":
    main()
