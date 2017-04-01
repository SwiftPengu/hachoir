from hachoir.field import FieldSet, RawBytes
from hachoir.stream import StringInputStream


class FragmentGroup:

    def __init__(self, parser):
        self.items = []
        self.parser = parser
        self.args = {}

    def add(self, item):
        self.items.append(item)

    def createInputStream(self):
        # FIXME: Use lazy stream creation
        data = []
        for item in self.items:
            data.append(item["rawdata"].value)
        data = b"".join(data)

        # FIXME: Use smarter code to send arguments
        tags = {"class": self.parser, "args": self.args}
        tags = iter(tags.items())
        return StringInputStream(data, "<fragment group>", tags=tags)


class CustomFragment(FieldSet):

    def __init__(self, parent, name, size, parser, description=None, group=None):
        FieldSet.__init__(self, parent, name, description, size=size)
        if not group:
            group = FragmentGroup(parser)
        self.field_size = size
        self.group = group
        self.group.add(self)

    def createFields(self):
        yield RawBytes(self, "rawdata", self.field_size // 8)

    def _createInputStream(self, **args):
        return self.group.createInputStream()