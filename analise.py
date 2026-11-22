"""Funções de análise do Radar: filtro de canal pequeno/novo, idioma do título e micronichos."""
import re

IDADE_MAX = 20          # canal começou a postar há no máximo X dias
INSCRITOS_MAX = 100000  # e tem no máximo X inscritos


def pequeno_recente(idade, inscritos):
    return idade is not None and idade <= IDADE_MAX and (inscritos or 0) <= INSCRITOS_MAX

PALAVRAS = {
    "pt": "o a os as de do da dos das que não com uma para por como mais seu sua ele ela quando foi isso você são está história brasil",
    "en": "the and of to in is was his her he she with for that this you what when how who why after before secret billionaire",
    "es": "el la los las de del que y en con por para una su cuando qué cómo historia nunca porque millonario",
    "de": "der die das und ist nicht mit von den dem ein eine wie was wenn warum geschichte über auch sich",
    "fr": "le la les des du et est une pour avec dans qui que pas sur au aux histoire pourquoi comment",
    "it": "il lo la gli le di del della che e è con per una non come quando perché storia",
}
PALAVRAS = {k: set(v.split()) for k, v in PALAVRAS.items()}
STOP = set().union(*PALAVRAS.values()) | set("a an my your i me we they it be are at by from as on our their its this".split())


def tokens(t):
    return re.findall(r"[\wÀ-ÿ']+", (t or "").lower())


def idioma_titulo(titulo, padrao):
    w = tokens(titulo)
    pont = {k: sum(1 for x in w if x in s) for k, s in PALAVRAS.items()}
    if re.search(r"[ãõç]", (titulo or "").lower()): pont["pt"] += 2
    if re.search(r"[ñ¿¡]", titulo or ""): pont["es"] += 2
    if re.search(r"[äöüß]", (titulo or "").lower()): pont["de"] += 2
    melhor = max(pont, key=pont.get)
    return melhor if pont[melhor] >= 2 and pont[melhor] > pont.get(padrao, 0) else padrao


def micronichos(saida, limite=120):
    grams = {}
    for x in saida:
        if x["tipo"] not in ("padrao", "explodindo"):
            continue
        w = [t for t in tokens(x["titulo"]) if len(t) > 2 and t not in STOP and not t.isdigit()]
        vistos = set()
        for n in (2, 3):
            for i in range(len(w) - n + 1):
                g = " ".join(w[i:i + n])
                if g not in vistos:
                    vistos.add(g)
                    grams.setdefault((x["idioma"], g), []).append(x)
    cand = []
    for (lg, g), xs in grams.items():
        cids = {x["cid"] for x in xs}
        if len(cids) >= 3:
            cand.append((lg, g, xs, cids))
    cand.sort(key=lambda c: (-len(c[3]), -sum(x["views"] for x in c[2])))
    finais, escolhidos = [], []
    for lg, g, xs, cids in cand:
        # junta com um micronicho já escolhido se os canais forem quase os mesmos
        dup = next((f for f, c in escolhidos if f["idioma"] == lg and len(cids & c) / len(cids | c) >= 0.5), None)
        if dup:
            if g not in dup["variacoes"] and len(dup["variacoes"]) < 4:
                dup["variacoes"].append(g)
            continue
        m = dict(expr=g, variacoes=[], idioma=lg, canais=len(cids), views=sum(x["views"] for x in xs),
                 temas=sorted({x["tema"] for x in xs}),
                 exemplos=[dict(id=x["id"], titulo=x["titulo"], canal=x["canal"], views=x["views"])
                           for x in sorted(xs, key=lambda y: -y["views"])[:4]])
        finais.append(m); escolhidos.append((m, cids))
        if len(finais) >= limite:
            break
    return finais
