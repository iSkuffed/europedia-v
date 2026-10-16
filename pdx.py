"""Minimal Paradox (Clausewitz/Jomini) script parser.
Block = list of (key, op, value) entries; bare list items are (None, None, value)."""
import re

TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[<>!?]=|[={}<>]|[^\s={}<>#"]+|#[^\n]*')


def tokenize(text):
    for t in TOKEN.findall(text):
        if t[0] != '#':
            yield t


def parse(text):
    toks = list(tokenize(text.lstrip('﻿')))
    pos = 0

    def block():
        nonlocal pos
        out = []
        while pos < len(toks):
            t = toks[pos]
            if t == '}':
                pos += 1
                return out
            pos += 1
            if pos < len(toks) and toks[pos] in ('=', '<', '>', '<=', '>=', '!=', '?='):
                op = toks[pos]
                pos += 1
                out.append((unq(t), op, value()))
            elif t == '{':
                out.append((None, None, block()))
            else:
                out.append((None, None, unq(t)))
        return out

    def value():
        nonlocal pos
        t = toks[pos]
        pos += 1
        if t == '{':
            return block()
        # color = rgb { ... } / hsv { ... }
        if pos < len(toks) and toks[pos] == '{' and t in ('rgb', 'hsv', 'hsv360', 'hex'):
            pos += 1
            return block()
        return unq(t)

    return block()


def unq(t):
    return t[1:-1] if t.startswith('"') else t


def get(block, key, default=None):
    for k, _, v in block:
        if k == key:
            return v
    return default


def items(block):
    return [(k, v) for k, _, v in block if k is not None]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == '__main__':
    b = parse('a = 1 # c\nb = { x = "y z" c d } e >= 2 col = rgb { 1 2 3 }')
    assert get(b, 'a') == '1'
    assert get(get(b, 'b'), 'x') == 'y z'
    assert [v for k, _, v in get(b, 'b') if k is None] == ['c', 'd']
    assert b[2] == ('e', '>=', '2')
    assert [v for _, _, v in get(b, 'col')] == ['1', '2', '3']
    print('ok')
