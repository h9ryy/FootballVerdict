from backend.app.ranks import rank_info


def test_rank_thresholds():
    assert rank_info(0)["name"] == "Дебютант"
    assert rank_info(299)["name"] == "Дебютант"
    assert rank_info(300)["name"] == "Знаток"
    assert rank_info(999)["name"] == "Знаток"
    assert rank_info(1000)["name"] == "Аналитик"
    assert rank_info(2000)["name"] == "Стратег"
    assert rank_info(4000)["name"] == "Оракул"


def test_rank_progress():
    r = rank_info(150)
    assert r["next"] == "Знаток" and r["to_next"] == 150 and r["progress"] == 50
    top = rank_info(9999)
    assert top["next"] is None and top["progress"] == 100