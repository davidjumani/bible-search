#!/usr/bin/env python3
"""Search a Bible text for lines containing given words (CLI twin of index.html).

Usage:
    python3 search.py "in Him" [--version NASB] [--exact-phrase] [--partial-words]
                               [--match-capitals] [--testament ot|nt] [--book john]
                               [--per-page 25] [--page 1] [--counts] [--links]

Versions (files in versions/): NASB, Living (TLB), Amplified (AMP), Message (MSG).

Options (same as the web page):
    --exact-phrase, --adjacent
        Words must appear together, in this order. Without it, words must
        appear in order but may have other words between them.
    --partial-words, --allow-supersets
        Also find words that contain yours (e.g. "man" in "mankind"). Without
        it, only whole words match.
    --match-capitals, --case-sensitive
        Capital letters must match. Without it, matching ignores case. A word
        still matches when it appears entirely uppercase in the text (e.g.
        searching "god" finds "GOD").

Filters and paging (same as the page's sidebar and pager):
    --testament ot|nt   Only show results from one testament.
    --book NAME         Only show results from one book (e.g. "1 john").
    --per-page N        Results per page: 25, 50 or 100 (default 25).
    --page N            Page number, starting at 1.
    --counts            Print match counts per testament and book, like the sidebar.
    --links             Print a BibleGateway "Full Chapter" link under each result.
"""
import argparse
import os
import re
import sys
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))

# name -> (file, BibleGateway version code); abbreviations are accepted too.
VERSIONS = {
    "NASB": ("nasb.txt", "NASB"),
    "Living": ("living.txt", "TLB"),
    "Amplified": ("amplified.txt", "AMP"),
    "Message": ("message.txt", "MSG"),
}
VERSION_ALIASES = {
    "TLB": "Living",
    "AMP": "Amplified",
    "MSG": "Message",
}

BOOKS = [
    "genesis", "exodus", "leviticus", "numbers", "deuteronomy", "joshua", "judges", "ruth",
    "1 samuel", "2 samuel", "1 kings", "2 kings", "1 chronicles", "2 chronicles", "ezra",
    "nehemiah", "esther", "job", "psalms", "proverbs", "ecclesiastes", "song of solomon",
    "isaiah", "jeremiah", "lamentations", "ezekiel", "daniel", "hosea", "joel", "amos",
    "obadiah", "jonah", "micah", "nahum", "habakkuk", "zephaniah", "haggai", "zechariah",
    "malachi",
    "matthew", "mark", "luke", "john", "acts", "romans", "1 corinthians", "2 corinthians",
    "galatians", "ephesians", "philippians", "colossians", "1 thessalonians",
    "2 thessalonians", "1 timothy", "2 timothy", "titus", "philemon", "hebrews", "james",
    "1 peter", "2 peter", "1 john", "2 john", "3 john", "jude", "revelation",
]
OT_COUNT = 39
TESTAMENT_NAMES = {"ot": "Old Testament", "nt": "New Testament"}

SEP = " -- "
REF_RE = re.compile(r"^(.*)\s+(\d+):\d+$")


def word_pattern(word, allow_supersets):
    exact = re.escape(word)
    upper = re.escape(word.upper())
    pat = f"(?:{exact}|{upper})" if upper != exact else exact
    return pat if allow_supersets else rf"\b{pat}\b"


def build_pattern(words, adjacent, allow_supersets, case_sensitive):
    parts = [word_pattern(w, allow_supersets) for w in words]
    # adjacent: words side by side; otherwise allow arbitrary tokens between, in order
    joiner = r"\s+" if adjacent else r"(?:\s+\S+)*?\s+"
    return re.compile(joiner.join(parts), 0 if case_sensitive else re.IGNORECASE)


def build_highlight(words, allow_supersets, case_sensitive):
    parts = [word_pattern(w, allow_supersets) for w in words]
    return re.compile("|".join(parts), 0 if case_sensitive else re.IGNORECASE)


def title_case(s):
    return re.sub(r"\w\S*", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), s)


def split_line(line):
    text, sep, ref = line.rpartition(SEP)
    return (text, ref) if sep else (line, "")


def book_of(ref):
    m = REF_RE.match(ref)
    if not m:
        return None
    book = m.group(1).strip().lower()
    return "psalms" if book == "psalm" else book  # Amplified labels it "Psalm"


def testament_of(book):
    if book not in BOOKS:
        return None
    return "ot" if BOOKS.index(book) < OT_COUNT else "nt"


def chapter_url(ref, bg_version):
    m = REF_RE.match(ref)
    if not m:
        return None
    query = quote(f"{title_case(m.group(1))} {m.group(2)}", safe="")
    return f"https://www.biblegateway.com/passage/?search={query}&version={bg_version}"


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\r\n") for l in f]
    return [l for l in lines if l.strip() and l.strip() != "."]


def resolve_version(name):
    key = name.strip()
    for v in VERSIONS:
        if v.lower() == key.lower():
            return v
    alias = VERSION_ALIASES.get(key.upper())
    if alias:
        return alias
    raise SystemExit(
        f"Unknown version '{name}'. Choose from: "
        + ", ".join(f"{v} ({VERSIONS[v][1]})" for v in VERSIONS)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Search a Bible text for words in lines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("words", help="Words to search for, space separated (e.g. 'in Him')")
    parser.add_argument("--version", default="NASB",
                        help="NASB, Living/TLB, Amplified/AMP or Message/MSG (default NASB)")
    parser.add_argument("--exact-phrase", "--adjacent", dest="adjacent", action="store_true",
                        help="Words must appear together, in this order")
    parser.add_argument("--partial-words", "--allow-supersets", dest="allow_supersets",
                        action="store_true", help="Also find words that contain yours")
    parser.add_argument("--match-capitals", "--case-sensitive", dest="case_sensitive",
                        action="store_true", help="Capital letters must match")
    parser.add_argument("--testament", choices=["ot", "nt"], help="Only this testament")
    parser.add_argument("--book", help="Only this book (e.g. john, '1 corinthians')")
    parser.add_argument("--per-page", type=int, choices=[25, 50, 100], default=25,
                        help="Results per page (default 25)")
    parser.add_argument("--page", type=int, default=1, help="Page number, from 1")
    parser.add_argument("--counts", action="store_true",
                        help="Print match counts per testament and book")
    parser.add_argument("--links", action="store_true",
                        help="Print a BibleGateway 'Full Chapter' link for each result")
    parser.add_argument("--file", help="Search this file instead of a --version file")
    args = parser.parse_args()

    words = args.words.split()
    if not words:
        print("No words given", file=sys.stderr)
        sys.exit(1)

    version = resolve_version(args.version)
    filename, bg_version = VERSIONS[version]
    path = args.file or os.path.join(HERE, "versions", filename)

    book_filter = None
    if args.book:
        book_filter = args.book.strip().lower()
        if book_filter == "psalm":
            book_filter = "psalms"
        if book_filter not in BOOKS:
            raise SystemExit(f"Unknown book '{args.book}'.")

    pattern = build_pattern(words, args.adjacent, args.allow_supersets, args.case_sensitive)
    highlight = build_highlight(words, args.allow_supersets, args.case_sensitive)

    all_matches = []
    for line in load_lines(path):
        if pattern.search(line):
            text, ref = split_line(line)
            all_matches.append((text, ref, book_of(ref)))

    if args.counts:
        t_counts = {"ot": 0, "nt": 0}
        b_counts = {}
        for _, _, book in all_matches:
            t = testament_of(book)
            if t:
                t_counts[t] += 1
            b_counts[book] = b_counts.get(book, 0) + 1
        print("Testament")
        for t in ("ot", "nt"):
            if t_counts[t]:
                print(f"  {TESTAMENT_NAMES[t]}: {t_counts[t]}")
        print("Book")
        for b in BOOKS:
            if b_counts.get(b):
                print(f"  {title_case(b)}: {b_counts[b]}")
        print()

    def passes(m):
        _, _, book = m
        if book_filter and book != book_filter:
            return False
        if args.testament and testament_of(book) != args.testament:
            return False
        return True

    visible = [m for m in all_matches if passes(m)]
    pages = max(1, -(-len(visible) // args.per_page))
    page = min(max(args.page, 1), pages)
    start = (page - 1) * args.per_page

    bold = "\033[1m\033[33m" if sys.stdout.isatty() else ""
    reset = "\033[0m" if sys.stdout.isatty() else ""
    for text, ref, _ in visible[start:start + args.per_page]:
        if not ref:
            print(text)
            print()
            continue
        print(title_case(ref))
        print(highlight.sub(lambda m: f"{bold}{m.group(0)}{reset}", text))
        if args.links:
            url = chapter_url(ref, bg_version)
            if url:
                print(f"Full Chapter: {url}")
        print()

    n = len(visible)
    summary = f'{n} result{"" if n == 1 else "s"} for "{args.words}" in {bg_version}'
    if pages > 1:
        summary += f" (page {page} of {pages})"
    print(summary, file=sys.stderr)


if __name__ == "__main__":
    main()
