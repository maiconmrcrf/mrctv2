import os, re, json, time, threading
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

# ====== URL PUBLICA ======
# No Render, deixa vazio que ele descobre sozinho pelo host
URL_PUBLICA = os.environ.get("URL_PUBLICA", "")

def url_base():
    if URL_PUBLICA:
        return URL_PUBLICA.rstrip("/")
    # descobre pelo host do request
    host = request.host_url.rstrip("/")
    return host

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXIES = ["chrome120", "chrome110", "safari_15_5"]

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
        "Connection": "keep-alive"
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

def extrair_links_playlist(html):
    padroes = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.txt[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.m3u[^\s"\'<>]*)',
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        r'source\s*:\s*["\'](https?://[^"\']+)["\']',
        r'["\'](//[^\s"\']+\.m3u8[^\s"\']*)["\']'
    ]
    achados = []
    for p in padroes:
        m = re.findall(p, html, re.I)
        if m:
            achados.extend(m)
    return list(set(achados))

def debug_extrair(url_pagina, log):
    resultado = {
        "url_pagina": url_pagina,
        "http_status": None,
        "content_length": None,
        "content_type": None,
        "links_encontrados": [],
        "links_validados": [],
        "html_preview": None,
        "cookies": None,
        "selenium_usado": False,
        "erro": None
    }

    sess = criar_sessao("chrome120")

    try:
        log.append(f"[HTTP] GET {url_pagina[:120]}")
        r = sess.get(url_pagina, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, timeout=10, verify=False)
        resultado["http_status"] = r.status_code
        resultado["content_type"] = r.headers.get("Content-Type", "")
        resultado["content_length"] = len(r.text)
        resultado["html_preview"] = r.text[:3000]
        log.append(f"[HTTP] status={r.status_code} len={len(r.text)}")

        if r.status_code == 200 and "#EXTM3U" in r.text:
            log.append("[HTTP] Ja e um m3u8 direto!")
            return (r, url_pagina, {"user_agent": USER_AGENT}, "chrome120"), resultado

        if r.status_code == 200:
            links = extrair_links_playlist(r.text)
            resultado["links_encontrados"] = links[:20]
            log.append(f"[HTTP] {len(links)} link(s) encontrados")
            for lk in links:
                if lk.startswith("//"):
                    lk = "https:" + lk
                if not lk.startswith("http"):
                    continue
                try:
                    r2 = sess.get(lk, headers={"User-Agent": USER_AGENT, "Referer": url_pagina}, timeout=10, verify=False)
                    if r2.status_code == 200 and ("#EXTM3U" in r2.text or "#EXT-X" in r2.text):
                        resultado["links_validados"].append(lk)
                        log.append(f"[HTTP] VALIDO: {lk[:100]}")
                        cfg = {"user_agent": USER_AGENT, "referer": url_pagina}
                        return (r2, lk, cfg, "chrome120"), resultado
                except Exception as e:
                    log.append(f"[HTTP] link erro: {e}")

    except Exception as e:
        resultado["erro"] = f"HTTP: {e}"
        log.append(f"[HTTP] Excecao: {e}")

    log.append("[FIM] Nada funcionou")
    return None, resultado

def buscar_stream(canal, bruto, log):
    if not bruto:
        return None, None, None, None
    bruto = bruto.strip()
    cfg = None

    try:
        j = json.loads(bruto)
        cfg = {
            "url": j.get("url", "").strip(),
            "user_agent": j.get("user_agent", "").strip() or USER_AGENT,
            "cookie": j.get("cookie", "").strip(),
            "origin": j.get("origin", "").strip(),
            "referer": j.get("referer", "").strip()
        }
        log.append(f"[INPUT] JSON url={cfg['url'][:100]}")
    except json.JSONDecodeError:
        pass

    if not cfg and bruto.startswith("http"):
        log.append(f"[INPUT] URL={bruto[:100]}")
        alvo = substituir_canal(bruto, canal)
        cfg = {"url": alvo, "user_agent": USER_AGENT, "referer": alvo}

    if not cfg:
        return None, None, None, None

    alvo = substituir_canal(cfg["url"], canal)
    log.append(f"[CFG] Tentando {alvo[:120]}")

    for imp in PROXIES:
        try:
            sess = criar_sessao(imp)
            r = sess.get(alvo, headers=obter_headers(cfg), timeout=10, verify=False)
            log.append(f"[CFG] {imp} status={r.status_code}")
            if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                return (r, alvo, cfg, imp)
        except Exception as e:
            log.append(f"[CFG] {imp} erro: {e}")

    r, dbg = debug_extrair(alvo, log)
    if r:
        return r

    return None, None, None, None

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
  .log { font-size: 0.8em; color: #aaa; background: #0d0d14; padding: 10px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 500px; overflow-y: auto; }
  .log .ok { color: #00b894; }
  .log .err { color: #e74c3c; }
  a { color: #00b894; word-break: break-all; }
</style>
</head>
<body>
  <div class="box">
    <h1>PLAYER DEBUG</h1>
    <video id="player" class="video-js" controls playsinline></video>
    <input id="canal" placeholder="Nome do canal (ex: tnt)">
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
  log.innerText = 'Testando...';
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
            } else {
              log.innerText = 'Erro ao salvar: ' + (s.msg || '');
            }
          });
        } else {
          log.innerText = 'Tocando (nao salvo): ' + canal;
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
    return {"ok": False, "msg": "Nao consegui. Use DEBUG."}

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
    ref = quote(cfg.get("referer", ""))
    ck = quote(cfg.get("cookie", ""))
    for l in resp.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{host}{ep}?url={quote(abs_url)}&tunel={tunel}&ref={ref}&ck={ck}")
        else:
            linhas.append(ls)
    return Response("\n".join(linhas), status=200, headers={'Content-Type': 'application/vnd.apple.mpegurl'})

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', ''))
    ck_custom = unquote(request.args.get('ck', ''))
    if not target:
        return "URL ausente", 400
    sess = criar_sessao(tunel)
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if ref_custom: h["Referer"] = ref_custom
    if ck_custom: h["Cookie"] = ck_custom
    try:
        r = sess.get(target, headers=h, timeout=8, verify=False)
        host = url_base()
        linhas = []
        base = getattr(r, 'url', target)
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                linhas.append(f"{host}{ep}?url={quote(abs_url)}&tunel={tunel}&ref={quote(ref_custom)}&ck={quote(ck_custom)}")
            else:
                linhas.append(ls)
        return Response("\n".join(linhas), status=200, headers={'Content-Type': 'application/vnd.apple.mpegurl'})
    except Exception as e:
        return f"Erro: {e}", 500

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', ''))
    ck_custom = unquote(request.args.get('ck', ''))
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
                    'Accept-Ranges': 'bytes'
                })
    sess = criar_sessao(tunel)
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if ref_custom: h["Referer"] = ref_custom
    if ck_custom: h["Cookie"] = ck_custom
    try:
        r = sess.get(target, headers=h, timeout=15, verify=False)
        conteudo = r.content
        with TS_CACHE_LOCK:
            if len(TS_CACHE) >= TS_CACHE_MAX:
                mais_antigo = min(TS_CACHE.items(), key=lambda kv: kv[1][1])
                del TS_CACHE[mais_antigo[0]]
            TS_CACHE[target] = (conteudo, time.time())
        return Response(conteudo, status=r.status_code, headers={
            'Content-Type': 'video/mp2t',
            'Content-Length': str(len(conteudo)),
            'Cache-Control': 'public, max-age=60',
            'Accept-Ranges': 'bytes'
        })
    except Exception as e:
        return f"Erro TS: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
