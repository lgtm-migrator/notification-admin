import os

from flask import session
from mixpanel import Mixpanel  # type: ignore
from typing import Dict


class MixpanelInitializationError(Exception):
    """raised when MIXPANEL_PROJECT_TOKEN environment varaible is not set"""


class NotifyMixpanel:
    def __init__(self, callable) -> None:
        if not os.environ.get("MIXPANEL_PROJECT_TOKEN"):
            raise MixpanelInitializationError

        self.callable = callable
        self.mixpanel = Mixpanel(os.environ.get("MIXPANEL_PROJECT_TOKEN"))
        self.user: Dict[str, str] = {}

    def __call__(self, *args, **kwargs) -> None:
        self.callable(*args, **kwargs)

        if "user_details" in session:
            self.user = session["user_details"].copy()
            self.user.pop("password")
        else:
            return None


class track_mixpanel_event(NotifyMixpanel):
    def __call__(self, *args, **kwargs) -> None:
        super(track_mixpanel_event, self).__call__(*args, **kwargs)

        if self.user:
            self.mixpanel.track(str(self.user.get("email")), "Logged in", {})


class track_mixpanel_user_profile(NotifyMixpanel):
    def __call__(self, *args, **kwargs) -> None:
        super(track_mixpanel_user_profile, self).__call__(*args, **kwargs)

        if self.user:
            self.mixpanel.people_set(str(self.user.get("email")), self.user, meta={})
