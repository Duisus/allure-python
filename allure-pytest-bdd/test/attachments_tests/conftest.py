import os.path

import pytest
from pytest_bdd import then, parsers


@pytest.fixture()
def test_context():
    return {"last checked attachment": None}


@then(parsers.re("this attachment with content:(?:\n)(?P<expected_content>[\\S|\\s]*)"))
def check_attachment_content(expected_content, test_context, testdir):
    last_checked_attachment = test_context["last checked attachment"]

    file_path = os.path.join(testdir.tmpdir.strpath, last_checked_attachment["source"])
    with open(file_path, "r") as file:
        actual_content = file.read()

    assert actual_content == expected_content


@then(parsers.parse("attachment {attachment_name} must be in {location_name}"))
def suitable_attachment(attachment_name, location_name, test_context, allure_report):
    test_case_report = allure_report.test_cases[0]

    if location_name == "attachments":
        attachments = test_case_report["attachments"]
    else:
        attachments = _get_step_report(test_case_report, location_name)["attachments"]

    suitable_attachments = [attachment for attachment in attachments
                            if attachment["name"] == attachment_name]

    assert len(suitable_attachments) == 1
    test_context["last checked attachment"] = suitable_attachments[0]


@then(parsers.parse("attachments must not be in {location_name}"))
def attachments_must_no_be_in(location_name, allure_report):
    test_case_report = allure_report.test_cases[0]

    if location_name == "attachments":
        assert "attachments" not in test_case_report.keys()
    else:
        assert "attachments" not in _get_step_report(test_case_report, location_name).keys()


def _get_step_report(test_case_report, step_name):
    return next(step for step in test_case_report["steps"]
                if step["name"] == step_name)
