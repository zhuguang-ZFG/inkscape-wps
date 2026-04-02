#!/usr/bin/env sh
# 从 kamalmostafa/hershey-fonts 拉取 .jhf 到 inkscape_wps/data/fonts
# 注意：上游部分文件 glyph 索引为占位符 12345，拉取后请运行:
#   python3 tools/generate_hershey_jhf_maps.py
# 并删除仍为 12345 的 .jhf（见 data/fonts/README.txt）。
set -e
BASE="https://raw.githubusercontent.com/kamalmostafa/hershey-fonts/master"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/inkscape_wps/data/fonts"
mkdir -p "$DEST"
curl -sL "$BASE/COPYING" -o "$DEST/Hershey-COPYING.txt"
curl -sL "$BASE/AUTHORS" -o "$DEST/Hershey-AUTHORS.txt"
curl -sL "$BASE/README.md" -o "$DEST/Hershey-README-upstream.md"
curl -sL "$BASE/hershey-fonts/hershey.txt" -o "$DEST/hershey-index-reference.txt"
list="$(curl -sL "https://api.github.com/repos/kamalmostafa/hershey-fonts/contents/hershey-fonts?ref=master" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(x['name'] for x in d if x['name'].endswith('.jhf')))")"
for name in $list; do
  curl -sL --max-time 120 --fail "$BASE/hershey-fonts/$name" -o "$DEST/$name" && echo "ok $name" || echo "fail $name"
done
python3 "$ROOT/tools/generate_hershey_jhf_maps.py"
echo "请手动检查并删除仍以 12345 为索引的 .jhf（见 README.txt）"
