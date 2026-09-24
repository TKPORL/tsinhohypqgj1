"""配置管理模块"""
import os
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"
ENV_FILE = Path(__file__).parent / ".env"

_config = None

def _load_env_file():
    """读取.env文件（KEY=VALUE格式），不覆盖已存在的环境变量"""
    if not ENV_FILE.exists():
        return
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass

# 速度档位默认参数（config.yaml缺失时兜底）
SPEED_PROFILE_DEFAULTS = {
    "stable": {"detail_workers": 1, "delay_min": 0.5, "delay_max": 1.0, "image_workers": 2},
    "balanced": {"detail_workers": 2, "delay_min": 0.2, "delay_max": 0.5, "image_workers": 6},
    "fast": {"detail_workers": 4, "delay_min": 0.1, "delay_max": 0.3, "image_workers": 10},
}

def load_config():
    global _config
    if _config is None:
        _load_env_file()
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
        # 萌幻ACG凭据：config.yaml留空时从环境变量/.env注入
        acgrx = _config.get("acgrx") or {}
        if not acgrx.get("email"):
            acgrx["email"] = os.environ.get("ACGRX_EMAIL", "")
        if not acgrx.get("password"):
            acgrx["password"] = os.environ.get("ACGRX_PASSWORD", "")
    return _config

def get_speed_profile(name):
    """获取速度档位参数（白名单校验，含安全上限）"""
    config = load_config()
    speed_cfg = config.get("speed", {}) or {}
    profiles = speed_cfg.get("profiles", {}) or {}

    if name not in SPEED_PROFILE_DEFAULTS:
        name = speed_cfg.get("default", "balanced")
    if name not in SPEED_PROFILE_DEFAULTS:
        name = "balanced"

    # config.yaml自定义档位覆盖默认值
    profile = dict(SPEED_PROFILE_DEFAULTS[name])
    if name in profiles and isinstance(profiles[name], dict):
        profile.update(profiles[name])

    # 安全上限
    profile["detail_workers"] = max(1, min(int(profile.get("detail_workers", 2)), 4))
    profile["image_workers"] = max(1, min(int(profile.get("image_workers", 6)), 12))
    profile["delay_min"] = max(0.05, float(profile.get("delay_min", 0.2)))
    profile["delay_max"] = max(profile["delay_min"], float(profile.get("delay_max", 0.5)))
    return name, profile

def get_site_detail_workers(speed_name, site_key):
    """获取指定站点的详情并发数（优先site_detail_workers覆盖，其次档位默认）"""
    _, profile = get_speed_profile(speed_name)
    config = load_config()
    site_overrides = (config.get("speed", {}) or {}).get("site_detail_workers", {}) or {}
    workers = site_overrides.get(site_key, profile["detail_workers"])
    return max(1, min(int(workers), 4))

def get(key, default=None):
    config = load_config()
    keys = key.split(".")
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    return value if value is not None else default
