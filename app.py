import os, re, time, threading
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

import requests as std_requests

app = Flask(__name__)
PORTA = int(os.environ.get("PORT", 10000))

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-8761-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

TS_CACHE = OrderedDict()
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 800
TS_CACHE_TEMPO = 120

CANAIS_FIXOS = [
    "espn","premiereclubes","tnt","telecinepipoca",
    "telecinefun","telecinepremium","space",
]

_SESSAO_GLOBAL = None
_SESSAO_LOCK = threading.Lock()

def get_sessao_persistente():
    global _SESSAO_GLOBAL
    with _SESSAO_LOCK:
        if _SESSAO_GLOBAL is None:
            if USE_CURL:
                try: _SESSAO_GLOBAL = ImpersonateSession.Session(impersonate="firefox133")
                except Exception: _SESSAO_GLOBAL = ImpersonateSession.Session()
            else:
                _SESSAO_GLOBAL = ImpersonateSession.Session()
                adapter = std_requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=200, max_retries=2)
                _SESSAO_GLOBAL.mount('https://', adapter)
                _SESSAO_GLOBAL.mount('http://', adapter)
        return _SESSAO_GLOBAL

def montar_url(canal):
    canal = canal.strip().lower()
    return f"https://f8umt2oop68t.sbs/live/secure/pHGsJJgoEUBc-K5ACe7Hws--gF0WDhHii_3tGSGwoq4/1789760848/1d256d1fe0127694/{canal}/index.m3u8"

def montar_referer(canal):
    return f"{ORIGIN_FIXO}/play/{canal.strip().lower()}.html"

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
    try:
        sess = get_sessao_persistente()
        r = sess.get(url, headers=h, timeout=8, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            return r, url
    except Exception: pass
    try:
        r = std_requests.get(url, headers=h, timeout=8, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            return r, url
    except Exception: pass
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
    for requester in [get_sessao_persistente(), std_requests]:
        try:
            r = requester.get(url_segmento, headers=h, timeout=6, verify=False)
            if r.status_code == 200:
                with TS_CACHE_LOCK:
                    if len(TS_CACHE) >= TS_CACHE_MAX:
                        TS_CACHE.popitem(last=False)
                    TS_CACHE[url_segmento] = (r.content, agora)
                return r.content, 200
            if r.status_code in (403,404):
                return None, r.status_code
        except Exception: pass
    return None, 502

HTML_PAGINA = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>MARCOS TV — Streaming ao Vivo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  :root{--purple:#6c5ce7;--purple2:#a29bfe;--purple3:#4834d4;--bg:#07070d;--bg2:#0e0f17;--bd:rgba(108,92,231,.18);--mut:#8b93a5;--live:#e63946}
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  html,body{height:100%;width:100%;overflow-x:hidden}
  body{font-family:'Inter',-apple-system,BlinkMacSystemFont,Arial,sans-serif;background:var(--bg);color:#fff;min-height:100vh;
    background-image:radial-gradient(ellipse 80% 50% at 50% -10%,rgba(108,92,231,.18),transparent 55%),
    radial-gradient(ellipse 60% 50% at 90% 110%,rgba(108,92,231,.08),transparent 55%);
    background-attachment:fixed;padding:14px;padding-bottom:40px}
  .app{width:100%;max-width:960px;margin:0 auto}
  .brand{display:flex;align-items:center;justify-content:center;gap:10px;margin:8px 0 18px;position:relative}
  .brand-logo{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--purple),var(--purple3));display:flex;align-items:center;justify-content:center;box-shadow:0 10px 30px rgba(108,92,231,.45),inset 0 1px 0 rgba(255,255,255,.3)}
  .brand-logo svg{width:26px;height:26px;fill:#fff}
  .brand-text{text-align:left;line-height:1.05}
  .brand-text h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(1.4em,5vw,1.9em);font-weight:700;letter-spacing:-.5px;color:#fff}
  .brand-text .sub{font-size:.68em;color:var(--purple2);letter-spacing:3px;font-weight:600;text-transform:uppercase;margin-top:2px}
  .live-pill{position:absolute;right:0;top:50%;transform:translateY(-50%);display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:20px;background:rgba(230,57,70,.12);border:1px solid rgba(230,57,70,.35);font-size:.65em;font-weight:800;color:#ff6673;letter-spacing:1px}
  .live-pill .dot{width:6px;height:6px;border-radius:50%;background:var(--live);box-shadow:0 0 8px var(--live);animation:pulse 1.4s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .player-card{background:linear-gradient(180deg,var(--bg2),var(--bg));border:1px solid var(--bd);border-radius:20px;padding:14px;box-shadow:0 30px 70px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.04)}
  .video-wrap{position:relative;border-radius:14px;overflow:hidden;background:#000}
  .video-js{width:100%;height:420px;background:#000}
  .video-js.vjs-fullscreen{width:100vw!important;height:100vh!important;top:0!important;left:0!important;position:fixed!important;border-radius:0!important;z-index:999999!important}
  .video-js.vjs-fullscreen video,.video-js.vjs-fullscreen .vjs-tech{width:100vw!important;height:100vh!important;object-fit:contain!important}
  .video-js .vjs-big-play-button{background:linear-gradient(135deg,var(--purple),var(--purple3))!important;border:none!important;width:70px!important;height:70px!important;line-height:70px!important;border-radius:50%!important;top:50%!important;left:50%!important;margin:-35px 0 0 -35px!important;box-shadow:0 15px 40px rgba(108,92,231,.5)!important}
  .video-js .vjs-big-play-button .vjs-icon-placeholder::before{font-size:34px!important;line-height:70px!important}
  .video-js .vjs-control-bar{background:linear-gradient(180deg,transparent,rgba(0,0,0,.9))!important;height:50px!important}
  .video-js .vjs-play-progress{background:linear-gradient(90deg,var(--purple),var(--purple2))!important}
  .video-js .vjs-load-progress{background:rgba(108,92,231,.2)!important}
  @media(max-width:640px){.video-js{height:220px}}
  .now-playing{display:flex;align-items:center;justify-content:space-between;padding:12px 4px 0;margin-top:6px}
  .now-playing .left{display:flex;align-items:center;gap:10px}
  .now-playing .cover{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,rgba(108,92,231,.3),rgba(162,155,254,.15));border:1px solid rgba(108,92,231,.4);display:flex;align-items:center;justify-content:center;font-weight:900;color:var(--purple2);font-size:14px;text-transform:uppercase;font-family:'Space Grotesk',sans-serif}
  .now-playing .txt .lbl{font-size:.62em;color:var(--mut);letter-spacing:1.5px;text-transform:uppercase;font-weight:700}
  .now-playing .txt .nm{font-size:.95em;font-weight:800;color:#fff;margin-top:1px;text-transform:capitalize}
  .now-playing .status-txt{font-size:.68em;font-weight:700;letter-spacing:.5px}
  .status-txt.ok{color:#00e701}
  .status-txt.err{color:#ff5566}
  .status-txt.loading{color:var(--purple2)}
  .controls{display:flex;gap:8px;margin-top:12px}
  .controls input{flex:1;background:var(--bg);border:1.5px solid var(--bd);color:#fff;padding:14px 16px;border-radius:12px;font-family:inherit;font-size:.9em;font-weight:500;outline:none;transition:.2s}
  .controls input:focus{border-color:var(--purple);box-shadow:0 0 0 3px rgba(108,92,231,.15)}
  .controls input::placeholder{color:#444}
  .btn-play{background:linear-gradient(135deg,var(--purple),var(--purple3));color:#fff;border:none;padding:14px 22px;border-radius:12px;font-family:inherit;font-weight:800;font-size:.85em;cursor:pointer;letter-spacing:.5px;display:flex;align-items:center;gap:8px;box-shadow:0 10px 25px rgba(108,92,231,.4);transition:.15s}
  .btn-play:active{transform:scale(.97)}
  .btn-play:disabled{opacity:.5;cursor:not-allowed}
  .btn-play svg{width:14px;height:14px;fill:#fff}
  .sec-title{display:flex;align-items:center;gap:8px;margin:24px 2px 12px}
  .sec-title .bar{width:3px;height:16px;border-radius:2px;background:linear-gradient(180deg,var(--purple),var(--purple3))}
  .sec-title h2{font-size:.85em;font-weight:800;letter-spacing:.5px;text-transform:uppercase}
  .sec-title .count{margin-left:auto;font-size:.7em;color:var(--mut);font-weight:600;padding:3px 10px;background:var(--bg2);border:1px solid var(--bd);border-radius:12px}
  .canais-fixos{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
  .canal-btn{background:linear-gradient(180deg,var(--bg2),var(--bg));border:1.5px solid var(--bd);border-radius:14px;padding:16px 8px;cursor:pointer;text-align:center;transition:.2s;position:relative;overflow:hidden}
  .canal-btn:hover{border-color:var(--purple);transform:translateY(-3px);box-shadow:0 15px 30px rgba(0,0,0,.5),0 0 0 1px rgba(108,92,231,.3)}
  .canal-btn:active{transform:scale(.97)}
  .canal-btn .ico{width:44px;height:44px;margin:0 auto 8px;border-radius:12px;background:linear-gradient(135deg,rgba(108,92,231,.25),rgba(162,155,254,.1));border:1px solid rgba(108,92,231,.35);display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.1em;color:var(--purple2);text-transform:uppercase}
  .canal-btn .nm{font-size:.72em;font-weight:800;color:#c9cfe0;letter-spacing:.8px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .canal-btn.ativo{border-color:var(--purple);background:linear-gradient(180deg,rgba(108,92,231,.18),rgba(108,92,231,.04));box-shadow:0 0 25px rgba(108,92,231,.35),inset 0 0 0 1px rgba(162,155,254,.3)}
  .canal-btn.ativo .ico{background:linear-gradient(135deg,var(--purple),var(--purple3));color:#fff;border-color:transparent}
  .canal-btn.ativo .nm{color:#fff}
  .footer{text-align:center;color:#333;font-size:.7em;margin-top:32px;letter-spacing:.5px;padding-bottom:20px}
  .footer b{color:var(--purple2);font-weight:700}
</style>
</head>
<body>
<div class="app">
  <div class="brand">
    <div class="brand-logo">
      <svg viewBox="0 0 24 24"><path d="M21 6h-7.6l-1.3-2.5c-.2-.3-.5-.5-.9-.5H3c-1.1 0-2 .9-2 2v13c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-9 11c-2.8 0-5-2.2-5-5s2.2-5 5-5 5 2.2 5 5-2.2 5-5 5z"/></svg>
    </div>
    <div class="brand-text">
      <h1>MARCOS TV</h1>
      <div class="sub">Streaming ao vivo</div>
    </div>
    <div class="live-pill"><div class="dot"></div>AO VIVO</div>
  </div>

  <div class="player-card">
    <div class="video-wrap">
      <video id="player" class="video-js" controls playsinline preload="auto"></video>
    </div>
    <div class="now-playing">
      <div class="left">
        <div class="cover" id="nowCover">?</div>
        <div class="txt">
          <div class="lbl">Assistindo agora</div>
          <div class="nm" id="nowNome">Nenhum canal</div>
        </div>
      </div>
      <div class="status-txt" id="status">Aguardando...</div>
    </div>
    <div class="controls">
      <input id="canal" type="text" placeholder="Digite o nome do canal..." autocomplete="off">
      <button id="btnPlay" class="btn-play" onclick="tocar()">
        <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>PLAY
      </button>
    </div>
  </div>

  <div class="sec-title">
    <div class="bar"></div>
    <h2>Canais Disponíveis</h2>
    <span class="count">{{ canais|length }} canais</span>
  </div>

  <div class="canais-fixos">
    {% for c in canais %}
    <div class="canal-btn" data-canal="{{ c }}" onclick="tocarFixo('{{ c }}', this)">
      <div class="ico">{{ c[0] }}</div>
      <div class="nm">{{ c }}</div>
    </div>
    {% endfor %}
  </div>

  <div class="footer">© 2026 <b>MARCOS TV</b> — Todos os direitos reservados</div>
</div>
<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player=videojs('player',{controls:true,autoplay:false,preload:'auto',liveui:true,
  html5:{vhs:{overrideNative:true,maxBufferLength:40,maxMaxBufferLength:80,liveSyncDuration:8,
  liveMaxLatencyDuration:25,enableLowInitialPlaylist:true,smoothQualityChange:true,fastQualityChange:true,handlePartialData:true}}});
var statusEl=document.getElementById('status'),nowNome=document.getElementById('nowNome'),
    nowCover=document.getElementById('nowCover'),btn=document.getElementById('btnPlay'),
    input=document.getElementById('canal');
player.on('fullscreenchange',function(){
  if(player.isFullscreen()){try{if(screen.orientation&&screen.orientation.lock)screen.orientation.lock('landscape').catch(function(){});}catch(e){}}
  else{try{if(screen.orientation&&screen.orientation.unlock)screen.orientation.unlock().catch(function(){});}catch(e){}}
});
function setStatus(m,t){statusEl.className='status-txt'+(t?' '+t:'');statusEl.innerText=m||''}
function marcarAtivo(el){document.querySelectorAll('.canal-btn').forEach(function(b){b.classList.remove('ativo')});if(el)el.classList.add('ativo')}
function tocarFixo(c,el){marcarAtivo(el);input.value=c;tocar()}
function tocar(){
  var c=input.value.trim().toLowerCase();
  if(!c){setStatus('Digite o nome do canal','err');input.focus();return}
  nowNome.innerText=c;nowCover.innerText=c[0].toUpperCase();
  setStatus('Carregando...','loading');btn.disabled=true;
  fetch('/testar/'+encodeURIComponent(c)).then(r=>r.json()).then(d=>{
    btn.disabled=false;
    if(d.ok){
      setStatus('● Ao vivo','ok');
      player.pause();player.error(null);
      player.src({src:'/play/'+encodeURIComponent(c)+'?t='+Date.now(),type:'application/x-mpegURL'});
      player.load();
      player.play().catch(function(e){setStatus('Erro ao reproduzir','err')});
    } else setStatus('Canal indisponível','err');
  }).catch(e=>{btn.disabled=false;setStatus('Erro de conexão','err')});
}
input.addEventListener('keydown',function(e){if(e.key==='Enter')tocar()});
</script>
</body>
</html>
'''

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin']='*'
    r.headers['Access-Control-Allow-Headers']='*'
    return r

@app.route('/')
def index():
    return render_template_string(HTML_PAGINA, canais=CANAIS_FIXOS)

@app.route('/testar/<canal>')
def testar(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return {"ok": False, "msg": "Nome inválido"}
    r, _ = buscar_m3u8(canal)
    if r: return {"ok": True}
    return {"ok": False, "msg": "Canal '" + canal + "' indisponível"}

@app.route('/play/<canal>')
def play(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal):
        return "Nome inválido", 400
    r, url_orig = buscar_m3u8(canal)
    if not r: return "Canal não encontrado", 404
    base = getattr(r, 'url', url_orig)
    linhas = []
    for l in r.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{ep}?url={quote(abs_url, safe='')}&canal={canal}")
        else: linhas.append(ls)
    return Response("\n".join(linhas), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'})

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal: return "Faltam parâmetros", 400
    h = obter_headers(canal); r = None
    try: r = get_sessao_persistente().get(target, headers=h, timeout=8, verify=False)
    except Exception: pass
    if not r or r.status_code != 200:
        try: r = std_requests.get(target, headers=h, timeout=8, verify=False)
        except Exception as e: return f"Erro: {e}", 500
    if r.status_code != 200: return f"upstream {r.status_code}", r.status_code
    base = getattr(r, 'url', target)
    linhas = []
    for l in r.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{ep}?url={quote(abs_url, safe='')}&canal={canal}")
        else: linhas.append(ls)
    return Response("\n".join(linhas), status=200, headers={
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'})

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    canal = request.args.get('canal', '')
    if not target or not canal: return "Faltam parâmetros", 400
    conteudo, status = buscar_segmento(target, canal)
    if conteudo is None: return f"Erro segmento {status}", status
    return Response(conteudo, status=200, headers={
        'Content-Type': 'video/mp2t',
        'Content-Length': str(len(conteudo)),
        'Cache-Control': 'public, max-age=120',
        'Accept-Ranges': 'bytes',
        'Access-Control-Allow-Origin': '*'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
