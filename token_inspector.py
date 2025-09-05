#!/usr/bin/env python3
"""
代币和池检查工具
用于检查LP池中的代币地址、检验池类型等
"""

import json
from web3 import Web3
from typing import Dict, Optional, Tuple


class TokenInspector:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.w3 = self.setup_web3()
    
    def load_config(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ 配置文件 {self.config_file} 不存在!")
            return {}
        except json.JSONDecodeError as e:
            print(f"❌ 配置文件格式错误: {e}")
            return {}
    
    def setup_web3(self) -> Web3:
        """设置Web3连接"""
        try:
            w3 = Web3(Web3.HTTPProvider(self.config['network']['rpc_url']))
            if not w3.is_connected():
                print(f"❌ 无法连接到网络: {self.config['network']['name']}")
                return None
            print(f"✅ 成功连接到 {self.config['network']['name']}")
            return w3
        except Exception as e:
            print(f"❌ Web3连接失败: {e}")
            return None
    
    def get_erc20_abi(self):
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
                "name": "name",
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
            }
        ]
    
    def get_v3_pool_abi(self):
        """获取V3池的基本ABI"""
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
            }
        ]
    
    def inspect_pool(self, pool_address: str) -> Optional[Dict]:
        """检查LP池的详细信息"""
        if not self.w3:
            return None
            
        try:
            print(f"\n🔍 检查池: {pool_address}")
            
            # 尝试V3池
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self.get_v3_pool_abi()
            )
            
            # 获取代币地址
            token0_address = pool_contract.functions.token0().call()
            token1_address = pool_contract.functions.token1().call()
            fee = pool_contract.functions.fee().call()
            
            print(f"   池类型: V3")
            print(f"   手续费: {fee / 10000}%")
            print(f"   Token0地址: {token0_address}")
            print(f"   Token1地址: {token1_address}")
            
            # 获取代币信息
            token0_info = self.get_token_info(token0_address)
            token1_info = self.get_token_info(token1_address)
            
            if token0_info:
                print(f"   Token0: {token0_info['symbol']} ({token0_info['name']}) - {token0_info['decimals']} decimals")
            
            if token1_info:
                print(f"   Token1: {token1_info['symbol']} ({token1_info['name']}) - {token1_info['decimals']} decimals")
            
            return {
                'pool_type': 'v3',
                'pool_address': pool_address,
                'fee': fee,
                'fee_percent': fee / 10000,
                'token0': {
                    'address': token0_address,
                    **token0_info
                },
                'token1': {
                    'address': token1_address,
                    **token1_info
                }
            }
            
        except Exception as e:
            print(f"   ❌ 检查失败: {e}")
            return None
    
    def get_token_info(self, token_address: str) -> Optional[Dict]:
        """获取代币信息"""
        try:
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.get_erc20_abi()
            )
            
            symbol = token_contract.functions.symbol().call()
            name = token_contract.functions.name().call()
            decimals = token_contract.functions.decimals().call()
            
            return {
                'symbol': symbol,
                'name': name,
                'decimals': decimals
            }
        except Exception as e:
            print(f"   获取代币信息失败: {e}")
            return {'symbol': 'UNKNOWN', 'name': 'Unknown Token', 'decimals': 18}
    
    def update_config_with_token_addresses(self, pool_info: Dict) -> None:
        """更新配置文件中的代币地址"""
        if not pool_info:
            return
            
        # 找到对应的池配置
        for pool in self.config.get('pools', []):
            if pool['contract_address'].lower() == pool_info['pool_address'].lower():
                
                # 更新token0信息
                token0_symbol = pool_info['token0']['symbol']
                if pool['token0']['symbol'] == token0_symbol and not pool['token0']['contract_address']:
                    pool['token0']['contract_address'] = pool_info['token0']['address']
                    pool['token0']['decimals'] = pool_info['token0']['decimals']
                    print(f"   ✅ 更新 {token0_symbol} 地址: {pool_info['token0']['address']}")
                
                # 更新token1信息
                token1_symbol = pool_info['token1']['symbol']
                if pool['token1']['symbol'] == token1_symbol and not pool['token1']['contract_address']:
                    pool['token1']['contract_address'] = pool_info['token1']['address']
                    pool['token1']['decimals'] = pool_info['token1']['decimals']
                    print(f"   ✅ 更新 {token1_symbol} 地址: {pool_info['token1']['address']}")
                
                # 更新tokens部分
                if token0_symbol in self.config.get('tokens', {}) and not self.config['tokens'][token0_symbol]['contract_address']:
                    self.config['tokens'][token0_symbol]['contract_address'] = pool_info['token0']['address']
                    self.config['tokens'][token0_symbol]['decimals'] = pool_info['token0']['decimals']
                    self.config['tokens'][token0_symbol]['name'] = pool_info['token0']['name']
                
                if token1_symbol in self.config.get('tokens', {}) and not self.config['tokens'][token1_symbol]['contract_address']:
                    self.config['tokens'][token1_symbol]['contract_address'] = pool_info['token1']['address']
                    self.config['tokens'][token1_symbol]['decimals'] = pool_info['token1']['decimals']
                    self.config['tokens'][token1_symbol]['name'] = pool_info['token1']['name']
        
        # 保存配置
        self.save_config()
    
    def save_config(self) -> None:
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"   💾 配置已保存到 {self.config_file}")


def main():
    inspector = TokenInspector()
    
    print("🔍 代币和池检查工具")
    print("-" * 40)
    
    # 检查配置中的所有池
    pools = inspector.config.get('pools', [])
    if not pools:
        print("❌ 配置中没有找到池")
        return
    
    for pool in pools:
        pool_address = pool['contract_address']
        pool_info = inspector.inspect_pool(pool_address)
        
        if pool_info:
            inspector.update_config_with_token_addresses(pool_info)
        
        print("-" * 40)


if __name__ == "__main__":
    main()
