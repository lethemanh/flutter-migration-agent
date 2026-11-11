"""A11y tree extraction, interactable pruning, DOM reducers, and deterministic action throttling."""
from pathlib import Path
from hashlib import sha256
import re
from urllib.parse import urlsplit
from ..core.common import digest


METRICS = '''() => ({
  viewportWidth: innerWidth, viewportHeight: innerHeight,
  scrollWidth: document.documentElement.scrollWidth,
  hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  overflowingSelectors: [...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > innerWidth + 2).slice(0,10).map(el => el.tagName.toLowerCase()),
  themeAttribute: document.documentElement.getAttribute('data-theme'),
  backgroundColor: getComputedStyle(document.body).backgroundColor,
  textColor: getComputedStyle(document.body).color
})'''

UI_SNAPSHOT = '''() => {
 const all = [...document.querySelectorAll('button,input,select,textarea,a,h1,h2,h3,label,[role],[class*="Mui"]')]
   .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
 const impliedRole = (el) => {
   const explicit = el.getAttribute('role');
   if (explicit) return explicit;
   const tag = el.tagName.toLowerCase();
   if (tag === 'button') return 'button';
   if (tag === 'a' && el.hasAttribute('href')) return 'link';
   if (tag === 'input') return ({checkbox:'checkbox',radio:'radio',search:'searchbox'}[el.type] || 'textbox');
   if (tag === 'textarea') return 'textbox';
   if (tag === 'select') return 'combobox';
   if (/^h[1-6]$/.test(tag)) return 'heading';
   if (tag === 'nav') return 'navigation';
   if (tag === 'main') return 'main';
   if (tag === 'header') return 'banner';
   if (tag === 'footer') return 'contentinfo';
   if (tag === 'ul' || tag === 'ol') return 'list';
   if (tag === 'li') return 'listitem';
   if (tag === 'table') return 'table';
   if (tag === 'tr') return 'row';
   if (tag === 'td' || tag === 'th') return 'cell';
   if (tag === 'dialog') return 'dialog';
   return null;
 };
 let axCount = 0;
 const buildAxTree = (root, depth = 0) => {
   if (!root || depth > 6 || axCount > 150) return [];
   const nodes = [];
   for (const child of root.children || []) {
     if (axCount > 150) break;
     const style = getComputedStyle(child);
     if (style.display === 'none' || style.visibility === 'hidden' || child.getAttribute('aria-hidden') === 'true') continue;
     const role = impliedRole(child);
     const sub = buildAxTree(child, role ? depth + 1 : depth);
     if (role) {
       axCount += 1;
       const label = child.getAttribute('aria-label') || (child.matches('button,a,label,h1,h2,h3,h4,[role=menuitem],[role=tab],[role=heading]') ? child.textContent.trim().slice(0, 120) : null);
       const node = {role};
       if (label) node.name = label;
       if (/^h[1-6]$/i.test(child.tagName)) node.level = Number(child.tagName[1]);
       if (child.matches(':disabled') || child.getAttribute('aria-disabled') === 'true') node.disabled = true;
       if (child.matches(':required') || child.getAttribute('aria-required') === 'true') node.required = true;
       if (child.getAttribute('aria-expanded') !== null) node.expanded = child.getAttribute('aria-expanded') === 'true';
       if (child.getAttribute('aria-selected') !== null) node.selected = child.getAttribute('aria-selected') === 'true';
       if (child.matches('input[type=checkbox],input[type=radio]')) node.checked = Boolean(child.checked);
       if (sub.length) node.children = sub;
       nodes.push(node);
     } else if (sub.length) {
       nodes.push(...sub);
     }
   }
   return nodes;
 };
 const links = [...new Set([...document.querySelectorAll('a[href]')].map(a => {
   try {
     const u = new URL(a.getAttribute('href'), window.location.origin);
     return u.origin === window.location.origin ? u.pathname : null;
   } catch (_) { return null; }
 }).filter(Boolean))].slice(0, 100);
 return {truncated: all.length > 200, discoveredLinks: links, accessibilityTree: buildAxTree(document.body), elements: all.slice(0,200).map(el => {
   const s=getComputedStyle(el), b=el.getBoundingClientRect();
   return {id:el.id || null,testId:el.getAttribute('data-testid'),name:el.getAttribute('name'),
     label:el.matches('button,a,label,h1,h2,h3,[role=menuitem],[role=tab]') ? el.textContent.trim().slice(0,160) : null,tag:el.tagName.toLowerCase(), role:el.getAttribute('role'), type:el.getAttribute('type'),
     accessibleLabel:el.getAttribute('aria-label'), disabled:el.matches(':disabled') || el.getAttribute('aria-disabled')==='true',
     required:el.matches(':required'), readOnly:el.hasAttribute('readonly'),
     rect:{x:b.x,y:b.y,width:b.width,height:b.height},
     styles:Object.fromEntries(['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','borderRadius','padding','margin','gap','borderColor'].map(k=>[k,s[k]]))};
 })};
}'''


def wait_for_deterministic_settle(page, ready_selector=None, timeout_ms=15000):
    """Deterministic action throttling: wait for ready selector or networkidle before inspecting the screen."""
    if ready_selector:
        page.locator(ready_selector).wait_for(state='visible', timeout=timeout_ms)
    elif hasattr(page, 'wait_for_load_state'):
        page.wait_for_load_state('networkidle', timeout=timeout_ms)


def capture_state(page, path: Path):
    """Wait for fonts and paint frames, extract pruned A11y/UI snapshot, and capture a verified 390x844 PNG."""
    from PIL import Image
    page.wait_for_function(
        '''async () => {
            await document.fonts.ready;
            await new Promise(resolve =>
                requestAnimationFrame(() => requestAnimationFrame(resolve)));
            return true;
        }''',
        timeout=15000,
    )
    ui = page.evaluate(UI_SNAPSHOT)
    page.screenshot(path=str(path), full_page=False, animations='disabled')
    with Image.open(path) as image:
        image.load()
        if image.format != 'PNG' or image.size != (390, 844):
            raise ValueError('UI state screenshot must be a valid 390x844 PNG')
    return dict(screenshotSha256=digest(path), ui=ui)


def route_pattern(template):
    segments = re.split(r'(:[A-Za-z_][A-Za-z_0-9]*|\[[A-Za-z_][A-Za-z_0-9]*\])', template)
    return re.compile(''.join('[^/]+' if index % 2 else re.escape(part)
                              for index, part in enumerate(segments)))


def canonical_route(path, templates=()):
    pathname = urlsplit(path).path or '/'
    if pathname in templates:
        return pathname
    for template in templates:
        if route_pattern(template).fullmatch(pathname):
            return template
    return pathname


def crawl_sitemap(page, start_paths, local_url, manifest_routes, max_depth=0, max_pages=25, initial_links=None, state=None):
    """Summarize links observed on directed route captures without following them."""
    templates = tuple(route['path'] for route in manifest_routes)
    visited = list(dict.fromkeys(canonical_route(path, templates) for path in start_paths))
    edges = {}
    for source, links in (initial_links or {}).items():
        for link in links:
            if link.startswith('/') and not link.startswith('//'):
                edge = (canonical_route(source, templates), canonical_route(link, templates))
                edges[edge] = dict(fromPath=edge[0], toPath=edge[1])
    paths = sorted(set(visited) | {target for _, target in edges})
    if state is not None:
        state.visited_urls.update(visited)
    return dict(visitedUrls=visited, maxDepth=0, maxPages=max_pages,
                discoveredLinks=list(edges.values()), allDiscoveredPaths=paths,
                unmappedPaths=[path for path in paths if path not in templates])


class ExplorationClicks:
    """Track no-op elements by route and DOM identity within an exploration run."""

    def __init__(self, templates):
        self.templates = templates
        self.blocked = set()

    def route(self, page):
        return canonical_route(page.url, self.templates)

    def click(self, page, selector, timeout_ms):
        before = self.route(page)
        locator = page.locator(selector)
        identity = locator.evaluate("""element => {
            const path = [];
            for (let node = element; node && node.parentElement; node = node.parentElement) {
                path.push([node.localName, Array.from(node.parentElement.children).indexOf(node)]);
            }
            return JSON.stringify(path);
        }""", timeout=timeout_ms) if hasattr(locator, 'evaluate') else selector
        key = sha256(f'{before}:{identity}'.encode()).hexdigest()
        if key in self.blocked:
            return None
        responses = []

        def on_response(response):
            origin = urlsplit(page.url)
            response_url = urlsplit(response.url)
            if ((response_url.scheme, response_url.netloc) == (origin.scheme, origin.netloc)
                    and response.request.resource_type in ('xhr', 'fetch', 'document')):
                responses.append(True)

        if hasattr(page, 'on'):
            page.on('response', on_response)
        try:
            locator.click(timeout=timeout_ms)
            if not responses and before == self.route(page) and hasattr(page, 'wait_for_timeout'):
                page.wait_for_timeout(min(750, timeout_ms))
        finally:
            if hasattr(page, 'remove_listener'):
                page.remove_listener('response', on_response)
        changed = before != self.route(page) or bool(responses)
        if not changed:
            self.blocked.add(key)
        return changed
