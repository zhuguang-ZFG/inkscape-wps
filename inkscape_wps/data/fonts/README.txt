本目录：随包分发的 Hershey 单线矢量字体（.jhf）及 ASCII 映射（*.jhf.map.json）
================================================================================

上游来源
--------
- 仓库：https://github.com/kamalmostafa/hershey-fonts
- 字形数据许可：见 Hershey-COPYING.txt（须保留署名：Dr. A. V. Hershey / U.S. NBS；格式转换 James Hurt 等，详见全文）。
- libhersheyfont 等代码为 GPLv2+，本仓库**仅再分发**其中的 .jhf 字形数据文件，不链接该 GPL 库。

已包含的 .jhf（共 11 个）
--------------------------
上游仓库中部分 .jhf 的索引列为占位符「12345」，无法映射字符，已从随包集合中剔除。
当前保留文件均有真实 glyph 编号，并已生成 **同名 *.jhf.map.json**（前 95 行按文件内顺序对应 ASCII 可打印字符 32–126）。

- rowmans / rowmand / rowmant：罗马体系列
- scriptc / scripts：手写体系列
- greekc / greeks：希腊字母
- cyrilc_1：西里尔
- gothgbt / gothgrt / gothitt：哥特类

使用方式
--------
1. 在应用「开始 → 单线字库 → 选择 JSON…」旁，可将配置项 **stroke_font_json_path** 留空时仍默认 **hershey_roman.json**；若要用本目录 .jhf，请将配置指向具体路径，例如：
   （包内相对路径因安装方式而异，建议使用文件选择器选至本目录下的 rowmans.jhf。）
2. 推荐每个 .jhf 与同目录下 **stem.jhf.map.json** 成对存在（可用 `tools/generate_hershey_jhf_maps.py` 生成）。若缺失 map，程序会按 **文件内前 95 个 glyph 行** 顺序对应 ASCII 32–126（与脚本规则一致）；非 rowmans 行序的字库请自备 map。

重新生成映射
------------
若从上游更新了 .jhf，可在仓库根执行：
  python3 tools/generate_hershey_jhf_maps.py
