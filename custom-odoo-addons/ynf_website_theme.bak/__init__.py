from . import models
from . import controllers


def _ynf_post_init(env):
    """Set up Lattafa-style mega-menu + Track My Order menu after install/upgrade."""
    try:
        env["website"]._ynf_setup_menus()
    except Exception:
        # Non-fatal: menus can be set up manually if this fails
        pass
