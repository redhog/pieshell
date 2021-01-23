class LineList(list):
    def __repr__(self):
        if not len(self):
            return "[]"
        return "[%s]" % (",\n ".join(repr(item) for item in self))
