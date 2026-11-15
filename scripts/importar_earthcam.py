import json
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

DB_PATH = "data/cameras.db"
SLASH = chr(47)
PROTO = "https:" + SLASH + SLASH
HOST = PROTO + "www." + "earthcam.com"
API_URL = HOST + "/api/mapsearch/get_locations_network.php?r=ecn&a=fetch"
MAX_WORKERS = 10

def validar_camera(place):
    url = str(place.get("url") or "").strip()
    if "www." + "earthcam.com" not in url or "myearthcam.com" in url:
        return None
    if url.startswith("http:"):
        url = "https:" + url[5:]

    posn = place.get("posn") or []
    if len(posn) < 2:
        return None

    try:
        lat, lon = float(posn[0]), float(posn[1])
    except Exception:
        return None

    try:
        r = requests.get(url, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            return None

        m_cam = re.search(r"[?&]cam=([a-zA-Z0-9_-]+)", url)
        cam_key = m_cam.group(1) if m_cam else None
        m_json = re.search(r"json_base\s*=\s*(\{.*\});", r.text)
        stream_url = None
        liveon = "true"

        if m_json:
            try:
                jb = json.loads(m_json.group(1))
                cams = jb.get("cam", {})
                target = cams.get(cam_key) if (cam_key and cam_key in cams) else next(iter(cams.values()), {})
                liveon = str(target.get("liveon", "true")).lower()
                stream_url = (target.get("stream") or "").replace("\\/", "/")
            except Exception:
                pass

        if liveon == "false":
            return None

        if not stream_url:
            m_st = re.search(r'"stream"\s*:\s*"(https?:\\/\\/[^"]+\.m3u8[^"]*)"', r.text)
            if m_st:
                stream_url = m_st.group(1).replace("\\/", "/")

        if not stream_url or ".m3u8" not in stream_url:
            return None

        origem_id = str(place.get("id") or url).strip()
        nome = str(place.get("name") or "EarthCam Live").strip()[:200]
        cidade = str(place.get("city") or "Global").strip()[:100]
        pais = str(place.get("country") or "Internacional").strip()[:100]
        proxy_url = f"/api/earthcam/stream.m3u8?url={quote(url, safe='')}"

        return {
            "slug": f"ec-{origem_id[:20]}",
            "nome": nome,
            "cidade": cidade,
            "latitude": lat,
            "longitude": lon,
            "pagina_oficial": url,
            "stream_url": proxy_url,
            "pais": pais,
            "origem_id": origem_id,
        }
    except Exception:
        return None

def main():
    print("🌎 Baixando catálogo global oficial da EarthCam...")
    s = requests.Session(impersonate="chrome")
    s.get(HOST + "/mapsearch/", timeout=20)
    resp = s.get(API_URL, headers={"Referer": HOST + "/mapsearch/"}, timeout=25)
    resp.raise_for_status()

    data = resp.json()
    places = next(iter(data.get("data", [{}]))).get("places", [])
    oficiais = [p for p in places if "www." + "earthcam.com" in str(p.get("url", "")) and "myearthcam.com" not in str(p.get("url", ""))]
    print(f"📦 Total no mapa: {len(places)} | Câmeras oficiais EarthCam para validar: {len(oficiais)}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT origem_id FROM cameras WHERE origem = 'earthcam'")
    existentes = {row for row in cur.fetchall()}

    pendentes = [p for p in oficiais if str(p.get("id") or p.get("url")) not in existentes]
    print(f"🔍 Novas para verificar stream ao vivo: {len(pendentes)}")

    validas = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(validar_camera, p) for p in pendentes]
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            if res:
                validas.append(res)
                print(f"  ✅ [{res['pais']}] {res['nome']} ({res['cidade']})")
            if i % 50 == 0:
                print(f"  ... {i}/{len(pendentes)} verificadas ({len(validas)} vivas)")

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    inseridas = 0
    for d in validas:
        cur.execute(
            """
            INSERT OR IGNORE INTO cameras (
                slug, nome, cidade, bairro, latitude, longitude,
                categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                autorizada, pode_retransmitir, online, ultima_verificacao,
                regiao, status, url_stream, pais, codigo_pais,
                origem, origem_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'Turismo / Cidade', 'EarthCam', ?, ?, 'hls', 1, 1, 1, ?, 'Global', 'ativo', ?, ?, 'EC', 'earthcam', ?)
            """,
            (
                d["slug"], d["nome"], d["cidade"], "Geral",
                d["latitude"], d["longitude"], d["pagina_oficial"],
                d["stream_url"], agora, d["stream_url"],
                d["pais"], d["origem_id"],
            ),
        )
        if cur.rowcount > 0:
            inseridas += 1

    conn.commit()
    conn.close()
    print(f"\n🎉 Concluído! {inseridas} câmeras icônicas da EarthCam adicionadas com proxy anti-expiração!")

if __name__ == "__main__":
    main()
