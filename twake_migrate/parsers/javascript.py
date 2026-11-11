"""Tree-sitter AST parsing and a restricted token-expression interpreter."""
import json
import re

_LANGUAGES = None


def _get_languages():
    global _LANGUAGES
    if _LANGUAGES is None:
        from tree_sitter import Language
        import tree_sitter_javascript
        import tree_sitter_typescript
        _LANGUAGES = {
            'js': Language(tree_sitter_javascript.language()),
            'ts': Language(tree_sitter_typescript.language_typescript()),
            'tsx': Language(tree_sitter_typescript.language_tsx()),
        }
    return _LANGUAGES


def parse(source, language='js'):
    from tree_sitter import Parser
    tree = Parser(_get_languages()[language]).parse(source.encode())
    if tree.root_node.has_error:
        errors = [n for n in descendants(tree.root_node) if n.type == 'ERROR' or n.is_missing]
        raise ValueError(f'Invalid {language} syntax near {errors[0].start_point if errors else tree.root_node.start_point}')
    return tree.root_node

def descendants(node, kind=None):
    if kind is None or node.type == kind:
        yield node
    for child in node.named_children:
        yield from descendants(child, kind)

def text(node):
    return node.text.decode() if node else ''

def string(node):
    # JS string decoding, without eval. Preserve Unicode and handle JSON escapes.
    raw = text(node)
    if node.type not in {'string', 'template_string'}:
        raise ValueError(f'Expected string, got {node.type}')
    if node.type == 'template_string' and any(c.type == 'template_substitution' for c in node.named_children):
        raise ValueError('Dynamic template string is not a static design token')
    body = raw[1:-1]
    def escape(match):
        seq = match[1]
        if seq.startswith('u{'):
            return chr(int(seq[2:-1],16))
        if seq.startswith('u'):
            return chr(int(seq[1:],16))
        if seq.startswith('x'):
            return chr(int(seq[1:],16))
        return {'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f','v':'\v','0':'\0','\n':''}.get(seq,seq)
    return re.sub(r'\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[\s\S])', escape, body)

def prop(node, key):
    if node:
        for pair in node.named_children:
            if pair.type == 'pair' and text(pair.child_by_field_name('key')).strip("'\"") == key:
                return pair.child_by_field_name('value')
    raise ValueError(f'Missing AST property: {key}')

def variable(root, name):
    for node in descendants(root, 'variable_declarator'):
        if text(node.child_by_field_name('name')) == name:
            return node.child_by_field_name('value')
    raise ValueError(f'Missing variable: {name}')

def evaluate(node, env=None):
    env = env or {}
    if node is None:
        raise ValueError('Missing token expression')
    kind = node.type
    if kind == 'parenthesized_expression':
        return evaluate(node.named_children[0], env)
    if kind == 'number':
        value = text(node)
        return float(value) if '.' in value else int(value)
    if kind in {'string','template_string'}:
        return string(node)
    if kind == 'true': return True
    if kind == 'false': return False
    if kind == 'null': return None
    if kind in {'identifier', 'shorthand_property_identifier'} and text(node) in env:
        return env[text(node)]
    if kind == 'unary_expression' and text(node).startswith('-'):
        return -evaluate(node.named_children[-1], env)
    if kind == 'array':
        return [evaluate(n, env) for n in node.named_children]
    if kind == 'object':
        result = {}
        for pair in node.named_children:
            if pair.type == 'comment': continue
            if pair.type == 'shorthand_property_identifier':
                result[text(pair)] = evaluate(pair, env)
                continue
            if pair.type != 'pair': raise ValueError(f'Unsupported object member: {pair.type}')
            key = pair.child_by_field_name('key')
            name = string(key) if key.type == 'string' else text(key)
            result[name] = evaluate(pair.child_by_field_name('value'), env)
        return result
    if kind in {'member_expression','subscript_expression'}:
        obj = evaluate(node.child_by_field_name('object'), env)
        key_node = node.child_by_field_name('property') or node.child_by_field_name('index')
        key = text(key_node) if kind == 'member_expression' else evaluate(key_node, env)
        if isinstance(obj, dict) and str(key) in obj: return obj[str(key)]
        raise ValueError(f'Unknown token reference: {key}')
    if kind == 'call_expression':
        fn = node.child_by_field_name('function')
        args = [evaluate(n, env) for n in node.child_by_field_name('arguments').named_children]
        if text(fn) == 'alpha' and len(args) == 2:
            return {'color':args[0], 'alpha':args[1]}
        if fn.type == 'member_expression' and text(fn.child_by_field_name('property')) == 'join':
            return args[0].join(evaluate(fn.child_by_field_name('object'), env))
    raise ValueError(f'Unsupported token expression: {kind}: {text(node)[:80]}')
