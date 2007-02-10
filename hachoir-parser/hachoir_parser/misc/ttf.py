"""
TrueType Font parser.

Author: Victor Stinner
Creation date: 2007-02-08
"""

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet, ParserError,
    UInt16, UInt32, Bit, Bits, NullBits,
    String, RawBytes, Bytes, Enum,
    TimestampMac32)
from hachoir_core.endian import BIG_ENDIAN
from hachoir_core.text_handler import hexadecimal, humanFilesize

MIN_NB_TABLE = 3
MAX_NB_TABLE = 30

DIRECTION_NAME = {
    0: "Mixed directional",
    1: "Left to right",
    2: "Left to right + neutrals",
   -1: "Right to left",
   -2: "Right to left + neutrals",
}

NAMEID_NAME = {
    0: "Copyright notice",
    1: "Font family name",
    2: "Font subfamily name",
    3: "Unique font identifier",
    4: "Full font name",
    5: "Version string",
    6: "Postscript name",
    7: "Trademark",
    8: "Manufacturer name",
    9: "Designer",
    10: "Description",
    11: "URL Vendor",
    12: "URL Designer",
    13: "License Description",
    14: "License info URL",
    16: "Preferred Family",
    17: "Prefrred Subfamily",
    18: "Compatible Full",
    19: "Sample text",
    20: "PostScript CID findfont name",
}

PLATFORM_NAME = {
    0: "Unicode",
    1: "Macintosh",
    2: "ISO",
    3: "Microsoft",
    4: "Custom",
}

class TableHeader(FieldSet):
    def createFields(self):
        yield String(self, "tag", 4)
        yield UInt32(self, "checksum", text_handler=hexadecimal)
        yield UInt32(self, "offset")
        yield UInt32(self, "size", text_handler=humanFilesize)

    def createDescription(self):
         return "Table entry: %s (%s)" % (self["tag"].display, self["size"].display)

class NameHeader(FieldSet):
    def createFields(self):
        yield Enum(UInt16(self, "platformID"), PLATFORM_NAME)
        yield UInt16(self, "encodingID")
        yield UInt16(self, "languageID")
        yield Enum(UInt16(self, "nameID"), NAMEID_NAME)
        yield UInt16(self, "length")
        yield UInt16(self, "offset")

    def getCharset(self):
        if self["platformID"].value == 3 and self["encodingID"].value == 1:
            return "UTF-16-BE"
        else:
            return "ASCII"

    def createDescription(self):
        platform = self["platformID"].display
        name = self["nameID"].display
        return "Name record: %s (%s)" % (name, platform)

def parseFontHeader(self):
    yield UInt16(self, "maj_ver", "Major version")
    yield UInt16(self, "min_ver", "Minor version")
    yield UInt16(self, "font_maj_ver", "Font major version")
    yield UInt16(self, "font_min_ver", "Font minor version")
    yield UInt32(self, "checksum", text_handler=hexadecimal)
    yield Bytes(self, "magic", 4, r"Magic string (\x5F\x0F\x3C\xF5)")
    if self["magic"].value != "\x5F\x0F\x3C\xF5":
        raise ParserError("TTF: invalid magic of font header")

    # Flags
    yield Bit(self, "y0", "Baseline at y=0")
    yield Bit(self, "x0", "Left sidebearing point at x=0")
    yield Bit(self, "instr_point", "Instructions may depend on point size")
    yield Bit(self, "ppem", "Force PPEM to integer values for all")
    yield Bit(self, "instr_width", "Instructions may alter advance width")
    yield Bit(self, "vertical", "e laid out vertically?")
    yield NullBits(self, "reserved[]", 1)
    yield Bit(self, "linguistic", "Requires layout for correct linguistic rendering?")
    yield Bit(self, "gx", "Metamorphosis effects?")
    yield Bit(self, "strong", "Contains strong right-to-left glyphs?")
    yield Bit(self, "indic", "contains Indic-style rearrangement effects?")
    yield Bit(self, "lossless", "Data is lossless (Agfa MicroType compression)")
    yield Bit(self, "converted", "Font converted (produce compatible metrics)")
    yield Bit(self, "cleartype", "Optimised for ClearType")
    yield Bits(self, "adobe", 2, "(used by Adobe)")

    yield UInt16(self, "unit_per_em", "Units per em")
    if not(16 <= self["unit_per_em"].value <= 16384):
        raise ParserError("TTF: Invalid unit/em value")
    yield UInt32(self, "created_high")
    yield TimestampMac32(self, "created")
    yield UInt32(self, "modified_high")
    yield TimestampMac32(self, "modified")
    yield UInt16(self, "xmin")
    yield UInt16(self, "ymin")
    yield UInt16(self, "xmax")
    yield UInt16(self, "ymax")

    # Mac style
    yield Bit(self, "bold")
    yield Bit(self, "italic")
    yield Bit(self, "underline")
    yield Bit(self, "outline")
    yield Bit(self, "shadow")
    yield Bit(self, "condensed", "(narrow)")
    yield Bit(self, "extensed")
    yield NullBits(self, "reserved[]", 9)

    yield UInt16(self, "lowest", "Smallest readable size in pixels")
    yield Enum(UInt16(self, "font_dir", "Font direction hint"), DIRECTION_NAME)
    yield Enum(UInt16(self, "ofst_format"), {0: "short offsets", 1: "long"})
    yield UInt16(self, "glyph_format", "(=0)")

def parseNames(self):
    # Read header
    yield UInt16(self, "format")
    if self["format"].value != 0:
        raise ParserError("TTF (names): Invalid format (%u)" % self["format"].value)
    yield UInt16(self, "count")
    yield UInt16(self, "offset")

    # Read name index
    entries = []
    for index in xrange(self["count"].value):
        entry = NameHeader(self, "header[]")
        yield entry
        entries.append(entry)

    # Sort names by their offset
    entries.sort(key=lambda field: field["offset"].value)

    # Read name value
    last = None
    for entry in entries:
        # Skip duplicates values
        new = (entry["offset"].value, entry["length"].value)
        if last and last == new:
            self.error("Skip duplicate %s %s" % (entry.name, new))
            continue
        last = (entry["offset"].value, entry["length"].value)

        # Skip negative offset
        offset = entry["offset"].value + self["offset"].value
        if offset < self.current_size//8:
            self.error("Skip value %s (negative offset)" % entry.name)
            continue

        # Add padding if any
        padding = self.seekByte(offset, relative=True)
        if padding:
            yield padding

        # Read value
        size = entry["length"].value
        if size:
            yield String(self, "value[]", size, entry.description, charset=entry.getCharset())

class Table(FieldSet):
    TAG_INFO = {
        "head": ("header", "Font header", parseFontHeader),
        "name": ("names", "Names", parseNames),
    }

    def __init__(self, parent, name, table, **kw):
        FieldSet.__init__(self, parent, name, **kw)
        self.table = table
        tag = table["tag"].value
        if tag in self.TAG_INFO:
            self._name, self._description, self.parser = self.TAG_INFO[tag]
        else:
            self.parser = None

    def createFields(self):
        if self.parser:
            for field in self.parser(self):
                yield field
        else:
            yield RawBytes(self, "content", self.size//8)

    def createDescription(self):
        return "Table %s (%s)" % (self.table["tag"].value, self.table.path)

class TrueTypeFontFile(Parser):
    endian = BIG_ENDIAN
    tags = {
        "id": "ttf",
        "category": "misc",
        "file_ext": ("ttf",),
        "min_size": 10*8, # FIXME
        "description": "TrueType font",
    }

    def validate(self):
        if self["maj_ver"].value != 1:
            return "Invalid major version (%u)" % self["maj_ver"].value
        if self["min_ver"].value != 0:
            return "Invalid minor version (%u)" % self["min_ver"].value
        if not (MIN_NB_TABLE <= self["nb_table"].value <= MAX_NB_TABLE):
            return "Invalid number of table (%u)" % self["nb_table"].value
        return True

    def createFields(self):
        yield UInt16(self, "maj_ver", "Major version")
        yield UInt16(self, "min_ver", "Minor version")
        yield UInt16(self, "nb_table")
        yield UInt16(self, "search_range")
        yield UInt16(self, "entry_selector")
        yield UInt16(self, "range_shift")
        tables = []
        for index in xrange(self["nb_table"].value):
            table = TableHeader(self, "table_hdr[]")
            yield table
            tables.append(table)
        tables.sort(key=lambda field: field["offset"].value)
        for table in tables:
            padding = self.seekByte(table["offset"].value, null=True)
            if padding:
                yield padding
            size = table["size"].value
            if size:
                yield Table(self, "table[]", table, size=size*8)
        padding = self.seekBit(self.size, null=True)
        if padding:
            yield padding
