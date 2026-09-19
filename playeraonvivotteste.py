import os, sys, json, logging, urllib3, time, re, threading, subprocess
from flask import Flask, Response, request, render_template_string
from urllib.parse import urljoin, quote, unquote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from curl_cffi import requests as ImpersonateSession
    USE_CURL = True
except ImportError:
    import requests as ImpersonateSession
    USE_CURL = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    TEM_SELENIUM = True
except ImportError:
    TEM_SELENIUM = False

logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("MARCOS_TV")
logger.disabled = True

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 9999))

# ===== URL DO TERMUX (Serveo) — atualiza quando mudar =====
URL_TERMUX = os.environ.get("URL_TERMUX", "https://tvmrc1.serveousercontent.com")

PASTA_PERFIS = os.path.expanduser("./canais_dados")
os.makedirs(PASTA_PERFIS, exist_ok=True)

PROXIES = ["chrome120", "chrome110", "safari_15_5"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CANAIS_DISPONIVEIS = [
    "cazetv", "cazetv2", "cazetv3", "cazetv4", "cazetv5", "cazetv6",
    "combate", "dazn",
    "disneyplus", "disneyplus02", "disneyplus03", "disneyplus04", "disneyplus05", "disneyplus06", "disneyplus07", "disneyplus08", "disneyplus09",
    "espn", "espn2", "espn3", "espn4", "espn5", "espn6",
    "getv",
    "max", "max1", "max2", "max3", "max02", "max03", "max04", "max05", "max06",
    "nsports", "nossofutebol",
    "paramount", "paramount02", "paramount03", "paramount04", "paramount05", "paramount06", "paramount07", "paramountnetwork",
    "premiere", "premiere2", "premiere3", "premiere4", "premiere5", "premiere6", "premiere7", "premiere8",
    "primevideo1", "primevideo2",
    "sportv", "sportv2", "sportv3", "sportv4", "sportynet", "sportynet1", "sportynet2", "sportynet3",
    "ufcfightpass", "xsports", "band_sports", "canalgoat", "off",
    "24h_chaves", "24h_dragonballz", "24h_naruto", "24h_simpsons", "24h_todomundoodiaocris",
    "cartoonnetwork", "cartoonito", "discoverykids", "dreamworks", "gloob", "gloobinho", "nickjr", "nickelodeon", "tooncast", "tvratimbum",
    "animalplanet", "discoverychannel", "discoveryhh", "discoveryid", "discoveryscience", "discoverytheater", "discoveryturbo", "discoveryworld",
    "fishtv", "history", "history2",
    "ae", "amc", "amcseries", "axn", "adultswim", "cinemax", "comedycentral",
    "gnt", "hbo", "hbo2", "hbofamily", "hbomundi", "hboplus", "hbopop", "hbosignature", "hboxtreme",
    "hgtv", "megapix", "sony", "space", "starchannel", "studiouniversal",
    "tcm", "tlc", "tnt", "tntnovelas", "tntseries",
    "telecineaction", "telecinecult", "telecinefun", "telecinepipoca", "telecinepremium", "telecinetouch",
    "universal", "usa", "warner", "warnerchannel",
    "bandnews", "bandrj", "bandsp", "cnnbrasil", "globonews",
    "recordmg", "recordrj", "recordsp", "recorddf", "recordesp",
    "sbtrj", "sbtsp", "redetv",
    "aparecida", "cancaonova", "cultura",
    "globoam", "globoce", "globoes", "globomg", "globopb", "globope", "globorj", "globors", "globosp", "globodf", "globoesp",
    "mtv", "multishow", "foodnetwork", "masterchef", "playboy", "sexyhot",
    "amazonprime", "amazonprime02", "amazonprime03", "amazonprime04", "amazonprime05",
    "appletv01", "appletv02", "appletv03", "appletv04", "appletv05", "appletv06",
    "pt_abola", "pt_benficatv", "pt_canal11", "pt_eleven1", "pt_eleven2", "pt_eleven3",
    "pt_sporttv1", "pt_sporttv2", "pt_sporttv3", "pt_sporttv4", "pt_sporttv5", "pt_sporttv6", "pt_sporttv7",
    "globoplaynovelas"
]
CANAIS_DISPONIVEIS = list(dict.fromkeys(CANAIS_DISPONIVEIS))

def listar_perfis():
    try:
        return sorted([os.path.splitext(f)[0] for f in os.listdir(PASTA_PERFIS) if f.endswith('.json')])
    except Exception:
        return []

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    return r

@app.route('/')
def index():
    perfis = listar_perfis()
    canais_manuais_html = ""
    for p in perfis:
        canais_manuais_html += f'<div class="canal-item canal-manual" onclick="playCanal(\'{p}\')">{p}</div>'
    canais_fixos_html = ""
    for c in CANAIS_DISPONIVEIS:
        canais_fixos_html += f'<div class="canal-item" onclick="playCanal(\'{c}\')">{c}</div>'
    canais_html = canais_manuais_html + canais_fixos_html
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MARCOS TV</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
        <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
        <link href="https://unpkg.com/@videojs/themes@1/dist/city/index.css" rel="stylesheet">
        <style>
            :root { --bg:#0a0a0f; --card:#14141f; --border:#272738; --accent:#6c5ce7; --danger:#e74c3c; --warning:#e67e22; }
            * { box-sizing:border-box; margin:0; padding:0; }
            body { font-family:'Inter',sans-serif; background:var(--bg); color:#fff; padding:20px; }
            .container { max-width:1000px; margin:0 auto; }
            header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
            .brand { font-size:1.8em; font-weight:800; background:linear-gradient(135deg,#fff,#a29bfe); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
            .player-box { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px; margin-bottom:20px; }
            .video-js { width:100%; height:420px; border-radius:8px; }
            @media(max-width:768px){ .video-js { height:240px; } }
            .controls { display:flex; gap:10px; margin-top:12px; flex-wrap:wrap; }
            input { flex:1; min-width:200px; background:#0d0d14; border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff; outline:none; }
            button { border:none; padding:12px 20px; border-radius:8px; font-weight:600; cursor:pointer; color:#fff; transition:0.2s; }
            .btn-play { background:var(--accent); }
            .btn-canais { background:var(--warning); }
            button:hover { opacity:0.85; }
            .modal { display:none; position:fixed; z-index:9999; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.8); }
            .modal-content { background:var(--card); margin:5% auto; padding:20px; border:1px solid var(--border); border-radius:12px; width:90%; max-width:600px; max-height:80vh; overflow-y:auto; }
            .modal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; }
            .modal-title { font-size:1.2em; font-weight:600; }
            .close-btn { background:var(--danger); padding:8px 15px; border-radius:6px; cursor:pointer; }
            .canal-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(100px,1fr)); gap:8px; }
            .canal-item { background:#0d0d14; border:1px solid var(--border); padding:8px; border-radius:6px; text-align:center; cursor:pointer; font-size:0.8em; text-transform:uppercase; transition:0.2s; }
            .canal-item:hover { background:var(--accent); border-color:var(--accent); }
            .canal-manual { background:#1a1a2e; border-color:var(--accent); }
        </style>
    </head>
    <body>
        <div class="container">
            <header><div class="brand">MARCOS TV</div></header>
            <div class="player-box">
                <video id="player" class="video-js vjs-theme-city" controls preload="auto" playsinline></video>
                <div class="controls">
                    <input id="canal-input" placeholder="Nome do canal (ex: espn, tnt, warner)...">
                    <button class="btn-play" onclick="playModo()">PLAY</button>
                    <button class="btn-canais" onclick="abrirModal()">CANAIS</button>
                </div>
            </div>
        </div>
        <div id="modal-canais" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">LISTA DE CANAIS</div>
                    <button class="close-btn" onclick="fecharModal()">X</button>
                </div>
                <div class="canal-grid">{{ canais_html|safe }}</div>
            </div>
        </div>
        <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
        <script>
            var player = videojs('player');
            var URL_TERMUX = "{{ url_termux }}";

            function playModo() {
                var val = document.getElementById('canal-input').value.trim().toLowerCase();
                if(!val) return;
                carregarDirect('/play/' + val);
            }
            function playCanal(nome) {
                document.getElementById('canal-input').value = nome;
                carregarDirect('/play/' + nome);
                fecharModal();
            }
            function carregarDirect(path) {
                var urlFinal = URL_TERMUX + path;
                player.src({ src: urlFinal, type: 'application/x-mpegURL' });
                player.play();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
            function abrirModal() { document.getElementById('modal-canais').style.display = 'block'; }
            function fecharModal() { document.getElementById('modal-canais').style.display = 'none'; }
            window.onclick = function(event) {
                var modal = document.getElementById('modal-canais');
                if (event.target == modal) modal.style.display = 'none';
            }
        </script>
    </body>
    </html>
    ''', canais_html=canais_html, url_termux=URL_TERMUX)

if __name__ == '__main__':
    import logging as _l
    _l.getLogger('werkzeug').disabled = True
    _l.getLogger('flask').disabled = True
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.log = lambda self, type, msg, *args: None
    print("=" * 50)
    print("       MARCOS TV - RENDER")
    print("=" * 50)
    print(f"  Termux: {URL_TERMUX}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
