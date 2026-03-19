from contextvars import ContextVar


_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_user_id_var: ContextVar[str] = ContextVar("user_id", default="")
_user_role_var: ContextVar[str] = ContextVar("user_role", default="")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


def set_actor(user_id: str, role: str) -> None:
    _user_id_var.set(user_id)
    _user_role_var.set(role)


def clear_actor() -> None:
    _user_id_var.set("")
    _user_role_var.set("")


def get_actor() -> tuple[str, str]:
    return _user_id_var.get(), _user_role_var.get()
