#!/usr/bin/env python3
"""
配置管理模块
从环境变量(.env文件)中读取配置信息
"""

import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# Webhook配置
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PROXY_URL = os.getenv('PROXY_URL', '')
USE_PROXY = os.getenv('USE_PROXY', 'false').lower() in ('true', '1', 'yes')

# 验证必需的配置
if not WEBHOOK_URL:
    print("警告: 未设置 WEBHOOK_URL 环境变量，webhook功能将无法使用")

def get_webhook_config():
    """获取webhook配置信息"""
    return {
        'webhook_url': WEBHOOK_URL,
        'proxy_url': PROXY_URL,
        'use_proxy': USE_PROXY
    }

def validate_config():
    """验证配置是否完整"""
    if not WEBHOOK_URL:
        return False, "WEBHOOK_URL 未设置"
    return True, "配置验证通过"
