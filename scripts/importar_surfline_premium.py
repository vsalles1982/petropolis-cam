#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Importador de câmeras PREMIUM do Surfline -> data/cameras.db
=============================================================
Fluxo:
  1. Consulta a API interna do Surfline (/kbyg/mapview) com curl_cffi
     (impersonate="chrome") varrendo uma grade de bounding boxes regionais
     (Havaí, Califórnia, Austrália, Europa, Ásia, etc.).
  2. Seleciona SOMENTE as câmeras com isPremium == True.
  3. Valida cada stream .m3u8 com os headers Referer/Origin exigidos pelo
     CloudFront (cdn-surfline.com). 200 OK + conteúdo começando com #EXTM3U.
  4. Insere no SQLite com os mesmos campos do padrão 'surfline', porém:
       - origem      = 'surfline_premium'
       - origem_id   = id da câmera (não do spot)
       - slug        = 'slp-<camera_id>'
       - stream_url  = '/api/surfline_premium/stream?url=<encoded>'
         (rota protegida por anti-SSRF no surfline_premium_proxy.py)
Saída no console: premium encontradas, validadas OK, offline/descartadas,
já existentes e inseridas no banco.

Uso:
    .venv/bin/python scripts/importar_surfline_premium.py [--sem-validar]
"""
import argparse
import sqlite3
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cameras.db"
MAPVIEW_URL = "https://services.surfline.com/kbyg/mapview"
ORIGEM = "surfline_premium"
SITE_BASE = "https://www.surfline.com"
CDN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": SITE_BASE + "/",
    "Origin": SITE_BASE,
}
MAX_WORKERS = 3            # varredura da API do mapview (sensível a rate-limit)
VALIDATION_WORKERS = 10    # validação HLS no CDN (tolera paralelismo)
SLEEP_ENTRE_BBOX = 1.0
RETRY_403_BACKOFF = [3, 8, 20]  # segundos entre tentativas em caso de 403/rate-limit

# ----------------------------------------------------------------------------
# Grade de regiões: (nome, south, west, north, east, pais, codigo_pais, regiao)
# A primeira caixa que contiver o ponto (lat, lon) define o país/região.
# As mesmas caixas (expandidas em 1°) servem para varrer a API.
# Ordenar por especificidade: caixas pequenas/precisas primeiro.
# ----------------------------------------------------------------------------
REGIOES = [
    # --- EUA / Havaí ---------------------------------------------------------
    ("Havaí",               18.0, -161.5,  29.0, -154.0, "Estados Unidos", "US", "HI"),
    ("Alasca",              51.0, -170.0,  61.0, -140.0, "Estados Unidos", "US", "CA/West"),
    ("Costa Oeste EUA",     32.0, -125.0,  49.5, -116.5, "Estados Unidos", "US", "CA/West"),
    ("Costa Leste/Golfo",   23.5,  -99.0,  49.5,  -66.5, "Estados Unidos", "US", "East/FL"),
    ("Bermuda",             31.8,  -65.5,  32.8,  -64.4, "Bermuda", "BM", "Caribe"),
    # --- México / América Central / Caribe -----------------------------------
    ("México Caribe",       17.5,  -92.0,  22.0,  -86.7, "México", "MX", "Caribe/MX"),
    ("Baja México",         22.0, -116.0,  32.3, -109.0, "México", "MX", "Caribe/MX"),
    ("Guatemala",           13.5,  -94.5,  14.5,  -90.5, "Guatemala", "GT", "Caribe/MX"),
    ("El Salvador",         12.8,  -92.0,  14.6,  -87.7, "El Salvador", "SV", "Caribe/MX"),
    ("Honduras/Nicarágua",  11.5,  -87.0,  17.0,  -82.5, "América Central & Caribe", "NI", "Caribe/MX"),
    ("Costa Rica",           8.0,  -88.0,  11.5,  -82.5, "Costa Rica", "CR", "Caribe/MX"),
    ("Panamá",               7.0,  -83.0,   9.8,  -77.0, "Panamá", "PA", "Caribe/MX"),
    ("Cuba",                19.5,  -85.5,  23.5,  -74.0, "Cuba", "CU", "Caribe"),
    ("Jamaica",             17.5,  -78.6,  18.8,  -76.0, "Jamaica", "JM", "Caribe"),
    ("Rep. Dominicana",     17.5,  -72.5,  20.0,  -68.0, "República Dominicana", "DO", "Caribe"),
    ("Turks e Caicos",      21.0,  -72.6,  22.0,  -71.0, "Turks e Caicos", "TC", "Caribe"),
    ("Bahamas",             20.5,  -80.0,  27.5,  -72.5, "Bahamas", "BS", "Caribe"),
    ("Porto Rico",          17.8,  -67.5,  18.6,  -65.0, "Porto Rico", "PR", "Caribe"),
    ("Barbados",            13.0,  -59.8,  13.5,  -59.3, "Barbados", "BB", "Caribe"),
    ("Caribe (fallback)",   14.0,  -74.0,  24.0,  -60.0, "América Central & Caribe", "MX", "Caribe/MX"),
    # --- América do Sul -------------------------------------------------------
    ("Equador",             -5.5,  -82.0,   2.0,  -75.0, "Equador", "EC", "Pacífico Sul"),
    ("Peru",               -18.5,  -81.5,  -2.0,  -70.0, "Peru", "PE", "Pacífico Sul"),
    ("Chile",              -50.0,  -78.0, -17.0,  -66.0, "Chile", "CL", "Pacífico Sul"),
    ("Brasil",             -35.0,  -55.0,   5.5,  -30.0, "Brasil", "BR", "Brasil"),
    ("Uruguai/Argentina",  -40.0,  -65.0, -30.0,  -48.0, "Argentina", "AR", "Atlântico Sul"),
    # --- Europa ---------------------------------------------------------------
    ("Canárias",            27.5,  -18.5,  29.5,  -13.0, "Espanha", "ES", "Europa"),
    ("Madeira/Açores",      30.0,  -31.5,  39.0, -13.0, "Portugal", "PT", "Europa"),
    ("Portugal",            36.5,  -10.0,  42.5,   -6.0, "Portugal", "PT", "Europa"),
    ("Irlanda",             51.0,  -11.0,  55.6,   -5.5, "Irlanda", "IE", "Europa"),
    ("Reino Unido",         49.8,   -6.5,  59.5,    2.5, "Reino Unido", "GB", "Europa"),
    ("Islândia",            63.0,  -25.0,  67.0,  -13.0, "Islândia", "IS", "Europa"),
    ("Espanha",             35.5,  -10.0,  44.0,    4.5, "Espanha", "ES", "Europa"),
    ("Marrocos",            27.0,  -13.5,  35.4,   -1.0, "Marrocos", "MA", "África do Norte"),
    ("França Atlântica",    43.0,   -2.5,  51.5,    8.5, "França", "FR", "Europa"),
    ("França Mediterrâneo", 42.8,    3.0,  44.0,    7.6, "França", "FR", "Europa"),
    ("Itália",              37.5,    8.5,  46.5,   18.5, "Itália", "IT", "Europa"),
    ("Malta",               35.7,   14.1,  36.0,   14.7, "Malta", "MT", "Europa"),
    ("Croácia/Adriático",   42.0,   13.5,  45.8,   19.5, "Croácia", "HR", "Europa"),
    ("Grécia",              35.5,   19.5,  41.0,   28.0, "Grécia", "GR", "Europa"),
    ("Chipre",              34.5,   32.0,  35.8,   34.8, "Chipre", "CY", "Europa"),
    ("Turquia",             36.0,   26.0,  42.0,   44.5, "Turquia", "TR", "Europa"),
    ("Dinamarca",           54.5,    8.0,  58.0,   13.0, "Dinamarca", "DK", "Europa"),
    ("Noruega/Suécia",      57.5,    4.5,  71.5,   25.0, "Noruega", "NO", "Europa"),
    ("Israel",              29.5,   32.0,  33.5,   35.5, "Israel", "IL", "Oriente Médio"),
    # --- África / Índico ------------------------------------------------------
    ("Cabo Verde",          14.5,  -25.5,  17.5,  -22.0, "Cabo Verde", "CV", "África do Norte"),
    ("Senegal",             13.5,  -18.0,  16.5,  -16.0, "Senegal", "SN", "África do Norte"),
    ("África do Sul",      -35.0,   17.0, -22.0,   33.0, "África do Sul", "ZA", "ZA"),
    ("Moçambique",         -27.0,   32.0, -10.0,   41.0, "Moçambique", "MZ", "África do Sul"),
    ("Reunião",            -21.5,   55.0, -20.8,   56.0, "Reunião (França)", "RE", "Índico"),
    ("Maurício",           -20.6,   57.2, -19.8,   58.0, "Maurício", "MU", "Índico"),
    ("Maldivas",            -1.5,   72.0,   8.0,   74.5, "Maldivas", "MV", "Índico"),
    ("Sri Lanka",            5.5,   79.0,  10.0,   82.5, "Sri Lanka", "LK", "Índico"),
    ("Índia",                7.5,   72.0,  20.0,   88.0, "Índia", "IN", "Índico"),
    # --- Ásia -----------------------------------------------------------------
    ("Indonésia",          -11.5,   94.0,   7.0,  122.0, "Indonésia", "ID", "Ásia/Indo"),
    ("Tailândia",            6.0,   97.0,  13.0,  106.0, "Tailândia", "TH", "Ásia/Indo"),
    ("Vietnã",               8.0,  104.0,  12.5,  110.5, "Vietnã", "VN", "Ásia/Indo"),
    ("Filipinas",            4.0,  115.0,  19.5,  127.0, "Filipinas", "PH", "Ásia/Indo"),
    ("Taiwan",              21.5,  118.0,  25.5,  122.5, "Taiwan", "TW", "Ásia/Indo"),
    ("China/Hong Kong",     18.0,  107.5,  24.0,  120.5, "China", "CN", "Ásia/Indo"),
    ("Coreia do Sul",       33.0,  124.0,  39.0,  130.0, "Coreia do Sul", "KR", "Ásia/Indo"),
    ("Japão",               24.0,  122.0,  46.0,  146.0, "Japão", "JP", "Ásia/Indo"),
    # --- Oceania / Pacífico ---------------------------------------------------
    ("Guam",                12.5,  143.5,  14.0,  145.0, "Guam (EUA)", "GU", "Pacífico Norte"),
    ("Austrália",          -44.0,  112.0, -10.0,  155.5, "Austrália", "AU", "AU"),
    ("Nova Caledônia",     -23.0,  163.5, -20.0,  168.0, "Nova Caledônia (França)", "NC", "Pacífico Sul"),
    ("Vanuatu",            -20.5,  166.0, -15.0,  168.0, "Vanuatu", "VU", "Pacífico Sul"),
    ("Fiji (Leste)",       -19.5,  176.0, -16.0,  180.0, "Fiji", "FJ", "Pacífico Sul"),
    ("Fiji (Oeste)",       -19.5, -180.0, -16.0, -177.0, "Fiji", "FJ", "Pacífico Sul"),
    ("Tonga",              -22.0, -176.0, -18.0, -173.5, "Tonga", "TO", "Pacífico Sul"),
    ("Samoa",              -14.5, -173.0, -13.3, -171.5, "Samoa", "WS", "Pacífico Sul"),
    ("Taiti",              -18.5, -150.5, -17.3, -149.0, "Taiti (França)", "PF", "Pacífico Sul"),
    ("Nova Zelândia",      -47.5,  166.0, -34.0,  179.0, "Nova Zelândia", "NZ", "NZ"),
]

FALLBACK = ("Desconhecido", "", "Geral")


def localizar_regiao(lat: float, lon: float):
    """Retorna (pais, codigo_pais, regiao) da primeira caixa que contém o ponto."""
    for _, s, w, n, e, pais, cc, regiao in REGIOES:
        if s <= lat <= n and w <= lon <= e:
            return pais, cc, regiao
    return FALLBACK


# ----------------------------------------------------------------------------
# 1) Varredura da API
# ----------------------------------------------------------------------------
def fetch_bbox(sess, nome, s, w, n, e, tentativas=4):
    qs = f"south={s}&west={w}&north={n}&east={e}"
    for i in range(tentativas):
        try:
            r = sess.get(f"{MAPVIEW_URL}?{qs}", impersonate="chrome",
                         headers=CDN_HEADERS, timeout=30)
            if r.status_code == 200:
                data = r.json()
                spots = (data.get("data") or {}).get("spots") or []
                return nome, spots, None
            if r.status_code in (403, 429):  # rate-limit do CloudFront/WAF
                if i < tentativas - 1:
                    backoff = RETRY_403_BACKOFF[min(i, len(RETRY_403_BACKOFF) - 1)]
                    print(f"  [403] {nome}: aguardando {backoff}s antes de tentar de novo...")
                    time.sleep(backoff)
                    continue
                return nome, [], f"HTTP {r.status_code} (persistente)"
            return nome, [], f"HTTP {r.status_code}"
        except Exception as exc:
            if i == tentativas - 1:
                return nome, [], repr(exc)[:120]
            time.sleep(1.5 * (i + 1))
    return nome, [], "esgotou tentativas"


def varrer_api():
    """Varre as caixas regionais e devolve spots deduplicados."""
    sess = requests.Session()
    spots_por_id = {}
    falhas = []
    caixas = []
    for nome, s, w, n, e, *_ in REGIOES:
        # expande 1° para pegar spots na borda, clampa nos limites válidos
        caixas.append((nome, max(-60.0, s - 1.0), max(-180.0, w - 1.0),
                       min(70.0, n + 1.0), min(180.0, e + 1.0)))

    print(f"[API] Varrendo {len(caixas)} bounding boxes (spots premium + grátis)...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = [pool.submit(fetch_bbox, sess, nome, s, w, n, e)
                   for nome, s, w, n, e in caixas]
        for fut in as_completed(futuros):
            nome, spots, erro = fut.result()
            novos = 0
            for sp in spots:
                sid = sp.get("_id")
                if not sid or sid in spots_por_id:
                    continue
                spots_por_id[sid] = sp
                novos += 1
            if erro:
                falhas.append((nome, erro))
                print(f"  [ERRO] {nome}: {erro}")
            elif novos:
                print(f"  [OK] {nome}: +{novos} spots")
            time.sleep(SLEEP_ENTRE_BBOX)
    if falhas:
        print(f"[API] {len(falhas)} caixas com falha (spots nelas ficam de fora desta rodada).")
    print(f"[API] Total de spots únicos: {len(spots_por_id)}")
    return list(spots_por_id.values())


# ----------------------------------------------------------------------------
# 2) Filtro premium
# ----------------------------------------------------------------------------
def filtrar_premium(spots):
    premium = []
    for sp in spots:
        lat, lon = sp.get("lat"), sp.get("lon")
        if lat is None or lon is None:
            continue
        for cam in (sp.get("cameras") or []):
            if not cam.get("isPremium"):
                continue  # grátis já está no banco; só nos interessa premium
            stream = cam.get("streamUrl") or ""
            if ".m3u8" not in stream:
                continue
            premium.append({
                "cam_id": cam.get("_id", ""),
                "titulo": (cam.get("title") or "").strip(),
                "spot_id": sp.get("_id", ""),
                "spot_nome": (sp.get("name") or "").strip() or "Praia",
                "lat": lat, "lon": lon,
                "stream": stream,
            })
    # dedupe por camera id (spot pode aparecer em caixas sobrepostas)
    vistos, unicos = set(), []
    for c in premium:
        if c["cam_id"] and c["cam_id"] not in vistos:
            vistos.add(c["cam_id"])
            unicos.append(c)
    print(f"[FILTRO] Câmeras premium com .m3u8: {len(unicos)}")
    return unicos


# ----------------------------------------------------------------------------
# 3) Validação dos streams
# ----------------------------------------------------------------------------
def validar_stream(sess, cam):
    """True se a playlist responde 200 e começa com #EXTM3U."""
    try:
        r = sess.get(cam["stream"], impersonate="chrome",
                     headers=CDN_HEADERS, timeout=12)
        if r.status_code == 200 and r.text.lstrip().startswith("#EXTM3U"):
            return True, None
        return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, repr(exc)[:100]


def validar_todos(cams):
    if not cams:
        return [], []
    ok, offline = [], []
    sess = requests.Session()
    print(f"[VALIDAÇÃO] Testando {len(cams)} playlists .m3u8...")
    with ThreadPoolExecutor(max_workers=VALIDATION_WORKERS) as pool:
        futuros = {pool.submit(validar_stream, sess, c): c for c in cams}
        for i, fut in enumerate(as_completed(futuros), 1):
            cam = futuros[fut]
            valido, motivo = fut.result()
            if valido:
                ok.append(cam)
            else:
                cam["motivo"] = motivo
                offline.append(cam)
            if i % 50 == 0:
                print(f"  ... {i}/{len(cams)} testadas (OK: {len(ok)}, offline: {len(offline)})")
    print(f"[VALIDAÇÃO] OK: {len(ok)} | Offline/descartadas: {len(offline)}")
    return ok, offline


# ----------------------------------------------------------------------------
# 4) Inserção no SQLite
# ----------------------------------------------------------------------------
INSERT_SQL = """
INSERT OR IGNORE INTO cameras (
    slug, nome, cidade, bairro, latitude, longitude, categoria, fonte,
    pagina_oficial, stream_url, tipo_stream, autorizada, pode_retransmitir,
    online, ultima_verificacao, regiao, status, url_stream, pais,
    codigo_pais, origem, origem_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def inserir(cams):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ja_existentes = {row[0] for row in cur.execute(
        "SELECT origem_id FROM cameras WHERE origem = ?", (ORIGEM,))}

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    linhas = []
    for c in cams:
        if c["cam_id"] in ja_existentes:
            continue
        pais, cc, regiao = localizar_regiao(c["lat"], c["lon"])
        proxied = f"/api/surfline_premium/stream?url={urllib.parse.quote(c['stream'], safe='')}"
        linhas.append((
            f"slp-{c['cam_id']}",
            f"{c['titulo']} (Surfline Premium)"[:200],
            c["spot_nome"][:100],
            "Surfline",
            c["lat"], c["lon"],
            "Praia", "Surfline",
            f"{SITE_BASE}/surf-report/{c['spot_id']}",
            proxied,
            "hls",
            1, 1,
            1,  # online: validada agora
            agora,
            regiao, "ativo", proxied,
            pais, cc,
            ORIGEM, c["cam_id"],
        ))

    antes = conn.total_changes
    cur.executemany(INSERT_SQL, linhas)
    conn.commit()
    inseridas = conn.total_changes - antes
    conn.close()
    return inseridas, len(linhas)


# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Importa câmeras premium do Surfline")
    parser.add_argument("--sem-validar", action="store_true",
                        help="Pula a validação HLS (insere sem testar)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[ERRO] Banco não encontrado: {DB_PATH}")
        sys.exit(1)

    spots = varrer_api()
    premium = filtrar_premium(spots)

    if args.sem_validar:
        ok, offline = premium, []
        print("[VALIDAÇÃO] Pulada (--sem-validar): todas serão inseridas.")
    else:
        ok, offline = validar_todos(premium)

    inseridas, candidatas = inserir(ok)
    ja_existentes = len(ok) - candidatas

    print("")
    print("=" * 60)
    print("RESUMO - Surfline Premium")
    print("=" * 60)
    print(f"Spots varridos na API:      {len(spots)}")
    print(f"Câmeras premium encontradas: {len(premium)}")
    print(f"Streams validados (200+M3U): {len(ok)}")
    print(f"Offline/descartadas:         {len(offline)}")
    print(f"Já existentes no banco:      {ja_existentes}")
    print(f"Inseridas agora:             {inseridas}")
    print("=" * 60)
    if offline:
        print("Exemplos descartadas (até 5):")
        for c in offline[:5]:
            print(f"  - {c['titulo']}: {c.get('motivo')}")

    print("")
    print("Verificação (rode no terminal):")
    print('  sqlite3 -header -column data/cameras.db "SELECT origem, COUNT(*) '
          "FROM cameras WHERE origem LIKE 'surfline%' GROUP BY origem;\"")


if __name__ == "__main__":
    main()
