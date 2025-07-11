"""Huarun Gas v2 配置流程"""
import time
import json
import random
import base64
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
import logging
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import (
    DOMAIN, CONF_CNO, CONF_NAME, CONF_UPDATE_INTERVAL,
    DEFAULT_NAME, DEFAULT_UPDATE_INTERVAL, MIN_UPDATE_INTERVAL, MAX_UPDATE_INTERVAL,
    ATTR_CNO, ATTR_NAME, ATTR_UPDATE_INTERVAL,
    ERROR_INVALID_CNO, ERROR_INVALID_INTERVAL, ERROR_CNO_NOT_FOUND,
    API_URL, API_AUTH_VERSION, PUBLIC_KEY_PEM
)
from .i18n import HuarunI18n

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class HuaRunGasV2FlowHandler(config_entries.ConfigFlow):
    """华润燃气配置流程处理器"""
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """用户配置步骤"""
        errors = {}
        i18n = HuarunI18n(self.hass, DOMAIN)
        await i18n.init_async()

        if user_input:
            # 验证账号格式（10位数字）
            cno = user_input.get(CONF_CNO)
            if not (cno and len(cno) == 10 and cno.isdigit()):
                errors[CONF_CNO] = ERROR_INVALID_CNO
            else:
                # 验证账号是否存在（API请求）
                valid, error_code = await self._validate_cno_with_api(cno)
                if not valid:
                    errors[CONF_CNO] = error_code

            # 验证更新间隔
            interval, interval_error = self._validate_update_interval(
                user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            )
            if interval_error:
                errors[CONF_UPDATE_INTERVAL] = interval_error
            else:
                user_input[CONF_UPDATE_INTERVAL] = interval

            if not errors:
                await self.async_set_unique_id(cno)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{user_input.get(CONF_NAME, DEFAULT_NAME)} ({cno})",
                    data={
                        CONF_CNO: cno,
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                        CONF_UPDATE_INTERVAL: interval,
                    },
                )

        # 加载翻译文本
        translations = await i18n._load_translations(self.hass.config.language)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_CNO,
                    description={"name": translations.get(f"data.{ATTR_CNO}", "User Account Number")}
                ): str,
                vol.Optional(
                    CONF_NAME,
                    default=DEFAULT_NAME,
                    description={"name": translations.get(f"data.{ATTR_NAME}", "Sensor Name")}
                ): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=str(DEFAULT_UPDATE_INTERVAL),
                    description={
                        "name": translations.get(f"data.{ATTR_UPDATE_INTERVAL}", "Update Interval (hours)"),
                        "description": f"({MIN_UPDATE_INTERVAL}-{MAX_UPDATE_INTERVAL} hours)"
                    }
                ): str,
            }),
            errors={k: translations.get(f"errors.{v}", v) for k, v in errors.items()},
        )

    async def _validate_cno_with_api(self, cno):
        """通过API验证账号是否存在"""
        try:
            # 加密参数
            public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode())
            timestamp = int(time.time() * 1000)
            random_num = random.randint(1000, 9999)
            data_to_encrypt = f"e5b871c278a84defa8817d22afc34338#{timestamp}#{random_num}"
            encrypted_data = public_key.encrypt(data_to_encrypt.encode(), padding.PKCS1v15())
            base64_encrypted = base64.urlsafe_b64encode(encrypted_data).decode()

            # 构建请求
            request_body = {"USER": "bizH5", "PWD": base64_encrypted}
            base64_body = base64.urlsafe_b64encode(json.dumps(request_body).encode()).decode()
            url = f"{API_URL}?authVersion={API_AUTH_VERSION}&consNo={cno}"
            headers = {"Content-Type": "application/json", "Param": base64_body}

            # 发送请求
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers=headers, timeout=30) as resp:
                resp_text = await resp.text()
                result = json.loads(resp_text)

                if result.get("msg") != "操作成功":
                    return False, ERROR_CNO_NOT_FOUND
                return True, None

        except Exception as e:
            _LOGGER.error(f"API验证失败: {str(e)}")
            return False, ERROR_INVALID_CNO

    def _validate_update_interval(self, interval_str):
        """验证更新间隔"""
        try:
            interval = int(interval_str)
            if MIN_UPDATE_INTERVAL <= interval <= MAX_UPDATE_INTERVAL:
                return interval, None
            return None, ERROR_INVALID_INTERVAL
        except (ValueError, TypeError):
            return None, ERROR_INVALID_INTERVAL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        # 修复：创建OptionsFlowHandler时不传递参数
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """选项流程处理器"""

    async def async_step_init(self, user_input=None):
        """选项配置步骤"""
        errors = {}
        # 直接使用基类提供的self.config_entry
        current_data = self.config_entry.data
        i18n = HuarunI18n(self.hass, DOMAIN)
        await i18n.init_async()
        translations = await i18n._load_translations(self.hass.config.language)

        if user_input:
            new_cno = user_input[CONF_CNO]
            # 验证账号变更
            if new_cno != current_data[CONF_CNO]:
                if not (new_cno and len(new_cno) == 10 and new_cno.isdigit()):
                    errors[CONF_CNO] = ERROR_INVALID_CNO
                else:
                    valid, error_code = await self._validate_cno_with_api(new_cno)
                    if not valid:
                        errors[CONF_CNO] = error_code

            # 验证更新间隔
            interval, interval_error = self._validate_update_interval(
                user_input.get(CONF_UPDATE_INTERVAL, current_data[CONF_UPDATE_INTERVAL])
            )
            if interval_error:
                errors[CONF_UPDATE_INTERVAL] = interval_error

            if not errors:
                # 更新配置
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_CNO: new_cno,
                        CONF_NAME: user_input.get(CONF_NAME, current_data[CONF_NAME]),
                        CONF_UPDATE_INTERVAL: interval,
                    }
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_CNO,
                    default=current_data[CONF_CNO],
                    description={"name": translations.get(f"data.{ATTR_CNO}", "User Account Number")}
                ): str,
                vol.Optional(
                    CONF_NAME,
                    default=current_data.get(CONF_NAME, DEFAULT_NAME),
                    description={"name": translations.get(f"data.{ATTR_NAME}", "Sensor Name")}
                ): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=str(current_data[CONF_UPDATE_INTERVAL]),
                    description={"name": translations.get(f"data.{ATTR_UPDATE_INTERVAL}", "Update Interval (hours)")}
                ): str,
            }),
            errors={k: translations.get(f"errors.{v}", v) for k, v in errors.items()},
        )

    # 复用验证方法
    async def _validate_cno_with_api(self, cno):
        return await HuaRunGasV2FlowHandler._validate_cno_with_api(self, cno)

    def _validate_update_interval(self, interval_str):
        return HuaRunGasV2FlowHandler._validate_update_interval(self, interval_str)