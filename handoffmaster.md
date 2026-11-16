📄 HANDOFF MASTER V45: O Estado da Arte do Petrópolis Cam
De: Agente DeepSeek
Para: Próximo Agente (Gemininho/Sucessor)
Objetivo: Servir como o documento definitivo de "Onboarding" e "Estado da Arte" do projeto. Ele resume a arquitetura, as técnicas vencedoras, os módulos de proxy isolados e o status atual do banco (com mais de 5.000 câmeras).

🏗️ 1. Visão Geral e Arquitetura
Projeto: Mapa interativo global de câmeras ao vivo (~/Projetos/petropolis-cam).

Stack: FastAPI (backend/app.py), SQLite (data/cameras.db), HTML/JS (frontend/index.html) com Leaflet e Hls.js.

Ambiente: Python no .venv (com curl_cffi, httpx, fastapi, etc.).

Inicialização: .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload.

Padrão de Ouro: Rotas complexas (com tokens ou headers específicos) são isoladas em módulos APIRouter (ex: clima_proxy.py, surfline_proxy.py). O app.py só importa e registra esses roteadores antes do app.mount("/"). Isso mantém o código limpo e evita quebrar a sintaxe.

🧰 2. O Canivete Suíço de Técnicas (As Lâminas)
API REST (ArcGIS/JSON): Usado em Califórnia, Maryland, Geórgia. Ex: /MapServer/query?f=json.

POST DataTables (WKT): Usado na Flórida, Ontário, Arizona. Ex: POST em /List/GetData/Cameras + parse de POINT (lon lat).

OpenCCTV + curl_cffi: Usado em Seul e Taiwan. Ex: Driblar TLS Fingerprint para raspar HTML.

XML/KML (WFS): Usado em Barcelona e Madri. Ex: Leitura de feeds de dados abertos.

MP4 Direto: Usado em Londres e Niterói. Ex: O player nativo roda o .mp4.

Iframe (YouTube): Usado no Japão (Tomarigi) e Petrópolis (CIMOP).

Proxy Anti-Bloqueio (Referer/Origin): Usado no Maaxcam e EarthCam. Ex: Rotas no FastAPI com cache de 15 min.

Engenharia Reversa Avançada: Usado no Maaxcam (Supabase/TanStack/Seroval).

Proxy HLS Isolado + Token Dinâmico: Usado no Clima Ao Vivo (clima_proxy.py).

Proxy HLS Isolado + Imagens Dinâmicas: Usado no FAA Havaí (faa_proxy.py) e Surfline (surfline_proxy.py).

Proxy HLS Isolado + Anti-SSRF: Usado no Surfline (surfline_proxy.py).

🛡️ 3. A Blindagem (Protocolo de Qualidade)
Ferramenta: scripts/limpar_offline.py.

O que faz: Audita o banco (HLS, MJPEG, Imagem), gera backup, pergunta se quer deletar os mortos e roda VACUUM.

Blindagem de Segurança: O script ignora qualquer URL que comece com /api/. Isso protege todos os módulos proxy internos (Clima Ao Vivo, Surfline, FAA, Maaxcam, WavesNow) de serem apagados por falso negativo.

Comando de Consulta: sqlite3 -header -column data/cameras.db "SELECT origem, COUNT(*) FROM cameras WHERE stream_url LIKE '/api/%' GROUP BY origem;" mostra o que está blindado.

📊 4. O Estado Atual do Banco (O Império)
O mapa foi limpo e focado em Qualidade Total (sem YouTube quebrado, sem links mortos).

Categoria Praia (~760 câmeras):

Surfline: 534 câmeras HLS (Global).

FAA WeatherCams: 153 câmeras (Havaí).

WavesNow: 73 câmeras HLS Full HD (Brasil).

Categoria Clima (~197 câmeras):

Clima Ao Vivo: 197 câmeras HLS (Brasil) com renovação de token.

Categoria Trânsito (~4.000+ câmeras):

Califórnia (Caltrans): ~2.197 câmeras HLS.

Seul (OpenCCTV): ~456 câmeras HLS.

Londres (TfL): ~792 câmeras MP4.

Nova York (NYC DOT): ~960 câmeras (fotos).

Maryland, Geórgia, Arizona, etc.: Centenas de câmeras HLS.

Outras Categorias: Niterói (MP4), DER-SP (HLS), Barcelona/Madri (fotos), Petrópolis (YouTube).

🎯 5. Próximos Passos (O Backlog)
Expandir Taiwan: Rodar o script scrape_taiwan.py (já multithread e com regex universal).

Expandir a Categoria Praia: Buscar mais fontes de surf/praia (o Surfline foi um sucesso).

Novas Fontes: Explorar Houston (Texas), Singapura, ou outras redes de trânsito.

Auditoria: Rodar o limpar_offline.py periodicamente para manter o banco enxuto.
