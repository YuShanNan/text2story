import os

# 在 Windows GBK 终端下，Rich 会检测为 legacy 模式并尝试渲染低分辨率字符版本，
# 导致 Unicode emoji（如 🎬 U+0001F3AC）因无法编码为 GBK 而崩溃。
# NO_COLOR=1 让 Rich 跳过所有颜色/emoji 渲染，保证测试在任意终端下可运行。
os.environ.setdefault("NO_COLOR", "1")
