import os, re, json, time, threading, random, concurrent.futures
import urllib3
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

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"

# ============ POOL DE PROXIES ============
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
]

PROXY_POOL = []
PROXY_POOL_LOCK = threading.Lock()
PROXY_LAST_UPDATE = 0
PROXY_UPDATE_INTERVAL = 600

def testar_proxy(p):
    """Testa se o proxy funciona contra um site de teste."""
    try:
        s = ImpersonateSession.Session(impersonate="firefox133")
        s.proxies = {"http": f"http://{p}", "https": f"http://{p}"}
        r = s.get("https://api.ipify.org?format=json", timeout=8, verify=False)
        if r.status_code == 200:
            return p
    except Exception:
        pass
    return None

def carregar_proxies():
    global PROXY_POOL, PROXY_LAST_UPDATE
    todos = set()
    for url in PROXY_SOURCES:
        try:
            r = ImpersonateSession.Session(impersonate="chrome120").get(
                url, timeout=15, verify=False
            )
            if r.status_code == 200:
                for linha in r.text.splitlines():
                    linha = linha.strip()
                    if ":" in linha and not linha.startswith("#"):
                        todos.add(linha)
        except Exception:
            pass

    todos_lista = list(todos)[:500]
    validos = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as ex:
        for res in ex.map(testar_proxy, todos_lista):
            if res:
                validos.append(res)

    with PROXY_POOL_LOCK:
        PROXY_POOL = validos
        PROXY_LAST_UPDATE = time.time()

    print(f"[PROXY] {len(validos)} válidos de {len(todos_lista)} testados")
    return validos

def pegar_proxy():
    global PROXY_POOL, PROXY_LAST_UPDATE
    with PROXY_POOL_LOCK:
        if PROXY_POOL and (time.time() - PROXY_LAST_UPDATE) < PROXY_UPDATE_INTERVAL:
            return random.choice(PROXY_POOL)
    carregar_proxies()
    with PROXY_POOL_LOCK:
        return random.choice(PROXY_POOL) if PROXY_POOL else None

# ============ FIM PROXIES ============

TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 200
TS_CACHE_TEMPO = 120

ARQ_SALVOS = "canais_salvos.json"
CANAIS_LOCK = threading.Lock()

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

def criar_sessao(imp=None, com_proxy=False):
    s = None
    if USE_CURL:
        try:
            s = ImpersonateSession.Session(impersonate=imp or "firefox133")
        except Exception:
            pass
    if s is None:
        s = ImpersonateSession.Session()

    if com_proxy:
        p = pegar_proxy()
        if p:
            s.proxies = {"http": f"http://{p}", "https": f"http://{p}"}
    return s

def imp_do_ua(ua):
    if not ua:
        return "firefox133"
    if "Firefox" in ua:
        return "firefox133"
    if "Safari" in ua and "Chrome" not in ua:
        return "safari_15_5"
    return "chrome120"

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

def buscar_stream(canal, bruto, log):
    if not bruto:
        return None, None, None, None
    bruto = bruto.strip()
    cfg = None

    try:
        j = json.loads(bruto)
        url_in = (j.get("url") or "").strip()
        origin_in = j.get("origin") or j.get("origem") or ""
        if origin_in and not str(origin_in).startswith("http"):
            origin_in = ""
        if not origin_in and url_in:
            m = re.match(r'(https?://[^/]+)', url_in)
            if m:
                origin_in = m.group(1)
        referer_in = j.get("referer") or j.get("referrer") or ""
        if not referer_in and origin_in:
            referer_in = origin_in + "/"

        cfg = {
            "url": url_in,
            "user_agent": (j.get("user_agent") or USER_AGENT).strip(),
            "cookie": (j.get("cookie") or "").strip(),
            "origin": origin_in.strip(),
            "referer": referer_in.strip(),
        }
        log.append(f"[INPUT] url={cfg['url'][:80]}")
        log.append(f"[INPUT] origin={cfg['origin'][:50]} ref={cfg['referer'][:50]}")
    except json.JSONDecodeError:
        pass

    if not cfg and bruto.startswith("http"):
        alvo = substituir_canal(bruto, canal)
        m = re.match(r'(https?://[^/]+)', alvo)
        origin_auto = m.group(1) if m else ""
        cfg = {
            "url": alvo,
            "user_agent": USER_AGENT,
            "origin": origin_auto,
            "referer": (origin_auto + "/") if origin_auto else alvo,
        }

    if not cfg or not cfg.get("url"):
        return None, None, None, None

    alvo = substituir_canal(cfg["url"], canal)
    imp_pref = imp_do_ua(cfg.get("user_agent", ""))
    ordem = [imp_pref] + [p for p in ["firefox133", "chrome120", "chrome110", "safari_15_5"] if p != imp_pref]

    # 1) DIRETO
    for imp in ordem:
        try:
            sess = criar_sessao(imp, com_proxy=False)
            r = sess.get(alvo, headers=obter_headers(cfg), timeout=10, verify=False)
            log.append(f"[DIRETO] {imp} status={r.status_code}")
            if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                return (r, alvo, cfg, imp)
        except Exception as e:
            log.append(f"[DIRETO] {imp} erro: {type(e).__name__}")

    # 2) COM PROXY RESIDENCIAL
    log.append("[PROXY] Tentando proxies...")
    for imp in ordem[:2]:
        for tent in range(5):
            try:
                sess = criar_sessao(imp, com_proxy=True)
                r = sess.get(alvo, headers=obter_headers(cfg), timeout=15, verify=False)
                log.append(f"[PROXY] {imp} t{tent+1} status={r.status_code}")
                if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                    return (r, alvo, cfg, imp)
            except Exception as e:
                log.append(f"[PROXY] {imp} t{tent+1} erro: {type(e).__name__}")

    return None, None, None, None

# ============ HTML ============
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
  textarea { min-height: 120px; resize: vertical; }
  button { background: #00b894; color: #fff; border: 0; padding: 12px 20px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 0.95em; margin-right: 6px; margin-bottom: 6px; }
  button.salvar { background: #3498db; }
  .video-js { width: 100%; height: 380px; }
  @media (max-width: 600px) { .video-js { height: 200px; } }
  .log { font-size: 0.8em; color: #aaa; background: #0d0d14; padding: 10px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 500px; overflow-y: auto; }
  .log .ok { color: #00b894; }
  a { color: #00b894; word-break: break-all; }
</style>
</head>
<body>
  <div class="box">
    <h1>PLAYER DEBUG (com proxy residencial)</h1>
    <video id="player" class="video-js" controls playsinline></video>
    <input id="canal" placeholder="Nome do canal (ex: warner)">
    <button onclick="tocar()">PLAY</button>
    <button class="salvar" onclick="salvar()">SALVAR CANAL</button>
    <div class="log" id="log">Pronto</div>
  </div>

  <div class="box">
    <h1>DADOS BRUTOS</h1>
    <textarea id="bruto" placeholder="Cole aqui: JSON, URL m3u8, ou URL de site"></textarea>
  </div>

  <div class="box">
    <h1>CANAIS SALVOS</h1>
    <div id="listaSalvos" class="log">carregando...</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player');
var log = document.getElementById('log');

function atualizarLista() {
  fetch('/listar').then(r => r.json()).then(d => {
    if (!d.canais || !d.canais.length) {
      document.getElementById('listaSalvos').innerText = 'Nenhum canal salvo';
      return;
    }
    var html = '';
    d.canais.forEach(function(c) {
      var link = location.origin + '/fixo/' + c;
      html += '<div><b>' + c + '</b> → <a href="' + link + '" target="_blank">' + link + '</a> ';
      html += '<button onclick="navigator.clipboard.writeText(\\'' + link + '\\');this.innerText=\\'COPIADO\\'">COPIAR</button> ';
      html += '<button onclick="remover(\\'' + c + '\\')" style="background:#e74c3c">X</button></div>';
    });
    document.getElementById('listaSalvos').innerHTML = html;
  });
}

function remover(canal) {
  if (!confirm('Remover canal ' + canal + '?')) return;
  fetch('/remover/' + canal).then(() => atualizarLista());
}

function tocar() {
  var canal = document.getElementById('canal').value.trim().toLowerCase();
  var bruto = document.getElementById('bruto').value.trim();
  if (!canal) { log.innerText = 'Digite o canal'; return; }
  if (!bruto) { log.innerText = 'Cole os dados brutos'; return; }
  log.innerText = 'Testando com proxy (pode demorar 10-30s)...';
  fetch('/testar', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({canal: canal, bruto: bruto})
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      var src = '/play?canal=' + encodeURIComponent(canal) + '&bruto=' + encodeURIComponent(bruto);
      player.src({src: src, type: 'application/x-mpegURL'});
      player.play();
      log.innerText = 'Tocando: ' + canal;
      setTimeout(function() {
        if (confirm('Funcionou! Deseja SALVAR o canal "' + canal + '"?')) {
          fetch('/salvar', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({canal: canal, bruto: bruto})
          }).then(r => r.json()).then(s => {
            if (s.ok) {
              log.innerHTML = '<span class="ok">Canal salvo!<br>Link fixo: <a href="' + s.link + '" target="_blank">' + s.link + '</a></span>';
              atualizarLista();
            }
          });
        }
      }, 2000);
    } else {
      log.innerText = d.msg || 'Nao foi possivel';
    }
  }).catch(e => { log.innerText = 'Erro: ' + e; });
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

@app.route('/testar', methods=['POST'])
def testar():
    d = request.get_json() or {}
    canal = (d.get('canal') or '').strip().lower()
    bruto = (d.get('bruto') or '').strip()
    if not canal or not bruto:
        return {"ok": False, "msg": "Preencha os campos"}
    log = []
    r = buscar_stream(canal, bruto, log)
    if r[0]:
        return {"ok": True}
    return {"ok": False, "msg": "Nao consegui nem com proxy."}

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
    if not cfg:
        return f"Canal '{canal}' nao salvo", 404
    log = []
    r = buscar_stream(canal, cfg["bruto"], log)
    if r[0]:
        resp, url_a, cfg_usado, tunel = r
        return gerar_playlist(resp, url_a, cfg_usado, tunel)
    return f"Canal {canal} falhou", 500

@app.route('/play')
def play():
    canal = (request.args.get('canal') or '').strip().lower()
    bruto = unquote(request.args.get('bruto') or '').strip()
    if not canal or not bruto:
        return "Faltam parametros", 400
    log = []
    r = buscar_stream(canal, bruto, log)
    if r[0]:
        resp, url_a, cfg_usado, tunel = r
        return gerar_playlist(resp, url_a, cfg_usado, tunel)
    return f"Canal {canal} nao encontrado", 404

def gerar_playlist(resp, url_a, cfg, tunel):
    host = url_base()
    linhas = []
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
            linhas.append(f"{host}{ep}?{q}")
        else:
            linhas.append(ls)
    return Response("\n".join(linhas), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*'
    })

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    tunel = request.args.get('tunel', 'firefox133')
    ref_custom = unquote(request.args.get('ref', '') or '')
    ck_custom = unquote(request.args.get('ck', '') or '')
    org_custom = unquote(request.args.get('or', '') or '')
    if not target:
        return "URL ausente", 400

    # tenta direto e com proxy
    for com_proxy in [False, True, True]:
        sess = criar_sessao(tunel, com_proxy=com_proxy)
        h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if ref_custom: h["Referer"] = ref_custom
        if ck_custom: h["Cookie"] = ck_custom
        if org_custom: h["Origin"] = org_custom
        try:
            r = sess.get(target, headers=h, timeout=12, verify=False)
            if r.status_code == 200:
                host = url_base()
                linhas = []
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
                        linhas.append(f"{host}{ep}?{q}")
                    else:
                        linhas.append(ls)
                return Response("\n".join(linhas), status=200, headers={
                    'Content-Type': 'application/vnd.apple.mpegurl',
                    'Access-Control-Allow-Origin': '*'
                })
        except Exception:
            continue
    return "Falhou direto e via proxy", 502

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    tunel = request.args.get('tunel', 'firefox133')
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
                    'Access-Control-Allow-Origin': '*'
                })
            for com_proxy in [False, True, True]:
        sess = criar_sessao(tunel, com_proxy=com_proxy)
        h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if ref_custom: h["Referer"] = ref_custom
        if ck_custom: h["Cookie"] = ck_custom
        if org_custom: h["Origin"] = org_custom
        try:
            r = sess.get(target, headers=h, timeout=20, verify=False)
            if r.status_code == 200:
                conteudo = r.content
                with TS_CACHE_LOCK:
                    if len(TS_CACHE) >= TS_CACHE_MAX:
                        mais = min(TS_CACHE.items(), key=lambda kv: kv[1][1])
                        del TS_CACHE[mais[0]]
                    TS_CACHE[target] = (conteudo, time.time())
                return Response(conteudo, status=200, headers={
                    'Content-Type': 'video/mp2t',
                    'Content-Length': str(len(conteudo)),
                    'Cache-Control': 'public, max-age=60',
                    'Accept-Ranges': 'bytes',
                    'Access-Control-Allow-Origin': '*'
                })
        except Exception:
            continue
    return "Falhou direto e via proxy", 502

if __name__ == '__main__':
    # Pré-carrega proxies no boot
    print("Carregando lista de proxies (isso pode levar 30s)...")
    threading.Thread(target=carregar_proxies, daemon=True).start()
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
