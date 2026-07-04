from . import agent_bridges, agents, archive_room, browser, config, meetings, notifications, projects, providers, skills, workflow


ROUTE_MODULES = (config, browser, notifications, providers, skills, agents, agent_bridges, meetings, archive_room, workflow, projects)


def dispatch(handler, method, parsed_url):
    method = (method or "").upper()
    fn_name = {
        "GET": "handle_get",
        "POST": "handle_post",
        "PUT": "handle_put",
        "DELETE": "handle_delete",
    }.get(method)
    if not fn_name:
        return False
    for module in ROUTE_MODULES:
        handler_fn = getattr(module, fn_name, None)
        if handler_fn and handler_fn(handler, parsed_url):
            return True
    return False
