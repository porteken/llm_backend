import uuid
from time import sleep, time
from typing import Type, List

from crewai.tools import BaseTool
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

# --- Constants ---
# Using constants makes the code easier to read and change.
CONFIG_MAP_DATA_KEY = "script.py"
CONTAINER_MOUNT_PATH = "/app"
VOLUME_NAME = "code-volume"


class KubernetesCodeExecutor:
    """
    Executes Python code in a Kubernetes Job.

    This class handles the lifecycle of running a piece of Python code within a
    dedicated Kubernetes Job. It creates a ConfigMap to store the code, a Job
    to run it, waits for completion, retrieves the logs, and cleans up all
    resources.

    It is designed to be safe and robust, with timeouts, proper error handling,
    and guaranteed resource cleanup.
    """

    def __init__(
        self,
        namespace: str = "default",
        image: str = "python_test",
        timeout_seconds: int = 300,
    ):
        """
        Initializes the KubernetesCodeExecutor.

        Args:
            namespace (str): The Kubernetes namespace to operate in.
            image (str): The container image to use for the Job. Must have python3 available.
            timeout_seconds (int): Maximum time to wait for the Job to complete.
        """
        try:
            # Load config from default location (~/.kube/config) or in-cluster config
            config.load_kube_config()
        except config.ConfigException:
            print(
                "Could not load kube config. Are you running in a cluster or have a valid config file?"
            )
            # For in-cluster, use: config.load_incluster_config()
            raise

        self.core_api = client.CoreV1Api()
        self.batch_api = client.BatchV1Api()
        self.namespace = namespace
        self.image = image
        self.timeout_seconds = timeout_seconds

    def run(self, code_to_run: str, libraries_used, prefix: str = "code-runner") -> str:
        """
        Creates, runs, and cleans up a Kubernetes Job for the given code.

        This is the main entrypoint method.

        Args:
            code_to_run (str): The Python code to execute.
            prefix (str): A prefix for the Kubernetes resource names.

        Returns:
            str: The logs (stdout/stderr) from the completed Job.

        Raises:
            ApiException: If a Kubernetes API call fails.
            TimeoutError: If the job does not complete within the specified timeout.
        """
        job_id = str(uuid.uuid4())[:8]
        job_name = f"{prefix}-job-{job_id}"
        configmap_name = f"{prefix}-configmap-{job_id}"

        try:
            # 1. Create ConfigMap with the user's code
            self._create_configmap(configmap_name, code_to_run)

            # 2. Create and run the Job
            self._create_and_run_job(job_name, configmap_name, libraries_used)

            # 3. Wait for the job to complete and get results
            return self._wait_for_job_completion(job_name)

        except ApiException as e:
            print(f"Kubernetes API Error: {e.reason} (Status: {e.status})")
            # Re-raise or return a formatted error string
            return f"Error: A Kubernetes API error occurred. Status: {e.status}, Reason: {e.reason}"
        finally:
            # 4. ALWAYS clean up resources to prevent leaks
            self._cleanup_resources(job_name, configmap_name)

    def _create_configmap(self, name: str, code: str):
        """Creates a V1ConfigMap object and deploys it."""
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=name), data={CONFIG_MAP_DATA_KEY: code}
        )
        self.core_api.create_namespaced_config_map(
            namespace=self.namespace, body=configmap
        )

    def _create_and_run_job(
        self, job_name: str, configmap_name: str, libraries_used: List[str]
    ):
        if len(libraries_used) > 0:
            args = [
                f"pip3 install --no-cache-dir --user {' '.join(libraries_used)} && python3",
                "-u",
                f"{CONTAINER_MOUNT_PATH}/{CONFIG_MAP_DATA_KEY}",
            ]
        else:
            args = ["python3", "-u", f"{CONTAINER_MOUNT_PATH}/{CONFIG_MAP_DATA_KEY}"]
        """Creates a V1Job object and submits it to the cluster."""
        volume_mount = client.V1VolumeMount(
            name=VOLUME_NAME,
            mount_path=CONTAINER_MOUNT_PATH,
        )
        volume = client.V1Volume(
            name=VOLUME_NAME,
            config_map=client.V1ConfigMapVolumeSource(name=configmap_name),
        )
        security_context = client.V1SecurityContext(
            run_as_user=1001, run_as_non_root=True
        )

        container = client.V1Container(
            name=job_name,
            image=self.image,
            image_pull_policy="Never",
            command=["/bin/bash", "-c"],
            args=args,
            security_context=security_context,
            volume_mounts=[volume_mount],
        )
        pod_spec = client.V1PodSpec(
            restart_policy="Never", containers=[container], volumes=[volume]
        )
        template_spec = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": job_name}), spec=pod_spec
        )
        job_spec = client.V1JobSpec(
            template=template_spec,
            backoff_limit=2,  # Fail faster
            ttl_seconds_after_finished=60,  # Auto-cleanup by Kubernetes if our script fails
        )
        job_body = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name),
            spec=job_spec,
        )

        self.batch_api.create_namespaced_job(body=job_body, namespace=self.namespace)

    def _wait_for_job_completion(self, job_name: str) -> str:
        """Waits for a job to complete and returns its logs."""
        start_time = time()
        while time() - start_time < self.timeout_seconds:
            try:
                status = self.batch_api.read_namespaced_job_status(
                    job_name, self.namespace
                )
                if status.status.succeeded:
                    return self._get_pod_logs(job_name)
                if status.status.failed:
                    return f"Job failed. Logs:\n{self._get_pod_logs(job_name)}"
            except ApiException as e:
                # Can happen if the job is not yet fully registered
                if e.status == 404:
                    sleep(1)
                    continue
                raise  # Re-raise other API errors
            sleep(2)  # Poll less aggressively

        raise TimeoutError(
            f"Job '{job_name}' did not complete within {self.timeout_seconds} seconds."
        )

    def _get_pod_logs(self, job_name: str) -> str:
        """Retrieves logs from the pod created by a job."""
        try:
            pod_list = self.core_api.list_namespaced_pod(
                self.namespace, label_selector=f"job-name={job_name}"
            )
            if not pod_list.items:
                return "Could not find pod for the job. It might have been deleted or failed to start."

            pod_name = pod_list.items[0].metadata.name
            return self.core_api.read_namespaced_pod_log(
                pod_name, self.namespace
            ).strip()
        except ApiException as e:
            return f"Could not retrieve logs. Kubernetes API Error: {e.reason}"

    def _cleanup_resources(self, job_name: str, configmap_name: str):
        """Deletes the job and configmap, ignoring 'Not Found' errors."""
        delete_options = client.V1DeleteOptions(propagation_policy="Foreground")

        # Delete Job
        try:
            self.batch_api.delete_namespaced_job(
                name=job_name, namespace=self.namespace, body=delete_options
            )
        except ApiException as e:
            if e.status != 404:  # Ignore if not found
                print(f"Error deleting job '{job_name}': {e.reason}")

        # Delete ConfigMap
        try:
            self.core_api.delete_namespaced_config_map(
                name=configmap_name, namespace=self.namespace
            )
        except ApiException as e:
            if e.status != 404:  # Ignore if not found
                print(f"Error deleting configmap '{configmap_name}': {e.reason}")

    def cleanup_all_by_prefix(self, prefix: str = "code-runner"):
        """
        Deletes all Jobs and ConfigMaps in the namespace with a specific prefix.
        This is a utility function for manual cleanup and should be used with caution.
        """
        print(f"Starting cleanup of all resources with prefix '{prefix}'...")
        # Cleanup Jobs
        jobs = self.batch_api.list_namespaced_job(namespace=self.namespace)
        for job in jobs.items:
            if job.metadata.name.startswith(prefix):
                self._cleanup_resources(
                    job.metadata.name, "dummy-cm"
                )  # Only need job name here

        # Cleanup ConfigMaps
        configmaps = self.core_api.list_namespaced_config_map(namespace=self.namespace)
        for cm in configmaps.items:
            if cm.metadata.name.startswith(prefix):
                try:
                    self.core_api.delete_namespaced_config_map(
                        name=cm.metadata.name, namespace=self.namespace
                    )
                    print(f"ConfigMap '{cm.metadata.name}' deleted.")
                except ApiException as e:
                    if e.status != 404:
                        print(
                            f"Error deleting configmap '{cm.metadata.name}': {e.reason}"
                        )


# --- CrewAI Tool Definition ---


class KubernetesExecutionToolSchema(BaseModel):
    """Input schema for the KubernetesExecutionTool."""

    code: str = Field(
        ...,
        description="Python3 code used to be interpreted in the Docker container. ALWAYS PRINT the final result and the output of the code",
    )
    libraries_used: List[str] = Field(
        ...,
        description="List of libraries used in the code with proper installing names separated by commas. Example: numpy,pandas,beautifulsoup4",
    )


class KubernetesExecutionTool(BaseTool):
    name: str = "Kubernetes Python Code Executor"
    description: str = (
        "Executes Python code in a secure, sandboxed Kubernetes environment. Use this for running code, testing scripts, or any execution that requires isolation. It captures and returns all output (stdout/stderr) from the script."
    )
    args_schema: Type[BaseModel] = KubernetesExecutionToolSchema

    def _run(self, code: str, libraries_used: List) -> str:
        """
        The tool's execution logic.

        It instantiates the executor and runs the provided code.
        """
        # You can make the executor configurable here if needed
        # e.g., executor = KubernetesCodeExecutor(image="my-custom-image-with-libs:latest")
        executor = KubernetesCodeExecutor()
        try:
            results = executor.run(code, libraries_used)
            return results
        except Exception as e:
            return f"An unexpected error occurred: {e}"
