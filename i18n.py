"""国际化工具类"""
import logging
from typing import Dict, Optional
from homeassistant.helpers.translation import async_get_translations

_LOGGER = logging.getLogger(__name__)


class HuarunI18n:
    def __init__(self, hass, domain: str, default_lang: str = "zh-Hans"):
        self.hass = hass
        self.domain = domain
        self.default_lang = default_lang
        self.translations: Dict = {}

    async def init_async(self, lang: Optional[str] = None):
        """初始化翻译（优先用户语言，否则用系统默认）"""
        current_lang = lang or self.hass.config.language
        _LOGGER.debug(f"加载翻译，语言: {current_lang}")

        # 加载当前语言翻译
        self.translations = await self._load_translations(current_lang)

        # 补充默认语言翻译（防止缺失）
        if current_lang != self.default_lang:
            default_trans = await self._load_translations(self.default_lang)
            self._merge_translations(default_trans)

    async def _load_translations(self, lang: str) -> Dict:
        """从翻译文件加载内容"""
        translations = await async_get_translations(
            self.hass, lang, integrations=[self.domain], category="config_flow"
        )
        return translations.get(self.domain, {}).get("config_flow", {})

    def _merge_translations(self, default_trans: Dict):
        """合并默认语言翻译（当前语言缺失时补充）"""
        def deep_merge(target: Dict, source: Dict):
            for k, v in source.items():
                if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                    deep_merge(target[k], v)
                elif k not in target:
                    target[k] = v
        deep_merge(self.translations, default_trans)

    def get_text(self, key: str, default: str = "") -> str:
        """获取翻译文本（支持嵌套键）"""
        keys = key.split(".")
        current = self.translations
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                _LOGGER.debug(f"翻译键缺失: {key}，使用默认值")
                return default
        return current if isinstance(current, str) else default