"""Permission boundaries for unattended browser discovery."""
from contextlib import contextmanager
import re
from urllib.parse import urlsplit


RISKY_ACTION = re.compile(
    r'delete|cancel[\s_-]*subscription|unsubscribe|checkout|purchase|place[\s_-]*order|'
    r'\b(pay|remove|destroy|submit)\b', re.I
)


def same_origin(first, second):
    left, right = urlsplit(first), urlsplit(second)
    return (left.scheme, left.netloc) == (right.scheme, right.netloc)


def needs_confirmation(locator, selector, timeout):
    if RISKY_ACTION.search(selector):
        return True
    if not hasattr(locator, 'evaluate'):
        return True
    return locator.evaluate("""(element, pattern) => {
        const control = element.closest('button, a, input, [role=button], [role=link]') || element;
        if (control.matches('a[href]') && new URL(control.href).origin !== location.origin) return true;
        const labels = [control.textContent, control.getAttribute('aria-label'),
                        control.getAttribute('title'), control.id, control.getAttribute('data-testid'),
                        control.getAttribute('name'), control.getAttribute('href')];
        return control.matches('button[type=submit], input[type=submit], button:not([type])')
            && Boolean(control.form)
            || new RegExp(pattern, 'i').test(labels.filter(Boolean).join(' '));
    }""", RISKY_ACTION.pattern, timeout=timeout)


@contextmanager
def read_only_requests(page, origin):
    """Restrict requests while an unattended interaction is in progress."""
    context = page.context
    pattern = '**/*'

    def restrict(route):
        request = route.request
        if same_origin(request.url, origin) and request.method in {'GET', 'HEAD', 'OPTIONS', 'PROPFIND', 'REPORT'}:
            route.fallback()
        else:
            route.abort()

    context.route(pattern, restrict)
    try:
        yield
    finally:
        context.unroute(pattern, restrict)
