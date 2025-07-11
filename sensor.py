"""传感器核心逻辑"""
from datetime import datetime, timedelta
import logging
import base64
import time
import random
import json
import asyncio
from collections import deque
import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_CNO,
    CONF_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    API_URL,
    API_AUTH_VERSION,
    PUBLIC_KEY_PEM,
    RETRYABLE_STATUS_CODES,
    MAX_HOURLY_REQUESTS,
    HOURLY_WINDOW,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback
) -> None:
    """通过配置项初始化传感器"""
    data = config_entry.data
    options = config_entry.options

    # 关键修复：将配置中的刷新间隔（字符串）转换为整数
    update_interval = int(options.get(CONF_UPDATE_INTERVAL, data.get(CONF_UPDATE_INTERVAL, 24)))

    async_add_entities([
        HuaRunGasV2Sensor(
            hass,
            data[CONF_NAME],
            data[CONF_CNO],
            config_entry.entry_id,
            update_interval  # 传递整数类型
        )
    ], True)


class HuaRunGasV2Sensor(SensorEntity):
    """华润燃气传感器实体"""

    def __init__(self, hass, name, cno, entry_id, update_interval_hours):
        self.hass = hass
        self._name = name
        self._cno = cno
        self._entry_id = entry_id
        self._state = None  # 当前余额
        self._last_data = None  # 缓存成功数据
        self._last_successful_update = None  # 上次成功更新时间
        self._data_source = "无数据"  # 数据来源
        self._request_lock = asyncio.Lock()  # 请求锁（并发控制）

        # 正常刷新间隔（小时→秒）
        self._update_interval_hours = update_interval_hours
        self._update_interval_seconds = self._update_interval_hours * 3600
        _LOGGER.info("设置刷新间隔：%d小时（%d秒）",
                     self._update_interval_hours, self._update_interval_seconds)

        # 重试配置
        self._max_retries = 5  # 最大重试次数
        self._retry_interval_seconds = 3 * 60  # 重试间隔3分钟
        self._current_retry = 0  # 当前重试次数

        # API请求频率控制
        self._request_history = deque(maxlen=MAX_HOURLY_REQUESTS)  # 记录请求时间
        self._hourly_window = HOURLY_WINDOW

        # 缓存数据时间戳
        self._last_data_timestamp = None  # 缓存数据时间戳

        # 传感器属性
        self._attr_unique_id = f"huarun_gas_{cno}_{entry_id}"
        self._attr_min_time_between_updates = timedelta(seconds=self._update_interval_seconds)

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        """传感器附加属性"""
        now = time.time()
        hourly_requests = len([t for t in self._request_history if now - t < self._hourly_window])
        
        # 计算数据时效性
        data_age = "从未更新"
        if self._last_data_timestamp:
            age_seconds = (datetime.now() - self._last_data_timestamp).total_seconds()
            if age_seconds < 60:
                data_age = f"{int(age_seconds)}秒前"
            elif age_seconds < 3600:
                data_age = f"{int(age_seconds/60)}分钟前"
            else:
                data_age = f"{int(age_seconds/3600)}小时前"
        
        return {
            "用户编号": self._cno,
            "刷新间隔（小时）": self._update_interval_hours,
            "上次成功更新": self._last_successful_update or "从未成功",
            "数据时效性": data_age,
            "当前重试次数": self._current_retry,
            "最大重试次数": self._max_retries,
            "1小时内请求次数": hourly_requests,
            "1小时内请求限制": MAX_HOURLY_REQUESTS,
            "数据来源": self._data_source,
            "数据过期": self._is_data_stale(),
            "数据为空": self._last_data is not None and not self._last_data,
            "重试失败": self._current_retry >= self._max_retries,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._cno)},
            name="华润燃气表",
            manufacturer="华润燃气",
            entry_type=DeviceEntryType.SERVICE
        )

    @property
    def native_unit_of_measurement(self) -> str:
        return "元"

    @property
    def device_class(self) -> str:
        return "monetary"

    @property
    def available(self) -> bool:
        return self._last_data is not None

    def _is_data_stale(self):
        """判断数据是否过期（超过2倍更新间隔）"""
        if not self._last_data_timestamp:
            return True
        
        stale_threshold = timedelta(hours=self._update_interval_hours * 2)
        return (datetime.now() - self._last_data_timestamp) > stale_threshold

    async def async_update(self) -> None:
        """刷新传感器数据（主逻辑）"""
        is_retry = self._current_retry > 0
        if is_retry:
            _LOGGER.debug("执行第%d次重试（间隔3分钟）", self._current_retry)
        else:
            _LOGGER.debug("执行正常刷新（间隔：%d小时）", self._update_interval_hours)

        # 检查数据是否过期
        if self._is_data_stale() and self._last_data_timestamp:
            _LOGGER.warning("数据已过期（超过%d小时），尝试强制刷新", self._update_interval_hours * 2)

        try:
            # 检查API频率限制，如需等待则先等待
            wait_time = await self._get_required_wait_time()  # 修复：添加await调用异步方法
            if wait_time > 0:
                _LOGGER.info("请求频率超限，等待%.1f秒后执行", wait_time)
                await asyncio.sleep(wait_time)

            # 发送API请求
            session = async_get_clientsession(self.hass)
            data = await self._fetch_api_data(session)

            # 刷新成功：更新状态+重置重试
            self._state = data.get("totalGasBalance")
            self._last_data = data
            self._last_successful_update = time.strftime("%Y-%m-%d %H:%M:%S")
            self._last_data_timestamp = datetime.now()
            self._data_source = "实时数据"
            self._current_retry = 0  # 重置重试计数
            _LOGGER.info("刷新成功，当前余额：%s元", self._state)

        except Exception as e:
            # 失败处理：触发重试（未达最大次数）
            if self._current_retry < self._max_retries:
                self._current_retry += 1
                _LOGGER.warning(
                    "刷新失败（%s），第%d次重试将在3分钟后执行",
                    str(e), self._current_retry
                )
                self._data_source = "缓存数据"
                # 3分钟后调度重试
                self.hass.loop.call_later(
                    self._retry_interval_seconds,
                    lambda: self.hass.async_create_task(self.async_update())
                )
            else:
                # 达最大重试次数：停止重试
                _LOGGER.error(
                    "刷新失败，已达最大重试次数（%d次），将在%d小时后再次尝试",
                    self._max_retries, self._update_interval_hours
                )
                self._current_retry = 0  # 重置重试计数
                self._data_source = "缓存数据（重试失败）"

    async def _fetch_api_data(self, session) -> dict:
        """发送API请求（记录请求时间，计入频率限制）"""
        async with self._request_lock:
            self._request_history.append(time.time())  # 记录请求时间
            _LOGGER.debug("API请求（1小时内第%d次）", len(self._request_history))

        try:
            # 加密参数（华润API要求）
            public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode())
            timestamp = int(time.time() * 1000)
            random_num = random.randint(1000, 9999)
            data_to_encrypt = f"e5b871c278a84defa8817d22afc34338#{timestamp}#{random_num}"
            encrypted_data = public_key.encrypt(data_to_encrypt.encode(), padding.PKCS1v15())
            base64_encrypted = base64.urlsafe_b64encode(encrypted_data).decode()

            # 构建请求
            request_body = {"USER": "bizH5", "PWD": base64_encrypted}
            base64_body = base64.urlsafe_b64encode(json.dumps(request_body).encode()).decode()
            url = f"{API_URL}?authVersion={API_AUTH_VERSION}&consNo={self._cno}"
            headers = {"Content-Type": "application/json", "Param": base64_body}

            # 发送请求
            async with session.get(url, headers=headers, timeout=30) as resp:
                resp_text = await resp.text()
                result = json.loads(resp_text)

                # 处理API错误
                status_code = result.get("statusCode")
                msg = result.get("msg")
                
                if status_code in RETRYABLE_STATUS_CODES:
                    raise ConnectionError(f"服务器临时错误：{msg}（{status_code}）")
                
                if msg != "操作成功":
                    raise ValueError(f"API错误：{msg}（{status_code}）")

                # 检查返回数据格式是否正确
                data = result.get("dataResult")
                if not isinstance(data, dict):
                    raise ValueError("API格式错误：dataResult字段缺失或格式不正确")

                # 处理数据为空的情况
                if not data:
                    _LOGGER.warning("API返回空数据，可能账号无记录")
                    return {}

                return data

        except Exception as e:
            _LOGGER.error("API请求失败：%s", str(e))
            raise  # 抛出错误触发重试

    async def _get_required_wait_time(self) -> float:  # 修复：改为异步函数（async def）
        """计算频率限制等待时间（确保1小时内请求≤20次）"""
        async with self._request_lock:  # 现在在异步函数中，合法使用async with
            if len(self._request_history) < MAX_HOURLY_REQUESTS:
                return 0.0  # 未超限

            # 最早的请求是否在1小时内
            earliest_time = self._request_history[0]
            time_since_earliest = time.time() - earliest_time
            if time_since_earliest >= self._hourly_window:
                return 0.0  # 最早请求已超出窗口

            # 需等待至最早请求超出窗口
            return self._hourly_window - time_since_earliest

    async def clear_cache(self, new_cno=None):
        """清空缓存数据（用于账号变更时）"""
        self._state = None
        self._last_data = None
        self._last_successful_update = None
        self._last_data_timestamp = None
        self._data_source = "无数据"
        self._request_history.clear()
        
        # 如果提供了新账号，更新账号
        if new_cno:
            self._cno = new_cno
            self._attr_unique_id = f"huarun_gas_{new_cno}_{self._entry_id}"
            
        _LOGGER.info("缓存已清空")
