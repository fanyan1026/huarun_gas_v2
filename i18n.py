import json
import logging
import os
import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation

_LOGGER = logging.getLogger(__name__)

class HuarunI18n:
    def __init__(self, hass: HomeAssistant, domain: str):
        self.hass = hass
        self.domain = domain
        self.translations = {}
        self.lang = None

    async def init_async(self):
        """异步初始化国际化字典"""
        self.lang = await self._get_current_language()
        self.translations = await self._load_translations(self.lang)
        if not self.translations:
            _LOGGER.error(
                "[I18N] 致命错误：Home Assistant返回空翻译数据，语言: %s", self.lang
            )
            await self._log_possible_causes()
        else:
            _LOGGER.info("[I18N] 国际化文件加载成功，当前语言：%s，已加载key数：%d", self.lang, len(self.translations))

    async def _log_possible_causes(self):
        _LOGGER.error("[I18N] 可能原因：")
        _LOGGER.error("  1. 集成ID(%s)与manifest.json中的domain不匹配", self.domain)
        _LOGGER.error("  2. Home Assistant版本与集成不兼容")
        _LOGGER.error("  3. translations目录位置不正确")

    async def _get_current_language(self):
        language = getattr(self.hass.config, "language", None)
        if not language:
            language = "en"
        return language

    async def _load_translations(self, lang: str):
        """优先通过HA官方API获取，如失败则fallback到本地文件"""
        try:
            translations = await translation.async_get_translations(
                self.hass, lang, integrations=[self.domain], category="config_flow"
            )
            data = self._extract_valid_translations(translations)
            if data:
                return data
        except Exception as e:
            _LOGGER.warning("[I18N] async_get_translations异常: %s，fallback到本地文件", e)

        return await self._load_translations_from_file(lang)

    def _extract_valid_translations(self, raw_trans):
        """提取有效的 config_flow 子树"""
        paths_to_try = [
            f"{self.domain}.config_flow",
            "config_flow",
            self.domain,
            "",
        ]
        for path in paths_to_try:
            node = raw_trans
            if not path:
                if isinstance(node, dict) and any(k in node for k in ("step", "log", "errors")):
                    return node
                continue
            for part in path.split("."):
                if part and isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    break
            else:
                if isinstance(node, dict) and any(k in node for k in ("step", "log", "errors")):
                    return node
        return {}

    async def _load_translations_from_file(self, lang: str):
        """异步从本地json文件读取国际化内容"""
        translations_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "translations"
        )
        file_map = [
            f"{lang}.json",
            f"{lang.replace('-','_')}.json",
            "en.json",
        ]
        for fname in file_map:
            lang_filepath = os.path.join(translations_dir, fname)
            if await self._validate_language_file(lang_filepath):
                try:
                    async with aiofiles.open(lang_filepath, "r", encoding="utf-8") as f:
                        content = await f.read()
                        data = json.loads(content)
                        _LOGGER.info("[I18N] 已从本地文件加载翻译: %s", lang_filepath)
                        return self._extract_valid_translations(data)
                except Exception as e:
                    _LOGGER.error("[I18N] 解析本地翻译文件失败: %s, 错误: %s", lang_filepath, e)
        _LOGGER.error("[I18N] 未找到可用的翻译文件")
        return {}

    async def _validate_language_file(self, lang_filepath):
        """异步检查本地翻译文件是否存在且合法"""
        try:
            async with aiofiles.open(lang_filepath, "r", encoding="utf-8") as f:
                content = await f.read()
                json.loads(content)
            return True
        except Exception:
            return False

    def get_text(self, key: str, default: str = "") -> str:
        """多级key获取国际化文本，如step.user.title"""
        node = self.translations
        if not node:
            _LOGGER.warning("[I18N] translations尚未初始化或为空")
            return default or key
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                _LOGGER.warning(
                    "[I18N] 键缺失: %s，在路径 %s 处找不到 %s", key, " → ".join(key.split(".")[:-1]), part
                )
                _LOGGER.warning("[I18N] 当前节点可用子键: %s", list(node.keys()) if isinstance(node, dict) else "非dict")
                return default or key
        if isinstance(node, str):
            return node
        else:
            _LOGGER.warning("[I18N] key路径%s指向的内容不是字符串: %s", key, str(node))
            return default or key
