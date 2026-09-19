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

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 10000))

URL_PUBLICA = os.environ.get("URL_PUBLICA", "")

def url_base():
    if URL_PUBLICA:
        return URL_PUBLICA.rstrip("/")
    return request.host_url.rstrip("/")

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 500
TS_CACHE_TEMPO = 90

# ====== CANAIS HLS (passam pelo proxy) ======
CANAIS_FIXOS = [
    "espn",
    "premiere1",
    "tnt",
    "telecinepipoca",
    "telecinefun",
    "telecinepremium",
    "space",
    "warner",
]

# ====== CANAIS MPEG-TS (tocam direto com mpegts.js) ======
CANAIS_MPEGTS = {
    "premiere1": "http://79.127.238.228:14157/",
    "warner":    "http://79.127.238.228:14647/",
}

def criar_sessao(imp=None):
    if USE_CURL:
        try:
            return ImpersonateSession.Session(impersonate=imp or "firefox133")
        except Exception:
            pass
    return ImpersonateSession.Session()

def montar_url(canal):
    canal = canal.strip().lower()
    return f"https://f8umt2oop68t.sbs/live/secure/pHGsJJgoEUBc-K5ACe7Hws--gF0WDhHii_3tGSGwoq4/1789760848/1d256d1fe0127694/{canal}/index.m3u8"

def montar_referer(canal):
    canal = canal.strip().lower()
    return f"{ORIGIN_FIXO}/play/{canal}.html"

def obter_headers(canal):
    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Origin": ORIGIN_FIXO,
        "Referer": montar_referer(canal),
        "Cookie": COOKIE_FIXO,
        "Connection": "keep-alive",
    }

def buscar_m3u8(canal):
    url = montar_url(canal)
    h = obter_headers(canal)
    sess = criar_sessao("firefox133")
    try:
        r = sess.get(url, headers=h, timeout=15, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            return r, url
    except Exception:
        pass
    return None, None

def buscar_segmento(url_segmento, canal):
    with TS_CACHE_LOCK:
        item = TS_CACHE.get(url_segmento)
        if item:
            dados, t = item
            if time.time() - t < TS_CACHE_TEMPO:
                return dados, 200

    h = obter_headers(canal)
    for tent in range(2):
        sess = criar_sessao("firefox133")
        try:
            r = sess.get(url_segmento, headers=h, timeout=8, verify=False)
            if r.status_code == 200:
                with TS_CACHE_LOCK:
                    if len(TS_CACHE) >= TS_CACHE_MAX:
                        mais = min(TS_CACHE.items(), key=lambda kv: kv[1][1])
                        del TS_CACHE[mais[0]]
                    TS_CACHE[url_segmento] = (r.content, time.time())
                return r.content, 200
            if r.status_code in (403, 404):
                return None, r.status_code
        except Exception:
            pass
    return None, 502

# ============ HTML ============
HTML_PAGINA = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: radial-gradient(ellipse at top, #1a1a2e 0%, #0a0a0f 60%);
    color: #fff;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .app { width: 100%; max-width: 900px; }
  .brand { text-align: center; margin-bottom: 28px; }
  .brand h1 {
    font-size: clamp(2.2em, 8vw, 3.5em);
    font-weight: 900;
    letter-spacing: 2px;
    background: linear-gradient(135deg, #ffffff 0%, #a29bfe 50%, #6c5ce7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 6px;
    text-shadow: 0 0 40px rgba(108, 92, 231, 0.3);
  }
  .brand .sub {
    color: #6c5ce7;
    font-size: 0.75em;
    letter-spacing: 4px;
    font-weight: 600;
    text-transform: uppercase;
    opacity: 0.8;
  }
  .player-card {
    background: rgba(20, 20, 31, 0.85);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(108, 92, 231, 0.25);
    border-radius: 20px;
    padding: 18px;
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6), 0 0 80px rgba(108, 92, 231, 0.1);
    margin-bottom: 18px;
  }
  .video-js, #player_mpeg {
    width: 100%;
    height: 420px;
    border-radius: 14px;
    overflow: hidden;
    background: #000;
  }
  #player_mpeg { display: none; }
  @media (max-width: 640px) { .video-js, #player_mpeg { height: 220px; } }
  .controls {
    display: flex;
    gap: 10px;
    margin-top: 16px;
    flex-wrap: wrap;
  }
  .controls input {
    flex: 1;
    min-width: 160px;
    background: rgba(13, 13, 20, 0.9);
    border: 1.5px solid rgba(108, 92, 231, 0.3);
    color: #fff;
    padding: 14px 16px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 1em;
    font-weight: 500;
    outline: none;
    transition: all 0.2s;
  }
  .controls input:focus {
    border-color: #6c5ce7;
    box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.15);
  }
  .controls input::placeholder { color: #555; }
  .controls button {
    background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
    color: #fff;
    border: none;
    padding: 14px 28px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1em;
    letter-spacing: 0.5px;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: 0 8px 20px rgba(108, 92, 231, 0.35);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .controls button:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 28px rgba(108, 92, 231, 0.5);
  }
  .controls button:active { transform: translateY(0); }
  .controls button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .canais-fixos {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
  }
  .canal-btn {
    background: rgba(20, 20, 31, 0.7);
    border: 1.5px solid rgba(108, 92, 231, 0.4);
    color: #a29bfe;
    padding: 14px 8px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 0.8em;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
    text-shadow: 0 0 10px rgba(162, 155, 254, 0.6);
  }
  .canal-btn:hover {
    background: rgba(108, 92, 231, 0.15);
    border-color: #a29bfe;
    color: #fff;
    text-shadow: 0 0 16px rgba(162, 155, 254, 1);
    box-shadow: 0 0 25px rgba(108, 92, 231, 0.4);
    transform: translateY(-2px);
  }
  .canal-btn:active { transform: translateY(0); }
  .canal-btn.ativo {
    background: linear-gradient(135deg, rgba(108, 92, 231, 0.35), rgba(162, 155, 254, 0.35));
    border-color: #a29bfe;
    color: #fff;
    box-shadow: 0 0 30px rgba(108, 92, 231, 0.6);
  }

  .footer {
    text-align: center;
    color: #444;
    font-size: 0.75em;
    letter-spacing: 1px;
    margin-top: 20px;
  }
</style>
</head>
<body>
  <div class="app">
    <div class="brand">
      <h1>MARCOS TV</h1>
      <div class="sub">Premium Streaming</div>
    </div>

    <div class="player-card">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>
      <video id="player_mpeg" controls playsinline></video>

      <div class="canais-fixos">
        {% for c in canais %}
        <div class="canal-btn" data-canal="{{ c }}" onclick="tocarFixo('{{ c }}', this)">{{ c }}</div>
        {% endfor %}
      </div>

      <div class="controls">
        <input id="canal" type="text" placeholder="Nome do canal (ex: discoveryturbo)" autocomplete="off">
        <button id="btnPlay" onclick="tocar()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          PLAY
        </button>
      </div>
    </div>

    <div class="footer">© MARCOS TV</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mpegts.js@1.7.3/dist/mpegts.js"></script>
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

var videoJsEl = document.getElementById('player');
var videoMpegEl = document.getElementById('player_mpeg');

var playerMpeg = null;
var modoMpeg = false;

// ===== CANAIS MPEG-TS (vem do backend) =====
var CANAIS_MPEGTS = {{ canais_mpegts_json|safe }};
var PAGINA_HTTPS = (location.protocol === 'https:');

function marcarAtivo(el) {
  document.querySelectorAll('.canal-btn').forEach(function(b){ b.classList.remove('ativo'); });
  if (el) el.classList.add('ativo');
}

function pararMpeg() {
  if (playerMpeg) {
    try { playerMpeg.pause(); } catch(e){}
    try { playerMpeg.unload(); } catch(e){}
    try { playerMpeg.detachMediaElement(); } catch(e){}
    try { playerMpeg.destroy(); } catch(e){}
    playerMpeg = null;
  }
  modoMpeg = false;
}

// ===== TOCA MPEG-TS =====
// Em HTTP: usa URL direta (funciona 100%)
// Em HTTPS: usa proxy do Flask (fallback — pode cortar no Render)
function tocarMpegTs(canal) {
  pararMpeg();
  player.pause();

  videoJsEl.style.display = 'none';
  videoMpegEl.style.display = 'block';
  modoMpeg = true;

  var url;
  if (PAGINA_HTTPS) {
    url = '/mpegts_proxy?canal=' + encodeURIComponent(canal);
  } else {
    url = CANAIS_MPEGTS[canal];
  }

  try {
    playerMpeg = mpegts.createPlayer({
      type: 'mpegts',
      isLive: true,
      url: url
    }, {
      enableWorker: false,
      enableStashBuffer: false,
      stashInitialSize: 128,
      liveBufferLatencyChasing: true,
      liveBufferLatencyMaxLatency: 3.0,
      liveBufferLatencyMinRemain: 0.3
    });

    playerMpeg.attachMediaElement(videoMpegEl);
    playerMpeg.load();

    var p = playerMpeg.play();
    if (p && p.catch) p.catch(function(){});
  } catch (e) {}
}

function tocarHls(canal) {
  pararMpeg();
  videoMpegEl.style.display = 'none';
  videoJsEl.style.display = 'block';

  player.src({ src: '/play/' + encodeURIComponent(canal) + '?t=' + Date.now(), type: 'application/x-mpegURL' });
  player.play().catch(function(){});
}

function tocarFixo(canal, el) {
  marcarAtivo(el);
  input.value = canal;
  tocar();
}

function tocar() {
  var canal = input.value.trim().toLowerCase();
  if (!canal) { input.focus(); return; }

  if (CANAIS_MPEGTS[canal]) {
    tocarMpegTs(canal);
    return;
  }

  fetch('/testar/' + encodeURIComponent(canal))
    .then(r => r.json())
    .then(d => {
      if (d.ok) tocarHls(canal);
    })
    .catch(function(){});
}

function recarregar() {
  if (modoMpeg) return;
  var s = player.src();
  if (!s || s.indexOf('/play/') === -1) return;
  var canal = s.split('/play/')[1].split('?')[0];
  player.src({ src: '/play/' + canal + '?t=' + Date.now(), type: 'application/x-mpegURL' });
  player.play().catch(function(){});
}

player.on('error', function() { setTimeout(recarregar, 1000); });

var ultimoTempo = 0;
var travadoDesde = null;
setInterval(function() {
  if (modoMpeg) return;
  if (player.paused() || player.readyState() < 2) { travadoDesde = null; return; }
  var t = player.currentTime();
  if (t === ultimoTempo) {
    if (!travadoDesde) travadoDesde = Date.now();
    else if (Date.now() - travadoDesde > 10000) { travadoDesde = null; recarregar(); }
  } else { ultimoTempo = t; travadoDesde = null; }
}, 2000);

input.addEventListener('keydown', function(e) { if (e.key === 'Enter') tocar(); });
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
    return render_template_string(
        HTML_PAGINA,
        canais=CANAIS_FIXOS,
        canais_mpegts_json=json.dumps(CANAIS_MPEGTS)
    )

@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return {"ok": False}
    r, _ = buscar_m3u8(canal)
    return {"ok": bool(r)}

@app.route('/play/<canal>')
def play(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return "Nome invalido", 400

    r, url_orig = buscar_m3u8(canal)
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

# ============ PROXY MPEG-TS (só usado em HTTPS) ============
@app.route('/mpegts_proxy')
def mpegts_proxy():
    canal = (request.args.get('canal') or '').strip().lower()
    if canal not in CANAIS_MPEGTS:
        return "Canal invalido", 400

    target = CANAIS_MPEGTS[canal]
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    sess = criar_sessao()
    try:
        r = sess.get(target, headers=h, timeout=(5, 120), verify=False, stream=True)
        def gerar():
            try:
                for chunk in r.iter_content(16 * 1024):
                    if chunk:
                        yield chunk
            except Exception:
                pass
        return Response(gerar(), status=200, headers={
            'Content-Type': 'video/mp2t',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        })
    except Exception as e:
        return f"Erro: {e}", 500

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal:
        return "Faltam parametros", 400

    h = obter_headers(canal)
    sess = criar_sessao("firefox133")
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
