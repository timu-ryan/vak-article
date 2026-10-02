/**
 * Рисунки для статьи (SVG) — из тех же модулей, что и программа:
 *
 *   npx tsx article/scripts/figures.mts
 *
 * 1. profile.svg — профиль скорости ветра на станции: измерения зонда, значения GRIB на уровнях
 *    и кривые разных способов интерполяции; справа — нижние 3 км с режимами приземного слоя.
 * 2. error-height.svg — средняя ошибка положения от высоты для ключевых вариантов (out/compare/metrics.csv).
 *
 * PNG делаются отдельно headless-браузером (см. render.sh).
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { activeStep, DEFAULT_VERTICAL, vectorToWind, windToVector, type VerticalOptions } from '@rs/shared';
import { GribCatalog } from '../../packages/server/src/grib/catalog.ts';
import { GribFieldCache } from '../../packages/server/src/grib/reader.ts';
import { SoundingRegistry } from '../../packages/server/src/soundings/registry.ts';
import { windAtHeight, type WindNode } from '../../packages/server/src/trajectory/vertical.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const outDir = join(root, 'article', 'figures');
mkdirSync(outDir, { recursive: true });

// Цвета: проверенная категориальная палитра (порядок фиксирован), текст — нейтральный.
const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4'];
const INK = '#0b0b0b';
const MUTED = '#52514e';
const GRID = '#e4e3df';
const FONT = "'Times New Roman', 'Liberation Serif', Times, serif";

const n = (v: number): string => (Math.round(v * 100) / 100).toString();
const esc = (s: string): string => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

interface Series {
  label: string;
  color: string;
  dash?: string;
  width?: number;
  points: [number, number][];
}

interface Panel {
  x: number;
  y: number;
  w: number;
  h: number;
  xMax: number;
  yMax: number;
  xTicks: number[];
  yTicks: number[];
  xLabel: string;
  yLabel: string;
  title: string;
  series: Series[];
  dots?: { points: [number, number][]; label: string };
  /** true — по вертикали высота, по горизонтали величина (профиль). */
}

function panel(p: Panel): string {
  const sx = (v: number): number => p.x + (v / p.xMax) * p.w;
  const sy = (v: number): number => p.y + p.h - (v / p.yMax) * p.h;
  const parts: string[] = [];
  parts.push(`<text x="${p.x}" y="${p.y - 14}" font-size="17" font-weight="700" fill="${INK}">${esc(p.title)}</text>`);
  for (const t of p.yTicks) {
    parts.push(`<line x1="${p.x}" y1="${n(sy(t))}" x2="${p.x + p.w}" y2="${n(sy(t))}" stroke="${GRID}"/>`);
    parts.push(`<text x="${p.x - 8}" y="${n(sy(t))}" font-size="14" fill="${MUTED}" text-anchor="end" dominant-baseline="central">${String(t).replace('.', ',')}</text>`);
  }
  for (const t of p.xTicks) {
    parts.push(`<line x1="${n(sx(t))}" y1="${p.y}" x2="${n(sx(t))}" y2="${p.y + p.h}" stroke="${GRID}"/>`);
    parts.push(`<text x="${n(sx(t))}" y="${p.y + p.h + 20}" font-size="14" fill="${MUTED}" text-anchor="middle">${String(t).replace('.', ',')}</text>`);
  }
  parts.push(`<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" fill="none" stroke="${MUTED}" stroke-width="1"/>`);
  parts.push(`<text x="${p.x + p.w / 2}" y="${p.y + p.h + 44}" font-size="15" fill="${INK}" text-anchor="middle">${esc(p.xLabel)}</text>`);
  parts.push(`<text transform="translate(${p.x - 46} ${p.y + p.h / 2}) rotate(-90)" font-size="15" fill="${INK}" text-anchor="middle">${esc(p.yLabel)}</text>`);
  parts.push(`<clipPath id="clip-${p.x}"><rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}"/></clipPath>`);
  const lines = p.series
    .map((s) => {
      const d = s.points.map(([a, b], i) => `${i === 0 ? 'M' : 'L'}${n(sx(a))} ${n(sy(b))}`).join(' ');
      return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width ?? 2}" stroke-linejoin="round"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/>`;
    })
    .join('');
  parts.push(`<g clip-path="url(#clip-${p.x})">${lines}</g>`);
  if (p.dots) {
    parts.push(
      p.dots.points
        .filter(([a, b]) => a <= p.xMax && b <= p.yMax)
        .map(([a, b]) => `<circle cx="${n(sx(a))}" cy="${n(sy(b))}" r="5" fill="${INK}" stroke="#ffffff" stroke-width="2"/>`)
        .join(''),
    );
  }
  return parts.join('');
}

function legend(x: number, y: number, items: { label: string; color: string; dash?: string; dot?: boolean; width?: number }[], columns: number, colWidth: number): string {
  return items
    .map((item, i) => {
      const cx = x + (i % columns) * colWidth;
      const cy = y + Math.floor(i / columns) * 24;
      const mark = item.dot
        ? `<circle cx="${cx + 14}" cy="${cy}" r="5" fill="${INK}" stroke="#ffffff" stroke-width="2"/>`
        : `<line x1="${cx}" y1="${cy}" x2="${cx + 28}" y2="${cy}" stroke="${item.color}" stroke-width="${item.width ?? 2.5}"${item.dash ? ` stroke-dasharray="${item.dash}"` : ''}/>`;
      return `${mark}<text x="${cx + 36}" y="${cy}" font-size="14" fill="${INK}" dominant-baseline="central">${esc(item.label)}</text>`;
    })
    .join('');
}

function svg(width: number, height: number, body: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" font-family="${FONT}">` +
    `<rect width="${width}" height="${height}" fill="#ffffff"/>${body}</svg>`
  );
}

// ---------------------------------------------------------------------------------------------
// 1. Профиль ветра
// ---------------------------------------------------------------------------------------------
const PROFILE_SOUNDING = process.argv[2] ?? '03808-202609292315';
const LEAD = 6;

const soundings = await SoundingRegistry.load(join(root, 'real-measures'));
const sounding = soundings.get(PROFILE_SOUNDING);
if (!sounding) throw new Error(`Нет зондирования ${PROFILE_SOUNDING}`);

const catalog = new GribCatalog([join(root, 'data'), join(root, 'data', 'archive')]);
const fields = new GribFieldCache(64);
const release = new Date(sounding.release);
const run = await catalog.pickRunForLead(release, LEAD);
if (!run) throw new Error(`Нет прогона +${LEAD} ч для ${PROFILE_SOUNDING}`);
const step = activeStep(run.steps, (release.getTime() - run.runTime.getTime()) / 3600_000) as number;

// Ветер GRIB на уровнях в точке выпуска (билинейно), снизу вверх.
const nodes: WindNode[] = [];
for (const level of [...run.levels].sort((a, b) => a.heightM - b.heightM)) {
  const path = catalog.filePath(run, level.mb, step);
  if (!path) continue;
  const field = await fields.load(path);
  const s = field.sample(sounding.lon, sounding.lat, 'bilinear');
  nodes.push({ heightM: level.heightM, ...windToVector(s.windDirDeg, s.windSpeedMs) });
}

const speedAt = (h: number, vertical: VerticalOptions): number => {
  const w = windAtHeight(nodes, h, vertical, sounding.surfaceWind);
  return vectorToWind(w).speedMs;
};
const curve = (vertical: VerticalOptions, top: number, stepM = 25): [number, number][] =>
  Array.from({ length: Math.floor(top / stepM) + 1 }, (_, i) => i * stepM).map((h) => [speedAt(h, vertical), h / 1000]);

const measured: [number, number][] = [];
let last = -Infinity;
for (const p of sounding.profile) {
  if (p.heightM > 16500) break;
  if (p.heightM - last < 50) continue;
  measured.push([Math.hypot(p.u, p.v), p.heightM / 1000]);
  last = p.heightM;
}

const methods: { label: string; method: VerticalOptions['method']; dash?: string }[] = [
  { label: 'ступенька (ближайший уровень)', method: 'step', dash: '7 4' },
  { label: 'линейная', method: 'linear' },
  { label: 'натуральный кубический сплайн', method: 'spline' },
  { label: 'PCHIP', method: 'pchip' },
  { label: 'полином Лагранжа 3-й степени', method: 'poly' },
];
const surfaces: { label: string; surface: VerticalOptions['surface']; dash?: string }[] = [
  { label: 'держать ветер 850 гПа', surface: 'hold' },
  { label: 'ноль у земли', surface: 'zero' },
  { label: 'степенной закон, α = 1/7', surface: 'power' },
  { label: 'к измеренному приземному ветру', surface: 'observed' },
];

const maxSpeed = Math.ceil(Math.max(...measured.map(([v]) => v), ...nodes.map((x) => Math.hypot(x.u, x.v))) / 5) * 5;
const lowMax = Math.ceil(
  Math.max(...measured.filter(([, h]) => h <= 3).map(([v]) => v), ...nodes.filter((x) => x.heightM <= 3000).map((x) => Math.hypot(x.u, x.v))) / 5,
) * 5;
const gribDots: [number, number][] = nodes.map((x) => [Math.hypot(x.u, x.v), x.heightM / 1000]);

const left = panel({
  x: 90, y: 60, w: 560, h: 620, xMax: maxSpeed, yMax: 16,
  xTicks: Array.from({ length: maxSpeed / 5 + 1 }, (_, i) => i * 5),
  yTicks: [0, 2, 4, 6, 8, 10, 12, 14, 16],
  xLabel: 'Скорость ветра, м/с', yLabel: 'Высота над точкой выпуска, км',
  title: 'а) Способы интерполяции между уровнями (0–16 км)',
  series: [
    { label: 'измерения зонда', color: MUTED, width: 1.2, points: measured },
    ...methods.map((m, i) => ({
      label: m.label,
      color: SERIES[i] as string,
      ...(m.dash ? { dash: m.dash } : {}),
      points: curve({ ...DEFAULT_VERTICAL, method: m.method, surface: 'hold' }, 16000),
    })),
  ],
  dots: { points: gribDots, label: 'GRIB' },
});
const right = panel({
  x: 760, y: 60, w: 400, h: 620, xMax: lowMax, yMax: 3,
  xTicks: Array.from({ length: lowMax / 5 + 1 }, (_, i) => i * 5),
  yTicks: [0, 0.5, 1, 1.5, 2, 2.5, 3],
  xLabel: 'Скорость ветра, м/с', yLabel: '',
  title: 'б) Ниже 850 гПа (0–3 км), линейная интерполяция',
  series: [
    { label: 'измерения зонда', color: MUTED, width: 1.2, points: measured.filter(([, h]) => h <= 3.2) },
    ...surfaces.map((s, i) => ({
      label: s.label,
      color: SERIES[i] as string,
      points: curve({ ...DEFAULT_VERTICAL, method: 'linear', surface: s.surface }, 3000, 10),
    })),
  ],
  dots: { points: gribDots, label: 'GRIB' },
});
const legendA = legend(90, 770, [
  { label: 'измерения зонда', color: MUTED, width: 1.5 },
  { label: 'значения GRIB на уровнях', color: INK, dot: true },
  ...methods.map((m, i) => ({ label: m.label, color: SERIES[i] as string, ...(m.dash ? { dash: m.dash } : {}) })),
], 2, 300);
const legendB = legend(760, 770, surfaces.map((s, i) => ({ label: s.label, color: SERIES[i] as string })), 1, 300);
const runText = `${run.id.slice(6, 8)}.${run.id.slice(4, 6)}.${run.id.slice(0, 4)} ${run.id.slice(8)}:00 UTC`;
const caption =
  `Зондирование ВМО ${sounding.wmo}, выпуск ${release.toISOString().slice(0, 16).replace('T', ' ')} UTC; ` +
  `прогноз GRIB: прогон ${runText}, срок +${step} ч, точка выпуска`;
writeFileSync(
  join(outDir, 'profile.svg'),
  svg(1220, 880, left + right + legendA + legendB +
    `<text x="90" y="${880 - 14}" font-size="13" fill="${MUTED}">${esc(caption)}</text>`),
);
console.log('profile.svg:', caption, `; уровней ${nodes.length}`);

// ---------------------------------------------------------------------------------------------
// 2. Ошибка от высоты
// ---------------------------------------------------------------------------------------------
const csv = readFileSync(join(root, 'out', 'compare', 'metrics.csv'), 'utf8').trim().split('\n');
const header = (csv[0] as string).split(',');
const col = (name: string): number => header.indexOf(name);
const KEYS = [
  { key: 'step/hold/constant/nearest', label: 'старый способ: ступенька, ближайший узел', dash: '7 4' },
  { key: 'linear/hold/constant/nearest', label: 'текущий: линейная, ближайший узел' },
  { key: 'linear/hold/constant/bilinear', label: 'линейная, билинейная выборка' },
  { key: 'spline/observed/constant/bilinear', label: 'сплайн, приземный факт, билинейная' },
];
const sums = new Map<string, Map<number, number[]>>();
for (const line of csv.slice(1)) {
  const cells = line.split(',');
  if (cells[col('kind')] !== 'profile') continue;
  const key = cells[col('method')] as string;
  if (!KEYS.some((k) => k.key === key)) continue;
  const h = Number(cells[col('height_m')]);
  const byH = sums.get(key) ?? new Map<number, number[]>();
  byH.set(h, [...(byH.get(h) ?? []), Number(cells[col('error_km')])]);
  sums.set(key, byH);
}
const meanOf = (xs: number[]): number => xs.reduce((a, b) => a + b, 0) / xs.length;
const errSeries: Series[] = KEYS.map((k, i) => ({
  label: k.label,
  color: SERIES[i] as string,
  ...(k.dash ? { dash: k.dash } : {}),
  points: [...(sums.get(k.key) ?? new Map()).entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([h, errs]) => [h / 1000, meanOf(errs)] as [number, number]),
}));
const errMax = Math.ceil(Math.max(...errSeries.flatMap((s) => s.points.map(([, e]) => e))));
const chart = panel({
  x: 90, y: 60, w: 900, h: 440, xMax: 16, yMax: errMax,
  xTicks: [0, 2, 4, 6, 8, 10, 12, 14, 16],
  yTicks: Array.from({ length: errMax + 1 }, (_, i) => i),
  xLabel: 'Высота над точкой выпуска, км', yLabel: 'Средняя ошибка положения, км',
  title: 'Средняя ошибка положения зонда по высоте, прогноз +6 ч',
  series: errSeries,
});
writeFileSync(
  join(outDir, 'error-height.svg'),
  svg(1060, 640, chart + legend(90, 575, KEYS.map((k, i) => ({ label: k.label, color: SERIES[i] as string, ...(k.dash ? { dash: k.dash } : {}) })), 2, 460)),
);
for (const s of errSeries) console.log('error-height:', s.label, s.points.at(-1));
