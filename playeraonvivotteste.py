import os, re, json, time, threading, subprocess, hashlib
import urllib3
from flask import Flask, Response, request, render_template_string, jsonify
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

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 10000))

URL_PUBLICA = os.environ.get("URL_PUBLICA", "")

def url_base():
    if URL_PUBLICA:
        return URL_PUBLICA.rstrip("/")
    return request.host_url.rstrip("/")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXIES = ["chrome120", "chrome110", "safari_15_5"]

TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 200
TS_CACHE_TEMPO = 120

ARQ_SALVOS = "canais_salvos.json"
CANAIS_LOCK = threading.Lock()

EMBEDS_DOMINIOS = [
    "https://ww5.embedtv.lat",
    "https://2608.cdnembedcanais.xyz",
    "https://w1.rdse.buzz",
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
    "premiere": ["premiere", "premiere1"],
}

CANAIS_DISPONIVEIS = [
    "espn", "espn2", "espn3", "espn4", "espn5", "espn6",
    "tnt", "tntnovelas", "tntseries",
    "warner", "warnerchannel", "space", "megapix",
    "telecinepremium", "telecineaction", "telecinefun", "telecinepipoca", "telecinetouch", "telecinecult",
    "sportv", "sportv2", "sportv3", "sportv4",
    "premiere", "premiere2", "premiere3", "premiere4", "premiere5", "premiere6", "premiere7", "premiere8",
    "max", "max1", "max2", "max3",
    "discoverychannel", "discoveryhh", "discoveryid", "discoveryscience", "discoverytheater", "discoveryturbo", "discoveryworld",
    "history", "history2", "ae", "amc", "axn", "cinemax", "comedycentral",
    "gnt", "hbo", "hbo2", "hbofamily", "hbomundi", "hboplus", "hbopop", "hbosignature", "hboxtreme",
    "hgtv", "sony", "studiouniversal", "tcm", "tlc", "universal", "usa",
    "paramount", "paramountnetwork",
    "cartoonnetwork", "cartoonito", "discoverykids", "dreamworks", "gloob", "gloobinho", "nickjr", "nickelodeon", "tooncast", "tvratimbum",
    "animalplanet", "fishtv",
    "bandnews", "bandsp", "cnnbrasil", "globonews", "recordtv", "sbt", "redetv",
    "mtv", "multishow", "foodnetwork", "masterchef",
    "amazonprime", "appletv01", "appletv02",
    "globoplaynovelas",
]
CANAIS_DISPONIVEIS = list(dict.fromkeys(CANAIS_DISPONIVEIS))

def carregar_salvos():
    if not os.path.exists(ARQ_SALVOS):
        return {}
    try:
        with open(ARQ_SALVOS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def salvar_em_disco(dados):
    with CANAIS_LOCK:
        try:
            with open(ARQ_SALVOS, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

CANAIS_SALVOS = carregar_salvos()

def criar_sessao(imp=None):
    if USE_CURL:
        try:
            return ImpersonateSession.Session(impersonate=imp or "chrome120")
        except Exception:
            pass
    return ImpersonateSession.Session()

def obter_headers(cfg):
    h = {
        "User-Agent": cfg.get("user_agent") or USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    if cfg.get("cookie"): h["Cookie"] = cfg["cookie"]
    if cfg.get("origin"): h["Origin"] = cfg["origin"]
    if cfg.get("referer"): h["Referer"] = cfg["referer"]
    return h

def extrair_nome_canal(url):
    m = re.search(r'/([^/]+)/index\.m3u8', url) or re.search(r'/([^/?]+)\.m3u8', url)
    if m:
        return m.group(1).lower()
    m = re.search(r'/([^/?]+)/?$', url)
    return m.group(1).lower() if m else "canal"

def substituir_canal(url_orig, canal):
    antigo = extrair_nome_canal(url_orig)
    if antigo and antigo != "canal":
        r = re.sub(rf'/{re.escape(antigo)}/index\.m3u8', f'/{canal}/index.m3u8', url_orig, flags=re.I)
        if r != url_orig:
            return r
    return url_orig

def extrair_links_playlist(html, base_url=""):
    padroes = [
        r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.m3u[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.txt[^\s"\'<>\\]*)',
        r'file\s*:\s*["\']([^"\']+)["\']',
        r'source\s*:\s*["\']([^"\']+)["\']',
        r'sources\s*:\s*\[\s*["\']([^"\']+)["\']',
        r'player\.src\s*\(\s*["\']([^"\']+)["\']',
        r'["\'](//[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']',
        r'["\'](/[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']',
        r'["\']([^"\']*\.m3u8[^"\']*)["\']',
    ]
    enc = []
    for p in padroes:
        for m in re.findall(p, html, re.I):
            if m.startswith("//"):
                m = "https:" + m
            elif m.startswith("/") and base_url:
                m = urljoin(base_url, m)
            if m.startswith("http") and m not in enc:
                enc.append(m)
    return enc

def extrair_iframes(html, base_url=""):
    urls = []
    for m in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I):
        if m.startswith("//"):
            m = "https:" + m
        elif m.startswith("/") and base_url:
            m = urljoin(base_url, m)
        if m.startswith("http"):
            urls.append(m)
    return urls

def validar_m3u8(sess, url, referer=None):
    try:
        h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if referer:
            h["Referer"] = referer
        r = sess.get(url, headers=h, timeout=8, verify=False, allow_redirects=True)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            return r, url
    except Exception:
        pass
    return None, None

def tentar_extrair_m3u8(url_pagina, sess, profundidade=0, max_prof=3, referer_original=None):
    if profundidade > max_prof:
        return None, None, None
    try:
        r = sess.get(url_pagina, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }, timeout=12, verify=False, allow_redirects=True)
        if r.status_code != 200:
            return None, None, None

        html = r.text
        url_final = str(r.url)
        ref_final = url_final

        for u in extrair_links_playlist(html, url_final):
            r2, u_val = validar_m3u8(sess, u, ref_final)
            if r2:
                return r2, u_val, ref_final

        for ifr in extrair_iframes(html, url_final):
            r2, u_val, ref = tentar_extrair_m3u8(ifr, sess, profundidade + 1, max_prof, ref_final)
            if r2:
                return r2, u_val, ref

    except Exception:
        pass
    return None, None, None

def get_path(nome):
    for p in [f"/data/data/com.termux/files/usr/bin/{nome}", f"/usr/bin/{nome}"]:
        if os.path.exists(p):
            return p
    try:
        s = subprocess.check_output(["which", nome], text=True).strip()
        return s or None
    except Exception:
        return None

chromium_bin = get_path("chromium-browser") or get_path("chromium")
chromedriver_bin = get_path("chromedriver")

def criar_driver():
    if not TEM_SELENIUM or not chromedriver_bin or not chromium_bin:
        return None
    o = Options()
    o.binary_location = chromium_bin
    for a in [
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        f"user-agent={USER_AGENT}", "--disable-blink-features=AutomationControlled",
        "--window-size=1280,720", "--disable-infobars", "--disable-extensions",
        "--disable-gpu", "--lang=pt-BR",
    ]:
        o.add_argument(a)
    o.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    o.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    try:
        return webdriver.Chrome(service=Service(chromedriver_bin), options=o)
    except Exception:
        return None

def capturar_via_selenium(url_pagina):
    d = criar_driver()
    if d is None:
        return None, None
    stream_url = None
    cookie_str = ""
    try:
        d.get(url_pagina)
        time.sleep(2)
        ifs = d.find_elements(By.TAG_NAME, "iframe")
        if ifs:
            try:
                d.switch_to.frame(ifs[0])
                time.sleep(2)
            except Exception:
                pass
        try:
            d.execute_script("""
                var v=document.querySelector('video');if(v)v.play();
                var b=document.querySelectorAll('button,.play,.jw-icon-playback,[class*=play]');
                for(var i=0;i<b.length;i++)b[i].click();
            """)
            time.sleep(2)
        except Exception:
            pass
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in d.get_cookies()])
        us = []
        for e in d.get_log("performance"):
            m = json.loads(e["message"])["message"]
            if m["method"] in ("Network.requestWillBeSent", "Network.responseReceived"):
                x = m["params"].get("request", {}).get("url") or m["params"].get("response", {}).get("url")
                if x and any(k in x.lower() for k in ['.m3u8', '.mpd', '.txt', '.m3u']) and x not in us:
                    us.append(x)
        if us:
            stream_url = us[0]
    except Exception:
        pass
    finally:
        d.quit()
    return stream_url, cookie_str

def resolver_auto(canal):
    """Tenta descobrir o stream do canal sem JSON salvo."""
    # 1) Embed HTTP
    sess = criar_sessao("chrome120")
    for var in ALIASES.get(canal, [canal]):
        for base in EMBEDS_DOMINIOS:
            embed_url = f"{base}/{var}"
            r, u, ref = tentar_extrair_m3u8(embed_url, sess)
            if r:
                cfg = {
                    "perfil_nome": f"embed_{var}",
                    "user_agent": USER_AGENT,
                    "referer": ref,
                    "origin": base,
                }
                return r, u, cfg, "chrome120"

    # 2) Selenium (só se disponível)
    if TEM_SELENIUM and chromedriver_bin and chromium_bin:
        for var in ALIASES.get(canal, [canal]):
            url_pagina = f"{BASE_SELENIUM}/{var}"
            u, ck = capturar_via_selenium(url_pagina)
            if u:
                try:
                    r = sess.get(u, headers={
                        "User-Agent": USER_AGENT,
                        "Referer": url_pagina,
                        "Cookie": ck,
                        "Origin": BASE_SELENIUM,
                    }, timeout=10, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        cfg = {
                            "perfil_nome": f"sel_{var}",
                            "user_agent": USER_AGENT,
                            "referer": url_pagina,
                            "cookie": ck,
                            "origin": BASE_SELENIUM,
                        }
                        return r, u, cfg, "chrome120"
                except Exception:
                    pass
    return None, None, None, None

def buscar_stream(canal, bruto, log):
    """Tenta: JSON salvo -> URL -> auto-resolver."""
    if bruto:
        bruto = bruto.strip()
        cfg = None

        try:
            j = json.loads(bruto)
            cfg = {
                "url": (j.get("url") or "").strip(),
                "user_agent": (j.get("user_agent") or USER_AGENT).strip(),
                "cookie": (j.get("cookie") or "").strip(),
                "origin": (j.get("origin") or j.get("origem") or "").strip(),
                "referer": (j.get("referer") or "").strip(),
            }
            if cfg["origin"] and not cfg["origin"].startswith("http"):
                cfg["origin"] = ""
            if cfg["url"] and not cfg["origin"]:
                m = re.match(r'(https?://[^/]+)', cfg["url"])
                if m:
                    cfg["origin"] = m.group(1)
            if cfg["url"] and not cfg["referer"]:
                cfg["referer"] = cfg["origin"] + "/" if cfg["origin"] else cfg["url"]
            log.append(f"[INPUT] JSON url={cfg['url'][:100]}")
        except json.JSONDecodeError:
            pass

        if not cfg and bruto.startswith("http"):
            alvo = substituir_canal(bruto, canal)
            cfg = {"url": alvo, "user_agent": USER_AGENT, "referer": alvo}
            m = re.match(r'(https?://[^/]+)', alvo)
            if m:
                cfg["origin"] = m.group(1)
            log.append(f"[INPUT] URL={bruto[:100]}")

        if cfg and cfg.get("url"):
            alvo = substituir_canal(cfg["url"], canal)
            for imp in PROXIES:
                try:
                    s = criar_sessao(imp)
                    r = s.get(alvo, headers=obter_headers(cfg), timeout=10, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        log.append(f"[CFG] {imp} OK")
                        return r, alvo, cfg, imp
                except Exception as e:
                    log.append(f"[CFG] {imp} erro: {e}")

    # Fallback: auto-resolver
    log.append("[AUTO] Tentando descobrir via embeds...")
    return resolver_auto(canal)

HTML_PAGINA = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Player Debug</title>
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, Arial, sans-serif; background: #0a0a0f; color: #fff; padding: 16px; }
  .box { max-width: 1000px; margin: 0 auto; background: #14141f; border: 1px solid #272738; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
  h1 { font-size: 1.1em; margin-bottom: 10px; color: #a29bfe; }
  h2 { font-size: 0.95em; margin: 12px 0 6px; color: #00b894; }
  input, textarea { width: 100%; background: #0d0d14; border: 1px solid #272738; color: #fff; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-family: monospace; font-size: 0.85em; }
  textarea { min-height: 90px; resize: vertical; }
  button { background: #00b894; color: #fff; border: 0; padding: 12px 20px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 0.95em; margin-right: 6px; margin-bottom: 6px; }
  button.debug { background: #e67e22; }
  button.salvar { background: #3498db; }
  .video-js { width: 100%; height: 380px; }
  @media (max-width: 600px) { .video-js { height: 200px; } }
  .log { font-size: 0.8em; color: #aaa; background: #0d0d14; padding: 10px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; }
  .log .ok { color: #00b894; }
  a { color: #00b894; word-break: break-all; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
  .canal { background: #0d0d14; border: 1px solid #272738; padding: 8px; border-radius: 6px; text-align: center; cursor: pointer; font-size: 0.8em; text-transform: uppercase; transition: 0.15s; }
  .canal:hover { background: #6c5ce7; border-color: #6c5ce7; }
</style>
</head>
<body>
  <div class="box">
    <h1>PLAYER DEBUG</h1>
    <video id="player" class="video-js" controls playsinline></video>
    <input id="canal" placeholder="Nome do canal (ex: espn, tnt, warner)">
    <button onclick="tocar()">PLAY</button>
    <button class="salvar" onclick="salvar()">SALVAR CANAL</button>
    <button class="debug" onclick="toggleCanais()">📺 CANAIS</button>
    <div class="log" id="log">Pronto</div>
  </div>

  <div class="box" id="box-canais" style="display:none">
    <h1>CANAIS DISPONÍVEIS</h1>
    <div class="grid" id="listaAuto">carregando...</div>
  </div>

  <div class="box">
    <h1>DADOS BRUTOS (opcional)</h1>
    <textarea id="bruto" placeholder='Cole JSON: {"url":"...","origin":"...","referer":"...","cookie":"...","user_agent":"..."}'></textarea>
  </div>

  <div class="box">
    <h1>CANAIS SALVOS</h1>
    <div id="listaSalvos" class="log">carregando...</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player');
var log = document.getElementById('log');

function setLog(msg, ok) {
  log.innerHTML = ok ? '<span class="ok">' + msg + '</span>' : msg;
}

function toggleCanais() {
  var b = document.getElementById('box-canais');
  b.style.display = b.style.display === 'none' ? 'block' : 'none';
}

function atualizarLista() {
  fetch('/listar').then(r => r.json()).then(d => {
    var box = document.getElementById('listaSalvos');
    if (!d.canais || !d.canais.length) { box.innerText = 'Nenhum canal salvo'; return; }
    var html = '';
    d.canais.forEach(function(c) {
      var link = location.origin + '/fixo/' + c;
      html += '<div><b>' + c + '</b> → <a href="' + link + '" target="_blank">' + link + '</a> ';
      html += '<button onclick="navigator.clipboard.writeText(\\'' + link + '\\');this.innerText=\\'COPIADO\\'">COPIAR</button> ';
      html += '<button onclick="remover(\\'' + c + '\\')" style="background:#e74c3c">X</button></div>';
    });
    box.innerHTML = html;
  });
}

function atualizarAuto() {
  fetch('/canais').then(r => r.json()).then(d => {
    var box = document.getElementById('listaAuto');
    var html = '';
    d.canais.forEach(function(c) {
      html += '<div class="canal" onclick="playCanal(\\'' + c + '\\')">' + c + '</div>';
    });
    box.innerHTML = html;
  });
}

function playCanal(c) {
  document.getElementById('canal').value = c;
  document.getElementById('bruto').value = '';
  tocar();
}

function remover(canal) {
  if (!confirm('Remover ' + canal + '?')) return;
  fetch('/remover/' + canal).then(() => atualizarLista());
}

function tocar() {
  var canal = document.getElementById('canal').value.trim().toLowerCase();
  var bruto = document.getElementById('bruto').value.trim();
  if (!canal) { setLog('Digite o canal'); return; }
  setLog('Carregando ' + canal + '...');
  var src = '/play/' + encodeURIComponent(canal);
  player.src({ src: src, type: 'application/x-mpegURL' });
  player.play().then(function(){ setLog('Tocando: ' + canal, true); }).catch(function(e){ setLog('Erro: ' + e.message); });
}

function salvar() {
  var canal = document.getElementById('canal').value.trim().toLowerCase();
  var bruto = document.getElementById('bruto').value.trim();
  if (!canal || !bruto) { setLog('Preencha canal e bruto'); return; }
  setLog('Salvando...');
  fetch('/salvar', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({canal: canal, bruto: bruto})
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      setLog('Salvo! Link: ' + d.link, true);
      atualizarLista();
    } else {
      setLog(d.msg || 'Erro');
    }
  });
}

atualizarLista();
atualizarAuto();
</script>
</body>
</html>
'''

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    return r

@app.route('/')
def index():
    return render_template_string(HTML_PAGINA)

@app.route('/canais')
def api_canais():
    return jsonify({"canais": CANAIS_DISPONIVEIS})

@app.route('/testar', methods=['POST'])
def testar():
    d = request.get_json() or {}
    canal = (d.get('canal') or '').strip().lower()
    bruto = (d.get('bruto') or '').strip()
    if not canal:
        return {"ok": False, "msg": "Preencha canal"}
    log = []
    r = buscar_stream(canal, bruto, log)
    return {"ok": bool(r and r[0])}

@app.route('/salvar', methods=['POST'])
def salvar_canal():
    d = request.get_json() or {}
    canal = (d.get('canal') or '').strip().lower()
    bruto = (d.get('bruto') or '').strip()
    if not canal or not bruto:
        return {"ok": False, "msg": "Faltou canal ou bruto"}
    CANAIS_SALVOS[canal] = {"bruto": bruto}
    salvar_em_disco(CANAIS_SALVOS)
    link = f"{url_base()}/fixo/{canal}"
    return {"ok": True, "link": link, "canal": canal}

@app.route('/remover/<canal>')
def remover_canal(canal):
    canal = canal.lower()
    if canal in CANAIS_SALVOS:
        del CANAIS_SALVOS[canal]
        salvar_em_disco(CANAIS_SALVOS)
        return {"ok": True}
    return {"ok": False}

@app.route('/listar')
def listar_salvos():
    return {"canais": list(CANAIS_SALVOS.keys())}

@app.route('/fixo/<canal>')
def link_fixo(canal):
    canal = canal.lower()
    cfg = CANAIS_SALVOS.get(canal)
    bruto = cfg["bruto"] if cfg else ""
    log = []
    r = buscar_stream(canal, bruto, log)
    if r and r[0]:
        resp, url_a, cfg_usado, tunel = r
        return gerar_playlist(resp, url_a, cfg_usado, tunel)
    return f"Canal {canal} falhou", 500

@app.route('/play/<canal>')
def play_canal(canal):
    canal = canal.strip('/').lower()
    cfg = CANAIS_SALVOS.get(canal)
    bruto = cfg["bruto"] if cfg else ""
    log = []
    r = buscar_stream(canal, bruto, log)
    if r and r[0]:
        resp, url_a, cfg_usado, tunel = r
        return gerar_playlist(resp, url_a, cfg_usado, tunel)
    return f"Canal {canal} nao encontrado", 404

@app.route('/play')
def play_query():
    canal = (request.args.get('canal') or '').strip().lower()
    bruto = unquote(request.args.get('bruto') or '').strip()
    if not canal:
        return "Faltam parametros", 400
    log = []
    r = buscar_stream(canal, bruto, log)
    if r and r[0]:
        resp, url_a, cfg_usado, tunel = r
        return gerar_playlist(resp, url_a, cfg_usado, tunel)
    return f"Canal {canal} nao encontrado", 404

def gerar_playlist(resp, url_a, cfg, tunel):
    L = []
    base = getattr(resp, 'url', url_a)
    ref = quote(cfg.get("referer", "") or "", safe='')
    ck = quote(cfg.get("cookie", "") or "", safe='')
    org = quote(cfg.get("origin", "") or "", safe='')
    for l in resp.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            q = f"url={quote(abs_url, safe='')}&tunel={tunel}"
            if ref: q += f"&ref={ref}"
            if ck: q += f"&ck={ck}"
            if org: q += f"&or={org}"
            L.append(f"{ep}?{q}")
        else:
            L.append(ls)
    return Response("\n".join(L), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*',
    })

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', '') or '')
    ck_custom = unquote(request.args.get('ck', '') or '')
    org_custom = unquote(request.args.get('or', '') or '')
    if not target:
        return "URL ausente", 400
    sess = criar_sessao(tunel)
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if ref_custom: h["Referer"] = ref_custom
    if ck_custom: h["Cookie"] = ck_custom
    if org_custom: h["Origin"] = org_custom
    try:
        r = sess.get(target, headers=h, timeout=8, verify=False, allow_redirects=True)
        L = []
        base = getattr(r, 'url', target)
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                q = f"url={quote(abs_url, safe='')}&tunel={tunel}"
                if ref_custom: q += f"&ref={quote(ref_custom, safe='')}"
                if ck_custom: q += f"&ck={quote(ck_custom, safe='')}"
                if org_custom: q += f"&or={quote(org_custom, safe='')}"
                L.append(f"{ep}?{q}")
            else:
                L.append(ls)
        return Response("\n".join(L), status=200, headers={
            'Content-Type': 'application/vnd.apple.mpegurl',
            'Access-Control-Allow-Origin': '*',
        })
    except Exception as e:
        return f"Erro: {e}", 500

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', '') or '')
    ck_custom = unquote(request.args.get('ck', '') or '')
    org_custom = unquote(request.args.get('or', '') or '')
    if not target:
        return "URL ausente", 400
    with TS_CACHE_LOCK:
        item = TS_CACHE.get(target)
        if item:
            dados, t = item
            if time.time() - t < TS_CACHE_TEMPO:
                return Response(dados, status=200, headers={
                    'Content-Type': 'video/mp2t',
                    'Content-Length': str(len(dados)),
                    'Cache-Control': 'public, max-age=60',
                    'Accept-Ranges': 'bytes',
                    'Access-Control-Allow-Origin': '*',
                })
    sess = criar_sessao(tunel)
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if ref_custom: h["Referer"] = ref_custom
    if ck_custom: h["Cookie"] = ck_custom
    if org_custom: h["Origin"] = org_custom
    try:
        r = sess.get(target, headers=h, timeout=15, verify=False)
        conteudo = r.content
        with TS_CACHE_LOCK:
            if len(TS_CACHE) >= TS_CACHE_MAX:
                mais = min(TS_CACHE.items(), key=lambda kv: kv[1][1])
                del TS_CACHE[mais[0]]
            TS_CACHE[target] = (conteudo, time.time())
        return Response(conteudo, status=r.status_code, headers={
            'Content-Type': 'video/mp2t',
            'Content-Length': str(len(conteudo)),
            'Cache-Control': 'public, max-age=60',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*',
        })
    except Exception as e:
        return f"Erro TS: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
