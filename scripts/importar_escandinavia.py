import sqlite3
from datetime import datetime, timezone
from curl_cffi import requests

DB_PATH = "data/cameras.db"
BASE_URL = "https://tomarigi.me"

FONTES = [
    {
        "endpoint": "/api/vegvesen-spots",
        "pais": "Noruega",
        "codigo_pais": "NO",
        "origem": "vegvesen",
        "fonte_nome": "Statens vegvesen (Noruega)",
        "prefixo_slug": "no-vegvesen",
    },
    {
        "endpoint": "/api/fintraffic-spots",
        "pais": "Finlândia",
        "codigo_pais": "FI",
        "origem": "fintraffic",
        "fonte_nome": "Fintraffic (Finlândia)",
        "prefixo_slug": "fi-fintraffic",
    },
]

def main():
    s = requests.Session(impersonate="chrome")
    s.get(BASE_URL, timeout=20)
    headers = {"Referer": f"{BASE_URL}/", "Accept": "application/json"}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for f in FONTES:
        print(f"🌍 Buscando {f['pais']} ({f['endpoint']})...")
        try:
            r = s.get(f"{BASE_URL}{f['endpoint']}", headers=headers, timeout=25)
            if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
                print(f"  ⚠️ Falha ou formato inesperado em {f['pais']}: HTTP {r.status_code}")
                continue
            data = r.json()
            spots = data.get("spots", data) if isinstance(data, dict) else data
        except Exception as e:
            print(f"  ⚠️ Erro ao baixar {f['pais']}: {e}")
            continue

        inseridas = 0
        for spot in spots:
            if not spot.get("is_live", True):
                continue

            origem_id = str(spot.get("id", "")).strip()
            nome = str(spot.get("name", "")).strip()
            lat = spot.get("lat")
            lng = spot.get("lng")
            media_url = spot.get("image_url") or spot.get("stream_url") or spot.get("embed_url")

            if not origem_id or not nome or lat is None or lng is None or not media_url:
                continue

            # Define tipo conforme extensão/campo (foto JPEG para marcador dourado ou stream)
            tipo_stream = "imagem" if spot.get("image_url") else "hls"
            slug = f"{f['prefixo_slug']}-{origem_id.replace('vegvesen-', '').replace('fintraffic-', '')}"[:100]
            pagina_oficial = spot.get("source_url") or media_url

            cur.execute(
                """
                INSERT OR IGNORE INTO cameras (
                    slug, nome, cidade, bairro, latitude, longitude,
                    categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                    autorizada, pode_retransmitir, online, ultima_verificacao,
                    regiao, status, url_stream, pais, codigo_pais,
                    origem, origem_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'Clima / Trânsito', ?, ?, ?, ?, 1, 1, 1, ?, 'Europa', 'ativo', ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    nome[:200],
                    f["pais"],
                    "Geral",
                    float(lat),
                    float(lng),
                    f["fonte_nome"],
                    pagina_oficial,
                    media_url,
                    tipo_stream,
                    agora,
                    media_url,
                    f["pais"],
                    f["codigo_pais"],
                    f["origem"],
                    origem_id,
                ),
            )
            if cur.rowcount > 0:
                inseridas += 1

        conn.commit()
        print(f"  ✅ {f['pais']}: {inseridas} novas câmeras inseridas (de {len(spots)} recebidas).")

    conn.close()

if __name__ == "__main__":
    main()
