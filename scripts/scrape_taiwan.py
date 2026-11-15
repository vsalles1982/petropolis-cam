import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

DOMINIO = "https://opencctv.org"
ROTA_PAIS = "/cameras/taiwan"
PAGINA_INICIAL = 1
PAGINA_FINAL = 120   # Aumente se quiser varrer mais páginas (vai até ~527)
MAX_WORKERS = 12

def extrair_camera(cam_url):
    try:
        r = requests.get(cam_url, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            return None
        html = r.text

        if "://youtube.com" in html or "youtu.be" in html:
            return None

        hls = re.findall(r'https?://[^\s\'"\\<>]+\.m3u8[^\s\'"\\<>]*', html)
        mjpeg = re.findall(r'https?://[^\s\'"\\<>]+(?:\.mjpg|\.mjpeg|video\.cgi|nphMotionJpeg)[^\s\'"\\<>]*', html, re.I)

        if hls:
            stream_url = hls[0]
            tipo = "hls"
        elif mjpeg:
            stream_url = mjpeg[0]
            tipo = "mjpeg"
        else:
            return None

        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        nome = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else "Câmera Taiwan"

        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', html)
        if not coord_match:
            return None
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))

        id_match = re.search(r'-(\d+)$', cam_url)
        origem_id = id_match.group(1) if id_match else cam_url.split("/")[-1]

        return {
            "slug": f"tw-{origem_id}",
            "nome": nome[:200],
            "cidade": "Taiwan",
            "latitude": lat,
            "longitude": lon,
            "stream_url": stream_url,
            "tipo_stream": tipo,
            "pagina_oficial": cam_url,
            "origem_id": origem_id,
        }
    except Exception:
        return None

def main():
    conn = sqlite3.connect("data/cameras.db")
    cur = conn.cursor()

    cur.execute("SELECT origem_id FROM cameras WHERE origem = 'taiwan_opencctv'")
    existentes = {row[0] for row in cur.fetchall()}
    print(f"🇹🇼 Já existem {len(existentes)} câmeras de Taiwan no banco.")

    inseridas = 0
    paginas_vazias = 0

    for page in range(PAGINA_INICIAL, PAGINA_FINAL + 1):
        list_url = f"{DOMINIO}{ROTA_PAIS}?page={page}"
        try:
            r = requests.get(list_url, impersonate="chrome", timeout=20)
        except Exception as e:
            print(f"⚠️ Erro de conexão na pág {page}: {e}")
            continue

        if r.status_code != 200:
            print(f"⚠️ HTTP {r.status_code} na pág {page}")
            break

        caminhos = sorted(set(re.findall(r'href="(/cameras/taiwan/[^"]+-\d+)"', r.text)))
        if not caminhos:
            paginas_vazias += 1
            if paginas_vazias >= 3:
                print(f"🛑 Fim da listagem detectado na página {page}.")
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
            print(f"📄 Pág {page}: {len(caminhos)} links (todos já no banco)")
            continue

        novos_registros = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(extrair_camera, u) for u in novas_urls]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    novos_registros.append(res)
                    existentes.add(res["origem_id"])

        for d in novos_registros:
            cur.execute(
                """
                INSERT OR IGNORE INTO cameras (
                    slug, nome, cidade, bairro, latitude, longitude,
                    categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                    autorizada, pode_retransmitir, online, regiao, status,
                    url_stream, pais, codigo_pais, origem, origem_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'Trânsito', 'OpenCCTV Taiwan', ?, ?, ?, 1, 1, 1, 'Ásia', 'ativo', ?, 'Taiwan', 'TW', 'taiwan_opencctv', ?)
                """,
                (
                    d["slug"], d["nome"], d["cidade"], d["cidade"],
                    d["latitude"], d["longitude"], d["pagina_oficial"],
                    d["stream_url"], d["tipo_stream"], d["stream_url"], d["origem_id"],
                ),
            )
            if cur.rowcount > 0:
                inseridas += 1

        conn.commit()
        print(f"📄 Pág {page}: +{len(novos_registros)} streams extraídos (Total acumulado: {inseridas})")

    conn.close()
    print(f"\n🎉 Concluído! {inseridas} novas câmeras de vídeo contínuo adicionadas em Taiwan.")

if __name__ == "__main__":
    main()
