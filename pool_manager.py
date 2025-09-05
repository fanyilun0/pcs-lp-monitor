#!/usr/bin/env python3
"""
池管理工具 - 用于添加、删除和搜索LP池配置
"""

import json
import argparse
import sys
from typing import Dict, List, Optional
from web3 import Web3


class PoolManager:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        
    def load_config(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"配置文件 {self.config_file} 不存在!")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"配置文件格式错误: {e}")
            sys.exit(1)
    
    def save_config(self) -> None:
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"配置已保存到 {self.config_file}")
    
    def add_pool(self, pool_address: str, name: str = None, token0_symbol: str = None, 
                 token1_symbol: str = None, fee_tier: str = None, enabled: bool = True) -> None:
        """添加新的LP池到配置"""
        
        # 检查池是否已存在
        for pool in self.config['pools']:
            if pool['contract_address'].lower() == pool_address.lower():
                print(f"池地址 {pool_address} 已存在!")
                return
        
        # 生成池ID
        pool_id = f"pool_{len(self.config['pools'])}"
        
        # 创建新池配置
        new_pool = {
            "id": pool_id,
            "name": name or f"Pool {pool_address[:8]}...",
            "contract_address": pool_address,
            "token0": {
                "symbol": token0_symbol or "TOKEN0",
                "contract_address": "",
                "decimals": 18
            },
            "token1": {
                "symbol": token1_symbol or "TOKEN1", 
                "contract_address": "",
                "decimals": 18
            },
            "fee_tier": fee_tier or "0.3%",
            "pool_type": "v3",
            "enabled": enabled,
            "target_token": token0_symbol or "TOKEN0"
        }
        
        self.config['pools'].append(new_pool)
        self.save_config()
        print(f"✅ 成功添加池: {new_pool['name']} ({pool_address})")
    
    def remove_pool(self, pool_address: str) -> None:
        """从配置中移除LP池"""
        original_count = len(self.config['pools'])
        self.config['pools'] = [
            pool for pool in self.config['pools'] 
            if pool['contract_address'].lower() != pool_address.lower()
        ]
        
        if len(self.config['pools']) < original_count:
            self.save_config()
            print(f"✅ 成功移除池: {pool_address}")
        else:
            print(f"❌ 未找到池地址: {pool_address}")
    
    def list_pools(self) -> None:
        """列出所有配置的池"""
        if not self.config['pools']:
            print("❌ 没有配置任何池")
            return
            
        print("\n📋 当前配置的池:")
        print("-" * 80)
        for i, pool in enumerate(self.config['pools'], 1):
            status = "✅ 启用" if pool['enabled'] else "❌ 禁用"
            print(f"{i}. {pool['name']}")
            print(f"   地址: {pool['contract_address']}")
            print(f"   代币对: {pool['token0']['symbol']}/{pool['token1']['symbol']}")
            print(f"   手续费: {pool['fee_tier']}")
            print(f"   状态: {status}")
            print(f"   目标代币: {pool['target_token']}")
            print()
    
    def enable_pool(self, pool_address: str) -> None:
        """启用指定池"""
        self._toggle_pool(pool_address, True)
    
    def disable_pool(self, pool_address: str) -> None:
        """禁用指定池"""
        self._toggle_pool(pool_address, False)
    
    def _toggle_pool(self, pool_address: str, enabled: bool) -> None:
        """切换池的启用状态"""
        for pool in self.config['pools']:
            if pool['contract_address'].lower() == pool_address.lower():
                pool['enabled'] = enabled
                self.save_config()
                status = "启用" if enabled else "禁用"
                print(f"✅ 成功{status}池: {pool['name']}")
                return
        print(f"❌ 未找到池地址: {pool_address}")
    
    def search_pools_by_token(self, token_symbol: str) -> None:
        """根据代币符号搜索池"""
        matching_pools = []
        token_symbol = token_symbol.upper()
        
        for pool in self.config['pools']:
            if (token_symbol in pool['token0']['symbol'].upper() or 
                token_symbol in pool['token1']['symbol'].upper()):
                matching_pools.append(pool)
        
        if not matching_pools:
            print(f"❌ 未找到包含 {token_symbol} 的池")
            return
            
        print(f"\n🔍 包含 {token_symbol} 的池:")
        print("-" * 60)
        for pool in matching_pools:
            status = "✅ 启用" if pool['enabled'] else "❌ 禁用"
            print(f"• {pool['name']}")
            print(f"  地址: {pool['contract_address']}")
            print(f"  代币对: {pool['token0']['symbol']}/{pool['token1']['symbol']}")
            print(f"  状态: {status}")
            print()


def main():
    parser = argparse.ArgumentParser(description='LP池配置管理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 添加池命令
    add_parser = subparsers.add_parser('add', help='添加新的LP池')
    add_parser.add_argument('address', help='LP池合约地址')
    add_parser.add_argument('--name', help='池名称')
    add_parser.add_argument('--token0', help='代币0符号')
    add_parser.add_argument('--token1', help='代币1符号')
    add_parser.add_argument('--fee', help='手续费等级')
    add_parser.add_argument('--disabled', action='store_true', help='添加时禁用池')
    
    # 移除池命令
    remove_parser = subparsers.add_parser('remove', help='移除LP池')
    remove_parser.add_argument('address', help='LP池合约地址')
    
    # 列出池命令
    subparsers.add_parser('list', help='列出所有配置的池')
    
    # 启用池命令
    enable_parser = subparsers.add_parser('enable', help='启用指定池')
    enable_parser.add_argument('address', help='LP池合约地址')
    
    # 禁用池命令
    disable_parser = subparsers.add_parser('disable', help='禁用指定池')
    disable_parser.add_argument('address', help='LP池合约地址')
    
    # 搜索池命令
    search_parser = subparsers.add_parser('search', help='根据代币符号搜索池')
    search_parser.add_argument('token', help='代币符号')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = PoolManager()
    
    if args.command == 'add':
        manager.add_pool(
            pool_address=args.address,
            name=args.name,
            token0_symbol=args.token0,
            token1_symbol=args.token1,
            fee_tier=args.fee,
            enabled=not args.disabled
        )
    elif args.command == 'remove':
        manager.remove_pool(args.address)
    elif args.command == 'list':
        manager.list_pools()
    elif args.command == 'enable':
        manager.enable_pool(args.address)
    elif args.command == 'disable':
        manager.disable_pool(args.address)
    elif args.command == 'search':
        manager.search_pools_by_token(args.token)


if __name__ == "__main__":
    main()
