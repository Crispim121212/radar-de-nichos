import sys, json, time, re, urllib.parse, urllib.request
from yt_dlp import YoutubeDL
sys.stdout.reconfigure(encoding="utf-8")
Q = {
 "vidareal": ["gta 6 vs real life", "gta 6 real life locations", "gta 6 florida man", "gta 6 florida joker real", "gta 6 trailer vs real life", "vice city real miami", "gta 6 vida real", "gta 6 vs vida real", "gta 6 vida real comparação"],
 "hacker": ["gta 6 hacker story", "gta 6 leak 2022 explained", "arion kurtaj", "gta 6 vazamento 2022", "hacker gta 6 história"],
 "nota": ["gta 6 user score metacritic", "gta 6 review bombing", "gta 6 nota baixa jogadores", "gta 6 metacritic usuarios", "gta 6 critics vs players"],
}
y = YoutubeDL({"quiet": True, "extract_flat": True, "playlistend": 30, "no_warnings": True, "ignoreerrors": True})
res = []
for tema, qs in Q.items():
    for q in qs:
        for nome, sp in {"mes": "EgIIBA%3D%3D", "semana": "EgIIAw%3D%3D", "sempre": ""}.items():
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}" + (f"&sp={sp}" if sp else "")
            r = y.extract_info(url, download=False) or {}
            for e in r.get("entries") or []:
                if not e or not e.get("view_count"): continue
                res.append(dict(tema=tema, q=q, janela=nome, id=e["id"], titulo=e.get("title"), canal=e.get("channel"), cid=e.get("channel_id"), views=e["view_count"], dur=round((e.get("duration") or 0)/60,1)))
            time.sleep(1)
        print(tema, q, len(res), flush=True)
json.dump(res, open("gta_video2_busca.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
fortes = {}
for v in sorted(res, key=lambda x: -x["views"]):
    if v["views"] >= 20000 and v["cid"] and v["cid"] not in fortes: fortes[v["cid"]] = v
yc = YoutubeDL({"quiet": True, "extract_flat": True, "playlistend": 60, "no_warnings": True, "ignoreerrors": True})
canais = {}
for cid in list(fortes)[:140]:
    l = yc.extract_info(f"https://www.youtube.com/channel/{cid}/videos", download=False) or {}
    ents = [e for e in (l.get("entries") or []) if e]
    vs = sorted([e.get("view_count") or 0 for e in ents])
    info = dict(nome=l.get("channel"), inscritos=l.get("channel_follower_count"), videos=len(ents), mediana=vs[len(vs)//2] if vs else 0)
    try:
        x = urllib.request.urlopen(urllib.request.Request(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore")
        d = re.findall(r"<published>([^<]+)</published>", x)
        if d: info["criado"] = d[0][:10]
    except Exception: pass
    canais[cid] = info; time.sleep(0.8)
json.dump(canais, open("gta_video2_canais.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("FIM", len(res), len(canais))
