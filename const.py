"""华润燃气 v2 集成常量定义（支持多语言翻译）"""
import voluptuous as vol

# 集成核心信息
DOMAIN = "huarun_gas_v2"  # 集成唯一标识（必须与目录名一致）
NAME = "华润燃气 v2"  # 集成显示名称
VERSION = "2.0.0"  # 版本号

# 配置项键名（用于存储配置数据）
CONF_CNO = "cno"  # 用户账号（存储键名）
CONF_NAME = "name"  # 传感器名称（存储键名）
CONF_UPDATE_INTERVAL = "update_interval_hours"  # 更新间隔（存储键名，单位：小时）


# 配置默认值与限制
DEFAULT_NAME = "华润燃气余额"  # 传感器默认名称
DEFAULT_UPDATE_INTERVAL = 24  # 默认更新间隔（小时）
MIN_UPDATE_INTERVAL = 1  # 最小更新间隔（小时）
MAX_UPDATE_INTERVAL = 72  # 最大更新间隔（小时）
MAX_HOURLY_REQUESTS = 20  # 每小时最大请求次数（防止API限制）
HOURLY_WINDOW = 3600  # 时间窗口（秒，用于请求频率控制）

# 新增：定义可重试的状态码
RETRYABLE_STATUS_CODES = [500, 502, 503, 504]  # 根据实际情况调整

# 支持的设备平台
PLATFORMS = ["sensor"]  # 仅支持传感器平台

# API 配置信息
API_URL = "https://mbhapp.crcgas.com/bizonline/api/h5/pay/queryArrears"  # 燃气数据查询接口
API_AUTH_VERSION = "v2"  # API 认证版本
PUBLIC_KEY_PEM = '''-----BEGIN PUBLIC KEY-----
MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAIi4Gb8iOGcc05iqNilFb1gM6/iG4fSiECeEaEYN2cxaBVT+6zgp+Tp0TbGVqGMIB034BLaVdNZZPnqKFH4As8UCAwEAAQ==
-----END PUBLIC KEY-----'''  # API 加密公钥


# 错误码（用于多语言提示）
ERROR_INVALID_CNO = "errors.error_invalid_cno"  # 无效账号错误键
ERROR_INVALID_INTERVAL = "errors.error_invalid_interval"  # 无效更新间隔错误键
ERROR_CNO_NOT_FOUND = "errors.error_cno_not_found"  # 账号不存在错误键
ERROR_API_FORMAT = "errors.error_api_format"  # API格式错误键

# 配置流程字段翻译键（对应 config_flow 表单字段）
ATTR_CNO = "step.user.data.attr_cno"  # 账号字段标签
ATTR_NAME = "step.user.data.attr_name"  # 名称字段标签
ATTR_UPDATE_INTERVAL = "step.user.data.attr_update_interval"  # 更新间隔字段标签

# 配置流程步骤描述翻译键
FLOW_STEP_USER_TITLE = "step.user.title"  # 用户配置步骤标题
FLOW_STEP_USER_DESCRIPTION = "step.user.description"  # 用户配置步骤描述
FLOW_STEP_OPTIONS_TITLE = "step.options.title"  # 选项配置步骤标题
FLOW_STEP_OPTIONS_DESCRIPTION = "step.options.description"  # 选项配置步骤描述

# 日志信息翻译键
LOG_SETUP_ENTRY = "log.setup_entry"  # 加载配置项日志
LOG_PLATFORM_LOAD_FAILED = "log.platform_load_failed"  # 平台加载失败日志
LOG_UNLOAD_ENTRY = "log.unload_entry"  # 卸载配置项日志

# 配置验证 Schema（用于校验用户输入）
DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_CNO): str,  # 账号（必填）
    vol.Optional(
        CONF_NAME,
        default=DEFAULT_NAME  # 默认名称
    ): str,
    vol.Optional(
        CONF_UPDATE_INTERVAL,
        default=DEFAULT_UPDATE_INTERVAL  # 默认更新间隔
    ): vol.All(
        int,
        vol.Range(
            min=MIN_UPDATE_INTERVAL,
            max=MAX_UPDATE_INTERVAL,
            msg=ERROR_INVALID_INTERVAL  # 错误提示关联到翻译键
        )
    )
})
