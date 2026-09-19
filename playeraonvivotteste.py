import requests, re, os, sys, socket, time, subprocess, threading
from flask import Flask, Response, request, render_template_string
from flask_cors import CORS
from urllib.parse import urljoin, quote, unquote, urlparse
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=100)
session.mount('https://', adapter)

app = Flask(__name__)
CORS(app)

PORTA = int(os.environ.get("PORT", 8888))

ULTIMO_CANAL = "---"
DOMINIO_ATUAL = "---"

REFERER_PORTAL = "https://1709.cdnembedcanais.xyz/"
BASE_PORTAL = "https://1709.cdnembedcanais.xyz"

CANAIS = [
    "warner", "adultswim", "amazonprimevideo", "amazonprime", "bandsports", "canaloff", "cazetv",
    "combate", "dazn", "disneyplus",
    "espn", "espn2", "espn3", "espn4", "espn5", "espn6",
    "max", "max02", "max03", "max04", "max05", "max06",
    "nossofutebol", "nsports", "paramountplus",
    "premiereclubes", "premiere2", "premiere3", "premiere4", "premiere5", "premiere6", "premiere7", "premiere8",
    "sportv", "sportv2", "sportv3", "tnt", "xsports",
    "ae", "amc", "axn", "cinemax", "globoplaynovelas",
    "hbo", "hbo2", "hbofamily", "hbomundi", "hboplus", "hbopop", "hbosignature", "hboxtreme",
    "megapix", "paramountnetwork", "sonychannel", "space", "studiouniversal",
    "tcaction", "tccult", "tcfun", "tcpipoca", "tcpremium", "tctouch",
    "tntnovelas", "tntseries", "universaltv",
    "bandsp", "globomg", "globorj", "globors", "globosp",
    "recordmg", "recordrj", "recordsp", "redetv", "sbtsp", "tvcultura",
    "animalplanet", "comedycentral",
    "discoverychannel", "discoveryhomehealth", "investigationdiscovery", "discoveryscience",
    "discoverytheater", "discoveryturbo", "discoveryworld",
    "foodnetwork", "gnt", "hgtv", "history", "history2",
    "mtv", "multishow", "bandnews", "cnnbrasil", "globonews", "jovempannews", "recordnews",
    "cartoonito", "cartoonnetwork", "discoverykids", "dreamworks",
    "gloob", "gloobinho", "nickelodeon", "nickjr", "tooncast"
]


def capturar_dominio_real(nome):
    url_portal = f"{BASE_PORTAL}/{nome}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": REFERER_PORTAL,
        "Accept": "*/*"
    }
    try:
        r = session.get(url_portal, headers=headers, timeout=8, verify=False)
        links = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', r.text)
        for link in links:
            if nome in link.lower() or "index" in link.lower():
                return urlparse(link).netloc, link
        if links:
            return urlparse(links[0]).netloc, links[0]
    except Exception:
        pass
    return None, None


def obter_ip_rede():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}:{PORTA}"
    except Exception:
        return f"http://127.0.0.1:{PORTA}"


@app.route('/stream/<nome>')
def proxy_m3u8(nome):
    global ULTIMO_CANAL, DOMINIO_ATUAL
    nome = nome.lower().strip('/')
    ULTIMO_CANAL = nome.upper()

    dom_real, link_real = capturar_dominio_real(nome)

    if dom_real:
        DOMINIO_ATUAL = dom_real

        candidatos = []
        if link_real:
            candidatos.append(link_real)
        candidatos += [
            f"https://{dom_real}/{nome}/tracks-v1a1/mono.ts.m3u8",
            f"https://{dom_real}/{nome}/index.m3u8",
            f"https://{dom_real}/index.m3u8",
            f"https://{dom_real}/{nome}/playlist.m3u8",
        ]

        for url in candidatos:
            try:
                r = session.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": REFERER_PORTAL,
                        "Origin": BASE_PORTAL
                    },
                    timeout=6,
                    verify=False
                )
                if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                    base = url.rsplit('/', 1)[0] + "/"
                    host = request.host_url.rstrip('/')
                    linhas = []
                    for line in r.text.splitlines():
                        ls = line.strip()
                        if ls and not ls.startswith('#'):
                            abs_url = urljoin(base, ls)
                            ep = "/m3u8" if '.m3u8' in ls else "/ts"
                            linhas.append(f"{host}{ep}?url={quote(abs_url, safe='')}&ref={quote(REFERER_PORTAL, safe='')}")
                        else:
                            linhas.append(ls)
                    return Response("\n".join(linhas), status=200, headers={
                        'Content-Type': 'application/x-mpegURL',
                        'Access-Control-Allow-Origin': '*',
                        'Cache-Control': 'no-cache'
                    })
            except Exception:
                continue

    DOMINIO_ATUAL = "OFFLINE"
    return "Canal offline", 503


@app.route('/m3u8')
def proxy_subm3u8():
    target = unquote(request.args.get('url', ''))
    ref = unquote(request.args.get('ref', '') or REFERER_PORTAL)
    if not target:
        return "URL ausente", 400
    try:
        r = session.get(target, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": ref,
            "Origin": BASE_PORTAL
        }, timeout=8, verify=False)
        if r.status_code != 200:
            return f"upstream {r.status_code}", r.status_code
        base = getattr(r, 'url', target)
        host = request.host_url.rstrip('/')
        linhas = []
        for line in r.text.splitlines():
            ls = line.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/m3u8" if '.m3u8' in ls else "/ts"
                linhas.append(f"{host}{ep}?url={quote(abs_url, safe='')}&ref={quote(ref, safe='')}")
            else:
                linhas.append(ls)
        return Response("\n".join(linhas), status=200, headers={
            'Content-Type': 'application/x-mpegURL',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache'
        })
    except Exception as e:
        return f"Erro: {e}", 500


@app.route('/ts')
def proxy_ts():
    target = unquote(request.args.get('url', ''))
    ref = unquote(request.args.get('ref', '') or REFERER_PORTAL)
    if not target:
        return "URL ausente", 400
    try:
        r = session.get(target, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": ref,
            "Origin": BASE_PORTAL
        }, stream=True, timeout=15, verify=False)
        def gerar():
            for chunk in r.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk
        return Response(gerar(), status=r.status_code, headers={
            'Content-Type': 'video/mp2t',
            'Access-Control-Allow-Origin': '*',
            'Accept-Ranges': 'bytes'
        })
    except Exception as e:
        return f"Erro TS: {e}", 500


@app.route('/playlist')
def baixar_playlist():
    ip = request.host_url.rstrip('/')
    linhas = ["#EXTM3U"]
    for c in sorted(CANAIS):
        linhas.append(f'#EXTINF:-1 tvg-name="{c.upper()}" group-title="CANAIS",{c.upper()}')
        linhas.append(f"{ip}/stream/{c}")
    return Response("\n".join(linhas), content_type='text/plain')


HTML_PAGINA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800;900&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html { height: 100%; overflow: hidden; }
  body {
    font-family: 'Orbitron', 'Inter', -apple-system, Arial, sans-serif;
    background: #000a14;
    color: #fff;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  /* ===== FUNDO ===== */
  .stars {
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image:
      radial-gradient(1px 1px at 20% 30%, #ff8c00, transparent),
      radial-gradient(1px 1px at 60% 70%, #0088ff, transparent),
      radial-gradient(1px 1px at 80% 20%, #ffa500, transparent),
      radial-gradient(1px 1px at 10% 80%, #00aaff, transparent),
      radial-gradient(1px 1px at 40% 50%, #ffffff, transparent),
      radial-gradient(1px 1px at 90% 60%, #ff8c00, transparent),
      radial-gradient(1px 1px at 30% 90%, #0088ff, transparent),
      radial-gradient(1px 1px at 70% 10%, #ffffff, transparent);
    animation: estrelas 20s linear infinite;
  }
  @keyframes estrelas {
    from { opacity: 0.4; } 50% { opacity: 1; } to { opacity: 0.4; }
  }
  .bg-glow { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
  .glow {
    position: absolute; border-radius: 50%;
    filter: blur(140px);
    animation: pulsar 6s ease-in-out infinite;
  }
  .glow1 {
    width: 700px; height: 700px;
    background: radial-gradient(circle, #0088ff 0%, transparent 70%);
    top: -250px; left: -200px;
    opacity: 0.6;
  }
  .glow2 {
    width: 600px; height: 600px;
    background: radial-gradient(circle, #ff8c00 0%, transparent 70%);
    bottom: -200px; right: -180px;
    opacity: 0.5;
    animation-delay: -3s;
  }
  .glow3 {
    width: 500px; height: 500px;
    background: radial-gradient(circle, #ffa500 0%, transparent 70%);
    top: 40%; left: 40%;
    opacity: 0.3;
    animation-delay: -1.5s;
  }
  @keyframes pulsar {
    0%, 100% { transform: scale(1); opacity: 0.5; }
    50% { transform: scale(1.2); opacity: 0.8; }
  }
  .grid-bg {
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image:
      linear-gradient(rgba(0, 136, 255, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255, 140, 0, 0.06) 1px, transparent 1px);
    background-size: 60px 60px;
    mask-image: radial-gradient(ellipse at center, #000 5%, transparent 65%);
    -webkit-mask-image: radial-gradient(ellipse at center, #000 5%, transparent 65%);
  }

  /* ===== TOPO FIXO ===== */
  .topo-fixo {
    position: relative; z-index: 10;
    flex-shrink: 0;
    padding: 10px 14px;
    background: linear-gradient(180deg, rgba(0, 6, 14, 0.98) 0%, rgba(0, 6, 14, 0.85) 100%);
    border-bottom: 1px solid rgba(0, 136, 255, 0.35);
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6), 0 1px 0 rgba(255, 140, 0, 0.2);
  }
  .brand { text-align: center; margin-bottom: 8px; }
  .brand h1 {
    font-family: 'Orbitron', sans-serif;
    font-size: clamp(1.2em, 5vw, 1.9em);
    font-weight: 900; letter-spacing: 6px;
    background: linear-gradient(135deg, #ffffff 0%, #0088ff 40%, #ff8c00 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 0 15px rgba(0, 136, 255, 0.8)) drop-shadow(0 0 30px rgba(255, 140, 0, 0.5));
    animation: brilhar 3s ease-in-out infinite;
  }
  @keyframes brilhar {
    0%, 100% { filter: drop-shadow(0 0 15px rgba(0, 136, 255, 0.8)) drop-shadow(0 0 30px rgba(255, 140, 0, 0.5)) brightness(1); }
    50% { filter: drop-shadow(0 0 25px rgba(0, 136, 255, 1)) drop-shadow(0 0 50px rgba(255, 140, 0, 0.8)) brightness(1.3); }
  }
  .brand .sub {
    color: #ff8c00;
    font-size: 0.55em; letter-spacing: 8px;
    font-weight: 600; text-transform: uppercase;
    text-shadow: 0 0 15px rgba(255, 140, 0, 1), 0 0 30px rgba(0, 136, 255, 0.5);
  }

  /* ===== PLAYER ===== */
  .player-wrap {
    position: relative;
    background: linear-gradient(135deg, rgba(0, 10, 25, 0.95), rgba(10, 15, 30, 0.95));
    border: 1.5px solid rgba(0, 136, 255, 0.5);
    border-radius: 12px; padding: 6px;
    box-shadow:
      0 0 30px rgba(0, 136, 255, 0.35),
      0 0 60px rgba(255, 140, 0, 0.2),
      0 20px 60px rgba(0, 0, 0, 0.9);
    overflow: hidden;
  }
  .player-wrap::before {
    content: '';
    position: absolute;
    top: -2px; left: -100%;
    width: 100%; height: 2px;
    background: linear-gradient(90deg, transparent, #0088ff, #ff8c00, #0088ff, transparent);
    animation: scanline 4s linear infinite;
  }
  @keyframes scanline { 0% { left: -100%; } 100% { left: 100%; } }
  .video-js {
    width: 100%; height: 32vh; max-height: 280px; min-height: 140px;
    border-radius: 8px; overflow: hidden; background: #000;
  }

  /* ===== ÁREA DOS CANAIS ===== */
  .canais-area {
    position: relative; z-index: 1;
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    -webkit-overflow-scrolling: touch;
  }
  .canais-area::-webkit-scrollbar { width: 4px; }
  .canais-area::-webkit-scrollbar-track { background: transparent; }
  .canais-area::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #0088ff, #ff8c00);
    border-radius: 4px;
  }
  .canais-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 6px;
    padding-bottom: 20px;
  }
  .canal-btn {
    position: relative;
    background: rgba(0, 10, 25, 0.85);
    border: 1.5px solid rgba(0, 136, 255, 0.45);
    color: #ff8c00;
    padding: 12px 6px;
    border-radius: 8px;
    font-family: 'Orbitron', sans-serif;
    font-weight: 700; font-size: 0.62em;
    letter-spacing: 1.2px; text-transform: uppercase;
    cursor: pointer; transition: all 0.15s ease;
    text-align: center;
    text-shadow: 0 0 8px rgba(255, 140, 0, 0.8);
    user-select: none; touch-action: manipulation;
    overflow: hidden;
  }
  .canal-btn::before {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(0, 136, 255, 0.3), transparent);
    transition: left 0.5s;
  }
  .canal-btn:hover::before { left: 100%; }
  .canal-btn:hover, .canal-btn:active {
    background: rgba(0, 136, 255, 0.25);
    border-color: #ff8c00;
    color: #ffffff;
    box-shadow:
      0 0 20px rgba(255, 140, 0, 0.6),
      0 0 40px rgba(0, 136, 255, 0.3);
  }
  .canal-btn.ativo {
    background: linear-gradient(135deg, rgba(0, 136, 255, 0.5), rgba(255, 140, 0, 0.4));
    border-color: #ff8c00;
    color: #fff;
    box-shadow:
      0 0 25px rgba(255, 140, 0, 0.9),
      0 0 50px rgba(0, 136, 255, 0.5);
    animation: ativo-pulsar 1.5s ease-in-out infinite;
  }
  @keyframes ativo-pulsar {
    0%, 100% { box-shadow: 0 0 25px rgba(255, 140, 0, 0.9), 0 0 50px rgba(0, 136, 255, 0.5); }
    50% { box-shadow: 0 0 35px rgba(255, 140, 0, 1), 0 0 70px rgba(0, 136, 255, 0.8); }
  }

  /* ===== VIDEO.JS CUSTOM ===== */
  .video-js .vjs-big-play-button {
    background: radial-gradient(circle, rgba(0, 136, 255, 0.95), rgba(255, 140, 0, 0.95));
    border: 2px solid #ff8c00;
    width: 60px; height: 60px; line-height: 56px;
    border-radius: 50%;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    box-shadow:
      0 0 20px #ff8c00,
      0 0 40px rgba(0, 136, 255, 0.7);
    animation: play-pulse 2s ease-in-out infinite;
  }
  @keyframes play-pulse {
    0%, 100% { box-shadow: 0 0 20px #ff8c00, 0 0 40px rgba(0, 136, 255, 0.7); }
    50% { box-shadow: 0 0 30px #ff8c00, 0 0 60px rgba(0, 136, 255, 1); }
  }
  .video-js .vjs-big-play-button:hover {
    transform: translate(-50%, -50%) scale(1.1);
  }
  .video-js .vjs-control-bar {
    background: linear-gradient(to top, rgba(0, 6, 14, 0.98), transparent);
    height: 40px;
    border-top: 1px solid rgba(0, 136, 255, 0.2);
  }
  .video-js .vjs-play-progress {
    background: linear-gradient(90deg, #0088ff, #ff8c00);
    box-shadow: 0 0 8px #ff8c00;
  }
  .video-js .vjs-load-progress { background: rgba(0, 136, 255, 0.3); }
  .video-js .vjs-slider { background: rgba(255, 140, 0, 0.25); }
  .video-js .vjs-volume-level {
    background: #ff8c00;
    box-shadow: 0 0 8px #ff8c00;
  }
  .video-js .vjs-play-control .vjs-icon-placeholder:before {
    color: #ff8c00;
    text-shadow: 0 0 10px #ff8c00;
  }
  .video-js .vjs-fullscreen-control .vjs-icon-placeholder:before {
    color: #0088ff;
    text-shadow: 0 0 10px #0088ff;
  }
  .video-js .vjs-volume-panel .vjs-icon-placeholder:before {
    color: #0088ff;
    text-shadow: 0 0 10px #0088ff;
  }
  .video-js .vjs-current-time,
  .video-js .vjs-duration,
  .video-js .vjs-remaining-time {
    color: #ff8c00;
    text-shadow: 0 0 8px rgba(255, 140, 0, 0.6);
  }
</style>
</head>
<body>
  <div class="stars"></div>
  <div class="bg-glow">
    <div class="glow glow1"></div>
    <div class="glow glow2"></div>
    <div class="glow glow3"></div>
  </div>
  <div class="grid-bg"></div>

  <div class="topo-fixo">
    <div class="brand">
      <h1>MARCOS TV</h1>
      <div class="sub">Premium Streaming</div>
    </div>
    <div class="player-wrap">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>
    </div>
  </div>

  <div class="canais-area">
    <div class="canais-grid" id="canais">
      {% for c in canais %}
      <div class="canal-btn" data-canal="{{ c }}">{{ c }}</div>
      {% endfor %}
    </div>
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
      smoothQualityChange: true,
      fastQualityChange: true
    }
  }
});

function marcarAtivo(el) {
  document.querySelectorAll('.canal-btn').forEach(function(b){ b.classList.remove('ativo'); });
  if (el) el.classList.add('ativo');
}

document.getElementById('canais').addEventListener('click', function(e) {
  var alvo = e.target.closest('.canal-btn');
  if (!alvo) return;
  var canal = alvo.getAttribute('data-canal');
  if (!canal) return;
  marcarAtivo(alvo);

  player.pause();
  player.src({ src: 'about:blank' });

  var url = '/stream/' + encodeURIComponent(canal) + '?t=' + Date.now();
  player.src({ src: url, type: 'application/x-mpegURL' });
  player.play().catch(function(){});
});

player.on('error', function() {
  setTimeout(function() {
    var s = player.src();
    if (s && s.indexOf('/stream/') !== -1) {
      var c = s.split('/stream/')[1].split('?')[0];
      player.src({ src: '/stream/' + c + '?t=' + Date.now(), type: 'application/x-mpegURL' });
      player.play().catch(function(){});
    }
  }, 1500);
});

var ultimoTempo = 0, travadoDesde = null;
setInterval(function() {
  if (player.paused() || player.readyState() < 2) { travadoDesde = null; return; }
  var t = player.currentTime();
  if (t === ultimoTempo) {
    if (!travadoDesde) travadoDesde = Date.now();
    else if (Date.now() - travadoDesde > 10000) {
      travadoDesde = null;
      var s = player.src();
      if (s && s.indexOf('/stream/') !== -1) {
        var c = s.split('/stream/')[1].split('?')[0];
        player.src({ src: '/stream/' + c + '?t=' + Date.now(), type: 'application/x-mpegURL' });
        player.play().catch(function(){});
      }
    }
  } else { ultimoTempo = t; travadoDesde = null; }
}, 2000);
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_PAGINA, canais=CANAIS)


if __name__ == '__main__':
    import logging as _l
    _l.getLogger('werkzeug').disabled = True
    _l.getLogger('flask').disabled = True
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.log = lambda self, type, msg, *args: None
    print("=" * 50)
    print("       MARCOS TV - PROXY")
    print("=" * 50)
    print(f"  Porta: {PORTA}")
    print(f"  Local: http://localhost:{PORTA}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
