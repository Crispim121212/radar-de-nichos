"""Reaplica idioma do título + micronichos no histórico de hoje e regera site/dados.js (sem nova varredura)."""
import json, sys, pathlib, datetime
sys.stdout.reconfigure(encoding="utf-8")
from analise import idioma_titulo, micronichos, pequeno_recente
B = pathlib.Path(__file__).parent
p = sorted((B / "historico").glob("*.json"))[-1]
d = json.loads(p.read_text(encoding="utf-8"))
antes = len(d["videos"])
d["videos"] = [v for v in d["videos"] if pequeno_recente(v.get("idade"), v.get("inscritos"))]
print("vídeos:", antes, "->", len(d["videos"]))
for v in d["videos"]:
    v.setdefault("mercado", v["idioma"]); v["idioma"] = idioma_titulo(v["titulo"], v["mercado"])
for n in d["nichos"]:
    for lg in n["por"]:
        vs = [x for x in d["videos"] if x["tema"] == n["id"] and x["idioma"] == lg]
        n["por"][lg].update(n=len(vs), views=sum(x["views"] for x in vs),
                            explodindo=len({x["cid"] for x in vs if x["tipo"] in ("explodindo", "padrao")}))
    fortes = [lg for lg in n["por"] if n["por"][lg]["explodindo"] >= 1 or n["por"][lg]["n"] >= 6]
    vazios = [lg for lg in n["por"] if n["por"][lg]["n"] <= 1]
    n["lacunas"] = [dict(de=a, para=b) for a in fortes for b in vazios if a != b]
for n in d["nichos"]:
    n["total"] = sum(p["views"] for p in n["por"].values()); n["explodindo"] = sum(p["explodindo"] for p in n["por"].values())
    n["imitadores"] = sum(x.get("imitadores", 0) for x in d["videos"] if x["tema"] == n["id"])
d["nichos"].sort(key=lambda n: (-n["explodindo"], -n["total"]))
d["serie"][-1].update(videos=len(d["videos"]), explodindo=sum(1 for x in d["videos"] if x["tipo"] in ("explodindo", "padrao")))
d["micronichos"] = micronichos(d["videos"])
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
(B / "site" / "dados.js").write_text("window.RADAR = " + json.dumps(d, ensure_ascii=False) + ";", encoding="utf-8")
print(p.name, len(d["micronichos"]), "micronichos")
for m in d["micronichos"][:15]: print(m["idioma"], m["canais"], m["expr"], m["variacoes"])
