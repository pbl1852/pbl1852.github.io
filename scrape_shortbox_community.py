import html as html_lib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from lxml import html


OUT_DIR = Path("outputs/shortbox_community")
RAW_DIR = Path("community_scrape/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

URLS = {
    "TheQoo": "https://theqoo.net/square/2487689967",
    "DCInside": "https://gall.dcinside.com/board/view/?id=dcbest&no=414021",
    "FMKorea": "https://www.fmkorea.com/9667456984",
}

POSITIVE_KEYWORDS = [
    "재밌", "재미", "웃기", "웃겼", "좋", "잘될", "잘 될", "역대급", "기대",
    "최고", "대박", "레전드", "감동", "보기 좋", "매력", "기부", "착한",
    "잘하", "웃음", "개웃", "개재밌", "킹받", "화려", "잘 만든",
]

NEGATIVE_KEYWORDS = [
    "노잼", "싫", "별로", "아쉽", "억지", "질림", "지루", "망", "그만",
    "싫은", "불편", "오글", "과하", "소재고갈", "재미없", "안봤",
]

FUTURE_CONTENT_KEYWORDS = [
    "다음", "후속", "더 만들어", "만들어줘", "찍어줘", "컨텐츠", "콘텐츠",
    "기대된다", "신혼", "결혼", "군대", "회사", "유부", "시리즈", "포맷",
]


def fetch(url, data=None, referer=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if data is not None:
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read().decode("utf-8", "replace")


def clean_text(value):
    if value is None:
        return ""
    text = html_lib.unescape(str(value))
    text = re.sub(r"<br\\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"http\\S+|www\\.\\S+", " ", text)
    text = re.sub(r"\\s+", " ", text).strip()
    return text


def keyword_hits(text, keywords):
    return [kw for kw in keywords if kw in text]


def add_scores(row):
    text = row["text"]
    pos = keyword_hits(text, POSITIVE_KEYWORDS)
    neg = keyword_hits(text, NEGATIVE_KEYWORDS)
    fut = keyword_hits(text, FUTURE_CONTENT_KEYWORDS)
    row["positive_keywords"] = ", ".join(pos)
    row["negative_keywords"] = ", ".join(neg)
    row["future_content_keywords"] = ", ".join(fut)
    row["positive_keyword_count"] = len(pos)
    row["negative_keyword_count"] = len(neg)
    row["future_keyword_count"] = len(fut)
    row["keyword_score"] = len(pos) * 3 + len(neg) * 3 + len(fut) * 4
    row["engagement_score"] = int(row.get("like_count") or 0) - int(row.get("dislike_count") or 0)
    row["selection_score"] = row["keyword_score"] * 20 + max(row["engagement_score"], 0) + (50 if row.get("is_best") else 0)
    if neg and not pos:
        sentiment = "negative"
    elif pos and not neg:
        sentiment = "positive"
    elif pos and neg:
        sentiment = "mixed"
    else:
        sentiment = "neutral/other"
    row["sentiment_hint"] = sentiment
    return row


def scrape_theqoo():
    rows = []
    for cpage in range(1, 11):
        body = urllib.parse.urlencode(
            {
                "act": "dispTheqooContentCommentListTheqoo",
                "document_srl": "2487689967",
                "cpage": str(cpage),
            }
        ).encode()
        data = fetch("https://theqoo.net/index.php", data=body, referer=URLS["TheQoo"])
        parsed = json.loads(data)
        comments = parsed.get("comment_list") or []
        if not comments:
            break
        for item in comments:
            text = clean_text(item.get("ct"))
            if not text:
                continue
            rows.append(
                {
                    "source": "TheQoo",
                    "post_title": "유튜브 숏박스 장기연애 시리즈가 싫은 이유.txt",
                    "comment_id": item.get("srl", ""),
                    "author": "",
                    "published_at": item.get("rd", ""),
                    "text": text,
                    "url": URLS["TheQoo"],
                    "like_count": 0,
                    "dislike_count": 0,
                    "reply_page": cpage,
                    "is_best": False,
                }
            )
        time.sleep(0.15)
    return rows


def scrape_dcinside():
    page_html = fetch(URLS["DCInside"], referer=URLS["DCInside"])
    (RAW_DIR / "dcinside_latest.html").write_text(page_html, encoding="utf-8")
    token = re.search(r'id="e_s_n_o" name="e_s_n_o" value="([^"]+)"', page_html).group(1)
    rows = []
    seen = set()
    for page in range(1, 4):
        params = {
            "id": "dcbest",
            "no": "414021",
            "cmt_id": "dcbest",
            "cmt_no": "414021",
            "focus_cno": "",
            "focus_pno": "",
            "e_s_n_o": token,
            "comment_page": str(page),
            "sort": "D",
            "prevCnt": "",
            "board_type": "",
            "_GALLTYPE_": "G",
            "secret_article_key": "",
        }
        data = fetch(
            "https://gall.dcinside.com/board/comment/",
            data=urllib.parse.urlencode(params).encode(),
            referer=URLS["DCInside"],
        )
        parsed = json.loads(data)
        comments = parsed.get("comments") or []
        if not comments:
            break
        for item in comments:
            cid = item.get("no", "")
            if cid in seen:
                continue
            seen.add(cid)
            text = clean_text(item.get("memo"))
            if not text:
                continue
            rows.append(
                {
                    "source": "DCInside",
                    "post_title": "실시간 베스트 게시글 댓글",
                    "comment_id": cid,
                    "author": item.get("name", ""),
                    "published_at": item.get("reg_date", ""),
                    "text": text,
                    "url": URLS["DCInside"],
                    "like_count": 0,
                    "dislike_count": 0,
                    "reply_page": page,
                    "is_best": False,
                }
            )
        time.sleep(0.15)
    return rows


def parse_fmkorea_page(page_html, page_url, page_no):
    tree = html.fromstring(page_html)
    title = " ".join(tree.xpath("//h1//text()"))
    title = clean_text(title) or "유튜버 숏박스 근황"
    rows = []
    for li in tree.xpath("//li[contains(concat(' ', normalize-space(@class), ' '), ' fdb_itm ')]"):
        cid = (li.get("id") or "").replace("comment_", "").replace("_", "")
        text_nodes = li.xpath(".//div[contains(@class,'comment-content')]//div[contains(@class,'xe_content')]//text()")
        text = clean_text(" ".join(text_nodes))
        if not text:
            continue
        author = clean_text(" ".join(li.xpath(".//div[contains(@class,'meta')]//a[contains(@class,'member_plate')]//text()")))
        date = clean_text(" ".join(li.xpath(".//span[contains(@class,'date')]//text()")))
        voted = clean_text(" ".join(li.xpath(".//span[contains(@class,'voted_count')]//text()")))
        blamed = clean_text(" ".join(li.xpath(".//span[contains(@class,'blamed_count')]//text()")))
        def to_int(v):
            v = re.sub(r"[^0-9-]", "", v or "")
            return int(v) if v not in ("", "-") else 0
        rows.append(
            {
                "source": "FMKorea",
                "post_title": title,
                "comment_id": cid,
                "author": author,
                "published_at": date,
                "text": text,
                "url": page_url,
                "like_count": to_int(voted),
                "dislike_count": to_int(blamed),
                "reply_page": page_no,
                "is_best": "comment_best" in (li.get("class") or ""),
            }
        )
    return rows


def scrape_fmkorea():
    rows = []
    seen = set()
    for page in [1, 2, 3]:
        url = f"https://www.fmkorea.com/index.php?document_srl=9667456984&mid=humor&cpage={page}#9667456984_comment"
        data = fetch(url, referer=URLS["FMKorea"])
        (RAW_DIR / f"fmkorea_cpage_{page}.html").write_text(data, encoding="utf-8")
        for row in parse_fmkorea_page(data, url, page):
            if row["comment_id"] in seen:
                continue
            seen.add(row["comment_id"])
            rows.append(row)
        time.sleep(0.15)
    return rows


all_rows = scrape_theqoo() + scrape_dcinside() + scrape_fmkorea()
scored_rows = [add_scores(row) for row in all_rows]
df = pd.DataFrame(scored_rows)
df["text_length"] = df["text"].str.len()

selected = df[
    (df["keyword_score"] > 0) | (df["like_count"] >= 20) | (df["is_best"] == True)
].copy()
selected = selected.sort_values(
    ["selection_score", "like_count", "keyword_score"],
    ascending=[False, False, False],
).reset_index(drop=True)

top_positive = selected[selected["sentiment_hint"].isin(["positive", "mixed"])].head(80)
top_negative = selected[selected["sentiment_hint"].isin(["negative", "mixed"])].head(80)

keyword_summary_rows = []
for source, group in df.groupby("source"):
    for label, keywords in [
        ("positive", POSITIVE_KEYWORDS),
        ("negative", NEGATIVE_KEYWORDS),
        ("future_content", FUTURE_CONTENT_KEYWORDS),
    ]:
        joined = " ".join(group["text"].astype(str))
        for kw in keywords:
            count = joined.count(kw)
            if count:
                keyword_summary_rows.append({"source": source, "category": label, "keyword": kw, "count": count})
keyword_summary = pd.DataFrame(keyword_summary_rows).sort_values(["source", "category", "count"], ascending=[True, True, False])

source_summary = (
    df.groupby("source")
    .agg(total_comments=("text", "count"), selected_comments=("keyword_score", lambda s: int((s > 0).sum())), avg_like=("like_count", "mean"), max_like=("like_count", "max"))
    .reset_index()
)
source_summary["avg_like"] = source_summary["avg_like"].round(2)

for name, frame in {
    "all_comments": df,
    "selected_comments": selected,
    "top_positive": top_positive,
    "top_negative": top_negative,
    "keyword_summary": keyword_summary,
    "source_summary": source_summary,
}.items():
    frame.to_json(OUT_DIR / f"{name}.json", orient="records", force_ascii=False, indent=2)
    frame.to_csv(OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

print("all", len(df))
print("selected", len(selected))
print(source_summary.to_string(index=False))
