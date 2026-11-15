import re
import time
import sqlite3
from curl_cffi import requests

DOMINIO = "https://opencctv.org"
ROTA_PAIS = "/cameras/taiwan"
TOTAL_PAGINAS = 30  # Aumente até 527 se quiser varrer o país inteiro

def init_db():
    conn = sqlite3.connect("data/cameras.db")
    return conn

def extrair_camera(cam_url):
    try:
        r = requests.get(cam_url, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            return None
        html = r.text

        # Ignora YouTube e fotos estáticas
        if "://youtube.com" in html or "youtu.be" in html:
            return None

        # Busca stream HLS (.m3u8) ou MJPEG real
        hls = re.findall(r'https?://[^\s\'"\\<>]+\.m3u8[^\s\'"\\<>]*', html)
        mjpeg = re.findall(r'https?://[^\s\'"\\<>]+(?:\.mjpg|\.mjpeg|video\.cgi|nphMotionJpeg)[^\s\'"\\<>]*', html, re.I)

        if hls:
            stream_url = hls
            tipo = "hls"
        elif mjpeg:
            stream_url = mjpeg
            tipo = "mjpeg"
        else:
            return None

        # Extrai nome (H1)
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        nome = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else "Câmera Taiwan"

        # Extrai coordenadas (Lat, Lon)
        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', html)
        if not coord_match:
            return None
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))

        # Extrai ID da URL
        id_match = re.search(r'-(\d+)$', cam_url)
        origem_id = id_match.group(1) if id_match else cam_url.split("/")[-1]

        return {
            "slug": f"tw-{origem_id}",
            "nome": nome,
            "cidade": "Taiwan",
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
    conn = init_db()
    cur = conn.cursor()
    inseridas = 0

    for page in range(1, TOTAL_PAGINAS + 1):
        list_url = f"{DOMINIO}{ROTA_PAIS}?page={page}"
        print(f"📄 Lendo página {page}/{TOTAL_PAGINAS}...")
        r = requests.get(list_url, impersonate="chrome", timeout=20)
        if r.status_code != 200:
            print(f"  ⚠️ Erro HTTP {r.status_code} na página {page}")
            continue

        caminhos = list(set(re.findall(r'/cameras/taiwan/[a-z0-9\-]+/[a-z0-9\-]+-\d+', r.text)))
        for path in caminhos:
            cam_url = f"{DOMINIO}{path}"
            dados = extrair_camera(cam_url)
            if dados:
                cur.execute("""
                    INSERT OR IGNORE INTO cameras 
                    (slug, nome, cidade, bairro, latitude, longitude, categoria, fonte, pagina_oficial, stream_url, tipo_stream, autorizada, pode_retransmitir, online, regiao, status, pais, codigo_pais, origem, origem_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'Transito', 'OpenCCTV Taiwan', ?, ?, ?, 1, 1, 1, 'Taiwan', 'ativo', 'Taiwan', 'TW', 'taiwan_opencctv', ?)
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
    print(f"\n🎉 Concluído! {inseridas} novas câmeras de vídeo contínuo adicionadas em Taiwan.")

if __name__ == "__main__":
    main()
