# 破万卷 · po-wan-juan

一个会成长的个人阅读分身 Skill：把你主动投喂的记录整理为可审计的本地知识库，生成每日不超过 400 字的洞察，每周只推荐一篇值得亲读的文章。

**公开演示 v0.1.0**：https://zhoujinq.github.io/po-wan-juan/  
**Skill 目录**：[`po-wan-juan/`](po-wan-juan/)

> 公开网站只是介绍与虚构演示，不处理真实记录。你的聊天、档案、评测集和知识库不应上传到这个仓库。

## 它做什么

- 原样保存你主动提供的文字、链接、图片、视频与感悟，保留来源和阅读状态。
- 先浏览全部，再选择少量内容深读；无法访问就明确标记，不假装读过。
- 每日只留下“最值得知道、与你何干、留给你判断的问题”，正文不超过 400 字。
- 每周只推荐一篇全文已读的文章，没有合格者就宁缺毋滥。
- 用可修改、可回滚的档案和好坏评测集校准偏好，不宣称训练模型或创造意识。

## 获取与开始

1. 下载或克隆仓库，复制完整的 `po-wan-juan/` 文件夹到你的 Agent 用户技能目录。
2. 保持 `SKILL.md`、`references/`、`scripts/` 的相对结构不变。
3. 把下面这句话交给支持 Skill 的 Agent：

   > 使用破万卷，开始蒸馏我。请先分两轮询问我的目标、长期主题、现实瓶颈、代表性文字和好坏反馈，再引导我确认本地数据目录与提醒时间。不要在我确认前修改长期偏好或创建系统任务。

不同 Agent 的技能目录和加载方式不同，请按所用产品的说明安装。本仓库不提供统一的在线账号服务。

## 本地数据工具

脚本仅依赖 Python 标准库。以下命令中的数据目录必须位于仓库之外。

```bash
python po-wan-juan/scripts/powanjuan.py init --root "<数据目录>" --timezone "Asia/Shanghai"
python po-wan-juan/scripts/powanjuan.py ingest --root "<数据目录>" --date 2026-11-22 --text "一条虚构测试记录"
python po-wan-juan/scripts/powanjuan.py validate-daily --file "<数据目录>/daily/2026-11-22.md"
python po-wan-juan/scripts/powanjuan.py status --root "<数据目录>" --date 2026-11-22
```

Windows 提醒脚本位于 `po-wan-juan/scripts/windows-reminder.ps1`。只有使用者明确确认后才安装；可用 `-ShowReminder` 预览，用 `-Uninstall` 移除提醒且不删除个人数据。

## 运行测试

```bash
python -m unittest discover -s tests -v
```

测试只使用临时目录和虚构记录，不读取真实个人数据。覆盖初始化不覆盖、归档去重、档案确认、ISO 周计算、400 字校验、公开页锚点、隐私标识和外部运行依赖。

## 项目结构

```text
.
├── index.html                 # GitHub Pages 公开入口；无后端、无外部运行依赖
├── 破万卷.html                # 初始介绍页原稿，保留作历史记录
├── po-wan-juan/               # 可安装的完整 Skill
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── docs/
│   ├── 需求依赖矩阵.md
│   ├── 公开边界.md
│   └── 验收记录.md
└── tests/                     # Python 标准库自动测试
```

## 隐私与边界

详见 [`docs/公开边界.md`](docs/公开边界.md)。核心原则：公开方法和虚构演示，不公开真实个人数据。原始记录默认保存在使用者选择的本地目录；除读取公开来源所必需外，不上传私人内容。

灵感来源为页面列出的公开课程实验；本项目不是官方课程作品。
