#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新人オンボーディング（3か月目）タスク進捗レポート生成
データソース: Notion
  A = 登壇テスト後タスクDB（合格直後セットアップ / 目安）
  B = 3ヶ月目研修 main page（合格後オンボ + TTT / 第一目安タイムライン）
ルール:
  - A∪B でタスク統合（(再掲)と先頭番号を除いた名前で重複判定 → 1件に）
  - 完了 = どちらかのリストで✓
  - 締切タグ = Bに在ればBの第一目安を優先、無ければAの目安
  - 締切 = タグ群のうち最も早い締切（合格日+offset / 初登壇前=共通締切）
  - 「おまけ」は母数除外
出力: <repo>/onboarding/index.html （固定URL・毎週上書き / OUT_DIR で変更可）
"""
import json, re, datetime, html, os

# 発行日: 環境変数 REPORT_DATE 優先、無ければ実行日（毎週そのまま回せば当日になる）
_rd = os.environ.get("REPORT_DATE")
REPORT_DATE = datetime.date.fromisoformat(_rd) if _rd else datetime.date.today()
# 初登壇の共通締切（イベント固有なので環境変数で更新可）
DEBUT_DEADLINE = datetime.date.fromisoformat(os.environ.get("DEBUT_DEADLINE", "2026-06-12"))
HERE = os.path.dirname(os.path.abspath(__file__))

OFFSET = {
    "01_合格日": 0, "登壇テスト後すぐ": 0,
    "02_1週間以内": 7, "03_2週間以内": 14,
    "04_1ヶ月以内": 30, "登壇テスト後 1 ヶ月以内": 30,
    "登壇テスト後 2 ヶ月以内": 60,
}
DEBUT_TAGS = {"10_初研修登壇前", "10_初スクール登壇前", "10_研修参画日より前", "10_スクール参画日より前"}
EXCLUDE_TAGS = {"おまけ"}

STAGE_ORDER = ["01_合格日", "02_1週間以内", "03_2週間以内", "04_1ヶ月以内",
               "登壇前", "登壇テスト後 1 ヶ月以内", "登壇テスト後 2 ヶ月以内", "期限未設定"]
STAGE_LABEL = {
    "01_合格日": "合格日", "02_1週間以内": "1週間以内", "03_2週間以内": "2週間以内",
    "04_1ヶ月以内": "1ヶ月以内", "登壇前": "初登壇前",
    "登壇テスト後 1 ヶ月以内": "登壇後1ヶ月", "登壇テスト後 2 ヶ月以内": "登壇後2ヶ月",
    "期限未設定": "期限未設定",
}


def parse_list(raw):
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else [v]
    except Exception:
        return [raw]


def norm(name):
    s = name.replace("(再掲)", "").replace("（再掲）", "")
    s = re.sub(r"^\s*\d+(?:-\d+)?\.?\s*", "", s)   # 先頭の "1." "03-2." 等
    s = re.sub(r"\s+", "", s)
    return s


def resolve(tags, goukaku, debut):
    """締切タグ群 -> (stage_label, deadline, excluded)"""
    tags = set(tags or [])
    cands = []
    for t in tags:
        if t in OFFSET:
            cands.append((goukaku + datetime.timedelta(days=OFFSET[t]), t))
        elif t in DEBUT_TAGS:
            cands.append((debut, "登壇前"))
    if cands:
        cands.sort(key=lambda x: x[0])
        return cands[0][1], cands[0][0], False
    if tags & EXCLUDE_TAGS:
        return "おまけ", None, True
    return "期限未設定", None, False


def build_member(m):
    goukaku = datetime.date.fromisoformat(m["goukaku"])
    debut = datetime.date.fromisoformat(m["debut"]) if m.get("debut") else DEBUT_DEADLINE
    merged = {}
    for src in ("A", "B"):
        for r in m.get(src, []):
            name = r["名前"]
            if "(再掲)" in name or "（再掲）" in name:
                continue  # (再掲) は分母分子の両方から完全除外（全メンバー共通）
            checked = r.get("チェック") == "__YES__"
            tags = parse_list(r.get("第一目安") if src == "B" else r.get("目安"))
            kubun = r.get("区分")
            bunrui = parse_list(r.get("分類"))
            jiki = r.get("時期")
            key = norm(name)
            t = merged.get(key)
            if t is None:
                t = merged[key] = {"name": name, "a_tags": set(), "b_tags": set(),
                                   "checked": False, "src": set(), "kubun": kubun,
                                   "bunrui": set(), "jiki": jiki}
            t["src"].add(src)
            t["checked"] = t["checked"] or checked
            t["bunrui"] |= set(bunrui)
            if src == "A":
                t["a_tags"] |= set(tags)
            else:
                t["b_tags"] |= set(tags)
                if kubun:
                    t["kubun"] = kubun
                if jiki:
                    t["jiki"] = jiki
                if "(再掲)" not in name and "（再掲）" not in name:
                    t["name"] = name

    tasks = []
    for t in merged.values():
        chosen = t["b_tags"] if t["b_tags"] else t["a_tags"]
        stage, dl, excl = resolve(chosen, goukaku, debut)
        overdue = (not t["checked"]) and dl is not None and dl < REPORT_DATE
        due_soon = (not t["checked"]) and dl is not None and REPORT_DATE <= dl <= REPORT_DATE + datetime.timedelta(days=7)
        tasks.append({"name": t["name"], "stage": stage, "checked": t["checked"],
                      "excl": excl, "deadline": dl, "overdue": overdue, "due_soon": due_soon,
                      "src": "".join(sorted(t["src"])), "kubun": t["kubun"],
                      "bunrui": sorted(t["bunrui"]), "jiki": t.get("jiki")})

    counted = [t for t in tasks if not t["excl"]]
    done = sum(1 for t in counted if t["checked"])
    rate = round(done / len(counted) * 100) if counted else 0
    overdue_n = sum(1 for t in counted if t["overdue"])
    due_soon_n = sum(1 for t in counted if t["due_soon"])

    stages = {}
    for t in counted:
        d = stages.setdefault(t["stage"], {"total": 0, "done": 0, "overdue": 0})
        d["total"] += 1
        d["done"] += t["checked"]
        d["overdue"] += t["overdue"]
    bunrui_agg = {}
    for t in counted:
        for b in (t["bunrui"] or ["(未分類)"]):
            d = bunrui_agg.setdefault(b, {"total": 0, "done": 0})
            d["total"] += 1
            d["done"] += t["checked"]

    return {"name": m["name"], "goukaku": goukaku, "debut": debut, "elapsed": (REPORT_DATE - goukaku).days,
            "tasks": tasks, "counted": counted, "done": done, "total": len(counted),
            "rate": rate, "overdue": overdue_n, "due_soon": due_soon_n,
            "stages": stages, "bunrui": bunrui_agg, "omake": [t for t in tasks if t["excl"]]}


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def pbar(rate, color):
    return f'<span class="pbar"><span class="pfill" style="width:{rate}%;background:{color}"></span></span>'


def mini_bar(done, total):
    r = round(done / total * 100) if total else 0
    color = "var(--good)" if r == 100 else ("var(--warn)" if r > 0 else "#cbd5e0")
    return f'<span class="pbar sm"><span class="pfill" style="width:{r}%;background:{color}"></span></span>'


def status_of(m):
    if m["overdue"] > 0:
        return ("status-warn", f"⚠ 遅延 {m['overdue']}件")
    if m["rate"] >= 80:
        return ("status-good", "✓ 順調")
    if m["elapsed"] <= 5:
        return ("status-ok", "立ち上げ中")
    return ("status-ok", "進行中")


def render(members):
    members = sorted(members, key=lambda m: m["goukaku"])
    css = open(os.path.join(HERE, "style.css")).read()
    # 伝言板タブの中身は別ファイル（手編集ソース）。週次再生成では上書きしない。
    dengon_path = os.path.join(HERE, "dengonban.html")
    dengon = open(dengon_path, encoding="utf-8").read() if os.path.exists(dengon_path) else '<p class="meta">（伝言板は準備中）</p>'
    o = []
    o.append(f"""<!DOCTYPE html><html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PMG 新人トレーナー ダッシュボード — {REPORT_DATE}</title>
<style>{css}</style></head><body><div class="container">
<div class="page-head">
<h1 class="page-title">📋 PMG 新人トレーナー ダッシュボード</h1>
<p class="page-sub">登壇テスト合格後の新人トレーナー向け｜伝言板（コミュニケプラン）＋ 3か月オンボ進捗</p>
</div>
<div class="section-tabs">
<button class="section-btn" onclick="showSection('sec-dengon')">📋 伝言板</button>
<button class="section-btn active" onclick="showSection('sec-onbo')">📊 3か月オンボ</button>
</div>
<div id="sec-dengon" class="section-pane">{dengon}</div>
<div id="sec-onbo" class="section-pane active">
<h1>新人オンボーディング（3か月目）タスク進捗</h1>
<p class="meta">発行 {REPORT_DATE}（金曜夕礼用 / 自動更新）｜ 対象 6名 ｜ データ: Notion 登壇テスト後タスク + 3ヶ月目研修（A∪B統合）<br>
締切ルール: 合格日基準（合格日 / +7d / +14d / +30d / +60d）＋ 初登壇前タスク = 各人の初登壇日基準。「おまけ」と「(再掲)」は母数外。どちらかのリストで✓なら完了。</p>""")

    o.append('<h3>全員サマリ</h3><table class="summary-table"><thead><tr>'
             '<th>メンバー</th><th>合格日</th><th>経過</th><th>完了率</th>'
             '<th>遅延</th><th>今週締切</th><th>ステータス</th></tr></thead><tbody>')
    for m in members:
        cls, lbl = status_of(m)
        color = "var(--bad)" if m["overdue"] else ("var(--good)" if m["rate"] >= 80 else "var(--warn)")
        od = f'<span class="bad-n">●{m["overdue"]}件</span>' if m["overdue"] else "—"
        o.append(f'<tr><td><strong>{esc(m["name"])}</strong></td>'
                 f'<td>{m["goukaku"].strftime("%-m/%-d")}</td><td>+{m["elapsed"]}日</td>'
                 f'<td>{pbar(m["rate"], color)}<span class="rate">{m["done"]}/{m["total"]} ({m["rate"]}%)</span></td>'
                 f'<td>{od}</td><td>{m["due_soon"]}件</td>'
                 f'<td><span class="status-card {cls}">{lbl}</span></td></tr>')
    o.append('</tbody></table>')

    o.append('<div class="tabs">')
    for i, m in enumerate(members):
        o.append(f'<button class="tab-btn {"active" if i==0 else ""}" onclick="showTab(\'t{i}\')">{esc(m["name"])}</button>')
    o.append('</div>')

    for i, m in enumerate(members):
        o.append(f'<div id="t{i}" class="tab-content {"active" if i==0 else ""}">')
        o.append(f'<div class="score-bar"><span class="label">完了率</span><span class="value">{m["rate"]}%</span>'
                 f'<span class="label">完了 {m["done"]}/{m["total"]}</span>'
                 f'<span class="label">遅延 {m["overdue"]}件</span>'
                 f'<span class="label">今週締切 {m["due_soon"]}件</span>'
                 f'<span class="label">合格 {m["goukaku"].strftime("%-m/%-d")}（+{m["elapsed"]}日）</span></div>')

        o.append('<h4>タイムライン段階別</h4><table class="eval-table"><thead><tr>'
                 '<th>段階</th><th>締切</th><th>進捗</th><th>遅延</th></tr></thead><tbody>')
        for s in STAGE_ORDER:
            if s not in m["stages"]:
                continue
            d = m["stages"][s]
            if s == "登壇前":
                dl = m["debut"].strftime("%-m/%-d")
            elif s in OFFSET:
                dl = (m["goukaku"] + datetime.timedelta(days=OFFSET[s])).strftime("%-m/%-d")
            else:
                dl = "—"
            od = f'<span class="bad-n">●{d["overdue"]}</span>' if d["overdue"] else "—"
            o.append(f'<tr><td>{STAGE_LABEL.get(s, s)}</td><td>{dl}</td>'
                     f'<td>{mini_bar(d["done"], d["total"])} {d["done"]}/{d["total"]}</td><td>{od}</td></tr>')
        o.append('</tbody></table>')

        o.append('<h4>分類別 完了率</h4><div class="chip-row">')
        for b, d in sorted(m["bunrui"].items()):
            r = round(d["done"] / d["total"] * 100) if d["total"] else 0
            o.append(f'<span class="chip">{esc(b)} <b>{d["done"]}/{d["total"]}</b> {r}%</span>')
        o.append('</div>')

        rem = sorted([t for t in m["counted"] if not t["checked"]],
                     key=lambda t: (t["deadline"] or datetime.date(2099, 1, 1)))
        o.append(f'<h4>残タスク {len(rem)}件（未完了）</h4><table class="eval-table"><thead><tr>'
                 '<th>タスク</th><th>締切</th><th>段階</th><th>区分</th><th>出典</th></tr></thead><tbody>')
        for t in rem:
            rc = "overdue-row" if t["overdue"] else ("soon-row" if t["due_soon"] else "")
            dl = t["deadline"].strftime("%-m/%-d") if t["deadline"] else "—"
            flag = " ⚠" if t["overdue"] else (" ◷" if t["due_soon"] else "")
            o.append(f'<tr class="{rc}"><td>{esc(t["name"])}{flag}</td><td>{dl}</td>'
                     f'<td>{STAGE_LABEL.get(t["stage"], t["stage"])}</td>'
                     f'<td>{esc(t["kubun"] or "")}</td><td><span class="src">{t["src"]}</span></td></tr>')
        o.append('</tbody></table>')

        done_list = [t for t in m["counted"] if t["checked"]]
        o.append(f'<h4 class="muted">完了済み {len(done_list)}件</h4><div class="done-list">')
        o.append(" ".join(f'<span class="done-chip">✓ {esc(t["name"])}</span>' for t in done_list))
        o.append('</div>')

        if m["omake"]:
            o.append('<h4 class="muted">おまけ（母数外）</h4><div class="done-list">')
            o.append(" ".join(f'<span class="omake-chip">{"✓" if t["checked"] else "—"} {esc(t["name"])}</span>' for t in m["omake"]))
            o.append('</div>')
        o.append('</div>')

    o.append("""<div class="footer">自動生成: 新人オンボーディング進捗レポート ／ Notion（登壇テスト後タスクDB + 3ヶ月目研修 main page）統合集計。
凡例: ⚠=締切超過(遅延) ／ ◷=今週締切 ／ 出典 A=登壇テスト後タスク, B=3ヶ月目研修, AB=両方。</div></div></div>
<script>
function showTab(id){
  document.querySelectorAll('#sec-onbo .tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('#sec-onbo .tab-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}
function showSection(id){
  document.querySelectorAll('.section-pane').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.section-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}
</script></body></html>""")
    return "".join(o)


if __name__ == "__main__":
    data = json.load(open(os.path.join(HERE, "data.json")))
    members = [build_member(m) for m in data["members"]]
    out_dir = os.environ.get("OUT_DIR") or os.path.abspath(os.path.join(HERE, "..", "..", "onboarding"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w") as f:
        f.write(render(members))
    for m in sorted(members, key=lambda x: x["goukaku"]):
        print(f'{m["name"]}: {m["done"]}/{m["total"]} ({m["rate"]}%) 遅延{m["overdue"]} 今週{m["due_soon"]}')
    print("WROTE", out_path)
