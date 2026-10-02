#!/usr/bin/env bash
# SVG → PNG для вставки в Word: все article/figures/*.svg (без подпапок).
# Если папка статьи лежит внутри проекта программы и есть out/compare/figures,
# сначала обновляются рисунки «факт | прогноз» для рис. 4 и 5.
# Нужен headless Chromium (Playwright); путь можно задать в CHROME.
set -euo pipefail
ARTICLE="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="$(cd "$ARTICLE/.." && pwd)"
CHROME=${CHROME:-$(ls -d ~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell 2>/dev/null | tail -1)}
if [ -z "$CHROME" ]; then
  echo "Не найден headless Chromium: задайте путь в переменной CHROME" >&2
  exit 1
fi

if [ -d "$PROJECT/out/compare/figures" ]; then
  cp "$PROJECT/out/compare/figures/32540_20260929_1130_+6h__step-hold-constant-nearest.svg" "$ARTICLE/figures/compare-32540.svg"
  cp "$PROJECT/out/compare/figures/24122_20260928_1130_+6h__linear-hold-constant-nearest.svg" "$ARTICLE/figures/compare-24122.svg"
fi

for svg in "$ARTICLE"/figures/*.svg; do
  size=$(grep -o 'width="[0-9]*" height="[0-9]*"' "$svg" | head -1 | grep -o '[0-9]*' | paste -sd, -)
  "$CHROME" --headless --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --window-size="$size" --screenshot="${svg%.svg}.png" "file://$svg" 2>/dev/null
  echo "${svg%.svg}.png ($size)"
done
