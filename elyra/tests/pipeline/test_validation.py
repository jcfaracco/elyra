#
# Copyright 2018-2022 Elyra Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os

from conftest import AIRFLOW_TEST_OPERATOR_CATALOG
from conftest import KFP_COMPONENT_CACHE_INSTANCE
import pytest

from elyra.pipeline.pipeline import KubernetesAnnotation
from elyra.pipeline.pipeline import KubernetesSecret
from elyra.pipeline.pipeline import KubernetesToleration
from elyra.pipeline.pipeline import PIPELINE_CURRENT_VERSION
from elyra.pipeline.pipeline import VolumeMount
from elyra.pipeline.pipeline_constants import KUBERNETES_POD_ANNOTATIONS
from elyra.pipeline.pipeline_constants import KUBERNETES_SECRETS
from elyra.pipeline.pipeline_constants import KUBERNETES_TOLERATIONS
from elyra.pipeline.pipeline_constants import MOUNTED_VOLUMES
from elyra.pipeline.pipeline_definition import PipelineDefinition
from elyra.pipeline.validation import PipelineValidationManager
from elyra.pipeline.validation import ValidationResponse
from elyra.tests.pipeline.util import _read_pipeline_resource


@pytest.fixture
def load_pipeline():
    def _function(pipeline_filepath):
        response = ValidationResponse()

        pipeline = _read_pipeline_resource(f"resources/validation_pipelines/{pipeline_filepath}")
        return pipeline, response

    yield _function


@pytest.fixture
def validation_manager(setup_factory_data, component_cache):
    root = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__), "resources/validation_pipelines"))
    yield PipelineValidationManager.instance(root_dir=root)
    PipelineValidationManager.clear_instance()


async def test_invalid_lower_pipeline_version(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_only_notebook.pipeline")
    pipeline_version = PIPELINE_CURRENT_VERSION - 1
    pipeline["pipelines"][0]["app_data"]["version"] = pipeline_version

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    validation_manager._validate_pipeline_structure(pipeline_definition=pipeline_definition, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidPipeline"
    assert (
        issues[0]["message"] == f"Pipeline version {pipeline_version} is out of date "
        "and needs to be migrated using the Elyra pipeline editor."
    )


def test_invalid_upper_pipeline_version(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_only_notebook.pipeline")
    pipeline_version = PIPELINE_CURRENT_VERSION + 1
    pipeline["pipelines"][0]["app_data"]["version"] = pipeline_version

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    validation_manager._validate_pipeline_structure(pipeline_definition=pipeline_definition, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidPipeline"
    assert (
        issues[0]["message"] == "Pipeline was last edited in a newer version of Elyra. "
        "Update Elyra to use this pipeline."
    )


def test_invalid_pipeline_version_that_needs_migration(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_only_notebook.pipeline")
    pipeline["pipelines"][0]["app_data"]["version"] = 3

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    validation_manager._validate_pipeline_structure(pipeline_definition=pipeline_definition, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidPipeline"
    assert "needs to be migrated" in issues[0]["message"]


def test_basic_pipeline_structure(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_only_notebook.pipeline")

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    validation_manager._validate_pipeline_structure(pipeline_definition=pipeline_definition, response=response)
    assert not response.has_fatal
    assert not response.to_json().get("issues")


def test_basic_pipeline_structure_with_scripts(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_with_scripts.pipeline")

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    validation_manager._validate_pipeline_structure(pipeline_definition=pipeline_definition, response=response)
    assert not response.has_fatal
    assert not response.to_json().get("issues")


@pytest.mark.parametrize("catalog_instance", [KFP_COMPONENT_CACHE_INSTANCE], indirect=True)
async def test_invalid_runtime_node_kubeflow(validation_manager, load_pipeline, catalog_instance):
    pipeline, response = load_pipeline("kf_invalid_node_op.pipeline")
    node_id = "eace43f8-c4b1-4a25-b331-d57d4fc29426"

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_compatibility(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="KUBEFLOW_PIPELINES",
        pipeline_runtime="kfp",
    )

    issues = response.to_json().get("issues")
    print(issues)
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeType"
    assert issues[0]["data"]["nodeID"] == node_id


@pytest.mark.parametrize("catalog_instance", [KFP_COMPONENT_CACHE_INSTANCE], indirect=True)
async def test_invalid_runtime_node_kubeflow_with_supernode(validation_manager, load_pipeline, catalog_instance):
    pipeline, response = load_pipeline("kf_invalid_node_op_with_supernode.pipeline")
    node_id = "98aa7270-639b-42a4-9a07-b31cd0fa3205"
    pipeline_id = "00304a2b-dec4-4a73-ab4a-6830f97d7855"

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_compatibility(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="KUBEFLOW_PIPELINES",
        pipeline_runtime="kfp",
    )
    issues = response.to_json().get("issues")
    print(issues)
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeType"
    assert issues[0]["data"]["pipelineId"] == pipeline_id
    assert issues[0]["data"]["nodeID"] == node_id


async def test_invalid_pipeline_runtime_with_kubeflow_execution(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_with_scripts.pipeline")

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_compatibility(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="APACHE_AIRFLOW",
        pipeline_runtime="kfp",
    )
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidRuntime"


async def test_invalid_pipeline_runtime_with_local_execution(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_pipeline_with_scripts.pipeline")

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_compatibility(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="APACHE_AIRFLOW",
        pipeline_runtime="local",
    )
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidRuntime"
    assert issues[0]["data"]["pipelineType"] == "APACHE_AIRFLOW"


async def test_invalid_node_op_with_airflow(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("aa_invalid_node_op.pipeline")
    node_id = "749d4641-cee8-4a50-a0ed-30c07439908f"

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_compatibility(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="APACHE_AIRFLOW",
        pipeline_runtime="airflow",
    )
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeType"
    assert issues[0]["data"]["nodeID"] == node_id


async def test_invalid_node_property_structure(validation_manager, monkeypatch, load_pipeline):
    pipeline, response = load_pipeline("generic_invalid_node_property_structure.pipeline")
    node_id = "88ab83dc-d5f0-443a-8837-788ed16851b7"
    node_property = "runtime_image"
    pvm = validation_manager

    monkeypatch.setattr(pvm, "_validate_filepath", lambda node_id, node_label, property_name, filename, response: True)

    monkeypatch.setattr(pvm, "_validate_label", lambda node_id, node_label, response: True)

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await pvm._validate_node_properties(
        pipeline_definition=pipeline_definition, response=response, pipeline_type="GENERIC", pipeline_runtime="kfp"
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["propertyName"] == node_property
    assert issues[0]["data"]["nodeID"] == node_id


@pytest.mark.parametrize("catalog_instance", [KFP_COMPONENT_CACHE_INSTANCE], indirect=True)
async def test_missing_node_property_for_kubeflow_pipeline(
    validation_manager, monkeypatch, load_pipeline, catalog_instance
):
    pipeline, response = load_pipeline("kf_invalid_node_property_in_component.pipeline")
    node_id = "fe08b42d-bd8c-4e97-8010-0503a3185427"
    node_property = "notebook"
    pvm = validation_manager

    monkeypatch.setattr(pvm, "_validate_filepath", lambda node_id, file_dir, property_name, filename, response: True)

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await pvm._validate_node_properties(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="KUBEFLOW_PIPELINES",
        pipeline_runtime="kfp",
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["propertyName"] == node_property
    assert issues[0]["data"]["nodeID"] == node_id


def test_invalid_node_property_image_name(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_invalid_node_property_image_name.pipeline")
    node_ids = ["88ab83dc-d5f0-443a-8837-788ed16851b7", "7ae74ba6-d49f-48ea-9e4f-e44d13594b2f"]
    node_property = "runtime_image"

    for i, node_id in enumerate(node_ids):
        node = pipeline["pipelines"][0]["nodes"][i]
        node_label = node["app_data"].get("label")
        image_name = node["app_data"]["component_parameters"].get("runtime_image")
        validation_manager._validate_container_image_name(node["id"], node_label, image_name, response)

    issues = response.to_json().get("issues")
    assert len(issues) == 2
    # Test missing runtime image in node 0
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["propertyName"] == node_property
    assert issues[0]["data"]["nodeID"] == node_ids[0]
    assert issues[0]["message"] == "Required property value is missing."

    # Test invalid format for runtime image in node 1
    assert issues[1]["severity"] == 1
    assert issues[1]["type"] == "invalidNodeProperty"
    assert issues[1]["data"]["propertyName"] == node_property
    assert issues[1]["data"]["nodeID"] == node_ids[1]
    assert (
        issues[1]["message"] == "Node contains an invalid runtime image. Runtime image "
        "must conform to the format [registry/]owner/image:tag"
    )


def test_invalid_node_property_image_name_list(validation_manager):
    response = ValidationResponse()
    node_label = "test_label"
    node_id = "test-id"
    failing_image_names = [
        "12345566:one-two-three",
        "someregistry.io/some_org/some_tag/something/",
        "docker.io//missing_org_name:test",
    ]

    for image_name in failing_image_names:
        validation_manager._validate_container_image_name(node_id, node_label, image_name, response)

    issues = response.to_json().get("issues")
    assert len(issues) == len(failing_image_names)


def test_invalid_node_property_dependency_filepath_workspace(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    property_name = "test-property"

    validation_manager._validate_filepath(
        node_id=node["id"],
        file_dir=os.getcwd(),
        property_name=property_name,
        node_label=node["app_data"]["label"],
        filename="../invalid_filepath/to/file.ipynb",
        response=response,
    )
    issues = response.to_json().get("issues")
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidFilePath"
    assert issues[0]["data"]["propertyName"] == property_name
    assert issues[0]["data"]["nodeID"] == node["id"]


def test_invalid_node_property_dependency_filepath_non_existent(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    property_name = "test-property"

    validation_manager._validate_filepath(
        node_id=node["id"],
        file_dir=os.getcwd(),
        property_name=property_name,
        node_label=node["app_data"]["label"],
        filename="invalid_filepath/to/file.ipynb",
        response=response,
    )
    issues = response.to_json().get("issues")
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidFilePath"
    assert issues[0]["data"]["propertyName"] == property_name
    assert issues[0]["data"]["nodeID"] == node["id"]


def test_valid_node_property_dependency_filepath(validation_manager):
    response = ValidationResponse()
    valid_filename = os.path.join(
        os.path.dirname(__file__), "resources/validation_pipelines/generic_single_cycle.pipeline"
    )
    node = {"id": "test-id", "app_data": {"label": "test"}}
    property_name = "test-property"

    validation_manager._validate_filepath(
        node_id=node["id"],
        file_dir=os.getcwd(),
        property_name=property_name,
        node_label=node["app_data"]["label"],
        filename=valid_filename,
        response=response,
    )

    assert not response.has_fatal
    assert not response.to_json().get("issues")


async def test_valid_node_property_pipeline_filepath(monkeypatch, validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_basic_filepath_check.pipeline")

    monkeypatch.setattr(validation_manager, "_validate_label", lambda node_id, node_label, response: True)

    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_node_properties(
        pipeline_definition=pipeline_definition, response=response, pipeline_type="GENERIC", pipeline_runtime="kfp"
    )

    assert not response.has_fatal
    assert not response.to_json().get("issues")


def test_invalid_node_property_resource_value(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_invalid_node_property_hardware_resources.pipeline")
    node_id = "88ab83dc-d5f0-443a-8837-788ed16851b7"

    node = pipeline["pipelines"][0]["nodes"][0]
    validation_manager._validate_resource_value(
        node["id"],
        node["app_data"]["label"],
        resource_name="memory",
        resource_value=node["app_data"]["component_parameters"]["memory"],
        response=response,
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["propertyName"] == "memory"
    assert issues[0]["data"]["nodeID"] == node_id


def test_invalid_node_property_env_var(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    invalid_env_var = 'TEST_ENV_ONE"test_one"'
    validation_manager._validate_environmental_variables(
        node_id=node["id"], node_label=node["app_data"]["label"], env_var=invalid_env_var, response=response
    )
    issues = response.to_json().get("issues")
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidEnvPair"
    assert issues[0]["data"]["propertyName"] == "env_vars"
    assert issues[0]["data"]["nodeID"] == "test-id"


def test_invalid_node_property_volumes(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    volumes = [
        VolumeMount("/mount/test", "rwx-test-claim"),  # valid
        VolumeMount("/mount/test_two", "second-claim"),  # valid
        VolumeMount("/mount/test_four", "second#claim"),  # invalid pvc name
    ]
    validation_manager._validate_mounted_volumes(
        node_id=node["id"], node_label=node["app_data"]["label"], volumes=volumes, response=response
    )
    issues = response.to_json().get("issues")
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidVolumeMount"
    assert issues[0]["data"]["propertyName"] == MOUNTED_VOLUMES
    assert issues[0]["data"]["nodeID"] == "test-id"
    assert "not a valid Kubernetes resource name" in issues[0]["message"]


def test_valid_node_property_kubernetes_toleration(validation_manager):
    """
    Validate that valid kubernetes toleration definitions are not flagged as invalid.
    Constraints are documented in
    https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.23/#toleration-v1-core
    """
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    # The following tolerations are valid
    tolerations = [
        # parameters are key, operator, value, effect
        KubernetesToleration("", "Exists", "", "NoExecute"),
        KubernetesToleration("key0", "Exists", "", ""),
        KubernetesToleration("key1", "Exists", "", "NoSchedule"),
        KubernetesToleration("key2", "Equal", "value2", "NoExecute"),
        KubernetesToleration("key3", "Equal", "value3", "PreferNoSchedule"),
    ]
    validation_manager._validate_kubernetes_tolerations(
        node_id=node["id"], node_label=node["app_data"]["label"], tolerations=tolerations, response=response
    )
    issues = response.to_json().get("issues")
    assert len(issues) == 0, response.to_json()


def test_valid_node_property_kubernetes_pod_annotation(validation_manager):
    """
    Validate that valid kubernetes pod annotation definitions are not flagged as invalid.
    Constraints are documented in
    https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/#syntax-and-character-set
    """
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    # The following annotations are valid
    annotations = [
        # parameters are key and value
        KubernetesAnnotation("k", ""),
        KubernetesAnnotation("key", "value"),
        KubernetesAnnotation("n-a-m-e", "value"),
        KubernetesAnnotation("n.a.m.e", "value"),
        KubernetesAnnotation("n_a_m_e", "value"),
        KubernetesAnnotation("n-a.m_e", "value"),
        KubernetesAnnotation("prefix/name", "value"),
        KubernetesAnnotation("abc.def/name", "value"),
        KubernetesAnnotation("abc.def.ghi/n-a-m-e", "value"),
        KubernetesAnnotation("abc.def.ghi.jkl/n.a.m.e", "value"),
        KubernetesAnnotation("abc.def.ghi.jkl.mno/n_a_m_e", "value"),
        KubernetesAnnotation("abc.def.ghijklmno.pqr/n-a.m_e", "value"),
    ]
    validation_manager._validate_kubernetes_pod_annotations(
        node_id=node["id"], node_label=node["app_data"]["label"], annotations=annotations, response=response
    )
    issues = response.to_json().get("issues")
    assert len(issues) == 0, response.to_json()


def test_invalid_node_property_kubernetes_toleration(validation_manager):
    """
    Validate that invalid kubernetes toleration definitions are properly detected.
    Constraints are documented in
    https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.23/#toleration-v1-core
    """
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    # The following tolerations are invalid
    invalid_tolerations = [
        # parameters are key, operator, value, effect
        KubernetesToleration("", "", "", ""),  # cannot be all empty
        # invalid values for 'operator'
        KubernetesToleration("", "Equal", "value", ""),  # empty key requires 'Exists'
        KubernetesToleration("key0", "exists", "", ""),  # wrong case
        KubernetesToleration("key1", "Exist", "", ""),  # wrong keyword
        KubernetesToleration("key2", "", "", ""),  # wrong keyword (technically valid but enforced)
        # invalid values for 'value'
        KubernetesToleration("key3", "Exists", "value3", ""),  # 'Exists' -> no value
        # invalid values for 'effect'
        KubernetesToleration("key4", "Exists", "", "noschedule"),  # wrong case
        KubernetesToleration("key5", "Exists", "", "no-such-effect"),  # wrong keyword
    ]
    expected_error_messages = [
        "'' is not a valid operator. The value must be one of 'Exists' or 'Equal'.",
        "'Equal' is not a valid operator. Operator must be 'Exists' if no key is specified.",
        "'exists' is not a valid operator. The value must be one of 'Exists' or 'Equal'.",
        "'Exist' is not a valid operator. The value must be one of 'Exists' or 'Equal'.",
        "'' is not a valid operator. The value must be one of 'Exists' or 'Equal'.",
        "'value3' is not a valid value. It should be empty if operator is 'Exists'.",
        "'noschedule' is not a valid effect. Effect must be one of 'NoExecute', 'NoSchedule', or 'PreferNoSchedule'.",
        "'no-such-effect' is not a valid effect. Effect must be one of 'NoExecute', "
        "'NoSchedule', or 'PreferNoSchedule'.",
    ]

    # verify that the number of tolerations in this test matches the number of error messages
    assert len(invalid_tolerations) == len(expected_error_messages), "Test setup error. "

    validation_manager._validate_kubernetes_tolerations(
        node_id=node["id"], node_label=node["app_data"]["label"], tolerations=invalid_tolerations, response=response
    )
    issues = response.to_json().get("issues")
    assert len(issues) == len(invalid_tolerations), response.to_json()
    index = 0
    for issue in issues:
        assert issue["type"] == "invalidKubernetesToleration"
        assert issue["data"]["propertyName"] == KUBERNETES_TOLERATIONS
        assert issue["data"]["nodeID"] == "test-id"
        assert issue["message"] == expected_error_messages[index], f"Index is {index}"
        index = index + 1


def test_invalid_node_property_kubernetes_pod_annotation(validation_manager):
    """
    Validate that valid kubernetes pod annotation definitions are not flagged as invalid.
    Constraints are documented in
    https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/#syntax-and-character-set
    """
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    TOO_SHORT_LENGTH = 0
    MAX_PREFIX_LENGTH = 253
    MAX_NAME_LENGTH = 63
    TOO_LONG_LENGTH = MAX_PREFIX_LENGTH + 1 + MAX_NAME_LENGTH + 1  # prefix + '/' + name

    # The following annotations are invalid
    invalid_annotations = [
        # parameters are key and value
        # test length violations (key name and prefix)
        KubernetesAnnotation("a" * (TOO_SHORT_LENGTH), ""),  # empty key (min 1)
        KubernetesAnnotation("a" * (TOO_LONG_LENGTH), ""),  # key too long
        KubernetesAnnotation(f"{'a' * (MAX_PREFIX_LENGTH + 1)}/b", ""),  # key prefix too long
        KubernetesAnnotation(f"{'a' * (MAX_NAME_LENGTH + 1)}", ""),  # key name too long
        KubernetesAnnotation(f"prefix/{'a' * (MAX_NAME_LENGTH + 1)}", ""),  # key name too long
        KubernetesAnnotation(f"{'a' * (MAX_PREFIX_LENGTH + 1)}/name", ""),  # key prefix too long
        # test character violations (key name)
        KubernetesAnnotation("-", ""),  # name must start and end with alphanum
        KubernetesAnnotation("-a", ""),  # name must start with alphanum
        KubernetesAnnotation("a-", ""),  # name must start with alphanum
        KubernetesAnnotation("prefix/-b", ""),  # name start with alphanum
        KubernetesAnnotation("prefix/b-", ""),  # name must end with alphanum
        # test character violations (key prefix)
        KubernetesAnnotation("PREFIX/name", ""),  # prefix must be lowercase
        KubernetesAnnotation("pref!x/name", ""),  # prefix must contain alnum, '-' or '.'
        KubernetesAnnotation("pre.fx./name", ""),  # prefix must contain alnum, '-' or '.'
        KubernetesAnnotation("-pre.fx.com/name", ""),  # prefix must contain alnum, '-' or '.'
        KubernetesAnnotation("pre.fx-./name", ""),  # prefix must contain alnum, '-' or '.'
        KubernetesAnnotation("a/b/c", ""),  # only one separator char
    ]
    expected_error_messages = [
        "'' is not a valid Kubernetes annotation key.",
        f"'{'a' * (TOO_LONG_LENGTH)}' is not a valid Kubernetes annotation key.",
        f"'{'a' * (MAX_PREFIX_LENGTH + 1)}/b' is not a valid Kubernetes annotation key.",
        f"'{'a' * (MAX_NAME_LENGTH + 1)}' is not a valid Kubernetes annotation key.",
        f"'prefix/{'a' * (MAX_NAME_LENGTH + 1)}' is not a valid Kubernetes annotation key.",
        f"'{'a' * (MAX_PREFIX_LENGTH + 1)}/name' is not a valid Kubernetes annotation key.",
        "'-' is not a valid Kubernetes annotation key.",
        "'-a' is not a valid Kubernetes annotation key.",
        "'a-' is not a valid Kubernetes annotation key.",
        "'prefix/-b' is not a valid Kubernetes annotation key.",
        "'prefix/b-' is not a valid Kubernetes annotation key.",
        "'PREFIX/name' is not a valid Kubernetes annotation key.",
        "'pref!x/name' is not a valid Kubernetes annotation key.",
        "'pre.fx./name' is not a valid Kubernetes annotation key.",
        "'-pre.fx.com/name' is not a valid Kubernetes annotation key.",
        "'pre.fx-./name' is not a valid Kubernetes annotation key.",
        "'a/b/c' is not a valid Kubernetes annotation key.",
    ]

    # verify that the number of annotations in this test matches the number of error messages
    assert len(invalid_annotations) == len(expected_error_messages), "Test implementation error. "

    validation_manager._validate_kubernetes_pod_annotations(
        node_id=node["id"], node_label=node["app_data"]["label"], annotations=invalid_annotations, response=response
    )
    issues = response.to_json().get("issues")
    assert len(issues) == len(
        invalid_annotations
    ), f"validation returned unexpected results: {response.to_json()['issues']}"
    index = 0
    for issue in issues:
        assert issue["type"] == "invalidKubernetesAnnotation"
        assert issue["data"]["propertyName"] == KUBERNETES_POD_ANNOTATIONS
        assert issue["data"]["nodeID"] == "test-id"
        assert issue["message"] == expected_error_messages[index], f"Index is {index}"
        index = index + 1


def test_invalid_node_property_secrets(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    secrets = [
        KubernetesSecret("ENV_VAR1", "test-secret", "test-key1"),  # valid
        KubernetesSecret("ENV_VAR2", "test-secret", "test-key2"),  # valid
        KubernetesSecret("ENV_VAR3", "test-secret", ""),  # invalid: improper format of secret name/key
        KubernetesSecret("ENV_VAR5", "test%secret", "test-key"),  # invalid: not a valid Kubernetes resource name
        KubernetesSecret("ENV_VAR6", "test-secret", "test$key2"),  # invalid: not a valid Kubernetes secret key
    ]
    validation_manager._validate_kubernetes_secrets(
        node_id=node["id"], node_label=node["app_data"]["label"], secrets=secrets, response=response
    )
    issues = response.to_json().get("issues")
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidKubernetesSecret"
    assert issues[0]["data"]["propertyName"] == KUBERNETES_SECRETS
    assert issues[0]["data"]["nodeID"] == "test-id"
    assert "improperly formatted representation of secret name and key" in issues[0]["message"]
    assert "not a valid Kubernetes resource name" in issues[1]["message"]
    assert "not a valid Kubernetes secret key" in issues[2]["message"]


def test_valid_node_property_label(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id"}
    valid_label_name = "dead-bread-dead-bread-dead-bread-dead-bread-dead-bread-dead-bre"
    validation_manager._validate_label(node_id=node["id"], node_label=valid_label_name, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 0


def test_valid_node_property_label_min_length(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    valid_label_name = "d"
    validation_manager._validate_label(node_id=node["id"], node_label=valid_label_name, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 0


def test_invalid_node_property_label_filename_exceeds_max_length(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    valid_label_name = "deadbread-deadbread-deadbread-deadbread-deadbread-deadbread-de.py"
    validation_manager._validate_label(node_id=node["id"], node_label=valid_label_name, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 2


def test_invalid_node_property_label_max_length(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    invalid_label_name = "dead-bread-dead-bread-dead-bread-dead-bread-dead-bread-dead-bred"
    validation_manager._validate_label(node_id=node["id"], node_label=invalid_label_name, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 2
    assert issues[0]["type"] == "invalidNodeLabel"
    assert issues[0]["data"]["propertyName"] == "label"
    assert issues[0]["data"]["nodeID"] == "test-id"


def test_valid_node_property_label_filename_has_relative_path(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id", "app_data": {"label": "test"}}
    valid_label_name = "deadbread.py"
    validation_manager._validate_label(node_id=node["id"], node_label=valid_label_name, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 0


def test_invalid_node_property_label_bad_characters(validation_manager):
    response = ValidationResponse()
    node = {"id": "test-id"}
    invalid_label_name = "bad_label_*&^&$"
    validation_manager._validate_label(node_id=node["id"], node_label=invalid_label_name, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 2
    assert issues[0]["type"] == "invalidNodeLabel"
    assert issues[0]["data"]["propertyName"] == "label"
    assert issues[0]["data"]["nodeID"] == "test-id"


def test_pipeline_graph_single_cycle(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_single_cycle.pipeline")
    # cycle_ID = ['c309f6dd-b022-4b1c-b2b0-b6449bb26e8f', '8cb986cb-4fc9-4b1d-864d-0ec64b7ac13c']

    validation_manager._validate_pipeline_graph(pipeline=pipeline, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "circularReference"
    # assert issues[0]['data']['linkIDList'].sort() == cycle_ID.sort()


def test_pipeline_graph_double_cycle(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_double_cycle.pipeline")
    # cycle_ID = ['597b2971-b95d-4df7-a36d-9d93b0345298', 'b63378e4-9085-4a33-9330-6f86054681f4']
    # cycle_two_ID = ['c309f6dd-b022-4b1c-b2b0-b6449bb26e8f', '8cb986cb-4fc9-4b1d-864d-0ec64b7ac13c']

    validation_manager._validate_pipeline_graph(pipeline=pipeline, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "circularReference"
    # assert issues[0]['data']['linkIDList'].sort() == cycle_ID.sort()
    # assert issues[1]['severity'] == 1
    # assert issues[1]['type'] == 'circularReference'
    # assert issues[1]['data']['linkIDList'].sort() == cycle_two_ID.sort()


def test_pipeline_graph_singleton(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("generic_singleton.pipeline")
    node_id = "0195fefd-3ceb-4a90-a12c-3958ef0ff42e"

    validation_manager._validate_pipeline_graph(pipeline=pipeline, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert not response.has_fatal
    assert issues[0]["severity"] == 2
    assert issues[0]["type"] == "singletonReference"
    assert issues[0]["data"]["nodeID"] == node_id


def test_pipeline_valid_kfp_with_supernode(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("kf_supernode_valid.pipeline")

    validation_manager._validate_pipeline_graph(pipeline=pipeline, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 0
    assert not response.has_fatal


def test_pipeline_invalid_single_cycle_kfp_with_supernode(validation_manager, load_pipeline):
    pipeline, response = load_pipeline("kf_supernode_invalid_single_cycle.pipeline")

    validation_manager._validate_pipeline_graph(pipeline=pipeline, response=response)
    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert response.has_fatal
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "circularReference"


@pytest.mark.parametrize("catalog_instance", [KFP_COMPONENT_CACHE_INSTANCE], indirect=True)
async def test_pipeline_kfp_inputpath_parameter(validation_manager, load_pipeline, catalog_instance, component_cache):
    pipeline, response = load_pipeline("kf_inputpath_parameter.pipeline")
    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_node_properties(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="KUBEFLOW_PIPELINES",
        pipeline_runtime="kfp",
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 0


@pytest.mark.parametrize("catalog_instance", [KFP_COMPONENT_CACHE_INSTANCE], indirect=True)
async def test_pipeline_invalid_kfp_inputpath_parameter(
    validation_manager, load_pipeline, catalog_instance, component_cache
):
    invalid_key_node_id = "089a12df-fe2f-4fcb-ae37-a1f8a6259ca1"
    missing_param_node_id = "e8820c55-dc79-46d1-b32e-924fa5d70d2a"
    pipeline, response = load_pipeline("kf_invalid_inputpath_parameter.pipeline")
    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_node_properties(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="KUBEFLOW_PIPELINES",
        pipeline_runtime="kfp",
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 2
    assert response.has_fatal
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["nodeID"] == invalid_key_node_id
    assert issues[1]["severity"] == 1
    assert issues[1]["type"] == "invalidNodeProperty"
    assert issues[1]["data"]["nodeID"] == missing_param_node_id


@pytest.mark.parametrize("catalog_instance", [KFP_COMPONENT_CACHE_INSTANCE], indirect=True)
async def test_pipeline_invalid_kfp_inputpath_missing_connection(
    validation_manager, load_pipeline, catalog_instance, component_cache
):
    invalid_node_id = "5b78ea0a-e5fc-4022-94d4-7b9dc170d794"
    pipeline, response = load_pipeline("kf_invalid_inputpath_missing_connection.pipeline")
    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_node_properties(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="KUBEFLOW_PIPELINES",
        pipeline_runtime="kfp",
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert response.has_fatal
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["nodeID"] == invalid_node_id


@pytest.mark.parametrize("catalog_instance", [AIRFLOW_TEST_OPERATOR_CATALOG], indirect=True)
async def test_pipeline_aa_parent_node_missing_xcom_push(
    validation_manager, load_pipeline, catalog_instance, component_cache
):

    invalid_node_id = "b863d458-21b5-4a46-8420-5a814b7bd525"
    invalid_operator = "TestOperator"

    pipeline, response = load_pipeline("aa_parent_node_missing_xcom.pipeline")
    pipeline_definition = PipelineDefinition(pipeline_definition=pipeline)
    await validation_manager._validate_node_properties(
        pipeline_definition=pipeline_definition,
        response=response,
        pipeline_type="APACHE_AIRFLOW",
        pipeline_runtime="airflow",
    )

    issues = response.to_json().get("issues")
    assert len(issues) == 1
    assert response.has_fatal
    assert issues[0]["severity"] == 1
    assert issues[0]["type"] == "invalidNodeProperty"
    assert issues[0]["data"]["nodeID"] == invalid_node_id
    assert issues[0]["data"]["parentNodeID"] == invalid_operator
