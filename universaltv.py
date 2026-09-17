cat << 'EOF' > universaltv.py
import os, sys, json, time, re, threading
import urllib3
from flask import Flask, Response, request
from urllib.parse import urljoin, quote, unquote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from curl_cffi import requests as ImpersonateSession
    USE_CURL = True
except ImportError:
    import requests as ImpersonateSession
    USE_CURL = False

app = Flask(__name__)

# Render define PORT automaticamente
PORTA = int(os.environ.get("PORT", 9999))

PASTA_PERFIS = os.path.expanduser("./canais_dados")
os.makedirs(PASTA_PERFIS, exist_ok=True)

PROXIES = ["chrome120", "chrome110", "safari_15_5"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

EMBEDS_DOMINIOS = [
    "https://ww5.embedtv.lat",
    "https://2608.cdnembedcanais.xyz",
    "https://w1.rdse.buzz"
]

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

SESSAO = ImpersonateSession.Session()
SESSAO.headers.update({"User-Agent": USER_AGENT})


def criar_sessao(imp=None):
    if USE_CURL:
        try:
            return ImpersonateSession.Session(impersonate=imp or "chrome120")
        except Exception:
            pass
    return ImpersonateSession.Session()


def extrair_nome_canal(url):
    m = re.search(r'/([^/]+)/index\.m3u8', url) or re.search(r'/([^/?]+)\.m3u8', url)
    return m.group(1).lower() if m else "stream"


def substituir_canal_na_url(url_orig, canal):
    antigo = extrair_nome_canal(url_orig)
    if antigo and antigo != "stream":
        res = re.sub(rf'/{re.escape(antigo)}/index\.m3u8', f'/{canal}/index.m3u8', url_orig, flags=re.I)
        if res != url_orig:
            return res
        return re.sub(rf'/{re.escape(antigo)}\.m3u8', f'/{canal}.m3u8', url_orig, flags=re.I)
    return url_orig


def listar_perfis():
    if not os.path.isdir(PASTA_PERFIS):
        return []
    return sorted([os.path.splitext(f)[0] for f in os.listdir(PASTA_PERFIS) if f.endswith('.json')])


def carregar_perfil(p):
    f = os.path.join(PASTA_PERFIS, f"{p}.json")
    return json.load(open(f, 'r', encoding='utf-8')) if os.path.exists(f) else None


def obter_headers(cfg, ref_custom=None):
    h = {
        "User-Agent": cfg.get("user_agent") or USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site"
    }
    if cfg.get("cookie"):
        h["Cookie"] = cfg["cookie"]
    if cfg.get("origin"):
        h["Origin"] = cfg["origin"]
    ref = ref_custom or cfg.get("referer")
    if ref:
        h["Referer"] = ref
        if not h.get("Origin"):
            m = re.match(r'(https?://[^/]+)', ref)
            if m:
                h["Origin"] = m.group(1)
    return h


def extrair_links_playlist(html):
    padroes = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.txt[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.m3u[^\s"\'<>]*)',
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        r'source\s*:\s*["\'](https?://[^"\']+)["\']'
    ]
    encontrados = []
    for p in padroes:
        m = re.findall(p, html, re.I)
        if m:
            encontrados.extend(m)
    return list(set(encontrados))


def processar_embed(canal):
    sess = criar_sessao("chrome120")
    variacoes = ALIASES.get(canal, [canal])
    for var_canal in variacoes:
        for base in EMBEDS_DOMINIOS:
            embed_url = f"{base}/{var_canal}"
            try:
                r = sess.get(embed_url, headers={"User-Agent": USER_AGENT}, timeout=6, verify=False)
                if r.status_code == 200:
                    links = extrair_links_playlist(r.text)
                    for stream_url in links:
                        try:
                            r2 = sess.get(stream_url, headers={"User-Agent": USER_AGENT, "Referer": embed_url}, timeout=6, verify=False)
                            if r2.status_code == 200 and ("#EXTM3U" in r2.text or "#EXT-X" in r2.text):
                                cfg = {"perfil_nome": f"embed_{var_canal}", "user_agent": USER_AGENT, "referer": embed_url}
                                return r2, stream_url, cfg, "chrome120"
                        except Exception:
                            continue
            except Exception:
                continue
    return None, None, None, None


def processar_bruto(canal):
    perfis = listar_perfis()
    variacoes = ALIASES.get(canal, [canal])
    for var_canal in variacoes:
        for p in perfis:
            cfg = carregar_perfil(p)
            if not cfg:
                continue
            url_teste = substituir_canal_na_url(cfg.get("url", ""), var_canal)
            for imp in PROXIES:
                sess = criar_sessao(imp)
                try:
                    r = sess.get(url_teste, headers=obter_headers(cfg), timeout=6, verify=False)
                    if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
                        return r, url_teste, cfg, imp
                except Exception:
                    pass
    return None, None, None, None


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = '*'
    return r


@app.route('/')
def index():
    return "MarcosTV Online — use /play/<canal> (ex: /play/espn)"


@app.route('/play/<canal>')
def rota_play(canal):
    canal = canal.strip('/').lower()

    resp, url_a, cfg, tunel = processar_embed(canal)
    if resp:
        return gerar_playlist_proxy(resp, url_a, cfg, tunel)

    resp, url_a, cfg, tunel = processar_bruto(canal)
    if resp:
        return gerar_playlist_proxy(resp, url_a, cfg, tunel)

    return f"Erro 404: Canal '{canal}' não encontrado", 404


def gerar_playlist_proxy(resp, url_a, cfg, tunel):
    host = request.host_url.rstrip('/')
    linhas = []
    base = getattr(resp, 'url', url_a)
    p_nome = cfg.get("perfil_nome", "")
    ref_encoded = quote(cfg.get("referer", ""))
    cookie_encoded = quote(cfg.get("cookie", ""))

    for l in resp.text.splitlines():
        ls = l.strip()
        if ls and not ls.startswith('#'):
            abs_url = urljoin(base, ls)
            ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
            linhas.append(f"{host}{ep}?url={quote(abs_url)}&perfil={p_nome}&tunel={tunel}&ref={ref_encoded}&ck={cookie_encoded}")
        else:
            linhas.append(ls)

    return Response("\n".join(linhas), status=200, headers={'Content-Type': 'application/vnd.apple.mpegurl'})


@app.route('/proxy_m3u8')
def proxy_m3u8():
    target = unquote(request.args.get('url', ''))
    p_nome = request.args.get('perfil', '')
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', ''))
    ck_custom = unquote(request.args.get('ck', ''))
    cfg = carregar_perfil(p_nome) or {"user_agent": USER_AGENT}
    if ck_custom:
        cfg["cookie"] = ck_custom
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref_custom), timeout=8, verify=False)
        host = request.host_url.rstrip('/')
        linhas = []
        base = getattr(r, 'url', target)
        ref_encoded = quote(ref_custom or cfg.get("referer", ""))
        ck_encoded = quote(ck_custom or cfg.get("cookie", ""))
        for l in r.text.splitlines():
            ls = l.strip()
            if ls and not ls.startswith('#'):
                abs_url = urljoin(base, ls)
                ep = "/proxy_m3u8" if '.m3u8' in ls else "/ts_proxy"
                linhas.append(f"{host}{ep}?url={quote(abs_url)}&perfil={p_nome}&tunel={tunel}&ref={ref_encoded}&ck={ck_encoded}")
            else:
                linhas.append(ls)
        return Response("\n".join(linhas), status=200, headers={'Content-Type': 'application/vnd.apple.mpegurl'})
    except Exception as e:
        return str(e), 500


@app.route('/ts_proxy')
def ts_proxy():
    target = unquote(request.args.get('url', ''))
    p_nome = request.args.get('perfil', '')
    tunel = request.args.get('tunel', 'chrome120')
    ref_custom = unquote(request.args.get('ref', ''))
    ck_custom = unquote(request.args.get('ck', ''))
    cfg = carregar_perfil(p_nome) or {"user_agent": USER_AGENT}
    if ck_custom:
        cfg["cookie"] = ck_custom
    try:
        sess = criar_sessao(tunel)
        r = sess.get(target, headers=obter_headers(cfg, ref_custom), stream=True, timeout=10, verify=False)
        def gerar():
            if hasattr(r, 'iter_content'):
                for chunk in r.iter_content(128 * 1024):
                    if chunk:
                        yield chunk
            else:
                yield r.content
        return Response(gerar(), status=r.status_code, headers={'Content-Type': 'video/mp2t', 'Accept-Ranges': 'bytes'})
    except Exception as e:
        return f"Erro TS: {e}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORTA, threaded=True, debug=False, use_reloader=False)
EOF
