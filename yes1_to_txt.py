import struct
import sys


class Bintex:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read_uint8(self):
        v = self.data[self.pos]
        self.pos += 1
        return v

    def read_int(self):
        v = struct.unpack_from(">i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_short_string(self):
        length = self.read_uint8()
        if length == 0:
            return ""
        chars = []
        for _ in range(length):
            hi = self.data[self.pos]
            lo = self.data[self.pos + 1]
            self.pos += 2
            chars.append(chr((hi << 8) | lo))
        return "".join(chars)

    def read_long_string(self):
        length = self.read_int()
        if length == 0:
            return ""
        chars = []
        for _ in range(length):
            hi = self.data[self.pos]
            lo = self.data[self.pos + 1]
            self.pos += 2
            chars.append(chr((hi << 8) | lo))
        return "".join(chars)


class Yes1:
    MAGIC = bytes([0x98, 0x58, 0x0D, 0x0A, 0x00, 0x5D, 0xE0, 0x01])

    def __init__(self, path):
        self.f = open(path, "rb")
        data = self.f.read()
        self.data = data
        if data[:8] != self.MAGIC:
            raise RuntimeError(f"Bad header: {data[:8]!r}")

    def find_section(self, name):
        pos = 8
        target = name.encode("ascii")
        while True:
            if pos + 12 > len(self.data):
                return None
            sec_name = self.data[pos:pos + 12]
            pos += 12
            if sec_name == b"____________":
                return None
            size = struct.unpack_from(">i", self.data, pos)[0]
            pos += 4
            if sec_name == target:
                return pos, size
            pos += size

    def read_version_info(self):
        start, size = self.find_section("infoEdisi___")
        bt = Bintex(self.data[start:start + size])
        info = {"encoding": 1, "has_pericopes": 0}
        while True:
            key = bt.read_short_string()
            if key == "versi":
                bt.read_int()
            elif key == "format":
                bt.read_int()
            elif key == "nama":
                info["nama"] = bt.read_short_string()
            elif key in ("shortName", "shortTitle"):
                info["shortName"] = bt.read_short_string()
            elif key == "judul":
                info["longName"] = bt.read_short_string()
            elif key == "keterangan":
                info["description"] = bt.read_long_string()
            elif key == "nkitab":
                info["book_count"] = bt.read_int()
            elif key == "perikopAda":
                info["has_pericopes"] = bt.read_int()
            elif key == "encoding":
                info["encoding"] = bt.read_int()
            elif key == "locale":
                info["locale"] = bt.read_short_string()
            elif key == "end":
                break
            else:
                raise RuntimeError(f"unknown key in version info: {key}")
        self.info = info
        return info

    def load_books(self):
        start, size = self.find_section("infoKitab___")
        bt = Bintex(self.data[start:start + size])
        books = {}
        for _ in range(self.info["book_count"]):
            book = {}
            key_index = 0
            kosong = False
            while True:
                key = bt.read_short_string()
                if key == "versi":
                    bt.read_int()
                elif key == "pos":
                    book["bookId"] = bt.read_int()
                elif key in ("nama", "judul"):
                    book["shortName"] = bt.read_short_string()
                elif key == "npasal":
                    book["chapter_count"] = bt.read_int()
                elif key == "nayat":
                    book["verse_counts"] = [bt.read_uint8() for _ in range(book["chapter_count"])]
                elif key in ("ayatLoncat", "pdbBookNumber"):
                    bt.read_int()
                elif key == "pasal_offset":
                    book["chapter_offsets"] = [bt.read_int() for _ in range(book["chapter_count"] + 1)]
                elif key == "encoding":
                    bt.read_int()
                elif key == "offset":
                    book["offset"] = bt.read_int()
                elif key == "end":
                    if key_index == 0:
                        kosong = True
                    break
                else:
                    print(f"unknown key in book: {key}", file=sys.stderr)
                    break
                key_index += 1
            if not kosong and "bookId" in book:
                books[book["bookId"]] = book
        self.books = books
        return books

    def load_text_base_offset(self):
        start, _size = self.find_section("teks________")
        self.text_base_offset = start

    def load_chapter_text(self, book):
        encoding = self.info.get("encoding", 1)
        codec = "iso-8859-1" if encoding == 1 else "utf-8"
        chapters = []
        for ch in range(book["chapter_count"]):
            lo = self.text_base_offset + book["offset"] + book["chapter_offsets"][ch]
            hi = self.text_base_offset + book["offset"] + book["chapter_offsets"][ch + 1]
            raw = self.data[lo:hi]
            text = raw.decode(codec)
            verses = text.split("\n")
            if verses and verses[-1] == "":
                verses = verses[:-1]
            chapters.append(verses)
        return chapters


def main():
    in_path = sys.argv[1]
    out_path = sys.argv[2]

    yes = Yes1(in_path)
    info = yes.read_version_info()
    books = yes.load_books()
    yes.load_text_base_offset()

    with open(out_path, "w", encoding="utf-8") as out:
        for book_id in sorted(books.keys()):
            book = books[book_id]
            name = book.get("shortName", f"Book{book_id}").lower()
            chapters = yes.load_chapter_text(book)
            for chapter_index, verses in enumerate(chapters, start=1):
                for verse_index, verse in enumerate(verses, start=1):
                    out.write(f"{verse} -- {name} {chapter_index}:{verse_index}\n.\n")

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
