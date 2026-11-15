import re
import time
import sqlite3
from curl_cffi import requests

DOMINIO = "https://opencctv.org"
ROTA_PAIS = "/cameras/poland"
TOTAL_PAGINAS = 40

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
        nome = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else "Câmera Polônia"

        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', html)
        if not coord_match:
            return None
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))

        id_match = re.search(r'-(\d+)$', cam_url)
        origem_id = id_match.group(1) if id_match else cam_url.split("/")[-1]

        return {
            "slug": f"pl-{origem_id}",
            "nome": nome,
            "cidade": "Polônia",
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
        list_url = f"{DOMINIO}{ROTA_PAIS}?page={page}"
        print(f"📄 Polônia - Página {page}/{TOTAL_PAGINAS}...")
        r = requests.get(list_url, impersonate="chrome", timeout=20)
        if r.status_code != 200:
            continue

        caminhos = list(set(re.findall(r'href="(/cameras/poland/[^"]+-\d+)"', r.text)))
        for path in caminhos:
            dados = extrair_camera(f"{DOMINIO}{path}")
            if dados:
                cur.execute("""
                    INSERT OR IGNORE INTO cameras 
                    (slug, nome, cidade, bairro, latitude, longitude, categoria, fonte, pagina_oficial, stream_url, tipo_stream, autorizada, pode_retransmitir, online, regiao, status, pais, codigo_pais, origem, origem_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'Transito', 'OpenCCTV Polônia', ?, ?, ?, 1, 1, 1, 'Polônia', 'ativo', 'Polônia', 'PL', 'poland_opencctv', ?)
                """, (
                    dados["slug"], dados["nome"], dados["cidade"], dados["cidade"],
                    dados["latitude"], dados["longitude"], dados["pagina_oficial"],
                    dados["stream_url"], dados["tipo_stream"], dados["origem_id"]
                ))
                if cur.rowcount > 0:
                    inseridas += 1
                    print(f"  ✅ [{dados['tipo_stream'].upper()}] {dados['nome']} ({dados['latitude']}, {dados['longitude']})")
            time.sleep(0.25)
        conn.commit()

    conn.close()
    print(f"\n🎉 Concluído! {inseridas} novas câmeras de vídeo contínuo adicionadas na Polônia.")

if __name__ == "__main__":
    main()
