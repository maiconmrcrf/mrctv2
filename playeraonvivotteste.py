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

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

# ====== CACHE DE STREAM (guarda o m3u8 resolvido por 10s) ======
STREAM_CACHE = {}       # canal -> (resp_texto, url_base, ts)
STREAM_LOCK = threading.Lock()
STREAM_TEMPO = 10       # 10s (m3u8 muda toda hora, não adianta guardar muito)

# ====== CACHE DE SEGMENTOS (.ts) ======
TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 800
TS_CACHE_TEMPO = 300    # 5 min

# ====== SESSÃO ======
def criar_sessao():
    if USE_CURL:
        try:
            return ImpersonateSession.Session(impersonate="firefox133")
        except Exception:
            pass
    return ImpersonateSession.Session()

def montar_url(canal):
    canal = canal.strip().lower()
    return f"https://f8umt2oop68t.sbs/live/secure/pHGsJJgoEUBc-K5ACe7Hws--gF0WDhHii_3tGSGwoq4/1789760848/1d256d1fe0127694/{canal}/index.m3u8"

def obter_headers(canal):
    canal = canal.strip().lower()
    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Origin": ORIGIN_FIXO,
        "Referer": f"{ORIGIN_FIXO}/play/{canal}.html",
        "Cookie": COOKIE_FIXO,
        "Connection": "keep-alive",
    }

# ====== BUSCA M3U8 COM CACHE CURTO ======
def buscar_m3u8(canal, forcar=False):
    canal_l = canal.strip().lower()

    if not forcar:
        with STREAM_LOCK:
            item = STREAM_CACHE.get(canal_l)
            if item:
                texto, url_base, ts = item
                if time.time() - ts < STREAM_TEMPO:
                    return texto, url_base

    url = montar_url(canal)
    h = obter_headers(canal)
    sess = criar_sessao()
    try:
        r = sess.get(url, headers=h, timeout=15, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            base = getattr(r, 'url', url)
            with STREAM_LOCK:
                STREAM_CACHE[canal_l] = (r.text, str(base), time.time())
            return r.text, str(base)
    except Exception:
        pass
    return None, None

# ====== BUSCA SEGMENTO COM RETRY ======
def buscar_segmento(url_seg, canal):
    # 1) cache
    with TS_CACHE_LOCK:
        item = TS_CACHE.get(url_seg)
        if item:
            dados, t = item
            if time.time() - t < TS_CACHE_TEMPO:
                return dados, 200

    # 2) baixa com 3 tentativas
    h = obter_headers(canal)
    for tent in range(3):
        sess = criar_sessao()
        try:
            r = sess.get(url_seg, headers=h, timeout=25, verify=False)
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
            time.sleep(0.4)

    return None, 502

# ====== HTML ======
HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: #03060f;
    color: #fff;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    position: relative;
    overflow-x: hidden;
  }

  /* ===== FUNDO AZUL NEON ===== */
  .bg-glow {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
  }
  .glow {
    position: absolute;
    border-radius: 50%;
    filter: blur(120px);
    animation: pulsar 8s ease-in-out infinite;
  }
  .glow1 {
    width: 600px; height: 600px;
    background: radial-gradient(circle, #00a8ff 0%, transparent 70%);
    top: -200px; left: -180px;
    opacity: 0.5;
  }
  .glow2 {
    width: 520px; height: 520px;
    background: radial-gradient(circle, #0066ff 0%, transparent 70%);
    bottom: -180px; right: -160px;
    opacity: 0.45;
    animation-delay: -4s;
  }
  @keyframes pulsar {
    0%, 100% { transform: scale(1); opacity: 0.45; }
    50% { transform: scale(1.15); opacity: 0.65; }
  }
  .grid-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    background-image:
      linear-gradient(rgba(0, 168, 255, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0, 168, 255, 0.06) 1px, transparent 1px);
    background-size: 50px 50px;
    mask-image: radial-gradient(ellipse at center, #000 10%, transparent 70%);
    -webkit-mask-image: radial-gradient(ellipse at center, #000 10%, transparent 70%);
  }

  .app {
    width: 100%;
    max-width: 960px;
    position: relative;
    z-index: 1;
  }

  /* ===== HEADER ===== */
  .header {
    text-align: center;
    margin-bottom: 30px;
  }
  .header h1 {
    font-size: clamp(2.4em, 9vw, 4em);
    font-weight: 900;
    letter-spacing: 4px;
    color: #fff;
    margin-bottom: 8px;
    text-shadow:
      0 0 20px rgba(0, 168, 255, 0.7),
      0 0 60px rgba(0, 168, 255, 0.4);
  }
  .header .sub {
    color: #00a8ff;
    font-size: 0.72em;
    letter-spacing: 6px;
    font-weight: 600;
    text-transform: uppercase;
    text-shadow: 0 0 20px rgba(0, 168, 255, 0.5);
  }
  .header .divider {
    width: 80px;
    height: 2px;
    background: linear-gradient(90deg, transparent, #00a8ff, transparent);
    margin: 18px auto 0;
    border-radius: 2px;
    box-shadow: 0 0 20px rgba(0, 168, 255, 0.8);
  }

  /* ===== PLAYER ===== */
  .player-wrap {
    background: #080c18;
    border: 1px solid rgba(0, 168, 255, 0.25);
    border-radius: 18px;
    padding: 14px;
    margin-bottom: 20px;
    box-shadow:
      0 25px 70px rgba(0, 0, 0, 0.9),
      0 0 60px rgba(0, 168, 255, 0.15),
      inset 0 1px 0 rgba(0, 168, 255, 0.1);
  }
  .video-js {
    width: 100%;
    height: 480px;
    border-radius: 10px;
    overflow: hidden;
    background: #000;
  }
  @media (max-width: 640px) { .video-js { height: 240px; } }

  /* ===== CONTROLES ===== */
  .controls {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .controls input {
    flex: 1;
    min-width: 180px;
    background: #080c18;
    border: 1.5px solid rgba(0, 168, 255, 0.3);
    color: #fff;
    padding: 16px 18px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 1em;
    font-weight: 500;
    outline: none;
    transition: all 0.25s ease;
    letter-spacing: 0.3px;
  }
  .controls input:focus {
    border-color: #00a8ff;
    box-shadow:
      0 0 0 3px rgba(0, 168, 255, 0.15),
      0 0 30px rgba(0, 168, 255, 0.3);
  }
  .controls input::placeholder { color: #4a5570; font-weight: 400; }

  .controls button {
    background: linear-gradient(135deg, #00a8ff 0%, #0066ff 100%);
    color: #fff;
    border: none;
    padding: 16px 36px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1em;
    letter-spacing: 1.5px;
    cursor: pointer;
    transition: all 0.25s ease;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow:
      0 10px 30px rgba(0, 168, 255, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.25);
  }
  .controls button:hover {
    transform: translateY(-2px);
    box-shadow:
      0 15px 45px rgba(0, 168, 255, 0.6),
      0 0 60px rgba(0, 168, 255, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }
  .controls button:active { transform: translateY(0); }
  .controls button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  /* ===== FOOTER ===== */
  .footer {
    text-align: center;
    color: #2a3555;
    font-size: 0.7em;
    letter-spacing: 2px;
    margin-top: 24px;
    font-weight: 500;
  }

  /* ===== VIDEO.JS AZUL ===== */
  .video-js .vjs-big-play-button {
    background: linear-gradient(135deg, rgba(0, 168, 255, 0.95), rgba(0, 102, 255, 0.95));
    border: none;
    width: 80px;
    height: 80px;
    line-height: 80px;
    border-radius: 50%;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    transition: transform 0.25s ease;
    box-shadow: 0 10px 40px rgba(0, 168, 255, 0.6);
  }
  .video-js .vjs-big-play-button:hover {
    transform: translate(-50%, -50%) scale(1.08);
    box-shadow: 0 15px 55px rgba(0, 168, 255, 0.9);
  }
  .video-js .vjs-control-bar {
    background: linear-gradient(to top, rgba(3, 6, 15, 0.95), transparent);
    height: 46px;
  }
  .video-js .vjs-play-progress {
    background: linear-gradient(90deg, #00a8ff, #0066ff);
  }
  .video-js .vjs-load-progress {
    background: rgba(0, 168, 255, 0.25);
  }
  .video-js .vjs-slider {
    background: rgba(0, 168, 255, 0.15);
  }
  .video-js .vjs-volume-level {
    background: #00a8ff;
  }
</style>
</head>
<body>
  <div class="bg-glow">
    <div class="glow glow1"></div>
    <div class="glow glow2"></div>
  </div>
  <div class="grid-bg"></div>

  <div class="app">
    <div class="header">
      <h1>MARCOS TV</h1>
      <div class="sub">Premium Streaming</div>
      <div class="divider"></div>
    </div>

    <div class="player-wrap">
      <video id="player" class="video-js" controls playsinline preload="none"></video>
    </div>

    <div class="controls">
      <input id="canal" type="text" placeholder="Digite o nome do canal" autocomplete="off" spellcheck="false">
      <button id="btnPlay" onclick="tocar()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        PLAY
      </button>
    </div>

    <div class="footer">© MARCOS TV</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player', {
  controls: true,
  autoplay: false,
  preload: 'none',
  html5: { vhs: { overrideNative: true } }
});
var btn = document.getElementById('btnPlay');
var input = document.getElementById('canal');

// Reconexão automática: se o player travar, tenta de novo
player.on('error', function() {
  setTimeout(function() {
    if (player.src() && player.src().indexOf('/play/') !== -1) {
      var v = player.currentTime();
      player.load();
      if (v > 0) player.currentTime(v);
      player.play().catch(function(){});
    }
  }, 1500);
});

function tocar() {
  var canal = input.value.trim().toLowerCase();
  if (!canal) { input.focus(); return; }
  btn.disabled = true;

  var t = setTimeout(function(){ btn.disabled = false; }, 10000);

  fetch('/testar/' + encodeURIComponent(canal), { mode: 'cors' })
    .then(r => r.json())
    .then(d => {
      clearTimeout(t);
      btn.disabled = false;
      if (d && d.ok) {
        player.src({ src: '/play/' + encodeURIComponent(canal), type: 'application/x-mpegURL' });
        player.play().catch(function(){});
      }
    })
    .catch(function() {
      clearTimeout(t);
      btn.disabled = false;
    });
}

input.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') tocar();
});
</script>
</body>
</html>
'''

# ====== ROTAS ======
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    r.headers['Access-Control-Allow-Methods'] = '*'
    return r

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return jsonify({"ok": False})
    texto, _ = buscar_m3u8(canal)
    return jsonify({"ok": bool(texto)})

@app.route('/play/<canal>')
def play(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return "Nome invalido", 400

    texto, base = buscar_m3u8(canal)
    if not texto:
        return "Canal nao encontrado", 404

    linhas = []
    for l in texto.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{ep}?url={quote(abs_url, safe='')}&canal={canal}")
        else:
            linhas.append(ls)

    return Response("\n".join(linhas), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Cache-Control': 'no-cache'
    })

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal:
        return "Faltam parametros", 400

    h = obter_headers(canal)
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
        'Cache-Control': 'public, max-age=300',
        'Accept-Ranges': 'bytes'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
