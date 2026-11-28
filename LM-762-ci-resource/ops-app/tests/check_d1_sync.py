"""Test deploy/d1_sync.py against a local SQLite target (same algorithm as Cloudflare D1). Python stdlib only.

  python -X utf8 check_d1_sync.py [--db ../data/ops.db]

Cases: first push equals ops.db; a delta push writes only the changed rows; a push that dies half way is invisible to
readers and is cleaned by the next one; rollback; a new column; the ops.db views give the same answers on the copy.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "deploy"))
import d1_sync as D  # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAIL.append(name)


def view_rows(con, sql):
    return sorted(map(tuple, con.execute(sql).fetchall()), key=repr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(HERE.parent / "data" / "ops.db"))
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="d1test-"))
    try:
        db = tmp / "ops.db"
        src = sqlite3.connect(a.db)
        dst = sqlite3.connect(db)
        src.backup(dst)      # a consistent copy even while the live file is in WAL mode
        src.close()
        dst.close()
        tg = D.SqliteTarget(str(tmp / "d1.sqlite"))
        quiet = lambda *_: None  # noqa: E731

        s1 = D.push(tg, db, "t1", "b1", log=quiet)
        check("first push is snapshot 1", s1 == 1)
        check("first push: copy equals ops.db", D.verify(tg, db, log=quiet))
        loc = sqlite3.connect(db)
        views = [n for (n,) in loc.execute("SELECT name FROM sqlite_master WHERE type='view'")]
        same = all(view_rows(loc, f'SELECT * FROM "{v}"') == view_rows(tg.con, f'SELECT * FROM "{v}"') for v in views)
        check(f"ops.db views give the same rows on the copy ({len(views)} views)", same)

        calls = tg.calls
        s2 = D.push(tg, db, "t2", "b2", log=quiet)
        check("push without changes touches no table", tg.con.execute("SELECT tables FROM rd_sync WHERE sync_id=?", (s2,)).fetchone()[0] == "[]",
              f"{tg.calls - calls} calls")

        # a delta: one row changed, one deleted, one added
        pr = loc.execute("SELECT number, title FROM pr ORDER BY number LIMIT 2").fetchall()
        before_title = pr[0][1]
        loc.execute("UPDATE pr SET title = title || ' (edited)' WHERE number = ?", (pr[0][0],))
        loc.execute("DELETE FROM pr_label WHERE rowid = (SELECT MIN(rowid) FROM pr_label)")
        loc.execute("INSERT INTO feature(id, title) SELECT 'zz_test', 'test feature' WHERE NOT EXISTS (SELECT 1 FROM feature WHERE id='zz_test')")
        loc.commit()
        s3 = D.push(tg, db, "t3", "b3", log=quiet)
        ch = tg.con.execute("SELECT rows_in, rows_out, tables FROM rd_sync WHERE sync_id=?", (s3,)).fetchone()
        check("delta push writes only the changed rows", ch[0] == 2 and ch[1] == 1, f"in={ch[0]} out={ch[1]} {ch[2]}")
        check("delta push: copy equals ops.db", D.verify(tg, db, log=quiet))

        # a push that dies half way: readers keep seeing snapshot 3
        loc.execute("UPDATE pr SET title = 'HALF WAY' WHERE number = ?", (pr[1][0],))
        loc.commit()
        real_q = tg.q
        n = {"c": 0}

        def dying(sql, params=()):
            if sql.startswith("UPDATE rd_meta SET v = ? WHERE k = 'current'"):
                raise RuntimeError("network gone")
            n["c"] += 1
            return real_q(sql, params)
        tg.q = dying
        try:
            D.push(tg, db, "t4", "b4", log=quiet)
            check("half-way push raises", False)
        except RuntimeError:
            pass
        tg.q = real_q
        seen = tg.con.execute("SELECT title FROM pr WHERE number = ?", (pr[1][0],)).fetchone()[0]
        check("half-way push is invisible to readers", seen != "HALF WAY" and tg.con.execute("SELECT v FROM rd_meta WHERE k='current'").fetchone()[0] == s3)
        check("lock released after a failed push", tg.con.execute("SELECT v FROM rd_meta WHERE k='lock'").fetchone()[0] == 0)
        s5 = D.push(tg, db, "t5", "b5", log=quiet)
        check("next push cleans the half-way rows and goes live", D.verify(tg, db, log=quiet) and s5 == 5)
        check("no duplicate current rows after the clean-up",
              tg.con.execute("SELECT COUNT(*) FROM (SELECT _k FROM h_pr WHERE _to IS NULL GROUP BY _k HAVING COUNT(*) > 1)").fetchone()[0] == 0)

        # rollback to snapshot 3, then a push brings the copy back to ops.db
        D.rollback(tg, 3)
        t3 = tg.con.execute("SELECT title FROM pr WHERE number = ?", (pr[0][0],)).fetchone()[0]
        check("rollback: readers see snapshot 3", t3 == before_title + " (edited)" and
              tg.con.execute("SELECT title FROM pr WHERE number = ?", (pr[1][0],)).fetchone()[0] != "HALF WAY")
        s6 = D.push(tg, db, "t6", "b6", log=quiet)
        check("push after rollback: copy equals ops.db", D.verify(tg, db, log=quiet), f"snapshot {s6}")

        # schema change: a new column
        loc.execute("ALTER TABLE feature ADD COLUMN owner TEXT")
        loc.execute("UPDATE feature SET owner = 'qa' WHERE id = 'zz_test'")
        loc.commit()
        D.push(tg, db, "t7", "b7", log=quiet)
        check("new column reaches the copy", tg.con.execute("SELECT owner FROM feature WHERE id='zz_test'").fetchone()[0] == "qa")
        check("after the schema change: copy equals ops.db", D.verify(tg, db, log=quiet))

        # review 4.1: a change of bookkeeping columns only (an ingest re-stamping snapshot_id) writes nothing
        loc.execute("UPDATE bk_build SET snapshot_id = COALESCE(snapshot_id, 0) + 1")
        loc.execute("UPDATE pr SET snapshot_id = COALESCE(snapshot_id, 0) + 1")
        loc.commit()
        s8 = D.push(tg, db, "t8", "b8", log=quiet)
        r8 = tg.con.execute("SELECT rows_in, rows_out FROM rd_sync WHERE sync_id=?", (s8,)).fetchone()
        check("re-stamped snapshot_id only: no row written", tuple(r8) == (0, 0), f"in={r8[0]} out={r8[1]}")
        check("re-stamped snapshot_id only: verify still equal", D.verify(tg, db, log=quiet))

        # review 4.4: verify reads the values D1 holds, so a value changed in the copy is caught
        k = tg.con.execute("SELECT _k FROM h_pr WHERE _to IS NULL LIMIT 1").fetchone()[0]
        old_title = tg.con.execute("SELECT title FROM h_pr WHERE _k=? AND _to IS NULL", (k,)).fetchone()[0]
        tg.con.execute("UPDATE h_pr SET title = 'tampered' WHERE _k=? AND _to IS NULL", (k,))
        check("verify catches a value changed in the copy", not D.verify(tg, db, log=quiet))
        tg.con.execute("UPDATE h_pr SET title = ? WHERE _k=? AND _to IS NULL", (old_title, k))

        # review 4.7: unlock never frees a lock someone else holds
        tg.con.execute("UPDATE rd_meta SET v=?, s='other push' WHERE k='lock'", (int(D.time.time()) + 600,))
        D.unlock(tg, "me")
        check("unlock leaves another owner's lock", tg.con.execute("SELECT s FROM rd_meta WHERE k='lock'").fetchone()[0] == "other push")
        try:
            D.push(tg, db, "t9", "b9", log=quiet)
            check("push refuses while another push holds the lock", False)
        except SystemExit:
            check("push refuses while another push holds the lock", True)
        tg.con.execute("UPDATE rd_meta SET v=0, s=NULL WHERE k='lock'")

        # review 4.2: with keep=2, GC raises gc_floor; a second rollback can never reach a collected snapshot
        for i in range(4):
            loc.execute("UPDATE feature SET owner = ? WHERE id = 'zz_test'", (f"o{i}",))
            loc.commit()
            last = D.push(tg, db, f"g{i}", f"g{i}", keep=2, log=quiet)
        floor = tg.con.execute("SELECT v FROM rd_meta WHERE k='gc_floor'").fetchone()[0]
        D.rollback(tg, None, keep=2)
        cur1 = tg.con.execute("SELECT v FROM rd_meta WHERE k='current'").fetchone()[0]
        try:
            D.rollback(tg, None, keep=2)
            cur2 = tg.con.execute("SELECT v FROM rd_meta WHERE k='current'").fetchone()[0]
        except SystemExit:
            cur2 = cur1
        check("second rollback stays above gc_floor", cur1 > floor and cur2 > floor, f"floor {floor}, rollbacks -> {cur1}, {cur2}, last {last}")
        D.push(tg, db, "t10", "b10", log=quiet)
        check("push after rollbacks: copy equals ops.db", D.verify(tg, db, log=quiet))
        # public window: D1 holds only the last N days, local keeps all; verify compares against the same window
        asof = loc.execute("SELECT MAX(created_at) FROM pr").fetchone()[0] or D.now()
        D.push(tg, db, "w1", "w1", log=quiet, as_of=asof, days=30)
        cut = D.window_cut(30, asof)
        n_loc = loc.execute("SELECT COUNT(*) FROM wf_run").fetchone()[0]
        n_pub = tg.con.execute("SELECT COUNT(*) FROM wf_run").fetchone()[0]
        old_pub = tg.con.execute("SELECT COUNT(*) FROM wf_run WHERE created_at < ?", (cut,)).fetchone()[0]
        orphan = tg.con.execute("SELECT COUNT(*) FROM wf_job WHERE run_id NOT IN (SELECT run_id FROM wf_run)").fetchone()[0]
        open_loc = loc.execute("SELECT COUNT(*) FROM pr WHERE merged_at IS NULL AND closed_at IS NULL").fetchone()[0]
        open_pub = tg.con.execute("SELECT COUNT(*) FROM pr WHERE merged_at IS NULL AND closed_at IS NULL").fetchone()[0]
        check("window: D1 drops rows older than the cut, keeps open PRs, no orphan jobs",
              n_pub < n_loc and old_pub == 0 and orphan == 0 and open_pub == open_loc, f"wf_run {n_loc} -> {n_pub}, cut {cut}")
        check("window: verify with the same window says equal", D.verify(tg, db, log=quiet, days=30, as_of=asof))
        check("window: verify without the window sees the difference", not D.verify(tg, db, log=quiet))
        D.push(tg, db, "w2", "w2", log=quiet, as_of=asof, days=30)
        w2 = tg.con.execute("SELECT rows_in, rows_out FROM rd_sync ORDER BY sync_id DESC LIMIT 1").fetchone()
        check("window: same data, same window -> 0 rows written", tuple(w2) == (0, 0), str(tuple(w2)))
        # write budget: a push that would not fit stops before its first write (snapshot and rows unchanged)
        cur_b = tg.con.execute("SELECT v FROM rd_meta WHERE k='current'").fetchone()[0]
        n_b = sum(tg.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for (t,) in
                  tg.con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'h_%'").fetchall())
        os.environ["OPS_D1_DAILY_WRITES"] = "10"
        try:
            D.push(tg, db, "b1", "b1", log=quiet)   # no window: the old rows come back = many writes
            refused = False
        except RuntimeError as e:
            refused = "write budget" in str(e)
        finally:
            del os.environ["OPS_D1_DAILY_WRITES"]
        n_a = sum(tg.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for (t,) in
                  tg.con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'h_%'").fetchall())
        cur_a = tg.con.execute("SELECT v FROM rd_meta WHERE k='current'").fetchone()[0]
        check("budget: an over-budget push writes no row and keeps the snapshot", refused and n_a == n_b and cur_a == cur_b,
              f"refused={refused}, rows {n_b}->{n_a}, current {cur_b}->{cur_a}")
        D.push(tg, db, "b2", "b2", log=quiet)
        check("budget: the next push (in budget) cleans up and goes live", D.verify(tg, db, log=quiet))
        loc.close()
    finally:
        try:
            tg.con.close()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    print("RESULT:", "PASS" if not FAIL else f"FAIL ({len(FAIL)})")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
