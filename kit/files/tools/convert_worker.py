#!/usr/bin/env python3
"""Open one PDF: scan it and, when asked, convert it. Run by convert_sources.py, never by hand.

Reads one JSON request on standard input and prints one JSON answer on standard output. It
needs `pymupdf` (and `pymupdf4llm` to convert), so it runs under the interpreter that has them,
in isolated mode. It makes no network connection and writes only under the output directory
named in the request. The PDF is untrusted: this process is the one that is killed when it runs
too long or prints too much. See docs/kb/source-pipeline.md.
"""
import importlib.util
import json
import os
import re
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_REQUEST = 1 << 20
MAX_OBJECT_TEXT = 1 << 20
MAX_OBJECTS = 2_000_000
MAX_XMP = 1 << 20
MAX_TOC = 5000
GLYPH_TOLERANCE = 0.01  # glyph boxes are float32 differences, good to about 1e-4
OPACITY_TOLERANCE = 1e-6
WHITE = 0.95
MIN_GLYPH_BOX = 1.2
MIN_OPACITY = 0.05
DEFAULT_LIMITS = {"pages": 2000, "text_bytes": 50 * 1024 * 1024, "images": 500}

EMBEDDED_RE = re.compile(r"/(EmbeddedFiles?|EF)(?![A-Za-z0-9])")
ACTIVE_RE = re.compile(r"/(JavaScript|JS|Launch|RichMedia|SubmitForm|ImportData|XFA)(?![A-Za-z0-9])")
ACTION_TYPE_RE = re.compile(r"/S\s*/([A-Za-z0-9]+)")
EXTERNAL_ACTION_RE = re.compile(r"/S\s*/(GoToR|GoToE)(?![A-Za-z0-9])")
REF_RE = re.compile(r"(\d+)\s+\d+\s+R(?![A-Za-z0-9])")
NAME_ESCAPE_RE = re.compile(r"#([0-9A-Fa-f]{2})")
DESTINATION_RE = re.compile(r"/D\s*(\[[^\]]*\]|\d+\s+\d+\s+R|\([^)]*\)|/[A-Za-z0-9]+)")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kbscan = load("kbscan")


class Refused(Exception):
    def __init__(self, reason, message=""):
        super().__init__(reason)
        self.reason = reason
        self.message = message


def answer(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def import_pymupdf():
    try:
        import pymupdf
    except ImportError:
        raise Refused("missing-dependency", "pymupdf") from None
    pymupdf.TOOLS.mupdf_display_errors(False)
    return pymupdf


def import_pymupdf4llm():
    try:
        import pymupdf4llm
    except ImportError:
        raise Refused("missing-dependency", "pymupdf4llm") from None
    return pymupdf4llm


# ---- structure ----------------------------------------------------------------------


def decode_names(text):
    """Undo #xx escapes, so /J#53 reads as /JS: a hostile PDF can spell any name that way."""
    return NAME_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def object_text(doc, xref):
    try:
        return decode_names(doc.xref_object(xref)[:MAX_OBJECT_TEXT])
    except Exception:
        return ""


def values_after(text, key):
    """The raw values written after /key in an object's text (dictionary, array, reference, token)."""
    found = []
    for match in re.finditer(r"/" + key + r"(?![A-Za-z0-9])", text):
        i = match.end()
        while i < len(text) and text[i] in " \r\n\t":
            i += 1
        if text.startswith("<<", i):
            depth, j = 0, i
            while j < len(text):
                if text.startswith("<<", j):
                    depth += 1
                    j += 2
                elif text.startswith(">>", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            found.append(text[i:j])
        elif text.startswith("[", i):
            depth, j = 0, i
            while j < len(text):
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            found.append(text[i:j])
        elif text.startswith("(", i):
            depth, j = 0, i
            while j < len(text):
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            found.append(text[i:j])
        elif text.startswith("<", i):
            end = text.find(">", i)
            found.append(text[i:end + 1] if end != -1 else text[i:])
        else:
            token = re.match(r"\d+\s+\d+\s+R|/[A-Za-z0-9]+|\S+", text[i:])
            if token:
                found.append(token.group(0))
    return found


def pdf_string(value):
    """The text of a PDF literal or hex string value, or None for anything else."""
    value = value.strip()
    try:
        if value.startswith("(") and value.endswith(")"):
            raw = re.sub(r"\\(.)", r"\1", value[1:-1], flags=re.S)
            return raw
        if value.startswith("<") and not value.startswith("<<") and value.endswith(">"):
            digits = re.sub(r"\s+", "", value[1:-1])
            if len(digits) % 2:
                digits += "0"
            data = bytes.fromhex(digits)
            if data[:2] == b"\xfe\xff":
                return data[2:].decode("utf-16-be", "replace")
            return data.decode("latin-1")
    except ValueError:
        return None
    return None


def action_types(doc, value):
    """The /S names of every action reachable from an action value, following references and
    /Next without a depth limit (each object is read once), but not the /D destinations of a
    GoTo (those point at pages, not at actions)."""
    names, seen, pending = set(), set(), [value]
    while pending:
        current = decode_names(pending.pop() or "")
        if current.lstrip().startswith("["):
            names.add("GoTo")  # a bare destination array
            continue
        names |= set(ACTION_TYPE_RE.findall(current))
        plain = DESTINATION_RE.sub("", current)
        for ref in REF_RE.findall(plain):
            xref = int(ref)
            if xref not in seen:
                seen.add(xref)
                pending.append(object_text(doc, xref))
    return names


def scan_structure(doc, collector):
    length = doc.xref_length()
    if length > MAX_OBJECTS:
        raise Refused("too-many-objects", "the file has too many objects")
    try:
        if doc.embfile_count() > 0:
            collector.add("high", "source", "embedded-file")
    except Exception:
        pass
    for xref in range(1, length):
        text = object_text(doc, xref)
        if not text:
            continue
        if EMBEDDED_RE.search(text):
            collector.add("high", "source", "embedded-file")
        if ACTIVE_RE.search(text):
            collector.add("high", "source", "active-content")
        if EXTERNAL_ACTION_RE.search(text):
            collector.add("high", "link", "external-link")
        for value in values_after(text, "URI"):
            uri = pdf_string(value)
            if uri is not None and not kbscan.scheme_allowed(uri):
                collector.add("high", "link", "link-scheme")
        for key in ("OpenAction", "AA"):
            for value in values_after(text, key):
                if action_types(doc, value) - {"GoTo"}:
                    collector.add("high", "source", "active-content")


def luminance(color):
    if not color:
        return 0.0
    if len(color) == 1:
        return float(color[0])
    if len(color) == 3:
        r, g, b = color
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    if len(color) == 4:
        c, m, y, k = color
        return 0.2126 * (1 - c) * (1 - k) + 0.7152 * (1 - m) * (1 - k) + 0.0722 * (1 - y) * (1 - k)
    return 0.0


def backing_shapes(pymupdf, page):
    """Rectangles with a visible fill, or an image, that could sit behind white text."""
    shapes = []
    try:
        for drawing in page.get_drawings():
            fill = drawing.get("fill")
            opacity = drawing.get("fill_opacity")
            if fill is not None and luminance(fill) < WHITE and (1.0 if opacity is None else opacity) >= 0.5:
                shapes.append((pymupdf.Rect(drawing["rect"]), drawing.get("seqno")))
    except Exception:
        pass
    try:
        for image in page.get_image_info():
            shapes.append((pymupdf.Rect(image["bbox"]), None))
    except Exception:
        pass
    return shapes


def hidden_reason(pymupdf, page_rect, span, shapes_for):
    """Why a span of drawn text is hidden from a reader, or None."""
    x0, y0, x1, y1 = span["bbox"]
    if span.get("type") == 3:
        return "invisible"
    if (span.get("opacity") if span.get("opacity") is not None else 1.0) < MIN_OPACITY - OPACITY_TOLERANCE:
        return "transparent"
    dx, dy = span.get("dir") or (1.0, 0.0)
    height = (y1 - y0) if abs(dx) >= abs(dy) else (x1 - x0)
    if height < MIN_GLYPH_BOX - GLYPH_TOLERANCE:
        return "tiny"
    if x1 <= page_rect.x0 or x0 >= page_rect.x1 or y1 <= page_rect.y0 or y0 >= page_rect.y1:
        return "off-page"
    if luminance(span.get("color")) >= WHITE:
        centre = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        for rect, seqno in shapes_for():
            behind = seqno is None or span.get("seqno") is None or seqno < span["seqno"]
            if behind and rect.contains(centre):
                return None
        return "white"
    return None


WORD_FACTORS = (1.5, 1.08)


def span_text(span, factor=1.5):
    """The text of a drawn span. A space is put where the page leaves a gap between glyphs, because
    a kerning array draws the words of a sentence with no space character between them. The gap that
    counts is `factor` times the span's own typical letter gap (and at least 0.15 em), so letter-spaced
    text keeps its words. A second, finer factor catches words set only slightly wider than letters."""
    size = span.get("size") or 10.0
    dx, dy = span.get("dir") or (1.0, 0.0)
    pieces, gaps, previous = [], [], None
    for c in span.get("chars") or ():
        if not 0 < c[0] <= 0x10FFFF:
            continue
        gap = 0.0
        if previous is not None:
            try:
                if abs(dx) >= abs(dy):
                    gap = (c[2][0] - previous[3][2]) if dx >= 0 else (previous[3][0] - c[3][2])
                else:
                    gap = (c[2][1] - previous[3][3]) if dy >= 0 else (previous[3][1] - c[3][3])
            except (TypeError, IndexError):
                gap = 0.0
            gaps.append(gap)
        pieces.append((chr(c[0]), gap))
        previous = c
    median = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
    limit = max(0.15 * size, factor * median)
    return "".join((" " if gap > limit else "") + char for char, gap in pieces)


def raw_uri(doc, link):
    """The URI written in a link's action. MuPDF reads a target without a web scheme (a file:
    URL, a path, www.example.org) as a launch or remote link, so the written URI is read back."""
    xref = link.get("xref")
    if not xref:
        return None
    try:
        kind, value = doc.xref_get_key(xref, "A/URI")
    except Exception:
        return None
    return value if kind == "string" else None


def untraced_count(page_text, trace):
    """How many non-space characters of the page text the text trace does not account for. Both sides
    are NFKC-normalised, so a ligature counts the same on either. Text filled with a pattern, for
    example, is in the page text but absent from the trace."""
    drawn = Counter()
    for span in trace:
        drawn.update(ch for c in span.get("chars") or () if 0 < c[0] <= 0x10FFFF
                     for ch in unicodedata.normalize("NFKC", chr(c[0])) if not ch.isspace())
    page = Counter(ch for ch in unicodedata.normalize("NFKC", page_text) if not ch.isspace())
    return sum((page - drawn).values())


def scan_page(pymupdf, page, collector, budget):
    text = page.get_text("text")
    budget["bytes"] += len(text.encode("utf-8", "replace"))
    if budget["bytes"] > budget["limit"]:
        raise Refused("too-much-text", "extracted text exceeds the limit")
    collector.add_text("text", text)

    cache = {}

    def shapes_for():
        if "shapes" not in cache:
            cache["shapes"] = backing_shapes(pymupdf, page)
        return cache["shapes"]

    try:
        trace = page.get_texttrace()
    except Exception:
        trace = []
    judged = [(span, hidden_reason(pymupdf, page.rect, span, shapes_for)) for span in trace]
    hidden = [span for span, reason in judged if reason]
    shown = [span for span, reason in judged if not reason]
    if hidden:
        collector.add_hidden("hidden text", "\n".join(span_text(span) for span in hidden))
    for factor in WORD_FACTORS:
        if hidden:
            collector.check_phrases("hidden text", "\n".join(span_text(span, factor) for span in hidden), hidden=True)
        if shown:
            collector.check_phrases("text", "\n".join(span_text(span, factor) for span in shown))
    excess = untraced_count(text, trace)
    if excess:
        collector.check_untraced("hidden text", text, excess)

    for link in page.get_links():
        uri = link.get("uri") if link.get("kind") == pymupdf.LINK_URI else raw_uri(page.parent, link)
        if uri is not None:
            if not kbscan.scheme_allowed(uri):
                collector.add("high", "link", "link-scheme")
        elif link.get("kind") in (pymupdf.LINK_LAUNCH, pymupdf.LINK_GOTOR):
            collector.add("high", "link", "external-link")

    annotations = page.annots()
    for annot in annotations or []:
        try:
            if annot.type[1] == "FileAttachment":
                collector.add("high", "source", "embedded-file")
            for value in (annot.info or {}).values():
                if isinstance(value, str) and value:
                    collector.add_text("annotation", value)
        except Exception:
            continue
    try:
        for widget in page.widgets() or []:
            value = widget.field_value
            if isinstance(value, str) and value:
                collector.add_text("annotation", value)
    except Exception:
        pass


def scan_metadata(doc, collector):
    for value in (doc.metadata or {}).values():
        if isinstance(value, str) and value:
            collector.add_text("metadata", value)
    try:
        xmp = doc.get_xml_metadata()
        if isinstance(xmp, str) and xmp:
            collector.add_text("metadata", xmp[:MAX_XMP])
    except Exception:
        pass
    try:
        for entry in doc.get_toc(simple=True)[:MAX_TOC]:
            if len(entry) > 1 and isinstance(entry[1], str):
                collector.add_text("metadata", entry[1])
    except Exception:
        pass


def is_encrypted(doc):
    """True for any encrypted PDF, including one opened with an empty user password."""
    if doc.needs_pass or doc.is_encrypted or (doc.metadata or {}).get("encryption"):
        return True
    try:
        return doc.xref_get_key(-1, "Encrypt")[0] != "null"
    except Exception:
        return False


def open_document(pymupdf, path, limits):
    try:
        with open(path, "rb") as handle:
            head = handle.read(1024)
    except OSError:
        raise Refused("unreadable-pdf", "the file cannot be read") from None
    if b"%PDF-" not in head:
        raise Refused("not-a-pdf", "the file does not start like a PDF")
    try:
        doc = pymupdf.open(path)
    except Exception:
        raise Refused("unreadable-pdf", "the PDF cannot be opened") from None
    if is_encrypted(doc):
        return doc, True
    if doc.page_count > limits["pages"]:
        raise Refused("too-many-pages", "the PDF has more pages than the limit")
    return doc, False


def scan_document(pymupdf, doc, request, limits):
    """Scan an open document and return (collector, pages)."""
    phrases = kbscan.load_phrases(request.get("phrases") or kbscan.default_phrase_path())
    collector = kbscan.Collector(phrases, snippets=bool(request.get("snippets")))
    scan_metadata(doc, collector)
    scan_structure(doc, collector)
    budget = {"bytes": 0, "limit": limits["text_bytes"]}
    for number in range(doc.page_count):
        scan_page(pymupdf, doc.load_page(number), collector, budget)
    return collector, doc.page_count


def summary(collector, pages):
    result = collector.result()
    return {
        "ok": True,
        "pages": pages,
        "level": result.level,
        "scan": result.scan,
        "findings": result.lines(),
        "findings_detail": [list(f) for f in result.findings],
        "suppressed": result.suppressed,
    }


def limits_of(request):
    limits = dict(DEFAULT_LIMITS)
    for key, value in (request.get("limits") or {}).items():
        if key in limits and isinstance(value, int) and not isinstance(value, bool) and value >= (0 if key == "images" else 1):
            limits[key] = value
    return limits


def count_images(doc):
    total = 0
    for number in range(doc.page_count):
        total += len(doc.get_page_images(number))
    return total


IMAGE_LINK = re.compile(r"(!\[[^\]\n]*\]\()([^)\n]*)(\))")
HAS_SCHEME = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.\-]*:|//)")


def relink_images(markdown, names, prefix):
    """Point the links to extracted figures at text/<stem>/img/, whatever path the library wrote.
    A link with a scheme is left alone; it was already judged by the scan."""
    def fix(match):
        target = match.group(2)
        name = os.path.basename(target)
        if name in names and not HAS_SCHEME.match(target.strip()):
            return match.group(1) + prefix + "/" + name + match.group(3)
        return match.group(0)
    return IMAGE_LINK.sub(fix, markdown)


def convert_markdown(pymupdf, doc, request, limits):
    """Markdown with a page marker before each page. Figures are written only when asked."""
    llm = import_pymupdf4llm()
    outdir = request.get("outdir")
    if not isinstance(outdir, str) or not os.path.isdir(outdir):
        raise Refused("bad-request", "no output directory")
    images = bool(request.get("images"))
    image_dir = os.path.join(outdir, "img")
    if images:
        if count_images(doc) > limits["images"]:
            raise Refused("too-many-images", "the PDF has more images than the limit")
        os.mkdir(image_dir)
    try:
        chunks = llm.to_markdown(doc, page_chunks=True, write_images=images, ignore_images=not images,
                                 image_path=image_dir if images else "", image_format="png")
    except MemoryError:
        raise
    except Exception:
        raise Refused("unreadable-pdf", "the PDF cannot be converted") from None
    parts = []
    size = 0
    for number, chunk in enumerate(chunks, start=1):
        text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
        size += len(text.encode("utf-8", "replace"))
        if size > limits["text_bytes"]:
            raise Refused("too-much-text", "converted text exceeds the limit")
        parts.append(f"<!-- page: {number} -->\n\n{text.rstrip()}\n")
    markdown = "\n".join(parts)
    remote = kbscan.has_remote_image_link(markdown)  # judged before any link is rewritten
    found = 0
    if images:
        names = set(os.listdir(image_dir))
        found = len(names)
        if found > limits["images"]:
            raise Refused("too-many-images", "the PDF produced more images than the limit")
        markdown = relink_images(markdown, names, str(request.get("image_prefix") or "img").rstrip("/"))
    return markdown, found, remote, getattr(llm, "__version__", None) or llm.version


def handle(request):
    mode = request.get("mode")
    if mode == "version":
        pymupdf = import_pymupdf()
        llm = import_pymupdf4llm()
        return {"ok": True, "pymupdf": pymupdf.__version__, "pymupdf4llm": getattr(llm, "__version__", None) or llm.version}
    if mode not in ("scan", "convert"):
        raise Refused("bad-request", "unknown mode")
    path = request.get("pdf")
    if not isinstance(path, str) or not path:
        raise Refused("bad-request", "no PDF named")
    limits = limits_of(request)
    override = mode == "convert" and bool(request.get("override"))
    pymupdf = import_pymupdf()
    doc, encrypted = open_document(pymupdf, path, limits)
    try:
        if encrypted and (doc.needs_pass or not override):
            if doc.needs_pass and override:
                raise Refused("unreadable-pdf", "the PDF needs a password")
            collector = kbscan.Collector([], snippets=False)
            collector.add("high", "source", "encrypted")
            return summary(collector, 0)
        collector, pages = scan_document(pymupdf, doc, request, limits)
        if encrypted:
            collector.add("high", "source", "encrypted")
        if mode == "scan" or (collector.result().level == "high" and not override):
            return summary(collector, pages)
        markdown, images, remote, version = convert_markdown(pymupdf, doc, request, limits)
        if remote:
            collector.add("high", "link", "remote-image-link")
            if not override:
                return summary(collector, pages)
        with open(os.path.join(request["outdir"], "out.md"), "x", encoding="utf-8") as handle:
            handle.write(markdown)
        answer = summary(collector, pages)
        answer.update({"markdown": "out.md", "images": images, "pymupdf4llm": version})
        return answer
    finally:
        doc.close()


def main():
    try:
        raw = sys.stdin.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise Refused("bad-request", "request too large")
        try:
            request = json.loads(raw)
        except ValueError:
            raise Refused("bad-request", "request is not JSON") from None
        if not isinstance(request, dict):
            raise Refused("bad-request", "request is not an object")
        answer(handle(request))
        return 0
    except Refused as refusal:
        answer({"ok": False, "reason": refusal.reason, "message": refusal.message})
        return 0
    except kbscan.PhraseListError as exc:
        answer({"ok": False, "reason": "phrase-list", "message": str(exc)})
        return 0
    except MemoryError:
        answer({"ok": False, "reason": "out-of-memory", "message": "the PDF needs too much memory"})
        return 0
    except Exception as exc:
        answer({"ok": False, "reason": "unreadable-pdf", "message": type(exc).__name__})
        return 0


if __name__ == "__main__":
    sys.exit(main())
