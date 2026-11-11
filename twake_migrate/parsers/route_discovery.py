"""Static object-router discovery with explicit records for dynamic definitions."""
import re
from .javascript import descendants, text, string
from ..core.common import snake


def routes_from_objects(root, source):
    routes, review = [], []
    variables={text(n.child_by_field_name('name')):n.child_by_field_name('value') for n in descendants(root,'variable_declarator')}
    def value(node):
        seen=set()
        while node is not None and node.type=='identifier' and text(node) in variables and text(node) not in seen:
            seen.add(text(node));node=variables[text(node)]
        return node
    def array(node, parent=None):
        node=value(node)
        if node is None or node.type!='array':
            review.append(dict(sourceFile=source,sourceLine=node.start_point.row+1 if node else 1,reason='Dynamic object router/children requires source inventory'))
            return
        for item in node.named_children:
            item=value(item)
            if item is None or item.type!='object':
                review.append(dict(sourceFile=source,sourceLine=node.start_point.row+1,reason='Resolve route spread/factory entry'))
                continue
            props={text(p.child_by_field_name('key')).strip("'\""):p.child_by_field_name('value') for p in item.named_children if p.type=='pair'}
            raw=value(props.get('path'));index=text(props.get('index'))=='true'
            if raw is not None and raw.type not in {'string','template_string'}:
                review.append(dict(sourceFile=source,sourceLine=item.start_point.row+1,reason='Resolve dynamic route path'))
                continue
            try:path=string(raw) if raw is not None else ''
            except ValueError:
                review.append(dict(sourceFile=source,sourceLine=item.start_point.row+1,reason='Resolve dynamic route template'))
                continue
            path=(parent['path'] if index else parent['path'].rstrip('/')+'/'+path if path and not path.startswith('/') else path or parent['path']) if parent else path or '/'
            component=text(props.get('Component'))
            element=props.get('element')
            if element:
                element_node=next((n for n in descendants(element) if n.type in {'jsx_opening_element','jsx_self_closing_element'}),None)
                if element_node:component=text(element_node.child_by_field_name('name'))
            suffix='ROOT' if path=='/' else snake(path.replace(':','BY_'))+('_INDEX' if index else '')
            route=dict(id='ROUTE_'+suffix,path=path,component=component or 'layout',sourceFile=source,sourceLine=item.start_point.row+1,params=re.findall(r':(\w+)',path),parentRouteId=parent['id'] if parent else None)
            if component or raw is not None or index:routes.append(route)
            if 'children' in props:array(props['children'],route)
    for call in descendants(root,'call_expression'):
        if text(call.child_by_field_name('function')).split('.')[-1] not in {'createBrowserRouter','createHashRouter','useRoutes'}:continue
        args=call.child_by_field_name('arguments')
        array(args.named_children[0] if args and args.named_children else None)
    return routes,review
