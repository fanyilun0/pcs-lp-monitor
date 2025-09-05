好的，这是一个非常常见的需求，特别是对于关注早期项目的开发者和交易者。获取一个刚在BSC（BNB Smart Chain）上发布的Token价格，核心是找到它在去中心化交易所（DEX）上的流动性池，并读取该池中的资产比例。

总结 (TL;DR)

对于你的问题，最直接和推荐的答案是：

可以，DexScreener 是获取这类价格信息的绝佳工具。

它提供了非常友好的免费API，你可以通过API来获取价格。

下面我将详细解释如何操作，并提供其他几种方法。

方法一：使用DEX数据聚合平台API (最推荐)

这类平台专门监控各个链上的DEX活动，一旦有新的流动性池被创建，它们会迅速索引并提供数据。

1. DexScreener API

DexScreener 是目前最流行、最及时的工具之一。它的API非常简单易用。

工作原理：你不能直接用Token合约地址查询价格，因为一个Token可能在多个DEX、与不同的Token（如WBNB, USDT）组成交易对。你需要查询的是 “交易对（Pair）” 的信息。

API 使用步骤:

找到交易对地址 (Pair Address)：

首先，在 DexScreener 网站上搜索你的Token合约地址。

网站会列出所有包含该Token的交易对。选择你关心的那一个（通常是流动性最好的，比如 Token/WBNB 或 Token/USDT）。

进入该交易对的页面，URL中会包含交易对的地址，或者在页面信息中也能找到。

调用API:
使用以下API端点来获取该交易对的最新信息，包括价格。

https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}
{chain}: 对于BSC，这里填写 bsc。

{pair_address}: 填写上一步找到的交易对地址。

示例:
假设你要查询一个Token，在PancakeSwap上与WBNB组成的交易对，其交易对地址是 0x...。
你的API请求URL就是：
https://api.dexscreener.com/latest/dex/pairs/bsc/0x...

返回的JSON数据会非常丰富，其中 priceUsd 字段就是以美元计价的价格，priceNative 是以链的基础货币（BNB）计价的价格。

