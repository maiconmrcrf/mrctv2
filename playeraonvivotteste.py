import os, re, json, time, threading, subprocess, socket
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
PORTA = 9999
BASE_URL = "https://tvmrc1.serveousercontent.com"

PASTA_PERFIS = os.path.expanduser("./canais_dados")
os.makedirs(PASTA_PERFIS, exist_ok=True)

PROXIES = ["chrome120", "chrome110", "safari_15_5"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

EMBEDS_DOMINIOS = [
    "https://ww5.embedtv.lat",
    "https://2608.cdnembedcanais.xyz",
    "https://w1.rdse.buzz"
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
    "premiere": ["premiere", "premiere1"]
}

CANAIS_DISPONIVEIS = [
    "cazetv","cazetv2","cazetv3","cazetv4","cazetv5","cazetv6","combate","dazn",
    "disneyplus","disneyplus02","disneyplus03","disneyplus04","disneyplus05","disneyplus06","disneyplus07","disneyplus08","disneyplus09",
    "espn","espn2","espn3","espn4","espn5","espn6","getv",
    "max","max1","max2","max3","max02","max03","max04","max05","max06",
    "nsports","nossofutebol",
    "paramount","paramount02","paramount03","paramount04","paramount05","paramount06","paramount07","paramountnetwork",
    "premiere","premiere2","premiere3","premiere4","premiere5","premiere6","premiere7","premiere8",
    "primevideo1","primevideo2",
    "sportv","sportv2","sportv3","sportv4","sportynet","sportynet1","sportynet2","sportynet3",
    "ufcfightpass","xsports","band_sports","canalgoat","off",
    "24h_chaves","24h_dragonballz","24h_naruto","24h_simpsons","24h_todomundoodiaocris",
    "cartoonnetwork","cartoonito","discoverykids","dreamworks","gloob","gloobinho","nickjr","nickelodeon","tooncast","tvratimbum",
    "animalplanet","discoverychannel","discoveryhh","discoveryid","discoveryscience","discoverytheater","discoveryturbo","discoveryworld",
    "fishtv","history","history2","ae","amc","amcseries","axn","adultswim","cinemax","comedycentral",
    "gnt","hbo","hbo2","hbofamily","hbomundi","hboplus","hbopop","hbosignature","hboxtreme",
    "hgtv","megapix","sony","space","starchannel","studiouniversal",
    "tcm","tlc","tnt","tntnovelas","tntseries",
    "telecineaction","telecinecult","telecinefun","telecinepipoca","telecinepremium","telecinetouch",
    "universal","usa","warner","warnerchannel",
    "bandnews","bandrj","bandsp","cnnbrasil","globonews",
    "recordmg","recordrj","recordsp","recorddf","recordesp",
    "sbtrj","sbtsp","redetv","aparecida","cancaonova","cultura",
    "globoam","globoce","globoes","globomg","globopb","globope","globorj","globors","globosp","globodf","globoesp",
    "mtv","multishow","foodnetwork","masterchef","playboy","sexyhot",
    "amazonprime","amazonprime02","amazonprime03","amazonprime04","amazonprime05",
    "appletv01","appletv02","appletv03","appletv04","appletv05","appletv06",
    "pt_abola","pt_benficatv","pt_canal11","pt_eleven1","pt_eleven2","pt_eleven3",
    "pt_sporttv1","pt_sporttv2","pt_sporttv3","pt_sporttv4","pt_sporttv5","pt_sporttv6","pt_sporttv7",
    "globoplaynovelas"
]
CANAIS_DISPONIVEIS = list(dict.fromkeys(CANAIS_DISPONIVEIS))

CACHE_SELENIUM = {}
LOCK_SELENIUM = threading.Lock()
TEMPO_CACHE_SELENIUM = 600

SESSION = ImpersonateSession.Session() if USE_CURL else ImpersonateSession.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def criar_sessao(imp=None):
    if USE_CURL:
        try: return ImpersonateSession.Session(impersonate=imp or "chrome120")
        except Exception: pass
    return ImpersonateSession.Session()

def extrair_nome_canal(url):
    m = re.search(r'/([^/]+)/index\.m3u8', url) or re.search(r'/([^/?]+)\.m3u8', url)
    return m.group(1).lower() if m else "stream"

def substituir_canal_na_url(url_orig, canal):
    antigo = extrair_nome_canal(url_orig)
    if antigo and antigo != "stream":
        res = re.sub(rf'/{re.escape(antigo)}/index\.m3u8', f'/{canal}/index.m3u8', url_orig, flags=re.I)
        if res != url_orig: return res
        return re.sub(rf'/{re.escape(antigo)}\.m3u8', f'/{canal}.m3u8', url_orig, flags=re.I)
    return url_orig

def listar_perfis():
    return sorted([os.path.splitext(f)[0] for f in os.listdir(PASTA_PERFIS) if f.endswith('.json')])

def carregar_perfil(p):
    f = os.path.join(PASTA_PERFIS, f"{p}.json")
    return json.load(open(f, 'r', encoding='utf-8')) if os.path.exists(f) else None

def obter_headers(cfg, ref_custom=None):
    h = {"User-Agent": cfg.get("user_agent") or USER_AGENT,
         "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
         "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site"}
    if cfg.get("cookie"): h["Cookie"] = cfg["cookie"]
    if cfg.get("origin"): h["Origin"] = cfg["origin"]
    ref = ref_custom or cfg.get("referer")
    if ref:
        h["Referer"] = ref
        if not h.get("Origin"):
            m = re.match(r'(https?://[^/]+)', ref)
            if m: h["Origin"] = m.group(1)
    return h

def extrair_links_playlist(html):
    ps = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.txt[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.m3u[^\s"\'<>]*)',
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        r'source\s*:\s*["\'](https?://[^"\']+)["\']'
    ]
    enc = []
    for p in ps: enc.extend(re.findall(p, html, re.I))
    return list(set(enc))

def processar_embed(canal):
    sess = criar_sessao("chrome120")
    for var in ALIASES.get(canal, [canal]):
        for base in EMBEDS_DOMINIOS:
            embed_url = f"{base}/{var}"
            try:
                r = sess.get(embed_url, headers={"User-Agent": USER_AGENT}, timeout=4, verify=False)
                if r.status_code == 200:
                    for u in extrair_links_playlist(r.text):
                        try:
                            r2 = sess.get(u, headers={"User-Agent": USER_AGENT, "Referer": embed_url}, timeout=4, verify=False)
                            if r2.status_code == 200 and ("#EXTM3U" in r2.text or "#EXT-X" in r2.text):
                                cfg = {"perfil_nome": f"embed_{var}", "user_agent": USER_AGENT, "referer": embed_url}
                                return r2, u, cfg, "chrome120"
                        except Exception: continue
            except Exception: continue
    return None, None, None, None

def processar_bruto(canal):
    for var in ALIASES.get(canal, [canal]):
        for p in listar_perfis():
            cfg = carregar_perfil(p)
            if not cfg: continue
            u = substituir_canal_na_url(cfg.get("url", ""), var)
            for imp in PROXIES:
                sess = criar_sessao(imp)
                try:
                    r = sess.get(u, headers=obter_headers(cfg), timeout=4, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        return r, u, cfg, imp
                except Exception: pass
    return None, None, None, None


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    return r


# ================== PÁGINA ==================

HTML_PAGINA = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; width: 100%; overflow-x: hidden; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: radial-gradient(ellipse at top, #1a1a2e 0%, #0a0a0f 60%);
    color: #fff;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px;
  }
  .app { width: 100%; max-width: 900px; }
  .brand { text-align: center; margin-bottom: 16px; }
  .brand h1 {
    font-size: clamp(2em, 7vw, 3.2em);
    font-weight: 900;
    letter-spacing: 2px;
    background: linear-gradient(135deg, #ffffff 0%, #a29bfe 50%, #6c5ce7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 2px;
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
    padding: 14px;
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6);
  }
  
  /* CONTAINER DO PLAYER */
  .video-js {
    width: 100%;
    height: 380px;
    border-radius: 14px;
    overflow: hidden;
    background: #000;
  }

  /* FORÇA PREENCHIMENTO 100% SEM BORDAS PRETAS EM TELA CHEIA */
  .video-js.vjs-fullscreen {
    width: 100vw !important;
    height: 100vh !important;
    top: 0 !important;
    left: 0 !important;
    position: fixed !important;
    border-radius: 0 !important;
    z-index: 999999 !important;
  }

  .video-js.vjs-fullscreen video,
  .video-js.vjs-fullscreen .vjs-tech {
    width: 100vw !important;
    height: 100vh !important;
    object-fit: cover !important;
  }

  @media (max-width: 640px) { .video-js:not(.vjs-fullscreen) { height: 220px; } }

  .controls { display: flex; gap: 10px; margin-top: 14px; }
  .controls input {
    flex: 1;
    background: rgba(13, 13, 20, 0.9);
    border: 1.5px solid rgba(108, 92, 231, 0.3);
    color: #fff;
    padding: 12px 14px;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 0.95em;
    font-weight: 500;
    outline: none;
  }
  .controls input:focus { border-color: #6c5ce7; }
  
  .btn-play {
    background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
    color: #fff;
    border: none;
    padding: 12px 20px;
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
    grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
    gap: 8px;
    margin-top: 12px;
    max-height: 220px;
    overflow-y: auto;
    padding-right: 4px;
  }
  .canal-btn {
    background: rgba(20, 20, 31, 0.7);
    border: 1.5px solid rgba(108, 92, 231, 0.4);
    color: #a29bfe;
    padding: 10px 4px;
    border-radius: 10px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 0.75em;
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
    margin-top: 10px;
    font-size: 0.85em;
    color: #888;
    min-height: 18px;
    font-weight: 500;
  }
  .status.ok { color: #00b894; }
  .status.err { color: #e74c3c; }
  .footer { text-align: center; color: #444; font-size: 0.75em; margin-top: 16px; }
</style>
</head>
<body>
  <div class="app">
    <div class="brand">
      <h1>MARCOS TV</h1>
      <div class="sub">STREAMING</div>
    </div>

    <div class="player-card">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>

      <div class="controls">
        <input id="canal" type="text" placeholder="Nome do canal..." autocomplete="off">
        <button id="btnPlay" class="btn-play" onclick="tocar()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          PLAY
        </button>
      </div>

      <div class="canais-fixos">
        {% for c in canais %}
        <div class="canal-btn" data-canal="{{ c }}" onclick="tocarFixo('{{ c }}', this)">{{ c }}</div>
        {% endfor %}
      </div>

      <div class="status" id="status"></div>
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

player.on('fullscreenchange', function() {
  if (player.isFullscreen()) {
    try {
      if (screen.orientation && screen.orientation.lock) {
        screen.orientation.lock('landscape').catch(function(){});
      }
    } catch(e) {}
  } else {
    try {
      if (screen.orientation && screen.orientation.unlock) {
        screen.orientation.unlock().catch(function(){});
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

  player.pause();
  player.error(null);
  player.src({ src: '/play/' + encodeURIComponent(canal) + '?t=' + Date.now(), type: 'application/x-mpegURL' });
  player.load();
  player.play()
    .then(function() {
      btn.disabled = false;
      setStatus('Tocando: ' + canal, 'ok');
    })
    .catch(function(e) {
      btn.disabled = false;
      setStatus('Tocando: ' + canal, 'ok');
    });
}

input.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') tocar();
});
</script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_PAGINA, canais=CANAIS_DISPONIVEIS)


@app.route('/play/<canal>')
def rota_play(canal):
    canal = canal.strip('/').lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal): return "Nome invalido", 400
    resp, url_a, cfg, tunel = processar_embed(canal)
    if resp: return gerar_playlist_proxy(resp, url_a, cfg, tunel)
    resp, url_a, cfg, tunel = processar_bruto(canal)
    if resp: return gerar_playlist_proxy(resp, url_a, cfg, tunel)
    return f"404: {canal}", 404


def gerar_playlist_proxy(resp, url_a, cfg, tunel):
    host = BASE_URL.rstrip('/')
    linhas = []
    base = getattr(resp, 'url', url_a)
    p_nome = cfg.get("perfil_nome", "")
    ref = quote(cfg.get("referer", "") or "", safe='')
    ck = quote(cfg.get("cookie", "") or "", safe='')
    for l in resp.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{host}{ep}?url={quote(abs_url, safe='')}&perfil={p_nome}&tunel={tunel}&ref={ref}&ck={ck}")
        else: linhas.append(ls)
    return Response("\n".join(linhas), status=200, headers={
        'Content-Type':'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin':'*',
        'Cache-Control':'no-cache'
    })


@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url',''))
    p = request.args.get('perfil','')
    tunel = request.args.get('tunel','chrome120')
    ref = unquote(request.args.get('ref','') or '')
    ck = unquote(request.args.get('ck','') or '')
    cfg = carregar_perfil(p) or {"user_agent": USER_AGENT}
    if ck: cfg["cookie"] = ck
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref), timeout=8, verify=False)
        if r.status_code != 200: return f"upstream {r.status_code}", r.status_code
        host = BASE_URL.rstrip('/')
        base = getattr(r, 'url', target)
        linhas = []
        ref_e = quote(ref or cfg.get("referer","") or "", safe='')
        ck_e = quote(ck or cfg.get("cookie","") or "", safe='')
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                linhas.append(f"{host}{ep}?url={quote(abs_url, safe='')}&perfil={p}&tunel={tunel}&ref={ref_e}&ck={ck_e}")
            else: linhas.append(ls)
        return Response("\n".join(linhas), status=200, headers={
            'Content-Type':'application/vnd.apple.mpegurl',
            'Access-Control-Allow-Origin':'*',
            'Cache-Control':'no-cache'
        })
    except Exception as e:
        return str(e), 500


@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url',''))
    p = request.args.get('perfil','')
    tunel = request.args.get('tunel','chrome120')
    ref = unquote(request.args.get('ref','') or '')
    ck = unquote(request.args.get('ck','') or '')
    cfg = carregar_perfil(p) or {"user_agent": USER_AGENT}
    if ck: cfg["cookie"] = ck
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref), stream=True, timeout=15, verify=False)
        def gerar():
            if hasattr(r, 'iter_content'):
                for ch in r.iter_content(128*1024):
                    if ch: yield ch
            else: yield r.content
        return Response(gerar(), status=r.status_code, headers={
            'Content-Type':'video/mp2t',
            'Access-Control-Allow-Origin':'*',
            'Accept-Ranges':'bytes'
        })
    except Exception as e:
        return f"Erro TS: {e}", 500


if __name__ == '__main__':
    import logging as _l
    _l.getLogger('werkzeug').disabled = True
    _l.getLogger('flask').disabled = True
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.log = lambda self, type, msg, *args: None
    print("=" * 55)
    print("             MARCOS TV - ONLINE")
    print("=" * 55)
    print(f"  Local:    http://localhost:{PORTA}")
    print(f"  Público:  {BASE_URL}")
    print(f"  Túnel:    ssh -R tvmrc1:80:127.0.0.1:{PORTA} serveo.net")
    print("=" * 55)
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
