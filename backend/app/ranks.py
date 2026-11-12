# звания по общему числу очков (очки не отнимаются, поэтому звание не падает)
RANKS = [
    (0, "debut", "Дебютант"),
    (300, "znatok", "Знаток"),
    (1000, "analitik", "Аналитик"),
    (2000, "strateg", "Стратег"),
    (4000, "oracle", "Оракул"),
]


def rank_info(points: int) -> dict:
    idx = 0
    for i, (need, _, _) in enumerate(RANKS):
        if points >= need:
            idx = i
    need, key, name = RANKS[idx]
    nxt = RANKS[idx + 1] if idx + 1 < len(RANKS) else None
    out = {"key": key, "name": name, "next": None, "to_next": 0, "progress": 100}
    if nxt:
        span = nxt[0] - need
        out.update(next=nxt[2], to_next=nxt[0] - points,
                   progress=max(0, min(100, round((points - need) / span * 100))))
    return out