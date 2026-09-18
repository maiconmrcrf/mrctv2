import os, sys, json, logging, time, re, threading, subprocess, hashlib
from flask import Flask, Response, request, render_template_string, jsonify
from urllib.parse import urljoin, quote, unquote
import urllib3
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

logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger("MARCOS_TV")
logger.disabled = True

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 9999))

PASTA_PERFIS = os.path.expanduser("./canais_dados")
CACHE_SEL_DIR = os.path.expanduser("./cache_selenium")
os.makedirs(PASTA_PERFIS, exist_ok=True)
os.makedirs(CACHE_SEL_DIR, exist_ok=True)

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

# ============ CACHE SELENIUM (disco) ============
def cache_sel_path(canal):
    return os.path.join(CACHE_SEL_DIR, f"{hashlib.md5(canal.encode()).hexdigest()}.json")

def cache_sel_save(canal, url, cookie):
    with LOCK_SELENIUM:
        CACHE_SELENIUM[canal] = (url, cookie, time.time())
    try:
        json.dump({"url": url, "cookie": cookie, "ts": time.time()},
                  open(cache_sel_path(canal), 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass

def cache_sel_load(canal):
    p = cache_sel_path(canal)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding='utf-8'))
        if time.time() - d.get("ts", 0) > TEMPO_CACHE_SELENIUM:
            return None
        with LOCK_SELENIUM:
            CACHE_SELENIUM[canal] = (d["url"], d.get("cookie", ""), d["ts"])
        return d["url"], d.get("cookie", "")
    except Exception:
        return None

# ============ PERFIS LOCAIS ============
def listar_perfis():
    return sorted([os.path.splitext(f)[0] for f in os.listdir(PASTA_PERFIS) if f.endswith('.json')])

def carregar_perfil(p):
    if not p:
        return None
    f = os.path.join(PASTA_PERFIS, f"{p}.json")
    return json.load(open(f, 'r', encoding='utf-8')) if os.path.exists(f) else None

def deletar_perfil(p):
    f = os.path.join(PASTA_PERFIS, f"{p}.json")
    if os.path.exists(f):
        os.remove(f)
        return True
    return False

# ============ UTIL ============
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

def obter_headers(cfg, ref_custom=None):
    h = {
        "User-Agent": cfg.get("user_agent") or USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site"
    }
    if cfg.get("cookie"): h["Cookie"] = cfg["cookie"]
    if cfg.get("origin"): h["Origin"] = cfg["origin"]
    ref = ref_custom or cfg.get("referer")
    if ref:
        h["Referer"] = ref
        if not h.get("Origin"):
            m = re.match(r'(https?://[^/]+)', ref)
            if m:
                h["Origin"] = m.group(1)
    return h

def extrair_links_playlist(html):
    padroes = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.txt[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.m3u[^\s"\'<>]*)',
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        r'source\s*:\s*["\'](https?://[^"\']+)["\']'
    ]
    enc = []
    for p in padroes:
        m = re.findall(p, html, re.I)
        if m:
            enc.extend(m)
    return list(set(enc))

# ============ ESTRATÉGIAS ============
def processar_embed(canal):
    sess = criar_sessao("chrome120")
    for var_canal in ALIASES.get(canal, [canal]):
        for base in EMBEDS_DOMINIOS:
            embed_url = f"{base}/{var_canal}"
            try:
                r = sess.get(embed_url, headers={"User-Agent": USER_AGENT}, timeout=4, verify=False)
                if r.status_code == 200:
                    for stream_url in extrair_links_playlist(r.text):
                        try:
                            r2 = sess.get(stream_url, headers={"User-Agent": USER_AGENT, "Referer": embed_url}, timeout=4, verify=False)
                            if r2.status_code == 200 and ("#EXTM3U" in r2.text or "#EXT-X" in r2.text):
                                cfg = {
                                    "perfil_nome": f"embed_{var_canal}",
                                    "user_agent": USER_AGENT,
                                    "referer": embed_url,
                                    "origin": base
                                }
                                return r2, stream_url, cfg, "chrome120"
                        except Exception:
                            continue
            except Exception:
                continue
    return None, None, None, None

def get_path(nome):
    for p in [f"/data/data/com.termux/files/usr/bin/{nome}", f"/usr/bin/{nome}"]:
        if os.path.exists(p):
            return p
    try:
        saida = subprocess.check_output(["which", nome], text=True).strip()
        if saida:
            return saida
    except Exception:
        pass
    return None

chromium_bin = get_path("chromium-browser") or get_path("chromium")
chromedriver_bin = get_path("chromedriver")

def criar_driver():
    if not TEM_SELENIUM or not chromedriver_bin or not chromium_bin:
        return None
    options = Options()
    options.binary_location = chromium_bin
    for a in [
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        f"user-agent={USER_AGENT}", "--disable-blink-features=AutomationControlled",
        "--window-size=1280,720", "--disable-infobars", "--disable-extensions",
        "--disable-gpu", "--lang=pt-BR"
    ]:
        options.add_argument(a)
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
    stream_url = None
    cookie_str = ""
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
        urls = []
        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            if msg["method"] in ("Network.requestWillBeSent", "Network.responseReceived"):
                url = msg["params"].get("request", {}).get("url") or msg["params"].get("response", {}).get("url")
                if url and any(ext in url.lower() for ext in ['.m3u8', '.mpd', '.txt', '.m3u', '.ts', '.m4s']):
                    if url not in urls:
                        urls.append(url)
        if urls:
            stream_url = urls[0]
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
            m = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', resp.text)
            if m:
                return m.group(1), ""
            m = re.search(r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)', resp.text)
            if m:
                return m.group(1), ""
    except Exception:
        pass
    return None, ""

def processar_embed_especial(canal):
    for var_canal in ALIASES.get(canal, [canal]):
        # 1) RAM
        with LOCK_SELENIUM:
            cached = CACHE_SELENIUM.get(var_canal)
        if cached:
            stream_url, cookie_str, ts = cached
            if time.time() - ts < TEMPO_CACHE_SELENIUM:
                try:
                    headers = {
                        "User-Agent": USER_AGENT,
                        "Referer": f"{BASE_SELENIUM}/{var_canal}",
                        "Cookie": cookie_str,
                        "Origin": BASE_SELENIUM
                    }
                    r = SESSAO.get(stream_url, headers=headers, timeout=10, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        cfg = {
                            "perfil_nome": f"selenium_{var_canal}",
                            "user_agent": USER_AGENT,
                            "referer": f"{BASE_SELENIUM}/{var_canal}",
                            "cookie": cookie_str,
                            "origin": BASE_SELENIUM
                        }
                        return r, stream_url, cfg, "chrome120"
                except Exception:
                    pass

        # 2) Disco
        disk = cache_sel_load(var_canal)
        if disk:
            stream_url, cookie_str = disk
            try:
                headers = {
                    "User-Agent": USER_AGENT,
                    "Referer": f"{BASE_SELENIUM}/{var_canal}",
                    "Cookie": cookie_str,
                    "Origin": BASE_SELENIUM
                }
                r = SESSAO.get(stream_url, headers=headers, timeout=10, verify=False)
                if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                    cfg = {
                        "perfil_nome": f"selenium_{var_canal}",
                        "user_agent": USER_AGENT,
                        "referer": f"{BASE_SELENIUM}/{var_canal}",
                        "cookie": cookie_str,
                        "origin": BASE_SELENIUM
                    }
                    return r, stream_url, cfg, "chrome120"
            except Exception:
                pass

        # 3) Busca nova
        url_pagina = f"{BASE_SELENIUM}/{var_canal}"
        stream_url, cookie_str = obter_stream_http(BASE_SELENIUM, var_canal)
        if not stream_url:
            stream_url, cookie_str = capturar_url_stream_selenium(url_pagina)
        if stream_url:
            cache_sel_save(var_canal, stream_url, cookie_str)
            try:
                headers = {
                    "User-Agent": USER_AGENT,
                    "Referer": url_pagina,
                    "Cookie": cookie_str,
                    "Origin": BASE_SELENIUM
                }
                r = SESSAO.get(stream_url, headers=headers, timeout=10, verify=False)
                if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                    cfg = {
                        "perfil_nome": f"selenium_{var_canal}",
                        "user_agent": USER_AGENT,
                        "referer": url_pagina,
                        "cookie": cookie_str,
                        "origin": BASE_SELENIUM
                    }
                    return r, stream_url, cfg, "chrome120"
            except Exception:
                pass
    return None, None, None, None

def processar_bruto(canal):
    perfis = listar_perfis()
    for var_canal in ALIASES.get(canal, [canal]):
        for p in perfis:
            cfg = carregar_perfil(p)
            if not cfg:
                continue
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

# ============ PROXY ============
def gerar_playlist_proxy(resp, url_a, cfg, tunel):
    L = []
    base = getattr(resp, 'url', url_a)
    p_nome = cfg.get("perfil_nome", "")
    ref = quote(cfg.get("referer", "") or "", safe='')
    ck = quote(cfg.get("cookie", "") or "", safe='')
    org = quote(cfg.get("origin", "") or "", safe='')
    for l in resp.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            q = f"url={quote(abs_url, safe='')}&perfil={p_nome}&tunel={tunel}"
            if ref: q += f"&ref={ref}"
            if ck: q += f"&ck={ck}"
            if org: q += f"&or={org}"
            L.append(f"{ep}?{q}")
        else:
            L.append(ls)
    return Response("\n".join(L), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'no-cache'
    })

# ============ HTML ============
HTML_PAGINA = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarcosTV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<link href="https://unpkg.com/@videojs/themes@1/dist/city/index.css" rel="stylesheet">
<style>
  :root { --bg:#0a0a0f; --card:#14141f; --border:#272738; --accent:#6c5ce7; --warning:#e67e22; --danger:#e74c3c; --ok:#00b894; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', sans-serif; background: var(--bg); color: #fff; padding: 16px; }
  .container { max-width: 1000px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
  .brand { font-size: 1.6em; font-weight: 800; background: linear-gradient(135deg, #fff, #a29bfe); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .player-box { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
  .video-js { width: 100%; height: 420px; border-radius: 8px; }
  @media(max-width: 768px){ .video-js { height: 240px; } }
  .controls { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
  input { flex: 1; min-width: 180px; background: #0d0d14; border: 1px solid var(--border); padding: 12px; border-radius: 8px; color: #fff; outline: none; }
  button { border: none; padding: 12px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; color: #fff; transition: 0.2s; }
  .btn-play { background: var(--accent); }
  .btn-canais { background: var(--warning); }
  button:hover { opacity: 0.85; }
  .modal { display: none; position: fixed; z-index: 9999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); }
  .modal-content { background: var(--card); margin: 5% auto; padding: 20px; border: 1px solid var(--border); border-radius: 12px; width: 92%; max-width: 720px; max-height: 80vh; overflow-y: auto; }
  .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
  .modal-title { font-size: 1.2em; font-weight: 600; }
  .close-btn { background: var(--danger); padding: 8px 15px; border-radius: 6px; cursor: pointer; }
  .canal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(105px, 1fr)); gap: 8px; }
  .canal-item { background: #0d0d14; border: 1px solid var(--border); padding: 10px 6px; border-radius: 6px; text-align: center; cursor: pointer; font-size: 0.78em; text-transform: uppercase; transition: 0.2s; }
  .canal-item:hover { background: var(--accent); border-color: var(--accent); }
  .canal-manual { background: #1a1a2e; border-color: var(--accent); }
  .status { font-size: 0.85em; color: #aaa; margin-top: 8px; }
  .status .ok { color: var(--ok); }
</style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">MARCOS TV</div>
    </header>

    <div class="player-box">
      <video id="player" class="video-js vjs-theme-city" controls preload="auto" playsinline></video>
      <div class="controls">
        <input id="canal-input" placeholder="Nome do canal (ex: espn, tnt, warner)..." onkeydown="if(event.key==='Enter')playModo()">
        <button class="btn-play" onclick="playModo()">▶ PLAY</button>
        <button class="btn-canais" onclick="abrirModal()">📺 CANAIS</button>
      </div>
      <div class="status" id="status">Pronto</div>
    </div>
  </div>

  <div id="modal-canais" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <div class="modal-title">📺 LISTA DE CANAIS</div>
        <button class="close-btn" onclick="fecharModal()">X</button>
      </div>
      <div class="canal-grid" id="canais-grid">
        {{ canais_html|safe }}
      </div>
    </div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player');
var statusEl = document.getElementById('status');

function setStatus(msg, ok) {
  statusEl.innerHTML = ok ? '<span class="ok">' + msg + '</span>' : msg;
}

function playModo() {
  var val = document.getElementById('canal-input').value.trim().toLowerCase();
  if (!val) { setStatus('Digite um canal'); return; }
  carregar('/play/' + encodeURIComponent(val));
}

function playCanal(nome) {
  document.getElementById('canal-input').value = nome;
  carregar('/play/' + encodeURIComponent(nome));
  fecharModal();
}

function carregar(path) {
  setStatus('Carregando ' + path + '...');
  player.src({ src: path, type: 'application/x-mpegURL' });
  player.play().then(function(){ setStatus('Tocando', true); }).catch(function(e){ setStatus('Erro: ' + e.message); });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function abrirModal() { document.getElementById('modal-canais').style.display = 'block'; }
function fecharModal() { document.getElementById('modal-canais').style.display = 'none'; }

document.addEventListener('click', function(e) {
  var item = e.target.closest('.canal-item');
  if (item) {
    var c = item.getAttribute('data-canal');
    if (c) playCanal(c);
  }
});

window.onclick = function(event) {
  var modal = document.getElementById('modal-canais');
  if (event.target == modal) modal.style.display = 'none';
}
</script>
</body>
</html>
'''

# ============ ROTAS ============
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    return r

@app.route('/')
def index():
    perfis = listar_perfis()
    canais_manuais = "".join([
        f'<div class="canal-item canal-manual" data-canal="{p}">{p.upper()}</div>'
        for p in perfis
    ])
    canais_fixos = "".join([
        f'<div class="canal-item" data-canal="{c}">{c.upper()}</div>'
        for c in CANAIS_DISPONIVEIS
    ])
    return render_template_string(HTML_PAGINA, canais_html=canais_manuais + canais_fixos)

@app.route('/play/<canal>')
def rota_play(canal):
    canal = canal.strip('/').lower()

    resp, url_a, cfg, tunel = processar_embed(canal)
    if resp:
        return gerar_playlist_proxy(resp, url_a, cfg, tunel)

    resp, url_a, cfg, tunel = processar_embed_especial(canal)
    if resp:
        return gerar_playlist_proxy(resp, url_a, cfg, tunel)

    resp, url_a, cfg, tunel = processar_bruto(canal)
    if resp:
        return gerar_playlist_proxy(resp, url_a, cfg, tunel)

    return f"Canal '{canal}' nao encontrado", 404

@app.route('/deletar/<canal>', methods=['DELETE'])
def deletar_canal(canal):
    canal = canal.strip('/').lower()
    ok = deletar_perfil(canal)
    return jsonify({"success": ok}), (200 if ok else 404)

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    p_nome = request.args.get('perfil', '')
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', '') or '')
    ck_custom = unquote(request.args.get('ck', '') or '')
    org_custom = unquote(request.args.get('or', '') or '')

    cfg = carregar_perfil(p_nome) or {"user_agent": USER_AGENT}
    if ck_custom: cfg["cookie"] = ck_custom
    if ref_custom: cfg["referer"] = ref_custom
    if org_custom: cfg["origin"] = org_custom

    if not target:
        return "URL ausente", 400
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref_custom), timeout=8, verify=False)
        if r.status_code != 200:
            return f"upstream {r.status_code}", r.status_code
        return gerar_playlist_proxy(r, target, cfg, tunel)
    except Exception as e:
        return str(e), 500

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    p_nome = request.args.get('perfil', '')
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', '') or '')
    ck_custom = unquote(request.args.get('ck', '') or '')
    org_custom = unquote(request.args.get('or', '') or '')

    cfg = carregar_perfil(p_nome) or {"user_agent": USER_AGENT}
    if ck_custom: cfg["cookie"] = ck_custom
    if ref_custom: cfg["referer"] = ref_custom
    if org_custom: cfg["origin"] = org_custom

    if not target:
        return "URL ausente", 400
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref_custom), stream=True, timeout=15, verify=False)
        if r.status_code != 200:
            return f"upstream {r.status_code}", r.status_code

        def gerar():
            if hasattr(r, 'iter_content'):
                for chunk in r.iter_content(128 * 1024):
                    if chunk:
                        yield chunk
            else:
                yield r.content

        return Response(gerar(), status=r.status_code, headers={
            'Content-Type': 'video/mp2t',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*'
        })
    except Exception as e:
        return f"Erro TS: {e}", 500

# ============ MAIN ============
if __name__ == '__main__':
    print("=" * 40)
    print("       📺 MARCOS TV ONLINE")
    print("=" * 40)
    print(f"  ✅ http://localhost:{PORTA}")
    print("=" * 40)

    logging.getLogger('werkzeug').disabled = True
    logging.getLogger('flask').disabled = True
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.log = lambda self, type, msg, *args: None

    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
