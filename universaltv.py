cat > ~/universaltv.py << 'PYEOF'
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
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("MARCOS_TV")
logger.disabled = True

app = Flask(__name__)

PORTA = int(os.environ.get("PORT", 9999))
PASTA_PERFIS = os.path.expanduser("./canais_dados")
os.makedirs(PASTA_PERFIS, exist_ok=True)

PROXIES = ["chrome120", "chrome110", "safari_15_5"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

URL_PUBLICA_BASE = "https://mrctv2.onrender.com/stream"

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

EMBEDS_DOMINIOS = [
    "https://ww5.embedtv.lat",
    "https://2608.cdnembedcanais.xyz",
    "https://w1.rdse.buzz"
]

BASE_SELENIUM = "https://v1.rdse.lat"

ALIASES = {
    "warnerchannel": ["warnerchannel", "warner"],
    "warner": ["warner", "warnerchannel"],
    "telecinepremium": ["telecinepremium", "tcpremium"],
    "telecineaction": ["telecineaction", "tcaction"],
    "espn": ["espn", "espn1"],
    "tnt": ["tnt", "tntbr"],
    "max": ["max", "max1"],
    "premiere": ["premiere", "premiere1"]
}

CACHE_SELENIUM = {}
LOCK_SELENIUM = threading.Lock()
TEMPO_CACHE_SELENIUM = 600

SESSAO = ImpersonateSession.Session()
SESSAO.headers.update({"User-Agent": USER_AGENT})

def get_path(nome):
    for p in [f"/usr/bin/{nome}", f"/usr/local/bin/{nome}", f"/data/data/com.termux/files/usr/bin/{nome}"]:
        if os.path.exists(p):
            return p
    try:
        saida = subprocess.check_output(["which", nome], text=True).strip()
        return saida or None
    except Exception:
        return None

chromium_bin = get_path("chromium-browser") or get_path("chromium") or get_path("google-chrome")
chromedriver_bin = get_path("chromedriver")

def criar_driver():
    if not SELENIUM_OK or not chromedriver_bin or not chromium_bin:
        return None
    options = Options()
    options.binary_location = chromium_bin
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={USER_AGENT}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=pt-BR")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    try:
        return webdriver.Chrome(service=Service(chromedriver_bin), options=options)
    except Exception:
        return None

def capturar_url_stream_selenium(url_pagina):
    driver = criar_driver()
    if driver is None:
        return None, None
    stream_url, cookie_str = None, ""
    try:
        driver.get(url_pagina)
        time.sleep(2)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if iframes:
            try:
                driver.switch_to.frame(iframes[0])
                time.sleep(2)
            except Exception:
                pass
        try:
            driver.execute_script("""
                var v = document.querySelector('video');
                if (v) v.play();
                var btns = document.querySelectorAll('button, .play, .jw-icon-playback, [class*=play]');
                for (var i=0; i<btns.length; i++) btns[i].click();
            """)
            time.sleep(2)
        except Exception:
            pass
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        logs = driver.get_log("performance")
        urls_midia = []
        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            if msg["method"] in ("Network.requestWillBeSent", "Network.responseReceived"):
                url = msg["params"].get("request", {}).get("url") or msg["params"].get("response", {}).get("url")
                if any(ext in url.lower() for ext in ['.m3u8', '.mpd', '.txt', '.m3u', '.ts', '.m4s']):
                    if url not in urls_midia:
                        urls_midia.append(url)
        if urls_midia:
            stream_url = urls_midia[0]
    except Exception:
        pass
    finally:
        driver.quit()
    return stream_url, cookie_str

def obter_stream_http(base_url, canal):
    url_pagina = f"{base_url}/{canal}"
    try:
        resp = SESSAO.get(url_pagina, timeout=10, verify=False)
        if resp.status_code == 200:
            match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', resp.text)
            if match:
                return match.group(1), ""
            match = re.search(r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)', resp.text)
            if match:
                return match.group(1), ""
    except Exception:
        pass
    return None, ""

def processar_embed_especial(canal):
    variacoes = ALIASES.get(canal, [canal])
    for var_canal in variacoes:
        with LOCK_SELENIUM:
            if var_canal in CACHE_SELENIUM:
                stream_url, cookie_str, timestamp = CACHE_SELENIUM[var_canal]
                if time.time() - timestamp < TEMPO_CACHE_SELENIUM:
                    try:
                        headers = {"User-Agent": USER_AGENT, "Referer": f"{BASE_SELENIUM}/{var_canal}", "Cookie": cookie_str}
                        r = SESSAO.get(stream_url, headers=headers, timeout=10, verify=False)
                        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                            cfg = {"perfil_nome": f"selenium_{var_canal}", "user_agent": USER_AGENT, "referer": f"{BASE_SELENIUM}/{var_canal}", "cookie": cookie_str}
                            return r, stream_url, cfg, "chrome120"
                    except Exception:
                        pass
        url_pagina = f"{BASE_SELENIUM}/{var_canal}"
        stream_url, cookie_str = obter_stream_http(BASE_SELENIUM, var_canal)
        if not stream_url:
            stream_url, cookie_str = capturar_url_stream_selenium(url_pagina)
        if stream_url:
            with LOCK_SELENIUM:
                CACHE_SELENIUM[var_canal] = (stream_url, cookie_str, time.time())
            try:
                headers = {"User-Agent": USER_AGENT, "Referer": url_pagina, "Cookie": cookie_str}
                r = SESSAO.get(stream_url, headers=headers, timeout=10, verify=False)
                if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                    cfg = {"perfil_nome": f"selenium_{var_canal}", "user_agent": USER_AGENT, "referer": url_pagina, "cookie": cookie_str}
                    return r, stream_url, cfg, "chrome120"
            except Exception:
                pass
    return None, None, None, None

def criar_sessao(imp=None):
    if USE_CURL:
        try:
            return ImpersonateSession.Session(impersonate=imp or "chrome120")
        except Exception:
            pass
    return ImpersonateSession.Session()

def extrair_nome_canal(url):
    m = re.search(r'/([^/]+)/index\.m3u8', url) or re.search(r'/([^/?]+)\.m3u8', url)
    return m.group(1).lower() if m else "stream"

def substituir_canal_na_url(url_orig, canal):
    antigo = extrair_nome_canal(url_orig)
    if antigo and antigo != "stream":
        res = re.sub(rf'/{re.escape(antigo)}/index\.m3u8', f'/{canal}/index.m3u8', url_orig, flags=re.I)
        if res != url_orig:
            return res
        return re.sub(rf'/{re.escape(antigo)}\.m3u8', f'/{canal}.m3u8', url_orig, flags=re.I)
    return url_orig

def listar_perfis():
    return sorted([os.path.splitext(f)[0] for f in os.listdir(PASTA_PERFIS) if f.endswith('.json')])

def carregar_perfil(p):
    f = os.path.join(PASTA_PERFIS, f"{p}.json")
    return json.load(open(f, 'r', encoding='utf-8')) if os.path.exists(f) else None

def obter_headers(cfg, ref_custom=None):
    h = {
        "User-Agent": cfg.get("user_agent") or USER_AGENT,
        "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site"
    }
    if cfg.get("cookie"): h["Cookie"] = cfg["cookie"]
    if cfg.get("origin"): h["Origin"] = cfg["origin"]
    ref = ref_custom or cfg.get("referer")
    if ref:
        h["Referer"] = ref
        if not h.get("Origin"):
            m = re.match(r'(https?://[^/]+)', ref)
            if m: h["Origin"] = m.group(1)
    return h

def extrair_links_playlist(html):
    padroes = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.txt[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.m3u[^\s"\'<>]*)',
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        r'source\s*:\s*["\'](https?://[^"\']+)["\']'
    ]
    encontrados = []
    for p in padroes:
        m = re.findall(p, html, re.I)
        if m: encontrados.extend(m)
    return list(set(encontrados))

def processar_embed(canal):
    sess = criar_sessao("chrome120")
    variacoes = ALIASES.get(canal, [canal])
    for var_canal in variacoes:
        for base in EMBEDS_DOMINIOS:
            embed_url = f"{base}/{var_canal}"
            try:
                r = sess.get(embed_url, headers={"User-Agent": USER_AGENT}, timeout=4, verify=False)
                if r.status_code == 200:
                    links = extrair_links_playlist(r.text)
                    for stream_url in links:
                        try:
                            r2 = sess.get(stream_url, headers={"User-Agent": USER_AGENT, "Referer": embed_url}, timeout=4, verify=False)
                            if r2.status_code == 200 and ("#EXTM3U" in r2.text or "#EXT-X" in r2.text):
                                cfg = {"perfil_nome": f"embed_{var_canal}", "user_agent": USER_AGENT, "referer": embed_url}
                                return r2, stream_url, cfg, "chrome120"
                        except Exception:
                            continue
            except Exception:
                continue
    return None, None, None, None

def processar_bruto(canal):
    perfis = listar_perfis()
    variacoes = ALIASES.get(canal, [canal])
    for var_canal in variacoes:
        for p in perfis:
            cfg = carregar_perfil(p)
            if not cfg: continue
            url_teste = substituir_canal_na_url(cfg.get("url", ""), var_canal)
            for imp in PROXIES:
                sess = criar_sessao(imp)
                try:
                    r = sess.get(url_teste, headers=obter_headers(cfg), timeout=4, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        return r, url_teste, cfg, imp
                except Exception:
                    pass
    return None, None, None, None

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
        canais_manuais_html += f'<div class="canal-item canal-manual"><div class="canal-nome" onclick="playCanal(\'{p}\')">{p}</div></div>'
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
        <title>MarcosTV Premium</title>
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
            button { border:none; padding:12px 20px; border-radius:8px; font-weight:600; cursor:pointer; color:#fff; transition:.2s; }
            .btn-play { background:var(--accent); }
            .btn-canais { background:var(--warning); }
            button:hover { opacity:.85; }
            .modal { display:none; position:fixed; z-index:9999; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,.8); }
            .modal-content { background:var(--card); margin:5% auto; padding:20px; border:1px solid var(--border); border-radius:12px; width:90%; max-width:600px; max-height:80vh; overflow-y:auto; }
            .modal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; }
            .modal-title { font-size:1.2em; font-weight:600; }
            .close-btn { background:var(--danger); padding:8px 15px; border-radius:6px; cursor:pointer; }
            .canal-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(100px,1fr)); gap:8px; }
            .canal-item { background:#0d0d14; border:1px solid var(--border); padding:8px; border-radius:6px; text-align:center; cursor:pointer; font-size:.8em; text-transform:uppercase; transition:.2s; }
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
                    <button class="btn-canais" onclick="abrirModal()">📺 CANAIS</button>
                </div>
            </div>
        </div>
        <div id="modal-canais" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">📺 LISTA DE CANAIS</div>
                    <button class="close-btn" onclick="fecharModal()">X</button>
                </div>
                <div class="canal-grid">{{ canais_html|safe }}</div>
            </div>
        </div>
        <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
        <script>
            var player = videojs('player');
            function playModo(){ var v=document.getElementById('canal-input').value.trim().toLowerCase(); if(!v) return; carregarDirect('/stream/'+v); }
            function playCanal(n){ document.getElementById('canal-input').value=n; carregarDirect('/stream/'+n); fecharModal(); }
            function carregarDirect(p){ player.src({src:p,type:'application/x-mpegURL'}); player.play(); window.scrollTo({top:0,behavior:'smooth'}); }
            function abrirModal(){ document.getElementById('modal-canais').style.display='block'; }
            function fecharModal(){ document.getElementById('modal-canais').style.display='none'; }
            window.onclick = function(e){ var m=document.getElementById('modal-canais'); if(e.target==m) m.style.display='none'; }
        </script>
    </body>
    </html>
    ''', canais_html=canais_html)

@app.route('/stream/<canal>')
def rota_stream(canal):
    canal = canal.strip('/')
    if "Mozilla" in request.headers.get('User-Agent', '') and "raw" not in request.args:
        return index()
    for func in (processar_embed, processar_embed_especial, processar_bruto):
        resp, url_a, cfg, tunel = func(canal)
        if resp:
            return gerar_playlist_proxy(resp, url_a, cfg, tunel)
    return f"Erro 404: Canal '{canal}' nao encontrado", 404

def gerar_playlist_proxy(resp, url_a, cfg, tunel):
    host = request.host_url.rstrip('/')
    linhas = []
    base = getattr(resp, 'url', url_a)
    p_nome = cfg.get("perfil_nome", "")
    ref_encoded = quote(cfg.get("referer", ""))
    cookie_encoded = quote(cfg.get("cookie", ""))
    for l in resp.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{host}{ep}?url={quote(abs_url)}&perfil={p_nome}&tunel={tunel}&ref={ref_encoded}&ck={cookie_encoded}")
        else:
            linhas.append(ls)
    return Response("\n".join(linhas), status=200, headers={'Content-Type': 'application/vnd.apple.mpegurl'})

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    p_nome = request.args.get('perfil', '')
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', ''))
    ck_custom = unquote(request.args.get('ck', ''))
    cfg = carregar_perfil(p_nome) or {"user_agent": USER_AGENT}
    if ck_custom:
        cfg["cookie"] = ck_custom
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref_custom), timeout=6, verify=False)
        host = request.host_url.rstrip('/')
        linhas = []
        base = getattr(r, 'url', target)
        ref_encoded = quote(ref_custom or cfg.get("referer", ""))
        ck_encoded = quote(ck_custom or cfg.get("cookie", ""))
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                linhas.append(f"{host}{ep}?url={quote(abs_url)}&perfil={p_nome}&tunel={tunel}&ref={ref_encoded}&ck={ck_encoded}")
            else:
                linhas.append(ls)
        return Response("\n".join(linhas), status=200, headers={'Content-Type': 'application/vnd.apple.mpegurl'})
    except Exception as e:
        return str(e), 500

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    p_nome = request.args.get('perfil', '')
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', ''))
    ck_custom = unquote(request.args.get('ck', ''))
    cfg = carregar_perfil(p_nome) or {"user_agent": USER_AGENT}
    if ck_custom:
        cfg["cookie"] = ck_custom
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref_custom), stream=True, timeout=8, verify=False)
        def gerar():
            if hasattr(r, 'iter_content'):
                for chunk in r.iter_content(128 * 1024):
                    if chunk:
                        yield chunk
            else:
                yield r.content
        return Response(gerar(), status=r.status_code, headers={'Content-Type': 'video/mp2t', 'Accept-Ranges': 'bytes'})
    except Exception as e:
        return f"Erro TS: {e}", 500

@app.route('/health')
def health():
    return {"status": "ok", "service": "marcostv"}, 200

if __name__ == '__main__':
    print("=" * 50)
    print("       MARCOS TV ONLINE")
    print("=" * 50)
    print(f"  Porta: {PORTA}")
    print(f"  Publico: {URL_PUBLICA_BASE}/<canal>")
    print("=" * 50)

    import logging as flask_logging
    flask_logging.getLogger('werkzeug').disabled = True
    flask_logging.getLogger('flask').disabled = True
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.log = lambda self, type, msg, *args: None

    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
PYEOF
