#!/usr/bin/env python3
import sys
import httpx
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

# Lista de servidores de streaming do Maryland
STRMR_HOSTS = [f"strmr{i}.sha.maryland.gov" for i in range(1, 9)]

def testar_stream(feed_id: str) -> str:
    """Testa os servidores strmr para achar o que responde."""
    for host in STRMR_HOSTS:
        url = f"https://{host}/rtplive/{feed_id}/playlist.m3u8"
        try:
            # Usa um timeout curto para não travar
            r = httpx.head(url, timeout=3, verify=False) # verify=False para ignorar erro de SSL
            if r.status_code == 200:
                return url
        except Exception:
            continue
    return None

def harvest_maryland():
    print("[Maryland] Buscando câmeras via ArcGIS...")
    url_api = "https://mdgeodata.md.gov/imap/rest/services/Transportation/MD_TrafficCameras/MapServer/0/query?where=1%3D1&outFields=*&f=json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = httpx.get(url_api, headers=headers, timeout=30)
        r.raise_for_status()
        dados = r.json()
    except Exception as e:
        print(f"  !! Erro ao acessar a API: {e}")
        return []

    features = dados.get("features", [])
    print(f"  -> {len(features)} câmeras brutas encontradas.")

    # Prepara a lista de câmeras para testar os streams em paralelo
    cameras_raw = []
    for feat in features:
        attr = feat.get("attributes", {})
        feed_id = attr.get("feedID")
        lat = attr.get("lat")
        lon = attr.get("long")
        nome = attr.get("location") or attr.get("description") or "Maryland Camera"
        
        if feed_id and lat and lon:
            cameras_raw.append({
                "feed_id": feed_id,
                "nome": nome,
                "lat": float(lat),
                "lon": float(lon),
                "county": attr.get("county", "Maryland"),
            })

    print(f"  -> Testando streams para {len(cameras_raw)} câmeras (pode demorar um pouco)...")

    cameras = []
    # Usa ThreadPool para testar vários ao mesmo tempo (acelera muito)
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Mapeia feed_id para a URL que funcionou
        resultados = list(executor.map(lambda c: (c, testar_stream(c["feed_id"])), cameras_raw))
        
        for c, stream_url in resultados:
            if stream_url:
                cameras.append({
                    "slug": f"maryland-{c['feed_id']}",
                    "nome": c["nome"],
                    "cidade": c["county"],
                    "bairro": "Maryland",
                    "regiao": "Maryland",
                    "pais": "Estados Unidos",
                    "codigo_pais": "US",
                    "latitude": c["lat"],
                    "longitude": c["lon"],
                    "categoria": "Transito",
                    "fonte": "MDOT CHART",
                    "pagina_oficial": f"https://chart.maryland.gov/video/video.php?feed={c['feed_id']}",
                    "stream_url": stream_url,
                    "tipo_stream": "hls",
                    "autorizada": True,
                    "pode_retransmitir": True,
                    "online": True,
                    "origem": "maryland_chart",
                    "origem_id": c["feed_id"],
                    "video_id": None,
                })

    print(f"  -> {len(cameras)} câmeras com stream HLS válido.")
    return cameras

if __name__ == "__main__":
    cams = harvest_maryland()
    if cams:
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
