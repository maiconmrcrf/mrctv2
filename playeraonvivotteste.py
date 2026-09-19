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

# ====== CANAIS FIXOS NA INTERFACE ======
CANAIS_FIXOS = [
    "espn",
    "premiereclubes",
    "tnt",
    "telecinepipoca",
    "telecinefun",
    "telecinepremium",
    "space",
]

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
HTML_PAGINA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>MARCOS TV</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  :root{
    --bg-0:#05060a;
    --txt:#e8ecf4;
    --txt-dim:#7a8494;
    --accent:#8b7dff;
    --accent-2:#5be6ff;
    --accent-3:#ff6ec7;
    --accent-4:#ffd66e;
  }
  html{height:100%;overflow:hidden}
  body{
    font-family:'Space Grotesk',-apple-system,Arial,sans-serif;
    background:var(--bg-0);
    color:var(--txt);
    height:100vh;
    overflow:hidden;
    display:flex;
    flex-direction:column;
    position:relative;
  }
  .bg{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
  .bg::before{
    content:'';position:absolute;inset:0;
    background:
      radial-gradient(1200px 800px at 12% -10%, rgba(139,125,255,.35), transparent 60%),
      radial-gradient(900px 700px at 110% 10%, rgba(91,230,255,.25), transparent 60%),
      radial-gradient(1000px 900px at 50% 120%, rgba(255,110,199,.22), transparent 60%),
      radial-gradient(800px 600px at 80% 80%, rgba(255,214,110,.12), transparent 60%);
    animation:aurora 18s ease-in-out infinite alternate;
  }
  @keyframes aurora{
    0%{transform:translate3d(0,0,0) scale(1)}
    50%{transform:translate3d(-2%,1%,0) scale(1.05)}
    100%{transform:translate3d(2%,-1%,0) scale(1.02)}
  }
  .bg::after{
    content:'';position:absolute;inset:0;
    background-image:
      linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
    background-size:64px 64px;
    mask-image:radial-gradient(ellipse at 50% 40%, #000 20%, transparent 75%);
    -webkit-mask-image:radial-gradient(ellipse at 50% 40%, #000 20%, transparent 75%);
  }
  .grain{
    position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.35;mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/></svg>");
  }
  header{
    position:relative;z-index:5;
    display:flex;align-items:center;justify-content:space-between;
    padding:18px 22px 12px; gap:12px;
  }
  .logo{
    font-family:'Syne',sans-serif; font-weight:800; letter-spacing:.28em;
    font-size:clamp(14px,2.4vw,20px);
    background:linear-gradient(90deg,#fff 0%, #b7b1ff 35%, #5be6ff 70%, #ff6ec7 100%);
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
    filter:drop-shadow(0 0 18px rgba(139,125,255,.55));
  }
  .logo .dot{
    display:inline-block;width:6px;height:6px;border-radius:50%;
    background:var(--accent-2); margin-right:10px;
    box-shadow:0 0 12px var(--accent-2),0 0 30px var(--accent-2);
    vertical-align:middle; animation:blip 2.4s ease-in-out infinite;
  }
  @keyframes blip{0%,100%{opacity:1}50%{opacity:.35}}
  .meta{display:flex;gap:10px;align-items:center;font-size:11px;color:var(--txt-dim);letter-spacing:.15em;text-transform:uppercase}
  .pill{
    padding:6px 12px;border-radius:999px;
    border:1px solid rgba(255,255,255,.08);
    background:rgba(255,255,255,.02); backdrop-filter:blur(8px);
    display:inline-flex;align-items:center;gap:6px;
  }
  .pill .live{width:6px;height:6px;border-radius:50%;background:#ff4d6d;box-shadow:0 0 10px #ff4d6d;animation:blip 1.4s infinite}
  main{
    position:relative;z-index:3; flex:1; display:flex; flex-direction:column;
    padding:0 22px 22px; gap:18px; overflow:hidden; min-height:0;
  }
  @media(min-width:1024px){
    main{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:22px;align-items:start;}
  }
  .stage{
    position:relative; border-radius:22px;
    background:linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.01));
    border:1px solid rgba(255,255,255,.07);
    padding:12px; overflow:hidden;
    box-shadow: 0 40px 120px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.02) inset, 0 0 100px rgba(139,125,255,.15);
  }
  .stage::before{
    content:'';position:absolute;inset:-1px;border-radius:22px;padding:1px;
    background:conic-gradient(from 180deg at 50% 50%,
      rgba(139,125,255,.6), rgba(91,230,255,.6), rgba(255,110,199,.6), rgba(255,214,110,.6), rgba(139,125,255,.6));
    -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite:xor; mask-composite:exclude;
    animation:spin 12s linear infinite; opacity:.55; pointer-events:none;
  }
  @keyframes spin{to{transform:rotate(360deg)}}

  .video-js{
    width:100%;
    height:58vh;
    max-height:62vh;
    border-radius:16px;
    overflow:hidden;
    background:#000;
  }
  @media(max-width:900px){ .video-js{ height:52vh; } }

  .video-js video,
  .video-js .vjs-tech{
    object-fit: cover !important;
    width: 100% !important;
    height: 100% !important;
  }

  .fit-toggle{
    position:absolute; top:18px; right:18px;
    background:rgba(0,0,0,.6); backdrop-filter:blur(10px);
    border:1px solid rgba(255,255,255,.18);
    color:#fff; padding:8px 14px; border-radius:999px;
    font-family:'Syne',sans-serif; font-weight:700; font-size:11px;
    letter-spacing:.14em; text-transform:uppercase; cursor:pointer;
    z-index:20; transition:all .2s ease;
    display:flex; align-items:center; gap:6px;
  }
  .fit-toggle:hover{
    background:rgba(91,230,255,.25);
    border-color:#5be6ff;
    box-shadow:0 0 20px rgba(91,230,255,.35);
  }

  .now{
    display:flex;justify-content:space-between;align-items:center;
    margin-top:14px;padding:0 6px;gap:12px;flex-wrap:wrap;
  }
  .now .title{display:flex;align-items:center;gap:12px;min-width:0}
  .now .badge{
    font-family:'Syne',sans-serif;font-weight:700;font-size:11px;
    letter-spacing:.18em;text-transform:uppercase;color:#0a0a12;
    padding:6px 12px;border-radius:999px;
    background:linear-gradient(135deg,#5be6ff,#8b7dff);
    box-shadow:0 0 24px rgba(91,230,255,.35); white-space:nowrap;
  }
  .now .name{
    font-family:'Syne',sans-serif;font-weight:700;
    font-size:clamp(14px,2vw,18px);
    letter-spacing:.05em;color:#fff;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  }
  .now .name.off{color:var(--txt-dim)}
  .now .stat{font-size:11px;color:var(--txt-dim);letter-spacing:.12em;text-transform:uppercase}

  .panel{
    position:relative;border-radius:22px;
    background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.005));
    border:1px solid rgba(255,255,255,.06);
    padding:16px;min-height:0;
    display:flex;flex-direction:column;overflow:hidden;
    box-shadow:0 30px 80px rgba(0,0,0,.5), 0 0 60px rgba(91,230,255,.06);
  }
  @media(max-width:1023px){ .panel{flex:1} }
  .panel-head{
    display:flex;align-items:center;justify-content:space-between;
    margin-bottom:12px;gap:8px;flex-wrap:wrap;
  }
  .panel-title{
    font-family:'Syne',sans-serif;font-weight:700;font-size:12px;
    letter-spacing:.24em;text-transform:uppercase;color:#cfd4e4;
    display:flex;align-items:center;gap:10px;
  }
  .panel-title::before{
    content:'';width:16px;height:1px;background:linear-gradient(90deg,transparent,var(--accent-2));display:inline-block;
  }
  .search{position:relative;flex:1;max-width:220px}
  .search input{
    width:100%;background:rgba(0,0,0,.35);
    border:1px solid rgba(255,255,255,.08);border-radius:999px;
    padding:8px 14px 8px 34px;color:#fff;font-size:12px;outline:none;
    font-family:'Space Grotesk',sans-serif;letter-spacing:.02em;
    transition:border-color .2s, box-shadow .2s;
  }
  .search input:focus{border-color:rgba(91,230,255,.6);box-shadow:0 0 0 3px rgba(91,230,255,.12)}
  .search::before{
    content:'';position:absolute;left:13px;top:50%;transform:translateY(-50%);
    width:12px;height:12px;border:1.5px solid #6b7285;border-radius:50%;
  }
  .search::after{
    content:'';position:absolute;left:22px;top:calc(50% + 4px);
    width:5px;height:1.5px;background:#6b7285;transform:rotate(45deg);border-radius:2px;
  }
  .grid{
    display:grid;grid-template-columns:repeat(auto-fill, minmax(96px, 1fr));
    gap:8px;overflow-y:auto;padding-right:4px;padding-bottom:8px;
    min-height:0;flex:1;
  }
  .grid::-webkit-scrollbar{width:6px}
  .grid::-webkit-scrollbar-thumb{background:linear-gradient(180deg,var(--accent),var(--accent-2));border-radius:99px}
  .grid::-webkit-scrollbar-track{background:transparent}
  .ch{
    position:relative;border-radius:12px;padding:14px 8px;text-align:center;
    font-family:'Syne',sans-serif;font-weight:600;font-size:10px;
    letter-spacing:.16em;text-transform:uppercase;color:#cfd4e4;
    background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);
    cursor:pointer;transition:transform .2s ease, background .25s ease, border-color .25s ease, color .25s ease, box-shadow .25s ease;
    overflow:hidden;user-select:none;touch-action:manipulation;
  }
  .ch::before{
    content:'';position:absolute;inset:0;
    background:linear-gradient(135deg, rgba(139,125,255,.18), rgba(91,230,255,.12));
    opacity:0;transition:opacity .25s ease;
  }
  .ch span{position:relative;z-index:1}
  .ch:hover{
    transform:translateY(-2px);border-color:rgba(91,230,255,.4);color:#fff;
    box-shadow:0 10px 30px rgba(91,230,255,.15), inset 0 0 20px rgba(91,230,255,.06);
  }
  .ch:hover::before{opacity:1}
  .ch.active{
    color:#0a0a12;background:linear-gradient(135deg,#5be6ff,#8b7dff);
    border-color:transparent;
    box-shadow:0 10px 40px rgba(91,230,255,.45), 0 0 60px rgba(139,125,255,.25);
    transform:translateY(-1px);
  }
  .ch.active::before{opacity:0}
  .video-js .vjs-big-play-button{
    background:radial-gradient(circle at 30% 30%, rgba(255,255,255,.9), rgba(139,125,255,.9) 45%, rgba(91,230,255,.9) 100%);
    border:none;width:84px;height:84px;line-height:84px;border-radius:50%;
    top:50%;left:50%;transform:translate(-50%,-50%);
    box-shadow: 0 0 0 8px rgba(139,125,255,.15), 0 0 40px rgba(91,230,255,.55), 0 20px 60px rgba(0,0,0,.5);
    transition:transform .25s ease;
  }
  .video-js .vjs-big-play-button:hover{transform:translate(-50%,-50%) scale(1.08)}
  .video-js .vjs-big-play-button .vjs-icon-placeholder:before{font-size:36px;line-height:84px;color:#05060a}
  .video-js .vjs-control-bar{
    background:linear-gradient(to top, rgba(5,6,10,.95), rgba(5,6,10,.55) 60%, transparent);
    height:48px;backdrop-filter:blur(6px);
    border-top:1px solid rgba(255,255,255,.06);
  }
  .video-js .vjs-play-progress{background:linear-gradient(90deg,#5be6ff,#8b7dff,#ff6ec7)}
  .video-js .vjs-load-progress{background:rgba(255,255,255,.1)}
  .video-js .vjs-slider{background:rgba(255,255,255,.1)}
  .video-js .vjs-volume-level{background:linear-gradient(90deg,#5be6ff,#8b7dff)}
  .video-js .vjs-button>.vjs-icon-placeholder:before{color:#e8ecf4;text-shadow:0 0 10px rgba(91,230,255,.35)}
  .video-js .vjs-time-control{color:#cfd4e4}
  @media(max-width:1023px){
    header{padding:14px 14px 8px}
    main{padding:0 14px 14px;gap:12px}
    .stage{padding:8px;border-radius:16px}
    .video-js{border-radius:12px}
    .now .badge{font-size:10px;padding:5px 10px}
    .grid{grid-template-columns:repeat(auto-fill, minmax(84px,1fr));gap:6px}
  }
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="grain"></div>

  <header>
    <div class="logo"><span class="dot"></span>MARCOS TV</div>
    <div class="meta">
      <span class="pill"><span class="live"></span>LIVE</span>
      <span class="pill" id="clock">--:--</span>
    </div>
  </header>

  <main>
    <section class="stage">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>
      <button class="fit-toggle" id="fitToggle" title="Alternar modo de exibição">Cover</button>
      <div class="now">
        <div class="title">
          <div class="badge">ON AIR</div>
          <div class="name off" id="nowName">Nenhum canal selecionado</div>
        </div>
        <div class="stat" id="nowStat">Aguardando</div>
      </div>
    </section>

    <aside class="panel">
      <div class="panel-head">
        <div class="panel-title">Canais</div>
        <div class="search"><input id="q" placeholder="Buscar canal..." autocomplete="off"></div>
      </div>
      <div class="grid" id="grid">
        {% for c in canais %}
        <div class="ch" data-canal="{{ c }}"><span>{{ c }}</span></div>
        {% endfor %}
      </div>
    </aside>
  </main>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
  function atualizarRelogio(){
    var d = new Date();
    document.getElementById('clock').textContent =
      String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
  }
  setInterval(atualizarRelogio, 1000); atualizarRelogio();

  var player = videojs('player', {
    controls: true, autoplay: false, preload: 'auto', liveui: true,
    html5: { vhs: { overrideNative: true, maxBufferLength: 60, maxMaxBufferLength: 120, liveSyncDuration: 10, liveMaxLatencyDuration: 60, enableLowInitialPlaylist: true, smoothQualityChange: true, fastQualityChange: true } }
  });

  var grid = document.getElementById('grid');
  var nomeEl = document.getElementById('nowName');
  var statEl = document.getElementById('nowStat');

  /* TOGGLE COVER / CONTAIN */
  var fitModo = 'cover';
  var btnFit = document.getElementById('fitToggle');
  function aplicarFit(){
    var tech = document.querySelector('.video-js video, .video-js .vjs-tech');
    if (tech) tech.style.objectFit = fitModo;
    btnFit.textContent = (fitModo === 'cover') ? 'Cover' : 'Contain';
  }
  btnFit.addEventListener('click', function(){
    fitModo = (fitModo === 'cover') ? 'contain' : 'cover';
    aplicarFit();
  });
  player.on('loadedmetadata', aplicarFit);
  player.on('play', aplicarFit);
  aplicarFit();

  function marcar(canal){
    document.querySelectorAll('.ch').forEach(function(el){
      el.classList.toggle('active', el.getAttribute('data-canal') === canal);
    });
  }
  function setInfo(nome, sub){
    if (nome){ nomeEl.textContent = nome.toUpperCase(); nomeEl.classList.remove('off'); }
    else { nomeEl.textContent = 'Nenhum canal selecionado'; nomeEl.classList.add('off'); }
    statEl.textContent = sub || '';
  }
  function tocar(canal){
    marcar(canal);
    setInfo(canal, 'Conectando...');
    player.pause();
    player.src({ src: 'about:blank' });

    fetch('/testar/' + encodeURIComponent(canal))
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          var url = '/play/' + encodeURIComponent(canal) + '?t=' + Date.now();
          player.src({ src: url, type: 'application/x-mpegURL' });
          player.play().then(function(){
            setInfo(canal, 'AO VIVO');
            aplicarFit();
          }).catch(function(){ setInfo(canal, 'Aguardando play'); });
        } else {
          setInfo(canal, d.msg || 'Canal indisponivel');
        }
      })
      .catch(function(){ setInfo(canal, 'Erro'); });
  }
  grid.addEventListener('click', function(e){
    var alvo = e.target.closest('.ch');
    if (!alvo) return;
    var canal = alvo.getAttribute('data-canal');
    if (!canal) return;
    tocar(canal);
  });
  document.getElementById('q').addEventListener('input', function(e){
    var v = e.target.value.toLowerCase().trim();
    document.querySelectorAll('.ch').forEach(function(el){
      var t = el.getAttribute('data-canal') || '';
      el.style.display = (!v || t.indexOf(v) !== -1) ? '' : 'none';
    });
  });
  player.on('error', function(){
    setTimeout(function(){
      var s = player.src();
      if (s && s.indexOf('/play/') !== -1){
        var c = s.split('/play/')[1].split('?')[0];
        player.src({ src: '/play/' + c + '?t=' + Date.now(), type:'application/x-mpegURL' });
        player.play().catch(function(){});
        setInfo(c, 'Reconectando...');
      }
    }, 1500);
  });
  var ultimo = 0, travado = null;
  setInterval(function(){
    if (player.paused() || player.readyState() < 2) { travado = null; return; }
    var t = player.currentTime();
    if (t === ultimo){
      if (!travado) travado = Date.now();
      else if (Date.now() - travado > 10000){
        travado = null;
        var s = player.src();
        if (s && s.indexOf('/play/') !== -1){
          var c = s.split('/play/')[1].split('?')[0];
          player.src({ src: '/play/' + c + '?t=' + Date.now(), type:'application/x-mpegURL' });
          player.play().catch(function(){});
          setInfo(c, 'Reconectando...');
        }
      }
    } else { ultimo = t; travado = null; }
  }, 2000);
</script>
</body>
</html>
"""

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
