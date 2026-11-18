#!/usr/bin/env python3
"""4角女神 ネタ探し: 競馬まわりの「よく検索される言葉」を毎日集める。

  python3 collect_trends.py suggest  [--out DIR]   # YouTube検索候補（Mac mini で実行。クラウドからは届かない）
  python3 collect_trends.py youtube  [--out DIR]   # YouTube Data API: 直近48時間で伸びている競馬動画（クラウド可）
  python3 collect_trends.py report   [--out DIR]   # 前日比をまとめた report_YYYYMMDD.md を作る

標準ライブラリだけで動く。結果は DIR/YYYYMMDD/ に保存。
"""
import json, os, re, sys, time, datetime, urllib.parse, urllib.request
from collections import Counter

JST = datetime.timezone(datetime.timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
KANA = list("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわ")

def today():
    return datetime.datetime.now(JST).strftime("%Y%m%d")

def outdir(base, day=None):
    d = os.path.join(base, day or today())
    os.makedirs(d, exist_ok=True)
    return d

def load_seeds():
    with open(os.path.join(HERE, "seeds.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    seeds = list(cfg["always"])
    now = datetime.datetime.now(JST).date()
    for r in cfg["races"]:  # 開催日の14日前〜2日後だけ種語にする
        d = datetime.date.fromisoformat(r["date"])
        if -2 <= (d - now).days <= 14:
            seeds.extend(r["names"])
    return seeds, cfg.get("expand", [])

# ---------- 1) YouTube 検索候補 ----------
def yt_suggest(q):
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=ja&gl=JP&q="
           + urllib.parse.quote(q))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode("utf-8", "replace")
    data = json.loads(raw)
    return [s for s in data[1] if isinstance(s, str)]

def cmd_suggest(base):
    seeds, expand = load_seeds()
    score, seen_by = Counter(), {}
    raw = {}
    for seed in seeds:
        qs = [seed + " "] + ([seed + " " + k for k in KANA] if seed in expand else [])
        for q in qs:
            try:
                sug = yt_suggest(q)
            except Exception as e:
                print("NG", q, e, file=sys.stderr); sug = []
            raw[q] = sug
            for i, s in enumerate(sug):
                s = s.strip()
                if not s or s == seed: continue
                score[s] += max(1, 10 - i)          # 上に出る候補ほど高得点
                seen_by.setdefault(s, set()).add(seed)
            time.sleep(0.35)
    items = [{"phrase": p, "score": sc, "seeds": sorted(seen_by[p])} for p, sc in score.most_common()]
    d = outdir(base)
    with open(os.path.join(d, "suggest.json"), "w", encoding="utf-8") as f:
        json.dump({"at": datetime.datetime.now(JST).isoformat(), "seeds": seeds,
                   "items": items, "raw": raw}, f, ensure_ascii=False, indent=1)
    print(f"suggest: {len(items)} phrases from {len(raw)} queries -> {d}")

# ---------- 2) YouTube Data API ----------
def yt_token():
    acct = os.environ.get("YT_ACCOUNT", "yonkaku").upper()
    cid = os.environ.get("YT_WEB_CLIENT_ID") or os.environ["YT_CLIENT_ID"]
    sec = os.environ.get("YT_WEB_CLIENT_SECRET") or os.environ["YT_CLIENT_SECRET"]
    rt = os.environ[f"YT_{acct}_REFRESH_TOKEN"]
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec, "refresh_token": rt,
                                   "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=20) as r:
        return json.load(r)["access_token"]

def yt_get(tok, path, **params):
    url = "https://www.googleapis.com/youtube/v3/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

STOP = {"競馬", "競馬予想", "予想", "レース", "shorts", "動画", "解説", "結果", "中央競馬", "jra", "keiba", "公式", "最新", "今週"}
YT_QUERIES = ["競馬", "競馬 予想", "競馬 初心者", "競走馬"]   # search.list は1回100ユニット。増やしすぎない

def cmd_youtube(base):
    tok = yt_token()
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seeds, _ = load_seeds()
    race_qs = [s for s in seeds if s not in ("競馬", "競馬 予想", "競馬 初心者", "競走馬", "馬券")][:2]
    vids = {}
    for q in YT_QUERIES + race_qs:
        res = yt_get(tok, "search", part="snippet", q=q, type="video", order="viewCount",
                     publishedAfter=since, regionCode="JP", relevanceLanguage="ja", maxResults=25)
        for it in res.get("items", []):
            vids.setdefault(it["id"]["videoId"], {"q": set()})["q"].add(q)
    ids = list(vids)
    out = []
    for i in range(0, len(ids), 50):
        res = yt_get(tok, "videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i+50]))
        for v in res.get("items", []):
            st = v.get("statistics", {})
            out.append({"id": v["id"], "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                        "published": v["snippet"]["publishedAt"], "views": int(st.get("viewCount", 0)),
                        "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                        "duration": v["contentDetails"]["duration"], "tags": v["snippet"].get("tags", [])[:15],
                        "queries": sorted(vids[v["id"]]["q"])})
    out.sort(key=lambda x: -x["views"])
    # タイトル・タグに多く出る言葉（2文字以上のカタカナ語・漢字語・英字）
    words = Counter()
    for v in out:
        toks = set(re.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}|[A-Za-z][A-Za-z0-9]{1,}", v["title"] + " " + " ".join(v["tags"])))
        for t in toks:
            if t.lower() not in STOP: words[t] += 1
    d = outdir(base)
    with open(os.path.join(d, "youtube.json"), "w", encoding="utf-8") as f:
        json.dump({"at": datetime.datetime.now(JST).isoformat(), "since": since, "videos": out,
                   "words": words.most_common(80)}, f, ensure_ascii=False, indent=1)
    print(f"youtube: {len(out)} videos -> {d}")

# ---------- 3) レポート ----------
def _load(base, day, name):
    p = os.path.join(base, day, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f: return json.load(f)
    return None

def prev_day(base, day):
    days = sorted(x for x in os.listdir(base) if re.fullmatch(r"\d{8}", x) and x < day)
    return days[-1] if days else None

def cmd_report(base):
    day = today(); pd = prev_day(base, day)
    lines = [f"# 競馬の検索トレンド {day[:4]}/{day[4:6]}/{day[6:]}", ""]
    s, ps = _load(base, day, "suggest.json"), (_load(base, pd, "suggest.json") if pd else None)
    if s:
        prev = {x["phrase"]: x["score"] for x in (ps or {}).get("items", [])}
        new = [x for x in s["items"] if x["phrase"] not in prev and x["score"] >= 8] if ps else []
        up = sorted([x for x in s["items"] if x["phrase"] in prev and x["score"] - prev[x["phrase"]] >= 5],
                    key=lambda x: -(x["score"] - prev[x["phrase"]]))
        if ps:
            lines += [f"## 新しく出てきた検索候補（{pd}比）"] + [f"- {x['phrase']}（{x['score']}）" for x in new[:20]] + [""]
            lines += ["## 順位が上がった検索候補"] + [f"- {x['phrase']}（{prev[x['phrase']]}→{x['score']}）" for x in up[:15]] + [""]
        lines += ["## よく検索される言葉 上位30（YouTube検索候補）"] + \
                 [f"{i+1}. {x['phrase']}（{x['score']}）" for i, x in enumerate(s["items"][:30])] + [""]
    else:
        lines += ["（今日の検索候補データなし：Mac mini の収集が動いていない可能性）", ""]
    y = _load(base, day, "youtube.json")
    if y:
        lines += ["## 直近48時間で伸びている競馬動画（YouTube）"] + \
                 [f"- {v['views']:,}回 {v['title']}（{v['channel']}）" for v in y["videos"][:15]] + [""]
        py = _load(base, pd, "youtube.json") if pd else None
        pw = dict((py or {}).get("words", []))
        lines += ["## 動画タイトルに多い言葉"] + \
                 [f"- {w}（{c}本{'' if not py else '・前日' + str(pw.get(w, 0))}）" for w, c in y["words"][:25]] + [""]
    p = os.path.join(base, day, f"report_{day}.md")
    with open(p, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    print(p)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    base = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(HERE, "data")
    os.makedirs(base, exist_ok=True)
    {"suggest": cmd_suggest, "youtube": cmd_youtube, "report": cmd_report}[cmd](base)
