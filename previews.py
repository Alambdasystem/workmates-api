"""Safe, bounded previews; originals remain separate downloadable files."""
import re
import textwrap
from pathlib import Path
import xml.etree.ElementTree as ET
from documents import import_document

SVG_TAGS = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'title', 'desc', 'defs', 'marker', 'linearGradient', 'radialGradient', 'stop', 'clipPath', 'mask', 'pattern', 'style'}
SVG_ATTRS = {'id', 'viewBox', 'width', 'height', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'd', 'points', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'opacity', 'fill-opacity', 'stroke-opacity', 'transform', 'font-family', 'font-size', 'font-weight', 'text-anchor', 'dominant-baseline', 'dx', 'dy', 'marker-start', 'marker-mid', 'marker-end', 'markerWidth', 'markerHeight', 'refX', 'refY', 'orient', 'markerUnits', 'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform', 'clip-path', 'preserveAspectRatio', 'class', 'style'}


def sanitize_svg(content):
    if len(content) > 2 * 1024 * 1024 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('Unsupported SVG.')
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise ValueError('Invalid SVG.') from None
    local = lambda name: name.rsplit('}', 1)[-1]
    if local(root.tag) != 'svg':
        raise ValueError('Not an SVG image.')
    nodes = list(root.iter())
    if len(nodes) > 12000:
        raise ValueError('SVG is too complex.')
    def safe_css(value):
        # Keep local marker/fill references, never external resources or CSS imports.
        cleaned = re.sub(r'url\(\s*[\'"]?#[\w:.-]+[\'"]?\s*\)', '', value, flags=re.I)
        return not re.search(r'url\s*\(|@import|@font-face|expression\s*\(|javascript:|https?:|data:|\\|[<>]', cleaned, re.I)
    for node in nodes:
        for child in list(node):
            if local(child.tag) == 'foreignObject':
                # Diagram renderers often use HTML labels. Keep their words as SVG
                # text without retaining HTML, links, scripts or external styles.
                words = ' '.join(''.join(child.itertext()).split())[:600]
                def number(key, default):
                    try:
                        return max(-10000, min(10000, float(child.get(key, str(default)))))
                    except ValueError:
                        return default
                x = number('x', 0) + number('width', 160) / 2
                y = number('y', 0) + number('height', 32) / 2
                lines = textwrap.wrap(words, max(8, min(70, int(number('width', 160) / 7))))[:8] or ['']
                label = ET.Element('{http://www.w3.org/2000/svg}text', {'x': str(x), 'y': str(y - (len(lines)-1)*8 + 5), 'text-anchor': 'middle', 'font-family': 'sans-serif', 'font-size': '14', 'fill': '#294538'})
                for index, line in enumerate(lines):
                    span = ET.SubElement(label, '{http://www.w3.org/2000/svg}tspan', {'x': str(x), 'dy': '0' if index == 0 else '16'})
                    span.text = line
                node.insert(list(node).index(child), label)
            if local(child.tag) not in SVG_TAGS:
                node.remove(child)
        for key, value in list(node.attrib.items()):
            if key not in SVG_ATTRS or not safe_css(value):
                del node.attrib[key]
        if local(node.tag) == 'style' and not safe_css(node.text or ''):
            node.text = ''
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    return ET.tostring(root, encoding='utf-8')


def file_preview(filename, content):
    for signature, mime in ((b'\x89PNG\r\n\x1a\n', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'), (b'GIF87a', 'image/gif'), (b'GIF89a', 'image/gif')):
        if content.startswith(signature):
            return 'image', mime, content
    if content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        return 'image', 'image/webp', content
    suffix = Path(filename).suffix.lower()
    if suffix == '.svg':
        return 'image', 'image/svg+xml', sanitize_svg(content)
    if suffix in ('.docx', '.pdf'):
        try:
            return 'document', 'text/plain', import_document(filename, content)
        except Exception:
            raise ValueError('Document preview unavailable.') from None
    if suffix in ('.txt', '.md', '.csv', '.json', '.py', '.js', '.ts', '.sql', '.yaml', '.yml', '.html', '.xml', '.mmd'):
        try:
            return 'text', 'text/plain', content[:80000].decode('utf-8-sig')[:20000]
        except UnicodeError:
            pass
    raise ValueError('No preview for this format.')
