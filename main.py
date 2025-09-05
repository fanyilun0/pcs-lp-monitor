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
        """获取代币符号到CoinGecko ID的映射"""
        return {
            'WBNB': 'wbnb',
            'BNB': 'binancecoin', 
            'USDT': 'tether',
            'USDC': 'usd-coin',
            'ETH': 'ethereum',
            'BTCB': 'bitcoin',
            'CAKE': 'pancakeswap-token',
            'MCH': 'monsterra-mch'  # MCH的CoinGecko ID
        }
    
    def get_mock_prices(self) -> Dict[str, float]:
        """获取模拟价格"""
        return {
            'WBNB': 320.0,
            'USDT': 1.0,
            'MCH': 0.04,  # 示例价格
            'BNB': 320.0,
            'USDC': 1.0,
            'ETH': 2000.0,
            'BTCB': 35000.0,
            'CAKE': 2.5
        }
    
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
    
    def get_token_price(self, symbol: str) -> float:
        """获取代币价格 - 带缓存机制"""
        symbol_upper = symbol.upper()
        
        # 首先检查缓存
        cached_price = self.get_cached_price(symbol_upper)
        if cached_price is not None:
            return cached_price
        
        # 添加到批量请求队列
        self.batch_request_symbols.add(symbol_upper)
        
        # 如果只有一个代币或达到批量阈值，立即请求
        if len(self.batch_request_symbols) >= 5 or symbol_upper in ['WBNB', 'USDT', 'USDC']:  # 立即请求主要代币
            prices = self.fetch_prices_from_coingecko(list(self.batch_request_symbols))
            
            # 更新缓存
            for sym, price in prices.items():
                self.set_cached_price(sym, price, 'coingecko')
            
            # 清空批量请求队列
            self.batch_request_symbols.clear()
            
            # 如果成功获取到当前代币价格
            if symbol_upper in prices:
                return prices[symbol_upper]
        
        # 回退到模拟价格
        mock_prices = self.get_mock_prices()
        fallback_price = mock_prices.get(symbol_upper, 1.0)
        
        # 缓存模拟价格（较短的TTL）
        self.set_cached_price(symbol_upper, fallback_price, 'mock')
        
        self.logger.info(f"使用模拟价格 {symbol}: ${fallback_price}")
        return fallback_price
    
    def get_multiple_token_prices(self, symbols: List[str]) -> Dict[str, float]:
        """批量获取多个代币价格"""
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
            api_prices = self.fetch_prices_from_coingecko(uncached_symbols)
            mock_prices = self.get_mock_prices()
            
            for symbol in uncached_symbols:
                symbol_upper = symbol.upper()
                if symbol_upper in api_prices:
                    price = api_prices[symbol_upper]
                    self.set_cached_price(symbol_upper, price, 'coingecko')
                    prices[symbol_upper] = price
                else:
                    # 使用模拟价格
                    fallback_price = mock_prices.get(symbol_upper, 1.0)
                    self.set_cached_price(symbol_upper, fallback_price, 'mock')
                    prices[symbol_upper] = fallback_price
                    self.logger.info(f"使用模拟价格 {symbol}: ${fallback_price}")
        
        return prices
    
    def calculate_tvl(self, token0_symbol: str, token1_symbol: str, 
                     token0_amount: float, token1_amount: float) -> Tuple[float, float, float]:
        """计算TVL - 使用批量价格获取"""
        # 批量获取两个代币的价格
        prices = self.get_multiple_token_prices([token0_symbol, token1_symbol])
        
        token0_price = prices.get(token0_symbol.upper(), self.get_token_price(token0_symbol))
        token1_price = prices.get(token1_symbol.upper(), self.get_token_price(token1_symbol))
        
        token0_value = token0_amount * token0_price
        token1_value = token1_amount * token1_price
        tvl = token0_value + token1_value
        
        return token0_price, token1_price, tvl
    
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
        token0_price, token1_price, tvl = self.calculate_tvl(
            token0_symbol, token1_symbol, token0_amount, token1_amount
        )
        
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
            tvl_usd=tvl,
            target_token=target_token,
            target_token_amount=target_token_amount,
            target_token_price=target_token_price
        )
        
        return pool_data
    
    def check_for_changes(self, current_data: PoolData) -> None:
        """检查变化并报告"""
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
                self.logger.warning(f"🚨 {current_data.pool_name} 检测到重大变化:")
                self.logger.warning(f"   TVL变化: {tvl_change_percent:.2f}% (${prev_data.tvl_usd:.2f} -> ${current_data.tvl_usd:.2f})")
                self.logger.warning(f"   {current_data.target_token}数量变化: {target_change_percent:.2f}% ({prev_data.target_token_amount:.2f} -> {current_data.target_token_amount:.2f})")
        
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
    
    def print_status(self, pool_data_list: List[PoolData]) -> None:
        """打印当前状态"""
        print("\n" + "="*80)
        print(f"📊 LP池监控状态 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # 打印缓存统计
        with self.price_cache_lock:
            cache_stats = self.get_cache_stats()
            print(f"💾 价格缓存: {cache_stats['cached_tokens']} 个代币, {cache_stats['api_sources']} API源, {cache_stats['mock_sources']} 模拟源")
        
        for data in pool_data_list:
            print(f"\n🏊 {data.pool_name}")
            print(f"   地址: {data.pool_address}")
            print(f"   代币对: {data.token0_symbol}/{data.token1_symbol}")
            print(f"   {data.token0_symbol}: {data.token0_amount:,.2f} (${data.token0_price_usd:.4f})")
            print(f"   {data.token1_symbol}: {data.token1_amount:,.2f} (${data.token1_price_usd:.4f})")
            print(f"   💰 TVL: ${data.tvl_usd:,.2f}")
            print(f"   🎯 目标代币 {data.target_token}: {data.target_token_amount:,.2f}")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        api_sources = sum(1 for entry in self.price_cache.values() 
                         if entry.get('source') == 'coingecko' and self.is_cache_valid(entry))
        mock_sources = sum(1 for entry in self.price_cache.values() 
                          if entry.get('source') == 'mock' and self.is_cache_valid(entry))
        
        return {
            'cached_tokens': len([entry for entry in self.price_cache.values() if self.is_cache_valid(entry)]),
            'api_sources': api_sources,
            'mock_sources': mock_sources
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
                    # 从配置中获取代币符号，避免重复的合约调用
                    if 'token0' in pool_config and 'token1' in pool_config:
                        all_symbols.add(pool_config['token0']['symbol'])
                        all_symbols.add(pool_config['token1']['symbol'])
                
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
