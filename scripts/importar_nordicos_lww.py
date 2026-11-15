import re
import sqlite3
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

DB_PATH = "data/cameras.db"
HOST = "https://liveworldwebcams.com"
MAX_WORKERS = 10

PAISES_MAP = {
    "Norway": ("Noruega", "NO"),
    "Finland": ("Finlândia", "FI"),
    "Sweden": ("Suécia", "SE"),
    "Iceland": ("Islândia", "IS"),
    "Faroe Islands": ("Ilhas Faroé", "FO"),
}

def extrair_stream(cam):
    try:
        r = requests.get(cam["url"], impersonate="chrome", timeout=20)
        if r.status_code != 200:
            return None
        html = r.text

        # Busca o iframe dentro de player-iframe-wrap ou embedUrl no JSON-LD
        m = re.search(r'id=["\']player-iframe-wrap["\'][^>]*>.*?<iframe[^>]+src=["\']([^"\']+)["\']', html, re.S | re.I)
        if not m:
            m = re.search(r'"embedUrl"\s*:\s*"([^"]+)"', html)
        if not m:
            return None

        src = m.group(1).replace("\\/", "/").strip()
        if not src.startswith("http"):
            return None

        # Normaliza youtube-nocookie para ://youtube.com padrão
        yt_m = re.search(r'youtube(?:-nocookie)?\.com/embed/([a-zA-Z0-9_-]{11})', src)
        video_id = None
        if yt_m:
            video_id = yt_m.group(1)
            src = f"https://www.://youtube.com/{video_id}?autoplay=1&mute=1"

        pais_en = cam.get("country", "")
        pais_pt, codigo_pais = PAISES_MAP.get(pais_en, (pais_en, "EU"))

        return {
            "origem_id": str(cam["id"]),
            "slug": f"lww-{codigo_pais.lower()}-{cam['id']}",
            "nome": str(cam.get("title", "Câmera Nórdica")).strip()[:200],
            "cidade": str(cam.get("region") or pais_pt).strip()[:100],
            "latitude": float(cam["lat"]),
            "longitude": float(cam["lng"]),
            "stream_url": src,
            "pagina_oficial": cam["url"],
            "pais": pais_pt,
            "codigo_pais": codigo_pais,
            "video_id": video_id,
        }
    except Exception:
        return None

def main():
    s = requests.Session(impersonate="chrome")
    mapa_html = s.get(HOST + "/live-webcam-map/", timeout=20).text
    nonces = re.findall(r'nonce["\':\s=]+([a-f0-9]{10})', mapa_html, re.I)

    headers = {"Referer": HOST + "/live-webcam-map/", "Accept": "application/json"}
    if nonces:
        headers["X-WP-Nonce"] = next(iter(nonces))

    data = s.get(HOST + "/wp-json/wwm/v1/webcams", headers=headers, timeout=25).json()
    webcams = data.get("webcams", [])
    nordicas = [w for w in webcams if w.get("country") in PAISES_MAP]
    print(f"❄️ Encontradas {len(nordicas)} câmeras nórdicas no catálogo!")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(extrair_stream, c) for c in nordicas]
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                resultados.append(res)

    inseridas = 0
    for d in resultados:
        cur.execute(
            """
            INSERT OR IGNORE INTO cameras (
                slug, nome, cidade, bairro, latitude, longitude,
                categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                autorizada, pode_retransmitir, online, ultima_verificacao,
                regiao, status, url_stream, pais, codigo_pais,
                origem, origem_id, video_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'Vídeo Ao Vivo', 'Live World Webcams', ?, ?, 'iframe', 1, 1, 1, ?, 'Europa', 'ativo', ?, ?, ?, 'lww', ?, ?)
            """,
            (
                d["slug"], d["nome"], d["cidade"], "Geral",
                d["latitude"], d["longitude"], d["pagina_oficial"],
                d["stream_url"], agora, d["stream_url"],
                d["pais"], d["codigo_pais"], d["origem_id"], d["video_id"],
            ),
        )
        if cur.rowcount > 0:
            inseridas += 1
            print(f"  🎥 [{d['pais']}] {d['nome']} -> {d['stream_url'][:55]}...")

    conn.commit()
    conn.close()
    print(f"\n🎉 Concluído! {inseridas} câmeras de vídeo contínuo da Escandinávia inseridas!")

if __name__ == "__main__":
    main()
