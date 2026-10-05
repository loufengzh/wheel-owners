# wheel-owners

**安装前，检查一组本地 Python wheel 是否会占用相互冲突的目标路径。**

[English](../README.md) · 简体中文 · [Русский](README.ru.md) · [Deutsch](README.de.md)

`wheel-owners` 根据显式提供的安装布局，计算各个 wheel 的目标文件路径，
并报告文件归属冲突及文件与目录之间的冲突。它使用固定版本
`installer==0.7.0` 和仅记录结果的目标适配器，不安装待检查的包，
也不导入或执行包中的代码。

检查通过仅表示：在支持的模型内，本次提供的文件没有产生归属冲突。
这不保证依赖兼容、导入正确、ABI 兼容或软件安全。

## 快速开始

需要在 POSIX 主机上使用 Python 3.10 或更新版本。在项目源码目录中运行：

```sh
python -m pip install .
wheel-owners --layout examples/posix-layout.json a.whl b.whl
```

将 `a.whl` 和 `b.whl` 替换为真实的本地 wheel 文件名。
此安装方式不假设项目已发布到 PyPI。安装本工具时，pip 可能下载构建或运行
依赖；预检命令本身不访问网络。

必须显式列出要检查的所有 wheel，包括已经选定的依赖。
工具不解析依赖、不下载包、不递归扫描目录，也不检查当前已安装的环境。
同一规范化发行包名称只能提供一个文件，不能把多个候选版本交给工具选择。

## 安装布局

`--layout` 接受严格的 JSON 文件。目前仅支持
`posix-case-sensitive-v1`。示例：

```json
{
  "profile": "posix-case-sensitive-v1",
  "interpreter": "/venv/bin/python",
  "scheme": {
    "purelib": "/venv/lib/python3.12/site-packages",
    "platlib": "/venv/lib/python3.12/site-packages",
    "scripts": "/venv/bin",
    "headers": "/venv/include",
    "data": "/venv"
  }
}
```

五个安装方案路径均为必填项。所有路径必须是规范化的 POSIX 绝对路径。
它们是模型输入，工具不会创建或探测这些目录；`interpreter` 用于生成脚本，
不会被执行。请按实际计划使用的布局修改示例。

路径按 Unicode 码点精确比较，不模拟 Windows 或 macOS 的大小写折叠，
不进行 Unicode 规范化，也不模拟符号链接或实际文件系统的所有行为。

## 冲突规则

- 多个归属方占用同一目标文件，即使内容完全相同，也算冲突。
- 某个路径既需要是文件，又需要是其他文件的父目录，算冲突。
- 检查支持的 wheel 根目录和 `.data` 路径映射、原始脚本，以及生成的
  console/GUI entry-point 脚本。
- 不同安装方案映射到相同路径时，也会比较其文件归属。
- 仅共享目录不算冲突，因此文件互不重叠的命名空间包可以通过路径检查。
  这仍不保证其导入行为正确。

## 输出和退出码

输出为确定性 JSON，包含 `schema_version: 1`。

| 退出码 | 含义 |
| --- | --- |
| `0` | 本次支持的模型内未发现归属冲突 |
| `1` | 发现归属冲突 |
| `2` | 输入无效或情况不受支持，不能视为检查通过 |

相同输入、布局及工具和依赖版本下，结果具有确定性。
格式错误的 wheel 或路径、不受支持的版本或转换，以及重复的规范化发行包
名称都会导致错误。不要把进程失败或缺失输出当作成功。

本工具不模拟字节码生成、`.pth` 执行、导入钩子或可编辑安装。
完整边界见 [limits.md](limits.md)。

## 相关工作与开发

文件冲突检测已有长期的上游讨论和研究，本项目不声称首创。
[相关工具与一手资料](comparison.md) 包括 pip #4625、pip PR #14249、
`pip check`、`check-wheel-contents`、ModuleGuard 和 SPIRA Trust。
上游状态记录于 2026-10-05，发布前需要重新核实。

```sh
python -m pip install -e '.[test]'
python -m pytest
python -m build
```

构建命令需要开发环境中已安装 `build`。
请参阅 [贡献指南](../CONTRIBUTING.md)、[安全说明](../SECURITY.md)
和 [MIT 许可证](../LICENSE)。详细接口以[英文说明](../README.md)为准。
