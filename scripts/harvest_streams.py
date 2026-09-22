import sqlite3
import requests
import os
import re

# Caminho para o banco de dados do projeto
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cameras.db')

# Nossos feeds de teste com os dados que já conhecemos
CANDIDATE_STREAMS = [
    {
        "nome": "Trânsito Centro - Petrópolis",
        "regiao": "Petrópolis (Local)",
        "cidade": "Petrópolis",
        "bairro": "Centro",
        "categoria": "Trânsito",
        "fonte": "Mux Test",
        "tipo_stream": "hls",
        "latitude": -22.5044,
        "longitude": -43.1729,
        "stream_url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
    },
    {
        "nome": "Times Square - Nova York",
        "regiao": "Global - EUA",
        "cidade": "Nova York",
        "bairro": "Manhattan",
        "categoria": "Turismo",
        "fonte": "Sample Videos",
        "tipo_stream": "hls",
        "latitude": 40.7580,
        "longitude": -73.9855,
        "stream_url": "https://sample-videos.com/video123/hls/big-buck-bunny.m3u8"
    },
    {
        "nome": "Shibuya Crossing - Tóquio",
        "regiao": "Global - Ásia",
        "cidade": "Tóquio",
        "bairro": "Shibuya",
        "categoria": "Trânsito",
        "fonte": "Akamai",
        "tipo_stream": "hls",
        "latitude": 35.6595,
        "longitude": 139.7004,
        "stream_url": "https://cph-p2s-kclq.akamai.net/hls/live/2000341/test/master.m3u8"
    }
]

def slugify(text):
    """Transforma o nome em um identificador amigável (slug)."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def validar_stream(url):
    """Verifica rapidamente se o link responde via HTTP."""
    try:
        response = requests.head(url, timeout=5)
        if 200 <= response.status_code < 400: return True
    except:
        try:
            response = requests.get(url, timeout=5, stream=True)
            if 200 <= response.status_code < 400: return True
        except: pass
    return False

def injetar_cameras_dinamico():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔍 Fazendo engenharia reversa na estrutura do banco de dados...")
    cursor.execute("PRAGMA table_info(cameras)")
    schema = cursor.fetchall()
    
    if not schema:
        print("⚠️ Tabela 'cameras' não encontrada! Verifique se o banco original está na pasta correta.")
        return

    # Mapeia as regras de cada coluna do seu banco
    colunas_db = {}
    for col in schema:
        # col = (cid, name, type, notnull, default_value, pk)
        nome_col = col[1]
        colunas_db[nome_col] = {
            "tipo": col[2].upper() if col[2] else "TEXT",
            "obrigatoria": bool(col[3]),
            "is_pk": bool(col[5])
        }

    print("🚀 Iniciando varredura dinâmica dos streams...")
    sucessos = 0

    for cam in CANDIDATE_STREAMS:
        print(f"Testando: {cam['nome']}...", end=" ")
        
        is_active = validar_stream(cam['stream_url'])
        cam['status'] = 'ativo' if is_active else 'inativo'
        cam['slug'] = slugify(cam['nome'])
        
        if is_active:
            print("✅ [Online]")
            sucessos += 1
        else:
            print("⚠️ [Inativo]")

        # Monta os dados mesclando o que temos com o que o banco exige
        dados_para_inserir = {}
        for nome_col, regras in colunas_db.items():
            if regras["is_pk"]:
                continue  # Pula o ID (auto-incremento)

            if nome_col in cam:
                # Se sabemos o valor (ex: nome, latitude, stream), usamos ele
                dados_para_inserir[nome_col] = cam[nome_col]
            else:
                # Se o banco exige algo que não sabemos, injetamos um valor "coringa" seguro
                if regras["obrigatoria"]:
                    if "INT" in regras["tipo"] or "BOOL" in regras["tipo"]:
                        dados_para_inserir[nome_col] = 1 # Para campos como autorizada, pode_retransmitir
                    elif "REAL" in regras["tipo"] or "FLOAT" in regras["tipo"]:
                        dados_para_inserir[nome_col] = 0.0
                    else:
                        dados_para_inserir[nome_col] = "N/A"
                else:
                    dados_para_inserir[nome_col] = None

        colunas = list(dados_para_inserir.keys())
        valores = list(dados_para_inserir.values())

        # Verifica se já existe para fazer UPDATE ou INSERT
        cursor.execute("SELECT id FROM cameras WHERE nome = ?", (cam['nome'],))
        row = cursor.fetchone()

        if row:
            # Query Dinâmica de UPDATE
            set_clause = ", ".join([f"{c} = ?" for c in colunas])
            query = f"UPDATE cameras SET {set_clause} WHERE nome = ?"
            cursor.execute(query, valores + [cam['nome']])
        else:
            # Query Dinâmica de INSERT
            cols_clause = ", ".join(colunas)
            placeholders = ", ".join(["?"] * len(colunas))
            query = f"INSERT INTO cameras ({cols_clause}) VALUES ({placeholders})"
            cursor.execute(query, valores)

    conn.commit()
    conn.close()
    print(f"\n✨ Operação concluída com sucesso! Banco dominado. {sucessos}/{len(CANDIDATE_STREAMS)} inseridos.")

if __name__ == '__main__':
    injetar_cameras_dinamico()