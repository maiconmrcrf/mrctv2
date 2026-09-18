import os, sys, json, time, re, threading, subprocess, base64, logging, hashlib
from flask import Flask, Response, request, render_template_string
from urllib.parse import urljoin, quote, unquote, urlparse
import urllib3
urllib3.disable_warnings()

try:
    from curl_cffi import requests as S
    USE_CURL = True
except ImportError:
    import requests as S
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

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 9999))

# ====== CONFIG ======
URL_PUBLICA = os.environ.get("URL_PUBLICA", "").rstrip("/")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_USER = os.environ.get("GH_USER", "")
GH_REPO = os.environ.get("GH_REPO", "")
GH_API = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents" if GH_USER and GH_REPO else ""

PASTA = os.path.expanduser("./canais_dados")
CACHE_DIR = os.path.expanduser("./cache_canais")
os.makedirs(PASTA, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXIES = ["chrome120", "chrome110", "safari_15_5"]

BASE_SEL = "https://v1.rdse.lat"
EMBEDS = [
    "https://ww5.embedtv.lat",
    "https://2608.cdnembedcanais.xyz",
    "https://w1.rdse.buzz",
]

# TTLs
TTL_QUENTE = 30
TTL_FRIO = 600
TTL_DISCO = 3600

CANAIS = "tnt tntnovelas tntseries warner warnerchannel space megapix telecinepremium telecineaction telecinefun telecinepipoca telecinetouch telecinecult espn espn2 espn3 espn4 espn5 espn6 sportv sportv2 sportv3 sportv4 premiere premiere2 premiere3 premiere4 premiere5 premiere6 premiere7 premiere8 max max1 max2 max3 discoverychannel discoveryhh discoveryid discoveryscience discoverytheater discoveryturbo discoveryworld history history2 ae amc axn adultswim cinemax comedycentral gnt hbo hbo2 hbofamily hbomundi hboplus hbopop hbosignature hboxtreme hgtv sony studiouniversal tcm tlc universal usa paramount paramountnetwork cartoonnetwork cartoonito discoverykids dreamworks gloob gloobinho nickjr nickelodeon tooncast tvratimbum band_sports bandnews cnnbrasil globonews recordtv sbt redetv cultura mtv multishow foodnetwork masterchef amazonprime appletv01 appletv02 globoplaynovelas".split()

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

# Cache RAM
RAM = {}
LOCK = threading.Lock()

# ============ CACHE ============
def cache_path(c):
    return os.path.join(CACHE_DIR, f"{hashlib.md5(c.encode()).hexdigest()}.json")

def sessao(imp=None):
    if USE_CURL:
        try:
            return S.Session(impersonate=imp or "chrome120")
        except Exception:
            pass
    return S.Session()

def _valida(url, cfg, tunel):
    try:
        h = hdr(cfg)
        h["Range"] = "bytes=0-0"
        r = sessao(tunel).get(url, headers=h, timeout=4, verify=False, allow_redirects=True)
        return r.status_code in (200, 206)
    except Exception:
        return False

def cache_get(canal):
    agora = time.time()
    with LOCK:
        e = RAM.get(canal)
    if e:
        u, cfg, tn, ts = e
        idade = agora - ts
        if idade < TTL_QUENTE:
            return u, cfg, tn
        if idade < TTL_FRIO:
            if _valida(u, cfg, tn):
                with LOCK:
                    RAM[canal] = (u, cfg, tn, agora)
                return u, cfg, tn
            with LOCK:
                RAM.pop(canal, None)
            cache_del(canal)
            return None
        with LOCK:
            RAM.pop(canal, None)

    p = cache_path(canal)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding='utf-8'))
        idade = agora - d.get("ts", 0)
        if idade > TTL_DISCO:
            os.remove(p)
            return None
        u, cfg, tn = d["url"], d["cfg"], d.get("tunel", "chrome120")
        if idade < TTL_QUENTE:
            with LOCK:
                RAM[canal] = (u, cfg, tn, d["ts"])
            return u, cfg, tn
        if _valida(u, cfg, tn):
            with LOCK:
                RAM[canal] = (u, cfg, tn, agora)
            return u, cfg, tn
        os.remove(p)
        return None
    except Exception:
        try:
            os.remove(p)
        except Exception:
            pass
        return None

def cache_save(canal, url, cfg, tunel):
    ts = time.time()
    with LOCK:
        RAM[canal] = (url, cfg, tunel, ts)
    try:
        json.dump(
            {"url": url, "cfg": cfg, "tunel": tunel, "ts": ts},
            open(cache_path(canal), 'w', encoding='utf-8'),
            indent=2, ensure_ascii=False
        )
    except Exception:
        pass

def cache_del(canal):
    with LOCK:
        RAM.pop(canal, None)
    try:
        p = cache_path(canal)
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def cache_preload():
    n = 0
    for f in os.listdir(CACHE_DIR):
        if not f.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(CACHE_DIR, f), encoding='utf-8'))
            if time.time() - d.get("ts", 0) <= TTL_DISCO:
                c = d["cfg"].get("perfil_nome", "")
                if c:
                    chave = c[2:] if c.startswith(("e_", "s_")) else c
                    with LOCK:
                        RAM[chave] = (d["url"], d["cfg"], d.get("tunel", "chrome120"), d["ts"])
                    n += 1
        except Exception:
            pass
    return n

# ============ PERFIS ============
def listar():
    return sorted([os.path.splitext(f)[0] for f in os.listdir(PASTA) if f.endswith('.json')])

def carregar(p):
    if not p:
        return None
    f = os.path.join(PASTA, f"{p}.json")
    return json.load(open(f, encoding='utf-8')) if os.path.exists(f) else None

def salvar(p, d):
    json.dump(d, open(os.path.join(PASTA, f"{p}.json"), 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

def deletar(p):
    f = os.path.join(PASTA, f"{p}.json")
    if os.path.exists(f):
        os.remove(f)
        return True
    return False

# ============ UTIL ============
def nome_url(u):
    m = re.search(r'/([^/]+)/index\.m3u8', u) or re.search(r'/([^/?]+)\.m3u8', u)
    return m.group(1).lower() if m else "stream"

def trocar(u, c):
    a = nome_url(u)
    if a and a != "stream":
        r = re.sub(rf'/{re.escape(a)}/index\.m3u8', f'/{c}/index.m3u8', u, flags=re.I)
        return r if r != u else re.sub(rf'/{re.escape(a)}\.m3u8', f'/{c}.m3u8', u, flags=re.I)
    return u

def origem_da_url(u):
    try:
        p = urlparse(u)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return ""

def hdr(cfg, ref=None):
    h = {
        "User-Agent": cfg.get("user_agent") or UA,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }
    if cfg.get("cookie"):
        h["Cookie"] = cfg["cookie"]
    if cfg.get("origin"):
        h["Origin"] = cfg["origin"]
    r = ref or cfg.get("referer")
    if r:
        h["Referer"] = r
        if not h.get("Origin"):
            m = re.match(r'(https?://[^/]+)', r)
            if m:
                h["Origin"] = m.group(1)
    return h

def normalizar_cfg_json(j):
    """Aceita variações de chaves."""
    url = (j.get("url") or j.get("link") or j.get("stream") or "").strip()
    origin = j.get("origin") or j.get("Origin") or ""
    origem = j.get("origem")
    if not origin and isinstance(origem, str) and origem.startswith("http"):
        origin = origem
    if not origin and url:
        origin = origem_da_url(url)
    referer = j.get("referer") or j.get("referrer") or j.get("Referer") or (origin + "/" if origin else "")
    return {
        "url": url,
        "user_agent": (j.get("user_agent") or j.get("userAgent") or UA).strip(),
        "cookie": (j.get("cookie") or "").strip(),
        "origin": origin.strip(),
        "referer": referer.strip() if referer else "",
    }

def links(h):
    ps = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.txt[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.m3u[^\s"\'<>]*)',
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        r'source\s*:\s*["\'](https?://[^"\']+)["\']',
    ]
    o = []
    for p in ps:
        o.extend(re.findall(p, h, re.I))
    return list(set(o))

# ============ ESTRATÉGIAS ============
def emb(c):
    s = sessao("chrome120")
    for v in ALIASES.get(c, [c]):
        for b in EMBEDS:
            try:
                r = s.get(f"{b}/{v}", headers={"User-Agent": UA}, timeout=4, verify=False)
                if r.status_code == 200:
                    for u in links(r.text):
                        try:
                            r2 = s.get(u, headers={"User-Agent": UA, "Referer": f"{b}/{v}"}, timeout=4, verify=False)
                            if r2.status_code == 200 and ("#EXTM3U" in r2.text or "#EXT-X" in r2.text):
                                cfg = {
                                    "perfil_nome": f"e_{v}",
                                    "user_agent": UA,
                                    "referer": f"{b}/{v}",
                                    "origin": b,
                                }
                                return r2, u, cfg, "chrome120"
                        except Exception:
                            pass
            except Exception:
                pass
    return None, None, None, None

def getpath(n):
    for p in [f"/data/data/com.termux/files/usr/bin/{n}", f"/usr/bin/{n}"]:
        if os.path.exists(p):
            return p
    try:
        s = subprocess.check_output(["which", n], text=True).strip()
        return s or None
    except Exception:
        return None

CHROMIUM = getpath("chromium-browser") or getpath("chromium")
CDRIVER = getpath("chromedriver")

def driver():
    if not TEM_SELENIUM or not CDRIVER or not CHROMIUM:
        return None
    o = Options()
    o.binary_location = CHROMIUM
    for a in [
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        f"user-agent={UA}", "--disable-blink-features=AutomationControlled",
        "--window-size=1280,720", "--disable-infobars", "--disable-extensions",
        "--disable-gpu", "--lang=pt-BR"
    ]:
        o.add_argument(a)
    o.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    o.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    try:
        return webdriver.Chrome(service=Service(CDRIVER), options=o)
    except Exception:
        return None

def sel_capture(url):
    d = driver()
    if not d:
        return None, ""
    u = None
    ck = ""
    try:
        d.get(url)
        time.sleep(2)
        ifs = d.find_elements(By.TAG_NAME, "iframe")
        if ifs:
            try:
                d.switch_to.frame(ifs[0])
                time.sleep(2)
            except Exception:
                pass
        try:
            d.execute_script(
                "var v=document.querySelector('video');if(v)v.play();"
                "var b=document.querySelectorAll('button,.play,.jw-icon-playback,[class*=play]');"
                "for(var i=0;i<b.length;i++)b[i].click();"
            )
            time.sleep(2)
        except Exception:
            pass
        ck = "; ".join([f"{c['name']}={c['value']}" for c in d.get_cookies()])
        us = []
        for e in d.get_log("performance"):
            m = json.loads(e["message"])["message"]
            if m["method"] in ("Network.requestWillBeSent", "Network.responseReceived"):
                x = m["params"].get("request", {}).get("url") or m["params"].get("response", {}).get("url")
                if x and any(k in x.lower() for k in ['.m3u8', '.mpd', '.txt', '.m3u', '.ts', '.m4s']) and x not in us:
                    us.append(x)
        if us:
            u = us[0]
    except Exception:
        pass
    finally:
        d.quit()
    return u, ck

def sel(c):
    for v in ALIASES.get(c, [c]):
        url = f"{BASE_SEL}/{v}"
        u = None
        try:
            r = sessao("chrome120").get(url, timeout=10, verify=False)
            if r.status_code == 200:
                m = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', r.text) or \
                    re.search(r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)', r.text)
                if m:
                    u = m.group(1)
        except Exception:
            pass
        ck = ""
        if not u:
            u, ck = sel_capture(url)
        if u:
            try:
                r = sessao("chrome120").get(
                    u, headers={"User-Agent": UA, "Referer": url, "Cookie": ck, "Origin": BASE_SEL},
                    timeout=10, verify=False
                )
                if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                    cfg = {
                        "perfil_nome": f"s_{v}",
                        "user_agent": UA,
                        "referer": url,
                        "cookie": ck,
                        "origin": BASE_SEL,
                    }
                    return r, u, cfg, "chrome120"
            except Exception:
                pass
    return None, None, None, None

def bruto(c):
    for v in ALIASES.get(c, [c]):
        for p in listar():
            cfg = carregar(p)
            if not cfg:
                continue
            u = trocar(cfg.get("url", ""), v)
            for imp in PROXIES:
                try:
                    r = sessao(imp).get(u, headers=hdr(cfg), timeout=4, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        return r, u, cfg, imp
                except Exception:
                    pass
    return None, None, None, None

def resolver(canal):
    c = cache_get(canal)
    if c:
        u, cfg, tn = c
        try:
            r = sessao(tn).get(u, headers=hdr(cfg), timeout=8, verify=False)
            if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                return r, u, cfg, tn
        except Exception:
            pass
        cache_del(canal)
    for fn in (emb, sel, bruto):
        try:
            r, u, cf, t = fn(canal)
            if r:
                cache_save(canal, u, cf, t)
                return r, u, cf, t
        except Exception:
            pass
    return None, None, None, None

# ============ PROXY PLAYLIST ============
def pl_proxy(r, u_a, cfg, t):
    L = []
    base = getattr(r, 'url', u_a)
    p = cfg.get("perfil_nome", "")
    ref = quote(cfg.get("referer", "") or "", safe='')
    ck = quote(cfg.get("cookie", "") or "", safe='')
    org = quote(cfg.get("origin", "") or "", safe='')
    for l in r.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            au = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            q = f"url={quote(au, safe='')}&perfil={p}&tunel={t}"
            if ref: q += f"&ref={ref}"
            if ck: q += f"&ck={ck}"
            if org: q += f"&or={org}"
            L.append(f"{ep}?{q}")
        else:
            L.append(ls)
    return Response("\n".join(L), headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*'
    })

# ============ HTML PLAYER ============
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
  input, textarea { width: 100%; background: #0d0d14; border: 1px solid #272738; color: #fff; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-family: monospace; font-size: 0.85em; }
  textarea { min-height: 90px; resize: vertical; }
  button { background: #00b894; color: #fff; border: 0; padding: 12px 20px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 0.95em; margin-right: 6px; margin-bottom: 6px; }
  button.salvar { background: #3498db; }
  button.play { background: #e67e22; }
  .video-js { width: 100%; height: 380px; }
  @media (max-width: 600px) { .video-js { height: 200px; } }
  .log { font-size: 0.8em; color: #aaa; background: #0d0d14; padding: 10px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; }
  .log .ok { color: #00b894; }
  a { color: #00b894; word-break: break-all; }
</style>
</head>
<body>
  <div class="box">
    <h1>PLAYER DEBUG</h1>
    <video id="player" class="video-js" controls playsinline></video>
    <input id="canal" placeholder="Nome do canal (ex: tnt)">
    <button class="play" onclick="tocar()">PLAY</button>
    <button class="salvar" onclick="salvar()">SALVAR CANAL</button>
    <button onclick="invalidar()">INVALIDAR CACHE</button>
    <div class="log" id="log">Pronto</div>
  </div>

  <div class="box">
    <h1>DADOS BRUTOS (JSON)</h1>
    <textarea id="bruto" placeholder='Cole aqui o JSON: {"url":"...","origin":"...","referer":"...","cookie":"...","user_agent":"..."}'></textarea>
  </div>

  <div class="box">
    <h1>CANAIS SALVOS</h1>
    <div id="listaSalvos" class="log">carregando...</div>
  </div>

  <div class="box">
    <h1>CANAIS DISPONÍVEIS (auto)</h1>
    <div id="listaAuto" class="log">carregando...</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player');
var log = document.getElementById('log');

function atualizarLista() {
  fetch('/listar').then(r => r.json()).then(d => {
    var box = document.getElementById('listaSalvos');
    if (!d.canais || !d.canais.length) { box.innerText = 'Nenhum canal salvo'; return; }
    var html = '';
    d.canais.forEach(function(c) {
      var link = location.origin + '/play/' + c;
      html += '<div><b>' + c + '</b> → <a href="' + link + '" target="_blank">' + link + '</a> ';
      html += '<button onclick="navigator.clipboard.writeText(\\'' + link + '\\');this.innerText=\\'COPIADO\\'">COPIAR</button> ';
      html += '<button onclick="playCanal(\\'' + c + '\\')">PLAY</button> ';
      html += '<button onclick="remover(\\'' + c + '\\')" style="background:#e74c3c">X</button></div>';
    });
    box.innerHTML = html;
  });
}

function atualizarAuto() {
  fetch('/canais').then(r => r.json()).then(d => {
    var box = document.getElementById('listaAuto');
    if (!d.canais || !d.canais.length) { box.innerText = 'Nenhum'; return; }
    var html = '';
    d.canais.forEach(function(c) {
      html += '<span style="display:inline-block;margin:3px"><button onclick="playCanal(\\'' + c + '\\')" style="padding:6px 10px;font-size:0.8em">' + c + '</button></span>';
    });
    box.innerHTML = html;
  });
}

function playCanal(c) {
  document.getElementById('canal').value = c;
  player.src({src: '/play/' + c, type: 'application/x-mpegURL'});
  player.play();
  log.innerText = 'Tocando: ' + c;
}

function remover(canal) {
  if (!confirm('Remover ' + canal + '?')) return;
  fetch('/deletar/' + canal, {method: 'DELETE'}).then(() => { atualizarLista(); invalidar(); });
}

function invalidar() {
  var c = document.getElementById('canal').value.trim().toLowerCase();
  if (c) fetch('/invalidar/' + c).then(() => log.innerText = 'Cache invalidado: ' + c);
}

function tocar() {
  var canal = document.getElementById('canal').value.trim().toLowerCase();
  if (!canal) { log.innerText = 'Digite o canal'; return; }
  log.innerText = 'Testando ' + canal + '...';
  player.src({src: '/play/' + canal, type: 'application/x-mpegURL'});
  player.play();
  log.innerText = 'Tocando: ' + canal;
}

function salvar() {
  var canal = document.getElementById('canal').value.trim().toLowerCase();
  var bruto = document.getElementById('bruto').value.trim();
  if (!canal || !bruto) { log.innerText = 'Preencha canal e bruto'; return; }
  log.innerText = 'Salvando...';
  fetch('/salvar', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({canal: canal, bruto: bruto})
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      log.innerHTML = '<span class="ok">Salvo! Link: <a href="' + d.link + '" target="_blank">' + d.link + '</a></span>';
      atualizarLista();
    } else {
      log.innerText = d.msg || 'Erro';
    }
  });
}

atualizarLista();
atualizarAuto();
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
    return render_template_string(HTML_PAGINA)

@app.route('/play/<c>')
def play(c):
    c = c.strip('/').lower()
    r, u, cf, t = resolver(c)
    if r:
        return pl_proxy(r, u, cf, t)
    return f"404: {c} nao encontrado", 404

@app.route('/invalidar/<c>')
def invalidar(c):
    cache_del(c.strip('/').lower())
    return "ok"

@app.route('/deletar/<c>', methods=['DELETE'])
def del_c(c):
    ok = deletar(c.strip('/').lower())
    cache_del(c.strip('/').lower())
    return json.dumps({"success": ok})

@app.route('/listar')
def listar_salvos():
    return {"canais": listar()}

@app.route('/canais')
def listar_canais():
    return {"canais": CANAIS}

@app.route('/salvar', methods=['POST'])
def api_salvar():
    d = request.get_json() or {}
    canal = (d.get('canal') or '').strip().lower()
    bruto = (d.get('bruto') or '').strip()
    if not canal or not bruto:
        return {"ok": False, "msg": "Faltou canal ou bruto"}
    try:
        j = json.loads(bruto)
        cfg = normalizar_cfg_json(j)
        cfg["perfil_nome"] = canal
        cfg["canal_base"] = nome_url(cfg["url"])
        salvar(canal, cfg)
        cache_del(canal)
        link = f"{URL_PUBLICA or request.host_url.rstrip('/')}/play/{canal}"
        return {"ok": True, "link": link, "canal": canal}
    except Exception as e:
        return {"ok": False, "msg": f"JSON invalido: {e}"}

@app.route('/proxy_m3u8')
def pm8():
    t = unquote(request.args.get('url', ''))
    p = request.args.get('perfil', '')
    tn = request.args.get('tunel', 'chrome120')
    rf = unquote(request.args.get('ref', '') or '')
    ck = unquote(request.args.get('ck', '') or '')
    org = unquote(request.args.get('or', '') or '')
    cfg = carregar(p) or {"user_agent": UA}
    if ck:
        cfg["cookie"] = ck
    if rf:
        cfg["referer"] = rf
    if org:
        cfg["origin"] = org
    try:
        r = sessao(tn).get(t, headers=hdr(cfg, rf), timeout=8, verify=False)
        if r.status_code != 200:
            return f"upstream {r.status_code}", r.status_code
        L = []
        base = getattr(r, 'url', t)
        re_ = quote(rf or cfg.get("referer", "") or "", safe='')
        ce = quote(ck or cfg.get("cookie", "") or "", safe='')
        oe = quote(org or cfg.get("origin", "") or "", safe='')
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                au = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                q = f"url={quote(au, safe='')}&perfil={p}&tunel={tn}"
                if re_: q += f"&ref={re_}"
                if ce: q += f"&ck={ce}"
                if oe: q += f"&or={oe}"
                L.append(f"{ep}?{q}")
            else:
                L.append(ls)
        return Response("\n".join(L), headers={
            'Content-Type': 'application/vnd.apple.mpegurl',
            'Cache-Control': 'no-cache',
            'Access-Control-Allow-Origin': '*'
        })
    except Exception as e:
        return str(e), 500

@app.route('/ts_proxy')
def tsp():
    t = unquote(request.args.get('url', ''))
    p = request.args.get('perfil', '')
    tn = request.args.get('tunel', 'chrome120')
    rf = unquote(request.args.get('ref', '') or '')
    ck = unquote(request.args.get('ck', '') or '')
    org = unquote(request.args.get('or', '') or '')
    cfg = carregar(p) or {"user_agent": UA}
    if ck:
        cfg["cookie"] = ck
    if rf:
        cfg["referer"] = rf
    if org:
        cfg["origin"] = org
    try:
        r = sessao(tn).get(t, headers=hdr(cfg, rf), stream=True, timeout=10, verify=False)
        if r.status_code != 200:
            return f"upstream {r.status_code}", r.status_code

        def g():
            if hasattr(r, 'iter_content'):
                for ch in r.iter_content(128 * 1024):
                    if ch:
                        yield ch
            else:
                yield r.content

        return Response(g(), status=r.status_code, headers={
            'Content-Type': 'video/mp2t',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*'
        })
    except Exception as e:
        return f"Erro: {e}", 500

# ============ GITHUB SYNC (opcional) ============
def gh(fn, ct, msg):
    if not GH_API:
        return False
    h = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        r = sessao().get(f"{GH_API}/{fn}", headers=h, verify=False)
        d = {"message": msg, "content": base64.b64encode(ct.encode()).decode()}
        if r.status_code == 200:
            d["sha"] = r.json().get("sha", "")
        r2 = sessao().put(f"{GH_API}/{fn}", headers=h, json=d, verify=False)
        return r2.status_code in [200, 201]
    except Exception:
        return False

def m3u():
    if not URL_PUBLICA:
        return None
    L = ["#EXTM3U"]
    for p in listar():
        L += [f'#EXTINF:-1 tvg-name="{p.upper()}" group-title="MANUAIS",{p.upper()}', f"{URL_PUBLICA}/play/{p}"]
    for c in CANAIS:
        L += [f'#EXTINF:-1 tvg-name="{c.upper()}" group-title="CANAIS",{c.upper()}', f"{URL_PUBLICA}/play/{c}"]
    return "\n".join(L)

def att_m3u():
    c = m3u()
    if c and gh("lista_premium.m3u", c, f"Update {time.strftime('%d/%m/%Y %H:%M')}"):
        print(f"✅ Lista enviada: https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/main/lista_premium.m3u")

# ============ CLOUDFLARE TUNNEL (opcional) ============
def cf():
    while True:
        try:
            p = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", f"http://localhost:{PORTA}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            ult = None
            for ln in iter(p.stdout.readline, ""):
                m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', ln)
                if m and 'api.trycloudflare.com' not in m.group(0):
                    n = m.group(0).strip()
                    if n != ult:
                        ult = n
                        global URL_PUBLICA
                        URL_PUBLICA = n
                        print(f"🌐 {n}")
                        att_m3u()
            p.wait()
            time.sleep(5)
        except Exception:
            time.sleep(5)

def add_cli():
    print("\nCole JSON + Ctrl+D:")
    t = sys.stdin.read().strip()
    if not t:
        return
    try:
        d = json.loads(t)
        cfg = normalizar_cfg_json(d)
        s = nome_url(cfg["url"])
        n = input(f"Nome (Enter='{s}'): ").strip().lower() or s
        cfg["perfil_nome"] = n
        cfg["canal_base"] = s
        salvar(n, cfg)
        cache_del(n)
        print(f"✅ '{n}' salvo!")
    except Exception as e:
        print(f"❌ {e}")

# ============ MAIN ============
if __name__ == '__main__':
    modo_server = len(sys.argv) > 1 and sys.argv[1] == "server"

    if not modo_server:
        while True:
            os.system("clear||cls")
            print("=" * 50)
            print(" 📺 MARCOS TV (cache milissegundo)")
            print("=" * 50)
            print(f"Perfis: {listar()}")
            print(f"Cache disco: {len(os.listdir(CACHE_DIR))} canais")
            print(f"Cache RAM: {len(RAM)} canais\n")
            print(" [D] ADD BRUTO | [L] LIMPAR CACHE | [I] INICIAR | [S] SAIR")
            o = input("Opção: ").strip().upper()
            if o == "D":
                add_cli()
                input("ENTER...")
            elif o == "L":
                for f in os.listdir(CACHE_DIR):
                    os.remove(os.path.join(CACHE_DIR, f))
                with LOCK:
                    RAM.clear()
                print("🗑 Cache limpo!")
                input("ENTER...")
            elif o == "I":
                break
            elif o == "S":
                sys.exit(0)

    os.system(f"fuser -k {PORTA}/tcp >/dev/null 2>&1")
    os.system("clear||cls")
    print("=" * 40)
    print("  📺 MARCOS TV ONLINE")
    print("=" * 40)
    n = cache_preload()
    print(f"♻ {n} canais pré-carregados do disco")
    print(f"🌐 Porta: {PORTA}")
    if URL_PUBLICA:
        print(f"🔗 URL pública: {URL_PUBLICA}")
    print("=" * 40)

    if getpath("cloudflared"):
        threading.Thread(target=cf, daemon=True).start()

    logging.getLogger('werkzeug').disabled = True
    logging.getLogger('flask').disabled = True
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.log = lambda *a, **k: None

    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
