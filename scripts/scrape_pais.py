import sys
import re
import time
import sqlite3
from curl_cffi import requests

if len(sys.argv) < 3:
    print("Uso: python3 scripts/scrape_pais.py <slug-pais> <CODIGO_ISO> [paginas]")
    print("Ex:  python3 scripts/scrape_pais.py czech-republic CZ 30")
    sys.exit(1)

PAIS_SLUG = sys.argv[1].lower()
CODIGO_ISO = sys.argv[2].upper()
TOTAL_PAGINAS = int(sys.argv[3]) if len(sys.argv) > 3 else 30
DOMINIO = "https://opencctv.org"

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
        nome = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else f"Câmera {CODIGO_ISO}"

        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', html)
        if not coord_match:
            return None
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))

        id_match = re.search(r'-(\d+)$', cam_url)
        origem_id = id_match.group(1) if id_match else cam_url.split("/")[-1]

        return {
            "slug": f"{CODIGO_ISO.lower()}-{origem_id}",
            "nome": nome,
            "cidade": PAIS_SLUG.replace("-", " ").title(),
            "latitude": lat,
            "longitude": lon,
            "stream_url": stream_url,
            "tipo_stream": tipo,
            "pagina_oficial": cam_url,
            "origem_id": origem_id
        }
    except Exception:
        return None

def main():
    conn = sqlite3.connect("data/cameras.db")
    cur = conn.cursor()
    inseridas = 0

    for page in range(1, TOTAL_PAGINAS + 1):
        list_url = f"{DOMINIO}/cameras/{PAIS_SLUG}?page={page}"
        print(f"📄 [{CODIGO_ISO}] Página {page}/{TOTAL_PAGINAS}...")
        r = requests.get(list_url, impersonate="chrome", timeout=20)
        if r.status_code != 200:
            break

        caminhos = list(set(re.findall(rf'href="(/cameras/{PAIS_SLUG}/[^"]+-\d+)"', r.text)))
        if not caminhos:
            break

        for path in caminhos:
            dados = extrair_camera(f"{DOMINIO}{path}")
            if dados:
                cur.execute("""
                    INSERT OR IGNORE INTO cameras 
                    (slug, nome, cidade, bairro, latitude, longitude, categoria, fonte, pagina_oficial, stream_url, tipo_stream, autorizada, pode_retransmitir, online, regiao, status, pais, codigo_pais, origem, origem_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'Transito', ?, ?, ?, ?, 1, 1, 1, ?, 'ativo', ?, ?, ?, ?)
                """, (
                    dados["slug"], dados["nome"], dados["cidade"], dados["cidade"],
                    dados["latitude"], dados["longitude"], f"OpenCCTV {dados['cidade']}",
                    dados["pagina_oficial"], dados["stream_url"], dados["tipo_stream"],
                    dados["cidade"], dados["cidade"], CODIGO_ISO,
                    f"{PAIS_SLUG}_opencctv", dados["origem_id"]
                ))
                if cur.rowcount > 0:
                    inseridas += 1
                    print(f"  ✅ [{dados['tipo_stream'].upper()}] {dados['nome']} ({dados['latitude']}, {dados['longitude']})")
            time.sleep(0.25)
        conn.commit()

    conn.close()
    print(f"\n🎉 Concluído [{CODIGO_ISO}]! {inseridas} novas câmeras de vídeo contínuo adicionadas.")

if __name__ == "__main__":
    main()
