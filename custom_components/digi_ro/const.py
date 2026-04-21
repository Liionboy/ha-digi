DOMAIN = "digi_ro"
PLATFORMS = ["sensor"]

CONF_COOKIE = "cookie"
CONF_COOKIES = "cookies"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_AUTH_METHOD = "auth_method"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SELECTED_ADDRESS = "selected_address"

AUTH_METHOD_COOKIE = "cookie"
AUTH_METHOD_LOGIN = "login"

DEFAULT_UPDATE_INTERVAL = 1800
API_BASE = "https://www.digi.ro"
LOGIN_URL = f"{API_BASE}/auth/login?redirectTo=%2F"
TWO_FA_URL = f"{API_BASE}/auth/2fa?redirectTo=%2F"
TWO_FA_SEND_URL = f"{API_BASE}/api-post-2fa-send-code"
TWO_FA_VALIDATE_URL = f"{API_BASE}/api-post-2fa-validate-code"
ADDRESS_SELECT_URL = f"{API_BASE}/auth/address-select?redirectTo=%2F"
ADDRESS_CONFIRM_URL = f"{API_BASE}/store/address-confirm-existing"
INVOICES_URL = f"{API_BASE}/my-account/invoices"
ATTRIBUTION = "Date furnizate de DIGI România"
