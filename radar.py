"""Radar de Nichos v2 — varredura diária e aprofundada do YouTube (grátis: yt-dlp + autocomplete, sem API paga).
Uso: python radar.py [--forcar] [--temas a,b] [--idiomas pt,en]
Gera site/dados.js (lido por site/index.html) e historico/AAAA-MM-DD.json.
"""
import re, sys, json, time, math, datetime, pathlib, urllib.parse, urllib.request, statistics, threading
from concurrent.futures import ThreadPoolExecutor
from yt_dlp import YoutubeDL
from analise import idioma_titulo, micronichos, pequeno_recente

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent
HOJE = datetime.date.today().isoformat()
HIST = BASE / "historico"; HIST.mkdir(exist_ok=True)
CACHE = BASE / "cache_canais.json"
VISTOS = BASE / "vistos.json"
LOG = BASE / "radar.log"

IDIOMAS = {  # hl, gl, rótulo
    "pt": ("pt-BR", "BR", "Português"),
    "en": ("en", "US", "Inglês"),
    "es": ("es", "ES", "Espanhol"),
    "de": ("de", "DE", "Alemão"),
    "fr": ("fr", "FR", "Francês"),
    "it": ("it", "IT", "Italiano"),
}
FILTROS = {"EgQIBBgD": False, "EgQIBBgC": True}  # este mês + 4–20 min | este mês + >20 min (longo)
SEMANA = {"EgQIAxgD": False, "EgQIAxgC": True}   # esta semana (2ª rodada)
LONGO = {**FILTROS, **SEMANA}
MIN_VIEWS = 10000
MIN_VIEWS_2 = 3000     # 2ª rodada (nichos vazios)
POR_TEMA = 25          # canais analisados por nicho
MAX_CANAIS = 400       # + os melhores no geral
SUGESTOES = 2          # termos extras do autocomplete por tema/idioma
BOLA_DE_NEVE = 30      # canais explodindo usados para achar imitadores
WORKERS = 5
WORKERS_BUSCA = 8

_lock = threading.Lock()
_local = threading.local()


def log(*a):
    s = " ".join(str(x) for x in a)
    with _lock:
        print(s, flush=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M} {s}\n")


def carregar(p, padrao):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def salvar(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def ydl(tipo):
    """Uma instância de YoutubeDL por thread e por tipo."""
    k = "y_" + tipo
    if not hasattr(_local, k):
        o = {"quiet": True, "skip_download": True, "ignoreerrors": True, "no_warnings": True}
        if tipo == "busca": o.update(extract_flat=True, playlistend=60)
        if tipo == "canal": o.update(extract_flat=True, playlistend=100)
        setattr(_local, k, YoutubeDL(o))
    return getattr(_local, k)


def sugestoes(termo, hl, gl, n=None, pular=0):
    n = SUGESTOES if n is None else n
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt"
           f"&hl={hl}&gl={gl}&q={urllib.parse.quote(termo)}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        return [s for s in d[1] if s.lower() != termo.lower()][pular:pular + n]
    except Exception:
        return []


def buscar(job):
    termo, lg, sp, tema, origem = job[:5]
    minv = job[5] if len(job) > 5 else MIN_VIEWS
    hl, gl, _ = IDIOMAS[lg]
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(termo)}&sp={sp}&hl={hl}&gl={gl}"
    for tentativa in range(2):
        try:
            r = ydl("busca").extract_info(url, download=False) or {}
            break
        except Exception as e:
            r = {}; time.sleep(5)
    out = []
    for e in (r.get("entries") or []):
        if not e or not e.get("id") or not e.get("channel_id"):
            continue
        if (e.get("view_count") or 0) < minv:
            continue
        out.append(dict(id=e["id"], titulo=e.get("title") or "", canal=e.get("channel") or "",
                        cid=e["channel_id"], views=e.get("view_count") or 0,
                        dur=round((e.get("duration") or 0) / 60, 1), tema=tema, idioma=lg,
                        termo=termo, longo=LONGO[sp], origem=origem))
    time.sleep(0.8)
    return out


def raio_x(cid):
    try:
        l = ydl("canal").extract_info(f"https://www.youtube.com/channel/{cid}/videos", download=False) or {}
    except Exception:
        return cid, None
    ents = [e for e in (l.get("entries") or []) if e]
    vs = [e.get("view_count") or 0 for e in ents]
    info = dict(nome=l.get("channel") or l.get("uploader"), inscritos=l.get("channel_follower_count"),
                videos=len(ents), videos_mais=len(ents) >= 100, inicio=None, checado=HOJE,
                v30=sum(1 for v in vs if v >= 30000), v100=sum(1 for v in vs if v >= 100000),
                mediana=int(statistics.median(vs)) if vs else 0, soma=sum(vs),
                ultimos=[dict(id=e["id"], t=e.get("title"), v=e.get("view_count")) for e in ents[:6]])
    # data de criação do canal pelo feed RSS (exata, não é bloqueado em servidor)
    try:
        req = urllib.request.Request(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            datas = re.findall(r"<published>([^<]+)</published>", r.read().decode("utf-8", "ignore"))
        if datas:
            info["inicio"] = datas[0][:10]
            if len(datas) - 1 < 15 and len(datas) > 1:
                info["primeiro_video"] = datas[-1][:10]
    except Exception:
        pass
    time.sleep(0.8)
    return cid, info


def main():
    args = sys.argv[1:]
    def arg(nome):
        return args[args.index(nome) + 1].split(",") if nome in args else None
    if (HIST / f"{HOJE}.json").exists() and "--forcar" not in args:
        log("já rodou hoje, nada a fazer"); return
    temas = json.loads((BASE / "temas.json").read_text(encoding="utf-8"))
    if arg("--temas"): temas = {k: v for k, v in temas.items() if k in arg("--temas")}
    langs = arg("--idiomas") or list(IDIOMAS)
    global SUGESTOES, POR_TEMA
    if "--grande" in args: SUGESTOES, POR_TEMA = 2, 25
    else: SUGESTOES, POR_TEMA = 1, 12
    t0 = time.time()
    log(f"== início varredura {HOJE} ({len(temas)} temas × {len(langs)} idiomas)")

    # 1) termos: semente + autocomplete
    jobs = []
    for tid, t in temas.items():
        for lg in langs:
            semente = t.get(lg)
            if not semente: continue
            hl, gl, _ = IDIOMAS[lg]
            for termo in [semente] + sugestoes(semente, hl, gl):
                for sp in FILTROS:
                    jobs.append((termo, lg, sp, tid, "busca"))
    log(f"buscas planejadas: {len(jobs)}")

    videos = {}
    def juntar(res):
        for v in res:
            if v["id"] not in videos or videos[v["id"]]["views"] < v["views"]:
                videos[v["id"]] = v
    with ThreadPoolExecutor(WORKERS_BUSCA) as ex:
        for i, res in enumerate(ex.map(buscar, jobs), 1):
            juntar(res)
            if i % 25 == 0: log(f"buscas {i}/{len(jobs)} · {len(videos)} vídeos")
    log(f"buscas ok: {len(videos)} vídeos com {MIN_VIEWS}+ views")

    # 2) raio-x dos canais (cache 3 dias)
    cache = carregar(CACHE, {})
    def precisa(cid):
        c = cache.get(cid)
        return not c or "v30" not in c or not c.get("inicio") or datetime.date.fromisoformat(c["checado"]) <= datetime.date.today() - datetime.timedelta(days=3)
    def checar(cids):
        alvo = [c for c in cids if precisa(c)]
        log(f"raio-x de {len(alvo)} canais ({len(cids) - len(alvo)} do cache)")
        with ThreadPoolExecutor(WORKERS) as ex:
            for i, (cid, info) in enumerate(ex.map(raio_x, alvo), 1):
                if info: cache[cid] = info
                if i % 25 == 0: salvar(CACHE, cache); log(f"canais {i}/{len(alvo)}")
        salvar(CACHE, cache)
    def selecionar(vs, ja=()):
        ordem, geral = [], []
        for v in sorted(vs, key=lambda x: -x["views"]):
            if v["cid"] not in geral: geral.append(v["cid"])
        ordem = [c for c in geral[:MAX_CANAIS] if c not in ja]
        for tid in temas:  # garante os melhores canais de CADA nicho
            n = 0
            for v in sorted((x for x in vs if x["tema"] == tid), key=lambda x: -x["views"]):
                if v["cid"] in ja: continue
                if v["cid"] not in ordem: ordem.append(v["cid"])
                n += 1
                if n >= POR_TEMA: break
        return ordem
    ordem = selecionar(list(videos.values()))
    checar(ordem)

    hoje_d = datetime.date.today()
    def idade(c):
        return (hoje_d - datetime.date.fromisoformat(c["inicio"])).days if c and c.get("inicio") else None
    def novo(c):
        i = idade(c)
        return (i is not None and i <= 90) or (c and not c["videos_mais"] and c["videos"] <= 12)

    # 2b) 2ª rodada para nichos sem nenhum canal pequeno e recente
    def tem_canal(tid):
        return any(pequeno_recente(idade(cache.get(v["cid"])), (cache.get(v["cid"]) or {}).get("inscritos"))
                   for v in videos.values() if v["tema"] == tid and cache.get(v["cid"]))
    vazios = [tid for tid in temas if not tem_canal(tid)]
    if vazios:
        jobs3 = []
        for tid in vazios:
            for lg in langs:
                semente = temas[tid].get(lg)
                if not semente: continue
                hl, gl, _ = IDIOMAS[lg]
                for termo in [semente] + sugestoes(semente, hl, gl, n=4, pular=SUGESTOES):
                    for sp in list(FILTROS) + list(SEMANA):
                        jobs3.append((termo, lg, sp, tid, "busca2", MIN_VIEWS_2))
        log(f"2ª rodada: {len(vazios)} nichos vazios, {len(jobs3)} buscas")
        antes = set(videos)
        with ThreadPoolExecutor(WORKERS_BUSCA) as ex:
            for i, res in enumerate(ex.map(buscar, jobs3), 1):
                juntar(res)
                if i % 50 == 0: log(f"2ª rodada {i}/{len(jobs3)}")
        novos_v = [videos[k] for k in videos if k not in antes]
        checar(selecionar(novos_v, ja=set(cache)))
        log(f"nichos ainda vazios: {sum(1 for t in temas if not tem_canal(t))} de {len(temas)}")

    # 3) bola de neve: títulos virais de canais novos → imitadores
    sementes = []
    for v in sorted(videos.values(), key=lambda x: -x["views"]):
        c = cache.get(v["cid"])
        if c and novo(c) and v["views"] >= 30000 and v["cid"] not in [s[1] for s in sementes]:
            sementes.append((v, v["cid"]))
        if len(sementes) >= BOLA_DE_NEVE: break
    jobs2 = [(v["titulo"][:80], v["idioma"], sp, v["tema"], "imitador:" + v["id"]) for v, _ in sementes for sp in FILTROS]
    if jobs2:
        log(f"bola de neve: {len(jobs2)} buscas a partir de {len(sementes)} virais")
        with ThreadPoolExecutor(WORKERS) as ex:
            for res in ex.map(buscar, jobs2): juntar(res)
        novos_cids = []
        for v in videos.values():
            if v["cid"] not in ordem and v["cid"] not in novos_cids: novos_cids.append(v["cid"])
        checar(novos_cids[:200])

    # 4) classificar
    vistos = carregar(VISTOS, {"canais": {}, "videos": {}})
    imitadores = {}
    for v in videos.values():
        if v["origem"].startswith("imitador:"):
            imitadores.setdefault(v["origem"][9:], set()).add(v["cid"])
    saida = []
    for v in videos.values():
        c = cache.get(v["cid"])
        if not c: continue
        i = idade(c); insc = c.get("inscritos")
        if not pequeno_recente(i, insc): continue  # só canais pequenos e recentes
        ratio = v["views"] / max(insc or 0, 500) if insc is not None else None
        nv = novo(c)
        padrao_dono = (i is not None and i <= 20) and c["videos"] <= 10 and c["v30"] >= 3
        if padrao_dono: tipo = "padrao"
        elif nv and v["views"] >= 30000: tipo = "explodindo"
        elif ratio and ratio >= 5 and (insc or 0) <= 50000: tipo = "outlier"
        else: tipo = "forte"
        score = math.log10(v["views"]) * 10
        if nv: score += 15
        if padrao_dono: score += 15
        if ratio: score += min(math.log10(ratio + 1) * 8, 20)
        if c["videos"] <= 20 and not c["videos_mais"]: score += 5
        score += min(c["v30"], 10)
        imit = len(imitadores.get(v["id"], set()) - {v["cid"]})
        score += min(imit * 2, 10)
        vistos["canais"].setdefault(v["cid"], HOJE)
        vistos["videos"].setdefault(v["id"], HOJE)
        saida.append({**v, "mercado": v["idioma"], "idioma": idioma_titulo(v["titulo"], v["idioma"]), "inscritos": insc, "videos_canal": c["videos"], "videos_mais": c["videos_mais"],
                      "inicio": c.get("inicio"), "idade": i, "ratio": round(ratio, 1) if ratio else None,
                      "v30": c["v30"], "v100": c["v100"], "mediana": c["mediana"], "ultimos": c.get("ultimos", []),
                      "imitadores": imit, "tipo": tipo, "score": round(score, 1),
                      "novo_hoje": vistos["canais"][v["cid"]] == HOJE, "visto_em": vistos["videos"][v["id"]]})
    salvar(VISTOS, vistos)

    # 5) nichos × idiomas e lacunas
    nichos = []
    for tid, t in temas.items():
        por = {}
        for lg in langs:
            vs = [x for x in saida if x["tema"] == tid and x["idioma"] == lg]
            por[lg] = dict(n=len(vs), views=sum(x["views"] for x in vs),
                           explodindo=len({x["cid"] for x in vs if x["tipo"] in ("explodindo", "padrao")}),
                           canais_novos=len({x["cid"] for x in vs if x["idade"] is not None and x["idade"] <= 90}))
        fortes = [lg for lg in por if por[lg]["explodindo"] >= 1 or por[lg]["n"] >= 6]
        vazios = [lg for lg in por if por[lg]["n"] <= 1]
        nichos.append(dict(id=tid, nome=t["nome"], por=por,
                           lacunas=[dict(de=a, para=b) for a in fortes for b in vazios if a != b],
                           total=sum(p["views"] for p in por.values()),
                           explodindo=sum(p["explodindo"] for p in por.values()),
                           imitadores=sum(x["imitadores"] for x in saida if x["tema"] == tid)))
    nichos.sort(key=lambda n: (-n["explodindo"], -n["total"]))

    # 5b) micronichos (analise.py)
    finais = micronichos(saida)

    # 6) série histórica
    serie = []
    for p in sorted(HIST.glob("*.json"))[-13:]:
        if p.stem == HOJE: continue
        d = carregar(p, {})
        serie.append(dict(data=p.stem, videos=len(d.get("videos", [])),
                          explodindo=sum(1 for x in d.get("videos", []) if x["tipo"] in ("explodindo", "padrao"))))
    serie.append(dict(data=HOJE, videos=len(saida), explodindo=sum(1 for x in saida if x["tipo"] in ("explodindo", "padrao"))))

    dados = dict(gerado=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), data=HOJE,
                 idiomas={k: IDIOMAS[k][2] for k in langs}, duracao_min=round((time.time() - t0) / 60),
                 videos=sorted(saida, key=lambda x: -x["score"])[:4000], nichos=nichos, serie=serie, micronichos=finais)
    salvar(HIST / f"{HOJE}.json", dados)
    (BASE / "site" / "dados.js").write_text("window.RADAR = " + json.dumps(dados, ensure_ascii=False) + ";", encoding="utf-8")
    log(f"== fim em {dados['duracao_min']} min: {len(saida)} vídeos, "
        f"{sum(1 for x in saida if x['tipo']=='padrao')} no padrão do dono, "
        f"{sum(1 for x in saida if x['tipo']=='explodindo')} explodindo, "
        f"{len({x['cid'] for x in saida if x['novo_hoje']})} canais novos hoje, {len(finais)} micronichos")


if __name__ == "__main__":
    main()
