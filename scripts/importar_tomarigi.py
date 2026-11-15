import sqlite3
from datetime import datetime, timezone
from curl_cffi import requests

DB_PATH = "data/cameras.db"
BASE_URL = "https://tomarigi.me"
ENDPOINT = "/api/japan-map-data"

CATEGORIAS = {
    "bousai": "Clima / Monitoramento",
    "nature": "Natureza",
    "city": "Cidade",
    "traffic": "Trânsito",
    "rail": "Ferrovia",
    "airport": "Aeroporto",
    "sea": "Praia / Mar",
    "mountain": "Montanha",
    "animal": "Animais",
}

def main():
    print("🇯🇵 Iniciando sessão no Tomarigi...")
    s = requests.Session(impersonate="chrome")
    s.get(BASE_URL, timeout=20)

    headers = {
        "Referer": f"{BASE_URL}/",
        "Accept": "application/json",
    }
    resp = s.get(f"{BASE_URL}{ENDPOINT}", headers=headers, timeout=30)
    resp.raise_for_status()
    dados = resp.json()

    spots = dados.get("spots", [])
    print(f"📦 Total recebido da API: {len(spots)} câmeras")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    inseridas = 0
    ignoradas_offline = 0
    duplicadas = 0

    for spot in spots:
        if not spot.get("is_live", True):
            ignoradas_offline += 1
            continue

        origem_id = str(spot.get("id", "")).strip()
        video_id = str(spot.get("video_id", "")).strip()
        nome = str(spot.get("name", "")).strip()
        lat = spot.get("lat")
        lng = spot.get("lng")

        if not origem_id or not video_id or not nome or lat is None or lng is None:
            continue

        cursor.execute(
            "SELECT id FROM cameras WHERE (origem = 'tomarigi' AND origem_id = ?) OR video_id = ?",
            (origem_id, video_id),
        )
        if cursor.fetchone():
            duplicadas += 1
            continue

        slug = f"jp-tomarigi-{origem_id[:16]}"
        cat_raw = str(spot.get("category", "")).lower()
        categoria = CATEGORIAS.get(cat_raw, "Geral")
        canal = str(spot.get("channel_title") or "YouTube Live").strip()
        fonte = f"Tomarigi / {canal}"[:200]

        embed_url = f"https://youtube.com{video_id}?autoplay=1&mute=1"
        pagina_oficial = f"https://youtube.com{video_id}"

        cursor.execute(
            """
            INSERT INTO cameras (
                slug, nome, cidade, bairro, latitude, longitude,
                categoria, fonte, pagina_oficial, stream_url, tipo_stream,
                autorizada, pode_retransmitir, online, ultima_verificacao,
                regiao, status, url_stream, pais, codigo_pais,
                origem, origem_id, video_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                nome[:200],
                "Japão",
                "Geral",
                float(lat),
                float(lng),
                categoria,
                fonte,
                pagina_oficial,
                embed_url,
                "iframe",
                1,
                1,
                1,
                agora,
                "Ásia",
                "ativo",
                embed_url,
                "Japão",
                "JP",
                "tomarigi",
                origem_id,
                video_id,
            ),
        )
        inseridas += 1

    conn.commit()
    conn.close()

    print(f"✅ Importação concluída!")
    print(f"   • Novas inseridas: {inseridas}")
    print(f"   • Ignoradas (offline na API): {ignoradas_offline}")
    print(f"   • Já existentes/duplicadas: {duplicadas}")

if __name__ == "__main__":
    main()
