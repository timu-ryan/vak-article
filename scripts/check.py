#!/usr/bin/env python3
"""
Проверка статьи по требованиям журнала:
  - объём (знаки с пробелами) — всего и без списка литературы;
  - число слов в аннотации;
  - число источников, каждый ли цитируется, нет ли ссылок на несуществующие;
  - порядок нумерации по первому упоминанию (с --renumber — перенумеровать);
  - оставшиеся места «[уточнить]».

    python3 article/scripts/check.py [--renumber]
"""
import os
import re
import sys

PATH = os.path.join(os.path.dirname(__file__), '..', 'article.md')
text = open(PATH, encoding='utf-8').read()

head, _, refs_part = text.partition('## Литература')
ref_lines = [l for l in refs_part.strip().splitlines() if re.match(r'^\d+\. ', l)]
refs = {int(l.split('.', 1)[0]): l.split('. ', 1)[1] for l in ref_lines}

cited_order = []
for group in re.findall(r'\[(\d+(?:\s*[,–-]\s*\d+)*)\]', head):
    for part in re.split(r'\s*,\s*', group):
        if re.search(r'[–-]', part):
            a, b = map(int, re.split(r'\s*[–-]\s*', part))
            nums = range(a, b + 1)
        else:
            nums = [int(part)]
        for num in nums:
            if num not in cited_order:
                cited_order.append(num)

if '--renumber' in sys.argv:
    mapping = {old: new for new, old in enumerate(cited_order, start=1)}
    missing = [k for k in refs if k not in mapping]
    for k in missing:  # нецитируемые — в конец (их потом надо процитировать или убрать)
        mapping[k] = len(mapping) + 1

    def sub(m):
        parts = re.split(r'\s*,\s*', m.group(1))
        out = []
        for part in parts:
            if re.search(r'[–-]', part):
                a, b = map(int, re.split(r'\s*[–-]\s*', part))
                out.extend(mapping[x] for x in range(a, b + 1))
            else:
                out.append(mapping[int(part)])
        out = sorted(set(out))
        return '[' + ', '.join(map(str, out)) + ']'

    new_head = re.sub(r'\[(\d+(?:\s*[,–-]\s*\d+)*)\]', sub, head)
    new_refs = '\n'.join(f'{mapping[k]}. {v}' for k, v in sorted(refs.items(), key=lambda kv: mapping[kv[0]]))
    with open(PATH, 'w', encoding='utf-8') as f:
        f.write(new_head + '## Литература\n\n' + new_refs + '\n')
    print('Перенумеровано:', ', '.join(f'{k}→{v}' for k, v in sorted(mapping.items()) if k != v) or 'без изменений')
    sys.exit(0)


def plain(s):
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', s)          # картинки
    s = re.sub(r'^\|?[-| :]+\|?$', '', s, flags=re.M)     # разделители таблиц
    s = s.replace('|', ' ')
    s = re.sub(r'[*#`]', '', s)
    s = re.sub(r'\$\$.*?\$\$', ' ', s, flags=re.S)        # выносные формулы — не текст
    s = s.replace('$', '')
    s = re.sub(r'\\[a-zA-Z]+', '', s)                      # команды LaTeX во внутритекстовых формулах
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n\s*\n+', '\n', s)
    return s.strip()


full = plain(text)
body = plain(head[head.index('## Введение'):])
abstract = re.search(r'\*\*Аннотация\.\*\*(.*?)\n\n', text, flags=re.S).group(1)
abstract_en = re.search(r'\*\*Abstract\.\*\*(.*?)\n\n', text, flags=re.S).group(1)

print(f'Знаков с пробелами: всего {len(full)}, основной текст (Введение — Заключение) {len(body)}')
print(f'Аннотация: {len(abstract.split())} слов; Abstract: {len(abstract_en.split())} words')
print(f'Источников: {len(refs)}; процитировано: {len(cited_order)}')
uncited = sorted(set(refs) - set(cited_order))
unknown = sorted(set(cited_order) - set(refs))
if uncited:
    print('  не процитированы:', uncited)
if unknown:
    print('  ссылки на несуществующие номера:', unknown)
in_order = cited_order == sorted(cited_order)
print('Нумерация по порядку первого упоминания:', 'да' if in_order else f'нет ({cited_order})')
todo = re.findall(r'\[уточнить[^\]]*\]', text)
print(f'Мест «уточнить»: {len(todo)}')
for t in todo:
    print('  ', t)
