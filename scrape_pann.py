import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from lxml import html


URLS = [
    "https://pann.nate.com/talk/375405942",
    "https://pann.nate.com/talk/329010006",
    "https://pann.nate.com/talk/373450519",
    "https://pann.nate.com/talk/373118823",
    "https://pann.nate.com/talk/373358445",
]

OUT_DIR = Path("pann_scrape")
OUT_DIR.mkdir(exist_ok=True)


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read().decode("utf-8", errors="replace")


def clean(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    junk = ["본문 바로가기", "댓글", "공유하기", "스크랩", "인쇄하기"]
    for item in junk:
        text = text.replace(item, " ")
    return re.sub(r"\s+", " ", text).strip()


def text_first(tree, xpaths):
    for xp in xpaths:
        vals = tree.xpath(xp)
        vals = [clean(v if isinstance(v, str) else v.text_content()) for v in vals]
        vals = [v for v in vals if v]
        if vals:
            return vals[0]
    return ""


def parse_post(url, html_text):
    tree = html.fromstring(html_text)
    title = text_first(
        tree,
        [
            "//h1/text()",
            "//h2/text()",
            "//meta[@property='og:title']/@content",
            "//title/text()",
        ],
    )
    body = text_first(
        tree,
        [
            "//*[@id='contentArea']//text()",
            "//*[contains(@class,'viewarea')]//text()",
            "//*[contains(@class,'posting')]//text()",
            "//*[contains(@class,'board_view')]//text()",
        ],
    )

    rows = []
    if body:
        rows.append(
            {
                "source": "NatePann",
                "content_group": "SNL",
                "type": "post",
                "title": title,
                "text": body,
                "url": url,
            }
        )

    return rows, title


def fetch_reply_page(pann_id, page, order="W"):
    data = urllib.parse.urlencode(
        {
            "pann_id": pann_id,
            "reply_id": 0,
            "rereply_id": 0,
            "page": page,
            "penm": "",
            "order": order,
        }
    ).encode()
    req = urllib.request.Request(
        "https://pann.nate.com/talk/reply/load",
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://pann.nate.com/talk/{pann_id}",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read().decode("utf-8", errors="replace")


def parse_reply_html(url, title, reply_html, page):
    tree = html.fromstring(reply_html)
    rows = []
    for item in tree.xpath("//dl[contains(concat(' ', normalize-space(@class), ' '), ' cmt_item ')]"):
        item_id = item.get("id", "")
        comment_id = item_id.replace("content_area_dl_", "")
        author = text_first(item, [".//span[contains(@class,'nameui')]/@title", ".//span[contains(@class,'nameui')]/text()"])
        published_at = text_first(item, [".//dt/i/text()"])
        like_count = text_first(item, [".//dd[contains(@class,'n_good')]/text()"])
        dislike_count = text_first(item, [".//dd[contains(@class,'n_bad')]/text()"])
        comment_text = text_first(item, [".//dd[contains(@class,'usertxt')]//span/text()", ".//dd[contains(@class,'usertxt')]//text()"])
        if not comment_text:
            continue
        rows.append(
            {
                "source": "NatePann",
                "content_group": "SNL",
                "type": "comment",
                "title": title,
                "text": comment_text,
                "url": url,
                "comment_id": comment_id,
                "author": author,
                "published_at": published_at,
                "like_count": int(like_count) if like_count.isdigit() else 0,
                "dislike_count": int(dislike_count) if dislike_count.isdigit() else 0,
                "reply_page": page,
            }
        )
    return rows


def main():
    all_rows = []
    diagnostics = []
    for url in URLS:
        html_text = fetch(url)
        post_id = url.rstrip("/").split("/")[-1]
        (OUT_DIR / f"{post_id}.html").write_text(html_text, encoding="utf-8")
        post_rows, title = parse_post(url, html_text)
        rows = list(post_rows)
        seen_comment_ids = set()
        for page in range(1, 51):
            reply_html = fetch_reply_page(post_id, page)
            reply_rows = parse_reply_html(url, title, reply_html, page)
            new_rows = []
            for row in reply_rows:
                if row["comment_id"] not in seen_comment_ids:
                    seen_comment_ids.add(row["comment_id"])
                    new_rows.append(row)
            rows.extend(new_rows)
            if not new_rows:
                break
            time.sleep(0.25)
        diagnostics.append(
            {
                "url": url,
                "title": title,
                "static_rows": len(rows),
                "comment_rows": sum(1 for row in rows if row["type"] == "comment"),
            }
        )
        all_rows.extend(rows)
        time.sleep(0.5)

    with (OUT_DIR / "natepann_snl_static.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source",
                "content_group",
                "type",
                "title",
                "text",
                "url",
                "comment_id",
                "author",
                "published_at",
                "like_count",
                "dislike_count",
                "reply_page",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    (OUT_DIR / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    print("total rows", len(all_rows))


if __name__ == "__main__":
    main()
