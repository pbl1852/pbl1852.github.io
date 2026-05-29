import json
import re
from pathlib import Path

import pandas as pd


YOUTUBE_PATH = Path("/Users/jeonboyun/Downloads/snl 유튜브 댓글.xlsx")
PANN_PATH = Path("pann_scrape/natepann_snl_static.csv")
OUT_DIR = Path("outputs/snl_combined")
OUT_DIR.mkdir(parents=True, exist_ok=True)


FINAL_COLUMNS = [
    "source",
    "content_group",
    "type",
    "title",
    "text",
    "clean_text",
    "url",
    "video_id",
    "comment_id",
    "author",
    "published_at",
    "like_count",
    "dislike_count",
    "reply_page",
    "text_length",
]


def clean_text(value):
    if pd.isna(value):
        return ""
    text = str(value)
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"\S+@\S+", " ", text)
    text = re.sub(r"[\n\r\t]+", " ", text)
    text = re.sub(r"[^가-힣a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_youtube(df):
    df = df.copy()
    df["source"] = "YouTube"
    df["content_group"] = df.get("content_group", "SNL").fillna("SNL")
    df["type"] = df.get("type", "comment").fillna("comment")
    if "title" not in df.columns:
        df["title"] = ""
    if "text" not in df.columns and "comment" in df.columns:
        df["text"] = df["comment"]
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[FINAL_COLUMNS]


def normalize_pann(df):
    df = df.copy()
    df["source"] = "NatePann"
    df["content_group"] = "SNL"
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[FINAL_COLUMNS]


youtube_df = normalize_youtube(pd.read_excel(YOUTUBE_PATH))
pann_df = normalize_pann(pd.read_csv(PANN_PATH, encoding="utf-8-sig"))

combined_df = pd.concat([youtube_df, pann_df], ignore_index=True)
for frame in [youtube_df, pann_df, combined_df]:
    frame["clean_text"] = frame["text"].apply(clean_text)
    frame["text_length"] = frame["clean_text"].str.len()
    frame["like_count"] = pd.to_numeric(frame["like_count"], errors="coerce").fillna(0).astype(int)
    frame["dislike_count"] = pd.to_numeric(frame["dislike_count"], errors="coerce").fillna(0).astype(int)

combined_df = combined_df[combined_df["clean_text"].str.len() > 0].copy()

source_summary = (
    combined_df.groupby(["source", "type"], dropna=False)
    .agg(
        rows=("text", "count"),
        avg_like_count=("like_count", "mean"),
        max_like_count=("like_count", "max"),
        avg_text_length=("text_length", "mean"),
    )
    .reset_index()
)
source_summary["avg_like_count"] = source_summary["avg_like_count"].round(2)
source_summary["avg_text_length"] = source_summary["avg_text_length"].round(2)

files = {
    "combined_raw": combined_df,
    "youtube_only": combined_df[combined_df["source"] == "YouTube"].copy(),
    "natepann_only": combined_df[combined_df["source"] == "NatePann"].copy(),
    "source_summary": source_summary,
}

for name, frame in files.items():
    path = OUT_DIR / f"{name}.json"
    path.write_text(frame.fillna("").to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    frame.to_csv(OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

print("combined_rows", len(combined_df))
print(source_summary.to_string(index=False))
