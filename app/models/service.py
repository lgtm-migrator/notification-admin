from flask import Markup, abort, current_app
from flask_babel import _
from flask_babel import lazy_gettext as _l
from notifications_utils.field import Field
from notifications_utils.formatters import nl2br
from notifications_utils.take import Take
from werkzeug.utils import cached_property

from app.models import JSONModel
from app.models.organisation import Organisation
from app.models.user import InvitedUsers, User, Users
from app.notify_client.api_key_api_client import api_key_api_client
from app.notify_client.billing_api_client import billing_api_client
from app.notify_client.email_branding_client import email_branding_client
from app.notify_client.inbound_number_client import inbound_number_client
from app.notify_client.invite_api_client import invite_api_client
from app.notify_client.job_api_client import job_api_client
from app.notify_client.letter_branding_client import letter_branding_client
from app.notify_client.service_api_client import service_api_client
from app.notify_client.template_folder_api_client import template_folder_api_client
from app.utils import get_default_sms_sender


class Service(JSONModel):

    ALLOWED_PROPERTIES = {
        "active",
        "contact_link",
        "email_branding",
        "email_from",
        "id",
        "inbound_api",
        "letter_branding",
        "letter_contact_block",
        "message_limit",
        "sms_daily_limit",
        "rate_limit",
        "name",
        "permissions",
        "prefix_sms",
        "research_mode",
        "service_callback_api",
        "volume_email",
        "volume_sms",
        "volume_letter",
        "consent_to_research",
        "count_as_live",
        "go_live_user",
        "go_live_at",
        "sending_domain",
    }

    TEMPLATE_TYPES = (
        "email",
        "sms",
        "letter",
    )

    def __init__(self, _dict):

        super().__init__(_dict)
        if "permissions" not in self._dict:
            self.permissions = {"email", "sms", "letter"}

    @classmethod
    def from_id(cls, service_id):
        return cls(service_api_client.get_service(service_id)["data"])

    def update(self, **kwargs):
        return service_api_client.update_service(self.id, **kwargs)

    def update_count_as_live(self, count_as_live):
        return service_api_client.update_count_as_live(self.id, count_as_live=count_as_live)

    def update_status(self, live, message_limit, sms_daily_limit):
        return service_api_client.update_status(self.id, live=live, message_limit=message_limit, sms_daily_limit=sms_daily_limit)

    def force_permission(self, permission, on=False):

        permissions, permission = set(self.permissions), {permission}

        return self.update_permissions(
            permissions | permission if on else permissions - permission,
        )

    def update_permissions(self, permissions):
        return self.update(permissions=list(permissions))

    def toggle_research_mode(self):
        self.update(research_mode=not self.research_mode)

    @property
    def trial_mode(self):
        return self._dict["restricted"]

    @property
    def live(self):
        return not self.trial_mode

    def has_permission(self, permission):
        return permission in self.permissions

    @cached_property
    def has_jobs(self):
        return job_api_client.has_jobs(self.id)

    @cached_property
    def invited_users(self):
        return InvitedUsers(self.id)

    @cached_property
    def active_users(self):
        return Users(self.id)

    @cached_property
    def team_members(self):
        return sorted(
            self.invited_users + self.active_users,
            key=lambda user: user.email_address.lower(),
        )

    @cached_property
    def has_team_members(self):
        return len([user for user in self.active_users if user.has_permission_for_service(self.id, "manage_service")]) > 1

    @cached_property
    def has_team_members_status(self):
        """
        `has_team_members` only checks for active users, this property looks
        for invited users as well.

        Returns True, "in-progress" or False
        """
        if self.has_team_members:
            return True

        active_and_invited_members = [
            user for user in self.team_members if user.has_permission_for_service(self.id, "manage_service")
        ]
        if len(active_and_invited_members) > 1:
            return "in-progress"

        return False

    def cancel_invite(self, invited_user_id):
        if str(invited_user_id) not in {user.id for user in self.invited_users}:
            abort(404)

        return invite_api_client.cancel_invited_user(
            service_id=self.id,
            invited_user_id=str(invited_user_id),
        )

    def get_team_member(self, user_id):

        if str(user_id) not in {user.id for user in self.active_users}:
            abort(404)

        return User.from_id(user_id)

    @cached_property
    def all_templates(self):

        templates = service_api_client.get_service_templates(self.id)["data"]

        return [template for template in templates if template["template_type"] in self.available_template_types]

    @cached_property
    def all_template_ids(self):
        return {template["id"] for template in self.all_templates}

    def get_templates(self, template_type="all", template_folder_id=None, user=None):
        if user and template_folder_id:
            folder = self.get_template_folder(template_folder_id)
            if not user.has_template_folder_permission(folder):
                return []

        if isinstance(template_type, str):
            template_type = [template_type]
        if template_folder_id:
            template_folder_id = str(template_folder_id)
        return [
            template
            for template in self.all_templates
            if (set(template_type) & {"all", template["template_type"]}) and template.get("folder") == template_folder_id
        ]

    def get_template(self, template_id, version=None):
        return service_api_client.get_service_template(self.id, str(template_id), version)["data"]

    def get_template_folder_with_user_permission_or_403(self, folder_id, user):
        template_folder = self.get_template_folder(folder_id)

        if not user.has_template_folder_permission(template_folder):
            abort(403)

        return template_folder

    def get_template_with_user_permission_or_403(self, template_id, user):
        template = self.get_template(template_id)

        self.get_template_folder_with_user_permission_or_403(template["folder"], user)

        return template

    @property
    def available_template_types(self):
        return list(filter(self.has_permission, self.TEMPLATE_TYPES))

    @property
    def use_case_data(self):
        result = service_api_client.get_use_case_data(self.id)
        if result is None:
            return None, {}
        return result["step"], result["form_data"]

    def store_use_case_data(self, step, form_data):
        return service_api_client.store_use_case_data(
            self.id,
            {
                "step": step,
                "form_data": form_data,
            },
        )

    @property
    def has_accepted_tos(self):
        return service_api_client.has_accepted_tos(self.id)

    @property
    def has_submitted_go_live(self):
        return self.go_live_user is not None

    @property
    def pending_live(self):
        return self.trial_mode and self.has_submitted_go_live

    def register_submit_use_case(self):
        return service_api_client.register_submit_use_case(self.id)

    @property
    def has_submitted_use_case(self):
        return service_api_client.has_submitted_use_case(self.id)

    @property
    def has_templates(self):
        return bool(self.all_templates)

    def has_folders(self):
        return bool(self.all_template_folders)

    @property
    def has_multiple_template_types(self):
        return len({template["template_type"] for template in self.all_templates}) > 1

    @property
    def has_email_templates(self):
        return len(self.get_templates("email")) > 0

    @property
    def has_sms_templates(self):
        return len(self.get_templates("sms")) > 0

    @cached_property
    def email_reply_to_addresses(self):
        return service_api_client.get_reply_to_email_addresses(self.id)

    @property
    def has_email_reply_to_address(self):
        return bool(self.email_reply_to_addresses)

    @property
    def count_email_reply_to_addresses(self):
        return len(self.email_reply_to_addresses)

    @property
    def default_email_reply_to_address(self):
        return next(
            (x["email_address"] for x in self.email_reply_to_addresses if x["is_default"]),
            None,
        )

    def get_email_reply_to_address(self, id):
        return service_api_client.get_reply_to_email_address(self.id, id)

    @cached_property
    def sms_senders(self):
        return service_api_client.get_sms_senders(self.id)

    @property
    def sms_senders_with_hints(self):
        def attach_hint(sender):
            hints = []
            default_txt = _("default")
            if sender["is_default"]:
                hints += [default_txt]
            if sender["inbound_number_id"]:
                hints += ["receives replies"]
            if hints:
                sender["hint"] = "(" + " and ".join(hints) + ")"
            return sender

        return [attach_hint(sender) for sender in self.sms_senders]

    @property
    def default_sms_sender(self):
        return get_default_sms_sender(self.sms_senders)

    @property
    def count_sms_senders(self):
        return len(self.sms_senders)

    @property
    def sms_sender_is_govuk(self):
        return self.default_sms_sender in {"GOVUK", "None"}

    def get_sms_sender(self, id):
        return service_api_client.get_sms_sender(self.id, id)

    @cached_property
    def letter_contact_details(self):
        return service_api_client.get_letter_contacts(self.id)

    @property
    def count_letter_contact_details(self):
        return len(self.letter_contact_details)

    @property
    def default_letter_contact_block(self):
        return next(
            (letter_contact_block for letter_contact_block in self.letter_contact_details if letter_contact_block["is_default"]),
            None,
        )

    @property
    def default_letter_contact_block_html(self):
        if self.default_letter_contact_block:
            return Markup(
                Take(
                    Field(
                        self.default_letter_contact_block["contact_block"],
                        html="escape",
                    )
                ).then(nl2br)
            )
        return ""

    def edit_letter_contact_block(self, id, contact_block, is_default):
        service_api_client.update_letter_contact(
            self.id,
            letter_contact_id=id,
            contact_block=contact_block,
            is_default=is_default,
        )

    def remove_default_letter_contact_block(self):
        if self.default_letter_contact_block:
            self.edit_letter_contact_block(
                self.default_letter_contact_block["id"],
                self.default_letter_contact_block["contact_block"],
                is_default=False,
            )

    def get_letter_contact_block(self, id):
        return service_api_client.get_letter_contact(self.id, id)

    @property
    def go_live_checklist(self):
        # `status` can be False, True or "in-progress"
        # `completed` is False or True
        items = [
            {
                "text": _("Tell us about how you intend to use GC Notify"),
                "status": self.has_submitted_use_case,
                "endpoint": "main.use_case",
            },
            {
                "text": _("Add templates with content you plan on sending"),
                "status": self.has_templates,
                "endpoint": "main.choose_template",
            },
            {
                "text": _("Add a team member who can manage settings"),
                "status": self.has_team_members_status,
                "endpoint": "main.manage_users",
            },
            {
                "text": _("Accept the terms of use"),
                "status": self.has_accepted_tos,
                "endpoint": "main.terms_of_use",
            },
        ]

        return [item | {"completed": item["status"] is True} for item in items]

    @property
    def go_live_checklist_completed(self):
        return all([checklist["completed"] for checklist in self.go_live_checklist])

    @cached_property
    def free_sms_fragment_limit(self):
        return billing_api_client.get_free_sms_fragment_limit_for_year(self.id) or 0

    @cached_property
    def data_retention(self):
        return service_api_client.get_service_data_retention(self.id)

    def get_data_retention_item(self, id):
        return next((dr for dr in self.data_retention if dr["id"] == id), None)

    def get_days_of_retention(self, notification_type):
        return next(
            (dr for dr in self.data_retention if dr["notification_type"] == notification_type),
            {},
        ).get("days_of_retention", current_app.config["ACTIVITY_STATS_LIMIT_DAYS"])

    @property
    def email_branding_id(self):
        return self._dict["email_branding"]

    @property
    def default_branding_is_french(self):
        return self._dict["default_branding_is_french"]

    @cached_property
    def email_branding(self):
        if self.email_branding_id:
            return email_branding_client.get_email_branding(self.email_branding_id)["email_branding"]
        return None

    @cached_property
    def email_branding_name(self):
        if self.email_branding is None:
            return (
                "French Government of Canada signature"
                if self.default_branding_is_french is True
                else "English Government of Canada signature"
            )
        return self.email_branding["name"]

    @property
    def letter_branding_id(self):
        return self._dict["letter_branding"]

    @cached_property
    def letter_branding(self):
        if self.letter_branding_id:
            return letter_branding_client.get_letter_branding(self.letter_branding_id)
        return None

    @cached_property
    def organisation(self):
        return Organisation.from_service(self.id)

    @property
    def organisation_id(self):
        return self._dict["organisation"]

    @property
    def organisation_type(self):
        return self.organisation.organisation_type or self._dict["organisation_type"]

    @property
    def organisation_type_label(self):
        return dict(Organisation.TYPES).get(self.organisation_type)

    @cached_property
    def inbound_number(self):
        return inbound_number_client.get_inbound_sms_number_for_service(self.id)["data"].get("number", "")

    @property
    def has_inbound_number(self):
        return bool(self.inbound_number)

    @cached_property
    def all_template_folders(self):
        return sorted(
            template_folder_api_client.get_template_folders(self.id),
            key=lambda folder: folder["name"].lower(),
        )

    @cached_property
    def all_template_folder_ids(self):
        return {folder["id"] for folder in self.all_template_folders}

    def get_user_template_folders(self, user):
        """Returns a modified list of folders a user has permission to view

        For each folder, we do the following:
        - if user has no permission to view the folder, skip it
        - if folder is visible and its parent is visible, we add it to the list of folders
        we later return without modifying anything
        - if folder is visible, but the parent is not, we iterate through the parent until we
        either find a visible parent or reach root folder. On each iteration we concatenate
        invisible parent folder name to the front of our folder name, modifying the name, and we
        change parent_folder_id attribute to a higher level parent. This flattens the path to the
        folder making sure it displays in the closest visible parent.

        """
        user_folders = []
        for folder in self.all_template_folders:
            if not user.has_template_folder_permission(folder, service=self):
                continue
            parent = self.get_template_folder(folder["parent_id"])
            if user.has_template_folder_permission(parent, service=self):
                user_folders.append(folder)
            else:
                folder_attrs = {
                    "id": folder["id"],
                    "name": folder["name"],
                    "parent_id": folder["parent_id"],
                    "users_with_permission": folder["users_with_permission"],
                }
                while folder_attrs["parent_id"] is not None:
                    folder_attrs["name"] = [
                        parent["name"],
                        folder_attrs["name"],
                    ]
                    if parent["parent_id"] is None:
                        folder_attrs["parent_id"] = None
                    else:
                        parent = self.get_template_folder(parent["parent_id"])
                        folder_attrs["parent_id"] = parent.get("id", None)
                        if user.has_template_folder_permission(parent, service=self):
                            break
                user_folders.append(folder_attrs)
        return user_folders

    def get_template_folders(self, template_type="all", parent_folder_id=None, user=None):
        if user:
            folders = self.get_user_template_folders(user)
        else:
            folders = self.all_template_folders
        if parent_folder_id:
            parent_folder_id = str(parent_folder_id)

        return [
            folder
            for folder in folders
            if (folder["parent_id"] == parent_folder_id and self.is_folder_visible(folder["id"], template_type, user))
        ]

    def get_template_folder(self, folder_id):
        if folder_id is None:
            return {
                "id": None,
                "name": _l("Templates"),
                "parent_id": None,
            }
        return self._get_by_id(self.all_template_folders, folder_id)

    def is_folder_visible(self, template_folder_id, template_type="all", user=None):

        if template_type == "all":
            return True

        if self.get_templates(template_type, template_folder_id):
            return True

        if any(
            self.is_folder_visible(child_folder["id"], template_type, user)
            for child_folder in self.get_template_folders(template_type, template_folder_id, user)
        ):
            return True

        return False

    def get_template_folder_path(self, template_folder_id):

        folder = self.get_template_folder(template_folder_id)

        if folder["id"] is None:
            return [folder]

        return self.get_template_folder_path(folder["parent_id"]) + [self.get_template_folder(folder["id"])]

    def get_template_path(self, template):
        return self.get_template_folder_path(template["folder"]) + [
            template,
        ]

    def get_template_folders_and_templates(self, template_type, template_folder_id):
        return self.get_templates(template_type, template_folder_id) + self.get_template_folders(
            template_type, template_folder_id
        )

    @property
    def count_of_templates_and_folders(self):
        return len(self.all_templates + self.all_template_folders)

    def move_to_folder(self, ids_to_move, move_to):

        ids_to_move = set(ids_to_move)

        template_folder_api_client.move_to_folder(
            service_id=self.id,
            folder_id=move_to,
            template_ids=ids_to_move & self.all_template_ids,
            folder_ids=ids_to_move & self.all_template_folder_ids,
        )

    @cached_property
    def api_keys(self):
        return sorted(
            api_key_api_client.get_api_keys(self.id)["apiKeys"],
            key=lambda key: key["name"].lower(),
        )

    def get_api_key(self, id):
        return self._get_by_id(self.api_keys, id)
