#!/usr/bin/env python3
"""
Pancake LP池监控主程序
监控指定LP池的TVL和代币数量变化
"""

import json
import time
import os
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from dataclasses import dataclass, asdict
import logging
import requests
from threading import Lock
import asyncio
from webhook import send_message_async


@dataclass
class PoolData:
    """LP池数据结构"""
    timestamp: str
    pool_address: str
    pool_name: str
    token0_symbol: str
    token1_symbol: str
    token0_amount: float
    token1_amount: float
    token0_price_usd: float
    token1_price_usd: float
    tvl_usd: float
    target_token: str
    target_token_amount: float
    target_token_price: float


class LPMonitor:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.w3 = None
        self.setup_web3()
        self.setup_logging()
        self.setup_directories()
        self.previous_data: Dict[str, PoolData] = {}
        
        # 价格缓存系统
        self.price_cache: Dict[str, Dict] = {}  # {symbol: {price: float, timestamp: datetime, source: str}}
        self.price_cache_lock = Lock()  # 线程安全锁
        self.cache_ttl_minutes = self.config.get('price_cache', {}).get('ttl_minutes', 5)  # 缓存有效期5分钟
        self.batch_request_symbols = set()  # 待批量请求的代币符号
        
    def load_config(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ 配置文件 {self.config_file} 不存在!")
            print("请先运行: python pool_manager.py add [池地址] --name [池名称]")
            exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ 配置文件格式错误: {e}")
            exit(1)
    
    def setup_web3(self) -> None:
        """设置Web3连接"""
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.config['network']['rpc_url']))
            if not self.w3.is_connected():
                print(f"❌ 无法连接到网络: {self.config['network']['name']}")
                exit(1)
            print(f"✅ 成功连接到 {self.config['network']['name']}")
        except Exception as e:
            print(f"❌ Web3连接失败: {e}")
            exit(1)
    
    def setup_logging(self) -> None:
        """设置日志"""
        if self.config['output'].get('file_log', False):
            log_dir = self.config['output'].get('log_directory', './logs')
            os.makedirs(log_dir, exist_ok=True)
            
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(f"{log_dir}/lp_monitor.log"),
                    logging.StreamHandler() if self.config['output'].get('console_log', True) else logging.NullHandler()
                ]
            )
        else:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
        
        self.logger = logging.getLogger(__name__)
    
    def setup_directories(self) -> None:
        """创建必要的目录"""
        data_dir = self.config['output'].get('data_directory', './data')
        log_dir = self.config['output'].get('log_directory', './logs')
        
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        
        # 在配置中添加价格缓存设置
        if 'price_cache' not in self.config:
            self.config['price_cache'] = {
                'ttl_minutes': 5,  # 缓存有效期5分钟
                'batch_threshold': 5,  # 批量请求阈值
                'enable_stats': True  # 启用统计信息
            }
    
    def get_v3_pool_abi(self) -> List[Dict]:
        """获取PancakeSwap V3池的正确ABI"""
        return [
            {
                "inputs": [],
                "name": "token0",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token1", 
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "fee",
                "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "liquidity",
                "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "slot0",
                "outputs": [
                    {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                    {"internalType": "int24", "name": "tick", "type": "int24"},
                    {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                    {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                    {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                    {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                    {"internalType": "bool", "name": "unlocked", "type": "bool"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def get_v2_pool_abi(self) -> List[Dict]:
        """获取PancakeSwap V2池的ABI"""
        return [
            {
                "inputs": [],
                "name": "token0",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token1", 
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
                    {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
                    {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def get_erc20_abi(self) -> List[Dict]:
        """获取ERC20代币的基本ABI"""
        return [
            {
                "inputs": [],
                "name": "symbol",
                "outputs": [{"internalType": "string", "name": "", "type": "string"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def detect_pool_type(self, pool_address: str) -> str:
        """检测池类型 (V2 或 V3)"""
        try:
            # 尝试V3池的方法
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self.get_v3_pool_abi()
            )
            
            # 尝试调用V3特有的fee()方法
            pool_contract.functions.fee().call()
            return "v3"
            
        except Exception:
            try:
                # 尝试V2池的方法
                pool_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(pool_address),
                    abi=self.get_v2_pool_abi()
                )
                
                # 尝试调用V2特有的getReserves()方法
                pool_contract.functions.getReserves().call()
                return "v2"
                
            except Exception:
                return "unknown"
    
    def get_token_info(self, token_address: str) -> Optional[Tuple[str, int]]:
        """获取代币信息"""
        try:
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.get_erc20_abi()
            )
            
            symbol = token_contract.functions.symbol().call()
            decimals = token_contract.functions.decimals().call()
            
            return (symbol, decimals)
        except Exception as e:
            self.logger.error(f"获取代币 {token_address} 信息失败: {e}")
            return None
    
    def get_v3_pool_reserves(self, pool_address: str) -> Optional[Tuple[str, str, float, float, int, int]]:
        """获取V3池的储备量和代币信息"""
        try:
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self.get_v3_pool_abi()
            )
            
            # 获取代币地址
            token0_address = pool_contract.functions.token0().call()
            token1_address = pool_contract.functions.token1().call()
            
            # 获取代币信息
            token0_info = self.get_token_info(token0_address)
            token1_info = self.get_token_info(token1_address)
            
            if not token0_info or not token1_info:
                return None
                
            token0_symbol, token0_decimals = token0_info
            token1_symbol, token1_decimals = token1_info
            
            # 获取代币合约
            erc20_abi = self.get_erc20_abi()
            token0_contract = self.w3.eth.contract(address=token0_address, abi=erc20_abi)
            token1_contract = self.w3.eth.contract(address=token1_address, abi=erc20_abi)
            
            # 获取池中的代币余额
            token0_balance = token0_contract.functions.balanceOf(pool_address).call()
            token1_balance = token1_contract.functions.balanceOf(pool_address).call()
            
            # 转换为人类可读的数量
            token0_amount = token0_balance / (10 ** token0_decimals)
            token1_amount = token1_balance / (10 ** token1_decimals)
            
            return (token0_symbol, token1_symbol, token0_amount, token1_amount, 
                   token0_decimals, token1_decimals)
                   
        except Exception as e:
            self.logger.error(f"获取V3池 {pool_address} 数据失败: {e}")
            return None
    
    def get_v2_pool_reserves(self, pool_address: str) -> Optional[Tuple[str, str, float, float, int, int]]:
        """获取V2池的储备量和代币信息"""
        try:
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self.get_v2_pool_abi()
            )
            
            # 获取代币地址
            token0_address = pool_contract.functions.token0().call()
            token1_address = pool_contract.functions.token1().call()
            
            # 获取代币信息
            token0_info = self.get_token_info(token0_address)
            token1_info = self.get_token_info(token1_address)
            
            if not token0_info or not token1_info:
                return None
                
            token0_symbol, token0_decimals = token0_info
            token1_symbol, token1_decimals = token1_info
            
            # 获取储备量
            reserves = pool_contract.functions.getReserves().call()
            token0_reserve = reserves[0]
            token1_reserve = reserves[1]
            
            # 转换为人类可读的数量
            token0_amount = token0_reserve / (10 ** token0_decimals)
            token1_amount = token1_reserve / (10 ** token1_decimals)
            
            return (token0_symbol, token1_symbol, token0_amount, token1_amount, 
                   token0_decimals, token1_decimals)
                   
        except Exception as e:
            self.logger.error(f"获取V2池 {pool_address} 数据失败: {e}")
            return None
            
    def get_pool_reserves(self, pool_address: str, pool_type: str = None) -> Optional[Tuple[str, str, float, float, int, int]]:
        """获取LP池的储备量和代币信息"""
        if pool_type is None:
            pool_type = self.detect_pool_type(pool_address)
            
        if pool_type == "v3":
            return self.get_v3_pool_reserves(pool_address)
        elif pool_type == "v2":
            return self.get_v2_pool_reserves(pool_address)
        else:
            self.logger.error(f"未知的池类型: {pool_type} (池地址: {pool_address})")
            return None
    
    def is_cache_valid(self, cache_entry: Dict) -> bool:
        """检查缓存是否有效"""
        if not cache_entry:
            return False
        
        cache_time = cache_entry.get('timestamp')
        if not cache_time:
            return False
        
        now = datetime.now()
        ttl = timedelta(minutes=self.cache_ttl_minutes)
        
        return (now - cache_time) < ttl
    
    def get_cached_price(self, symbol: str) -> Optional[float]:
        """从缓存获取价格"""
        with self.price_cache_lock:
            cache_entry = self.price_cache.get(symbol.upper())
            if self.is_cache_valid(cache_entry):
                self.logger.debug(f"使用缓存价格 {symbol}: ${cache_entry['price']} (来源: {cache_entry['source']})")
                return cache_entry['price']
        return None
    
    def set_cached_price(self, symbol: str, price: float, source: str = 'api') -> None:
        """设置缓存价格"""
        with self.price_cache_lock:
            self.price_cache[symbol.upper()] = {
                'price': price,
                'timestamp': datetime.now(),
                'source': source
            }
    
    def get_coingecko_mapping(self) -> Dict[str, str]:
        """从配置文件动态获取代币符号到CoinGecko ID的映射"""
        mapping = {
            'WBNB': 'binancecoin',  # WBNB应该使用BNB的价格，因为它们1:1兑换
            'BNB': 'binancecoin', 
            'USDT': 'tether',
            'USDC': 'usd-coin',
            'ETH': 'ethereum',
            'BTCB': 'bitcoin',
        }
        
        # 从配置文件的tokens部分获取额外的映射
        tokens_config = self.config.get('tokens', {})
        for token_symbol, token_info in tokens_config.items():
            if 'coingecko_id' in token_info:
                mapping[token_symbol.upper()] = token_info['coingecko_id']
        
        return mapping
    
    
    def get_dexscreener_pair_addresses(self) -> Dict[str, str]:
        """从配置文件动态获取代币到DexScreener交易对地址的映射"""
        mapping = {}
        
        # 从配置文件的pools部分获取交易对地址
        pools_config = self.config.get('pools', [])
        for pool in pools_config:
            if pool.get('enabled', True):
                target_token = pool.get('target_token')
                pool_address = pool.get('contract_address')
                if target_token and pool_address:
                    mapping[target_token.upper()] = pool_address
        
        return mapping
    
    def fetch_prices_from_dexscreener(self, symbols: List[str]) -> Dict[str, float]:
        """从DexScreener获取价格"""
        pair_mapping = self.get_dexscreener_pair_addresses()
        prices = {}
        
        for symbol in symbols:
            symbol_upper = symbol.upper()
            pair_address = pair_mapping.get(symbol_upper)
            
            if not pair_address:
                continue
                
            try:
                url = f"https://api.dexscreener.com/latest/dex/pairs/bsc/{pair_address}"
                self.logger.info(f"从DexScreener获取 {symbol} 价格: {pair_address}")
                
                response = requests.get(url, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    if 'pair' in data and data['pair']:
                        pair_data = data['pair']
                        
                        # 获取USD价格
                        price_usd = pair_data.get('priceUsd')
                        if price_usd:
                            price = float(price_usd)
                            prices[symbol_upper] = price
                            self.logger.info(f"DexScreener价格 {symbol}: ${price}")
                        else:
                            self.logger.warning(f"DexScreener未找到 {symbol} 的USD价格")
                    else:
                        self.logger.warning(f"DexScreener未找到交易对数据: {pair_address}")
                else:
                    self.logger.warning(f"DexScreener API请求失败 {symbol}: {response.status_code}")
                    
            except Exception as e:
                self.logger.warning(f"从DexScreener获取 {symbol} 价格失败: {e}")
        
        return prices
    
    def fetch_prices_from_coingecko(self, symbols: List[str]) -> Dict[str, float]:
        """批量从CoinGecko获取价格"""
        coingecko_mapping = self.get_coingecko_mapping()
        prices = {}
        
        # 筛选出有CoinGecko ID映射的代币
        coingecko_ids = []
        symbol_to_id = {}
        
        for symbol in symbols:
            symbol_upper = symbol.upper()
            coingecko_id = coingecko_mapping.get(symbol_upper)
            if coingecko_id:
                coingecko_ids.append(coingecko_id)
                symbol_to_id[coingecko_id] = symbol_upper
        
        if not coingecko_ids:
            return prices
        
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': ','.join(coingecko_ids),
                'vs_currencies': 'usd'
            }
            
            self.logger.info(f"批量从CoinGecko获取 {len(coingecko_ids)} 个代币价格: {list(symbol_to_id.values())}")
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                for coingecko_id, price_data in data.items():
                    symbol = symbol_to_id.get(coingecko_id)
                    price = price_data.get('usd')
                    if symbol and price:
                        prices[symbol] = float(price)
                        self.logger.info(f"CoinGecko价格 {symbol}: ${price}")
            else:
                self.logger.warning(f"CoinGecko API请求失败: {response.status_code}")
                
        except Exception as e:
            self.logger.warning(f"批量获取CoinGecko价格失败: {e}")
        
        return prices
    
    def get_token_price(self, symbol: str) -> Optional[float]:
        """获取代币价格 - 带缓存机制，移除模拟价格逻辑"""
        symbol_upper = symbol.upper()
        
        # 首先检查缓存
        cached_price = self.get_cached_price(symbol_upper)
        if cached_price is not None:
            return cached_price
        
        # 尝试从DexScreener获取
        dexscreener_prices = self.fetch_prices_from_dexscreener([symbol_upper])
        if symbol_upper in dexscreener_prices:
            price = dexscreener_prices[symbol_upper]
            self.set_cached_price(symbol_upper, price, 'dexscreener')
            return price
        
        # 尝试从CoinGecko获取
        coingecko_prices = self.fetch_prices_from_coingecko([symbol_upper])
        if symbol_upper in coingecko_prices:
            price = coingecko_prices[symbol_upper]
            self.set_cached_price(symbol_upper, price, 'coingecko')
            return price
        
        # 如果都获取失败，返回None
        self.logger.warning(f"无法获取 {symbol} 的价格，所有API源都失败")
        return None
    
    def get_multiple_token_prices(self, symbols: List[str]) -> Dict[str, float]:
        """批量获取多个代币价格 - 优先使用DexScreener，移除模拟价格"""
        prices = {}
        uncached_symbols = []
        
        # 检查缓存
        for symbol in symbols:
            cached_price = self.get_cached_price(symbol)
            if cached_price is not None:
                prices[symbol.upper()] = cached_price
            else:
                uncached_symbols.append(symbol)
        
        # 批量获取未缓存的价格
        if uncached_symbols:
            # 优先尝试DexScreener
            dexscreener_prices = self.fetch_prices_from_dexscreener(uncached_symbols)
            
            # 对于DexScreener未获取到的，再尝试CoinGecko
            remaining_symbols = [s for s in uncached_symbols if s.upper() not in dexscreener_prices]
            coingecko_prices = self.fetch_prices_from_coingecko(remaining_symbols) if remaining_symbols else {}
            
            for symbol in uncached_symbols:
                symbol_upper = symbol.upper()
                if symbol_upper in dexscreener_prices:
                    price = dexscreener_prices[symbol_upper]
                    self.set_cached_price(symbol_upper, price, 'dexscreener')
                    prices[symbol_upper] = price
                elif symbol_upper in coingecko_prices:
                    price = coingecko_prices[symbol_upper]
                    self.set_cached_price(symbol_upper, price, 'coingecko')
                    prices[symbol_upper] = price
                else:
                    # 如果无法获取价格，记录警告但不添加到prices中
                    self.logger.warning(f"无法获取 {symbol} 的价格")
        
        return prices
    
    def calculate_tvl(self, token0_symbol: str, token1_symbol: str, 
                     token0_amount: float, token1_amount: float) -> Optional[Tuple[float, float, float, float, float, float, float]]:
        """计算TVL及各代币占比 - 使用批量价格获取"""
        # 批量获取两个代币的价格
        prices = self.get_multiple_token_prices([token0_symbol, token1_symbol])
        
        token0_price = prices.get(token0_symbol.upper())
        token1_price = prices.get(token1_symbol.upper())
        
        # 如果任何一个代币价格获取失败，返回None
        if token0_price is None or token1_price is None:
            missing_tokens = []
            if token0_price is None:
                missing_tokens.append(token0_symbol)
            if token1_price is None:
                missing_tokens.append(token1_symbol)
            self.logger.error(f"无法获取代币价格: {', '.join(missing_tokens)}")
            return None
        
        # 计算各代币的TVL
        token0_tvl = token0_amount * token0_price
        token1_tvl = token1_amount * token1_price
        total_tvl = token0_tvl + token1_tvl
        
        # 计算占比
        token0_percentage = (token0_tvl / total_tvl * 100) if total_tvl > 0 else 0
        token1_percentage = (token1_tvl / total_tvl * 100) if total_tvl > 0 else 0
        
        return token0_price, token1_price, total_tvl, token0_tvl, token1_tvl, token0_percentage, token1_percentage
    
    def monitor_pool(self, pool_config: Dict) -> Optional[PoolData]:
        """监控单个LP池"""
        pool_address = pool_config['contract_address']
        pool_type = pool_config.get('pool_type', 'v3')
        
        # 如果配置中没有池类型，自动检测
        if pool_type not in ['v2', 'v3']:
            pool_type = self.detect_pool_type(pool_address)
            self.logger.info(f"自动检测池 {pool_address} 类型: {pool_type}")
        
        reserves_data = self.get_pool_reserves(pool_address, pool_type)
        if not reserves_data:
            return None
        
        token0_symbol, token1_symbol, token0_amount, token1_amount, _, _ = reserves_data
        
        # 计算价格和TVL
        tvl_result = self.calculate_tvl(
            token0_symbol, token1_symbol, token0_amount, token1_amount
        )
        
        if tvl_result is None:
            self.logger.error(f"跳过池 {pool_address}，无法获取代币价格")
            return None
        
        token0_price, token1_price, total_tvl, token0_tvl, token1_tvl, token0_percentage, token1_percentage = tvl_result
        
        # 确定目标代币
        target_token = pool_config.get('target_token', token0_symbol)
        if target_token == token0_symbol:
            target_token_amount = token0_amount
            target_token_price = token0_price
        else:
            target_token_amount = token1_amount
            target_token_price = token1_price
        
        # 创建数据对象
        pool_data = PoolData(
            timestamp=datetime.now().isoformat(),
            pool_address=pool_address,
            pool_name=pool_config['name'],
            token0_symbol=token0_symbol,
            token1_symbol=token1_symbol,
            token0_amount=token0_amount,
            token1_amount=token1_amount,
            token0_price_usd=token0_price,
            token1_price_usd=token1_price,
            tvl_usd=total_tvl,
            target_token=target_token,
            target_token_amount=target_token_amount,
            target_token_price=target_token_price
        )
        
        # 添加TVL占比信息到pool_data（用于显示）
        pool_data.token0_tvl = token0_tvl
        pool_data.token1_tvl = token1_tvl
        pool_data.token0_percentage = token0_percentage
        pool_data.token1_percentage = token1_percentage
        
        return pool_data
    
    def get_alert_emoji(self, percent: float, threshold: float = 5.0) -> str:
        """根据变化百分比获取警告emoji"""
        abs_percent = abs(percent)
        if abs_percent >= threshold * 3:  # 超过阈值3倍
            return "🚨" if percent < 0 else "🎉"
        elif abs_percent >= threshold * 2:  # 超过阈值2倍
            return "⚠️" if percent < 0 else "📈"
        elif abs_percent >= threshold:  # 超过阈值
            return "🔻" if percent < 0 else "🔺"
        else:
            return "ℹ️"

    def send_alert_webhook(self, current_data: PoolData, prev_data: PoolData, 
                          tvl_change_percent: float, target_change_percent: float, threshold: float) -> None:
        """发送报警信息到 webhook"""
        try:
            # 简化的报警消息
            alert_emoji = self.get_alert_emoji(max(abs(tvl_change_percent), abs(target_change_percent)), threshold)
            
            # 基本信息
            message = f"{alert_emoji} {current_data.pool_name} LP池报警\n"
            message += f"时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\n\n"
            
            # TVL变化
            tvl_color = "🟢" if tvl_change_percent > 0 else "🔴"
            message += f"{tvl_color} TVL: {tvl_change_percent:+.2f}% (${prev_data.tvl_usd:,.0f} → ${current_data.tvl_usd:,.0f})\n"
            
            # 目标代币变化
            token_color = "🟢" if target_change_percent > 0 else "🔴"
            message += f"{token_color} {current_data.target_token}: {target_change_percent:+.2f}% ({prev_data.target_token_amount:,.0f} → {current_data.target_token_amount:,.0f})\n\n"
            
            # 两个代币的详细变化
            # Token0变化
            token0_amount_change = ((current_data.token0_amount - prev_data.token0_amount) / prev_data.token0_amount) * 100
            token0_tvl_change = ((current_data.token0_tvl - prev_data.token0_tvl) / prev_data.token0_tvl) * 100
            token0_emoji = "🟢" if token0_amount_change > 0 else "🔴"
            
            message += f"{token0_emoji} {current_data.token0_symbol}:\n"
            message += f"数量: {prev_data.token0_amount:,.0f} → {current_data.token0_amount:,.0f} ({token0_amount_change:+.1f}%)\n"
            message += f"TVL: ${prev_data.token0_tvl:,.0f} → ${current_data.token0_tvl:,.0f} ({token0_tvl_change:+.1f}%)\n\n"
            
            # Token1变化
            token1_amount_change = ((current_data.token1_amount - prev_data.token1_amount) / prev_data.token1_amount) * 100
            token1_tvl_change = ((current_data.token1_tvl - prev_data.token1_tvl) / prev_data.token1_tvl) * 100
            token1_emoji = "🟢" if token1_amount_change > 0 else "🔴"
            
            message += f"{token1_emoji} {current_data.token1_symbol}:\n"
            message += f"数量: {prev_data.token1_amount:,.0f} → {current_data.token1_amount:,.0f} ({token1_amount_change:+.1f}%)\n"
            message += f"TVL: ${prev_data.token1_tvl:,.0f} → ${current_data.token1_tvl:,.0f} ({token1_tvl_change:+.1f}%)"
            
            # 异步发送消息
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已经在异步上下文中，使用 create_task
                    asyncio.create_task(send_message_async(message))
                else:
                    # 如果不在异步上下文中，创建新的事件循环
                    asyncio.run(send_message_async(message))
            except RuntimeError:
                # 如果在线程中运行，使用 run_coroutine_threadsafe
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(send_message_async(message))
                    loop.close()
                except Exception as e:
                    self.logger.error(f"发送webhook消息失败: {e}")
                    
        except Exception as e:
            self.logger.error(f"构建或发送webhook报警消息失败: {e}")

    def check_for_changes(self, current_data: PoolData) -> None:
        """检查变化并报告 - 带颜色emoji警告"""
        pool_address = current_data.pool_address
        threshold = self.config['monitoring'].get('alert_threshold_percent', 5.0)
        
        if pool_address in self.previous_data:
            prev_data = self.previous_data[pool_address]
            
            # 检查TVL变化
            tvl_change_percent = ((current_data.tvl_usd - prev_data.tvl_usd) / prev_data.tvl_usd) * 100
            
            # 检查目标代币数量变化
            target_change_percent = ((current_data.target_token_amount - prev_data.target_token_amount) / 
                                   prev_data.target_token_amount) * 100
            
            if abs(tvl_change_percent) >= threshold or abs(target_change_percent) >= threshold:
                # 获取合适的警告emoji
                tvl_emoji = self.get_alert_emoji(tvl_change_percent, threshold)
                token_emoji = self.get_alert_emoji(target_change_percent, threshold)
                
                self.logger.warning(f"{tvl_emoji} {current_data.pool_name} 检测到重大变化:")
                
                # TVL变化颜色标识
                tvl_color = "🟢" if tvl_change_percent > 0 else "🔴"
                self.logger.warning(f"   {tvl_color} TVL变化: {tvl_change_percent:.2f}% (${prev_data.tvl_usd:.2f} -> ${current_data.tvl_usd:.2f})")
                
                # 代币数量变化颜色标识
                token_color = "🟢" if target_change_percent > 0 else "🔴"
                self.logger.warning(f"   {token_color} {current_data.target_token}数量变化: {target_change_percent:.2f}% ({prev_data.target_token_amount:.2f} -> {current_data.target_token_amount:.2f})")
                
                # 发送详细信息到 webhook
                self.send_alert_webhook(current_data, prev_data, tvl_change_percent, target_change_percent, threshold)
        
        self.previous_data[pool_address] = current_data
    
    def save_data(self, pool_data_list: List[PoolData]) -> None:
        """保存数据到文件"""
        if not pool_data_list:
            return
            
        data_dir = self.config['output'].get('data_directory', './data')
        timestamp = datetime.now().strftime('%Y%m%d')
        
        # 保存为JSON
        if self.config['output'].get('export_json', True):
            json_file = f"{data_dir}/lp_data_{timestamp}.json"
            data_to_save = [asdict(data) for data in pool_data_list]
            
            # 加载现有数据
            existing_data = []
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except:
                    existing_data = []
            
            existing_data.extend(data_to_save)
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
        # 保存为CSV
        if self.config['output'].get('export_csv', True):
            csv_file = f"{data_dir}/lp_data_{timestamp}.csv"
            file_exists = os.path.exists(csv_file)
            
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=asdict(pool_data_list[0]).keys())
                if not file_exists:
                    writer.writeheader()
                for data in pool_data_list:
                    writer.writerow(asdict(data))
    
    def format_change_percent(self, percent: float, threshold: float = 5.0) -> str:
        """格式化变化百分比并添加合适的emoji"""
        if abs(percent) >= threshold:
            if percent > 0:
                return f"🟢 +{percent:.2f}%"  # 绿色上涨
            else:
                return f"🔴 {percent:.2f}%"   # 红色下跌
        else:
            if percent > 0:
                return f"⚪ +{percent:.2f}%"  # 白色小幅上涨
            else:
                return f"⚪ {percent:.2f}%"   # 白色小幅下跌

    def print_status(self, pool_data_list: List[PoolData]) -> None:
        """打印当前状态 - 紧凑表格显示所有LP池"""
        print(f"\n📊 LP池监控 {datetime.now().strftime('%H:%M:%S')} 💾缓存:{self.get_cache_stats()['cached_tokens']}个")
        
        if not pool_data_list:
            print("❌ 没有数据显示")
            return
        
        # 紧凑表格头部
        print(f"{'池名称':<28} {'总TVL':<20} {'代币1':<40} {'代币2':<40}")
        print("-" * 128)
        
        for data in pool_data_list:
            # 格式化池名称
            pool_name = data.pool_name
          
            # 格式化总TVL
            if data.tvl_usd >= 1000000:
                tvl_str = f"💎${data.tvl_usd/1000000:.1f}M"
            elif data.tvl_usd >= 1000:
                tvl_str = f"💰${data.tvl_usd/1000:.0f}K"
            else:
                tvl_str = f"💰${data.tvl_usd:.0f}"
            

            # 格式化代币信息 - 更紧凑
            token0_info = f"🔸{data.token0_percentage:.1f}% {data.token0_symbol} {data.token0_amount:,.0f} ${data.token0_tvl/1000:.0f}K"
            token1_info = f"🔹{data.token1_percentage:.1f}% {data.token1_symbol} {data.token1_amount:,.0f} ${data.token1_tvl/1000:.0f}K"
            
            # 打印一行显示所有信息
            print(f"{pool_name:<28} {tvl_str:<20} {token0_info:<40} {token1_info:<40}")
        
        print("-" * 82)
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        dexscreener_sources = sum(1 for entry in self.price_cache.values() 
                                 if entry.get('source') == 'dexscreener' and self.is_cache_valid(entry))
        
        return {
            'cached_tokens': len([entry for entry in self.price_cache.values() if self.is_cache_valid(entry)]),
            'dexscreener_sources': dexscreener_sources
        }
    
    def clear_expired_cache(self) -> None:
        """清理过期的缓存条目"""
        with self.price_cache_lock:
            expired_keys = []
            for symbol, entry in self.price_cache.items():
                if not self.is_cache_valid(entry):
                    expired_keys.append(symbol)
            
            for key in expired_keys:
                del self.price_cache[key]
            
            if expired_keys:
                self.logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")
    
    def run(self) -> None:
        """主监控循环"""
        interval = self.config['monitoring'].get('interval_seconds', 30)
        enabled_pools = [pool for pool in self.config['pools'] if pool.get('enabled', True)]
        
        if not enabled_pools:
            print("❌ 没有启用的LP池，请先配置池!")
            print("使用命令: python pool_manager.py list")
            return
        
        print(f"🚀 开始监控 {len(enabled_pools)} 个LP池...")
        print(f"⏱️  监控间隔: {interval} 秒")
        print(f"📂 数据保存: {self.config['output']['data_directory']}")
        print(f"💾 价格缓存TTL: {self.cache_ttl_minutes} 分钟")
        print("\n按 Ctrl+C 停止监控")
        
        try:
            cycle_count = 0
            while True:
                pool_data_list = []
                
                # 每10个监控周期清理一次过期缓存
                if cycle_count % 10 == 0:
                    self.clear_expired_cache()
                
                # 预先批量获取所有需要的代币价格
                all_symbols = set()
                for pool_config in enabled_pools:
                    # 动态获取池中的代币符号
                    pool_address = pool_config['contract_address']
                    pool_type = pool_config.get('pool_type', 'v3')
                    reserves_data = self.get_pool_reserves(pool_address, pool_type)
                    if reserves_data:
                        token0_symbol, token1_symbol, _, _, _, _ = reserves_data
                        all_symbols.add(token0_symbol)
                        all_symbols.add(token1_symbol)
                
                if all_symbols:
                    self.logger.info(f"预加载 {len(all_symbols)} 个代币价格到缓存")
                    self.get_multiple_token_prices(list(all_symbols))
                
                for pool_config in enabled_pools:
                    data = self.monitor_pool(pool_config)
                    if data:
                        pool_data_list.append(data)
                        self.check_for_changes(data)
                
                if pool_data_list:
                    self.save_data(pool_data_list)
                    if self.config['output'].get('console_log', True):
                        self.print_status(pool_data_list)
                
                cycle_count += 1
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
        except Exception as e:
            self.logger.error(f"监控过程中发生错误: {e}")


def main():
    print("🔍 Pancake LP池监控器")
    print("-" * 40)
    
    monitor = LPMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
