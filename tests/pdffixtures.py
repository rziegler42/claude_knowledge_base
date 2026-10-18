"""Hand-assembled PDF fixtures for the scan and conversion tests. Standard library only.

A fixture is built from raw PDF objects so each hostile or borderline feature is exactly the one
under test: white text, tiny text, invisible text, links, actions, attachments, metadata. Nothing
here is committed as a binary; tests build fixtures into temporary directories.
"""


def esc(text):
    """A PDF literal string for Latin-1 text."""
    out = text.encode("latin-1")
    return b"(" + out.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def utf16(text):
    """A PDF hex string holding UTF-16BE text with a byte-order mark."""
    return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode("ascii") + b">"


def number(value):
    return (b"%.4f" % value).rstrip(b"0").rstrip(b".") or b"0"


def color_ops(color):
    if color is None:
        return b""
    return b" ".join(number(c) for c in color) + (b" g\n" if len(color) == 1 else b" rg\n")


class Pdf:
    """Numbered objects, written with a classic cross-reference table."""

    def __init__(self):
        self.bodies = {}
        self.next = 1

    def alloc(self):
        number_ = self.next
        self.next += 1
        return number_

    def put(self, num, body):
        self.bodies[num] = body

    def add(self, body):
        num = self.alloc()
        self.put(num, body)
        return num

    def stream(self, entries, data):
        head = b"<< " + entries + (b" " if entries else b"") + b"/Length " + str(len(data)).encode() + b" >>\nstream\n"
        return self.add(head + data + b"\nendstream")

    def render(self, root, info=None):
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for num in sorted(self.bodies):
            offsets[num] = len(out)
            out += str(num).encode() + b" 0 obj\n" + self.bodies[num] + b"\nendobj\n"
        start = len(out)
        size = max(self.bodies) + 1
        out += b"xref\n0 " + str(size).encode() + b"\n0000000000 65535 f \n"
        for num in range(1, size):
            out += b"%010d 00000 n \n" % offsets[num] if num in offsets else b"0000000000 65535 f \n"
        trailer = b"<< /Size " + str(size).encode() + b" /Root " + str(root).encode() + b" 0 R"
        if info is not None:
            trailer += b" /Info " + str(info).encode() + b" 0 R"
        out += b"trailer\n" + trailer + b" >>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n"
        return bytes(out)


class Page:
    """Content for one page, in drawing order."""

    def __init__(self, width=612, height=792):
        self.width, self.height = width, height
        self.ops = []
        self.states = {}
        self.uses_image = False
        self.uses_pattern = False

    def text(self, x, y, size, string, *, fill=(0,), mode=0, state=None, pattern=False):
        ops = [b"q\n"]
        if state:
            self.states[state[0]] = state[1]
            ops.append(b"/" + state[0].encode() + b" gs\n")
        ops.append(b"BT\n/F1 " + number(size) + b" Tf\n")
        if pattern:
            self.uses_pattern = True
            ops.append(b"/Pattern cs /P1 scn\n")
        else:
            ops.append(color_ops(fill))
        if mode:
            ops.append(str(mode).encode() + b" Tr\n")
        ops.append(b"1 0 0 1 " + number(x) + b" " + number(y) + b" Tm\n")
        ops.append(esc(string) + b" Tj\nET\nQ\n")
        self.ops.append(b"".join(ops))
        return self

    def lines(self, x, y, size, strings, leading=None, **kw):
        leading = leading if leading is not None else size * 1.2
        for index, string in enumerate(strings):
            self.text(x, y - index * leading, size, string, **kw)
        return self

    def rect(self, x, y, w, h, fill=(0,), state=None):
        head = b"q\n"
        if state:
            self.states[state[0]] = state[1]
            head += b"/" + state[0].encode() + b" gs\n"
        self.ops.append(head + color_ops(fill) + b" ".join(number(v) for v in (x, y, w, h)) + b" re f\nQ\n")
        return self

    def raw(self, ops):
        """Append content-stream operators exactly as given."""
        self.ops.append(ops)
        return self

    def image(self, x, y, w, h):
        self.uses_image = True
        self.ops.append(b"q\n" + b" ".join(number(v) for v in (w, 0, 0, h, x, y)) + b" cm\n/Im1 Do\nQ\n")
        return self

    def content(self):
        return b"".join(self.ops)


class Context:
    """What a fixture's configure hook may change."""

    def __init__(self, pdf, catalog, page_nums):
        self.pdf = pdf
        self.catalog = catalog  # list of bytes entries inside the catalog dictionary
        self.page_nums = page_nums
        self.annots = {}  # page index -> list of object numbers
        self.info = {}  # name -> bytes value (a PDF string)

    def annotate(self, body, page=0):
        num = self.pdf.add(body)
        self.annots.setdefault(page, []).append(num)
        return num


def build(pages=None, *, configure=None, info=None, rect=None):
    """Return the bytes of a PDF. `configure(ctx)` may add objects, annotations, and catalog keys."""
    pages = pages or [Page().text(72, 700, 12, "Ordinary visible text.")]
    pdf = Pdf()
    catalog = pdf.alloc()
    tree = pdf.alloc()
    font = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    image = pdf.stream(b"/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8", b"\x80")
    pattern = None
    if any(page.uses_pattern for page in pages):
        pattern = pdf.stream(b"/Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 /BBox [0 0 10 10] "
                             b"/XStep 10 /YStep 10 /Resources << >>", b"1 g 0 0 10 10 re f")
    contents = [pdf.stream(b"", page.content()) for page in pages]
    page_nums = [pdf.alloc() for _ in pages]
    ctx = Context(pdf, [], page_nums)
    if info:
        ctx.info.update(info)
    if configure:
        configure(ctx)
    for index, page in enumerate(pages):
        states = b"".join(b"/" + name.encode() + b" " + body + b" " for name, body in page.states.items())
        resources = b"<< /Font << /F1 " + str(font).encode() + b" 0 R >> "
        if states:
            resources += b"/ExtGState << " + states + b">> "
        if page.uses_image:
            resources += b"/XObject << /Im1 " + str(image).encode() + b" 0 R >> "
        if page.uses_pattern:
            resources += b"/Pattern << /P1 " + str(pattern).encode() + b" 0 R >> "
        resources += b">>"
        annots = ctx.annots.get(index)
        annot_entry = b""
        if annots:
            annot_entry = b" /Annots [" + b" ".join(str(n).encode() + b" 0 R" for n in annots) + b"]"
        box = rect or (0, 0, page.width, page.height)
        pdf.put(page_nums[index],
                b"<< /Type /Page /Parent " + str(tree).encode() + b" 0 R /MediaBox [" +
                b" ".join(number(v) for v in box) + b"] /Contents " + str(contents[index]).encode() +
                b" 0 R /Resources " + resources + annot_entry + b" >>")
    pdf.put(tree, b"<< /Type /Pages /Kids [" + b" ".join(str(n).encode() + b" 0 R" for n in page_nums) +
            b"] /Count " + str(len(page_nums)).encode() + b" >>")
    pdf.put(catalog, b"<< /Type /Catalog /Pages " + str(tree).encode() + b" 0 R " + b" ".join(ctx.catalog) + b" >>")
    info_num = None
    if ctx.info:
        info_num = pdf.add(b"<< " + b" ".join(b"/" + k.encode() + b" " + v for k, v in ctx.info.items()) + b" >>")
    return pdf.render(catalog, info_num)


# ---- annotations and actions ---------------------------------------------------------

def link(uri):
    return (b"<< /Type /Annot /Subtype /Link /Rect [72 600 200 620] /Border [0 0 0] /A << /S /URI /URI " +
            esc(uri) + b" >> >>")


def note(text, subtype=b"Text"):
    return b"<< /Type /Annot /Subtype /" + subtype + b" /Rect [72 500 200 520] /Contents " + utf16(text) + b" >>"


def attach_file(ctx, name="a.txt", data=b"hello"):
    """An embedded file reachable through the catalog's name tree."""
    stream = ctx.pdf.stream(b"/Type /EmbeddedFile", data)
    spec = ctx.pdf.add(b"<< /Type /Filespec /F " + esc(name) + b" /EF << /F " + str(stream).encode() + b" 0 R >> >>")
    return spec


def embed(ctx):
    spec = attach_file(ctx)
    ctx.catalog.append(b"/Names << /EmbeddedFiles << /Names [(a.txt) " + str(spec).encode() + b" 0 R] >> >>")


def attach_annotation(ctx):
    spec = attach_file(ctx)
    ctx.annotate(b"<< /Type /Annot /Subtype /FileAttachment /Rect [10 10 30 30] /FS " + str(spec).encode() + b" 0 R >>")


def open_action(action):
    def configure(ctx):
        ctx.catalog.append(b"/OpenAction " + action)
    return configure


def additional_actions(action):
    def configure(ctx):
        ctx.catalog.append(b"/AA << /WC " + action + b" >>")
    return configure


def page_additional_actions(action):
    def configure(ctx):
        ctx.annotate(b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (f) /Rect [10 10 30 30] /AA << /E " + action + b" >> >>")
    return configure


def combine(*hooks):
    def configure(ctx):
        for hook in hooks:
            hook(ctx)
    return configure


def with_links(*uris):
    def configure(ctx):
        for uri in uris:
            ctx.annotate(link(uri))
    return configure


def with_notes(*texts):
    def configure(ctx):
        for text in texts:
            ctx.annotate(note(text))
    return configure


def with_info(**fields):
    def configure(ctx):
        for key, text in fields.items():
            ctx.info[key] = utf16(text)
    return configure


def action_chain(length, final):
    """An open action that is `length` GoTo actions linked by /Next, ending in `final`."""
    def configure(ctx):
        target = str(ctx.page_nums[0]).encode()
        numbers = [ctx.pdf.alloc() for _ in range(length)]
        for index, num in enumerate(numbers):
            following = numbers[index + 1] if index + 1 < length else None
            nxt = b" /Next " + str(following).encode() + b" 0 R" if following else b" /Next " + final
            ctx.pdf.put(num, b"<< /S /GoTo /D [" + target + b" 0 R /Fit]" + nxt + b" >>")
        ctx.catalog.append(b"/OpenAction " + str(numbers[0]).encode() + b" 0 R")
    return configure
