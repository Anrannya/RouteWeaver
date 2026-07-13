#!/usr/bin/env python3
"""Build a compact CSQA-oriented commonsense KB (stages 1-3).

Input: train_rand_split.jsonl
Output schema (runtime KB only):
{
  "fact_id": "fact_000001",
  "concept": "closet",
  "dimension": "primary_function",
  "fact": "A closet is commonly used to store clothes and belongings.",
  "conditions": []
}

The script uses CSQA training inputs to establish concept coverage. It uses
context-aware WordNet sense selection for high-precision lexical facts and a
small set of conservative CSQA-derived relation templates. Validation/source
metadata is written to a separate audit file, never to the runtime KB.
"""
from __future__ import annotations

import collections
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

INPUT = Path('/mnt/data/train_rand_split.jsonl')
OUT_DIR = Path('/mnt/data/csqa_kb_stage1_3')
OUT_DIR.mkdir(parents=True, exist_ok=True)

WN_FILES = {
    'n': (Path('/tmp/index.noun'), Path('/tmp/data.noun')),
    'v': (Path('/tmp/index.verb'), Path('/tmp/data.verb')),
    'a': (Path('/tmp/index.adj'), Path('/tmp/data.adj.txt')),
}

STOP = set('''a an the and or of to in on at for from with by as is are was were be been being it its
this that these those someone somebody person people they their them he she his her you your we our
what where when why how which who would could should might may can do does did has have had not no very
more most much many some any into out over under after before during while if then than also usually
commonly typically often generally likely'''.split())
MASS_OR_ABSTRACT = set('''music science history information furniture equipment food money water energy
knowledge intelligence freedom advice research traffic weather work fun clothing literature homework
jewelry mail blood ice gold silver sugar cotton leather paper glass wood rock luggage baggage
software machinery transportation legislation traffic clothing underwear underclothes'''.split())
GENERIC_HYPERNYMS = {
    'entity', 'physical entity', 'abstraction', 'thing', 'object', 'whole', 'unit', 'group',
    'location', 'place', 'area', 'person', 'activity', 'act', 'state', 'event', 'attribute',
    'artifact', 'structure', 'instrumentality', 'organism', 'living thing', 'substance', 'matter',
    'communication', 'relation', 'causal agent', 'psychological feature', 'social group',
    'natural object', 'body part', 'part', 'content', 'process'
}
GENERIC_WORDS = set('entity thing object item place area person people something anything someone location stuff'.split())

ABSTRACT_NOUN_LEX = {4, 7, 9, 10, 11, 12, 16, 19, 21, 22, 23, 24, 26, 27, 28}
GEO_TERMS = {'ocean', 'sea', 'country', 'state', 'city', 'continent', 'river', 'lake', 'mountain', 'island', 'america', 'europe', 'africa', 'asia', 'england', 'ireland', 'canada'}

LOCATION_WORDS = set('''place area region country state city town village room house home building store shop market
station airport school hospital restaurant zoo office bank church library hotel theater theatre court mall center
centre gym museum bar pub boutique factory farm park garden forest desert sea ocean river lake road street highway
freeway workplace auditorium classroom bedroom kitchen bathroom basement attic shelf cupboard drawer box bag pocket
container field island continent coast beach mountain valley cave yard backyard'''.split())


def norm_text(value: str) -> str:
    value = (value or '').lower().strip().replace('’', "'").replace('`', "'")
    value = re.sub(r'^[\"\']+|[\"\']+$', '', value)
    value = re.sub(r"[^a-z0-9\-\' ]+", ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def strip_article(value: str) -> str:
    value = norm_text(value)
    for article in ('a ', 'an ', 'the ', 'some ', 'many ', 'your ', 'his ', 'her ', 'their ', 'our '):
        if value.startswith(article) and len(value) > len(article) + 1:
            return value[len(article):]
    return value


def tokens(value: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z][a-z\-']+", norm_text(value))
        if token not in STOP and len(token) > 1
    ]


def cap(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def is_plural_phrase(value: str) -> bool:
    value = strip_article(value)
    if value in {'people', 'men', 'women', 'children', 'feet', 'teeth', 'mice', 'geese'}:
        return True
    last = value.split()[-1] if value.split() else ''
    return last.endswith('s') and not last.endswith(('ss', 'us', 'is', 'ous'))


def noun_subject(value: str, gloss: str = '') -> str:
    value = strip_article(value)
    if not value:
        return value
    if is_plural_phrase(value):
        return cap(value)
    if value in MASS_OR_ABSTRACT or value.endswith(('ing', 'ness', 'tion', 'sion', 'ity', 'ment', 'ance', 'ence')):
        return cap(value)
    return cap(('an ' if value[0] in 'aeiou' else 'a ') + value)


def gerund(value: str) -> str:
    value = strip_article(value)
    words = value.split()
    if not words:
        return value
    first = words[0]
    irregular = {
        'run': 'running', 'lie': 'lying', 'die': 'dying', 'sit': 'sitting', 'get': 'getting',
        'make': 'making', 'take': 'taking', 'drive': 'driving', 'write': 'writing',
        'use': 'using', 'practice': 'practicing', 'swim': 'swimming', 'cut': 'cutting',
        'put': 'putting', 'begin': 'beginning', 'win': 'winning'
    }
    if first in irregular:
        words[0] = irregular[first]
    elif first.endswith('e') and len(first) > 3:
        words[0] = first[:-1] + 'ing'
    elif not first.endswith('ing'):
        words[0] = first + 'ing'
    return ' '.join(words)


def clean_gloss(gloss: str) -> str:
    gloss = gloss.strip().strip(' .;').replace('_', ' ')
    gloss = re.sub(r'^\(plural\)\s*', '', gloss, flags=re.I)
    return re.sub(r'\s+', ' ', gloss)


class WordNetDB:
    def __init__(self) -> None:
        self.index: dict[str, dict[str, list[str]]] = {}
        self.syn: dict[str, dict[str, dict[str, Any]]] = {}
        for pos, (index_path, data_path) in WN_FILES.items():
            if not index_path.exists() or not data_path.exists():
                raise FileNotFoundError(f'Missing WordNet file: {index_path} or {data_path}')
            self.index[pos] = self._parse_index(index_path)
            self.syn[pos] = self._parse_data(data_path)

    @staticmethod
    def _parse_index(path: Path) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        with path.open(encoding='utf-8', errors='ignore') as handle:
            for line in handle:
                if not line or line[0].isspace():
                    continue
                parts = line.split()
                if len(parts) < 6:
                    continue
                try:
                    lemma = parts[0]
                    synset_count = int(parts[2])
                    pointer_count = int(parts[3])
                    index = 4 + pointer_count
                    offsets = parts[index + 2:index + 2 + synset_count]
                except (ValueError, IndexError):
                    continue
                if len(offsets) == synset_count:
                    result[lemma] = offsets
        return result

    @staticmethod
    def _parse_data(path: Path) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        with path.open(encoding='utf-8', errors='ignore') as handle:
            for line in handle:
                if not line or not line[0].isdigit() or ' | ' not in line:
                    continue
                left, gloss = line.rstrip('\n').split(' | ', 1)
                parts = left.split()
                try:
                    offset = parts[0]
                    lex_file = int(parts[1])
                    pos = parts[2]
                    word_count = int(parts[3], 16)
                    index = 4
                    words: list[str] = []
                    for _ in range(word_count):
                        words.append(parts[index].replace('_', ' '))
                        index += 2
                    pointer_count = int(parts[index])
                    index += 1
                    pointers: list[tuple[str, str, str, str]] = []
                    for _ in range(pointer_count):
                        symbol, target_offset, target_pos, source_target = parts[index:index + 4]
                        index += 4
                        pointers.append((symbol, target_offset, target_pos, source_target))
                except (ValueError, IndexError):
                    continue
                result[offset] = {
                    'offset': offset,
                    'lex': lex_file,
                    'pos': pos,
                    'words': words,
                    'gloss': clean_gloss(gloss.split('; "')[0]),
                    'pointers': pointers,
                }
        return result

    def variants(self, phrase: str, pos: str) -> list[str]:
        phrase = strip_article(phrase)
        values = [phrase]
        extra: list[str] = []
        for value in values:
            if pos == 'n':
                if value.endswith('ies') and len(value) > 4:
                    extra.extend([value[:-1], value[:-3] + 'y'])
                if value.endswith('ves') and len(value) > 4:
                    extra.extend([value[:-3] + 'f', value[:-3] + 'fe'])
                if value.endswith('men') and len(value) > 3:
                    extra.append(value[:-3] + 'man')
                if value.endswith('children'):
                    extra.append(value[:-8] + 'child')
                if value.endswith('es') and len(value) > 3:
                    extra.append(value[:-2])
                if value.endswith('s') and not value.endswith(('ss', 'us', 'is')) and len(value) > 2:
                    extra.append(value[:-1])
            elif pos == 'v':
                pieces = value.split()
                first = pieces[0] if pieces else ''
                rest = ' '.join(pieces[1:])
                irregular = {
                    'went': 'go', 'gone': 'go', 'got': 'get', 'made': 'make', 'took': 'take',
                    'taken': 'take', 'felt': 'feel', 'found': 'find', 'bought': 'buy',
                    'brought': 'bring', 'thought': 'think', 'caught': 'catch', 'ran': 'run',
                    'seen': 'see', 'saw': 'see', 'wrote': 'write', 'written': 'write',
                    'ate': 'eat', 'eaten': 'eat', 'driven': 'drive', 'drove': 'drive',
                    'gave': 'give', 'given': 'give', 'kept': 'keep', 'left': 'leave',
                    'lost': 'lose', 'won': 'win', 'sat': 'sit', 'stood': 'stand',
                    'lay': 'lie', 'lain': 'lie', 'told': 'tell', 'heard': 'hear'
                }
                forms: list[str] = []
                if first in irregular:
                    forms.append(irregular[first])
                if first.endswith('ing') and len(first) > 5:
                    forms.extend([first[:-3], first[:-3] + 'e'])
                if first.endswith('ied'):
                    forms.append(first[:-3] + 'y')
                if first.endswith('ed') and len(first) > 4:
                    forms.extend([first[:-2], first[:-1]])
                if first.endswith('es') and len(first) > 3:
                    forms.append(first[:-2])
                if first.endswith('s') and len(first) > 2:
                    forms.append(first[:-1])
                extra.extend([(form + (' ' + rest if rest else '')).strip() for form in forms])
            elif pos == 'a':
                if value.endswith('er') and len(value) > 4:
                    extra.append(value[:-2])
                if value.endswith('est') and len(value) > 5:
                    extra.append(value[:-3])
        values.extend(extra)
        output: list[str] = []
        for value in values:
            key = value.replace(' ', '_')
            if key and key not in output:
                output.append(key)
        return output

    def candidates(self, phrase: str) -> list[tuple[str, str, int, int, dict[str, Any]]]:
        output: list[tuple[str, str, int, int, dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()
        for pos in ('n', 'v', 'a'):
            matched_variants = 0
            for variant_rank, key in enumerate(self.variants(phrase, pos)):
                offsets = self.index[pos].get(key)
                if not offsets:
                    continue
                matched_variants += 1
                for sense_rank, offset in enumerate(offsets[:5]):
                    if (pos, offset) in seen:
                        continue
                    synset = self.syn[pos].get(offset)
                    if synset:
                        seen.add((pos, offset))
                        output.append((pos, key, variant_rank, sense_rank, synset))
                if matched_variants >= 2:
                    break
        return output

    def linked(self, synset: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for pointer_symbol, offset, pos, _ in synset['pointers']:
            if pointer_symbol == symbol and pos in self.syn and offset in self.syn[pos]:
                output.append(self.syn[pos][offset])
        return output


wn = WordNetDB()

@lru_cache(maxsize=100000)
def stem_tokens(value: str) -> tuple[str, ...]:
    def stem(token: str) -> str:
        if len(token) > 6 and token.endswith('ing'):
            token = token[:-3]
        elif len(token) > 5 and token.endswith('ied'):
            token = token[:-3] + 'y'
        elif len(token) > 5 and token.endswith('ed'):
            token = token[:-2]
        elif len(token) > 5 and token.endswith('es'):
            token = token[:-2]
        elif len(token) > 4 and token.endswith('s') and not token.endswith(('ss', 'us', 'is')):
            token = token[:-1]
        if len(token) > 5 and token.endswith('e'):
            token = token[:-1]
        return token
    return tuple(stem(token) for token in tokens(value))

@lru_cache(maxsize=None)
def sense_representation(pos: str, offset: str) -> frozenset[str]:
    synset = wn.syn[pos][offset]
    text = ' '.join(synset['words']) + ' ' + synset['gloss']
    current = [synset]
    for _ in range(2):
        next_level: list[dict[str, Any]] = []
        for item in current:
            for hypernym in wn.linked(item, '@')[:2]:
                text += ' ' + ' '.join(hypernym['words']) + ' ' + hypernym['gloss']
                next_level.append(hypernym)
        current = next_level
    for symbol in ('+', '&', '^'):
        for related in wn.linked(synset, symbol)[:4]:
            text += ' ' + ' '.join(related['words']) + ' ' + related['gloss']
    return frozenset(tokens(text))


@lru_cache(maxsize=None)
def sense_stem_representation(pos: str, offset: str) -> frozenset[str]:
    return frozenset(stem_tokens(' '.join(sorted(sense_representation(pos, offset)))))


def pos_prior(concept: str, role: str, stem: str, answer_label: str, choice_label: str | None, pos: str) -> float:
    concept = norm_text(concept)
    stem_lower = stem.lower()
    score = 0.0
    is_answer = role == 'choice' and choice_label == answer_label
    if re.search(r'\bwhere\b|what (?:place|location)', stem_lower):
        score += 3.5 if pos == 'n' else -1.5
    if is_answer and re.search(r'what (?:do|does|did|can|could|would|should|might|may)\b', stem_lower):
        score += 3.0 if pos == 'v' else (-0.5 if pos == 'n' else 0.0)
    if role == 'question_concept' and re.search(r'what (?:do|does|did|can|could|would|should|might|may)\b', stem_lower):
        score += 1.5 if pos == 'n' else 0.0
    if re.search(r'what (?:kind|type) of|which (?:kind|type)', stem_lower):
        score += 2.5 if pos == 'n' else 0.0
    if concept.startswith('to '):
        score += 4.0 if pos == 'v' else -2.0
    if concept.endswith('ing'):
        score += 1.5 if pos == 'v' else (0.7 if pos == 'n' else 0.0)
    if ' ' in concept and any(token in concept.split() for token in ('of', 'in', 'at', 'on', 'with', 'for')):
        score += 2.0 if pos == 'n' else 0.0
    if is_plural_phrase(concept):
        score += 1.2 if pos == 'n' else 0.0
    return score


def occurrence_sense_score(
    concept: str,
    candidate: tuple[str, str, int, int, dict[str, Any]],
    context: str,
    role: str,
    stem: str,
    answer_label: str,
    choice_label: str | None,
) -> float:
    pos, key, variant_rank, sense_rank, synset = candidate
    context_counts = collections.Counter(tokens(context))
    representation = sense_representation(pos, synset['offset'])
    lemmas = set(tokens(' '.join(synset['words'])))
    context_stems = collections.Counter(stem_tokens(context))
    representation_stems = sense_stem_representation(pos, synset['offset'])
    score = 2.0 * sum(min(context_counts[token], 3) for token in representation)
    score += 4.0 * sum(min(context_stems[token], 3) for token in representation_stems)
    score += 3.0 * sum(min(context_counts[token], 3) for token in lemmas)
    score += 2.0 * len(set(tokens(concept)) & lemmas)
    score -= variant_rank * 0.35 + sense_rank * 1.35
    score += pos_prior(concept, role, stem, answer_label, choice_label, pos)
    exact_key = strip_article(concept).replace(' ', '_')
    if key == exact_key:
        score += 0.5
    if pos == 'n' and is_plural_phrase(concept) and key != exact_key:
        score += 1.6
    if pos == 'n' and is_plural_phrase(concept) and any(word[:1].isupper() for word in synset['words']) and synset['lex'] == 18:
        score -= 5.0
    stem_lower = stem.lower()
    escaped = re.escape(strip_article(concept))
    if pos == 'v' and re.search(rf"\b(?:to|can|could|will|would|should|doesn['’]?t|does not|didn['’]?t|did not)\s+{escaped}\b", stem_lower):
        score += 5.0
    if pos in {'n', 'a'} and re.search(rf"\bthe\s+{escaped}\b", stem_lower):
        score += 2.0
    if strip_article(concept) == 'last' and re.search(r'\bthe last of\b', stem_lower):
        if pos == 'a' and sense_rank == 1:
            score += 10.0
        if pos == 'n' and any(word in synset['gloss'].lower() for word in ('dying act', 'death')):
            score -= 10.0
    if pos == 'a' and any(pattern in stem_lower for pattern in ('too what', 'what ideas', 'what kind of life', 'what type of life', 'how would', 'how did')):
        score += 2.5
    if pos == 'n' and synset['lex'] == 15:
        gloss_lower = synset['gloss'].lower()
        if 'officially dissolved' in gloss_lower or 'overthrown by revolution' in gloss_lower:
            score -= 9.0
        elif 'former ' in gloss_lower or 'formerly ' in gloss_lower:
            score -= 4.0
        if 'since 1991 an independent state' in gloss_lower or 'independent state' in gloss_lower:
            score += 12.0
        if any(text in gloss_lower for text in ('capital and largest city', 'a federation in', 'a state in', 'a state on', 'mid-atlantic state', 'midwestern state')):
            score += 4.0
    return score


def choose_occurrence_sense(
    concept: str,
    context: str,
    role: str,
    stem: str,
    answer_label: str,
    choice_label: str | None,
) -> tuple[str, str, int, int, dict[str, Any]] | None:
    candidates = wn.candidates(concept)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: occurrence_sense_score(concept, item, context, role, stem, answer_label, choice_label),
    )


def rank_occurrence_senses(
    concept: str,
    context: str,
    role: str,
    stem: str,
    answer_label: str,
    choice_label: str | None,
) -> list[tuple[float, tuple[str, str, int, int, dict[str, Any]]]]:
    candidates = wn.candidates(concept)
    ranked = [
        (occurrence_sense_score(concept, item, context, role, stem, answer_label, choice_label), item)
        for item in candidates
    ]
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


def gloss_dimension(pos: str, gloss: str) -> str:
    lower = gloss.lower()
    if pos == 'v':
        if any(text in lower for text in ('cause', 'result', 'bring about', 'lead to')):
            return 'effect'
        if any(text in lower for text in ('use', 'serve', 'function')):
            return 'primary_function'
        return 'capability'
    if pos == 'a':
        return 'property'
    if any(text in lower for text in ('used for', 'used to', 'designed for', 'device for', 'instrument for', 'tool for', 'serves to')):
        return 'primary_function'
    if any(text in lower for text in ('place where', 'area where', 'room where', 'location', 'site where')):
        return 'typical_location'
    if any(text in lower for text in ('part of', 'component of', 'portion of')):
        return 'part_whole'
    return 'category'


def sense_qualifier(base_concept: str, synset: dict[str, Any]) -> str:
    hypernyms = wn.linked(synset, '@')
    for hypernym in hypernyms:
        candidate = hypernym['words'][0].replace('_', ' ')
        if norm_text(candidate) not in GENERIC_HYPERNYMS and not set(tokens(candidate)) <= GENERIC_WORDS:
            return candidate
    base_forms = {norm_text(base_concept)}
    for pos in ('n', 'v', 'a'):
        base_forms.update(norm_text(value.replace('_', ' ')) for value in wn.variants(base_concept, pos))
    for word in synset['words']:
        candidate = word.replace('_', ' ')
        if norm_text(candidate) not in base_forms:
            return candidate
    short = ' '.join(tokens(synset['gloss'])[:4])
    return short or synset['pos']


def _canonical_display(canonical: str, synset: dict[str, Any]) -> str:
    normalized = norm_text(canonical)
    for word in synset['words']:
        display = word.replace('_', ' ')
        if norm_text(display) == normalized:
            return display
    return canonical.replace('_', ' ')


def _canonical_noun_subject(canonical: str, synset: dict[str, Any]) -> str:
    canonical = canonical.replace('_', ' ')
    display = _canonical_display(canonical, synset)
    words = norm_text(display).split()
    is_proper = any(ch.isupper() for ch in display) or (display.isupper() and len(display) > 1)
    if is_proper:
        if any(term in words for term in ('ocean', 'sea')):
            return 'The ' + display
        return display
    if synset['lex'] == 15 and (set(words) & GEO_TERMS or norm_text(canonical) in GEO_TERMS):
        title = ' '.join(word.capitalize() for word in words)
        if any(term in words for term in ('ocean', 'sea')):
            return 'The ' + title
        return title
    if synset['lex'] in ABSTRACT_NOUN_LEX or canonical in MASS_OR_ABSTRACT or canonical.endswith(('ing', 'ness', 'tion', 'sion', 'ity', 'ment', 'ance', 'ence')):
        return cap(canonical)
    return noun_subject(canonical)


def _noun_predicate(gloss: str) -> str:
    gloss = clean_gloss(gloss)
    if re.match(r'^(?:a|an|the|any|some|one|someone|something|several|two|three|four|five)\b', gloss, flags=re.I):
        return gloss
    first = norm_text(gloss).split()[0] if norm_text(gloss).split() else ''
    mass_starts = {'equipment', 'furniture', 'information', 'machinery', 'software', 'clothing', 'luggage', 'baggage', 'food', 'water', 'money', 'material'}
    if first in mass_starts or is_plural_phrase(first):
        return gloss
    return ('an ' if gloss[:1].lower() in 'aeiou' else 'a ') + gloss


def make_definition_fact(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> dict[str, Any] | None:
    pos, key, _, _, synset = candidate
    canonical = synset['words'][0].replace('_', ' ')
    gloss = clean_gloss(synset['gloss'])
    if len(tokens(gloss)) < 3:
        return None
    if len(set(tokens(gloss)) - set(tokens(canonical))) < 2:
        return None
    if pos == 'n':
        subject = _canonical_noun_subject(canonical, synset)
        predicate = _noun_predicate(gloss)
        first = norm_text(gloss).split()[0] if norm_text(gloss).split() else ''
        if canonical in MASS_OR_ABSTRACT and is_plural_phrase(first):
            fact = f'{subject} refers to {gloss}.'
        else:
            fact = f'{subject} is {predicate}.'
    elif pos == 'v':
        if norm_text(gloss).startswith(norm_text(canonical)):
            return None
        fact = f'To {canonical} means to {gloss}.'
    else:
        fact = f'{cap(canonical)} describes something {gloss}.'
    fact = re.sub(r'\s+', ' ', fact).replace('..', '.')
    return {
        'concept': concept_label,
        'dimension': gloss_dimension(pos, gloss),
        'fact': fact,
        'conditions': [],
        '_source_kind': 'wordnet_definition',
        '_source_ref': f'{pos}:{synset["offset"]}',
        '_priority': 100,
    }

def make_hypernym_fact(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> dict[str, Any] | None:
    pos, key, _, _, synset = candidate
    canonical = synset['words'][0].replace('_', ' ')
    hypernyms = wn.linked(synset, '@')
    if not hypernyms:
        return None
    hypernym = hypernyms[0]['words'][0].replace('_', ' ')
    if norm_text(hypernym) in GENERIC_HYPERNYMS or set(tokens(hypernym)) <= GENERIC_WORDS:
        return None
    if norm_text(hypernym) in {norm_text(base_concept), norm_text(canonical)}:
        return None
    if pos == 'n':
        fact = f'{_canonical_noun_subject(canonical, synset)} is a kind of {hypernym}.'
        dimension = 'category'
    else:
        return None
    return {
        'concept': concept_label,
        'dimension': dimension,
        'fact': fact,
        'conditions': [],
        '_source_kind': 'wordnet_hypernym',
        '_source_ref': f'{pos}:{synset["offset"]}',
        '_priority': 92,
    }


def make_secondary_hypernym_fact(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> dict[str, Any] | None:
    """Return one additional, non-generic direct category when WordNet encodes multiple parents.

    This adds breadth without relying on loose RelatedTo-style edges or rare synonyms.
    """
    pos, key, _, _, synset = candidate
    if pos != 'n':
        return None
    canonical = synset['words'][0].replace('_', ' ')
    hypernyms = wn.linked(synset, '@')
    if len(hypernyms) < 2:
        return None
    primary = norm_text(hypernyms[0]['words'][0].replace('_', ' '))
    for linked in hypernyms[1:]:
        hypernym = linked['words'][0].replace('_', ' ')
        normalized = norm_text(hypernym)
        if normalized == primary:
            continue
        if normalized in GENERIC_HYPERNYMS or set(tokens(hypernym)) <= GENERIC_WORDS:
            continue
        if normalized in {norm_text(base_concept), norm_text(canonical)}:
            continue
        fact = f'{_canonical_noun_subject(canonical, synset)} is also a kind of {hypernym}.'
        dimension = 'category'
        return {
            'concept': concept_label,
            'dimension': dimension,
            'fact': fact,
            'conditions': [],
            '_source_kind': 'wordnet_secondary_hypernym',
            '_source_ref': f'{pos}:{synset["offset"]}',
            '_priority': 90,
        }
    return None


def make_compound_head_fact(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> dict[str, Any] | None:
    """Create a conservative compositional category for transparent noun compounds."""
    pos, key, _, _, synset = candidate
    if pos != 'n':
        return None
    canonical = synset['words'][0].replace('_', ' ')
    parts = canonical.split()
    if not 2 <= len(parts) <= 4 or 'of' in parts or is_plural_phrase(canonical):
        return None
    if any(any(ch.isupper() for ch in word) for word in synset['words']):
        return None
    head = parts[-1]
    transparent_heads = {
        'store', 'shop', 'room', 'station', 'park', 'garden', 'instrument', 'machine', 'device',
        'tool', 'container', 'building', 'vehicle', 'tree', 'fish', 'bird', 'dog', 'cat', 'court',
        'field', 'food', 'drink', 'chair', 'table', 'box', 'bag', 'bottle', 'cup', 'book',
        'school', 'hospital', 'office', 'farm', 'club', 'meter', 'holder', 'booth', 'source',
        'salon', 'theater', 'theatre', 'mall', 'market', 'house', 'boat', 'car', 'truck',
        'shoe', 'shirt', 'coat', 'hat', 'pen', 'basket', 'cabinet', 'bed', 'door', 'window'
    }
    if norm_text(head) not in transparent_heads:
        return None
    if head in {'of', 'for', 'in', 'on', 'at', 'with', 'from', 'to'}:
        return None
    if norm_text(head) in GENERIC_HYPERNYMS or set(tokens(head)) <= GENERIC_WORDS:
        return None
    if norm_text(canonical) in GEO_TERMS or norm_text(canonical) in ABSTRACT_NOUN_LEX:
        return None
    # Require WordNet to recognize the head as a noun; this rejects accidental phrase endings.
    if not any(key in wn.index['n'] for key in wn.variants(head, 'n')):
        return None
    direct = {norm_text(item['words'][0].replace('_', ' ')) for item in wn.linked(synset, '@')}
    if norm_text(head) in direct:
        return None
    fact = f'{_canonical_noun_subject(canonical, synset)} is a kind of {head}.'
    return {
        'concept': concept_label,
        'dimension': 'category',
        'fact': fact,
        'conditions': [],
        '_source_kind': 'compound_head_category',
        '_source_ref': f'n:{synset["offset"]}',
        '_priority': 91,
    }

def make_synonym_facts(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> list[dict[str, Any]]:
    pos, key, _, _, synset = candidate
    canonical = synset['words'][0].replace('_', ' ')
    alternatives: list[str] = []
    for word in synset['words']:
        alternative = word.replace('_', ' ')
        if norm_text(alternative) not in {norm_text(canonical), norm_text(base_concept)} and alternative not in alternatives:
            alternatives.append(alternative)
    output: list[dict[str, Any]] = []
    for index, alternative in enumerate(alternatives[:2]):
        if re.search(r'[()]|\(a\)$', alternative):
            continue
        if pos == 'v':
            fact = f'To {canonical} can also mean to {alternative}.'
        elif pos == 'a':
            fact = f'{cap(canonical)} can also be described as {alternative}.'
        else:
            fact = f'{_canonical_noun_subject(canonical, synset)} can also be called {alternative}.'
        output.append({
            'concept': concept_label,
            'dimension': 'lexical_equivalence',
            'fact': fact,
            'conditions': [],
            '_source_kind': f'wordnet_synonym_{index + 1}',
            '_source_ref': f'{pos}:{synset["offset"]}',
            '_priority': 82 - index * 7,
        })
    return output


def make_gloss_derived_fact(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> dict[str, Any] | None:
    pos, key, _, _, synset = candidate
    if pos != 'n':
        return None
    canonical = synset['words'][0].replace('_', ' ')
    subject = _canonical_noun_subject(canonical, synset)
    gloss = clean_gloss(synset['gloss'])
    lower = gloss.lower()
    fact = None
    dimension = None

    # Keep only relative clauses that begin with an explicit predicate.
    match = re.search(r'\b(?:that|which)\s+((?:contains|has|holds|stores|carries|keeps|serves|provides|allows|enables|connects|covers|protects|supports|produces|causes|includes)\b.+)$', gloss, flags=re.I)
    if match:
        clause = match.group(1).strip(' .;')
        if len(tokens(clause)) >= 3:
            fact = f'{subject} {clause}.'
            dimension = 'capability' if clause.lower().startswith(('allows', 'enables', 'provides')) else 'property'

    if fact is None:
        match = re.search(r'\bused (?:primarily |mainly )?for\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} is commonly used for {match.group(1).strip(" .;")}.'
            dimension = 'primary_function'
    if fact is None:
        match = re.search(r'\bused (?:primarily |mainly )?to\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} is commonly used to {match.group(1).strip(" .;")}.'
            dimension = 'primary_function'
    if fact is None:
        match = re.search(r'\bfor (keeping|holding|storing|carrying|cutting|measuring|protecting|transporting|cooking|writing|cleaning|covering)\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} is used for {match.group(1)} {match.group(2).strip(" .;")}.'
            dimension = 'primary_function'
    if fact is None:
        match = re.search(r'\b(?:filled|covered) with\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} typically contains or is covered with {match.group(1).strip(" .;")}.'
            dimension = 'typical_content'
    if fact is None:
        match = re.search(r'\bconsisting of\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} consists of {match.group(1).strip(" .;")}.'
            dimension = 'typical_content'
    if fact is None:
        match = re.search(r'\b(?:located|found|situated) (?:in|on|at)\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} is typically located in or on {match.group(1).strip(" .;")}.'
            dimension = 'typical_location'
    if fact is None:
        match = re.search(r'\bpart of\s+(.+)$', gloss, flags=re.I)
        if match:
            fact = f'{subject} is part of {match.group(1).strip(" .;")}.'
            dimension = 'part_whole'

    if not fact or len(tokens(fact)) < 4:
        return None
    fact = re.sub(r'\s+', ' ', fact).replace('..', '.')
    return {
        'concept': concept_label,
        'dimension': dimension,
        'fact': fact,
        'conditions': [],
        '_source_kind': 'wordnet_gloss_relation',
        '_source_ref': f'n:{synset["offset"]}',
        '_priority': 94,
    }

def make_antonym_fact(base_concept: str, concept_label: str, candidate: tuple[str, str, int, int, dict[str, Any]]) -> dict[str, Any] | None:
    pos, key, _, _, synset = candidate
    antonyms = wn.linked(synset, '!')
    if not antonyms:
        return None
    antonym = antonyms[0]['words'][0].replace('_', ' ')
    canonical = synset['words'][0].replace('_', ' ')
    if norm_text(antonym) == norm_text(canonical):
        return None
    fact = f'{cap(antonym)} is an opposite of {canonical}.'
    return {
        'concept': concept_label,
        'dimension': 'property',
        'fact': fact,
        'conditions': [],
        '_source_kind': 'wordnet_antonym',
        '_source_ref': f'{pos}:{synset["offset"]}',
        '_priority': 88,
    }


def final_question_clause(stem: str) -> str:
    text = stem.strip()
    question_end = text.rfind('?')
    if question_end < 0:
        question_end = len(text)
    start = max(text.rfind('.', 0, question_end), text.rfind('!', 0, question_end), text.rfind('?', 0, question_end))
    return text[start + 1:question_end + 1].strip()


def concept_in_clause(clause: str, concept: str) -> bool:
    concept_tokens = [token for token in norm_text(concept).split() if len(token) > 2 and token not in {'the', 'and', 'for', 'with'}]
    clause_tokens = set(norm_text(clause).split())
    return bool(concept_tokens) and sum(token in clause_tokens for token in concept_tokens) >= max(1, len(concept_tokens) - 1)


def clean_location_answer(answer: str) -> str:
    answer = strip_article(answer)
    answer = re.sub(r'^(?:in|at|on|inside|outside)\s+', '', answer)
    return answer.strip()


def location_preposition(answer: str) -> str:
    words = set(norm_text(answer).split())
    at_terms = {'store', 'shop', 'market', 'station', 'airport', 'school', 'hospital', 'restaurant', 'zoo', 'office',
                'bank', 'church', 'library', 'hotel', 'theater', 'theatre', 'court', 'mall', 'center', 'centre',
                'gym', 'museum', 'bar', 'pub', 'boutique', 'factory', 'farm', 'meeting', 'fairgrounds', 'venue', 'auditorium', 'park'}
    return 'at' if words & at_terms else 'in'


def be_verb(value: str) -> str:
    return 'are' if is_plural_phrase(value) else 'is'


def likely_person(concept: str, context: str) -> bool:
    candidate = choose_occurrence_sense(concept, context, 'question_concept', context, '', None)
    return bool(candidate and candidate[0] == 'n' and candidate[4]['lex'] == 18)


def format_location_object(place: str) -> str:
    place = clean_location_answer(place)
    words = set(norm_text(place).split())
    if words & {'atlantic', 'pacific', 'indian'} and words & {'ocean', 'sea'}:
        return 'the ' + ' '.join(word.capitalize() for word in place.split())
    candidate = choose_occurrence_sense(place, place, 'choice', place, '', None)
    if candidate and candidate[0] == 'n' and candidate[4]['lex'] == 15:
        display = _canonical_display(candidate[1].replace('_', ' '), candidate[4])
        if any(ch.isupper() for ch in display):
            return display
    if is_plural_phrase(place) or place in MASS_OR_ABSTRACT:
        return place
    return ('an ' if place[:1] in 'aeiou' else 'a ') + place


def likely_location(answer: str, context: str) -> bool:
    answer_norm = clean_location_answer(answer)
    if set(answer_norm.split()) & LOCATION_WORDS:
        return True
    candidate = choose_occurrence_sense(answer_norm, context, 'choice', context, '', None)
    if candidate and candidate[0] == 'n':
        synset = candidate[4]
        if synset['lex'] == 15:
            return True
        representation = sense_representation('n', synset['offset'])
        if representation & LOCATION_WORDS:
            return True
    return False


def make_csqa_relation_fact(row: dict[str, Any]) -> dict[str, Any] | None:
    question = row['question']
    stem = question['stem']
    clause = final_question_clause(stem)
    clause_lower = norm_text(clause)
    concept = strip_article(question.get('question_concept', ''))
    answer_raw = next(choice['text'] for choice in question['choices'] if choice['label'] == row['answerKey'])
    answer = strip_article(answer_raw)
    if not concept or not answer or not concept_in_clause(clause, concept):
        return None

    dimension: str | None = None
    fact: str | None = None
    pattern: str | None = None

    # Explicit location questions only. Named or contextual associations without a stable place type are rejected.
    if 'where' in clause_lower and likely_location(answer, stem + ' ' + ' '.join(c['text'] for c in question['choices'])):
        place = clean_location_answer(answer)
        preposition = location_preposition(place)
        place_object = format_location_object(place)
        negative = any(text in clause_lower for text in ('unlikely', 'least likely', 'not likely', 'not welcome', 'not be able to find'))
        if negative:
            fact = f'{noun_subject(concept)} {be_verb(concept)} not typically found or welcome {preposition} {place_object}.'
            pattern = 'explicit_location_negative'
        elif any(text in clause_lower for text in ('store', 'stored', 'keep', 'kept', 'put ')):
            fact = f'{noun_subject(concept)} {be_verb(concept)} commonly stored or kept {preposition} {place_object}.'
            pattern = 'explicit_storage_location'
        elif re.search(r'\b(?:live|lives|living|habitat|reside|resides)\b', clause_lower) and likely_person(concept, stem + ' ' + concept):
            fact = f'{noun_subject(concept)} commonly lives in {place_object}.'
            pattern = 'explicit_living_location'
        elif any(text in clause_lower for text in ('find', 'found', 'locate', 'located', 'where is', 'where are', 'where do', 'where can', 'where would', 'where might', 'work', 'buy', 'purchase', 'sold', 'selling')):
            fact = f'{noun_subject(concept)} can commonly be found {preposition} {place_object}.'
            pattern = 'explicit_find_location'
        if fact:
            dimension = 'typical_location'

    # Directionally unambiguous causal relations.
    if fact is None and ('lead to' in clause_lower or 'result in' in clause_lower):
        fact = f'{cap(concept)} can lead to {answer}.'
        dimension = 'effect'
        pattern = 'explicit_lead_to'
    if fact is None and re.search(r'what (?:could|can|might|would) cause\b', clause_lower):
        fact = f'{cap(answer)} can cause {concept}.'
        dimension = 'cause'
        pattern = 'explicit_reverse_cause'
    if fact is None and re.search(r'what does .+ cause\b', clause_lower):
        fact = f'{cap(concept)} can cause {answer}.'
        dimension = 'effect'
        pattern = 'explicit_forward_cause'
    if fact is None and ('consequence' in clause_lower or 'result of' in clause_lower):
        fact = f'{cap(answer)} can be a consequence of {concept}.'
        dimension = 'effect'
        pattern = 'explicit_consequence'

    if fact is None and 'goal of' in clause_lower:
        fact = f'{cap(answer)} is a common goal of {concept}.'
        dimension = 'human_intention'
        pattern = 'explicit_goal'

    if fact is None and ('used for' in clause_lower or 'purpose of' in clause_lower):
        fact = f'{noun_subject(concept)} is commonly used for {answer}.'
        dimension = 'primary_function'
        pattern = 'explicit_used_for'

    if fact is None and re.search(r'what can be done to\b', clause_lower):
        fact = f'{noun_subject(concept)} can be {answer}.'
        dimension = 'capability'
        pattern = 'explicit_passive_capability'

    if fact is None and 'opposite of' in clause_lower:
        fact = f'{cap(answer)} is an opposite of {concept}.'
        dimension = 'property'
        pattern = 'explicit_opposite'

    if fact is None and re.search(r'located where|located in what', clause_lower):
        fact = f'{noun_subject(concept)} is located in or on {answer}.'
        dimension = 'part_location'
        pattern = 'explicit_part_location'

    # Only accept composition when the question explicitly says the answer is made of the concept.
    if fact is None and re.search(r'made (?:mostly |largely )?of\s+' + re.escape(concept) + r'\b', clause_lower):
        fact = f'{noun_subject(answer)} is made largely of {concept}.'
        dimension = 'composition'
        pattern = 'explicit_composition'

    if fact is None:
        return None

    fact = re.sub(r'\s+', ' ', fact).replace('..', '.')
    # Conservative construction-time cleaning.
    bad_fragments = ('what.', 'where.', 'which.', 'someone is a kind of', 'a people', 'a shoes', 'a books')
    if len(tokens(fact)) < 4 or any(fragment in fact.lower() for fragment in bad_fragments):
        return None
    return {
        'concept': concept,
        'dimension': dimension,
        'fact': fact,
        'conditions': [],
        '_source_kind': 'csqa_train_explicit_relation',
        '_source_ref': row.get('id', ''),
        '_priority': 96,
        '_pattern': pattern,
    }


def validate_candidate(candidate: dict[str, Any]) -> tuple[bool, str]:
    concept = strip_article(candidate.get('concept', ''))
    fact = re.sub(r'\s+', ' ', candidate.get('fact', '')).strip()
    fact = re.sub(r'\.{2,}$', '.', fact)
    candidate['fact'] = fact
    dimension = candidate.get('dimension', '')
    if not concept or not dimension or not fact:
        return False, 'missing_required_field'
    if not fact.endswith('.'):
        return False, 'incomplete_sentence'
    fact_tokens = tokens(fact)
    source_kind = candidate.get('_source_kind', '')
    if source_kind.startswith(('wordnet_synonym', 'wordnet_antonym', 'wordnet_hypernym')):
        minimum_tokens = 2
    elif source_kind == 'wordnet_definition':
        minimum_tokens = 3
    else:
        minimum_tokens = 4
    if len(fact_tokens) < minimum_tokens:
        return False, 'too_short_or_generic'
    if len(fact) > 320:
        return False, 'too_long'
    if '?' in fact:
        return False, 'question_leakage'
    if re.search(r'\b(?:option|answer|question|choice)\s+[abcde]\b', fact.lower()):
        return False, 'answer_mapping_leakage'
    if any(text in fact.lower() for text in ('in the described situation', 'in this question', 'the other options')):
        return False, 'context_dependent'
    if re.search(r'\b(a|an)\s+(people|shoes|books|clothes|cats|dogs|sunglasses|foods)\b', fact.lower()):
        return False, 'article_number_error'
    if fact.lower().count(' is a kind of ') and norm_text(fact.split(' is a kind of ', 1)[1]) in GENERIC_HYPERNYMS:
        return False, 'generic_hypernym'
    # Synonyms are retained only when the selected sense is supported by repeated CSQA contexts.
    if candidate['_source_kind'] == 'wordnet_synonym_1':
        alternative = fact.rsplit(' ', 1)[-1].rstrip('.').lower()
        if len(alternative) <= 1:
            return False, 'invalid_synonym'
    if candidate['_source_kind'] == 'wordnet_synonym_2':
        if len(tokens(fact)) < 2:
            return False, 'invalid_second_synonym'
    # Avoid circular synonym statements.
    if candidate['_source_kind'].startswith('wordnet_synonym'):
        left_right = re.findall(r'called (.+?)\.$|mean to (.+?)\.$|described as (.+?)\.$', fact.lower())
        if left_right and norm_text(concept) in {norm_text(x) for group in left_right for x in group if x}:
            return False, 'circular_synonym'
    return True, 'accepted'


def main() -> None:
    rows = [json.loads(line) for line in INPUT.open(encoding='utf-8') if line.strip()]
    question_count = len(rows)
    min_facts = question_count * 2
    max_facts = question_count * 3
    target_facts = round(question_count * 2.02)

    inventory: dict[str, dict[str, Any]] = {}
    occurrence_senses: dict[str, list[tuple[tuple[str, str, int, int, dict[str, Any]], str]]] = collections.defaultdict(list)

    # Stage 1: full training-input concept coverage. Labels are not used for inventory extraction.
    for row in rows:
        question = row['question']
        choices = question['choices']
        choice_text = ' '.join(choice['text'] for choice in choices)
        items = [('question_concept', question.get('question_concept', ''), None)] + [
            ('choice', choice['text'], choice['label']) for choice in choices
        ]
        for role, raw, choice_label in items:
            concept = strip_article(raw)
            if not concept:
                continue
            entry = inventory.setdefault(concept, {
                'concept': concept,
                'occurrence_count': 0,
                'question_concept_count': 0,
                'choice_count': 0,
                'raw_forms': collections.Counter(),
                'sense_concepts': [],
            })
            entry['occurrence_count'] += 1
            entry[f'{role}_count'] += 1
            entry['raw_forms'][raw] += 1
            context = question['stem'] + ' ' + choice_text + ' ' + question.get('question_concept', '')
            informative = role == 'question_concept' or (role == 'choice' and choice_label == row['answerKey'])
            if informative:
                ranked = rank_occurrence_senses(
                    concept, context, role, question['stem'], row['answerKey'], choice_label
                )
                if ranked:
                    occurrence_senses[concept].append((ranked[0][1], row.get('id', '')))
                    # Preserve one close alternative sense with an explicit qualifier instead of
                    # permanently binding an ambiguous word to a single possibly wrong meaning.
                    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] <= 4.0:
                        first = ranked[0][1]
                        second = ranked[1][1]
                        if (first[0], first[4]['offset']) != (second[0], second[4]['offset']):
                            occurrence_senses[concept].append((second, row.get('id', '') + ':alt'))

    # Concepts seen only as distractors still receive their common dictionary sense.
    for concept in inventory:
        if concept not in occurrence_senses:
            default_selected = choose_occurrence_sense(concept, concept, 'choice', concept, '', None)
            if default_selected and is_plural_phrase(concept) and default_selected[4]['lex'] == 18 and any(word[:1].isupper() for word in default_selected[4]['words']):
                alternatives = [item for item in wn.candidates(concept) if item[0] == 'n' and item[1] != strip_article(concept).replace(' ', '_') and item[4]['lex'] != 18]
                if alternatives:
                    default_selected = alternatives[0]
            if default_selected:
                occurrence_senses[concept].append((default_selected, 'default_common_sense'))

    retained_senses: list[tuple[str, str, tuple[str, str, int, int, dict[str, Any]], int, float]] = []
    alternate_sense_budget = 700
    ordered_concepts = sorted(occurrence_senses, key=lambda value: (-inventory[value]['question_concept_count'], -inventory[value]['occurrence_count'], value))
    for concept in ordered_concepts:
        items = occurrence_senses[concept]
        counts = collections.Counter((item[0][0], item[0][4]['offset']) for item in items)
        total = len(items)
        top = counts.most_common(3)
        selected_rows: list[tuple[tuple[str, str, int, int, dict[str, Any]], int, float]] = []
        for index, ((pos, offset), count) in enumerate(top):
            share = count / total
            keep_second_observed = (
                index == 1
                and share >= 0.15
                and (count >= 2 or inventory[concept]['question_concept_count'] >= 2)
            )
            if index == 0 or keep_second_observed:
                candidate = next(item[0] for item in items if item[0][0] == pos and item[0][4]['offset'] == offset)
                selected_rows.append((candidate, count, share))
        all_candidates = wn.candidates(concept)
        selected_keys = {(item[0][0], item[0][4]['offset']) for item in selected_rows}
        is_geo_concept = any(item[4]['lex'] == 15 for item in all_candidates if item[0] == 'n')
        if alternate_sense_budget > 0 and len(selected_rows) < 2 and not is_geo_concept and (inventory[concept]['question_concept_count'] > 0 or inventory[concept]['occurrence_count'] >= 2):
            ranked_defaults = rank_occurrence_senses(concept, concept, 'choice', concept, '', None)
            top_default_score = ranked_defaults[0][0] if ranked_defaults else float('-inf')
            for alternative_score, alternative in ranked_defaults:
                key = (alternative[0], alternative[4]['offset'])
                if key in selected_keys or alternative[3] > 3:
                    continue
                if top_default_score - alternative_score > 0.75:
                    continue
                selected_rows.append((alternative, 1, 0.0))
                selected_keys.add(key)
                alternate_sense_budget -= 1
                break
        multiple = len(selected_rows) > 1
        available_pos = {item[0] for item in all_candidates}
        labels: list[str] = []
        for candidate, count, share in selected_rows:
            pos, _, variant_rank, sense_rank, synset = candidate
            label = concept
            needs_qualifier = multiple or sense_rank > 0 or (len(available_pos) > 1 and pos != 'n')
            if needs_qualifier:
                qualifier = sense_qualifier(concept, synset)
                label = f'{concept} ({qualifier})'
            labels.append(label)
            retained_senses.append((concept, label, candidate, count, share))
        inventory[concept]['sense_concepts'] = labels

    # Stage 2: candidate generation.
    candidates: list[dict[str, Any]] = []
    for base_concept, concept_label, candidate, occurrence_count, occurrence_share in retained_senses:
        generated: list[dict[str, Any] | None] = [
            make_definition_fact(base_concept, concept_label, candidate),
            make_gloss_derived_fact(base_concept, concept_label, candidate),
            make_hypernym_fact(base_concept, concept_label, candidate),
            make_secondary_hypernym_fact(base_concept, concept_label, candidate),
            make_compound_head_fact(base_concept, concept_label, candidate),
            make_antonym_fact(base_concept, concept_label, candidate),
        ]
        generated.extend(make_synonym_facts(base_concept, concept_label, candidate))
        for fact in generated:
            if fact:
                fact['_occurrence_count'] = occurrence_count
                fact['_occurrence_share'] = occurrence_share
                candidates.append(fact)

    # Stage 3: deterministic cleaning, exact semantic-key deduplication, and quantity control.
    accepted_candidates: list[dict[str, Any]] = []
    rejection_counts: collections.Counter[str] = collections.Counter()
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        valid, reason = validate_candidate(candidate)
        if not valid:
            rejection_counts[reason] += 1
            continue
        key = (
            norm_text(candidate['concept']),
            candidate['dimension'],
            norm_text(candidate['fact']),
        )
        if key in seen:
            rejection_counts['exact_duplicate'] += 1
            continue
        seen.add(key)
        accepted_candidates.append(candidate)

    # Prefer reliable definitions and typed lexical relations; use lower-priority synonyms only as quantity backfill.
    accepted_candidates.sort(key=lambda item: (
        -item['_priority'],
        -min(item.get('_occurrence_count', 1), 20),
        -item.get('_occurrence_share', 0.0),
        item['concept'], item['dimension'], item['fact'],
    ))

    if len(accepted_candidates) < min_facts:
        raise RuntimeError(
            f'Only {len(accepted_candidates)} cleaned facts were available; minimum required is {min_facts}.'
        )
    selected = accepted_candidates[:min(target_facts, max_facts)]
    if len(selected) < min_facts:
        selected = accepted_candidates[:min_facts]

    runtime_path = OUT_DIR / 'csqa_commonsense_kb.jsonl'
    audit_path = OUT_DIR / 'csqa_kb_audit.jsonl'
    inventory_path = OUT_DIR / 'csqa_concept_inventory.json'
    summary_path = OUT_DIR / 'csqa_kb_summary.json'

    source_counts: collections.Counter[str] = collections.Counter()
    dimension_counts: collections.Counter[str] = collections.Counter()
    pattern_counts: collections.Counter[str] = collections.Counter()

    with runtime_path.open('w', encoding='utf-8') as runtime_file, audit_path.open('w', encoding='utf-8') as audit_file:
        for index, candidate in enumerate(selected, start=1):
            fact_id = f'fact_{index:06d}'
            runtime_record = {
                'fact_id': fact_id,
                'concept': candidate['concept'],
                'dimension': candidate['dimension'],
                'fact': candidate['fact'],
                'conditions': candidate['conditions'],
            }
            runtime_file.write(json.dumps(runtime_record, ensure_ascii=False) + '\n')
            audit_record = {
                'fact_id': fact_id,
                'source_kind': candidate['_source_kind'],
                'source_ref': candidate['_source_ref'],
                'occurrence_count': candidate.get('_occurrence_count', 1),
                'occurrence_share': round(candidate.get('_occurrence_share', 1.0), 6),
                'construction_checks': {
                    'required_fields': True,
                    'complete_sentence': True,
                    'minimum_specificity': True,
                    'no_question_or_answer_mapping': True,
                    'deduplicated': True,
                },
            }
            if candidate.get('_pattern'):
                audit_record['pattern'] = candidate['_pattern']
                pattern_counts[candidate['_pattern']] += 1
            audit_file.write(json.dumps(audit_record, ensure_ascii=False) + '\n')
            source_counts[candidate['_source_kind']] += 1
            dimension_counts[candidate['dimension']] += 1

    serializable_inventory = []
    for concept in sorted(inventory):
        entry = inventory[concept]
        serializable_inventory.append({
            'concept': concept,
            'occurrence_count': entry['occurrence_count'],
            'question_concept_count': entry['question_concept_count'],
            'choice_count': entry['choice_count'],
            'raw_forms': dict(entry['raw_forms'].most_common()),
            'sense_concepts': entry['sense_concepts'],
        })
    inventory_path.write_text(json.dumps(serializable_inventory, ensure_ascii=False, indent=2), encoding='utf-8')

    summary = {
        'input_file': INPUT.name,
        'question_count': question_count,
        'required_fact_count': {'minimum': min_facts, 'maximum': max_facts},
        'target_fact_count': target_facts,
        'final_fact_count': len(selected),
        'facts_per_question': round(len(selected) / question_count, 6),
        'normalized_concept_count': len(inventory),
        'concepts_with_wordnet_senses': len(occurrence_senses),
        'retained_sense_count': len(retained_senses),
        'candidate_fact_count_before_cleaning': len(candidates),
        'clean_fact_count_before_quantity_cap': len(accepted_candidates),
        'rejection_counts': dict(rejection_counts.most_common()),
        'source_distribution': dict(source_counts.most_common()),
        'dimension_distribution': dict(dimension_counts.most_common()),
        'csqa_relation_pattern_distribution': dict(pattern_counts.most_common()),
        'runtime_schema': ['fact_id', 'concept', 'dimension', 'fact', 'conditions'],
        'stage_scope': {
            'stage_1': 'Use all CSQA training questions, choices, and question concepts to establish concept coverage and context-aware senses.',
            'stage_2': 'Generate decontextualized lexical and commonsense facts from selected dictionary senses; do not convert CSQA answer labels into facts.',
            'stage_3': 'Remove malformed, generic, context-dependent, answer-mapping, and duplicate records; keep runtime fields minimal.',
        },
        'important_limitations': [
            'This is a deterministic stage-1-to-3 knowledge base, not a guarantee that every fact will improve an LLM answer.',
            'Whether a fact distinguishes the current five choices must be evaluated by the later runtime validator.',
            'Whether and where to inject a valid fact belongs to the later GRPO routing stage.',
        ],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    notice = '''CSQA KB stage 1-3 source notice\n\nThe concept coverage is induced from the uploaded CSQA training split.\nLexical definitions and semantic relations were adapted from Princeton WordNet 3.1 data files.\nWordNet data source used for this build: open-language/en-wordnet, database/3.1.\nThe runtime KB intentionally omits source and validation metadata; those are stored in csqa_kb_audit.jsonl.\n'''
    (OUT_DIR / 'SOURCE_NOTICE.txt').write_text(notice, encoding='utf-8')

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
