# 狼人杀 / Werewolf

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-支持-blue.svg)](https://www.docker.com/)

> 基于 Web 的狼人杀多人游戏

## 简介

线下玩狼人杀没带牌，或者牌不够。这个项目就是一个线上发牌工具，手机上打开网页就能发牌看身份，省得洗牌分牌。


## 在线体验

🎮 **示例网站**：[https://wmh.wwww.us.kg/](https://wmh.wwww.us.kg/)

> 网站可能存在访问延迟或临时维护，如无法访问请稍后再试或自行部署。

## 特性

- 完整的狼人杀游戏逻辑，支持 14 种角色
- 4-12 人灵活配置，自适应人数
- 上帝视角管理游戏
- 基于 Socket.IO 的实时通信
- 中英双语支持
- Docker 一键部署
- 适配 PC 和手机端

## 角色列表

| 角色 | 技能 |
|------|------|
| 狼人 | 夜晚杀人 |
| 预言家 | 夜晚查验身份 |
| 女巫 | 解药救人 / 毒药杀人 |
| 猎人 | 死后开枪 |
| 守卫 | 夜晚保护一人 |
| 白痴 | 投票出局可翻牌免死 |
| 平民 | 投票找出狼人 |
| 白狼王 | 自爆带走一人 |
| 狼美人 | 魅惑一人同死 |
| 石像鬼 | 可查验身份 |
| 丘比特 | 连接两人为情侣 |
| 长老 | 有两条命 |
| 替罪羊 | 平票时被选中 |
| 吹笛者 | 魅惑所有人获胜 |

## 快速开始

### Docker 部署（推荐）

```bash
# 启动服务
docker-compose up

# 访问游戏
# http://localhost:5544
```

就这么简单，一条命令启动全部服务。

### 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python app.py

# 访问 http://localhost:5544
# 可以在yml修改
```

## 游戏流程

```
创建房间 → 设置角色 → 开放房间 → 玩家加入 → 开始游戏
```

1. **创建房间**：点击"创建房间"，成为上帝
2. **设置游戏**：调整玩家人数和角色配置
3. **开放房间**：点击"开放房间"，其他玩家可加入
4. **加入游戏**：玩家输入房间号和昵称加入
5. **开始游戏**：上帝点击"开始游戏"，系统自动分配角色
6. **查看角色**：上帝查看所有角色，玩家只看到自己的角色
