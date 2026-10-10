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
    {"nome":"espn","img":"https://a1.espncdn.com/combiner/i?img=%2Fi%2Fespn%2Fespn_logos%2Fespn_red.png"},
    {"nome":"premiereclubes","img":"https://s3.glbimg.com/v1/AUTH_f486c675dfaf4c6e96c25f0c21f85eb5/prod/home-share-1b75cdaa.png"},
    {"nome":"tnt","img":"https://cdn.telaviva.com.br/wp-content/uploads/2021/01/tnt-.jpg"},
    {"nome":"telecinepipoca","img":"https://static.wikia.nocookie.net/tvpediabrasil/images/2/22/Tcpipocab.jpg/revision/latest?cb=20200817021740&path-prefix=pt-br"},
    {"nome":"telecinefun","img":"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSdwYXXJGHWCEKu6CHe5UoTaNsPQH-nqyw52ZScjT3WGQ&s=10"},
    {"nome":"telecinepremium","img":"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcStyWsptODGUYXW-QHPSH3ZHHFf1vBZ4KUiUs8QeA5JIg&s=10"},
    {"nome":"space","img":"https://static.wikia.nocookie.net/tvpediabrasil/images/4/4f/Space.jpg/revision/latest?cb=20180422160945&path-prefix=pt-br"},
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
<meta name="theme-color" content="#f5f7fb">
<title>MARCOS TV — Streaming ao Vivo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
:root{
  --p1:#5b4bff;--p2:#8b7dff;--p3:#3a2bd9;
  --acc:#00c98a;--live:#ff3355;
  --bg:#f5f7fb;--bg2:#ffffff;--bg3:#eef1f8;
  --bd:#e0e5f0;
  --txt:#0a0d1f;--mut:#6b7391;--mut2:#98a0bb;
  --sh:0 4px 20px rgba(30,40,90,.08);
  --sh2:0 12px 40px rgba(30,40,90,.14);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;width:100%;overflow-x:hidden}
body{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,Arial,sans-serif;
  background:var(--bg);color:var(--txt);min-height:100vh;
  background-image:
    radial-gradient(ellipse 70% 50% at 50% -10%,rgba(91,75,255,.10),transparent 60%),
    radial-gradient(ellipse 60% 40% at 100% 100%,rgba(139,125,255,.06),transparent 60%);
  background-attachment:fixed;
  zoom:81%;
}
@supports not (zoom: 1){
  body{transform:scale(.81);transform-origin:top center;width:123.45%}
}
.app{width:100%;max-width:1180px;margin:0 auto;padding:22px 20px 70px}

.header{display:flex;align-items:center;gap:16px;padding:16px 20px;margin-bottom:22px;background:var(--bg2);border:1px solid var(--bd);border-radius:22px;box-shadow:var(--sh)}
.logo{width:56px;height:56px;border-radius:18px;flex-shrink:0;background:linear-gradient(135deg,var(--p1),var(--p3));display:flex;align-items:center;justify-content:center;box-shadow:0 10px 24px rgba(91,75,255,.35)}
.logo svg{width:32px;height:32px;fill:#fff}
.titulo{flex:1;min-width:0}
.titulo h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(1.7em,4.5vw,2.3em);font-weight:700;letter-spacing:-1px;line-height:1;color:var(--txt)}
.titulo .sub{font-size:.72em;color:var(--mut);letter-spacing:4px;font-weight:700;text-transform:uppercase;margin-top:4px}
.live-badge{display:flex;align-items:center;gap:7px;padding:10px 16px;background:rgba(255,51,85,.08);border:1.5px solid rgba(255,51,85,.25);border-radius:20px;flex-shrink:0}
.live-badge .dot{width:8px;height:8px;border-radius:50%;background:var(--live);box-shadow:0 0 10px var(--live);animation:blink 1.4s infinite}
.live-badge span{font-size:.72em;font-weight:800;color:var(--live);letter-spacing:1.5px;text-transform:uppercase}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}

.player-card{background:var(--bg2);border:1px solid var(--bd);border-radius:26px;padding:18px;margin-bottom:26px;box-shadow:var(--sh2);position:relative;overflow:hidden}
.player-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,var(--p1),var(--p2),transparent)}
.video-wrap{position:relative;border-radius:18px;overflow:hidden;background:#000;box-shadow:0 12px 40px rgba(0,0,0,.25)}
.video-js{width:100%;height:480px;background:#000}
.video-js.vjs-fullscreen{width:100vw!important;height:100vh!important;top:0!important;left:0!important;position:fixed!important;border-radius:0!important;z-index:999999!important}
.video-js.vjs-fullscreen video,.video-js.vjs-fullscreen .vjs-tech{width:100vw!important;height:100vh!important;object-fit:contain!important}
.video-js .vjs-big-play-button{background:linear-gradient(135deg,var(--p1),var(--p3))!important;border:none!important;width:84px!important;height:84px!important;line-height:84px!important;border-radius:50%!important;top:50%!important;left:50%!important;margin:-42px 0 0 -42px!important;box-shadow:0 20px 50px rgba(91,75,255,.5),0 0 0 14px rgba(91,75,255,.12)!important}
.video-js .vjs-big-play-button .vjs-icon-placeholder::before{font-size:40px!important;line-height:84px!important}
.video-js .vjs-control-bar{background:linear-gradient(180deg,transparent,rgba(0,0,0,.92))!important;height:58px!important;padding:0 10px!important}
.video-js .vjs-play-progress{background:linear-gradient(90deg,var(--p1),var(--p2))!important}
.video-js .vjs-load-progress{background:rgba(91,75,255,.3)!important}
@media(max-width:750px){.video-js{height:270px}}

.now-bar{display:flex;align-items:center;justify-content:space-between;padding:18px 6px 6px;gap:14px}
.now-left{display:flex;align-items:center;gap:14px;min-width:0}
.now-cover{width:52px;height:52px;border-radius:14px;flex-shrink:0;background:#fff;border:1.5px solid var(--bd);display:flex;align-items:center;justify-content:center;padding:6px;overflow:hidden}
.now-cover img{width:100%;height:100%;object-fit:contain}
.now-cover span{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.5em;color:var(--p1);text-transform:uppercase}
.now-txt{min-width:0}
.now-txt .lbl{font-size:.66em;color:var(--mut);letter-spacing:2px;font-weight:800;text-transform:uppercase}
.now-txt .nm{font-size:1.15em;font-weight:800;color:var(--txt);margin-top:2px;text-transform:capitalize;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.now-status{font-size:.78em;font-weight:800;letter-spacing:.5px;padding:8px 14px;border-radius:20px;flex-shrink:0;transition:.25s}
.now-status.ok{color:var(--acc);background:rgba(0,201,138,.1);border:1.5px solid rgba(0,201,138,.3)}
.now-status.err{color:var(--live);background:rgba(255,51,85,.08);border:1.5px solid rgba(255,51,85,.25)}
.now-status.loading{color:var(--p1);background:rgba(91,75,255,.08);border:1.5px solid rgba(91,75,255,.25)}

.search-bar{display:flex;gap:10px;margin-top:16px}
.search-bar input{flex:1;background:var(--bg3);border:1.5px solid var(--bd);color:var(--txt);padding:16px 20px;border-radius:14px;font-family:inherit;font-size:.95em;font-weight:500;outline:none;transition:.25s}
.search-bar input::placeholder{color:var(--mut2)}
.search-bar input:focus{border-color:var(--p1);background:#fff;box-shadow:0 0 0 4px rgba(91,75,255,.12)}
.btn-play{background:linear-gradient(135deg,var(--p1),var(--p3));color:#fff;border:none;padding:16px 28px;border-radius:14px;font-family:inherit;font-weight:800;font-size:.9em;cursor:pointer;letter-spacing:.8px;display:flex;align-items:center;gap:9px;box-shadow:0 10px 25px rgba(91,75,255,.3);transition:.2s;text-transform:uppercase}
.btn-play:hover{transform:translateY(-2px);box-shadow:0 15px 32px rgba(91,75,255,.4)}
.btn-play:active{transform:scale(.97)}
.btn-play:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn-play svg{width:16px;height:16px;fill:#fff}

.sec-head{display:flex;align-items:center;gap:10px;margin:30px 4px 16px}
.sec-head .bar{width:4px;height:22px;border-radius:2px;background:linear-gradient(180deg,var(--p1),var(--p3))}
.sec-head h2{font-size:1em;font-weight:800;letter-spacing:.8px;text-transform:uppercase;color:var(--txt)}
.sec-head .count{margin-left:auto;font-size:.78em;color:var(--mut);font-weight:700;padding:6px 14px;background:var(--bg2);border:1px solid var(--bd);border-radius:14px}

.canais-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
.canal{background:var(--bg2);border:1.5px solid var(--bd);border-radius:18px;padding:22px 12px;cursor:pointer;text-align:center;transition:.25s cubic-bezier(.2,.8,.2,1);position:relative;overflow:hidden;box-shadow:var(--sh)}
.canal:hover{border-color:var(--p1);transform:translateY(-5px);box-shadow:var(--sh2),0 0 0 1px rgba(91,75,255,.2)}
.canal:active{transform:translateY(-2px) scale(.98)}
.canal .ico{width:64px;height:64px;margin:0 auto 12px;border-radius:16px;background:#fff;border:1.5px solid var(--bd);display:flex;align-items:center;justify-content:center;padding:8px;overflow:hidden;transition:.25s}
.canal .ico img{width:100%;height:100%;object-fit:contain;display:block}
.canal .ico span{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.5em;color:var(--p1);text-transform:uppercase}
.canal .nm{font-size:.82em;font-weight:800;color:var(--txt);letter-spacing:.8px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.canal.ativo{border-color:var(--p1);background:linear-gradient(180deg,rgba(91,75,255,.06),#fff);box-shadow:0 8px 30px rgba(91,75,255,.25),inset 0 0 0 1px rgba(91,75,255,.15)}
.canal.ativo .ico{border-color:rgba(91,75,255,.35);box-shadow:0 8px 20px rgba(91,75,255,.18)}

.footer{text-align:center;color:var(--mut2);font-size:.78em;margin-top:46px;letter-spacing:1px;padding-bottom:20px;font-weight:600}
.footer b{color:var(--p1);font-weight:800}
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
        <div class="now-cover" id="nowCover"><span>?</span></div>
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
    <div class="canal" data-canal="{{ c.nome }}" onclick="tocarFixo('{{ c.nome }}', this)">
      <div class="ico">
        {% if c.img %}<img src="{{ c.img }}" alt="{{ c.nome }}">{% else %}<span>{{ c.nome[0] }}</span>{% endif %}
      </div>
      <div class="nm">{{ c.nome }}</div>
    </div>
    {% endfor %}
  </div>

  <div class="footer">© 2026 <b>MARCOS TV</b> — Todos os direitos reservados</div>
</div>
<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var CANAIS = {{ canais|tojson }};
function achaImg(nome){
  var n = (nome||'').toLowerCase();
  for(var i=0;i<CANAIS.length;i++){
    if(CANAIS[i].nome===n && CANAIS[i].img) return CANAIS[i].img;
  }
  return '';
}
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
var nowNome = document.getElementById('nowNome');
var nowCover = document.getElementById('nowCover');
var btn = document.getElementById('btnPlay');
var input = document.getElementById('canal');

function setStatus(m,t){ statusEl.className='now-status'+(t?' '+t:''); statusEl.innerText=m||''; }
function marcarAtivo(el){ document.querySelectorAll('.canal').forEach(function(b){ b.classList.remove('ativo'); }); if(el) el.classList.add('ativo'); }
function atualizaNow(nome){
  nowNome.innerText = nome;
  var img = achaImg(nome);
  if(img){ nowCover.innerHTML = '<img src="'+img+'" alt="'+nome+'">'; }
  else{ nowCover.innerHTML = '<span>'+nome.charAt(0).toUpperCase()+'</span>'; }
}
function tocarFixo(c,el){ marcarAtivo(el); input.value = c; tocar(); }

function tocar(){
  var c = input.value.trim().toLowerCase();
  if(!c){ setStatus('Digite um canal','err'); input.focus(); return; }
  atualizaNow(c);
  setStatus('Carregando...','loading');
  btn.disabled = true;
  fetch('/testar/' + encodeURIComponent(c))
    .then(function(r){ return r.json(); })
    .then(function(d){
      btn.disabled = false;
      if(d.ok){
        setStatus('● Ao vivo','ok');
        player.pause();
        player.error(null);
        player.src({ src: '/play/' + encodeURIComponent(c) + '?t=' + Date.now(), type: 'application/x-mpegURL' });
        player.load();
        player.play().catch(function(){ setStatus('Erro ao reproduzir','err'); });
      } else {
        setStatus('Indisponível','err');
      }
    })
    .catch(function(){ btn.disabled = false; setStatus('Erro de conexão','err'); });
}
input.addEventListener('keydown', function(e){ if(e.key==='Enter') tocar(); });
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
