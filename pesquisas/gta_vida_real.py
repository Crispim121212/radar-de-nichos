import sys, json, time, re, urllib.parse, urllib.request, datetime
from yt_dlp import YoutubeDL
sys.stdout.reconfigure(encoding="utf-8")
Q = {
 "en": ["gta 6 real life locations","real miami vice city history","gta 6 real life inspiration","gta 6 hacker story","arion kurtaj gta",
        "history of rockstar games","how much did gta 6 cost","real crimes that inspired gta","gta 6 florida man","gta documentary",
        "rise of rockstar games","gta vs real life","leonida real florida","gta 6 leak documentary","gta 6 explained business"],
 "pt": ["gta na vida real","gta 6 vida real","história da rockstar","miami real gta","hacker gta 6","quanto custou gta 6",
        "crimes reais gta","gta documentário","vice city na vida real","gta 6 flórida real","gta 6 explicado"],
 "es": ["gta 6 vida real","historia de rockstar games","hacker gta 6","gta 6 lugares reales"],
 "de": ["gta 6 echtes leben","geschichte rockstar games","gta 6 hacker"],
}
LOC = {"en":("en","US"),"pt":("pt-BR","BR"),"es":("es","ES"),"de":("de","DE")}
SP = {"mes":"EgIIBA%3D%3D","sempre":""}
y = YoutubeDL({"quiet":True,"extract_flat":True,"playlistend":30,"no_warnings":True,"ignoreerrors":True})
res = []
for lg, qs in Q.items():
    hl, gl = LOC[lg]
    for q in qs:
        for nome, sp in SP.items():
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&hl={hl}&gl={gl}" + (f"&sp={sp}" if sp else "")
            r = y.extract_info(url, download=False) or {}
            for e in r.get("entries") or []:
                if not e or not e.get("view_count"): continue
                res.append(dict(lg=lg, q=q, janela=nome, id=e["id"], titulo=e.get("title"), canal=e.get("channel"),
                                cid=e.get("channel_id"), views=e["view_count"], dur=round((e.get("duration") or 0)/60,1)))
            time.sleep(1.5)
        print(lg, q, len(res), flush=True)
json.dump(res, open("busca.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
# raio-x dos canais com vídeos fortes
fortes = {}
for v in sorted(res, key=lambda x: -x["views"]):
    if v["views"] >= 20000 and v["cid"] and v["cid"] not in fortes: fortes[v["cid"]] = v
yc = YoutubeDL({"quiet":True,"extract_flat":True,"playlistend":60,"no_warnings":True,"ignoreerrors":True})
canais = {}
for i, cid in enumerate(list(fortes)[:160]):
    l = yc.extract_info(f"https://www.youtube.com/channel/{cid}/videos", download=False) or {}
    ents = [e for e in (l.get("entries") or []) if e]
    info = dict(nome=l.get("channel"), inscritos=l.get("channel_follower_count"), videos=len(ents),
                v30=sum(1 for e in ents if (e.get("view_count") or 0) >= 30000),
                ultimos=[(e.get("title"), e.get("view_count")) for e in ents[:8]])
    try:
        x = urllib.request.urlopen(urllib.request.Request(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", headers={"User-Agent":"Mozilla/5.0"}), timeout=15).read().decode("utf-8","ignore")
        d = re.findall(r"<published>([^<]+)</published>", x)
        if d: info["criado"] = d[0][:10]
    except Exception: pass
    canais[cid] = info
    if i % 20 == 0: print("canais", i, flush=True)
    time.sleep(1.2)
json.dump(canais, open("canais.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("FIM", len(res), len(canais))
