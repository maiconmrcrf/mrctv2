import os, re, json, time, threading
import urllib3
from collections import OrderedDict
from datetime import datetime
from flask import Flask, Response, request, render_template_string, jsonify
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VISITAS_FILE = os.path.join(BASE_DIR, "visitas.json")
BUSCAS_FILE  = os.path.join(BASE_DIR, "buscas.json")

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:155.0) Gecko/155.0 Firefox/155.0"
COOKIE_FIXO = "bitmovin_analytics_uuid=a07b3c21-c8bc-4692-876b-53ffa4df341f"
ORIGIN_FIXO = "https://bolodechocolate.fit"

ADMIN_SENHA = "temple2026"

# ====== CACHE ======
TS_CACHE = OrderedDict()
TS_CACHE_LOCK = threading.Lock()
TS_CACHE_MAX = 800
TS_CACHE_TEMPO = 120

# ====== ASSISTINDO AGORA ======
ASSISTINDO = {}   # ip -> {canal, quando}
ASSISTINDO_LOCK = threading.Lock()

# ====== CANAIS ======
CANAIS_FIXOS = [
    "espn","premiereclubes","tnt","telecinepipoca",
    "telecinefun","telecinepremium","space",
]

_SESSAO_GLOBAL = None
_SESSAO_LOCK = threading.Lock()

def ler_json(c, p):
    if not os.path.exists(c): return p
    try:
        with open(c, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return p

def salvar_json(c, d):
    with open(c, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def get_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    if request.headers.get("CF-Connecting-IP"):
        return request.headers.get("CF-Connecting-IP")
    return request.remote_addr or "?"

def registrar_visita():
    try:
        v = ler_json(VISITAS_FILE, [])
        v.insert(0, {
            "ip": get_ip(),
            "ua": request.headers.get("User-Agent","")[:160],
            "data": datetime.now().isoformat(),
        })
        v = v[:2000]
        salvar_json(VISITAS_FILE, v)
    except Exception: pass

def registrar_busca(canal, ok):
    try:
        b = ler_json(BUSCAS_FILE, [])
        b.insert(0, {
            "canal": canal, "ok": ok,
            "ip": get_ip(),
            "data": datetime.now().isoformat(),
        })
        b = b[:2000]
        salvar_json(BUSCAS_FILE, b)
    except Exception: pass

def marcar_assistindo(canal):
    with ASSISTINDO_LOCK:
        ASSISTINDO[get_ip()] = {"canal": canal, "quando": time.time()}

def limpar_assistindo():
    with ASSISTINDO_LOCK:
        agora = time.time()
        for ip in list(ASSISTINDO.keys()):
            if agora - ASSISTINDO[ip]["quando"] > 60:
                del ASSISTINDO[ip]

@app.before_request
def contar():
    if request.method == "GET" and request.path == "/":
        registrar_visita()

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

# ============ HTML ============
HTML_PAGINA = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>MARCOS TV</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;width:100%;overflow-x:hidden}
  body{font-family:'Inter',-apple-system,Arial,sans-serif;
    background:radial-gradient(ellipse at top,#1a1a2e 0%,#0a0a0f 60%);
    color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:12px}
  .app{width:100%;max-width:900px}
  .brand{text-align:center;margin-bottom:16px}
  .brand h1{font-size:clamp(2em,7vw,3.2em);font-weight:900;letter-spacing:2px;
    background:linear-gradient(135deg,#fff 0%,#a29bfe 50%,#6c5ce7 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:2px}
  .brand .sub{color:#6c5ce7;font-size:.75em;letter-spacing:4px;font-weight:600;text-transform:uppercase;opacity:.8}
  .player-card{background:rgba(20,20,31,.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
    border:1px solid rgba(108,92,231,.25);border-radius:20px;padding:14px;
    box-shadow:0 25px 60px rgba(0,0,0,.6)}
  .video-js{width:100%;height:380px;border-radius:14px;overflow:hidden;background:#000}
  .video-js.vjs-fullscreen{width:100vw!important;height:100vh!important;top:0!important;left:0!important;
    position:fixed!important;border-radius:0!important;z-index:999999!important}
  .video-js.vjs-fullscreen video,.video-js.vjs-fullscreen .vjs-tech{width:100vw!important;height:100vh!important;object-fit:cover!important}
  @media(max-width:640px){.video-js:not(.vjs-fullscreen){height:220px}}
  .controls{display:flex;gap:10px;margin-top:14px}
  .controls input{flex:1;background:rgba(13,13,20,.9);border:1.5px solid rgba(108,92,231,.3);color:#fff;
    padding:12px 14px;border-radius:12px;font-family:inherit;font-size:.95em;font-weight:500;outline:none}
  .controls input:focus{border-color:#6c5ce7}
  .btn-play{background:linear-gradient(135deg,#6c5ce7 0%,#a29bfe 100%);color:#fff;border:none;padding:12px 20px;
    border-radius:12px;font-family:inherit;font-weight:700;font-size:.9em;cursor:pointer;display:flex;align-items:center;gap:8px;
    box-shadow:0 8px 20px rgba(108,92,231,.35)}
  .canais-fixos{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin-top:12px}
  .canal-btn{background:rgba(20,20,31,.7);border:1.5px solid rgba(108,92,231,.4);color:#a29bfe;padding:10px 4px;
    border-radius:10px;font-family:inherit;font-weight:700;font-size:.75em;letter-spacing:1px;text-transform:uppercase;
    cursor:pointer;text-align:center;transition:all .2s}
  .canal-btn:hover{background:rgba(108,92,231,.2);color:#fff;border-color:#a29bfe}
  .canal-btn.ativo{background:linear-gradient(135deg,rgba(108,92,231,.4),rgba(162,155,254,.4));border-color:#a29bfe;color:#fff;
    box-shadow:0 0 20px rgba(108,92,231,.5)}
  .status{text-align:center;margin-top:10px;font-size:.85em;color:#888;min-height:18px;font-weight:500}
  .status.ok{color:#00b894}.status.err{color:#e74c3c}
  .footer{text-align:center;color:#444;font-size:.75em;margin-top:16px}
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
    <div class="canais-fixos">
      {% for c in canais %}
      <div class="canal-btn" data-canal="{{ c }}" onclick="tocarFixo('{{ c }}',this)">{{ c }}</div>
      {% endfor %}
    </div>
    <div class="controls">
      <input id="canal" type="text" placeholder="Nome do canal..." autocomplete="off">
      <button id="btnPlay" class="btn-play" onclick="tocar()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> PLAY
      </button>
    </div>
    <div class="status" id="status"></div>
  </div>
  <div class="footer">© MARCOS TV</div>
</div>
<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
var player=videojs('player',{controls:true,autoplay:false,preload:'auto',liveui:true,
  html5:{vhs:{overrideNative:true,maxBufferLength:40,maxMaxBufferLength:80,liveSyncDuration:8,
  liveMaxLatencyDuration:25,enableLowInitialPlaylist:true,smoothQualityChange:true,fastQualityChange:true,handlePartialData:true}}});
var statusEl=document.getElementById('status'),btn=document.getElementById('btnPlay'),input=document.getElementById('canal');
player.on('fullscreenchange',function(){
  if(player.isFullscreen()){try{if(screen.orientation&&screen.orientation.lock)screen.orientation.lock('landscape').catch(function(){});}catch(e){}}
  else{try{if(screen.orientation&&screen.orientation.unlock)screen.orientation.unlock().catch(function(){});}catch(e){}}
});
function setStatus(m,t){statusEl.className='status'+(t?' '+t:'');statusEl.innerText=m||''}
function marcarAtivo(el){document.querySelectorAll('.canal-btn').forEach(function(b){b.classList.remove('ativo')});if(el)el.classList.add('ativo')}
function tocarFixo(c,el){marcarAtivo(el);input.value=c;tocar()}
function tocar(){
  var c=input.value.trim().toLowerCase();
  if(!c){setStatus('Digite o nome do canal','err');input.focus();return}
  setStatus('Carregando '+c+'...');btn.disabled=true;
  fetch('/testar/'+encodeURIComponent(c)).then(r=>r.json()).then(d=>{
    btn.disabled=false;
    if(d.ok){
      setStatus('Tocando: '+c,'ok');
      player.pause();player.error(null);
      player.src({src:'/play/'+encodeURIComponent(c)+'?t='+Date.now(),type:'application/x-mpegURL'});
      player.load();
      player.play().catch(function(e){setStatus('Erro: '+e.message,'err')});
    } else setStatus(d.msg||'Canal indisponivel','err');
  }).catch(e=>{btn.disabled=false;setStatus('Erro: '+e.message,'err')});
}
input.addEventListener('keydown',function(e){if(e.key==='Enter')tocar()});
</script>
</body>
</html>
'''

# ============ ROTAS ============
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
    canal=canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$',canal):
        registrar_busca(canal,False)
        return {"ok":False,"msg":"Nome invalido"}
    r,_=buscar_m3u8(canal)
    ok = r is not None
    registrar_busca(canal,ok)
    if ok: return {"ok":True}
    return {"ok":False,"msg":"Canal '"+canal+"' indisponivel"}

@app.route('/play/<canal>')
def play(canal):
    canal=canal.strip().lower()
    if not re.match(r'^[a-z0-9_\-]+$',canal):
        return "Nome invalido",400
    r,url_orig=buscar_m3u8(canal)
    if not r: return "Canal nao encontrado",404
    marcar_assistindo(canal)
    base=getattr(r,'url',url_orig)
    linhas=[]
    for l in r.text.splitlines():
        ls=l.strip()
        if ls and not ls.startswith('#'):
            abs_url=urljoin(base,ls)
            ep="/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{ep}?url={quote(abs_url,safe='')}&canal={canal}")
        else: linhas.append(ls)
    return Response("\n".join(linhas),status=200,headers={'Content-Type':'application/vnd.apple.mpegurl','Access-Control-Allow-Origin':'*','Cache-Control':'no-cache'})

@app.route('/proxy_m3u8')
def proxy_m3u8():
    target=unquote(request.args.get('url',''))
    canal=request.args.get('canal','')
    if not target or not canal: return "Faltam parametros",400
    h=obter_headers(canal); r=None
    try: r=get_sessao_persistente().get(target,headers=h,timeout=8,verify=False)
    except Exception: pass
    if not r or r.status_code!=200:
        try: r=std_requests.get(target,headers=h,timeout=8,verify=False)
        except Exception as e: return f"Erro: {e}",500
    if r.status_code!=200: return f"upstream {r.status_code}",r.status_code
    marcar_assistindo(canal)
    base=getattr(r,'url',target)
    linhas=[]
    for l in r.text.splitlines():
        ls=l.strip()
        if ls and not ls.startswith('#'):
            abs_url=urljoin(base,ls)
            ep="/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{ep}?url={quote(abs_url,safe='')}&canal={canal}")
        else: linhas.append(ls)
    return Response("\n".join(linhas),status=200,headers={'Content-Type':'application/vnd.apple.mpegurl','Access-Control-Allow-Origin':'*','Cache-Control':'no-cache'})

@app.route('/ts_proxy')
def ts_proxy():
    target=unquote(request.args.get('url',''))
    canal=request.args.get('canal','')
    if not target or not canal: return "Faltam parametros",400
    conteudo,status=buscar_segmento(target,canal)
    if conteudo is None: return f"Erro segmento {status}",status
    marcar_assistindo(canal)
    return Response(conteudo,status=200,headers={'Content-Type':'video/mp2t','Content-Length':str(len(conteudo)),'Cache-Control':'public, max-age=120','Accept-Ranges':'bytes','Access-Control-Allow-Origin':'*'})

# ============ ADMIN ============
ADMIN_HTML = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin - Marcos TV</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root{--purple:#6c5ce7;--purple2:#a29bfe;--bg:#0f1117;--bg2:#171a22;--bg3:#1f232d;--bd:#2a2e38;--txt:#fff;--mut:#8b93a5;--grn:#00e701}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:Arial,sans-serif;padding:16px}
.wrap{max-width:1200px;margin:0 auto}
h1{color:var(--purple2);font-size:22px;margin-bottom:20px}
h2{color:var(--purple2);font-size:15px;margin:20px 0 10px;text-transform:uppercase;letter-spacing:1px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.stat{background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:14px}
.stat b{display:block;color:var(--mut);font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.stat span{font-size:22px;font-weight:900;color:var(--grn)}
.stat.gold span{color:var(--purple2)}
table{width:100%;border-collapse:collapse;background:var(--bg2);border-radius:10px;overflow:hidden;font-size:12px}
th{background:var(--bg3);color:var(--purple2);padding:10px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.8px}
td{padding:10px;border-bottom:1px solid var(--bd)}
tr:hover td{background:var(--bg3)}
.tab{display:inline-block;padding:8px 14px;background:var(--bg2);border:1px solid var(--bd);border-radius:6px;color:var(--mut);cursor:pointer;font-weight:700;font-size:12px;margin-right:6px}
.tab.ativo{background:var(--purple);color:#fff;border-color:var(--purple)}
.painel{display:none}.painel.ativo{display:block}
</style></head><body>
<div class="wrap">
<h1>📺 Painel Admin — Marcos TV</h1>
<div>
<div class="tab ativo" onclick="aba('visitas',this)">👁 Visitas</div>
<div class="tab" onclick="aba('assistindo',this)">▶ Assistindo agora</div>
<div class="tab" onclick="aba('buscas',this)">🔍 Buscas</div>
<div class="tab" onclick="aba('canais',this)">📺 Canais</div>
</div>
<div class="painel ativo" id="p-visitas">
  <div class="stats" id="s-visitas"></div>
  <h2>Últimas visitas</h2>
  <div style="overflow-x:auto"><table><thead><tr><th>Data/Hora</th><th>IP</th><th>Navegador</th></tr></thead><tbody id="t-visitas"></tbody></table></div>
</div>
<div class="painel" id="p-assistindo">
  <div class="stats" id="s-assistindo"></div>
  <h2>Assistindo agora</h2>
  <div style="overflow-x:auto"><table><thead><tr><th>IP</th><th>Canal</th><th>Último sinal</th></tr></thead><tbody id="t-assistindo"></tbody></table></div>
</div>
<div class="painel" id="p-buscas">
  <div class="stats" id="s-buscas"></div>
  <h2>Buscas recentes</h2>
  <div style="overflow-x:auto"><table><thead><tr><th>Data/Hora</th><th>IP</th><th>Canal</th><th>Status</th></tr></thead><tbody id="t-buscas"></tbody></table></div>
</div>
<div class="painel" id="p-canais">
  <h2>Canais fixos</h2>
  <div id="lista-canais" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px"></div>
</div>
</div>
<script>
function aba(n,el){
  document.querySelectorAll('.painel').forEach(p=>p.classList.remove('ativo'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('ativo'));
  document.getElementById('p-'+n).classList.add('ativo');
  el.classList.add('ativo');
}
async function carregar(){
  const v = await (await fetch('/api/visitas')).json();
  const hoje = v.filter(x=>x.data&&x.data.slice(0,10)===new Date().toISOString().slice(0,10)).length;
  const ips = new Set(v.map(x=>x.ip)).size;
  document.getElementById('s-visitas').innerHTML=
    '<div class="stat"><b>Hoje</b><span>'+hoje+'</span></div>'+
    '<div class="stat gold"><b>Total</b><span>'+v.length+'</span></div>'+
    '<div class="stat"><b>IPs únicos</b><span>'+ips+'</span></div>';
  document.getElementById('t-visitas').innerHTML = v.slice(0,80).map(x=>
    '<tr><td>'+((x.data||'').slice(0,16).replace('T',' '))+'</td><td>'+x.ip+'</td><td style="color:var(--mut);font-size:10px">'+(x.ua||'').slice(0,60)+'</td></tr>'
  ).join('') || '<tr><td colspan="3" style="text-align:center;padding:20px">Nenhuma visita</td></tr>';

  const a = await (await fetch('/api/assistindo')).json();
  document.getElementById('s-assistindo').innerHTML=
    '<div class="stat"><b>Assistindo</b><span>'+a.total+'</span></div>';
  document.getElementById('t-assistindo').innerHTML = (a.lista||[]).map(x=>
    '<tr><td>'+x.ip+'</td><td style="color:var(--purple2);font-weight:800">'+x.canal+'</td><td style="color:var(--mut);font-size:10px">'+x.ha+'s atrás</td></tr>'
  ).join('') || '<tr><td colspan="3" style="text-align:center;padding:20px">Ninguém assistindo</td></tr>';

  const b = await (await fetch('/api/buscas')).json();
  const ok = b.filter(x=>x.ok).length;
  document.getElementById('s-buscas').innerHTML=
    '<div class="stat"><b>Total buscas</b><span>'+b.length+'</span></div>'+
    '<div class="stat gold"><b>Com sucesso</b><span>'+ok+'</span></div>';
  document.getElementById('t-buscas').innerHTML = b.slice(0,80).map(x=>
    '<tr><td>'+((x.data||'').slice(0,16).replace('T',' '))+'</td><td>'+x.ip+'</td><td style="color:var(--purple2);font-weight:800">'+x.canal+'</td><td>'+(x.ok?'✅':'❌')+'</td></tr>'
  ).join('') || '<tr><td colspan="4" style="text-align:center;padding:20px">Nenhuma busca</td></tr>';

  const c = await (await fetch('/api/canais')).json();
  document.getElementById('lista-canais').innerHTML = c.canais.map(c=>
    '<div style="background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:14px;text-align:center;color:var(--purple2);font-weight:800;letter-spacing:1px;text-transform:uppercase;font-size:12px">'+c+'</div>'
  ).join('');
}
carregar();
setInterval(carregar,15000);
</script></body></html>"""

@app.route('/admin')
def admin_panel():
    if request.args.get('s','') != ADMIN_SENHA:
        return """<html><body style='background:#0f1117;color:#fff;font-family:Arial;padding:40px'>
        <h2>🔒 Admin Marcos TV</h2><form method='get'>
        <input name='s' type='password' placeholder='Senha' style='padding:12px;font-size:16px;border-radius:8px;border:1px solid #2a2e38;background:#171a22;color:#fff'>
        <button type='submit' style='padding:12px 24px;background:#6c5ce7;color:#fff;border:none;font-weight:bold;border-radius:8px;cursor:pointer'>Entrar</button>
        </form></body></html>""", 401
    return ADMIN_HTML

@app.route('/api/visitas')
def api_visitas(): return jsonify(ler_json(VISITAS_FILE, []))

@app.route('/api/buscas')
def api_buscas(): return jsonify(ler_json(BUSCAS_FILE, []))

@app.route('/api/canais')
def api_canais(): return jsonify({"canais": CANAIS_FIXOS})

@app.route('/api/assistindo')
def api_assistindo():
    limpar_assistindo()
    agora = time.time()
    lista = []
    with ASSISTINDO_LOCK:
        for ip, info in ASSISTINDO.items():
            lista.append({"ip": ip, "canal": info["canal"], "ha": int(agora - info["quando"])})
    return jsonify({"total": len(lista), "lista": lista})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
