import gzip
import sqlite3

from backend.app.backup import make_backup, seconds_to_next
from datetime import datetime, timezone


def test_backup_is_valid_and_old_copies_removed(tmp_path):
    src = tmp_path / "app.db"
    con = sqlite3.connect(src)
    con.execute("create table t(x)")
    con.execute("insert into t values (1)")
    con.commit()
    con.close()
    out_dir = tmp_path / "backups"
    for i in range(4):
        make_backup(src, out_dir, keep=2, stamp=f"2026010{i}-000000")
    files = sorted(out_dir.glob("football-*.db.gz"))
    assert len(files) == 2
    restored = tmp_path / "restored.db"
    with gzip.open(files[-1]) as f:
        restored.write_bytes(f.read())
    con = sqlite3.connect(restored)
    assert con.execute("select x from t").fetchone() == (1,)
    con.close()


def test_next_run_is_within_a_day():
    s = seconds_to_next(datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    assert 0 < s <= 24 * 3600