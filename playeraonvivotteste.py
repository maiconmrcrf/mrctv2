import os, re, json, time, threading
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

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 10000))

# ==========================================================
# 3 TEMPLATES FIXOS
# ==========================================================
TEMPLATES = [
    {
        "nome": "cdn13embed",
        "url": "https://ywppjexvlyulasvmgzjdftfjikth1709oq80soveui6lkbi2iza2zf.cdn13embed.xyz/{canal}/index.m3u8",
        "user_agent": "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0",
        "cookie": "__dtsu=51A017746968408D2A64C9BB119F7C31; _ga=GA1.1.82788829.1788834221; _ga_2T9N2RHEW3=GS2.1.s1789787692$o8$g0$t1789787692$j60$l0$h0",
        "origin": "https://1709.cdnembedcanais.xyz",
        "referer": "https://1709.cdnembedcanais.xyz/{canal}/",
        "extra_headers": {}
    },
    {
        "nome": "ssl-images-cdn",
        "url": "https://za260pb3a281.ssl-images-cdn.site/live/secure/Y268yrAOpISOsm-I2QK6YhusYCGFnsLqG4xL1QWLlfE/1789809883/d58366a60d35086a/{canal}/index.m3u8",
        "user_agent": "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0",
        "cookie": "sid=d58366a60d35086a",
        "origin": "https://player.cdn-img.st",
        "referer": "https://player.cdn-img.st/{canal}.html",
        "extra_headers": {}
    },
    {
        "nome": "f8umt2oop68t",
        "url": "https://f8umt2oop68t.sbs/live/secure/oHEwnKLrH-OwU22w3Y26wZ8n0Ay9sNR5ZsH59KBTpOM/1789809844/d6c96ae763d80960/{canal}/index.m3u8",
        "user_agent": "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0",
        "cookie": "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f",
        "origin": "https://bolodechocolate.fit",
        "referer": "https://bolodechocolate.fit/play/{canal}.html",
        "extra_headers": {}
    },
]

# ==========================================================

TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 500
TS_CACHE_TEMPO = 90

TEMPLATE_USADO = {}
TEMPLATE_USADO_LOCK = threading.Lock()

def criar_sessao():
    if USE_CURL:
        try:
            return ImpersonateSession.Session(impersonate="firefox133")
        except Exception:
            pass
    return ImpersonateSession.Session()

def montar_url(canal, tpl):
    return tpl["url"].replace("{canal}", canal)

def montar_referer(canal, tpl):
    ref = tpl.get("referer", "") or ""
    return ref.replace("{canal}", canal) if ref else ""

def obter_headers(canal, tpl):
    h = {
        "User-Agent": tpl.get("user_agent") or "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    if tpl.get("origin"):
        h["Origin"] = tpl["origin"]
    ref = montar_referer(canal, tpl)
    if ref:
        h["Referer"] = ref
    if tpl.get("cookie"):
        h["Cookie"] = tpl["cookie"]
    extras = tpl.get("extra_headers") or {}
    if isinstance(extras, dict):
        for k, v in extras.items():
            if k and v:
                h[str(k)] = str(v)
    return h

def buscar_m3u8(canal):
    for tpl in TEMPLATES:
        url = montar_url(canal, tpl)
        h = obter_headers(canal, tpl)
        sess = criar_sessao()
        try:
            r = sess.get(url, headers=h, timeout=12, verify=False)
            if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                with TEMPLATE_USADO_LOCK:
                    TEMPLATE_USADO[canal] = tpl["nome"]
                return r, url, tpl
        except Exception:
            continue
    return None, None, None

def buscar_segmento(url_seg, canal):
    with TS_CACHE_LOCK:
        item = TS_CACHE.get(url_seg)
        if item:
            dados, t = item
            if time.time() - t < TS_CACHE_TEMPO:
                return dados, 200

    with TEMPLATE_USADO_LOCK:
        nome_tpl = TEMPLATE_USADO.get(canal)

    tpl = None
    for t in TEMPLATES:
        if t["nome"] == nome_tpl:
            tpl = t
            break
    if not tpl:
        tpl = TEMPLATES[0]

    h = obter_headers(canal, tpl)
    for tent in range(2):
        sess = criar_sessao()
        try:
            r = sess.get(url_seg, headers=h, timeout=8, verify=False)
            if r.status_code == 200:
                with TS_CACHE_LOCK:
                    if len(TS_CACHE) >= TS_CACHE_MAX:
                        mais = min(TS_CACHE.items(), key=lambda kv: kv[1][1])
                        del TS_CACHE[mais[0]]
                    TS_CACHE[url_seg] = (r.content, time.time())
                return r.content, 200
            if r.status_code in (403, 404):
                return None, r.status_code
        except Exception:
            pass
    return None, 502

HTML_PAGINA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: #000;
    color: #fff;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .app { width: 100%; max-width: 900px; }
  .brand { text-align: center; margin-bottom: 30px; }
  .brand h1 {
    font-size: clamp(2.4em, 9vw, 4em);
    font-weight: 900;
    letter-spacing: 4px;
    color: #fff;
    margin-bottom: 6px;
  }
  .brand .sub {
    color: #666;
    font-size: 0.72em;
    letter-spacing: 6px;
    font-weight: 500;
    text-transform: uppercase;
  }
  .header-line {
    width: 60px; height: 2px;
    background: #fff;
    margin: 16px auto 0;
    opacity: 0.3;
  }
  .player-wrap {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 14px;
    margin-bottom: 16px;
  }
  .video-js {
    width: 100%;
    height: 440px;
    border-radius: 10px;
    overflow: hidden;
    background: #000;
  }
  @media (max-width: 640px) { .video-js { height: 240px; } }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; }
  .controls input {
    flex: 1;
    min-width: 180px;
    background: #0a0a0a;
    border: 1.5px solid #222;
    color: #fff;
    padding: 16px 18px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 1em;
    font-weight: 500;
    outline: none;
    transition: border-color 0.2s;
  }
  .controls input:focus { border-color: #fff; }
  .controls input::placeholder { color: #555; font-weight: 400; }
  .controls button {
    background: #fff;
    color: #000;
    border: none;
    padding: 16px 36px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1em;
    letter-spacing: 1.5px;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .controls button:hover {
    background: #e5e5e5;
    transform: translateY(-1px);
  }
  .controls button:active { transform: translateY(0); }
  .controls button:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  .footer {
    text-align: center;
    color: #333;
    font-size: 0.7em;
    letter-spacing: 2px;
    margin-top: 22px;
  }
  .video-js .vjs-big-play-button {
    background: rgba(255, 255, 255, 0.95);
    border: none;
    width: 80px; height: 80px; line-height: 80px;
    border-radius: 50%;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
  }
  .video-js .vjs-big-play-button .vjs-icon-placeholder:before {
    color: #000; font-size: 2em; line-height: 80px;
  }
  .video-js .vjs-big-play-button:hover {
    background: #fff;
    transform: translate(-50%, -50%) scale(1.08);
  }
  .video-js .vjs-control-bar {
    background: rgba(0, 0, 0, 0.85);
    height: 46px;
  }
  .video-js .vjs-play-progress { background: #fff; }
  .video-js .vjs-load-progress { background: rgba(255,255,255,0.2); }
  .video-js .vjs-slider { background: rgba(255,255,255,0.15); }
</style>
</head>
<body>
  <div class="app">
    <div class="brand">
      <h1>MARCOS TV</h1>
      <div class="sub">Premium Streaming</div>
      <div class="header-line"></div>
    </div>

    <div class="player-wrap">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>
    </div>

    <div class="controls">
      <input id="canal" type="text" placeholder="Digite o nome do canal" autocomplete="off" spellcheck="false">
      <button id="btnPlay" onclick="tocar()">PLAY</button>
    </div>

    <div class="footer">© MARCOS TV</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player', {
  controls: true,
  autoplay: false,
  preload: 'auto',
  liveui: true,
  html5: {
    vhs: {
      overrideNative: true,
      maxBufferLength: 60,
      maxMaxBufferLength: 120,
      liveSyncDuration: 10,
      liveMaxLatencyDuration: 60,
      enableLowInitialPlaylist: true,
      limitRenditionByPlayerDimensions: false,
      smoothQualityChange: true,
      fastQualityChange: true
    }
  }
});
var btn = document.getElementById('btnPlay');
var input = document.getElementById('canal');

function tocar() {
  var canal = input.value.trim().toLowerCase();
  if (!canal) { input.focus(); return; }
  btn.disabled = true;

  var t = setTimeout(function(){ btn.disabled = false; }, 20000);

  fetch('/testar/' + encodeURIComponent(canal))
    .then(r => r.json())
    .then(d => {
      clearTimeout(t);
      btn.disabled = false;
      if (d.ok) {
        player.src({ src: '/play/' + encodeURIComponent(canal) + '?t=' + Date.now(), type: 'application/x-mpegURL' });
        player.play().catch(function(){});
      }
    })
    .catch(function() {
      clearTimeout(t);
      btn.disabled = false;
    });
}

// Reconexao automatica
player.on('error', function() {
  setTimeout(function() {
    var s = player.src();
    if (s && s.indexOf('/play/') !== -1) {
      var c = s.split('/play/')[1].split('?')[0];
      player.src({ src: '/play/' + c + '?t=' + Date.now(), type: 'application/x-mpegURL' });
      player.play().catch(function(){});
    }
  }, 1500);
});

// Detecta travamento (10s sem progresso)
var ultimoTempo = 0;
var travadoDesde = null;
setInterval(function() {
  if (player.paused() || player.readyState() < 2) { travadoDesde = null; return; }
  var t = player.currentTime();
  if (t === ultimoTempo) {
    if (!travadoDesde) travadoDesde = Date.now();
    else if (Date.now() - travadoDesde > 10000) {
      travadoDesde = null;
      var s = player.src();
      if (s && s.indexOf('/play/') !== -1) {
        var c = s.split('/play/')[1].split('?')[0];
        player.src({ src: '/play/' + c + '?t=' + Date.now(), type: 'application/x-mpegURL' });
        player.play().catch(function(){});
      }
    }
  } else { ultimoTempo = t; travadoDesde = null; }
}, 2000);

input.addEventListener('keydown', function(e) { if (e.key === 'Enter') tocar(); });
</script>
</body>
</html>
"""

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    return r

@app.route('/')
def index():
    return render_template_string(HTML_PAGINA)

@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return jsonify({"ok": False, "msg": "Nome invalido"})
    r, _, tpl = buscar_m3u8(canal)
    if r:
        return jsonify({"ok": True, "fonte": tpl["nome"]})
    return jsonify({"ok": False, "msg": "Canal indisponivel"})

@app.route('/play/<canal>')
def play(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return "Nome invalido", 400

    r, url_orig, tpl = buscar_m3u8(canal)
    if not r:
        return "Canal nao encontrado", 404

    base = getattr(r, 'url', url_orig)
    linhas = []
    for l in r.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{ep}?url={quote(abs_url, safe='')}&canal={canal}")
        else:
            linhas.append(ls)

    return Response("\n".join(linhas), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'no-cache'
    })

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal:
        return "Faltam parametros", 400

    with TEMPLATE_USADO_LOCK:
        nome_tpl = TEMPLATE_USADO.get(canal)
    tpl = None
    for t in TEMPLATES:
        if t["nome"] == nome_tpl:
            tpl = t
            break
    if not tpl:
        tpl = TEMPLATES[0]

    h = obter_headers(canal, tpl)
    sess = criar_sessao()
    try:
        r = sess.get(target, headers=h, timeout=12, verify=False)
        if r.status_code != 200:
            return f"upstream {r.status_code}", r.status_code

        base = getattr(r, 'url', target)
        linhas = []
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                linhas.append(f"{ep}?url={quote(abs_url, safe='')}&canal={canal}")
            else:
                linhas.append(ls)

        return Response("\n".join(linhas), status=200, headers={
            'Content-Type': 'application/vnd.apple.mpegurl',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache'
        })
    except Exception as e:
        return f"Erro: {e}", 500

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal:
        return "Faltam parametros", 400

    conteudo, status = buscar_segmento(target, canal)
    if conteudo is None:
        return f"Erro segmento {status}", status

    return Response(conteudo, status=200, headers={
        'Content-Type': 'video/mp2t',
        'Content-Length': str(len(conteudo)),
        'Cache-Control': 'public, max-age=60',
        'Accept-Ranges': 'bytes',
        'Access-Control-Allow-Origin': '*'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
