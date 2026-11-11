"""Small shims so one code base runs on Odoo 17 to 20."""


def get_param(icp, key, default=False):
    """ir.config_parameter.get_param, which Odoo 20 replaced with typed getters (get_str...)."""
    if hasattr(icp, "get_param"):
        return icp.get_param(key, default)
    value = icp.get_str(key, None)
    return default if value in (None, "") else value


def set_param(icp, key, value):
    if hasattr(icp, "set_param"):
        return icp.set_param(key, value)
    return icp.set_str(key, value)
