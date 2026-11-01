"""Compact views of the actual compiled workflow."""
import json


def graph_rows(compiled):
    graph = compiled.get_graph()
    # Stable topological order, including the conditional tool branch.
    pending = list(graph.nodes)
    ordered = []
    while pending:
        ready = next((n for n in pending if all(
            e.source in ordered for e in graph.edges if e.target == n)), None)
        if ready is None:
            raise ValueError('Workflow diagram requires an acyclic graph')
        ordered.append(ready)
        pending.remove(ready)
    midpoint = (len(ordered) + 1) // 2
    return graph, [ordered[:midpoint], ordered[midpoint:]]


def graph_dot(compiled, visited):
    graph, rows = graph_rows(compiled)
    q = json.dumps
    lines = ['digraph Workflow {', 'rankdir=TB;',
             'graph [pad="0.2", nodesep="0.25", ranksep="0.65", bgcolor="transparent"];',
             'node [shape=box, style="rounded,filled", color="#B5C5D8", fontname="Helvetica", fontsize=11];',
             'edge [color="#7B90A5", arrowsize=0.65];']
    for node in graph.nodes:
        color = '#D2F2E0' if node in visited else '#EBF1F8'
        if str(node).startswith('__'):
            color = '#E6E6EB'
        label = str(node).strip('_').replace('_', ' ')
        lines.append(f'{q(node)} [label={q(label)}, fillcolor={q(color)}];')
    # Snake layout: first row left-to-right, second row right-to-left.
    display_rows = [rows[0], list(reversed(rows[1]))]
    for index, row in enumerate(display_rows):
        lines.append(f'subgraph row{index} {{ rank=same; ' + '; '.join(q(n) for n in row) + '; }')
        for a, b in zip(row, row[1:]):
            lines.append(f'{q(a)} -> {q(b)} [style=invis, weight=100];')
    if rows[1]:
        lines.append(f'{q(rows[0][-1])} -> {q(rows[1][0])} [style=invis, weight=100];')
    for edge in graph.edges:
        a, b = edge.source, edge.target
        # Reverse the DOT constraint while preserving the real arrow direction.
        reverse = a in rows[1] and b in rows[1]
        if reverse:
            a, b = b, a
        attrs = ['constraint=false']
        if reverse:
            attrs.append('dir=back')
        if getattr(edge, 'conditional', False):
            attrs.append('style=dashed')
        lines.append(f'{q(a)} -> {q(b)} [{", ".join(attrs)}];')
    return '\n'.join(lines + ['}'])


def graph_mermaid(compiled):
    graph, rows = graph_rows(compiled)
    lines = ['flowchart TB']
    for index, row in enumerate(rows):
        lines += [f'  subgraph row{index}[" "]', '    direction LR' if index == 0 else '    direction RL']
        for node in row:
            lines.append(f'    {node}["{str(node).strip("_").replace("_", " ")}"]')
        # Keep same-row edges inside their row declaration.
        for edge in graph.edges:
            if edge.source in row and edge.target in row:
                arrow = '-.->' if getattr(edge, 'conditional', False) else '-->'
                lines.append(f'    {edge.source} {arrow} {edge.target}')
        lines += ['  end', f'  style row{index} fill:transparent,stroke:transparent']
    for edge in graph.edges:
        if not any(edge.source in r and edge.target in r for r in rows):
            lines.append(f'  {edge.source} --> {edge.target}')
    return '\n'.join(lines)
