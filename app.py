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
CANAIS_FIXOS = ["espn","premiereclubes","tnt","telecinepipoca","telecinefun","telecinepremium","space"]
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
    return {"User-Agent":USER_AGENT,"Accept":"*/*","Accept-Language":"pt-BR,pt;q=0.9,en;q=0.8","Origin":ORIGIN_FIXO,"Referer":montar_referer(canal),"Cookie":COOKIE_FIXO,"Connection":"keep-alive"}

def buscar_m3u8(canal):
    url = montar_url(canal); h = obter_headers(canal)
    try:
        r = get_sessao_persistente().get(url, headers=h, timeout=8, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text): return r, url
    except Exception: pass
    try:
        r = std_requests.get(url, headers=h, timeout=8, verify=False)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text): return r, url
    except Exception: pass
    return None, None

def buscar_segmento(url_segmento, canal):
    agora = time.time()
    with TS_CACHE_LOCK:
        if url_segmento in TS_CACHE:
            dados, t = TS_CACHE[url_segmento]
            if agora - t < TS_CACHE_TEMPO:
                TS_CACHE.move_to_end(url_segmento); return dados, 200
            else: del TS_CACHE[url_segmento]
    h = obter_headers(canal)
    for requester in [get_sessao_persistente(), std_requests]:
        try:
            r = requester.get(url_segmento, headers=h, timeout=6, verify=False)
            if r.status_code == 200:
                with TS_CACHE_LOCK:
                    if len(TS_CACHE) >= TS_CACHE_MAX: TS_CACHE.popitem(last=False)
                    TS_CACHE[url_segmento] = (r.content, agora)
                return r.content, 200
            if r.status_code in (403,404): return None, r.status_code
        except Exception: pass
    return None, 502

HTML_PAGINA = r'''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<meta name="theme-color" content="#05050a">
<title>MARCOS TV — Streaming ao Vivo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
:root{--p1:#7c5cff;--p2:#a78bfa;--p3:#5b21b6;--acc:#00e5a0;--live:#ff2d55;--bg:#05050a;--bd:rgba(124,92,255,.14);--bd2:rgba(124,92,255,.32);--mut:#7a7f95}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;width:100%;overflow-x:hidden}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,Arial,sans-serif;background:var(--bg);color:#f0f0f5;min-height:100vh;
background-image:radial-gradient(ellipse 90% 60% at 50% -20%,rgba(124,92,255,.22),transparent 55%),radial-gradient(ellipse 70% 50% at 100% 110%,rgba(0,229,160,.05),transparent 55%),radial-gradient(ellipse 60% 40% at 0% 90%,rgba(124,92,255,.08),transparent 55%);
background-attachment:fixed;zoom:81%}
@supports not (zoom: 1){body{transform:scale(.81);transform-origin:top center;width:123.45%}}
.app{width:100%;max-width:1100px;margin:0 auto;padding:20px 18px 60px}
.header{display:flex;align-items:center;gap:14px;padding:14px 18px;margin-bottom:18px;background:linear-gradient(135deg,rgba(18,18,28,.9),rgba(10,10,18,.85));border:1px solid var(--bd);border-radius:20px;backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);box-shadow:0 10px 40px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.04)}
.logo{width:52px;height:52px;border-radius:16px;flex-shrink:0;background:linear-gradient(135deg,var(--p1),var(--p3));display:flex;align-items:center;justify-content:center;box-shadow:0 12px 32px rgba(124,92,255,.45),inset 0 1px 0 rgba(255,255,255,.3);position:relative}
.logo::after{content:'';position:absolute;inset:-3px;border-radius:18px;background:linear-gradient(135deg,var(--p1),transparent 60%);opacity:.5;filter:blur(10px);z-index:-1}
.logo svg{width:30px;height:30px;fill:#fff}
.titulo{flex:1;min-width:0}
.titulo h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(1.6em,4.5vw,2.2em);font-weight:700;letter-spacing:-1px;line-height:1;background:linear-gradient(135deg,#fff,var(--p2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.titulo .sub{font-size:.72em;color:var(--mut);letter-spacing:4px;font-weight:600;text-transform:uppercase;margin-top:4px}
.live-badge{display:flex;align-items:center;gap:7px;padding:9px 14px;background:rgba(255,45,85,.1);border:1px solid rgba(255,45,85,.35);border-radius:20px;flex-shrink:0}
.live-badge .dot{width:7px;height:7px;border-radius:50%;background:var(--live);box-shadow:0 0 10px var(--live);animation:blink 1.4s infinite}
.live-badge span{font-size:.7em;font-weight:800;color:#ff5577;letter-spacing:1.5px;text-transform:uppercase}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.player-card{background:linear-gradient(180deg,rgba(18,18,28,.72),rgba(8,8,14,.85));border:1px solid var(--bd);border-radius:24px;padding:16px;margin-bottom:22px;backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);box-shadow:0 30px 70px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.05);position:relative;overflow:hidden}
.player-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--p1),transparent);opacity:.6}
.video-wrap{position:relative;border-radius:16px;overflow:hidden;background:#000;box-shadow:0 20px 50px rgba(0,0,0,.6)}
.video-js{width:100%;height:460px;background:#000}
.video-js.vjs-fullscreen{width:100vw!important;height:100vh!important;top:0!important;left:0!important;position:fixed!important;border-radius:0!important;z-index:999999!important}
.video-js.vjs-fullscreen video,.video-js.vjs-fullscreen .vjs-tech{width:100vw!important;height:100vh!important;object-fit:contain!important}
.video-js .vjs-big-play-button{background:linear-gradient(135deg,var(--p1),var(--p3))!important;border:none!important;width:80px!important;height:80px!important;line-height:80px!important;border-radius:50%!important;top:50%!important;left:50%!important;margin:-40px 0 0 -40px!important;box-shadow:0 20px 50px rgba(124,92,255,.55),0 0 0 12px rgba(124,92,255,.12)!important}
.video-js .vjs-big-play-button .vjs-icon-placeholder::before{font-size:38px!important;line-height:80px!important}
.video-js .vjs-control-bar{background:linear-gradient(180deg,transparent,rgba(0,0,0,.95))!important;height:56px!important;padding:0 8px!important}
.video-js .vjs-play-progress{background:linear-gradient(90deg,var(--p1),var(--p2))!important}
.video-js .vjs-load-progress{background:rgba(124,92,255,.25)!important}
@media(max-width:700px){.video-js{height:260px}}
.now-bar{display:flex;align-items:center;justify-content:space-between;padding:14px 6px 4px;gap:12px}
.now-left{display:flex;align-items:center;gap:12px;min-width:0}
.now-cover{width:46px;height:46px;border-radius:12px;flex-shrink:0;background:linear-gradient(135deg,rgba(124,92,255,.35),rgba(167,139,250,.12));border:1px solid rgba(124,92,255,.45);display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.3em;color:var(--p2);text-transform:uppercase}
.now-txt{min-width:0}
.now-txt .lbl{font-size:.65em;color:var(--mut);letter-spacing:2px;font-weight:700;text-transform:uppercase}
.now-txt .nm{font-size:1.05em;font-weight:800;color:#fff;margin-top:2px;text-transform:capitalize;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.now-status{font-size:.75em;font-weight:800;letter-spacing:.5px;padding:6px 12px;border-radius:20px;flex-shrink:0}
.now-status.ok{color:var(--acc);background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.3)}
.now-status.err{color:#ff5566;background:rgba(255,85,102,.1);border:1px solid rgba(255,85,102,.3)}
.now-status.loading{color:var(--p2);background:rgba(124,92,255,.12);border:1px solid rgba(124,92,255,.3)}
.search-bar{display:flex;gap:10px;margin-top:14px}
.search-bar input{flex:1;background:rgba(5,5,10,.6);border:1.5px solid var(--bd);color:#fff;padding:15px 18px;border-radius:14px;font-family:inherit;font-size:.95em;font-weight:500;outline:none;transition:.25s}
.search-bar input::placeholder{color:#3a3f52}
.search-bar input:focus{border-color:var(--p1);box-shadow:0 0 0 4px rgba(124,92,255,.15);background:rgba(5,5,10,.85)}
.btn-play{background:linear-gradient(135deg,var(--p1),var(--p3));color:#fff;border:none;padding:15px 26px;border-radius:14px;font-family:inherit;font-weight:800;font-size:.9em;cursor:pointer;letter-spacing:.8px;display:flex;align-items:center;gap:9px;box-shadow:0 12px 28px rgba(124,92,255,.4),inset 0 1px 0 rgba(255,255,255,.2);transition:.2s;text-transform:uppercase}
.btn-play:hover{transform:translateY(-1px);box-shadow:0 15px 35px rgba(124,92,255,.55)}
.btn-play:active{transform:scale(.97)}
.btn-play:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn-play svg{width:15px;height:15px;fill:#fff}
.sec-head{display:flex;align-items:center;gap:10px;margin:28px 4px 14px}
.sec-head .bar{width:4px;height:20px;border-radius:2px;background:linear-gradient(180deg,var(--p1),var(--p3));box-shadow:0 0 12px rgba(124,92,255,.6)}
.sec-head h2{font-size:.95em;font-weight:800;letter-spacing:.8px;text-transform:uppercase}
.sec-head .count{margin-left:auto;font-size:.75em;color:var(--mut);font-weight:700;padding:5px 12px;background:rgba(18,18,28,.6);border:1px solid var(--bd);border-radius:14px}
.canais-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}
.canal{background:linear-gradient(180deg,rgba(18,18,28,.9),rgba(8,8,14,.9));border:1.5px solid var(--bd);border-radius:16px;padding:18px 10px;cursor:pointer;text-align:center;transition:.25s cubic-bezier(.2,.8,.2,1);position:relative;overflow:hidden}
.canal::before{content:'';position:absolute;inset:0;background:radial-gradient(circle at 50% -20%,rgba(124,92,255,.2),transparent 65%);opacity:0;transition:.3s}
.canal:hover::before{opacity:1}
.canal:hover{border-color:var(--bd2);transform:translateY(-4px);box-shadow:0 20px 40px rgba(0,0,0,.55),0 0 0 1px rgba(124,92,255,.25)}
.canal:active{transform:translateY(-2px) scale(.98)}
.canal .ico{width:52px;height:52px;margin:0 auto 10px;border-radius:14px;background:linear-gradient(135deg,rgba(124,92,255,.28),rgba(167,139,250,.08));border:1px solid rgba(124,92,255,.35);display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.35em;color:var(--p2);text-transform:uppercase}
.canal .nm{font-size:.8em;font-weight:800;color:#c9cfe0;letter-spacing:.8px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.canal.ativo{border-color:var(--p1);background:linear-gradient(180deg,rgba(124,92,255,.18),rgba(124,92,255,.02));box-shadow:0 0 30px rgba(124,92,255,.4),inset 0 0 0 1px rgba(167,139,250,.35)}
.canal.ativo .ico{background:linear-gradient(135deg,var(--p1),var(--p3));color:#fff;border-color:transparent;box-shadow:0 10px 25px rgba(124,92,255,.5)}
.canal.ativo .nm{color:#fff}
.footer{text-align:center;color:#2e3240;font-size:.75em;margin-top:40px;letter-spacing:1px;padding-bottom:20px;font-weight:600}
.footer b{color:var(--p2);font-weight:800;background:linear-gradient(135deg,var(--p2),var(--p1));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="logo"><svg viewBox="0 0 24 24"><path d="M21 6h-7.6l-1.3-2.5c-.2-.3-.5-.5-.9-.5H3c-1.1 0-2 .9-2 2v13c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-9 11c-2.8 0-5-2.2-5-5s2.2-5 5-5 5 2.2 5 5-2.2 5-5 5z"/></svg></div>
    <div class="titulo"><h1>MARCOS TV</h1><div class="sub">Streaming ao vivo</div></div>
    <div class="live-badge"><div class="dot"></div><span>Ao vivo</span></div>
  </div>
  <div class="player-card">
    <div class="video-wrap"><video id="player" class="video-js" controls playsinline preload="auto"></video></div>
    <div class="now-bar">
      <div class="now-left">
        <div class="now-cover" id="nowCover">?</div>
        <div class="now-txt"><div class="lbl">Assistindo agora</div><div class="nm" id="nowNome">Nenhum canal</div></div>
      </div>
      <div class="now-status loading" id="status">Aguardando...</div>
    </div>
    <div class="search-bar">
      <input id="canal" type="text" placeholder="Digite o nome do canal..." autocomplete="off">
      <button id="btnPlay" class="btn-play" onclick="tocar()"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>Play</button>
    </div>
  </div>
  <div class="sec-head"><div class="bar"></div><h2>Canais Disponíveis</h2><span class="count">{{ canais|length }} canais</span></div>
  <div class="canais-grid">
    {% for c in canais %}
    <div class="canal" data-canal="{{ c }}" onclick="tocarFixo('{{ c }}', this)">
      <div class="ico">{{ c[0] }}</div><div class="nm">{{ c }}</div>
    </div>
    {% endfor %}
  </div>
  <div class="footer">© 2026 <b>MARCOS TV</b> — Todos os direitos reservados</div>
</div>
<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player=videojs('player',{controls:true,autoplay:false,preload:'auto',liveui:true,html5:{vhs:{overrideNative:true,maxBufferLength:40,maxMaxBufferLength:80,liveSyncDuration:8,liveMaxLatencyDuration:25,enableLowInitialPlaylist:true,smoothQualityChange:true,fastQualityChange:true,handlePartialData:true}}});
var statusEl=document.getElementById('status'),nowNome=document.getElementById('nowNome'),nowCover=document.getElementById('nowCover'),btn=document.getElementById('btnPlay'),input=document.getElementById('canal');
player.on('fullscreenchange',function(){if(player.isFullscreen()){try{if(screen.orientation&&screen.orientation.lock)screen.orientation.lock('landscape').catch(function(){});}catch(e){}}else{try{if(screen.orientation&&screen.orientation.unlock)screen.orientation.unlock().catch(function(){});}catch(e){}}});
function setStatus(m,t){statusEl.className='now-status'+(t?' '+t:'');statusEl.innerText=m||''}
function marcarAtivo(el){document.querySelectorAll('.canal').forEach(function(b){b.classList.remove('ativo')});if(el)el.classList.add('ativo')}
function tocarFixo(c,el){marcarAtivo(el);input.value=c;tocar()}
function tocar(){
  var c=input.value.trim().toLowerCase();
  if(!c){setStatus('Digite um canal','err');input.focus();return}
  nowNome.innerText=c;nowCover.innerText=c[0].toUpperCase();setStatus('Carregando...','loading');btn.disabled=true;
  fetch('/testar/'+encodeURIComponent(c)).then(r=>r.json()).then(d=>{
    btn.disabled=false;
    if(d.ok){setStatus('● Ao vivo','ok');player.pause();player.error(null);player.src({src:'/play/'+encodeURIComponent(c)+'?t='+Date.now(),type:'application/x-mpegURL'});player.load();player.play().catch(function(e){setStatus('Erro ao reproduzir','err')});}
    else setStatus('Indisponível','err');
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
    if not re.match(r'^[a-z0-9_\-]+$', canal): return {"ok": False, "msg": "Nome inválido"}
    r, _ = buscar_m3u8(canal)
    if r: return {"ok": True}
    return {"ok": False, "msg": "Canal indisponível"}

@app.route('/play/<canal>')
def play(canal):
    canal = canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$', canal): return "Nome inválido", 400
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
    return Response("\n".join(linhas), status=200, headers={'Content-Type':'application/vnd.apple.mpegurl','Access-Control-Allow-Origin':'*','Cache-Control':'no-cache'})

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url','')); canal = request.args.get('canal','')
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
    return Response("\n".join(linhas), status=200, headers={'Content-Type':'application/vnd.apple.mpegurl','Access-Control-Allow-Origin':'*','Cache-Control':'no-cache'})

@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url','')); canal = request.args.get('canal','')
    if not target or not canal: return "Faltam parâmetros", 400
    conteudo, status = buscar_segmento(target, canal)
    if conteudo is None: return f"Erro segmento {status}", status
    return Response(conteudo, status=200, headers={'Content-Type':'video/mp2t','Content-Length':str(len(conteudo)),'Cache-Control':'public, max-age=120','Accept-Ranges':'bytes','Access-Control-Allow-Origin':'*'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
