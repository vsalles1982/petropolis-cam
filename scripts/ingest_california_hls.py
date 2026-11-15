import sqlite3
import requests

DB_PATH = "data/cameras.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    inseridas = 0

    print("🇺🇸 Iniciando varredura 100% VÍDEO HLS na Califórnia (Distritos D01 a D12)...\n")

    for d in range(1, 13):
        dist = f"d{d}"
        dist_num = f"{d:02d}"
        p1 = "https://" + "cwwp2" + "." + "dot" + "." + "ca.gov"
        p2 = "data"
        p3 = "cctv"
        url = f"{p1}/{p2}/{dist}/{p3}/cctvStatusD{dist_num}.json"
        print("Testando:", url)
        
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                print(f"  ⚠️ Distrito {dist_num}: HTTP {r.status_code}")
                continue

            dados = r.json().get("data", [])
            dist_count = 0

            for item in dados:
                cctv = item.get("cctv", {})
                if cctv.get("inService") != "true":
                    continue

                img_data = cctv.get("imageData", {})
                stream_url = img_data.get("streamingVideoURL", "").strip()

                # Filtro estrito: APENAS vídeo contínuo HLS (.m3u8)
                if not stream_url or ".m3u8" not in stream_url.lower():
                    continue

                loc = cctv.get("location", {})
                nome = loc.get("locationName") or f"Caltrans D{dist_num} Cam"
                cidade = loc.get("nearbyPlace") or "Califórnia"
                lat = float(loc.get("latitude") or 0)
                lon = float(loc.get("longitude") or 0)

                if lat == 0 or lon == 0:
                    continue

                cam_id = f"d{dist_num}_{cctv.get('index', inseridas)}"
                slug = f"us-ca-{cam_id}"

                cur.execute("""
                    INSERT OR IGNORE INTO cameras 
                    (slug, nome, cidade, bairro, latitude, longitude, categoria, fonte, pagina_oficial, stream_url, tipo_stream, autorizada, pode_retransmitir, online, regiao, status, pais, codigo_pais, origem, origem_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'Transito', 'Caltrans CA', 'https://ca.gov', ?, 'hls', 1, 1, 1, 'Califórnia', 'ativo', 'Estados Unidos', 'US', 'caltrans_ca', ?)
                """, (slug, nome, cidade, cidade, lat, lon, stream_url, cam_id))

                if cur.rowcount > 0:
                    inseridas += 1
                    dist_count += 1

            conn.commit()
            print(f"  ✅ Distrito {dist_num}: +{dist_count} vídeos HLS adicionados.")
        except Exception as e:
            print(f"  ❌ Erro no Distrito {dist_num}: {e}")

    conn.close()
    print(f"\n🎉 Vitória na Califórnia! Total de {inseridas} câmeras de VÍDEO AO VIVO (.m3u8) adicionadas!")

if __name__ == "__main__":
    main()
