from functools import partial

import allure_commons
import pytest
from allure_commons.lifecycle import AllureLifecycle
from allure_commons.model2 import Label, Link
from allure_commons.model2 import Status
from allure_commons.model2 import StatusDetails
from allure_commons.types import LabelType
from allure_commons.utils import host_tag, thread_tag
from allure_commons.utils import now
from allure_commons.utils import platform_label
from allure_commons.utils import uuid4

from .attachment_worker import AttachmentWorker
from .utils import allure_links
from .utils import get_full_name, get_name, get_params
from .utils import get_pytest_report_status
from .utils import get_status_details
from .utils import get_step_name
from .utils import get_uuid
from .utils import pytest_markers


class PytestBDDListener(object):
    def __init__(self):
        self.lifecycle = AllureLifecycle()
        self.host = host_tag()
        self.thread = thread_tag()

    def _scenario_finalizer(self, scenario):
        for step in scenario.steps:
            step_uuid = get_uuid(str(id(step)))
            with self.lifecycle.update_step(uuid=step_uuid) as step_result:
                if step_result:
                    step_result.status = Status.SKIPPED
                    self.lifecycle.stop_step(uuid=step_uuid)

    @pytest.hookimpl
    def pytest_bdd_before_scenario(self, request, feature, scenario):
        uuid = get_uuid(request.node.nodeid)
        full_name = get_full_name(feature, scenario)
        name = get_name(request.node, scenario)
        with self.lifecycle.schedule_test_case(uuid=uuid) as test_result:
            test_result.fullName = full_name
            test_result.name = name
            test_result.start = now()
            test_result.labels.extend([Label(name=LabelType.TAG, value=value)
                                       for value in pytest_markers(request.node)])
            test_result.labels.append(Label(name=LabelType.HOST, value=self.host))
            test_result.labels.append(Label(name=LabelType.THREAD, value=self.thread))
            test_result.labels.append(Label(name=LabelType.FRAMEWORK, value="pytest-bdd"))
            test_result.labels.append(Label(name=LabelType.LANGUAGE, value=platform_label()))
            test_result.labels.append(Label(name=LabelType.FEATURE, value=feature.name))
            test_result.links.extend([Link(link_type, url, name)
                                      for link_type, url, name in allure_links(request.node)])
            test_result.parameters = get_params(request.node)

        finalizer = partial(self._scenario_finalizer, scenario)
        request.node.addfinalizer(finalizer)

    @pytest.hookimpl
    def pytest_bdd_after_scenario(self, request, feature, scenario):
        uuid = get_uuid(request.node.nodeid)
        with self.lifecycle.update_test_case(uuid=uuid) as test_result:
            test_result.stop = now()

    @pytest.hookimpl
    def pytest_bdd_before_step_call(self, request, feature, scenario, step, step_func, step_func_args):
        parent_uuid = get_uuid(request.node.nodeid)
        uuid = get_uuid(str(id(step)))
        with self.lifecycle.start_step(parent_uuid=parent_uuid, uuid=uuid) as step_result:
            step_result.name = get_step_name(request.node, step)

    @pytest.hookimpl
    def pytest_bdd_after_step(self, request, feature, scenario, step, step_func, step_func_args):
        uuid = get_uuid(str(id(step)))
        with self.lifecycle.update_step(uuid=uuid) as step_result:
            step_result.status = Status.PASSED
        self.lifecycle.stop_step(uuid=uuid)

    @pytest.hookimpl
    def pytest_bdd_step_error(self, request, feature, scenario, step, step_func, step_func_args, exception):
        uuid = get_uuid(str(id(step)))
        with self.lifecycle.update_step(uuid=uuid) as step_result:
            step_result.status = Status.FAILED
            step_result.statusDetails = get_status_details(exception)
        self.lifecycle.stop_step(uuid=uuid)

    @pytest.hookimpl
    def pytest_bdd_step_func_lookup_error(self, request, feature, scenario, step, exception):
        uuid = get_uuid(str(id(step)))
        with self.lifecycle.update_step(uuid=uuid) as step_result:
            step_result.status = Status.BROKEN
        self.lifecycle.stop_step(uuid=uuid)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        report = (yield).get_result()

        status = get_pytest_report_status(report)

        status_details = StatusDetails(
            message=call.excinfo.exconly(),
            trace=report.longreprtext) if call.excinfo else None

        uuid = get_uuid(report.nodeid)
        with self.lifecycle.update_test_case(uuid=uuid) as test_result:

            if test_result and report.when == "setup":
                test_result.status = status
                test_result.statusDetails = status_details

            if report.when == "call" and test_result:
                if test_result.status not in [Status.PASSED, Status.FAILED]:
                    test_result.status = status
                    test_result.statusDetails = status_details

            if report.when == "teardown" and test_result:
                if test_result.status == Status.PASSED and status != Status.PASSED:
                    test_result.status = status
                    test_result.statusDetails = status_details

            if test_result and test_result.status:
                AttachmentWorker(test_result, item).delete_duplicates()

        if report.when == 'teardown':
            self.lifecycle.write_test_case(uuid=uuid)

    @allure_commons.hookimpl
    def attach_data(self, body, name, attachment_type, extension):
        self.lifecycle.attach_data(uuid4(), body, name=name, attachment_type=attachment_type, extension=extension)

    @allure_commons.hookimpl
    def attach_file(self, source, name, attachment_type, extension):
        self.lifecycle.attach_file(uuid4(), source, name=name, attachment_type=attachment_type, extension=extension)
