#!/usr/bin/env python3
"""Coletor global de câmeras públicas — Windy, Tomarigi e Open Eagle Eye."""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cameras.db"
OEE_JSON = Path.home() / ".openeagleeye" / "cameras.json"


def slugify(texto: str) -> str:
    texto = texto.lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


# ===============================================================
# COLETOR 1: Windy
# ===============================================================
def harvest_windy(api_key: str, limite_por_regiao: int = 1000):
    base = "https://api.windy.com/webcams/api/v3/webcams"
    headers = {"x-windy-api-key": api_key}
    quadrantes = [(-90, -180, 0, 0), (-90, 0, 0, 180), (0, -180, 90, 0), (0, 0, 90, 180)]
    todos = []
    for lat_min, lon_min, lat_max, lon_max in quadrantes:
        print(f"[Windy] Quadrante ({lat_min},{lon_min}) -> ({lat_max},{lon_max})...")
        offset = 0
        coletados = 0
        while offset < limite_por_regiao:
            params = {"lang": "en", "limit": 50, "offset": offset,
                      "include": "location,categories,images,urls",
                      "bbox": f"{lat_min},{lon_min},{lat_max},{lon_max}"}
            try:
                r = httpx.get(base, headers=headers, params=params, timeout=60)
                r.raise_for_status()
                dados = r.json()
            except Exception as e:
                print(f"  !! Erro (offset={offset}): {e}")
                break
            webcams = dados.get("webcams", [])
            if not webcams:
                break
            todos.extend(webcams)
            coletados += len(webcams)
            print(f"  -> +{len(webcams)} (total: {coletados})")
            if len(webcams) < 50:
                break
            offset += 50
            time.sleep(1)
    cameras = []
    for w in todos:
        loc = w.get("location", {}) or {}
        cats = w.get("categories", []) or []
        cat_nome = cats[0].get("name") if cats else "Outros"
        cameras.append({
            "slug": f"windy-{w['webcamId']}",
            "nome": w.get("title") or "Sem nome",
            "cidade": loc.get("city") or "Localizacao aproximada",
            "bairro": loc.get("region") or "Nao informado",
            "regiao": loc.get("region"),
            "pais": loc.get("country"),
            "codigo_pais": loc.get("countryCode"),
            "latitude": float(loc.get("latitude") or 0),
            "longitude": float(loc.get("longitude") or 0),
            "categoria": cat_nome,
            "fonte": "Windy",
            "pagina_oficial": f"https://www.windy.com/webcams/{w['webcamId']}",
            "stream_url": (w.get("urls") or {}).get("player", ""),
            "tipo_stream": "iframe",
            "autorizada": True,
            "pode_retransmitir": False,
            "online": w.get("status") == "active",
            "origem": "windy",
            "origem_id": str(w["webcamId"]),
            "video_id": None,
        })
    return cameras


# ===============================================================
# COLETOR 2: Tomarigi
# ===============================================================
def harvest_tomarigi(url_api: str = "https://tomarigi.me/api/world-spots"):
    print(f"[Tomarigi] GET {url_api}")
    try:
        r = httpx.get(url_api, timeout=30, headers={
            "User-Agent": "PetropolisCam/0.3 (catalogo comunitario)"})
        r.raise_for_status()
        spots = r.json()
    except Exception as e:
        print(f"  !! Erro: {e}")
        return []
    print(f"  -> {len(spots)} spots brutos")
    CATEGORIAS = {
        "bousai": "Clima e prevencao", "city": "Cidades", "coast": "Praias e litoral",
        "nature": "Natureza", "other": "Outros", "animal": "Animais",
        "train": "Trens e ferrovias", "landmark": "Pontos turisticos", "airport": "Aeroportos",
    }
    cameras = []
    for spot in spots:
        if not spot.get("is_live"):
            continue
        video_id = str(spot["video_id"])
        cameras.append({
            "slug": f"tomarigi-{spot['id']}",
            "nome": str(spot.get("name", "Sem nome")),
            "cidade": "Localizacao aproximada",
            "bairro": "Nao informado",
            "regiao": None, "pais": None, "codigo_pais": None,
            "latitude": float(spot["lat"]),
            "longitude": float(spot["lng"]),
            "categoria": CATEGORIAS.get(spot.get("category"), "Outros"),
            "fonte": "Tomarigi / YouTube",
            "pagina_oficial": f"https://www.youtube.com/watch?v={video_id}",
            "stream_url": f"https://www.youtube.com/embed/{video_id}",
            "tipo_stream": "iframe",
            "autorizada": True,
            "pode_retransmitir": False,
            "online": True,
            "origem": "tomarigi",
            "origem_id": str(spot["id"]),
            "video_id": video_id,
        })
    return cameras


# ===============================================================
# COLETOR 3: Open Eagle Eye
# ===============================================================
PAISES = {
    "US": "Estados Unidos", "GB": "Reino Unido", "UK": "Reino Unido",
    "JP": "Japao", "BR": "Brasil", "CA": "Canada", "AU": "Australia",
    "DE": "Alemanha", "FR": "Franca", "IT": "Italia", "ES": "Espanha",
    "NL": "Paises Baixos", "NZ": "Nova Zelandia", "IE": "Irlanda",
    "NO": "Noruega", "SE": "Suecia", "FI": "Finlandia", "DK": "Dinamarca",
    "CH": "Suica", "AT": "Austria", "BE": "Belgica", "PT": "Portugal",
    "SG": "Singapura", "KR": "Coreia do Sul", "TW": "Taiwan", "HK": "Hong Kong",
    "MX": "Mexico", "AR": "Argentina", "CL": "Chile", "CO": "Colombia",
    "PL": "Polonia", "CZ": "Republica Tcheca", "GR": "Grecia", "TR": "Turquia",
    "IN": "India", "ZA": "Africa do Sul", "AE": "Emirados Arabes",
}

CATEGORIAS_OEE = {
    "city": "Cidades", "traffic": "Transito", "coast": "Praias e litoral",
    "beach": "Praias e litoral", "nature": "Natureza", "animal": "Animais",
    "landmark": "Pontos turisticos", "train": "Trens e ferrovias",
    "airport": "Aeroportos", "weather": "Clima e prevencao", "road": "Rodovia",
}


def harvest_openeagleeye(arquivo: Path = OEE_JSON):
    if not arquivo.exists():
        print(f"  !! Arquivo nao encontrado: {arquivo}")
        print("     Rode primeiro: openeagleeye")
        return []

    print(f"[OpenEagleEye] Lendo {arquivo}")
    with arquivo.open() as f:
        dados = json.load(f)

    if isinstance(dados, dict):
        for v in dados.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                dados = v
                break
        else:
            print("  !! Formato de JSON nao reconhecido")
            return []

    print(f"  -> {len(dados)} cameras brutas")

    cameras = []
    ignoradas = 0
    for c in dados:
        try:
            coords = c.get("coordinates") or {}
            lat = coords.get("lat") or coords.get("latitude") or 0
            lng = coords.get("lng") or coords.get("longitude") or coords.get("lon") or 0

            url = c.get("url") or c.get("snapshot_url") or c.get("image_url") or ""
            if not url:
                ignoradas += 1
                continue

            cam_id = str(c.get("id") or slugify(c.get("name", "sem-nome")))
            codigo_pais = (c.get("country") or "").upper()
            pais_nome = PAISES.get(codigo_pais, codigo_pais or "Nao informado")

            cat_raw = (c.get("category") or "other").lower()
            categoria = CATEGORIAS_OEE.get(cat_raw, c.get("category") or "Outros")

            cameras.append({
                "slug": f"eagleeye-{cam_id}",
                "nome": c.get("name") or "Sem nome",
                "cidade": c.get("city") or "Localizacao aproximada",
                "bairro": c.get("location") or "Nao informado",
                "regiao": c.get("location"),
                "pais": pais_nome,
                "codigo_pais": codigo_pais[:2] if codigo_pais else None,
                "latitude": float(lat),
                "longitude": float(lng),
                "categoria": categoria,
                "fonte": "Open Eagle Eye",
                "pagina_oficial": None,
                "stream_url": url,
                "tipo_stream": "imagem",
                "autorizada": True,
                "pode_retransmitir": False,
                "online": bool(c.get("verified", True)),
                "origem": "openeagleeye",
                "origem_id": cam_id,
                "video_id": None,
            })
        except Exception as e:
            print(f"  !! Erro em um item: {e}")
            continue

    print(f"  -> {len(cameras)} cameras normalizadas ({ignoradas} ignoradas sem URL)")
    return cameras


# ===============================================================
# GRAVAÇÃO
# ===============================================================
def gravar(cameras):
    if not cameras:
        print("Nada para gravar.")
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(cameras)")
    colunas_db = {row[1]: {"tipo": row[2], "obrigatoria": bool(row[3]), "pk": bool(row[5])}
                  for row in cursor.fetchall()}
    inseridas = atualizadas = 0
    for cam in cameras:
        dados = {}
        for nome_col, regras in colunas_db.items():
            if regras["pk"]:
                continue
            if nome_col in cam:
                dados[nome_col] = cam[nome_col]
            elif regras["obrigatoria"]:
                tipo = (regras["tipo"] or "").upper()
                if "INT" in tipo or "BOOL" in tipo:
                    dados[nome_col] = 1
                elif "REAL" in tipo or "FLOAT" in tipo:
                    dados[nome_col] = 0.0
                else:
                    dados[nome_col] = "N/A"
            else:
                dados[nome_col] = None
        cursor.execute("SELECT id FROM cameras WHERE origem = ? AND origem_id = ?",
                       (cam["origem"], cam["origem_id"]))
        existente = cursor.fetchone()
        cols = list(dados.keys())
        vals = list(dados.values())
        if existente:
            set_clause = ", ".join([f"{c} = ?" for c in cols])
            cursor.execute(f"UPDATE cameras SET {set_clause} WHERE id = ?", vals + [existente[0]])
            atualizadas += 1
        else:
            placeholders = ", ".join(["?"] * len(cols))
            cursor.execute(f"INSERT INTO cameras ({', '.join(cols)}) VALUES ({placeholders})", vals)
            inseridas += 1
    conn.commit()
    conn.close()
    print(f"\nOK Inseridas: {inseridas} | Atualizadas: {atualizadas} | Total: {len(cameras)}")


# ===============================================================
# CLI
# ===============================================================
def main():
    parser = argparse.ArgumentParser(description="Coletor global de cameras publicas")
    parser.add_argument("--fonte", choices=["windy", "tomarigi", "openeagleeye"], required=True)
    parser.add_argument("--api-key")
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.fonte == "windy":
        api_key = args.api_key or os.environ.get("WINDY_API_KEY")
        if not api_key:
            sys.exit("Defina WINDY_API_KEY no .env ou passe --api-key")
        print(f"Chave Windy carregada: {api_key[:8]}...")
        cameras = harvest_windy(api_key)
    elif args.fonte == "tomarigi":
        cameras = harvest_tomarigi()
    elif args.fonte == "openeagleeye":
        cameras = harvest_openeagleeye()
    else:
        sys.exit("Fonte invalida")

    if args.limite:
        cameras = cameras[:args.limite]

    print(f"\nTotal coletado: {len(cameras)}")
    if cameras:
        print("\nAmostra:")
        for c in cameras[:3]:
            print(f"  - {c['nome']} | {c['cidade']}, {c['pais']} | {c['categoria']} | {c['stream_url'][:60]}")

    if args.dry_run:
        print("\n[dry-run] Nada foi gravado.")
        return
    gravar(cameras)


if __name__ == "__main__":
    main()
