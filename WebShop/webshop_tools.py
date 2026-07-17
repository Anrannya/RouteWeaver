"""Deterministic action-grounding tool for WebShop.

The DoT agent lets an LLM emit the next action (``search[...]`` / ``click[...]`` /
``think[...]``).  Small models frequently return malformed strings or click an
ASIN / option that is not present on the current page, which makes the WebShop
environment raise ``AssertionError`` and aborts the whole episode.

``ground_action`` repairs the raw LLM output into an action that is *guaranteed*
to be legal for the current page, using the legal targets the environment has
already stored in ``env.sessions[session]`` (``asins`` on a search page,
``option_types`` on an item page).  It is local, dependency-free and never
raises, so it adds no latency and no API cost while eliminating the crashes.
"""

import re
import difflib

_ASIN_RE = re.compile(r'B0[0-9A-Z]{8}')
_VERB_RE = re.compile(r'(search|click|think)\s*\[(.*?)\]', re.IGNORECASE | re.DOTALL)
_VERB_LOOSE_RE = re.compile(r'(search|click|think)\b[:\s]*(.*)', re.IGNORECASE | re.DOTALL)


def _norm(text):
    """Lowercase and strip every non-alphanumeric char for robust matching."""
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


def _parse(raw_action):
    """Extract ``(verb, argument)`` from a possibly noisy LLM string."""
    a = re.sub(r'^\s*action\s*:\s*', '', (raw_action or '').strip(), flags=re.IGNORECASE)
    m = _VERB_RE.search(a) or _VERB_LOOSE_RE.search(a)
    if m:
        return m.group(1).lower(), m.group(2).strip().strip('[]').strip()
    return '', a


def _legal_targets(page, asins, options):
    """Return the click targets accepted by the env on the given page."""
    if page == 'search':
        return list(asins) + ['Back to Search']
    if page == 'item':
        return list(options) + ['Buy Now', 'Description', 'Features',
                                'Reviews', 'Attributes', '< Prev', 'Back to Search']
    if page == 'item_sub':
        return ['< Prev', 'Back to Search']
    return []


def _match_target(candidates, legal):
    """Find the legal target best supported by the candidate strings (or None)."""
    if not legal:
        return None
    legal_set = set(legal)
    legal_norm = {_norm(x): x for x in legal}
    # 1) exact ASIN mention that is actually on the page
    for c in candidates:
        for token in _ASIN_RE.findall(c or ''):
            if token in legal_set:
                return token
    # 2) normalized exact match, then legal-label-as-substring
    for c in candidates:
        cn = _norm(c)
        if not cn:
            continue
        if cn in legal_norm:
            return legal_norm[cn]
        for ln, orig in legal_norm.items():
            if ln and ln in cn:
                return orig
    # 3) conservative fuzzy match
    for c in candidates:
        cn = _norm(c)
        if not cn:
            continue
        hit = difflib.get_close_matches(cn, list(legal_norm), n=1, cutoff=0.8)
        if hit:
            return legal_norm[hit[0]]
    return None


def ground_action(env, session, raw_action, hint='', force_click=False):
    """Repair ``raw_action`` into a legal WebShop action for the current page.

    Args:
        env: the ``webshopEnv`` instance.
        session: session id (e.g. ``fixed_0``).
        raw_action: the raw string produced by the LLM.
        hint: optional step text that names the intended target (its ASIN is
            used as ground truth when the model output is unusable).
        force_click: when True the result is always a ``click`` (used for the
            mechanical "click and check item X" steps); otherwise a legitimate
            ``think`` / ``search`` is preserved.

    Returns a legal action string; never raises.
    """
    s = env.sessions.get(session, {})
    page = s.get('page_type', 'init')
    asins = list(s.get('asins') or [])
    options = list((s.get('option_types') or {}).keys())
    verb, arg = _parse(raw_action)

    if not force_click:
        if verb == 'search' and page == 'init':
            return f'search[{arg}]'
        if verb == 'think':
            return f'think[{arg or "continue"}]'

    legal = _legal_targets(page, asins, options)
    target = _match_target([arg, raw_action, hint], legal)
    if target is not None:
        return f'click[{target}]'

    # Legal, progress-making fallback so the episode never stalls or crashes.
    if page == 'search' and asins:
        return f'click[{asins[0]}]'
    if page == 'item':
        return f'click[{options[0]}]' if options else 'click[Buy Now]'
    if not force_click and verb == 'think':
        return f'think[{arg or "continue"}]'
    return 'think[continue]'
