import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

DOMINIO = "https://opencctv.org"
MAX_WORKERS = 12

PAISES = [
    {"slug": "norway", "nome": "Noruega", "codigo": "NO", "max_pags": 60},
    {"slug": "finland", "nome": "Finlândia", "codigo": "FI", "max_pags": 60},
    {"slug": "sweden", "nome": "Suécia", "codigo": "SE", "max_pags": 60},
]

def extrair_camera(cam_url, pais_info):
    try:
        r = requests.get(cam_url, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            return None
        html = r.text

        if "://youtube.com" in html or "youtu.be" in html:
            return None

        hls = re.findall(r'https?://[^\s\'"\\<>]+\.m3u8[^\s\'"\\<>]*', html)
        mjpeg = re.findall(r'https?://[^\s\'"\\<>]+(?:\.mjpg|\.mjpeg|video\.cgi|nphMotionJpeg|mjpg/video\.cgi)[^\s\'"\\<>]*', html, re.I)

        if hls:
            stream_url = hls
            tipo = "hls"
        elif mjpeg:
            stream_url = mjpeg
            tipo = "mjpeg"
        else:
            return None

        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        nome = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else f"Câmera {pais_info['nome']}"

        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', html)
        if not coord_match:
            return None
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))

        id_match = re.search(r'-(\d+)$', cam_url)
        origem_id = id_match.group(1) if id_match else cam_url.split("/")[-1]
        origem = f"{pais_info['slug']}_opencctv"

        return {
            "slug": f"{pais_info['codigo'].lower()}-{origem_id}",
            "nome": nome[:200],
            "cidade": pais_info["nome"],
            "latitude": lat,
            "longitude": lon,
            "stream_url": stream_url,
            "tipo_stream": tipo,
            "pagina_oficial": cam_url,
            "pais": pais_info["nome"],
            "codigo_pais": pais_info["codigo"],
            "origem": origem,
            "origem_id": origem_id,
        }
    except Exception:
        return None

def main():
    conn = sqlite3.connect("data/cameras.db")
    cur = conn.cursor()

    for p in PAISES:
        origem = f"{p['slug']}_opencctv"
        cur.execute("SELECT origem_id FROM cameras WHERE origem = ?", (origem,))
        existentes = {row for row in cur.fetchall()}

        inseridas = 0
        paginas_vazias = 0
        print(f"\n❄️ Varrendo {p['nome']} ({p['slug']}) no OpenCCTV (apenas HLS/MJPEG)...")

        for page in range(1, p["max_pags"] + 1):
            list_url = f"{DOMINIO}/cameras/{p['slug']}?page={page}"
            try:
                r = requests.get(list_url, impersonate="chrome", timeout=20)
            except Exception:
                continue

            if r.status_code != 200:
                break

            pattern = rf'href="(/cameras/{p["slug"]}/[^"]+-\d+)"'
            caminhos = sorted(set(re.findall(pattern, r.text)))
            if not caminhos:
                paginas_vazias += 1
                if paginas_vazias >= 2:
                    break
                continue
            paginas_vazias = 0

            novas_urls = []
            for path in caminhos:
                id_m = re.search(r'-(\d+)$', path)
                oid = id_m.group(1) if id_m else path
                if oid not in existentes:
                    novas_urls.append(f"{DOMINIO}{path}")

            if not novas_urls:
                continue

            novos = []
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futures = [ex.submit(extrair_camera, u, p) for u in novas_urls]
                for fut in as_completed(futures):
                    res = fut.result()
                    if res:
                        novos.append(res)
                        existentes.add(res["origem_id"])

            for d in novos:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO cameras (
                        slug, nome, cidade, bairro, latitude, longitude,
                        categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                        autorizada, pode_retransmitir, online, regiao, status,
                        url_stream, pais, codigo_pais, origem, origem_id
                    ) VALUES (?, ?, ?, ?, ?, ?, 'Vídeo Ao Vivo', 'OpenCCTV', ?, ?, ?, 1, 1, 1, 'Europa', 'ativo', ?, ?, ?, ?, ?)
                    """,
                    (
                        d["slug"], d["nome"], d["cidade"], d["cidade"],
                        d["latitude"], d["longitude"], d["pagina_oficial"],
                        d["stream_url"], d["tipo_stream"], d["stream_url"],
                        d["pais"], d["codigo_pais"], d["origem"], d["origem_id"],
                    ),
                )
                if cur.rowcount > 0:
                    inseridas += 1
                    print(f"  🎥 [{d['tipo_stream'].upper()}] {d['nome']} -> {d['stream_url'][:55]}...")

            conn.commit()
            if page % 10 == 0:
                print(f"  ... pág {page} verificada ({inseridas} vídeos encontrados até agora)")

        print(f"✅ {p['nome']}: {inseridas} streams de vídeo contínuo salvos!")

    conn.close()

if __name__ == "__main__":
    main()
