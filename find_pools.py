#!/usr/bin/env python3
"""
查找LP池工具 - 通过PancakeSwap V3 Factory查找MCH/WBNB池
"""

from web3 import Web3
import requests
import json

def find_v3_pools():
    """通过PancakeSwap V3 Factory查找MCH/WBNB池"""
    w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed1.binance.org/'))
    
    if not w3.is_connected():
        print("❌ 无法连接到BSC网络")
        return
    
    # PancakeSwap V3 Factory地址
    factory_address = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
    
    # 代币地址
    mch_address = "0xF8F331DFa811132c43C308757CD802ca982b7211"
    wbnb_address = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    
    # V3 Factory ABI (只需要getPool方法)
    factory_abi = [
        {
            "inputs": [
                {"internalType": "address", "name": "tokenA", "type": "address"},
                {"internalType": "address", "name": "tokenB", "type": "address"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"}
            ],
            "name": "getPool",
            "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    factory_contract = w3.eth.contract(address=factory_address, abi=factory_abi)
    
    # 常见的手续费等级 (以basis points为单位)
    fee_tiers = [
        (100, "0.01%"),
        (500, "0.05%"),
        (3000, "0.3%"),
        (10000, "1%")
    ]
    
    print(f"🔍 查找 MCH/WBNB LP池...")
    print(f"MCH地址: {mch_address}")
    print(f"WBNB地址: {wbnb_address}")
    print(f"Factory地址: {factory_address}")
    print("-" * 60)
    
    found_pools = []
    
    for fee, fee_str in fee_tiers:
        try:
            # 尝试两种代币顺序
            for token0, token1, order in [(mch_address, wbnb_address, "MCH/WBNB"), 
                                        (wbnb_address, mch_address, "WBNB/MCH")]:
                
                pool_address = factory_contract.functions.getPool(token0, token1, fee).call()
                
                if pool_address != "0x0000000000000000000000000000000000000000":
                    print(f"✅ 找到池 ({order} - {fee_str}): {pool_address}")
                    found_pools.append({
                        'address': pool_address,
                        'token0': token0,
                        'token1': token1,
                        'fee': fee,
                        'fee_str': fee_str,
                        'order': order
                    })
                    
                    # 检查这个池的详细信息
                    check_pool_details(w3, pool_address, order, fee_str)
                    
        except Exception as e:
            print(f"❌ 检查费率 {fee_str} 失败: {e}")
    
    if not found_pools:
        print("❌ 没有找到任何MCH/WBNB V3池")
        print("\n尝试查找V2池...")
        find_v2_pools(w3, mch_address, wbnb_address)
    else:
        print(f"\n✅ 总共找到 {len(found_pools)} 个池")
        return found_pools

def check_pool_details(w3, pool_address, order, fee_str):
    """检查池的详细信息"""
    try:
        # V3池基本ABI
        v3_abi = [
            {"inputs": [], "name": "liquidity", "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"}
        ]
        
        pool_contract = w3.eth.contract(address=pool_address, abi=v3_abi)
        liquidity = pool_contract.functions.liquidity().call()
        token0 = pool_contract.functions.token0().call()
        token1 = pool_contract.functions.token1().call()
        
        print(f"   流动性: {liquidity}")
        print(f"   Token0: {token0}")
        print(f"   Token1: {token1}")
        
        # 检查代币余额
        erc20_abi = [
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"}
        ]
        
        token0_contract = w3.eth.contract(address=token0, abi=erc20_abi)
        token1_contract = w3.eth.contract(address=token1, abi=erc20_abi)
        
        token0_symbol = token0_contract.functions.symbol().call()
        token1_symbol = token1_contract.functions.symbol().call()
        token0_decimals = token0_contract.functions.decimals().call()
        token1_decimals = token1_contract.functions.decimals().call()
        
        token0_balance = token0_contract.functions.balanceOf(pool_address).call()
        token1_balance = token1_contract.functions.balanceOf(pool_address).call()
        
        token0_amount = token0_balance / (10 ** token0_decimals)
        token1_amount = token1_balance / (10 ** token1_decimals)
        
        print(f"   {token0_symbol}: {token0_amount:,.6f}")
        print(f"   {token1_symbol}: {token1_amount:,.6f}")
        
        if token0_amount > 0 and token1_amount > 0:
            print("   ✅ 池中有流动性")
        else:
            print("   ⚠️  池中没有流动性")
            
    except Exception as e:
        print(f"   ❌ 获取池详情失败: {e}")
    
    print()

def find_v2_pools(w3, mch_address, wbnb_address):
    """查找V2池"""
    try:
        # PancakeSwap V2 Factory地址
        v2_factory_address = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
        
        v2_factory_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "", "type": "address"},
                    {"internalType": "address", "name": "", "type": "address"}
                ],
                "name": "getPair",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        factory_contract = w3.eth.contract(address=v2_factory_address, abi=v2_factory_abi)
        pair_address = factory_contract.functions.getPair(mch_address, wbnb_address).call()
        
        if pair_address != "0x0000000000000000000000000000000000000000":
            print(f"✅ 找到V2池: {pair_address}")
            
            # 检查V2池详情
            v2_abi = [
                {"inputs": [], "name": "getReserves", "outputs": [{"internalType": "uint112", "name": "_reserve0", "type": "uint112"}, {"internalType": "uint112", "name": "_reserve1", "type": "uint112"}, {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"}
            ]
            
            pair_contract = w3.eth.contract(address=pair_address, abi=v2_abi)
            reserves = pair_contract.functions.getReserves().call()
            
            print(f"   Reserve0: {reserves[0]}")
            print(f"   Reserve1: {reserves[1]}")
            
        else:
            print("❌ 没有找到V2池")
            
    except Exception as e:
        print(f"❌ 查找V2池失败: {e}")

def search_via_api():
    """通过第三方API搜索池"""
    print("\n🔍 尝试通过API搜索池...")
    
    # 这里可以集成DexScreener或其他API
    mch_address = "0xF8F331DFa811132c43C308757CD802ca982b7211"
    
    try:
        # DexScreener API
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mch_address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])
            
            print(f"找到 {len(pairs)} 个交易对:")
            
            for pair in pairs[:5]:  # 只显示前5个
                if 'BNB' in pair.get('baseToken', {}).get('symbol', '') or 'BNB' in pair.get('quoteToken', {}).get('symbol', ''):
                    print(f"   {pair.get('dexId', 'Unknown')}: {pair.get('pairAddress', 'N/A')}")
                    print(f"   交易对: {pair.get('baseToken', {}).get('symbol', 'Unknown')}/{pair.get('quoteToken', {}).get('symbol', 'Unknown')}")
                    print(f"   TVL: ${pair.get('liquidity', {}).get('usd', 0):,.2f}")
                    print()
        else:
            print(f"API请求失败: {response.status_code}")
            
    except Exception as e:
        print(f"API搜索失败: {e}")

if __name__ == "__main__":
    print("🔍 LP池查找工具")
    print("="*60)
    
    pools = find_v3_pools()
    search_via_api()
