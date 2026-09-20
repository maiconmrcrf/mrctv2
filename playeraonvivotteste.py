import os, re, json, time, threading
import urllib3
from collections import OrderedDict
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

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

# ====== CACHE ULTRA-RÁPIDO ======
TS_CACHE = OrderedDict()
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 800
TS_CACHE_TEMPO = 120

# ====== CANAIS FIXOS ======
CANAIS_FIXOS = [
    "espn",
    "premiereclubes",
    "tnt",
    "telecinepipoca",
    "telecinefun",
    "telecinepremium",
    "space",
]

# ====== POOL DE CONEXÕES PERSISTENTES ======
_SESSAO_GLOBAL = None
_SESSAO_LOCK = threading.Lock()

def get_sessao_persistente():
    global _SESSAO_GLOBAL
    with _SESSAO_LOCK:
        if _SESSAO_GLOBAL is None:
            if USE_CURL:
                try:
                    _SESSAO_GLOBAL = ImpersonateSession.Session(impersonate="firefox133")
                except Exception:
                    _SESSAO_GLOBAL = ImpersonateSession.Session()
            else:
                _SESSAO_GLOBAL = ImpersonateSession.Session()
                adapter = ImpersonateSession.adapters.HTTPAdapter(
                    pool_connections=100, 
                    pool_maxsize=200, 
                    max_retries=2
                )
                _SESSAO_GLOBAL.mount('https://', adapter)
                _SESSAO_GLOBAL.mount('http://', adapter)
        return _SESSAO_GLOBAL

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
    sess = get_sessao_persistente()
    try:
        r = sess.get(url, headers=h, timeout=8, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            return r, url
    except Exception:
        pass
    return None, None

def buscar_segmento(url_segmento, canal):
    agora = time.time()

    with TS_CACHE_LOCK:
        if url_segmento in TS_CACHE:
            dados, t = TS_CACHE[url_segmento]
            if agora - t < TS_CACHE_TEMPO:
                TS_CACHE.move_to_end(url_segmento)
                return dados, 200
            else:
                del TS_CACHE[url_segmento]

    h = obter_headers(canal)
    sess = get_sessao_persistente()
    
    for _ in range(2):
        try:
            r = sess.get(url_segmento, headers=h, timeout=6, verify=False)
            if r.status_code == 200:
                with TS_CACHE_LOCK:
                    if len(TS_CACHE) >= TS_CACHE_MAX:
                        TS_CACHE.popitem(last=False)
                    TS_CACHE[url_segmento] = (r.content, agora)
                return r.content, 200
            if r.status_code in (403, 404):
                return None, r.status_code
        except Exception:
            pass

    return None, 502

# ============ HTML / FRONTEND ============
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
    padding: 16px;
  }
  .app { width: 100%; max-width: 900px; }
  .brand { text-align: center; margin-bottom: 20px; }
  .brand h1 {
    font-size: clamp(2em, 7vw, 3.2em);
    font-weight: 900;
    letter-spacing: 2px;
    background: linear-gradient(135deg, #ffffff 0%, #a29bfe 50%, #6c5ce7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 4px;
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
    padding: 16px;
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6);
  }
  
  .video-js {
    width: 100%;
    height: 420px;
    border-radius: 14px;
    overflow: hidden;
    background: #000;
  }

  /* FIT MODES PARA O VÍDEO */
  .fit-contain video, .fit-contain .vjs-tech { object-fit: contain !important; }
  .fit-cover video, .fit-cover .vjs-tech { object-fit: cover !important; }
  .fit-fill video, .fit-fill .vjs-tech { object-fit: fill !important; }

  /* ESTILIZAÇÃO DO BOTÃO DE TAMANHO NA BARRA DO PLAYER */
  .vjs-fit-btn {
    font-family: 'Inter', sans-serif !important;
    font-size: 11px !important;
    font-weight: 800 !important;
    color: #a29bfe !important;
    cursor: pointer;
    display: flex !important;
    align-items: center;
    justify-content: center;
    padding: 0 8px !important;
    width: auto !important;
  }
  .vjs-fit-btn:hover { color: #fff !important; }

  .video-js.vjs-fullscreen,
  .video-js:-webkit-full-screen,
  .video-js:-moz-full-screen,
  .video-js:-ms-fullscreen {
    width: 100% !important;
    height: 100% !important;
    border-radius: 0 !important;
  }
  @media (max-width: 640px) { .video-js { height: 230px; } }

  .controls { display: flex; gap: 10px; margin-top: 14px; }
  .controls input {
    flex: 1;
    background: rgba(13, 13, 20, 0.9);
    border: 1.5px solid rgba(108, 92, 231, 0.3);
    color: #fff;
    padding: 14px 16px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 1em;
    font-weight: 500;
    outline: none;
  }
  .controls input:focus { border-color: #6c5ce7; }
  
  .btn-play {
    background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
    color: #fff;
    border: none;
    padding: 14px 24px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 0.9em;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 8px 20px rgba(108, 92, 231, 0.35);
  }

  .canais-fixos {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 8px;
    margin-bottom: 14px;
  }
  .canal-btn {
    background: rgba(20, 20, 31, 0.7);
    border: 1.5px solid rgba(108, 92, 231, 0.4);
    color: #a29bfe;
    padding: 12px 6px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 0.78em;
    letter-spacing: 1px;
    text-transform: uppercase;
    cursor: pointer;
    text-align: center;
    transition: all 0.2s;
  }
  .canal-btn:hover {
    background: rgba(108, 92, 231, 0.2);
    color: #fff;
    border-color: #a29bfe;
  }
  .canal-btn.ativo {
    background: linear-gradient(135deg, rgba(108, 92, 231, 0.4), rgba(162, 155, 254, 0.4));
    border-color: #a29bfe;
    color: #fff;
    box-shadow: 0 0 20px rgba(108, 92, 231, 0.5);
  }

  .status {
    text-align: center;
    margin-top: 12px;
    font-size: 0.85em;
    color: #888;
    min-height: 20px;
    font-weight: 500;
  }
  .status.ok { color: #00b894; }
  .status.err { color: #e74c3c; }
  .footer { text-align: center; color: #444; font-size: 0.75em; margin-top: 20px; }
</style>
</head>
<body>
  <div class="app">
    <div class="brand">
      <h1>MARCOS TV</h1>
      <div class="sub">STREAMING</div>
    </div>

    <div class="player-card">
      <video id="player" class="video-js fit-contain" controls playsinline preload="auto"></video>

      <div class="canais-fixos" style="margin-top: 14px;">
        {% for c in canais %}
        <div class="canal-btn" data-canal="{{ c }}" onclick="tocarFixo('{{ c }}', this)">{{ c }}</div>
        {% endfor %}
      </div>

      <div class="controls">
        <input id="canal" type="text" placeholder="Nome do canal..." autocomplete="off">
        <button id="btnPlay" class="btn-play" onclick="tocar()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          PLAY
        </button>
      </div>

      <div class="status" id="status"></div>
    </div>

    <div class="footer">© MARCOS TV</div>
  </div>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
// CONFIGURAÇÃO DO PLAYER E BUFFER ANTI-TRAVAMENTO
var player = videojs('player', {
  controls: true,
  autoplay: false,
  preload: 'auto',
  liveui: true,
  html5: {
    vhs: {
      overrideNative: true,
      maxBufferLength: 40,
      maxMaxBufferLength: 80,
      liveSyncDuration: 8,
      liveMaxLatencyDuration: 25,
      enableLowInitialPlaylist: true,
      smoothQualityChange: true,
      fastQualityChange: true,
      handlePartialData: true
    }
  }
});

var statusEl = document.getElementById('status');
var btn = document.getElementById('btnPlay');
var input = document.getElementById('canal');

// MODOS DE ENQUADRAMENTO DA TELA
var modostela = ['fit-contain', 'fit-cover', 'fit-fill'];
var rótulosModos = ['[ 16:9 ]', '[ CROP ]', '[ FULL ]'];
var nomesModos = ['PROPORCIONAL', 'PREENCHER', 'ESTICAR'];
var modoAtualIdx = 0;

// CRIA O BOTÃO DE TAMANHO DENTRO DA BARRA DO PLAYER (AO LADO DO BOTÃO [  ] DE TELA CHEIA)
var Button = videojs.getComponent('Button');
var FitButton = videojs.extend(Button, {
  constructor: function() {
    Button.apply(this, arguments);
    this.controlText('Tamanho da Tela');
  },
  buildCSSClass: function() {
    return 'vjs-control vjs-button vjs-fit-btn';
  },
  handleClick: function() {
    var el = player.el();
    el.classList.remove(modostela[modoAtualIdx]);
    modoAtualIdx = (modoAtualIdx + 1) % modostela.length;
    el.classList.add(modostela[modoAtualIdx]);
    this.el().innerText = rótulosModos[modoAtualIdx];
    setStatus('Tamanho: ' + nomesModos[modoAtualIdx], 'ok');
  }
});
videojs.registerComponent('FitButton', FitButton);

player.ready(function() {
  var controlBar = player.getChild('controlBar');
  var fullscreenIdx = controlBar.children().findIndex(c => c.name() === 'FullscreenToggle');
  var btnInstance = controlBar.addChild('FitButton', {}, fullscreenIdx !== -1 ? fullscreenIdx : undefined);
  if (btnInstance && btnInstance.el()) {
    btnInstance.el().innerText = rótulosModos[0];
  }
});

// APENAS QUANDO CLICAR NO BOTÃO DE TELA CHEIA DO PLAYER -> GIRA PARA HORIZONTAL
player.on('fullscreenchange', function() {
  if (player.isFullscreen()) {
    try {
      if (screen.orientation && screen.orientation.lock) {
        screen.orientation.lock('landscape').catch(function(){});
      } else if (screen.lockOrientation) {
        screen.lockOrientation('landscape');
      }
    } catch(e) {}
  } else {
    try {
      if (screen.orientation && screen.orientation.unlock) {
        screen.orientation.unlock().catch(function(){});
      } else if (screen.unlockOrientation) {
        screen.unlockOrientation();
      }
    } catch(e) {}
  }
});

function setStatus(msg, tipo) {
  statusEl.className = 'status' + (tipo ? ' ' + tipo : '');
  statusEl.innerText = msg || '';
}

function marcarAtivo(el) {
  document.querySelectorAll('.canal-btn').forEach(function(b){ b.classList.remove('ativo'); });
  if (el) el.classList.add('ativo');
}

function tocarFixo(canal, el) {
  marcarAtivo(el);
  input.value = canal;
  tocar();
}

function tocar() {
  var canal = input.value.trim().toLowerCase();
  if (!canal) {
    setStatus('Digite o nome do canal', 'err');
    input.focus();
    return;
  }
  setStatus('Carregando ' + canal + '...');
  btn.disabled = true;

  fetch('/testar/' + encodeURIComponent(canal))
    .then(r => r.json())
    .then(d => {
      btn.disabled = false;
      if (d.ok) {
        setStatus('Tocando: ' + canal, 'ok');
        
        // TROCA O CANAL SEM RECARREGAR A PÁGINA
        player.pause();
        player.error(null);
        player.src({ src: '/play/' + encodeURIComponent(canal) + '?t=' + Date.now(), type: 'application/x-mpegURL' });
        player.load();
        player.play().catch(function(e){ setStatus('Erro ao reproduzir: ' + e.message, 'err'); });
      } else {
        setStatus(d.msg || 'Canal indisponivel', 'err');
      }
    })
    .catch(e => {
      btn.disabled = false;
      setStatus('Erro de conexao: ' + e.message, 'err');
    });
}

input.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') tocar();
});
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
    return render_template_string(HTML_PAGINA, canais=CANAIS_FIXOS)

@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return {"ok": False, "msg": "Nome invalido"}
    r, _ = buscar_m3u8(canal)
    if r:
        return {"ok": True}
    return {"ok": False, "msg": "Canal '" + canal + "' indisponivel"}

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

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal:
        return "Faltam parametros", 400

    h = obter_headers(canal)
    sess = get_sessao_persistente()
    try:
        r = sess.get(target, headers=h, timeout=8, verify=False)
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
        'Cache-Control': 'public, max-age=120',
        'Accept-Ranges': 'bytes',
        'Access-Control-Allow-Origin': '*'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
