#!/usr/bin/env python3
"""Search nasb.txt for lines containing given words.

Usage:
    python3 search_nasb.py "word1 word2" [--adjacent] [--allow-supersets] [--file nasb.txt]

Flags:
    --adjacent          Words must appear consecutively (e.g. "in him" only
                         matches "in him", not "in the world is him").
                         Without this flag, words must appear in order but
                         may have other words between them.
    --allow-supersets   Match words even inside larger words (e.g. "in"
                         matches "insecure"). Without this flag, only whole
                         words match (word-boundary match).
    --case-sensitive    Match exact case. Without this flag, matching is
                         case-insensitive. A word is also matched if it
                         appears entirely uppercase in the text (e.g.
                         searching "god" still matches "GOD" in the text),
                         even in this mode.
"""
import argparse
import re
import sys


def word_pattern(word, allow_supersets):
    exact = re.escape(word)
    upper = re.escape(word.upper())
    pat = f"(?:{exact}|{upper})" if upper != exact else exact
    return pat if allow_supersets else rf"\b{pat}\b"


def build_pattern(words, adjacent, allow_supersets, case_sensitive):
    parts = [word_pattern(w, allow_supersets) for w in words]

    if adjacent:
        joiner = r"\s+"
    else:
        # allow arbitrary tokens between each word, in order
        joiner = r"(?:\s+\S+)*?\s+"

    pattern = joiner.join(parts)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def search(path, words, adjacent, allow_supersets, case_sensitive):
    pattern = build_pattern(words, adjacent, allow_supersets, case_sensitive)
    matches = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.strip() == ".":
                continue
            if pattern.search(line):
                matches.append(line)
    return matches


def main():
    parser = argparse.ArgumentParser(description="Search nasb.txt for words in lines.")
    parser.add_argument("words", help="Words to search for, space separated (e.g. 'in him')")
    parser.add_argument("--adjacent", action="store_true",
                         help="Require words to be consecutive")
    parser.add_argument("--allow-supersets", action="store_true",
                         help="Allow matching inside larger words")
    parser.add_argument("--case-sensitive", action="store_true",
                         help="Match exact case")
    parser.add_argument("--file", default="nasb.txt", help="Path to search file")
    args = parser.parse_args()

    words = args.words.split()
    if not words:
        print("No words given", file=sys.stderr)
        sys.exit(1)

    matches = search(args.file, words, args.adjacent, args.allow_supersets, args.case_sensitive)
    for line in matches:
        text, _, ref = line.rpartition(" -- ")
        if ref:
            print(ref.title())
            print(text)
            print()
        else:
            print(line)
            print()
    print(f"\n{len(matches)} match(es)", file=sys.stderr)


if __name__ == "__main__":
    main()
