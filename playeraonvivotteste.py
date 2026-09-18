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

# ============================================
# CONFIGURAÇÃO — EDITE AQUI QUANDO MUDAR
# ============================================
LINK_CLOUDFLARE = "https://applying-terrorist-coding-sierra.trycloudflare.com"
# ============================================

MODO = "video" if os.path.exists("/data/data/com.termux") else "page"

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 300
TS_CACHE_TEMPO = 120

# ====== STREAM (Termux) ======
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

def buscar_m3u8(canal):
    url = montar_url(canal)
    h = obter_headers(canal)
    sess = criar_sessao()
    try:
        r = sess.get(url, headers=h, timeout=15, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            return r, url
    except Exception:
        pass
    return None, None

def buscar_segmento(url_seg, canal):
    with TS_CACHE_LOCK:
        item = TS_CACHE.get(url_seg)
        if item:
            dados, t = item
            if time.time() - t < TS_CACHE_TEMPO:
                return dados, 200

    h = obter_headers(canal)
    sess = criar_sessao()
    try:
        r = sess.get(url_seg, headers=h, timeout=20, verify=False)
        if r.status_code == 200:
            with TS_CACHE_LOCK:
                if len(TS_CACHE) >= TS_CACHE_MAX:
                    mais = min(TS_CACHE.items(), key=lambda kv: kv[1][1])
                    del TS_CACHE[mais[0]]
                TS_CACHE[url_seg] = (r.content, time.time())
            return r.content, 200
        return None, r.status_code
    except Exception:
        return None, 500

# ====== HTML ======
HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow-x: hidden; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: #06060a;
    color: #fff;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }

  /* ===== FUNDO ALHO NEO ===== */
  .bg-orbs {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
  }
  .orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(100px);
    opacity: 0.55;
    animation: flutuar 18s ease-in-out infinite;
  }
  .orb1 {
    width: 480px; height: 480px;
    background: radial-gradient(circle, #6c5ce7 0%, transparent 70%);
    top: -140px; left: -120px;
    animation-delay: 0s;
  }
  .orb2 {
    width: 420px; height: 420px;
    background: radial-gradient(circle, #a29bfe 0%, transparent 70%);
    bottom: -160px; right: -100px;
    animation-delay: -6s;
  }
  .orb3 {
    width: 380px; height: 380px;
    background: radial-gradient(circle, #00b894 0%, transparent 70%);
    top: 45%; left: 55%;
    opacity: 0.35;
    animation-delay: -12s;
  }
  @keyframes flutuar {
    0%, 100% { transform: translate(0, 0) scale(1); }
    33% { transform: translate(40px, -30px) scale(1.08); }
    66% { transform: translate(-30px, 30px) scale(0.95); }
  }

  /* ===== GRADE SUTIL ===== */
  .grid-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    background-image:
      linear-gradient(rgba(108, 92, 231, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(108, 92, 231, 0.06) 1px, transparent 1px);
    background-size: 60px 60px;
    mask-image: radial-gradient(ellipse at center, #000 20%, transparent 75%);
    -webkit-mask-image: radial-gradient(ellipse at center, #000 20%, transparent 75%);
  }

  /* ===== APP ===== */
  .app {
    width: 100%;
    max-width: 900px;
    position: relative;
    z-index: 1;
  }

  .brand {
    text-align: center;
    margin-bottom: 28px;
    animation: aparecer 0.8s ease-out;
  }
  .brand h1 {
    font-size: clamp(2.4em, 9vw, 4em);
    font-weight: 900;
    letter-spacing: 3px;
    background: linear-gradient(135deg, #ffffff 0%, #a29bfe 45%, #6c5ce7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 8px;
    text-shadow: 0 0 60px rgba(108, 92, 231, 0.5);
    filter: drop-shadow(0 0 30px rgba(108, 92, 231, 0.4));
  }
  .brand .sub {
    color: #a29bfe;
    font-size: 0.72em;
    letter-spacing: 6px;
    font-weight: 500;
    text-transform: uppercase;
    opacity: 0.9;
  }

  .player-card {
    background: rgba(15, 15, 25, 0.72);
    backdrop-filter: blur(24px) saturate(150%);
    -webkit-backdrop-filter: blur(24px) saturate(150%);
    border: 1px solid rgba(108, 92, 231, 0.25);
    border-radius: 24px;
    padding: 20px;
    box-shadow:
      0 30px 80px rgba(0, 0, 0, 0.7),
      0 0 120px rgba(108, 92, 231, 0.15),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
    animation: aparecer 1s ease-out 0.15s both;
    position: relative;
    overflow: hidden;
  }
  .player-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(162, 155, 254, 0.6), transparent);
  }

  .video-js {
    width: 100%;
    height: 440px;
    border-radius: 16px;
    overflow: hidden;
    background: #000;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
  }
  @media (max-width: 640px) { .video-js { height: 220px; } }

  .controls {
    display: flex;
    gap: 12px;
    margin-top: 18px;
    flex-wrap: wrap;
  }
  .controls input {
    flex: 1;
    min-width: 160px;
    background: rgba(10, 10, 18, 0.9);
    border: 1.5px solid rgba(108, 92, 231, 0.3);
    color: #fff;
    padding: 15px 18px;
    border-radius: 14px;
    font-family: 'Inter', sans-serif;
    font-size: 1em;
    font-weight: 500;
    outline: none;
    transition: all 0.25s ease;
    letter-spacing: 0.3px;
  }
  .controls input:focus {
    border-color: #6c5ce7;
    box-shadow: 0 0 0 4px rgba(108, 92, 231, 0.15), 0 0 30px rgba(108, 92, 231, 0.25);
    background: rgba(15, 15, 25, 0.95);
  }
  .controls input::placeholder { color: #555; font-weight: 400; }

  .controls button {
    background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
    color: #fff;
    border: none;
    padding: 15px 32px;
    border-radius: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1em;
    letter-spacing: 1px;
    cursor: pointer;
    transition: all 0.25s ease;
    box-shadow:
      0 10px 30px rgba(108, 92, 231, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
    display: flex;
    align-items: center;
    gap: 10px;
    position: relative;
    overflow: hidden;
  }
  .controls button::before {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent);
    transition: left 0.5s;
  }
  .controls button:hover::before { left: 100%; }
  .controls button:hover {
    transform: translateY(-3px);
    box-shadow:
      0 15px 40px rgba(108, 92, 231, 0.55),
      0 0 60px rgba(162, 155, 254, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }
  .controls button:active {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(108, 92, 231, 0.4);
  }
  .controls button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .footer {
    text-align: center;
    color: #444;
    font-size: 0.72em;
    letter-spacing: 2px;
    margin-top: 22px;
    font-weight: 500;
    animation: aparecer 1s ease-out 0.3s both;
  }

  @keyframes aparecer {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ===== CUSTOM VIDEO.JS ===== */
  .video-js .vjs-big-play-button {
    background: linear-gradient(135deg, rgba(108, 92, 231, 0.9), rgba(162, 155, 254, 0.9));
    border: none;
    width: 90px;
    height: 90px;
    line-height: 90px;
    border-radius: 50%;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 10px 40px rgba(108, 92, 231, 0.5);
    transition: all 0.3s ease;
  }
  .video-js .vjs-big-play-button:hover {
    transform: translate(-50%, -50%) scale(1.1);
    box-shadow: 0 15px 50px rgba(108, 92, 231, 0.7);
  }
  .video-js .vjs-control-bar {
    background: linear-gradient(to top, rgba(0,0,0,0.9), transparent);
    height: 50px;
  }
  .video-js .vjs-play-progress {
    background: linear-gradient(90deg, #6c5ce7, #a29bfe);
  }
  .video-js .vjs-load-progress {
    background: rgba(162, 155, 254, 0.2);
  }
</style>
</head>
<body>
  <div class="bg-orbs">
    <div class="orb orb1"></div>
    <div class="orb orb2"></div>
    <div class="orb orb3"></div>
  </div>
  <div class="grid-bg"></div>

  <div class="app">
    <div class="brand">
      <h1>MARCOS TV</h1>
      <div class="sub">Premium Streaming</div>
    </div>

    <div class="player-card">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>
      <div class="controls">
        <input id="canal" type="text" placeholder="Digite o nome do canal" autocomplete="off">
        <button id="btnPlay" onclick="tocar()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          PLAY
        </button>
      </div>
    </div>

    <div class="footer">© MARCOS TV</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player', {
  controls: true,
  autoplay: false,
  preload: 'auto',
  html5: { vhs: { overrideNative: true } }
});
var btn = document.getElementById('btnPlay');
var input = document.getElementById('canal');
var MODO = "{{ modo }}";
var LINK_CLOUDFLARE = "{{ link_cloudflare }}";

function fetchComTimeout(url, ms) {
  return new Promise((resolve, reject) => {
    var controller = new AbortController();
    var t = setTimeout(() => { controller.abort(); reject(new Error('timeout')); }, ms);
    fetch(url, { signal: controller.signal, mode: 'cors' })
      .then(r => { clearTimeout(t); resolve(r); })
      .catch(e => { clearTimeout(t); reject(e); });
  });
}

function tocar() {
  var canal = input.value.trim().toLowerCase();
  if (!canal) { input.focus(); return; }

  btn.disabled = true;
  var candidatos = [];

  if (MODO === 'page') {
    if (LINK_CLOUDFLARE) candidatos.push(LINK_CLOUDFLARE.replace(/\\/$/, ''));
    candidatos.push('');
  } else {
    candidatos.push('');
  }

  var respostas = 0;
  var ganhou = false;

  candidatos.forEach(function(base) {
    var urlTest = base + '/testar/' + encodeURIComponent(canal);
    fetchComTimeout(urlTest, 6000)
      .then(r => r.json())
      .then(d => {
        respostas++;
        if (ganhou) return;
        if (d && d.ok) {
          ganhou = true;
          btn.disabled = false;
          var src = base + '/play/' + encodeURIComponent(canal);
          player.src({ src: src, type: 'application/x-mpegURL' });
          player.play().catch(function(){});
        } else if (respostas === candidatos.length) {
          btn.disabled = false;
        }
      })
      .catch(() => {
        respostas++;
        if (!ganhou && respostas === candidatos.length) {
          btn.disabled = false;
        }
      });
  });
}

input.addEventListener('keydown', function(e) { if (e.key === 'Enter') tocar(); });
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
    return render_template_string(
        HTML,
        modo=MODO,
        link_cloudflare=LINK_CLOUDFLARE
    )

@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return jsonify({"ok": False})
    r, _ = buscar_m3u8(canal)
    return jsonify({"ok": bool(r)})

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
        'Cache-Control': 'public, max-age=60',
        'Accept-Ranges': 'bytes'
    })

if __name__ == '__main__':
    print("=" * 55)
    print(f"  MARCOS TV - MODO: {MODO.upper()}")
    print("=" * 55)
    if MODO == "video":
        print(f"  Rodando no Termux (porta {PORTA})")
        print(f"  Ative o tunel:")
        print(f"    cloudflared tunnel --url http://localhost:{PORTA}")
    else:
        print(f"  Rodando no Render (pagina HTML)")
        print(f"  Cloudflare: {LINK_CLOUDFLARE}")
    print("=" * 55)
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
