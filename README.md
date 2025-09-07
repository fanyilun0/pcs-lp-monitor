# PancakeSwap LP池监控器

🔍 一个强大的 PancakeSwap V2/V3 流动性池监控工具，支持实时监控多个 LP 池的 TVL 变化、代币数量变化，并通过企业微信 Webhook 发送报警通知。

## ✨ 主要功能

- 🎯 **多池监控**: 同时监控多个 PancakeSwap V2/V3 流动性池
- 📊 **实时数据**: 实时获取池中代币数量、价格和 TVL 信息
- 🚨 **智能报警**: 当 TVL 或代币数量变化超过阈值时自动报警
- 📱 **企业微信推送**: 支持通过企业微信 Webhook 发送详细报警信息
- 💾 **数据存储**: 自动保存历史数据为 CSV 和 JSON 格式
- 🔄 **价格缓存**: 智能价格缓存机制，减少 API 调用次数
- 🌐 **多数据源**: 支持 DexScreener 和 CoinGecko 双重价格数据源
- 📈 **美观展示**: 带颜色 emoji 的状态展示和报警信息

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd pcs-lp-monitor

# 创建虚拟环境 (推荐)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或者 Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置设置

#### 环境变量配置
复制环境变量模板并配置：
```bash
cp env.example .env
```

编辑 `.env` 文件：
```env
# 企业微信 Webhook 配置 (必需)
WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_webhook_key_here

# 代理配置 (可选)
PROXY_URL=
USE_PROXY=false
```

#### 监控池配置
编辑 `config.json` 文件来配置要监控的流动性池：

```json
{
  "network": {
    "name": "BSC",
    "chain_id": 56,
    "rpc_url": "https://bsc-dataseed1.binance.org/"
  },
  "monitoring": {
    "interval_seconds": 30,
    "alert_threshold_percent": 5.0
  },
  "pools": [
    {
      "name": "MCH/WBNB Pool (1%)",
      "contract_address": "0x5b6F666Fb65412338c1eCE48c1acD92a38d716C6",
      "pool_type": "v3",
      "enabled": true,
      "target_token": "MCH"
    }
  ],
  "tokens": {
    "MCH": {
      "coingecko_id": "monsterra-mch"
    }
  }
}
```

### 3. 运行监控

```bash
python main.py
```

## 📊 监控展示

### 控制台输出示例
```
====================================================
📊 LP池监控状态 - 2024-01-01 12:00:00
====================================================
💾 价格缓存: 4 个代币 (DexScreener: 2)
====================================================

池名称                     代币对        TVL(USD)        
----------------------------------------------------
MCH/WBNB Pool (1%)        MCH/WBNB     $1,500,893     
  ├─ MCH: 29,013,516.85 @ $0.0517 (75.2%, $1,500,000)
  └─ WBNB: 2,456.78 @ $364.12 (24.8%, $893,457)

MTP/USDT Pool (0.01%)     MTP/USDT     $856,432       
  ├─ MTP: 12,345,678.90 @ $0.0345 (50.1%, $425,776)
  └─ USDT: 430,656.12 @ $1.0000 (49.9%, $430,656)

====================================================
```

### 报警消息示例
当检测到重大变化时，会发送详细的企业微信消息：

```
🚨 LP池报警通知
═══════════════════════
📈 池名称: MCH/WBNB Pool (1%)
📅 时间: 2024-01-01 12:30:15

💰 TVL变化:
   🟢 变化幅度: +7.23%
   📊 变化前: $1,400,256.78
   📊 变化后: $1,500,893.54
   💵 变化金额: $100,636.76

🪙 MCH 数量变化:
   🟢 变化幅度: +12.45%
   📈 变化前: 25,789,123.45
   📈 变化后: 29,013,516.85
   📊 变化数量: 3,224,393.40

📋 当前池详情:
═══════════════════════
🔸 MCH:
   💰 数量: 29,013,516.85
   💲 价格: $0.051700
   📊 TVL: $1,500,000.00 (75.2%)

🔹 WBNB:
   💰 数量: 2,456.78
   💲 价格: $364.120000
   📊 TVL: $893,457.00 (24.8%)

🔗 池地址: 0x5b6F666F...38d716C6
💎 总 TVL: $1,500,893.54
```

## ⚙️ 配置详解

### 网络配置
```json
"network": {
  "name": "BSC",           // 网络名称
  "chain_id": 56,          // 链 ID
  "rpc_url": "https://bsc-dataseed1.binance.org/"  // RPC 节点
}
```

### 监控配置
```json
"monitoring": {
  "interval_seconds": 30,        // 监控间隔（秒）
  "alert_threshold_percent": 5.0 // 报警阈值（百分比）
}
```

### 池配置
```json
"pools": [
  {
    "name": "池显示名称",
    "contract_address": "0x...",  // 池合约地址
    "pool_type": "v3",           // 池类型: v2 或 v3
    "enabled": true,             // 是否启用监控
    "target_token": "MCH"        // 目标代币符号
  }
]
```

### 代币配置
```json
"tokens": {
  "MCH": {
    "coingecko_id": "monsterra-mch"  // CoinGecko ID (可选)
  }
}
```

### 输出配置
```json
"output": {
  "console_log": true,        // 控制台输出
  "file_log": true,          // 文件日志
  "log_directory": "./logs", // 日志目录
  "data_directory": "./data", // 数据目录
  "export_csv": true,        // 导出 CSV
  "export_json": true        // 导出 JSON
}
```

## 🏗️ 系统架构

### 核心组件
- **LPMonitor**: 主监控类，负责池数据获取和变化检测
- **PoolData**: 数据结构，存储池的状态信息
- **价格缓存系统**: 智能缓存机制，提高性能和稳定性
- **Webhook 通知**: 异步消息发送系统

### 数据流程
1. **初始化**: 加载配置，连接 Web3，设置价格缓存
2. **数据获取**: 并行获取多个池的代币储备量
3. **价格查询**: 批量获取代币价格（DexScreener 优先，CoinGecko 备用）
4. **变化检测**: 对比历史数据，检测 TVL 和代币数量变化
5. **报警推送**: 超过阈值时发送详细报警信息
6. **数据存储**: 保存历史数据为 CSV 和 JSON 格式

### 价格数据源
1. **DexScreener** (优先): 实时去中心化交易所价格
2. **CoinGecko** (备用): 主流代币市场价格

## 📁 目录结构

```
pcs-lp-monitor/
├── main.py              # 主程序
├── webhook.py           # Webhook 消息发送
├── config.py            # 配置管理
├── config.json          # 主配置文件
├── .env                 # 环境变量 (需要创建)
├── env.example          # 环境变量模板
├── requirements.txt     # Python 依赖
├── logs/               # 日志文件目录
├── data/               # 数据文件目录
└── README.md           # 项目文档
```

## 🔧 高级功能

### 自动池类型检测
系统会自动检测池是 V2 还是 V3 类型，无需手动配置。

### 智能价格缓存
- 5分钟 TTL 缓存，减少 API 调用
- 批量价格获取，提高效率
- 多数据源容错机制

### 异步消息发送
- 支持长消息自动分段
- 防频率限制的延迟发送
- 异步非阻塞处理

## 🚨 报警规则

### 触发条件
当以下任一条件满足时触发报警：
- TVL 变化幅度 ≥ 配置阈值
- 目标代币数量变化 ≥ 配置阈值

### 报警等级
- 🚨 **严重**: 变化幅度 ≥ 阈值 × 3
- ⚠️ **警告**: 变化幅度 ≥ 阈值 × 2  
- 🔺 **提醒**: 变化幅度 ≥ 阈值

## 📝 日志管理

### 日志级别
- **INFO**: 正常监控信息、价格获取成功
- **WARNING**: 重大变化报警、API 请求失败
- **ERROR**: 系统错误、配置问题

### 日志文件
- 位置: `./logs/lp_monitor.log`
- 格式: `时间戳 - 级别 - 消息内容`
- 自动轮转，避免文件过大

## 🛠️ 故障排除

### 常见问题

**1. 无法连接到网络**
```
❌ 无法连接到网络: BSC
```
- 检查网络连接
- 更换 RPC 节点 URL
- 确认防火墙设置

**2. 代币价格获取失败**
```
⚠️ 无法获取 XXX 的价格，所有API源都失败
```
- 检查代币符号是否正确
- 在 `tokens` 配置中添加 `coingecko_id`
- 确认代币在交易所有流动性

**3. Webhook 发送失败**
```
❌ 发送webhook消息失败
```
- 检查 `.env` 文件中的 `WEBHOOK_URL`
- 确认企业微信机器人密钥正确
- 检查网络连接

**4. 池数据获取失败**
```
❌ 获取V3池 0x... 数据失败
```
- 确认池地址正确
- 检查池类型配置 (v2/v3)
- 确认池有足够流动性

### 调试模式
在 `config.json` 中启用调试日志：
```json
"price_cache": {
  "enable_debug_logs": true
}
```

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## ⚠️ 免责声明

本工具仅用于监控目的，不构成任何投资建议。使用者应当自行承担使用本工具的风险。

## 📞 支持

如果遇到问题或有功能建议，请：
1. 查看本文档的故障排除部分
2. 搜索已有的 Issues
3. 创建新的 Issue 并详细描述问题

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给它一个星标！**

Made with ❤️ for DeFi Community

</div>
