import re
import time
import sqlite3
from curl_cffi import requests

DB_PATH = "data/cameras.db"
DOMINIO_OPEN = "https://opencctv.org"
PROVINCIAS_FILE = [
    "tokyo", "kanagawa", "osaka", "kyoto", "hokkaido",
    "shizuoka", "nagano", "okinawa", "hyogo", "chiba"
]

def extrair_opencctv(cam_url, provincia):
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
            stream_url = hls
            tipo = "hls"
        elif mjpeg:
            stream_url = mjpeg
            tipo = "mjpeg"
        else:
            return None

        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        nome = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else f"Japão ({provincia.title()})"

        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', html)
        if not coord_match:
            return None
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))

        id_match = re.search(r'-(\d+)$', cam_url)
        origem_id = id_match.group(1) if id_match else cam_url.split("/")[-1]

        return {
            "slug": f"jp-{origem_id}",
            "nome": nome,
            "cidade": provincia.title(),
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    inseridas = 0

    print("🇯🇵 Iniciando pesca cirúrgica de VÍDEO AO VIVO no Japão (Províncias Turísticas & Portos)...\n")

    for prov in PROVINCIAS_FILE:
        print(f"🔎 Varrendo província: {prov.upper()}...")
        for page in range(1, 15):
            list_url = f"{DOMINIO_OPEN}/cameras/japan/{prov}?page={page}"
            r = requests.get(list_url, impersonate="chrome", timeout=15)
            if r.status_code != 200:
                break

            caminhos = list(set(re.findall(rf'href="(/cameras/japan/{prov}/[^"]+-\d+)"', r.text)))
            if not caminhos:
                break

            for path in caminhos:
                dados = extrair_opencctv(f"{DOMINIO_OPEN}{path}", prov)
                if dados:
                    cur.execute("""
                        INSERT OR IGNORE INTO cameras 
                        (slug, nome, cidade, bairro, latitude, longitude, categoria, fonte, pagina_oficial, stream_url, tipo_stream, autorizada, pode_retransmitir, online, regiao, status, pais, codigo_pais, origem, origem_id)
                        VALUES (?, ?, ?, ?, ?, ?, 'Turismo', 'OpenCCTV Japão', ?, ?, ?, 1, 1, 1, ?, 'ativo', 'Japão', 'JP', 'japan_video', ?)
                    """, (
                        dados["slug"], dados["nome"], dados["cidade"], dados["cidade"],
                        dados["latitude"], dados["longitude"], dados["pagina_oficial"],
                        dados["stream_url"], dados["tipo_stream"], dados["cidade"], dados["origem_id"]
                    ))
                    if cur.rowcount > 0:
                        inseridas += 1
                        print(f"  ✅ [{dados['tipo_stream'].upper()}] {dados['nome']} ({dados['latitude']}, {dados['longitude']})")
                time.sleep(0.2)
            conn.commit()

    conn.close()
    print(f"\n🎉 Concluído! {inseridas} câmeras de VÍDEO AO VIVO do Japão inseridas no banco.")

if __name__ == "__main__":
    main()
