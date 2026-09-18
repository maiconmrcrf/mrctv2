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

# ====== DETECTA MODO ======
# Se for Termux (existe /data/data/com.termux) → modo vídeo
# Senão → modo página (Render)
MODO = "video" if os.path.exists("/data/data/com.termux") else "page"

# ====== CONFIG ======
USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

LINKS_PADRAO = {
    "serveo": "https://tvmrc1.serveousercontent.com",
    "cloudflare": ""
}

ARQ_CONFIG = "config_links.json"

TS_CACHE = {}
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 300
TS_CACHE_TEMPO = 120

# ====== CONFIG DE LINKS (só no Render) ======
def carregar_links():
    if not os.path.exists(ARQ_CONFIG):
        return dict(LINKS_PADRAO)
    try:
        with open(ARQ_CONFIG, "r", encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("serveo", LINKS_PADRAO["serveo"])
        d.setdefault("cloudflare", "")
        return d
    except Exception:
        return dict(LINKS_PADRAO)

def salvar_links(d):
    try:
        with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

# ====== STREAM (só no Termux) ======
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: radial-gradient(ellipse at top, #1a1a2e 0%, #0a0a0f 60%);
    color: #fff; min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    padding: 20px;
  }
  .app { width: 100%; max-width: 900px; }
  .brand { text-align: center; margin-bottom: 26px; }
  .brand h1 {
    font-size: clamp(2.2em, 8vw, 3.5em);
    font-weight: 900; letter-spacing: 2px;
    background: linear-gradient(135deg, #ffffff 0%, #a29bfe 50%, #6c5ce7 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin-bottom: 6px;
    text-shadow: 0 0 40px rgba(108, 92, 231, 0.3);
  }
  .brand .sub {
    color: #6c5ce7; font-size: 0.75em; letter-spacing: 4px;
    font-weight: 600; text-transform: uppercase; opacity: 0.85;
  }
  .player-card {
    background: rgba(20, 20, 31, 0.85);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(108, 92, 231, 0.25);
    border-radius: 20px; padding: 18px;
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6), 0 0 80px rgba(108, 92, 231, 0.1);
    margin-bottom: 18px;
  }
  .video-js { width: 100%; height: 420px; border-radius: 14px; overflow: hidden; background: #000; }
  @media (max-width: 640px) { .video-js { height: 220px; } }
  .controls { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
  .controls input {
    flex: 1; min-width: 160px;
    background: rgba(13, 13, 20, 0.9);
    border: 1.5px solid rgba(108, 92, 231, 0.3);
    color: #fff; padding: 14px 16px; border-radius: 12px;
    font-family: 'Inter', sans-serif; font-size: 1em; font-weight: 500;
    outline: none; transition: all 0.2s;
  }
  .controls input:focus {
    border-color: #6c5ce7;
    box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.15);
  }
  .controls input::placeholder { color: #555; }
  .controls button {
    background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
    color: #fff; border: none; padding: 14px 28px; border-radius: 12px;
    font-family: 'Inter', sans-serif; font-weight: 700; font-size: 1em;
    letter-spacing: 0.5px; cursor: pointer; transition: all 0.2s;
    box-shadow: 0 8px 20px rgba(108, 92, 231, 0.35);
    display: flex; align-items: center; gap: 8px;
  }
  .controls button:hover { transform: translateY(-2px); box-shadow: 0 12px 28px rgba(108, 92, 231, 0.5); }
  .controls button:active { transform: translateY(0); }
  .controls button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
  .status {
    text-align: center; margin-top: 14px; font-size: 0.85em;
    color: #888; min-height: 20px; font-weight: 500;
  }
  .status.ok { color: #00b894; }
  .status.err { color: #e74c3c; }
  .footer {
    text-align: center; color: #444; font-size: 0.72em;
    letter-spacing: 1px; margin-top: 18px;
  }
  .admin-toggle {
    position: fixed; bottom: 14px; right: 14px;
    background: rgba(108, 92, 231, 0.15);
    border: 1px solid rgba(108, 92, 231, 0.3);
    color: #a29bfe; padding: 8px 14px; border-radius: 10px;
    font-size: 0.8em; cursor: pointer; font-family: 'Inter', sans-serif;
    font-weight: 600; backdrop-filter: blur(10px);
  }
  .admin-toggle:hover { background: rgba(108, 92, 231, 0.3); }
  .admin-modal {
    display: none; position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.8); z-index: 9999;
    align-items: center; justify-content: center; padding: 20px;
  }
  .admin-modal.open { display: flex; }
  .admin-box {
    background: #14141f; border: 1px solid rgba(108, 92, 231, 0.3);
    border-radius: 16px; padding: 24px; width: 100%; max-width: 500px;
  }
  .admin-box h2 { font-size: 1.1em; margin-bottom: 16px; color: #a29bfe; }
  .admin-box label { display: block; font-size: 0.8em; color: #888; margin-bottom: 6px; margin-top: 12px; }
  .admin-box input {
    width: 100%; background: #0d0d14; border: 1.5px solid rgba(108, 92, 231, 0.3);
    color: #fff; padding: 12px 14px; border-radius: 10px;
    font-family: monospace; font-size: 0.85em; outline: none;
  }
  .admin-box input:focus { border-color: #6c5ce7; }
  .admin-box .row { display: flex; gap: 8px; margin-top: 18px; }
  .admin-box button {
    flex: 1; padding: 12px; border-radius: 10px; border: none;
    font-weight: 700; cursor: pointer; font-family: 'Inter', sans-serif;
  }
  .admin-box .save { background: #00b894; color: #fff; }
  .admin-box .close { background: #333; color: #fff; }
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
      <div class="controls">
        <input id="canal" type="text" placeholder="Nome do canal (ex: discoveryturbo)" autocomplete="off">
        <button id="btnPlay" onclick="tocar()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          PLAY
        </button>
      </div>
      <div class="status" id="status"></div>
    </div>

    <div class="footer">© MARCOS TV</div>
  </div>

  <div class="admin-toggle" onclick="abrirAdmin()">⚙</div>

  <div class="admin-modal" id="adminModal">
    <div class="admin-box">
      <h2>Configurar Links</h2>
      <label>Link Serveo (fixo)</label>
      <input id="linkServeo" type="text" value="">
      <label>Link Cloudflare (atualize quando mudar)</label>
      <input id="linkCloudflare" type="text" placeholder="https://xxx.trycloudflare.com">
      <div class="row">
        <button class="save" onclick="salvarAdmin()">SALVAR</button>
        <button class="close" onclick="fecharAdmin()">FECHAR</button>
      </div>
    </div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player = videojs('player', { controls: true, autoplay: false, preload: 'auto' });
var statusEl = document.getElementById('status');
var btn = document.getElementById('btnPlay');
var input = document.getElementById('canal');
var MODO = "{{ modo }}";

function setStatus(msg, tipo) {
  statusEl.className = 'status' + (tipo ? ' ' + tipo : '');
  statusEl.innerText = msg || '';
}

function abrirAdmin() {
  if (MODO === 'video') {
    alert('Voce esta rodando no Termux. Edite os links no Render.');
    return;
  }
  fetch('/links').then(r => r.json()).then(d => {
    document.getElementById('linkServeo').value = d.serveo || '';
    document.getElementById('linkCloudflare').value = d.cloudflare || '';
    document.getElementById('adminModal').classList.add('open');
  });
}

function fecharAdmin() {
  document.getElementById('adminModal').classList.remove('open');
}

function salvarAdmin() {
  var serveo = document.getElementById('linkServeo').value.trim();
  var cf = document.getElementById('linkCloudflare').value.trim();
  fetch('/links', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ serveo: serveo, cloudflare: cf })
  }).then(r => r.json()).then(d => {
    if (d.ok) { alert('Salvo!'); fecharAdmin(); }
    else { alert('Erro: ' + (d.msg || '')); }
  });
}

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
  if (!canal) { setStatus('Digite o nome do canal', 'err'); input.focus(); return; }

  setStatus('Conectando...');
  btn.disabled = true;

  var candidatos = [];

  if (MODO === 'page') {
    // Render: busca links configurados
    fetch('/links').then(r => r.json()).then(links => {
      if (links.serveo) candidatos.push(links.serveo.replace(/\\/$/, ''));
      if (links.cloudflare) candidatos.push(links.cloudflare.replace(/\\/$/, ''));
      dispararTestes(canal, candidatos);
    }).catch(e => { btn.disabled = false; setStatus('Erro: ' + e.message, 'err'); });
  } else {
    // Termux: usa local direto
    candidatos.push('');
    dispararTestes(canal, candidatos);
  }
}

function dispararTestes(canal, candidatos) {
  if (!candidatos.length) {
    btn.disabled = false;
    setStatus('Nenhum link configurado', 'err');
    return;
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
          var viaTxt = base ? base.replace(/^https?:\\/\\//, '').split('/')[0] : 'local';
          setStatus('Tocando via ' + viaTxt, 'ok');
          var src = base + '/play/' + encodeURIComponent(canal);
          player.src({ src: src, type: 'application/x-mpegURL' });
          player.play().catch(function(e){ setStatus('Erro: ' + e.message, 'err'); });
        } else if (respostas === candidatos.length) {
          btn.disabled = false;
          setStatus('Canal indisponivel', 'err');
        }
      })
      .catch(() => {
        respostas++;
        if (!ganhou && respostas === candidatos.length) {
          btn.disabled = false;
          setStatus('Nenhum link respondeu', 'err');
        }
      });
  });
}

input.addEventListener('keydown', function(e) { if (e.key === 'Enter') tocar(); });
</script>
</body>
</html>
'''

# ====== ROTAS COMUNS ======
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    r.headers['Access-Control-Allow-Methods'] = '*'
    return r

@app.route('/')
def index():
    return render_template_string(HTML, modo=MODO)

# ====== ROTAS MODO PÁGINA (Render) ======
@app.route('/links', methods=['GET'])
def get_links():
    return jsonify(carregar_links())

@app.route('/links', methods=['POST'])
def post_links():
    d = request.get_json() or {}
    links = {
        "serveo": (d.get('serveo') or '').strip().rstrip('/'),
        "cloudflare": (d.get('cloudflare') or '').strip().rstrip('/')
    }
    if not links['serveo']:
        links['serveo'] = LINKS_PADRAO['serveo']
    if salvar_links(links):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Erro ao salvar"}), 500

# ====== ROTAS MODO VÍDEO (Termux) ======
@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return jsonify({"ok": False, "msg": "Nome invalido"})
    r, _ = buscar_m3u8(canal)
    if r:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Canal indisponivel"})

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

# ====== BOOT ======
if __name__ == '__main__':
    print("=" * 55)
    print(f"  MARCOS TV - MODO: {MODO.upper()}")
    print("=" * 55)
    if MODO == "video":
        print(f"  Rodando no Termux (porta {PORTA})")
        print(f"  Ative o tunel em outro terminal:")
        print(f"    ssh -R tvmrc1:80:127.0.0.1:{PORTA} serveo.net")
    else:
        print(f"  Rodando no Render (pagina HTML)")
    print("=" * 55)
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
