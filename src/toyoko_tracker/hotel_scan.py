#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import random
import re
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import tqdm as tq

START_CODE = 1
END_CODE = 400
MAX_PASSES = 3
TIMEOUT = 15
PAUSE_MIN, PAUSE_MAX = 0.3, 0.9

BASE = "https://www.toyoko-inn.com"

LANGS = {
    "ja": {
        "path": "",  # 日文无前缀
        "accept": "ja,en;q=0.6",
        "brand_regex": re.compile(r"(東[横橫]INN)\s*", re.IGNORECASE),
    },
    "en": {
        "path": "eng",
        "accept": "en-US,en;q=0.9",
        "brand_regex": re.compile(r"(Toyoko\s*Inn)\s*", re.IGNORECASE),
    },
    "ko": {
        "path": "korea",
        "accept": "ko,ko-KR;q=0.9,en;q=0.3",
        "brand_regex": re.compile(r"(도요코\s*인|토요코\s*인)\s*", re.IGNORECASE),
    },
    "zh_tw": {
        "path": "china",
        "accept": "zh-TW,zh;q=0.9,en;q=0.2",
        "brand_regex": re.compile(r"(東橫INN|東横INN)\s*", re.IGNORECASE),
    },
    "zh_cn": {
        "path": "china_cn",
        "accept": "zh-CN,zh;q=0.9,en;q=0.2",
        "brand_regex": re.compile(r"(东横INN|東横INN)\s*", re.IGNORECASE),
    },
}

HEADERS_COMMON = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# 判定文本是否像目标语言（用字符范围做快速检查）
def looks_like_lang(text: str, lang: str) -> bool:
    if not text:
        return False
    # 含有 CJK / 假名 / 韩文的通用判断
    has_cjk = bool(re.search(r"[\u4E00-\u9FFF]", text))
    has_kana = bool(re.search(r"[\u3040-\u30FF]", text))
    has_hangul = bool(re.search(r"[\uAC00-\uD7AF]", text))

    if lang == "en":
        # 英文里不应包含 CJK 或韩文/假名（允许数字、空格、符号、No.1 等）
        return not (has_cjk or has_kana or has_hangul)
    if lang == "ja":
        # 日文通常包含假名或汉字
        return has_kana or has_cjk
    if lang == "ko":
        # 韩文必须有 Hangul
        return has_hangul
    if lang in ("zh_tw", "zh_cn"):
        # 中文至少要有 CJK
        return has_cjk
    return True


def normalize_full(text: str) -> str:
    if not text:
        return text
    # 去掉前缀的【官方】等方括号块
    text = re.sub(r"^\s*【[^】]*】\s*", "", text)
    # 去掉 title 中的 | 或 ｜ 后面的栏目名
    text = re.split(r"[|｜]", text)[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_brand(full_name: str, lang: str) -> str:
    if not full_name:
        return full_name
    # 先移除品牌关键字
    s = LANGS[lang]["brand_regex"].sub("", full_name)
    # 移除可能残留的连接符/顿号点
    s = re.sub(r"^[\s\-–—·・]+", "", s).strip()
    return s


def build_url(code: str, lang: str) -> str:
    path = LANGS[lang]["path"]
    if path:
        return f"{BASE}/{path}/search/detail/{code}/"
    return f"{BASE}/search/detail/{code}/"


def fetch_html(url: str, lang: str) -> str | None:
    # 每个请求一个全新 session，避免 cookie 造成语言串味
    sess = requests.Session()
    headers = HEADERS_COMMON.copy()
    headers["Accept-Language"] = LANGS[lang]["accept"]
    try:
        resp = sess.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            return None
        return resp.text
    except requests.RequestException:
        return None


def extract_names_from_html(html: str, lang: str) -> tuple[str | None, str | None]:
    if not html:
        return None, None
    soup = BeautifulSoup(html, "html.parser")

    full = None

    # 1) H1 最可靠
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        full = h1.get_text(" ", strip=True)

    # 2) og:title / twitter:title
    if not full:
        og = soup.find("meta", attrs={"property": "og:title"}) or soup.find(
            "meta", attrs={"name": "og:title"}
        )
        if og and og.get("content"):
            full = og["content"].strip()

    if not full:
        tw = soup.find("meta", attrs={"name": "twitter:title"})
        if tw and tw.get("content"):
            full = tw["content"].strip()

    # 3) <title>
    if not full and soup.title and soup.title.string:
        full = soup.title.string.strip()

    if full:
        full = normalize_full(full)

    short = strip_brand(full, lang) if full else None

    # 语言一致性校验：如果不像该语言，就当作失败（留给重试）
    if full and not looks_like_lang(full, lang):
        full, short = None, None
    if short and not looks_like_lang(short, lang):
        full, short = None, None

    return full, short


def code_str(n: int) -> str:
    return f"{n:05d}"


def crawl_once(codes, want_fields, results: dict):
    """对 still-missing 的字段进行一次扫描。"""
    updated = 0
    for code in codes:
        fields_needed = want_fields[code]
        if not fields_needed:
            continue

        for lang in list(fields_needed):
            url = build_url(code, lang)
            html = fetch_html(url, lang)
            if not html:
                continue
            full, short = extract_names_from_html(html, lang)
            if not full and not short:
                continue

            rec = results[code]
            if full and not rec[f"name_full_{lang}"]:
                rec[f"name_full_{lang}"] = full
            if short and not rec[f"name_{lang}"]:
                rec[f"name_{lang}"] = short

            # Realtime log of names found for this code/lang
            try:
                shown = []
                if full:
                    shown.append(f"FULL={full}")
                if short and (not full or short != full):
                    shown.append(f"SHORT={short}")
                if shown:
                    tq.write(f"[{code}][{lang}] " + " | ".join(shown))
            except Exception:
                pass

            # 满足两者其一即可视为该语言有值
            if rec[f"name_full_{lang}"] or rec[f"name_{lang}"]:
                fields_needed.remove(lang)
                updated += 1

            # 轻微随机等待，避免触发风控
            time.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))

    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--threads", type=int, default=6, help="Number of concurrent threads (default: 6)")
    args = parser.parse_args()
    codes = [code_str(i) for i in range(START_CODE, END_CODE + 1)]
    # 初始化记录
    results = {
        c: {
            "code": c,
            "has_any": False,
            "name_full_ja": None,
            "name_ja": None,
            "name_full_en": None,
            "name_en": None,
            "name_full_ko": None,
            "name_ko": None,
            "name_full_zh_tw": None,
            "name_zh_tw": None,
            "name_full_zh_cn": None,
            "name_zh_cn": None,
        }
        for c in codes
    }

    # 需要抓取的语言集合（每个 code 单独维护）
    want_fields = {c: set(LANGS.keys()) for c in codes}

    for attempt in range(1, MAX_PASSES + 1):
        need_any = [c for c, langs in want_fields.items() if langs]
        if not need_any:
            break

        with tqdm(total=len(need_any), desc=f"第 {attempt}/{MAX_PASSES} 轮扫描 (threads={args.threads})", ncols=100) as bar:
            with ThreadPoolExecutor(max_workers=max(1, args.threads)) as ex:
                futures = {ex.submit(crawl_once, [c], want_fields, results): c for c in need_any}
                for fut in as_completed(futures):
                    try:
                        _ = fut.result()
                    finally:
                        bar.update(1)

        # 标记 has_any
        for c, rec in results.items():
            has_any = any(
                rec.get(f"name_{lang}") or rec.get(f"name_full_{lang}")
                for lang in LANGS.keys()
            )
            rec["has_any"] = bool(has_any)

        # 简要统计
        remaining = sum(1 for langs in want_fields.values() if langs)
        print(
            f"[round {attempt}] 尚有 {remaining} 个编码存在缺失字段；"
            f"下轮仅对缺失项重试。"
        )

        if attempt < MAX_PASSES and remaining:
            # 指数退避 + 抖动
            wait = min(8, 1.2 ** attempt) + random.random()
            time.sleep(wait)

    # 输出 JSON
    out = [results[c] for c in codes]
    Path("toyoko_hotel_names.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 同时输出一个 CSV（可选）
    try:
        import csv

        with open("toyoko_hotel_names.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            header = ["code", "has_any"] + sum(
                [
                    [f"name_full_{k}", f"name_{k}"]
                    for k in ("ja", "en", "ko", "zh_tw", "zh_cn")
                ],
                [],
            )
            w.writerow(header)
            for c in codes:
                r = results[c]
                row = [r["code"], r["has_any"]]
                for k in ("ja", "en", "ko", "zh_tw", "zh_cn"):
                    row += [r.get(f"name_full_{k}"), r.get(f"name_{k}")]
                w.writerow(row)
    except Exception:
        pass

    print("完成。结果已写入 toyoko_hotel_names.json（和 CSV）。")


if __name__ == "__main__":
    main()