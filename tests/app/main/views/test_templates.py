from datetime import datetime
from functools import partial
from unittest.mock import ANY, MagicMock, Mock

import pytest
from flask import url_for
from freezegun import freeze_time
from notifications_python_client.errors import HTTPError

from app.main.views.templates import (
    delete_preview_data,
    get_human_readable_delta,
    get_preview_data,
    set_preview_data,
)
from app.models.service import Service
from tests import (
    MockRedis,
    sample_uuid,
    single_notification_json,
    template_json,
    validate_route_permission,
)
from tests.app.main.views.test_template_folders import (
    CHILD_FOLDER_ID,
    FOLDER_TWO_ID,
    PARENT_FOLDER_ID,
    _folder,
    _template,
)
from tests.conftest import (
    SERVICE_ONE_ID,
    SERVICE_TWO_ID,
    TEMPLATE_ONE_ID,
    ClientRequest,
    ElementNotFound,
    create_active_caseworking_user,
    create_active_user_view_permissions,
    create_email_template,
    create_letter_contact_block,
    create_letter_template,
    create_letter_template_with_variables,
    create_sms_template,
    create_template,
    fake_uuid,
    mock_get_service_template_with_process_type,
    normalize_spaces,
)


class TestRedisPreviewUtilities:
    def test_set_get(self, fake_uuid, mocker):
        mock_redis_obj = MockRedis()
        mock_redis_method = MagicMock()
        mock_redis_method.get = Mock(side_effect=mock_redis_obj.get)
        mock_redis_method.set = Mock(side_effect=mock_redis_obj.set)
        mocker.patch("app.main.views.templates.redis_client", mock_redis_method)

        expected_data = {
            "name": "test name",
            "content": "test content",
            "template_content": "test content",
            "subject": "test subject",
            "template_type": "email",
            "process_type": "normal",
            "id": fake_uuid,
            "folder": None,
            "reply_to_text": "reply@go.com",
        }
        set_preview_data(expected_data, fake_uuid)
        actual_data = get_preview_data(fake_uuid)

        assert actual_data == expected_data

    def test_delete(self, fake_uuid, mocker):
        mock_redis_obj = MockRedis()
        mock_redis_method = MagicMock()
        mock_redis_method.get = Mock(side_effect=mock_redis_obj.get)
        mock_redis_method.set = Mock(side_effect=mock_redis_obj.set)
        mock_redis_method.delete = Mock(side_effect=mock_redis_obj.delete)
        mocker.patch("app.main.views.templates.redis_client", mock_redis_method)

        data = {
            "name": "test name",
            "content": "test content",
            "template_content": "test content",
            "subject": "test subject",
            "template_type": "email",
            "process_type": "normal",
            "id": fake_uuid,
            "folder": None,
            "reply_to_text": "reply@go.com",
        }
        set_preview_data(data, fake_uuid)
        delete_preview_data(fake_uuid)
        actual_data = get_preview_data(fake_uuid)

        assert actual_data == {}


def test_should_show_empty_page_when_no_templates(
    client_request,
    service_one,
    mock_get_service_templates_when_no_templates_exist,
    mock_get_template_folders,
):

    page = client_request.get(
        "main.choose_template",
        service_id=service_one["id"],
    )

    assert normalize_spaces(page.select_one("h1").text) == ("Templates")
    assert normalize_spaces(page.select_one("main p").text) == (
        "You need to create a template to send emails or text messages. You can also create folders to organize your templates."
    )
    assert page.select_one("#add_new_folder_form")
    assert page.select_one("#add_new_template_form")


def test_should_show_create_template_button_if_service_has_folder_permission(
    client_request: ClientRequest,
    service_one: Service,
    mock_get_service_templates_when_no_templates_exist,
    mock_get_template_folders,
):
    page = client_request.get(
        "main.choose_template",
        service_id=service_one.id,
    )

    assert normalize_spaces(page.select_one("h1").text) == ("Templates")
    assert normalize_spaces(page.select_one("main p").text) == (
        "You need to create a template to send emails or text messages. You can also create folders to organize your templates."
    )
    assert "Create template" in page.select_one("#add_new_template_form a.button").text


@pytest.mark.parametrize(
    "user, expected_page_title, extra_args, expected_templates",
    [
        (
            create_active_user_view_permissions(),
            "Browse Templates",
            {},
            [
                "sms_template_one",
                "sms_template_two",
                "email_template_one",
                "email_template_two",
                "letter_template_one",
                "letter_template_two",
            ],
        ),
        (
            create_active_user_view_permissions(),
            "Browse Templates",
            {"template_type": "sms"},
            ["sms_template_one", "sms_template_two"],
        ),
        (
            create_active_user_view_permissions(),
            "Browse Templates",
            {"template_type": "email"},
            ["email_template_one", "email_template_two"],
        ),
        (
            create_active_user_view_permissions(),
            "Browse Templates",
            {"template_type": "letter"},
            ["letter_template_one", "letter_template_two"],
        ),
        (
            create_active_caseworking_user(),
            "Browse Templates",
            {},
            [
                "sms_template_one",
                "sms_template_two",
                "email_template_one",
                "email_template_two",
                "letter_template_one",
                "letter_template_two",
            ],
        ),
        (
            create_active_caseworking_user(),
            "Browse Templates",
            {"template_type": "email"},
            ["email_template_one", "email_template_two"],
        ),
    ],
)
def test_should_show_page_for_choosing_a_template(
    client_request,
    mock_get_service_templates,
    mock_get_template_folders,
    mock_has_no_jobs,
    extra_args,
    expected_templates,
    service_one,
    mocker,
    fake_uuid,
    user,
    expected_page_title,
):
    expected_nav_links = ["All", "Email", "Text message", "Letter"]
    service_one["permissions"].append("letter")
    client_request.login(user)

    page = client_request.get("main.choose_template", service_id=service_one["id"], **extra_args)

    assert normalize_spaces(page.select_one("h1").text) == expected_page_title

    links_in_page = page.select(".pill a")

    assert len(links_in_page) == len(expected_nav_links)

    for index, expected_link in enumerate(expected_nav_links):
        assert links_in_page[index].text.strip() == expected_link

    template_links = page.select(".message-name a")

    assert len(template_links) == len(expected_templates)

    for index, expected_template in enumerate(expected_templates):
        assert template_links[index].text.strip() == expected_template

    mock_get_service_templates.assert_called_once_with(SERVICE_ONE_ID)
    mock_get_template_folders.assert_called_once_with(SERVICE_ONE_ID)


def test_choose_template_can_pass_through_an_initial_state_to_templates_and_folders_selection_form(
    client_request,
    mock_get_template_folders,
    mock_get_service_templates,
):
    page = client_request.get(
        "main.choose_template",
        service_id=SERVICE_ONE_ID,
        initial_state="add-new-template",
    )

    templates_and_folders_form = page.find("form")
    assert templates_and_folders_form["data-prev-state"] == "add-new-template"


def test_should_not_show_template_nav_if_only_one_type_of_template(
    client_request,
    mock_get_template_folders,
    mock_get_service_templates_with_only_one_template,
):

    page = client_request.get(
        "main.choose_template",
        service_id=SERVICE_ONE_ID,
    )

    assert not page.select(".pill")


def test_choose_template_page_with_sending_view(
    client_request: ClientRequest,
    mock_get_template_folders,
    mock_get_service_templates,
):
    page = client_request.get("main.choose_template", service_id=SERVICE_ONE_ID, view="sending")
    assert "Create template" not in page.text
    assert "Select template to send" in page.text
    assert not page.select("input[type=checkbox]")
    pill_links = [a["href"] for a in page.select(".pill a")]
    assert all([link.endswith("?view=sending") for link in pill_links])


def test_choose_template_page_without_sending_view(
    client_request: ClientRequest,
    mock_get_template_folders,
    mock_get_service_templates,
):
    page = client_request.get("main.choose_template", service_id=SERVICE_ONE_ID)
    assert "Create template" in page.text
    assert "Select template to send" not in page.text
    assert page.select("input[type=checkbox]")
    pill_links = [a["href"] for a in page.select(".pill a")]
    assert all([not link.endswith("?view=sending") for link in pill_links])


def test_should_not_show_live_search_if_list_of_templates_fits_onscreen(
    client_request, mock_get_template_folders, mock_get_service_templates
):

    page = client_request.get(
        "main.choose_template",
        service_id=SERVICE_ONE_ID,
    )

    assert not page.select(".live-search")


def test_should_show_live_search_if_list_of_templates_taller_than_screen(
    client_request,
    mock_get_template_folders,
    mock_get_more_service_templates_than_can_fit_onscreen,
):

    page = client_request.get(
        "main.choose_template",
        service_id=SERVICE_ONE_ID,
    )
    search = page.select_one(".live-search")

    assert search["data-module"] == "live-search"
    assert search["data-targets"] == "#template-list .template-list-item"

    assert len(page.select(search["data-targets"])) == len(page.select(".message-name")) == 14


def test_should_show_live_search_if_service_has_lots_of_folders(
    client_request,
    mock_get_template_folders,
    mock_get_service_templates,  # returns 4 templates
):

    mock_get_template_folders.return_value = [
        _folder("one", PARENT_FOLDER_ID),
        _folder("two", None, parent=PARENT_FOLDER_ID),
        _folder("three", None, parent=PARENT_FOLDER_ID),
        _folder("four", None, parent=PARENT_FOLDER_ID),
    ]

    page = client_request.get(
        "main.choose_template",
        service_id=SERVICE_ONE_ID,
    )

    count_of_templates_and_folders = len(page.select(".message-name"))
    count_of_folders = len(page.select(".template-list-folder:first-child"))
    count_of_templates = count_of_templates_and_folders - count_of_folders

    assert len(page.select(".live-search")) == 1
    assert count_of_folders == 4
    assert count_of_templates == 4


@pytest.mark.parametrize(
    "extra_permissions, expected_values, expected_labels",
    (
        pytest.param(
            [],
            [
                "email",
                "sms",
            ],
            [
                "Email",
                "Text",
            ],
        ),
        pytest.param(
            ["letter"],
            ["email", "sms"],
            [
                "Email",
                "Text",
            ],
        ),
    ),
)
def test_should_show_new_template_choices_if_service_has_folder_permission(
    client_request: ClientRequest,
    service_one: Service,
    mock_get_service_templates,
    mock_get_template_folders,
    extra_permissions,
    expected_values,
    expected_labels,
):
    service_one.permissions += extra_permissions

    page = client_request.get(
        "main.create_template",
        service_id=SERVICE_ONE_ID,
    )

    if not page.select("#what_type"):
        raise ElementNotFound()

    assert normalize_spaces(page.select_one("fieldset#what_type")["aria-labelledby"]) == ("what_type-label")
    assert normalize_spaces(page.select_one("#what_type-label").text) == ("Will you send the message by email or text?")
    assert [choice["value"] for choice in page.select("#what_type input[type=radio]")] == expected_values
    assert [normalize_spaces(choice.text) for choice in page.select("#what_type label")] == expected_labels


def test_should_show_page_for_one_template(
    client_request,
    mock_get_service_template,
    fake_uuid,
):
    template_id = fake_uuid
    page = client_request.get(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=template_id,
    )

    assert page.select_one("input[type=text]")["value"] == "Two week reminder"
    assert "Template &lt;em&gt;content&lt;/em&gt; with &amp; entity" in str(page.select_one("textarea"))
    assert "priority" not in str(page.select_one("main"))
    mock_get_service_template.assert_called_with(SERVICE_ONE_ID, template_id, None)


def test_caseworker_redirected_to_one_off(
    client_request, mock_get_service_templates, mock_get_service_template, mocker, fake_uuid, active_caseworking_user
):

    mocker.patch("app.user_api_client.get_user", return_value=active_caseworking_user)

    client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _expected_status=302,
        _expected_redirect=url_for(
            "main.send_one_off",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )


def test_user_with_only_send_and_view_redirected_to_one_off(
    client_request,
    mock_get_service_templates,
    mock_get_service_template,
    active_user_with_permissions,
    mocker,
    fake_uuid,
):
    active_user_with_permissions["permissions"][SERVICE_ONE_ID] = [
        "send_messages",
        "view_activity",
    ]
    client_request.login(active_user_with_permissions)
    client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _expected_status=302,
        _expected_redirect=url_for(
            "main.send_one_off",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )


@pytest.mark.parametrize(
    "permissions",
    (
        {"send_messages", "view_activity"},
        {"send_messages"},
        {"view_activity"},
        {},
    ),
)
def test_user_with_only_send_and_view_sees_letter_page(
    client_request,
    mock_get_service_templates,
    mock_get_template_folders,
    mock_get_service_letter_template,
    single_letter_contact_block,
    mock_has_jobs,
    active_user_with_permissions,
    mocker,
    fake_uuid,
    permissions,
):
    mocker.patch("app.main.views.templates.get_page_count_for_letter", return_value=1)
    active_user_with_permissions["permissions"][SERVICE_ONE_ID] = permissions
    client_request.login(active_user_with_permissions)
    page = client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )
    assert normalize_spaces(page.select_one("h1").text) == ("Two week reminder")
    assert normalize_spaces(page.select_one("title").text) == ("Two week reminder – Templates - service one – Notify")


@pytest.mark.parametrize(
    "letter_branding, expected_link, expected_link_text",
    (
        (
            None,
            partial(url_for, "main.request_letter_branding", from_template=TEMPLATE_ONE_ID),
            "Add logo",
        ),
        (
            TEMPLATE_ONE_ID,
            partial(url_for, "main.edit_template_postage", template_id=TEMPLATE_ONE_ID),
            "Change",
        ),
    ),
)
@pytest.mark.skip(reason="feature not in use")
def test_letter_with_default_branding_has_add_logo_button(
    mocker,
    fake_uuid,
    client_request,
    service_one,
    mock_get_template_folders,
    mock_get_service_letter_template,
    single_letter_contact_block,
    letter_branding,
    expected_link,
    expected_link_text,
):
    mocker.patch("app.main.views.templates.get_page_count_for_letter", return_value=1)
    service_one["permissions"] += ["letter"]
    service_one["letter_branding"] = letter_branding

    page = client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        _test_page_title=False,
    )

    first_edit_link = page.select_one(".template-container a")
    assert first_edit_link["href"] == expected_link(service_id=SERVICE_ONE_ID)
    assert first_edit_link.text == expected_link_text


@pytest.mark.parametrize(
    "template_postage,expected_result",
    [
        ("first", "Postage: first class"),
        ("second", "Postage: second class"),
    ],
)
def test_view_letter_template_displays_postage(
    client_request,
    service_one,
    mock_get_service_templates,
    mock_get_template_folders,
    single_letter_contact_block,
    mock_has_jobs,
    active_user_with_permissions,
    mocker,
    fake_uuid,
    template_postage,
    expected_result,
):
    mocker.patch("app.main.views.templates.get_page_count_for_letter", return_value=1)
    client_request.login(active_user_with_permissions)

    template = create_letter_template(postage=template_postage)
    mocker.patch("app.service_api_client.get_service_template", return_value=template)

    page = client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=template["data"]["id"],
        _test_page_title=False,
    )

    assert normalize_spaces(page.select_one(".letter-postage").text) == expected_result


def test_view_non_letter_template_does_not_display_postage(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    fake_uuid,
):
    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )
    assert "Postage" not in page.text


def test_edit_letter_template_postage_page_displays_correctly(
    client_request,
    service_one,
    fake_uuid,
    mocker,
):
    mocker.patch("app.service_api_client.get_service_template", return_value=create_letter_template())

    page = client_request.get(
        "main.edit_template_postage",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
    )

    assert page.select_one("h1").text.strip() == "Change postage"
    assert page.select("input[checked]")[0].attrs["value"] == "second"


def test_edit_letter_template_postage_page_404s_if_template_is_not_a_letter(
    client_request,
    service_one,
    mock_get_service_template,
    active_user_with_permissions,
    mocker,
    fake_uuid,
):
    client_request.login(active_user_with_permissions)
    page = client_request.get(
        "main.edit_template_postage",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _expected_status=404,
    )

    assert page.select_one("h1").text.strip() != "Edit postage"


def test_edit_letter_templates_postage_updates_postage(client_request, service_one, mocker, fake_uuid):
    mock_update_template_postage = mocker.patch("app.main.views.templates.service_api_client.update_service_template_postage")
    mocker.patch("app.service_api_client.get_service_template", return_value=create_letter_template())

    client_request.post(
        "main.edit_template_postage",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={"postage": "first"},
    )
    mock_update_template_postage.assert_called_with(SERVICE_ONE_ID, fake_uuid, "first")


@pytest.mark.parametrize(
    "permissions, links_to_be_shown, permissions_warning_to_be_shown",
    [
        (
            ["view_activity"],
            [],
            "If you need to send this text message or edit this template, contact your service manager.",
        ),
        (
            ["manage_api_keys"],
            [],
            None,
        ),
        (
            ["manage_templates"],
            [".edit_service_template"],
            None,
        ),
        (
            ["send_messages", "manage_templates"],
            [".add_recipients", ".edit_service_template"],
            None,
        ),
    ],
)
def test_should_be_able_to_view_a_template_with_links(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    active_user_with_permissions,
    single_letter_contact_block,
    fake_uuid,
    permissions,
    links_to_be_shown,
    permissions_warning_to_be_shown,
):
    active_user_with_permissions["permissions"][SERVICE_ONE_ID] = permissions + ["view_activity"]
    client_request.login(active_user_with_permissions)

    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert normalize_spaces(page.select_one("h1").text) == ("Two week reminder")
    assert normalize_spaces(page.select_one("title").text) == ("Two week reminder – Templates - service one – Notify")

    links_in_page = page.select("a")

    for link_to_be_shown in links_to_be_shown:
        assert url_for(
            link_to_be_shown,
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
        ) in [a["href"] for a in links_in_page]

    assert normalize_spaces(page.select_one("main p").text) == (permissions_warning_to_be_shown or "To: phone number")


def test_should_show_template_id_on_template_page(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    fake_uuid,
):
    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )
    assert page.select(".api-key-key")[0].text == fake_uuid


def test_should_show_logos_on_template_page(
    client_request,
    fake_uuid,
    mocker,
    service_one,
    app_,
):
    mocker.patch(
        "app.service_api_client.get_service_template",
        return_value={"data": template_json(SERVICE_ONE_ID, fake_uuid, type_="email")},
    )
    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert service_one["default_branding_is_french"] is False
    assert service_one["email_branding"] is None

    email_body = str(page.select_one(".email-message-body"))
    assert f"https://{app_.config['ASSET_DOMAIN']}/gc-logo-en.png" in email_body
    assert f"https://{app_.config['ASSET_DOMAIN']}/canada-logo.png" in email_body


def test_should_not_show_send_buttons_on_template_page_for_user_without_permission(
    client_request,
    fake_uuid,
    mock_get_service_template,
    active_user_view_permissions,
):
    client_request.login(active_user_view_permissions)

    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert "Ready to send?" not in str(page)
    assert "No, send yourself this message" not in str(page)


def test_should_show_sms_template_with_downgraded_unicode_characters(
    client_request,
    mocker,
    service_one,
    single_letter_contact_block,
    mock_get_template_folders,
    fake_uuid,
):
    msg = "here:\tare some “fancy quotes” and zero\u200Bwidth\u200Bspaces"
    rendered_msg = 'here: are some "fancy quotes" and zerowidthspaces'

    mocker.patch(
        "app.service_api_client.get_service_template",
        return_value={"data": template_json(service_one["id"], fake_uuid, type_="sms", content=msg)},
    )

    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert rendered_msg in page.text


def test_should_show_page_template_with_priority_select_if_platform_admin(
    platform_admin_client,
    platform_admin_user,
    mocker,
    mock_get_service_template,
    service_one,
    fake_uuid,
):
    mocker.patch("app.user_api_client.get_users_for_service", return_value=[platform_admin_user])
    template_id = fake_uuid
    response = platform_admin_client.get(
        url_for(
            ".edit_service_template",
            service_id=service_one["id"],
            template_id=template_id,
        )
    )

    assert response.status_code == 200
    assert "Two week reminder" in response.get_data(as_text=True)
    assert "Template &lt;em&gt;content&lt;/em&gt; with &amp; entity" in response.get_data(as_text=True)
    assert "Choose a priority queue" in response.get_data(as_text=True)
    mock_get_service_template.assert_called_with(service_one["id"], template_id, None)


@pytest.mark.parametrize("filetype", ["pdf", "png"])
@pytest.mark.parametrize(
    "view, extra_view_args",
    [
        (".view_letter_template_preview", {}),
        (".view_template_version_preview", {"version": 1}),
    ],
)
def test_should_show_preview_letter_templates(
    view,
    extra_view_args,
    filetype,
    logged_in_client,
    mock_get_service_email_template,
    service_one,
    fake_uuid,
    mocker,
):
    mocked_preview = mocker.patch(
        "app.main.views.templates.TemplatePreview.from_database_object",
        return_value="foo",
    )

    service_id, template_id = service_one["id"], fake_uuid

    response = logged_in_client.get(
        url_for(
            view,
            service_id=service_id,
            template_id=template_id,
            filetype=filetype,
            **extra_view_args,
        )
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "foo"
    mock_get_service_email_template.assert_called_with(service_id, template_id, extra_view_args.get("version"))
    assert mocked_preview.call_args[0][0]["id"] == template_id
    assert mocked_preview.call_args[0][0]["service"] == service_id
    assert mocked_preview.call_args[0][1] == filetype


def test_dont_show_preview_letter_templates_for_bad_filetype(logged_in_client, mock_get_service_template, service_one, fake_uuid):
    resp = logged_in_client.get(
        url_for(
            ".view_letter_template_preview",
            service_id=service_one["id"],
            template_id=fake_uuid,
            filetype="blah",
        )
    )
    assert resp.status_code == 404
    assert mock_get_service_template.called is False


@pytest.mark.parametrize("original_filename, new_filename", [("geo", "geo"), ("no-branding", None)])
def test_letter_branding_preview_image(
    mocker,
    platform_admin_client,
    original_filename,
    new_filename,
):
    mocked_preview = mocker.patch(
        "app.main.views.templates.TemplatePreview.from_example_template",
        return_value="foo",
    )
    resp = platform_admin_client.get(url_for(".letter_branding_preview_image", filename=original_filename))

    mocked_preview.assert_called_with(ANY, new_filename)
    assert resp.get_data(as_text=True) == "foo"


def test_choose_a_template_to_copy(
    client_request,
    mock_get_service_templates,
    mock_get_template_folders,
    mock_get_just_services_for_user,
):
    page = client_request.get(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
    )

    assert page.select(".folder-heading") == []

    expected = [
        ("Service 1 " "6 templates"),
        ("Service 1 sms_template_one " "Text message template"),
        ("Service 1 sms_template_two " "Text message template"),
        ("Service 1 email_template_one " "Email template"),
        ("Service 1 email_template_two " "Email template"),
        ("Service 1 letter_template_one " "Letter template"),
        ("Service 1 letter_template_two " "Letter template"),
        ("Service 2 " "6 templates"),
        ("Service 2 sms_template_one " "Text message template"),
        ("Service 2 sms_template_two " "Text message template"),
        ("Service 2 email_template_one " "Email template"),
        ("Service 2 email_template_two " "Email template"),
        ("Service 2 letter_template_one " "Letter template"),
        ("Service 2 letter_template_two " "Letter template"),
    ]
    actual = page.select(".template-list-item")

    assert len(actual) == len(expected)

    for actual, expected in zip(actual, expected):
        assert normalize_spaces(actual.text) == expected

    links = page.select("main nav a")
    assert links[0]["href"] == url_for(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_service=SERVICE_TWO_ID,
    )
    assert links[1]["href"] == url_for(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_service=SERVICE_TWO_ID,
    )
    assert links[2]["href"] == url_for(
        "main.copy_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        from_service=SERVICE_TWO_ID,
    )


def test_choose_a_template_to_copy_when_user_has_one_service(
    client_request,
    mock_get_service_templates,
    mock_get_template_folders,
    mock_get_empty_organisations_and_one_service_for_user,
):
    page = client_request.get(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
    )

    assert page.select(".folder-heading") == []

    expected = [
        ("sms_template_one " "Text message template"),
        ("sms_template_two " "Text message template"),
        ("email_template_one " "Email template"),
        ("email_template_two " "Email template"),
        ("letter_template_one " "Letter template"),
        ("letter_template_two " "Letter template"),
    ]
    actual = page.select(".template-list-item")

    assert len(actual) == len(expected)

    for actual, expected in zip(actual, expected):
        assert normalize_spaces(actual.text) == expected

    assert page.select("main nav a")[0]["href"] == url_for(
        "main.copy_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        from_service=SERVICE_TWO_ID,
    )


def test_choose_a_template_to_copy_from_folder_within_service(
    mocker,
    client_request,
    mock_get_template_folders,
    mock_get_non_empty_organisations_and_services_for_user,
):
    mock_get_template_folders.return_value = [
        _folder("Parent folder", PARENT_FOLDER_ID),
        _folder("Child folder empty", CHILD_FOLDER_ID, parent=PARENT_FOLDER_ID),
        _folder("Child folder non-empty", FOLDER_TWO_ID, parent=PARENT_FOLDER_ID),
    ]
    mocker.patch(
        "app.service_api_client.get_service_templates",
        return_value={
            "data": [
                _template(
                    "sms",
                    "Should not appear in list (at service root)",
                ),
                _template(
                    "sms",
                    "Should appear in list (at same level)",
                    parent=PARENT_FOLDER_ID,
                ),
                _template(
                    "sms",
                    "Should appear in list (nested)",
                    parent=FOLDER_TWO_ID,
                    template_id=TEMPLATE_ONE_ID,
                ),
            ]
        },
    )
    page = client_request.get(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_service=SERVICE_ONE_ID,
        from_folder=PARENT_FOLDER_ID,
    )

    assert normalize_spaces(page.select_one(".folder-heading").text) == ("service one Parent folder")
    breadcrumb_links = page.select(".folder-heading a")
    assert len(breadcrumb_links) == 1
    assert breadcrumb_links[0]["href"] == url_for(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_service=SERVICE_ONE_ID,
    )

    expected = [
        ("Child folder empty " "Empty"),
        ("Child folder non-empty " "1 template"),
        ("Child folder non-empty Should appear in list (nested) " "Text message template"),
        ("Should appear in list (at same level) " "Text message template"),
    ]
    actual = page.select(".template-list-item")

    assert len(actual) == len(expected)

    for actual, expected in zip(actual, expected):
        assert normalize_spaces(actual.text) == expected

    links = page.select("main nav#template-list a")
    assert links[0]["href"] == url_for(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_service=SERVICE_ONE_ID,
        from_folder=CHILD_FOLDER_ID,
    )
    assert links[1]["href"] == url_for(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_service=SERVICE_ONE_ID,
        from_folder=FOLDER_TWO_ID,
    )
    assert links[2]["href"] == url_for(
        "main.choose_template_to_copy",
        service_id=SERVICE_ONE_ID,
        from_folder=FOLDER_TWO_ID,
    )
    assert links[3]["href"] == url_for(
        "main.copy_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        from_service=SERVICE_ONE_ID,
    )


@pytest.mark.parametrize(
    "existing_template_names, expected_name",
    (
        (["Two week reminder"], "Two week reminder (copy)"),
        (["Two week reminder (copy)"], "Two week reminder (copy 2)"),
        (
            ["Two week reminder", "Two week reminder (copy)"],
            "Two week reminder (copy 2)",
        ),
        (
            ["Two week reminder (copy 8)", "Two week reminder (copy 9)"],
            "Two week reminder (copy 10)",
        ),
        (
            ["Two week reminder (copy)", "Two week reminder (copy 9)"],
            "Two week reminder (copy 10)",
        ),
        (
            ["Two week reminder (copy)", "Two week reminder (copy 10)"],
            "Two week reminder (copy 2)",
        ),
    ),
)
def test_load_edit_template_with_copy_of_template(
    client_request,
    active_user_with_permission_to_two_services,
    mock_get_service_templates,
    mock_get_service_email_template,
    mock_get_non_empty_organisations_and_services_for_user,
    existing_template_names,
    expected_name,
):
    mock_get_service_templates.side_effect = lambda service_id: {
        "data": [{"name": existing_template_name, "template_type": "sms"} for existing_template_name in existing_template_names]
    }
    client_request.login(active_user_with_permission_to_two_services)
    page = client_request.get(
        "main.copy_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        from_service=SERVICE_TWO_ID,
    )

    assert page.select_one("form")["method"] == "post"

    assert page.select_one("input")["value"] == (expected_name)
    assert page.select_one("textarea").text == ("\r\nYour ((thing)) is due soon")
    mock_get_service_email_template.assert_called_once_with(
        SERVICE_TWO_ID,
        TEMPLATE_ONE_ID,
    )


def test_copy_template_loads_template_from_within_subfolder(
    client_request,
    active_user_with_permission_to_two_services,
    mock_get_service_templates,
    mock_get_non_empty_organisations_and_services_for_user,
    mocker,
):
    template = template_json(SERVICE_TWO_ID, TEMPLATE_ONE_ID, name="foo", folder=PARENT_FOLDER_ID)

    mock_get_service_template = mocker.patch("app.service_api_client.get_service_template", return_value={"data": template})
    mock_get_template_folder = mocker.patch(
        "app.template_folder_api_client.get_template_folder",
        return_value=_folder("Parent folder", PARENT_FOLDER_ID),
    )
    client_request.login(active_user_with_permission_to_two_services)

    page = client_request.get(
        "main.copy_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        from_service=SERVICE_TWO_ID,
    )

    assert page.select_one("input")["value"] == "foo (copy)"
    mock_get_service_template.assert_called_once_with(SERVICE_TWO_ID, TEMPLATE_ONE_ID)
    mock_get_template_folder.assert_called_once_with(SERVICE_TWO_ID, PARENT_FOLDER_ID)


def test_cant_copy_template_from_non_member_service(
    client_request,
    mock_get_service_email_template,
    mock_get_organisations_and_services_for_user,
):
    client_request.get(
        "main.copy_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        from_service=SERVICE_TWO_ID,
        _expected_status=403,
    )
    assert mock_get_service_email_template.call_args_list == []


@pytest.mark.parametrize(
    "endpoint, data, expected_error",
    (
        (
            "main.create_template",
            {
                "what_type": "email",
            },
            "Sending emails has been disabled for your service.",
        ),
        (
            "main.create_template",
            {
                "what_type": "sms",
            },
            "Sending text messages has been disabled for your service.",
        ),
    ),
)
def test_should_not_allow_creation_of_template_through_form_without_correct_permission(
    client_request: ClientRequest,
    service_one: Service,
    mock_get_service_templates,
    mock_get_template_folders,
    endpoint,
    data,
    expected_error,
):
    service_one["permissions"] = []
    page = client_request.post(
        endpoint,
        service_id=SERVICE_ONE_ID,
        _data=data,
        _follow_redirects=True,
    )
    assert normalize_spaces(page.select("main p")[0].text) == expected_error
    assert page.select(".back-link")[0].text == "Back"
    assert page.select(".back-link")[0]["href"] == url_for(
        ".choose_template",
        service_id=SERVICE_ONE_ID,
        template_id="0",
    )


@pytest.mark.parametrize("type_of_template", ["email", "sms"])
def test_should_not_allow_creation_of_a_template_without_correct_permission(
    client_request,
    service_one,
    mocker,
    type_of_template,
):
    service_one["permissions"] = []
    template_description = {"sms": "text messages", "email": "emails"}

    page = client_request.get(
        ".add_service_template",
        service_id=SERVICE_ONE_ID,
        template_type=type_of_template,
        _follow_redirects=True,
    )
    assert page.select("main p")[0].text.strip() == "Sending {} has been disabled for your service.".format(
        template_description[type_of_template]
    )
    assert page.select(".back-link")[0].text == "Back"
    assert page.select(".back-link")[0]["href"] == url_for(
        ".choose_template",
        service_id=service_one["id"],
        template_id="0",
    )


@pytest.mark.parametrize(
    "template_data,  expected_status_code",
    [
        (create_email_template(), 200),
        (create_sms_template(), 200),
        (create_letter_template(), 302),
    ],
)
def test_should_redirect_to_one_off_if_template_type_is_letter(
    client_request,
    multiple_reply_to_email_addresses,
    multiple_sms_senders,
    fake_uuid,
    mocker,
    template_data,
    expected_status_code,
):
    mocker.patch("app.service_api_client.get_service_template", return_value=template_data)

    client_request.get(
        ".set_sender",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _expected_status=expected_status_code,
    )


def test_should_redirect_when_saving_a_template(
    client_request,
    mock_get_service_template,
    mock_update_service_template,
    fake_uuid,
):
    name = "new name"
    content = "template <em>content</em> with & entity"
    page = client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "id": fake_uuid,
            "name": name,
            "template_content": content,
            "template_type": "sms",
            "service": SERVICE_ONE_ID,
            "process_type": "normal",
        },
        _follow_redirects=True,
    )

    flash_banner = page.select_one(".banner-default-with-tick").string.strip()
    assert flash_banner == f"'{name}' template saved"

    mock_update_service_template.assert_called_with(
        fake_uuid,
        name,
        "sms",
        content,
        SERVICE_ONE_ID,
        None,
        "normal",
    )


@pytest.mark.parametrize("process_type", ["bulk", "priority"])
def test_should_edit_content_when_process_type_is_set_not_platform_admin(
    client_request,
    mocker,
    mock_update_service_template,
    fake_uuid,
    process_type,
):
    mock_get_service_template_with_process_type(mocker, process_type)
    client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "id": fake_uuid,
            "name": "new name",
            "template_content": "new template <em>content</em> with & entity",
            "template_type": "sms",
            "service": SERVICE_ONE_ID,
            "process_type": process_type,
            "button_pressed": "save",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".view_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )
    mock_update_service_template.assert_called_with(
        fake_uuid,
        "new name",
        "sms",
        "new template <em>content</em> with & entity",
        SERVICE_ONE_ID,
        None,
        process_type,
    )


def test_should_not_allow_template_edits_without_correct_permission(
    client_request,
    mock_get_service_template,
    service_one,
    fake_uuid,
):
    service_one["permissions"] = ["email"]

    page = client_request.get(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _follow_redirects=True,
    )

    assert page.select("main p")[0].text.strip() == "Sending text messages has been disabled for your service."
    assert page.select(".back-link")[0].text == "Back"
    assert page.select(".back-link")[0]["href"] == url_for(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
    )


@pytest.mark.parametrize("process_type", ["bulk", "priority"])
def test_should_403_when_edit_template_with_non_default_process_type_for_non_platform_admin(
    client,
    active_user_with_permissions,
    mocker,
    mock_get_service_template,
    mock_update_service_template,
    fake_uuid,
    process_type,
    service_one,
):
    service = service_one
    client.login(active_user_with_permissions, mocker, service)
    mocker.patch(
        "app.user_api_client.get_users_for_service",
        return_value=[active_user_with_permissions],
    )
    template_id = fake_uuid
    data = {
        "id": template_id,
        "name": "new name",
        "template_content": "template <em>content</em> with & entity",
        "template_type": "sms",
        "service": service["id"],
        "process_type": process_type,
    }
    response = client.post(
        url_for(".edit_service_template", service_id=service["id"], template_id=template_id),
        data=data,
    )
    assert response.status_code == 403
    mock_update_service_template.called == 0


@pytest.mark.parametrize("process_type", ["bulk", "priority"])
def test_should_403_when_create_template_with_non_default_process_type_for_non_platform_admin(
    client,
    active_user_with_permissions,
    mocker,
    mock_get_service_template,
    mock_update_service_template,
    fake_uuid,
    process_type,
    service_one,
):
    service = service_one
    client.login(active_user_with_permissions, mocker, service)
    mocker.patch(
        "app.user_api_client.get_users_for_service",
        return_value=[active_user_with_permissions],
    )
    template_id = fake_uuid
    data = {
        "id": template_id,
        "name": "new name",
        "template_content": "template <em>content</em> with & entity",
        "template_type": "sms",
        "service": service["id"],
        "process_type": process_type,
    }
    response = client.post(
        url_for(".add_service_template", service_id=service["id"], template_type="sms"),
        data=data,
    )
    assert response.status_code == 403
    mock_update_service_template.called == 0


@pytest.mark.parametrize(
    "template_data, template_type, expected_paragraphs",
    [
        (
            create_email_template(),
            "email",
            [
                "You removed ((date))",
                "You added ((name))",
                "When you send messages using this template you’ll need 3 columns of data:",
            ],
        ),
        (
            create_letter_template_with_variables(),
            "letter",
            [
                "You removed ((date))",
                "You added ((name))",
                "When you send messages using this template you’ll need 9 columns of data:",
            ],
        ),
    ],
)
def test_should_show_interstitial_when_making_breaking_change(
    client_request,
    mock_update_service_template,
    mock_get_user_by_email,
    fake_uuid,
    mocker,
    template_data,
    template_type,
    expected_paragraphs,
):

    mocker.patch("app.service_api_client.get_service_template", return_value=template_data)

    data = {
        "id": template_data["data"]["id"],
        "name": "new name",
        "template_content": "hello lets talk about ((thing))",
        "template_type": template_type,
        "subject": "reminder '\" <span> & ((name))",
        "service": SERVICE_ONE_ID,
        "process_type": "normal",
    }

    if template_type == "letter":
        data["postage"] = "None"

    page = client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=template_data["data"]["id"],
        _data=data,
        _expected_status=200,
    )

    assert page.h1.string.strip() == "Confirm changes"
    assert page.find("a", {"class": "back-link"})["href"] == url_for(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=template_data["data"]["id"],
    )
    for index, p in enumerate(expected_paragraphs):
        assert normalize_spaces(page.select("main p")[index].text) == p

    for key, value in {
        "name": "new name",
        "subject": "reminder '\" <span> & ((name))",
        "template_content": "hello lets talk about ((thing))",
        "confirm": "true",
    }.items():
        assert page.find("input", {"name": key})["value"] == value

    # BeautifulSoup returns the value attribute as unencoded, let’s make
    # sure that it is properly encoded in the HTML
    assert str(page.find("input", {"name": "subject"})) == (
        """<input name="subject" type="hidden" value="reminder '&quot; &lt;span&gt; &amp; ((name))"/>"""
    )


def test_removing_placeholders_is_not_a_breaking_change(
    client_request,
    mock_get_service_email_template,
    mock_update_service_template,
    fake_uuid,
):
    existing_template = mock_get_service_email_template(0, 0)["data"]
    client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "name": existing_template["name"],
            "template_content": "no placeholders",
            "subject": existing_template["subject"],
            "button_pressed": "save",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            "main.view_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )
    assert mock_update_service_template.called is True


def test_should_not_create_too_big_template(
    client_request,
    mock_get_service_template,
    mock_create_service_template_content_too_big,
    fake_uuid,
):
    page = client_request.post(
        ".add_service_template",
        service_id=SERVICE_ONE_ID,
        template_type="sms",
        _data={
            "name": "new name",
            "template_content": "template content",
            "template_type": "sms",
            "service": SERVICE_ONE_ID,
            "process_type": "normal",
        },
        _expected_status=200,
    )
    assert "Content has a character count greater than the limit of 459" in page.text


def test_should_not_update_too_big_template(
    client_request,
    mock_get_service_template,
    mock_update_service_template_400_content_too_big,
    fake_uuid,
):
    page = client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "id": fake_uuid,
            "name": "new name",
            "template_content": "template content",
            "service": SERVICE_ONE_ID,
            "template_type": "sms",
            "process_type": "normal",
        },
        _expected_status=200,
    )
    assert "Content has a character count greater than the limit of 459" in page.text


def test_should_redirect_when_saving_a_template_email(
    client_request,
    mock_get_service_email_template,
    mock_update_service_template,
    mock_get_user_by_email,
    fake_uuid,
):
    name = "new name"
    content = "template <em>content</em> with & entity ((thing)) ((date))"
    subject = "subject & entity"
    client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "id": fake_uuid,
            "name": name,
            "template_content": content,
            "template_type": "email",
            "service": SERVICE_ONE_ID,
            "subject": subject,
            "process_type": "normal",
            "button_pressed": "save",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".view_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )
    mock_update_service_template.assert_called_with(
        fake_uuid,
        name,
        "email",
        content,
        SERVICE_ONE_ID,
        subject,
        "normal",
    )


def test_should_redirect_when_previewing_a_template_email(
    client_request,
    mock_get_service_email_template,
    mock_update_service_template,
    mock_get_user_by_email,
    fake_uuid,
):
    name = "new name"
    content = "template <em>content</em> with & entity ((thing)) ((date))"
    subject = "subject & entity"
    client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "id": fake_uuid,
            "name": name,
            "template_content": content,
            "template_type": "email",
            "service": SERVICE_ONE_ID,
            "subject": subject,
            "process_type": "normal",
            "button_pressed": "preview",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".preview_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )


def test_preview_page_contains_preview(
    client_request, app_, mock_get_service_email_template, mock_get_user_by_email, fake_uuid, mocker
):
    preview_data = {
        "name": "test name",
        "subject": "test subject",
        "content": "test content",
        "template_type": "email",
        "id": fake_uuid,
    }
    mocker.patch(
        "app.main.views.templates.get_preview_data",
        return_value=preview_data,
    )

    page = client_request.get(
        ".preview_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert "test name" in page.text
    assert "test subject" in page.text
    assert "test content" in page.text

    email_body = str(page.select_one(".email-message-body"))
    assert f"https://{app_.config['ASSET_DOMAIN']}/gc-logo-en.png" in email_body
    assert f"https://{app_.config['ASSET_DOMAIN']}/canada-logo.png" in email_body


def test_preview_edit_button_should_redirect_to_edit_page(
    client_request, mock_get_service_email_template, mock_get_user_by_email, fake_uuid, mocker
):
    preview_data = {
        "name": "template 1",
        "content": "hi there",
        "subject": "test subject",
        "template_type": "email",
        "id": fake_uuid,
    }
    mocker.patch(
        "app.main.views.templates.get_preview_data",
        return_value=preview_data,
    )

    client_request.post(
        ".preview_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "button_pressed": "edit",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".edit_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )


def test_preview_edit_button_should_redirect_to_add_page(
    client_request, mock_get_service_email_template, mock_get_user_by_email, fake_uuid, mocker
):
    preview_data = {
        "name": "template 1",
        "content": "hi there",
        "subject": "test subject",
        "template_type": "email",
        "folder": "",
        "id": None,
    }
    mocker.patch(
        "app.main.views.templates.get_preview_data",
        return_value=preview_data,
    )

    client_request.post(
        ".preview_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "button_pressed": "edit",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".add_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=None,
            template_type="email",
            template_folder_id="",
            _external=True,
        ),
    )


@pytest.mark.parametrize("id", (sample_uuid(), None))
def test_preview_has_correct_back_link(
    id, client_request, app_, mock_get_service_email_template, mock_get_user_by_email, fake_uuid, mocker
):
    preview_data = {
        "name": "test name",
        "subject": "test subject",
        "content": "test content",
        "template_type": "email",
        "folder": "",
        "id": id,
    }
    mocker.patch(
        "app.main.views.templates.get_preview_data",
        return_value=preview_data,
    )

    page = client_request.get(
        ".preview_template",
        service_id=SERVICE_ONE_ID,
        template_id=id,
        _test_page_title=False,
    )

    expected_back_url = (
        url_for(
            ".edit_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=id,
        )
        if id
        else url_for(
            ".add_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=id,
            template_type="email",
            template_folder_id="",
        )
    )
    assert page.select(".back-link")[0]["href"] == expected_back_url


def test_preview_should_update_and_redirect_on_save(client_request, mock_update_service_template, fake_uuid, mocker):
    preview_data = {
        "name": "test name",
        "content": "test content",
        "subject": "test subject",
        "template_type": "email",
        "process_type": "normal",
        "id": fake_uuid,
    }
    mocker.patch(
        "app.main.views.templates.get_preview_data",
        return_value=preview_data,
    )

    client_request.post(
        ".preview_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "button_pressed": "save",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".view_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )
    mock_update_service_template.assert_called_with(
        fake_uuid, "test name", "email", "test content", SERVICE_ONE_ID, "test subject", "normal"
    )


def test_preview_should_create_and_redirect_on_save(client_request, mock_create_service_template, fake_uuid, mocker):
    preview_data = {
        "name": "test name",
        "content": "test content",
        "subject": "test subject",
        "template_type": "email",
        "process_type": "normal",
        "folder": None,
    }
    mocker.patch(
        "app.main.views.templates.get_preview_data",
        return_value=preview_data,
    )

    client_request.post(
        ".preview_template",
        service_id=SERVICE_ONE_ID,
        _data={
            "button_pressed": "save",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".view_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _external=True,
        ),
    )
    mock_create_service_template.assert_called_with(
        "test name", "email", "test content", SERVICE_ONE_ID, "test subject", "normal", None
    )


def test_should_show_delete_template_page_with_time_block(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    mocker,
    fake_uuid,
):
    with freeze_time("2012-01-01 12:00:00"):
        template = template_json("1234", "1234", "Test template", "sms", "Something very interesting")
        notification = single_notification_json("1234", template=template)

        mocker.patch(
            "app.template_statistics_client.get_template_statistics_for_template",
            return_value=notification,
        )

    with freeze_time("2012-01-01 12:10:00"):
        page = client_request.get(
            ".delete_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _test_page_title=False,
        )
    assert "Are you sure you want to delete ‘Two week reminder’?" in page.select(".banner-dangerous")[0].text
    assert normalize_spaces(page.select(".banner-dangerous p")[0].text) == ("This template was last used 10 minutes ago.")
    assert normalize_spaces(page.select(".sms-message-wrapper")[0].text) == (
        "service one: Template <em>content</em> with & entity"
    )
    mock_get_service_template.assert_called_with(SERVICE_ONE_ID, fake_uuid, None)


def test_should_show_delete_template_page_with_time_block_for_empty_notification(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    mocker,
    fake_uuid,
):
    with freeze_time("2012-01-08 12:00:00"):
        template = template_json("1234", "1234", "Test template", "sms", "Something very interesting")
        single_notification_json("1234", template=template)
        mocker.patch(
            "app.template_statistics_client.get_template_statistics_for_template",
            return_value=None,
        )

    with freeze_time("2012-01-01 11:00:00"):
        page = client_request.get(
            ".delete_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
            _test_page_title=False,
        )
    assert "Are you sure you want to delete ‘Two week reminder’?" in page.select(".banner-dangerous")[0].text
    assert normalize_spaces(page.select(".banner-dangerous p")[0].text) == (
        "This template was last used more than seven days ago."
    )
    assert normalize_spaces(page.select(".sms-message-wrapper")[0].text) == (
        "service one: Template <em>content</em> with & entity"
    )
    mock_get_service_template.assert_called_with(SERVICE_ONE_ID, fake_uuid, None)


def test_should_show_delete_template_page_with_never_used_block(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    fake_uuid,
    mocker,
):
    mocker.patch(
        "app.template_statistics_client.get_template_statistics_for_template",
        side_effect=HTTPError(response=Mock(status_code=404), message="Default message"),
    )
    page = client_request.get(
        ".delete_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )
    assert "Are you sure you want to delete ‘Two week reminder’?" in page.select(".banner-dangerous")[0].text
    assert not page.select(".banner-dangerous p")
    assert normalize_spaces(page.select(".sms-message-wrapper")[0].text) == (
        "service one: Template <em>content</em> with & entity"
    )
    mock_get_service_template.assert_called_with(SERVICE_ONE_ID, fake_uuid, None)


@pytest.mark.parametrize("parent", (PARENT_FOLDER_ID, None))
def test_should_redirect_when_deleting_a_template(
    mocker,
    client_request,
    mock_delete_service_template,
    mock_get_template_folders,
    parent,
):

    mock_get_template_folders.return_value = [
        {
            "id": PARENT_FOLDER_ID,
            "name": "Folder",
            "parent": None,
            "users_with_permission": [ANY],
        }
    ]
    mock_get_service_template = mocker.patch(
        "app.service_api_client.get_service_template",
        return_value={
            "data": _template(
                "sms",
                "Hello",
                parent=parent,
            )
        },
    )

    client_request.post(
        ".delete_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=TEMPLATE_ONE_ID,
        _expected_status=302,
        _expected_redirect=url_for(
            ".choose_template",
            service_id=SERVICE_ONE_ID,
            template_folder_id=parent,
            _external=True,
        ),
    )

    mock_get_service_template.assert_called_with(SERVICE_ONE_ID, TEMPLATE_ONE_ID, None)
    mock_delete_service_template.assert_called_with(SERVICE_ONE_ID, TEMPLATE_ONE_ID)


@freeze_time("2016-01-01T15:00")
def test_should_show_page_for_a_deleted_template(
    client_request,
    mock_get_template_folders,
    mock_get_deleted_template,
    single_letter_contact_block,
    mock_get_user,
    mock_get_user_by_email,
    mock_has_permissions,
    fake_uuid,
):
    template_id = fake_uuid
    page = client_request.get(
        ".view_template",
        service_id=SERVICE_ONE_ID,
        template_id=template_id,
        _test_page_title=False,
    )

    content = str(page)
    assert (
        url_for(
            "main.edit_service_template",
            service_id=SERVICE_ONE_ID,
            template_id=fake_uuid,
        )
        not in content
    )
    assert url_for("main.send_test", service_id=SERVICE_ONE_ID, template_id=fake_uuid) not in content
    assert page.select("p.hint")[0].text.strip() == "This template was deleted 2016-01-01 15:00:00.000000."
    assert "Delete this template" not in page.select_one("main").text

    mock_get_deleted_template.assert_called_with(SERVICE_ONE_ID, template_id, None)


@pytest.mark.parametrize(
    "route",
    [
        "main.create_template",
        "main.add_service_template",
        "main.edit_service_template",
        "main.delete_service_template",
    ],
)
def test_route_permissions(
    route,
    mocker,
    app_,
    client,
    api_user_active,
    service_one,
    mock_get_service_template,
    mock_get_template_folders,
    mock_get_template_statistics_for_template,
    fake_uuid,
):
    validate_route_permission(
        mocker,
        app_,
        "GET",
        200,
        url_for(
            route,
            service_id=service_one["id"],
            template_type="sms",
            template_id=fake_uuid,
        ),
        ["manage_templates"],
        api_user_active,
        service_one,
    )


def test_route_permissions_for_choose_template(
    mocker,
    app_,
    client,
    api_user_active,
    mock_get_template_folders,
    service_one,
    mock_get_service_templates,
):
    mocker.patch("app.job_api_client.get_job")
    validate_route_permission(
        mocker,
        app_,
        "GET",
        200,
        url_for(
            "main.choose_template",
            service_id=service_one["id"],
        ),
        [],
        api_user_active,
        service_one,
    )


@pytest.mark.parametrize(
    "route",
    [
        "main.create_template",
        "main.add_service_template",
        "main.edit_service_template",
        "main.delete_service_template",
    ],
)
def test_route_invalid_permissions(
    route,
    mocker,
    app_,
    client,
    api_user_active,
    service_one,
    mock_get_service_template,
    mock_get_template_statistics_for_template,
    fake_uuid,
):
    validate_route_permission(
        mocker,
        app_,
        "GET",
        403,
        url_for(
            route,
            service_id=service_one["id"],
            template_type="sms",
            template_id=fake_uuid,
        ),
        ["view_activity"],
        api_user_active,
        service_one,
    )


@pytest.mark.parametrize(
    "from_time, until_time, message",
    [
        (
            datetime(2000, 1, 1, 12, 0),
            datetime(2000, 1, 1, 12, 0, 59),
            "under a minute",
        ),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 1, 12, 1), "1 minute"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 1, 12, 2, 35), "2 minutes"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 1, 12, 59), "59 minutes"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 1, 13, 0), "1 hour"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 1, 14, 0), "2 hours"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 2, 11, 59), "23 hours"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 2, 12, 0), "1 day"),
        (datetime(2000, 1, 1, 12, 0), datetime(2000, 1, 3, 14, 0), "2 days"),
    ],
)
def test_get_human_readable_delta(from_time, until_time, message):
    assert get_human_readable_delta(from_time, until_time) == message


def test_can_create_email_template_with_emoji(
    client_request,
    mock_create_service_template,
    mock_get_template_folders,
    mock_get_service_template_when_no_template_exists,
):
    page = client_request.post(
        ".add_service_template",
        service_id=SERVICE_ONE_ID,
        template_type="email",
        _data={
            "name": "new name",
            "subject": "Food incoming!",
            "template_content": "here's a burrito 🌯",
            "template_type": "email",
            "service": SERVICE_ONE_ID,
            "process_type": "normal",
            "button_pressed": "save",
        },
        _follow_redirects=True,
    )
    assert mock_create_service_template.called is True

    flash_banner = page.select_one(".banner-default-with-tick").string.strip()
    assert flash_banner == "'new name' template saved"


def test_should_not_create_sms_template_with_emoji(
    client_request,
    service_one,
    mock_create_service_template,
):
    page = client_request.post(
        ".add_service_template",
        service_id=SERVICE_ONE_ID,
        template_type="sms",
        _data={
            "name": "new name",
            "template_content": "here are some noodles 🍜",
            "template_type": "sms",
            "service": SERVICE_ONE_ID,
            "process_type": "normal",
        },
        _expected_status=200,
    )
    assert "You can’t use 🍜 in text messages." in page.text
    assert mock_create_service_template.called is False


def test_should_not_update_sms_template_with_emoji(
    client_request,
    mock_get_service_template,
    mock_update_service_template,
    fake_uuid,
):
    page = client_request.post(
        ".edit_service_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data={
            "id": fake_uuid,
            "name": "new name",
            "template_content": "here's a burger 🍔",
            "service": SERVICE_ONE_ID,
            "template_type": "sms",
            "process_type": "normal",
        },
        _expected_status=200,
    )
    assert "You can’t use 🍔 in text messages." in page.text
    assert mock_update_service_template.called is False


def test_should_create_sms_template_without_downgrading_unicode_characters(client_request, mock_create_service_template):
    msg = "here:\tare some “fancy quotes” and non\u200Bbreaking\u200Bspaces"

    client_request.post(
        ".add_service_template",
        service_id=SERVICE_ONE_ID,
        template_type="sms",
        _data={
            "name": "new name",
            "template_content": msg,
            "template_type": "sms",
            "service": SERVICE_ONE_ID,
            "process_type": "normal",
        },
        expected_status=302,
    )

    mock_create_service_template.assert_called_with(
        ANY,  # name
        ANY,  # type
        msg,  # content
        ANY,  # service_id
        ANY,  # subject
        ANY,  # process_type
        ANY,  # parent_folder_id
    )


def test_should_show_message_before_redacting_template(
    client_request,
    mock_get_service_template,
    service_one,
    fake_uuid,
):

    page = client_request.get(
        "main.redact_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert ("Are you sure you want to redact personalised variable content?") in page.select(".banner-dangerous")[0].text

    form = page.select(".banner-dangerous form")[0]

    assert "action" not in form
    assert form["method"] == "post"


def test_should_show_redact_template(
    client_request,
    mock_get_service_template,
    mock_get_template_folders,
    mock_redact_template,
    single_letter_contact_block,
    service_one,
    fake_uuid,
):

    page = client_request.post(
        "main.redact_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _follow_redirects=True,
    )

    assert normalize_spaces(page.select(".banner-default-with-tick")[0].text) == (
        "Personalised content will be hidden for messages sent with this template"
    )

    mock_redact_template.assert_called_once_with(SERVICE_ONE_ID, fake_uuid)


def test_should_show_hint_once_template_redacted(
    client_request,
    mocker,
    service_one,
    mock_get_template_folders,
    fake_uuid,
):

    template = create_template(redact_personalisation=True)
    mocker.patch("app.service_api_client.get_service_template", return_value=template)

    page = client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=template["data"]["id"],
        _test_page_title=False,
    )

    assert page.select(".hint")[0].text.strip() == "Recipients' information will be redacted from system"


def test_should_not_show_redaction_stuff_for_letters(
    client_request,
    mocker,
    fake_uuid,
    mock_get_service_letter_template,
    mock_get_template_folders,
    single_letter_contact_block,
):

    mocker.patch("app.main.views.templates.get_page_count_for_letter", return_value=1)

    page = client_request.get(
        "main.view_template",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _test_page_title=False,
    )

    assert page.select(".hint") == []
    assert "personalisation" not in " ".join(link.text.lower() for link in page.select("a"))


def test_set_template_sender(
    client_request,
    fake_uuid,
    mock_update_service_template_sender,
    mock_get_service_letter_template,
    single_letter_contact_block,
):
    data = {
        "sender": "1234",
    }

    client_request.post(
        "main.set_template_sender",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
        _data=data,
    )

    mock_update_service_template_sender.assert_called_once_with(
        SERVICE_ONE_ID,
        fake_uuid,
        "1234",
    )


@pytest.mark.parametrize(
    "data",
    [
        [],
        [create_letter_contact_block()],
    ],
)
def test_add_sender_link_only_appears_on_services_with_no_senders(
    client_request,
    fake_uuid,
    mocker,
    data,
    mock_get_service_letter_template,
    no_letter_contact_blocks,
):
    mocker.patch("app.service_api_client.get_letter_contacts", return_value=data)

    page = client_request.get(
        "main.set_template_sender",
        service_id=SERVICE_ONE_ID,
        template_id=fake_uuid,
    )

    assert page.select_one(".md\\:w-3\\/4 form > a")["href"] == url_for(
        "main.service_add_letter_contact",
        service_id=SERVICE_ONE_ID,
        from_template=fake_uuid,
    )


@pytest.mark.parametrize(
    "template_data",
    [
        create_email_template(),
        create_sms_template(),
    ],
)
def test_add_recipients_redirects_many_recipients(template_data, client_request, mocker):
    mocker.patch("app.service_api_client.get_service_template", return_value=template_data)

    template_id = fake_uuid

    client_request.post(
        "main.add_recipients",
        service_id=SERVICE_ONE_ID,
        template_id=template_id,
        _data={
            "what_type": "many_recipients",
        },
        _expected_status=302,
        _expected_redirect=url_for(
            ".send_messages",
            service_id=SERVICE_ONE_ID,
            template_id=template_id,
            _external=True,
        ),
    )


@pytest.mark.parametrize(
    "template_type, template_data",
    [
        ("email", create_email_template()),
        ("sms", create_sms_template()),
    ],
)
def test_add_recipients_redirects_one_recipient(template_type, template_data, client_request, fake_uuid, mocker):
    mocker.patch("app.service_api_client.get_service_template", return_value=template_data)

    template_id = fake_uuid
    with client_request.session_transaction() as session:
        session["placeholders"] = {}
    recipient = "test@cds-snc.ca" if template_type == "email" else "6135555555"

    client_request.post(
        "main.add_recipients",
        service_id=SERVICE_ONE_ID,
        template_id=template_id,
        _data={"what_type": "one_recipient", "placeholder_value": recipient},
        _expected_status=302,
        _expected_redirect=url_for(
            ".send_one_off_step",
            service_id=SERVICE_ONE_ID,
            template_id=template_id,
            step_index=1,
            _external=True,
        ),
    )
