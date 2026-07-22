# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 共享会话模块
版本 1.0.0
"""

import os
import requests

# 保存并清理终端代理环境变量（避免代理干扰连接）
_SavedProxyEnv = {}
for _key in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY'):
    _val = os.environ.pop(_key, None)
    if _val is not None:
        _SavedProxyEnv[_key] = _val

# 全局 Session（禁用系统代理）
_session = requests.Session()
_session.headers.update({"User-Agent": "HONGXUN/1.0 (academic-research-tool)"})
_session.trust_env = False
