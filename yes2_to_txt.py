import struct
import sys


class Bintex:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def read_uint8(self):
        v = self.data[self.pos]
        self.pos += 1
        return v

    def read_int(self):
        v = struct.unpack_from(">i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_raw(self, n):
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def skip(self, n):
        self.pos += n

    def read_var_uint(self):
        first = self.data[self.pos]
        self.pos += 1
        if (first & 0x80) == 0:
            return first
        elif (first & 0xC0) == 0x80:
            next0 = self.data[self.pos]; self.pos += 1
            return ((first & 0x3F) << 8) | next0
        elif (first & 0xE0) == 0xC0:
            next1 = self.data[self.pos]; next0 = self.data[self.pos + 1]; self.pos += 2
            return ((first & 0x1F) << 16) | (next1 << 8) | next0
        elif (first & 0xF0) == 0xE0:
            next2 = self.data[self.pos]; next1 = self.data[self.pos + 1]; next0 = self.data[self.pos + 2]; self.pos += 3
            return ((first & 0x0F) << 24) | (next2 << 16) | (next1 << 8) | next0
        elif first == 0xF0:
            next3 = self.data[self.pos]; next2 = self.data[self.pos + 1]; next1 = self.data[self.pos + 2]; next0 = self.data[self.pos + 3]; self.pos += 4
            return (next3 << 24) | (next2 << 16) | (next1 << 8) | next0
        else:
            raise RuntimeError(f"unknown varuint first byte: {first:#x}")

    # ---- value-tagged reads (Bintex "Value" format) ----

    def read_value(self):
        t = self.read_uint8()
        return self._read_value(t)

    def _read_value(self, t):
        if t in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0e, 0x0f,
                  0x10, 0x11, 0x20, 0x21, 0x30, 0x31, 0x40, 0x41):
            return self._read_value_int(t)
        if t in (0x0c, 0x0d) or (0x51 <= t <= 0x5f) or (0x61 <= t <= 0x6f) or t in (0x70, 0x71, 0x72, 0x73):
            return self._read_value_string(t)
        if t in (0xc0, 0xc8, 0xc1, 0xc9, 0xc4, 0xcc):
            return self._read_value_int_array(t)
        if t in (0x90, 0x91):
            return self._read_value_simple_map(t)
        raise RuntimeError(f"value has unknown type: {t:#x}")

    def read_value_int(self):
        return self._read_value_int(self.read_uint8())

    def _read_value_int(self, t):
        if t == 0x0e:
            return 0
        if t in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
            return t
        if t == 0x0f:
            return -1
        if t in (0x10, 0x11):
            a = self.read_uint8()
            return ~a if t == 0x11 else a
        if t in (0x20, 0x21):
            a = (self.read_uint8() << 8) | self.read_uint8()
            return ~a if t == 0x21 else a
        if t in (0x30, 0x31):
            a = (self.read_uint8() << 16) | (self.read_uint8() << 8) | self.read_uint8()
            return ~a if t == 0x31 else a
        if t in (0x40, 0x41):
            a = (self.read_uint8() << 24) | (self.read_uint8() << 16) | (self.read_uint8() << 8) | self.read_uint8()
            return ~a if t == 0x41 else a
        raise RuntimeError(f"value is not int: {t:#x}")

    def read_value_string(self):
        return self._read_value_string(self.read_uint8())

    def _read_value_string(self, t):
        if t == 0x0c:
            return None
        if t == 0x0d:
            return ""
        if 0x51 <= t <= 0x5f:
            return self._read8(t & 0x0f)
        if 0x61 <= t <= 0x6f:
            return self._read16(t & 0x0f)
        if t == 0x70:
            return self._read8(self.read_uint8())
        if t == 0x71:
            return self._read16(self.read_uint8())
        if t == 0x72:
            return self._read8(self.read_int())
        if t == 0x73:
            return self._read16(self.read_int())
        raise RuntimeError(f"value is not string: {t:#x}")

    def _read8(self, length):
        b = self.read_raw(length)
        return b.decode("iso-8859-1")

    def _read16(self, length):
        chars = []
        for _ in range(length):
            hi = self.read_uint8(); lo = self.read_uint8()
            chars.append(chr((hi << 8) | lo))
        return "".join(chars)

    def read_value_int_array(self):
        return self._read_value_int_array(self.read_uint8())

    def _read_value_int_array(self, t):
        if t in (0xc0, 0xc8):
            return self._read_uint8_array(t)
        if t in (0xc1, 0xc9):
            return self._read_uint16_array(t)
        if t == 0xc4:
            length = self.read_uint8()
        elif t == 0xcc:
            length = self.read_int()
        else:
            raise RuntimeError(f"value is not int array: {t:#x}")
        res = []
        for _ in range(length):
            res.append(struct.unpack_from(">i", self.data, self.pos)[0])
            self.pos += 4
        return res

    def _read_uint8_array(self, t):
        length = self.read_uint8() if t == 0xc0 else self.read_int()
        b = self.read_raw(length)
        return list(b)

    def _read_uint16_array(self, t):
        length = self.read_uint8() if t == 0xc1 else self.read_int()
        res = []
        for _ in range(length):
            res.append((self.read_uint8() << 8) | self.read_uint8())
        return res

    def read_value_simple_map(self):
        return self._read_value_simple_map(self.read_uint8())

    def _read_value_simple_map(self, t):
        if t == 0x90:
            return {}
        if t != 0x91:
            raise RuntimeError(f"value is not simple map: {t:#x}")
        size = self.read_uint8()
        res = {}
        for _ in range(size):
            key_len = self.read_uint8()
            k = self._read8(key_len)
            v = self.read_value()
            res[k] = v
        return res


class SectionIndexEntry:
    __slots__ = ("name", "offset", "attributes_size", "content_size")


class Yes2:
    MAGIC = bytes([0x98, 0x58, 0x0D, 0x0A, 0x00, 0x5D, 0xE0, 0x02])

    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        if self.data[:8] != self.MAGIC:
            raise RuntimeError(f"Bad header: {self.data[:8]!r}")
        self._load_section_index()

    def _load_section_index(self):
        bt = Bintex(self.data, 12)
        version = bt.read_uint8()
        if version != 1:
            raise RuntimeError(f"unsupported section index version: {version}")
        section_count = bt.read_int()
        self.entries = {}
        for _ in range(section_count):
            e = SectionIndexEntry()
            name_len = bt.read_uint8()
            e.name = bt.read_raw(name_len).decode("ascii")
            e.offset = bt.read_int()
            e.attributes_size = bt.read_int()
            e.content_size = bt.read_int()
            bt.skip(4)
            self.entries[e.name] = e
        self.section_data_start_offset = bt.pos

    def get_section_attributes(self, name):
        e = self.entries.get(name)
        if e is None:
            return None
        bt = Bintex(self.data, self.section_data_start_offset + e.offset)
        return bt.read_value_simple_map()

    def get_section_content_offset(self, name):
        e = self.entries[name]
        return self.section_data_start_offset + e.offset + e.attributes_size

    def load_version_info(self):
        bt = Bintex(self.data, self.get_section_content_offset("versionInfo"))
        m = bt.read_value_simple_map()
        self.version_info = {
            "shortName": m.get("shortName"),
            "longName": m.get("longName"),
            "description": m.get("description"),
            "locale": m.get("locale"),
            "book_count": m.get("book_count"),
            "hasPericopes": m.get("hasPericopes", 0),
            "textEncoding": m.get("textEncoding", 2),
        }
        return self.version_info

    def load_books(self):
        bt = Bintex(self.data, self.get_section_content_offset("booksInfo"))
        book_count = bt.read_int()
        books = {}
        for _ in range(book_count):
            m = bt.read_value_simple_map()
            book = {
                "bookId": m.get("bookId", -1),
                "shortName": m.get("shortName"),
                "offset": m.get("offset"),
                "chapter_count": m.get("chapter_count"),
                "verse_counts": m.get("verse_counts"),
                "chapter_offsets": m.get("chapter_offsets"),
                "abbreviation": m.get("abbreviation"),
            }
            books[book["bookId"]] = book
        self.books = books
        return books

    def load_chapter_text(self, book, chapter_1):
        attrs = self.get_section_attributes("text")
        if attrs and attrs.get("compression.name"):
            raise RuntimeError(f"unsupported compression: {attrs.get('compression.name')}")

        text_base = self.get_section_content_offset("text")
        content_offset = book["offset"] + book["chapter_offsets"][chapter_1 - 1]
        bt = Bintex(self.data, text_base + content_offset)

        verse_count = book["verse_counts"][chapter_1 - 1]
        codec = "iso-8859-1" if self.version_info["textEncoding"] == 1 else "utf-8"

        verses = []
        for _ in range(verse_count):
            verse_len = bt.read_var_uint()
            raw = bt.read_raw(verse_len)
            verses.append(raw.decode(codec))
        return verses


BOOK_NAME_FIXUPS = {
    "psalm": "psalms",
}


def main():
    in_path = sys.argv[1]
    out_path = sys.argv[2]

    yes = Yes2(in_path)
    yes.load_version_info()
    books = yes.load_books()

    with open(out_path, "w", encoding="utf-8") as out:
        for book_id in sorted(books.keys()):
            book = books[book_id]
            name = (book.get("shortName") or f"Book{book_id}").lower()
            name = BOOK_NAME_FIXUPS.get(name, name)
            for chapter_index in range(1, book["chapter_count"] + 1):
                verses = yes.load_chapter_text(book, chapter_index)
                for verse_index, verse in enumerate(verses, start=1):
                    out.write(f"{verse} -- {name} {chapter_index}:{verse_index}\n.\n")

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
