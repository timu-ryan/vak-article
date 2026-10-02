#!/usr/bin/env python3
"""
Таблицы и числа для статьи — только из результатов пакетного сравнения (`npm run compare`).
Пишет Markdown в article/data/.

Откуда берутся результаты:
  - article/data/compare/*.csv (копия, metrics.csv — в сжатом виде .gz) — если папка есть;
  - иначе out/compare/*.csv в проекте программы.
Координаты станций — из real-measures/ проекта, если он рядом, иначе из таблицы ниже.

    python3 scripts/tables.py            # из папки статьи
    npm run compare && python3 article/scripts/tables.py   # в проекте, после пересчёта
"""
import csv
import glob
import gzip
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta

ARTICLE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ROOT = os.path.abspath(os.path.join(ARTICLE, '..'))
LOCAL = os.path.join(ARTICLE, 'data', 'compare')
OUT = LOCAL if os.path.isdir(LOCAL) else os.path.join(ROOT, 'out', 'compare')
DATA = os.path.join(ARTICLE, 'data')
os.makedirs(DATA, exist_ok=True)

# Точки выпуска (первая строка файлов зондирования) — на случай, если real-measures/ нет рядом.
COORDS = {
    '10393': (52.2093, 14.1204),
    '10238': (52.8149, 9.9250),
    '03808': (50.2186, -5.3261),
    '32540': (53.08, 158.58),
    '24122': (68.50, 112.43),
}

STATIONS = {
    '10393': 'Линденберг (Германия)',
    '10238': 'Берген (Германия)',
    '03808': 'Камборн (Великобритания)',
    '32540': 'Петропавловск-Камчатский',
    '24122': 'Оленёк',
}
ORDER = ['10393', '10238', '03808', '32540', '24122']

OLD = 'step/hold/constant/nearest'
CURRENT = 'linear/hold/constant/nearest'

VERTICAL = {'step': 'ступенька', 'linear': 'линейная', 'spline': 'сплайн', 'pchip': 'PCHIP', 'poly3': 'полином 3-й ст.'}
SURFACE = {'hold': 'нижний уровень', 'zero': 'ноль у земли', 'power': 'степенной закон', 'observed': 'приземный факт'}
ASCENT = {'constant': '5 м/с', 'measured': 'профиль зонда'}
INTERP = {'nearest': 'узел', 'bilinear': 'билинейная'}


def method_label(key):
    v, s, a, i = key.split('/')
    return f'{VERTICAL[v]}; {SURFACE[s]}; {ASCENT[a]}; {INTERP[i]}'


def read(name):
    path = os.path.join(OUT, name)
    if not os.path.exists(path) and os.path.exists(path + '.gz'):
        with gzip.open(path + '.gz', 'rt', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def fmt(x, digits=2):
    return f'{x:.{digits}f}'.replace('.', ',')


def table(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |', '|' + '|'.join('---' for _ in header) + '|']
    lines += ['| ' + ' | '.join(str(c) for c in row) + ' |' for row in rows]
    return '\n'.join(lines) + '\n'


def write(name, text):
    with open(os.path.join(DATA, name), 'w', encoding='utf-8') as f:
        f.write(text)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float('nan')


metrics = read('metrics.csv')
summary = read('summary.csv')
factors = read('factors.csv')
crossings = read('crossings.csv')
numbers = []

# --- Таблица 1. Станции и запуски -------------------------------------------------------------
first_rows = {wmo: {'latitude': str(lat), 'longitude': str(lon)} for wmo, (lat, lon) in COORDS.items()}
seen = set()
for path in sorted(glob.glob(os.path.join(ROOT, 'real-measures', '**', '*.csv'), recursive=True)):
    wmo = os.path.basename(path).split('-')[-1].replace('.csv', '')
    if wmo in seen:
        continue
    seen.add(wmo)
    with open(path, encoding='utf-8') as f:
        first_rows[wmo] = next(csv.DictReader(f))

report = [r for r in metrics if r['kind'] == 'report' and r['method'] == CURRENT]
top = [r for r in report if r['height_m'] == '16000']
by_station = defaultdict(list)
for r in top:
    by_station[r['wmo']].append(r)

launches = defaultdict(set)
for r in report:
    launches[r['wmo']].add(r['sounding'])

rows = []
for wmo in ORDER:
    rs = by_station[wmo]
    first = first_rows[wmo]
    count = len(launches[wmo])
    count_text = str(count) if count == len(rs) else f'{count} (до 16 км — {len(rs)})'
    drift = [float(r['obs_dist_km']) for r in rs]
    t16 = [float(r['obs_time_min']) for r in rs]
    kind = 'GPS, 1–2 с' if rs[0]['positions'] == 'measured' else 'TEMP, восстановлено по ветру'
    rows.append([
        wmo, STATIONS[wmo],
        f"{fmt(float(first['latitude']))}° с. ш., {fmt(abs(float(first['longitude'])))}° {'в' if float(first['longitude']) >= 0 else 'з'}. д.",
        kind, count_text, fmt(mean(drift), 1), fmt(max(drift), 1), round(mean(t16)),
    ])
all_drift = [float(r['obs_dist_km']) for r in top]
write('t1_stations.md', table(
    ['ВМО', 'Станция', 'Координаты', 'Траектория', 'Запусков', 'Снос до 16 км, км (ср.)', 'макс.', 'Время до 16 км, мин'],
    rows,
))
numbers.append(f'запусков всего: {sum(len(v) for v in launches.values())}, до 16 км поднялись {len(top)}; '
               f'средний снос до 16 км: {fmt(mean(all_drift), 1)} км; '
               f'минимум {fmt(min(all_drift), 1)}, максимум {fmt(max(all_drift), 1)} км')

# --- Таблица 2. Влияние факторов -----------------------------------------------------------
FACTOR_NAMES = {'vertical': 'Ветер по высоте', 'surface': 'Ниже 850 гПа', 'ascent': 'Подъём', 'interp': 'Выборка по сетке'}
VALUE_NAMES = {**VERTICAL, **SURFACE, **ASCENT, **INTERP}
cols = ['all'] + ORDER
rows = []
for r in factors:
    rows.append([FACTOR_NAMES[r['factor']], VALUE_NAMES[r['value']]] +
                [fmt(float(r[f'mean_error_{c}_km'])) for c in cols])
write('t2_factors.md', table(['Фактор', 'Значение', 'Все'] + ORDER, rows))

# --- Таблица 3. Способы: старый, текущий, лучшие, худшие ---------------------------------
allrows = [r for r in summary if r['station'] == 'all']
allrows.sort(key=lambda r: float(r['mean_error_km']))
pick = {r['method']: r for r in allrows}
chosen = []
for key in [OLD, CURRENT] + [r['method'] for r in allrows[:5]] + [r['method'] for r in allrows[-3:]]:
    if key not in chosen:
        chosen.append(key)
rank = {r['method']: i + 1 for i, r in enumerate(allrows)}
rows = []
for key in chosen:
    r = pick[key]
    note = 'старый способ' if key == OLD else 'текущий способ программы' if key == CURRENT else ''
    rows.append([rank[key], method_label(key), fmt(float(r['mean_error_km'])), fmt(float(r['rmse_km'])),
                 fmt(float(r['max_error_km']), 1), note])
write('t3_methods.md', table(['Место из 80', 'Способ (по высоте; ниже 850 гПа; подъём; сетка)',
                              'Средняя ошибка, км', 'RMSE, км', 'Макс., км', 'Примечание'], rows))
best = allrows[0]
numbers.append(f"лучший способ: {method_label(best['method'])}: {fmt(float(best['mean_error_km']))} км; "
               f"текущий: {fmt(float(pick[CURRENT]['mean_error_km']))}; старый: {fmt(float(pick[OLD]['mean_error_km']))}; "
               f"худший: {method_label(allrows[-1]['method'])}: {fmt(float(allrows[-1]['mean_error_km']))}")
numbers.append(f'разброс средних ошибок 80 способов: {fmt(float(allrows[0]["mean_error_km"]))}–{fmt(float(allrows[-1]["mean_error_km"]))} км')

# --- Таблица 4. Ошибка по высотам ------------------------------------------------------------
HEIGHTS = [1500, 3000, 5000, 7000, 9000, 12000, 16000]
keys = [OLD, CURRENT, 'linear/hold/constant/bilinear', best['method']]
keys = list(dict.fromkeys(keys))
rows = []
for key in keys:
    r = pick[key]
    rows.append([method_label(key)] + [fmt(float(r[f'mean_error_{h}m_km'])) for h in HEIGHTS])
# средний фактический снос на тех же высотах — для относительной ошибки
drift_h = {h: mean(float(r['obs_dist_km']) for r in report if r['height_m'] == str(h)) for h in HEIGHTS}
rows.append(['_средний фактический снос_'] + [fmt(drift_h[h], 1) for h in HEIGHTS])
write('t4_heights.md', table(['Способ'] + [f'{fmt(h / 1000, 1)} км' for h in HEIGHTS], rows))
rel = float(pick[CURRENT]['mean_error_16000m_km']) / drift_h[16000]
rel_best = float(pick[best['method']]['mean_error_16000m_km']) / drift_h[16000]
numbers.append(f'на 16 км: средний снос {fmt(drift_h[16000], 1)} км; ошибка текущего способа '
               f'{fmt(float(pick[CURRENT]["mean_error_16000m_km"]))} км ({fmt(rel * 100, 0)} % сноса); '
               f'лучшего {fmt(float(pick[best["method"]]["mean_error_16000m_km"]))} км ({fmt(rel_best * 100, 0)} %)')

# Угол места на 16 км: факт и ошибка прогноза (для наведения антенны)
eps = []
for r in top:
    d_obs, d_fc = float(r['obs_dist_km']), float(r['fc_dist_km'])
    e_obs = math.degrees(math.atan2(16.0, d_obs))
    e_fc = math.degrees(math.atan2(16.0, d_fc))
    eps.append((r['wmo'], e_obs, abs(e_fc - e_obs)))
numbers.append(f'угол места на 16 км (факт): от {fmt(min(e for _, e, _ in eps), 1)}° до {fmt(max(e for _, e, _ in eps), 1)}°; '
               f'средняя ошибка прогноза угла места (текущий способ) {fmt(mean(d for _, _, d in eps), 1)}°, '
               f'максимум {fmt(max(d for _, _, d in eps), 1)}°')
for wmo in ORDER:
    es = [e for w, e, _ in eps if w == wmo]
    numbers.append(f'  {wmo}: угол места на 16 км от {fmt(min(es), 1)}° до {fmt(max(es), 1)}°')

# --- Таблица 5. Пересечения трасс: 32540, 29.09.2026 11:30 ----------------------------------
EXAMPLE = '32540-202609291130'
release = next(datetime.fromisoformat(r['release'].replace('Z', '+00:00'))
               for r in metrics if r['sounding'] == EXAMPLE)


def clock(minutes):
    return (release + timedelta(seconds=round(float(minutes) * 60))).strftime('%H:%M')


def cell(h1, h2, t1, t2):
    if not h1:
        return '—'
    h1, h2 = round(float(h1)), round(float(h2))
    hs = f'{h1} м' if abs(h2 - h1) < 50 else f'{h1}–{h2} м'
    ts = clock(t1) if abs(float(t2) - float(t1)) < 0.5 else f'{clock(t1)}–{clock(t2)}'
    return f'{hs}, {ts}'


ex = [r for r in crossings if r['sounding'] == EXAMPLE]
airways = []
for r in sorted((r for r in ex if r['obs_from_m']), key=lambda r: float(r['obs_from_min'])):
    if r['airway'] not in airways:
        airways.append(r['airway'])
variants = [OLD, CURRENT, 'spline/hold/constant/nearest', 'pchip/hold/constant/nearest',
            'poly3/hold/constant/nearest', 'linear/hold/constant/bilinear',
            'linear/observed/constant/bilinear', 'spline/observed/constant/bilinear']
fact = {r['airway']: r for r in ex if r['method'] == CURRENT}
rows = [['**факт**'] + [cell(fact[a]['obs_from_m'], fact[a]['obs_to_m'], fact[a]['obs_from_min'], fact[a]['obs_to_min'])
                       if a in fact and fact[a]['obs_from_m'] else '—' for a in airways]]
for key in variants:
    got = {r['airway']: r for r in ex if r['method'] == key}
    rows.append([method_label(key)] + [cell(got[a]['fc_from_m'], got[a]['fc_to_m'], got[a]['fc_from_min'], got[a]['fc_to_min'])
                                       if a in got and got[a]['fc_from_m'] else '—' for a in airways])
write('t5_example_crossings.md', table(['Траектория'] + airways, rows))
numbers.append(f'пример {EXAMPLE}: выпуск {release:%d.%m.%Y %H:%M} UTC, трассы по факту: {", ".join(airways)}')

# --- Таблица 6. Верификация пересечений по способам (уникальные запуски) ----------------------
stats = defaultdict(lambda: {'hit': 0, 'miss': 0, 'false': 0, 'dh': [], 'dt': []})
per_station = defaultdict(lambda: {'hit': 0, 'miss': 0, 'false': 0})
for r in crossings:
    s = stats[r['method']]
    s[r['status']] += 1
    per_station[(r['method'], r['wmo'])][r['status']] += 1
    if r['status'] == 'hit':
        s['dh'].append(abs(float(r['fc_from_m']) - float(r['obs_from_m'])))
        s['dt'].append(abs(float(r['fc_from_min']) - float(r['obs_from_min'])))


def verif(key):
    s = stats[key]
    h, m, f = s['hit'], s['miss'], s['false']
    return h, m, f, h / (h + m), f / (h + f) if h + f else 0.0, h / (h + m + f), mean(s['dh']), mean(s['dt'])


ranked = sorted(stats, key=lambda k: (verif(k)[1] + verif(k)[2], -verif(k)[3], verif(k)[6]))
chosen = list(dict.fromkeys(variants + ranked[:3] + ranked[-2:]))
rows = []
for key in chosen:
    h, m, f, pod, far, csi, dh, dt = verif(key)
    st = ' / '.join(f"{per_station[(key, w)]['hit']}–{per_station[(key, w)]['miss']}–{per_station[(key, w)]['false']}"
                    for w in ['32540', '24122'])
    rows.append([method_label(key), h, m, f, fmt(pod), fmt(far), fmt(csi), round(dh), fmt(dt, 1), st])
write('t6_crossings.md', table(
    ['Способ', 'Угадано', 'Пропущено', 'Ложных', 'POD', 'FAR', 'CSI', 'Ошибка высоты входа, м',
     'Ошибка времени входа, мин', '32540 / 24122 (угад.–проп.–ложн.)'],
    rows,
))
actual = {w: per_station[(CURRENT, w)]['hit'] + per_station[(CURRENT, w)]['miss'] for w in ['32540', '24122']}
numbers.append(f'фактических пересечений: 32540 — {actual["32540"]}, 24122 — {actual["24122"]}; '
               f'запусков с планшетом: {len({r["sounding"] for r in crossings})}')
numbers.append(f'лучшие по пересечениям: ' + '; '.join(f'{method_label(k)} {verif(k)[:3]}' for k in ranked[:3]))
numbers.append(f'худшие по пересечениям: ' + '; '.join(f'{method_label(k)} {verif(k)[:3]}' for k in ranked[-2:]))

write('numbers.md', '\n'.join(f'- {n}' for n in numbers) + '\n')
print('\n'.join(numbers))
print('таблицы:', ', '.join(sorted(os.listdir(DATA))))
