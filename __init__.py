"""集成核心逻辑"""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .i18n import HuarunI18n

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """初始化集成（YAML配置支持）"""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """通过配置项初始化集成"""
    i18n = HuarunI18n(hass, DOMAIN)
    await i18n.init_async()
    
    # 获取翻译文本
    setup_log_msg = i18n.get_text("log.setup_entry", "加载配置项 {entry_id}（标题：{title}）")
    _LOGGER.info(setup_log_msg.format(entry_id=config_entry.entry_id, title=config_entry.title))

    # 确保数据结构存在
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    # 存储i18n实例和配置数据
    hass.data[DOMAIN][config_entry.entry_id] = {
        "config": config_entry.data,
        "i18n": i18n
    }

    # 兼容旧配置（确保更新间隔存在）
    if CONF_UPDATE_INTERVAL not in config_entry.options:
        options = {**config_entry.options, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL}
        hass.config_entries.async_update_entry(config_entry, options=options)

    # 加载传感器平台
    try:
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    except Exception as e:
        platform_load_error_msg = i18n.get_text("log.platform_load_failed", "平台加载失败：{error}")
        _LOGGER.exception(platform_load_error_msg.format(error=str(e)))
        raise ConfigEntryNotReady from e

    # 注册配置更新监听器
    config_entry.async_on_unload(
        config_entry.add_update_listener(async_update_options)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """卸载配置项"""
    i18n = hass.data[DOMAIN][config_entry.entry_id]["i18n"]
    unload_log_msg = i18n.get_text("log.unload_entry", "卸载配置项 {entry_id}")
    _LOGGER.info(unload_log_msg.format(entry_id=config_entry.entry_id))

    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    # 清理数据
    if unload_ok and config_entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(config_entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """配置更新后重新加载集成"""
    await hass.config_entries.async_reload(config_entry.entry_id)