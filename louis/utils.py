from louis import conf


def get_arg(explicit, conf_name, default):
    """
    Returns the prioritized source for the argument.  First checks if argument 
    explicitly given; if not, then checks for value in config file; if still not 
    found, will return default value.
    """ 
    if explicit:
        return explicit
    elif getattr(conf, conf_name, None):
        return getattr(conf, conf_name)
    else:
        if default:
            return default