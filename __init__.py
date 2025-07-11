"""集成核心逻辑"""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, \
    LOG_SETUP_ENTRY, LOG_PLATFORM_LOAD_FAILED, LOG_UNLOAD_ENTRY  # 导入日志翻译键
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

    setup_log_msg = i18n.get_text(LOG_SETUP_ENTRY, "加载配置项 {entry_id}（标题：{title}）")
    _LOGGER.info(setup_log_msg.format(entry_id=config_entry.entry_id, title=config_entry.title))

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN][config_entry.entry_id] = {
        "config": config_entry.data,
        "i18n": i18n
    }

    if CONF_UPDATE_INTERVAL not in config_entry.options:
        options = {**config_entry.options, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL}
        hass.config_entries.async_update_entry(config_entry, options=options)

    try:
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    except Exception as e:
        platform_load_error_msg = i18n.get_text(LOG_PLATFORM_LOAD_FAILED, "平台加载失败：{error}")
        _LOGGER.exception(platform_load_error_msg.format(error=str(e)))
        raise ConfigEntryNotReady from e

    config_entry.async_on_unload(
        config_entry.add_update_listener(async_update_options)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """卸载配置项"""
    i18n = hass.data[DOMAIN][config_entry.entry_id]["i18n"]
    unload_log_msg = i18n.get_text(LOG_UNLOAD_ENTRY, "卸载配置项 {entry_id}")
    _LOGGER.info(unload_log_msg.format(entry_id=config_entry.entry_id))

    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unload_ok and config_entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(config_entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """配置更新后重新加载集成"""
    await hass.config_entries.async_reload(config_entry.entry_id)
