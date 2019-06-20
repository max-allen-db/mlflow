"""
Internal package providing a Python CRUD interface to MLflow experiments and runs.
This is a lower level API than the :py:mod:`mlflow.tracking.fluent` module, and is
exposed in the :py:mod:`mlflow.tracking` module.
"""

import time
import datetime
from six import iteritems

from mlflow.store import SEARCH_MAX_RESULTS_DEFAULT
from mlflow.tracking import utils
from mlflow.utils.validation import _validate_param_name, _validate_tag_name, _validate_run_id, \
    _validate_experiment_artifact_location, _validate_experiment_name, _validate_metric
from mlflow.entities import Param, Metric, RunStatus, RunTag, ViewType
from mlflow.store.artifact_repository_registry import get_artifact_repository
from mlflow.utils.mlflow_tags import MLFLOW_USER
import numpy as np
import pandas as pd


class MlflowClient(object):
    """Client of an MLflow Tracking Server that creates and manages experiments and runs.
    """

    def __init__(self, tracking_uri=None):
        """
        :param tracking_uri: Address of local or remote tracking server. If not provided, defaults
                             to the service set by ``mlflow.tracking.set_tracking_uri``. See
                             `Where Runs Get Recorded <../tracking.html#where-runs-get-recorded>`_
                             for more info.
        """
        self.tracking_uri = tracking_uri or utils.get_tracking_uri()
        self.store = utils._get_store(self.tracking_uri)

    def get_run(self, run_id):
        """
        Fetch the run from backend store. The resulting :py:class:`Run <mlflow.entities.Run>`
        contains a collection of run metadata -- :py:class:`RunInfo <mlflow.entities.RunInfo>`,
        as well as a collection of run parameters, tags, and metrics --
        :py:class:`RunData <mlflow.entities.RunData>`. In the case where multiple metrics with the
        same key are logged for the run, the :py:class:`RunData <mlflow.entities.RunData>` contains
        the most recently logged value at the largest step for each metric.

        :param run_id: Unique identifier for the run.

        :return: A single :py:class:`mlflow.entities.Run` object, if the run exists. Otherwise,
                 raises an exception.
        """
        _validate_run_id(run_id)
        return self.store.get_run(run_id)

    def get_metric_history(self, run_id, key):
        """
        Return a list of metric objects corresponding to all values logged for a given metric.

        :param run_id: Unique identifier for run
        :param key: Metric name within the run

        :return: A list of :py:class:`mlflow.entities.Metric` entities if logged, else empty list
        """
        return self.store.get_metric_history(run_id=run_id, metric_key=key)

    def create_run(self, experiment_id, start_time=None, tags=None):
        """
        Create a :py:class:`mlflow.entities.Run` object that can be associated with
        metrics, parameters, artifacts, etc.
        Unlike :py:func:`mlflow.projects.run`, creates objects but does not run code.
        Unlike :py:func:`mlflow.start_run`, does not change the "active run" used by
        :py:func:`mlflow.log_param`.

        :param experiment_id: The ID of then experiment to create a run in.
        :param start_time: If not provided, use the current timestamp.
        :param tags: A dictionary of key-value pairs that are converted into
                     :py:class:`mlflow.entities.RunTag` objects.
        :return: :py:class:`mlflow.entities.Run` that was created.
        """

        tags = tags if tags else {}

        # Extract user from tags
        # This logic is temporary; the user_id attribute of runs is deprecated and will be removed
        # in a later release.
        user_id = tags.get(MLFLOW_USER, "unknown")

        return self.store.create_run(
            experiment_id=experiment_id,
            user_id=user_id,
            start_time=start_time or int(time.time() * 1000),
            tags=[RunTag(key, value) for (key, value) in iteritems(tags)]
        )

    def list_run_infos(self, experiment_id, run_view_type=ViewType.ACTIVE_ONLY):
        """:return: List of :py:class:`mlflow.entities.RunInfo`"""
        return self.store.list_run_infos(experiment_id, run_view_type)

    def list_experiments(self, view_type=None):
        """
        :return: List of :py:class:`mlflow.entities.Experiment`
        """
        final_view_type = ViewType.ACTIVE_ONLY if view_type is None else view_type
        return self.store.list_experiments(view_type=final_view_type)

    def get_experiment(self, experiment_id):
        """
        :param experiment_id: The experiment ID returned from ``create_experiment``.
        :return: :py:class:`mlflow.entities.Experiment`
        """
        return self.store.get_experiment(experiment_id)

    def get_experiment_by_name(self, name):
        """
        :param name: The experiment name.
        :return: :py:class:`mlflow.entities.Experiment`
        """
        return self.store.get_experiment_by_name(name)

    def create_experiment(self, name, artifact_location=None):
        """Create an experiment.

        :param name: The experiment name. Must be unique.
        :param artifact_location: The location to store run artifacts.
                                  If not provided, the server picks an appropriate default.
        :return: Integer ID of the created experiment.
        """
        _validate_experiment_name(name)
        _validate_experiment_artifact_location(artifact_location)
        return self.store.create_experiment(
            name=name,
            artifact_location=artifact_location,
        )

    def delete_experiment(self, experiment_id):
        """
        Delete an experiment from the backend store.

        :param experiment_id: The experiment ID returned from ``create_experiment``.
        """
        self.store.delete_experiment(experiment_id)

    def restore_experiment(self, experiment_id):
        """
        Restore a deleted experiment unless permanently deleted.

        :param experiment_id: The experiment ID returned from ``create_experiment``.
        """
        self.store.restore_experiment(experiment_id)

    def rename_experiment(self, experiment_id, new_name):
        """
        Update an experiment's name. The new name must be unique.

        :param experiment_id: The experiment ID returned from ``create_experiment``.
        """
        self.store.rename_experiment(experiment_id, new_name)

    def log_metric(self, run_id, key, value, timestamp=None, step=None):
        """
        Log a metric against the run ID. The timestamp defaults to the current timestamp.
        The step defaults to 0.
        """
        timestamp = timestamp if timestamp is not None else int(time.time())
        step = step if step is not None else 0
        _validate_metric(key, value, timestamp, step)
        metric = Metric(key, value, timestamp, step)
        self.store.log_metric(run_id, metric)

    def log_param(self, run_id, key, value):
        """
        Log a parameter against the run ID. Value is converted to a string.
        """
        _validate_param_name(key)
        param = Param(key, str(value))
        self.store.log_param(run_id, param)

    def set_tag(self, run_id, key, value):
        """
        Set a tag on the run ID. Value is converted to a string.
        """
        _validate_tag_name(key)
        tag = RunTag(key, str(value))
        self.store.set_tag(run_id, tag)

    def log_batch(self, run_id, metrics, params, tags):
        """
        Log multiple metrics, params, and/or tags.

        :param metrics: List of Metric(key, value, timestamp) instances.
        :param params: List of Param(key, value) instances.
        :param tags: List of RunTag(key, value) instances.

        Raises an MlflowException if any errors occur.
        :returns: None
        """
        for metric in metrics:
            _validate_metric(metric.key, metric.value, metric.timestamp, metric.step)
        for param in params:
            _validate_param_name(param.key)
        for tag in tags:
            _validate_tag_name(tag.key)
        self.store.log_batch(run_id=run_id, metrics=metrics, params=params, tags=tags)

    def log_artifact(self, run_id, local_path, artifact_path=None):
        """
        Write a local file to the remote ``artifact_uri``.

        :param local_path: Path to the file to write.
        :param artifact_path: If provided, the directory in ``artifact_uri`` to write to.
        """
        run = self.get_run(run_id)
        artifact_repo = get_artifact_repository(run.info.artifact_uri)
        artifact_repo.log_artifact(local_path, artifact_path)

    def log_artifacts(self, run_id, local_dir, artifact_path=None):
        """
        Write a directory of files to the remote ``artifact_uri``.

        :param local_dir: Path to the directory of files to write.
        :param artifact_path: If provided, the directory in ``artifact_uri`` to write to.
        """
        run = self.get_run(run_id)
        artifact_repo = get_artifact_repository(run.info.artifact_uri)
        artifact_repo.log_artifacts(local_dir, artifact_path)

    def list_artifacts(self, run_id, path=None):
        """
        List the artifacts for a run.

        :param run_id: The run to list artifacts from.
        :param path: The run's relative artifact path to list from. By default it is set to None
                     or the root artifact path.
        :return: List of :py:class:`mlflow.entities.FileInfo`
        """
        run = self.get_run(run_id)
        artifact_root = run.info.artifact_uri
        artifact_repo = get_artifact_repository(artifact_root)
        return artifact_repo.list_artifacts(path)

    def download_artifacts(self, run_id, path):
        """
        Download an artifact file or directory from a run to a local directory if applicable,
        and return a local path for it.

        :param run_id: The run to download artifacts from.
        :param path: Relative source path to the desired artifact.
        :return: Local path of desired artifact.
        """
        run = self.get_run(run_id)
        artifact_root = run.info.artifact_uri
        artifact_repo = get_artifact_repository(artifact_root)
        return artifact_repo.download_artifacts(path)

    def set_terminated(self, run_id, status=None, end_time=None):
        """Set a run's status to terminated.

        :param status: A string value of :py:class:`mlflow.entities.RunStatus`.
                       Defaults to "FINISHED".
        :param end_time: If not provided, defaults to the current time."""
        end_time = end_time if end_time else int(time.time() * 1000)
        status = status if status else RunStatus.to_string(RunStatus.FINISHED)
        self.store.update_run_info(run_id, run_status=RunStatus.from_string(status),
                                   end_time=end_time)

    def delete_run(self, run_id):
        """
        Deletes a run with the given ID.
        """
        self.store.delete_run(run_id)

    def restore_run(self, run_id):
        """
        Restores a deleted run with the given ID.
        """
        self.store.restore_run(run_id)

    def search_runs(self, experiment_ids, filter_string="",
                    run_view_type=ViewType.ACTIVE_ONLY,
                    max_results=SEARCH_MAX_RESULTS_DEFAULT,
                    order_by=None):
        """
        Search experiments that fit the search criteria.

        :param experiment_ids: List of experiment IDs, or a single int or string id.
        :param filter_string: Filter query string, defaults to searching all runs.
        :param run_view_type: one of enum values ACTIVE_ONLY, DELETED_ONLY, or ALL runs
                              defined in :py:class:`mlflow.entities.ViewType`.
        :param max_results: Maximum number of runs desired.
        :param order_by: List of columns to order by (e.g., "metrics.rmse"). The default
                         ordering is to sort by start_time DESC, then run_id.

        :return: A list of :py:class:`mlflow.entities.Run` objects that satisfy the search
            expressions
        """
        if isinstance(experiment_ids, int) or isinstance(experiment_ids, str):
            experiment_ids = [experiment_ids]
        return self.store.search_runs(experiment_ids=experiment_ids,
                                      filter_string=filter_string,
                                      run_view_type=run_view_type,
                                      max_results=max_results,
                                      order_by=order_by)

    def runs_to_pandas(self, runs):
        """
        Creates a pandas DataFrame from a list of :py:class:`mlflow.entities.Run` objects.

        Each run object has its own row in the DataFrame. There is a column for each
        of the following pieces of metadata:
        - (see below list)

        Additionally, each unique metric, parameter, and tag will have its own column
        in the DataFrame. Runs that don’t contain that metric, parameter, or tag will
        have a Nan, None, or None value filled in, respectively. The order of the columns
        are not guarenteed.

        For example, a metric named ‘loss’ would be accessible under the column
        ‘metrics.loss’. Similarly for parameters and tags as ‘params.*’ and ‘tags.*’.

        :param runs: a list of mlflow.entities.Run objects
        :return: pandas.DataFrame

        """
        info = {'date': [], 'run_id': [], 'run_name': [], 'parent_run_id': [], 'user_id': []}
        params, metrics, tags = ({}, {}, {})
        param_keys, metric_keys, tag_keys = (params.keys(), metrics.keys(), tags.keys())
        PARAM_NULL, METRIC_NULL, TAG_NULL = (None, np.nan, None)
        for i, run in enumerate(runs):
            # Break out the mlflow tags:
            info['date'].append(datetime.datetime.fromtimestamp(int(run.info.start_time / 1e3)))
            info['run_id'].append(run.info.run_id)
            info['run_name'].append(run.data.tags.get('mlflow.runName', None))
            info['parent_run_id'].append(run.data.tags.get('mlflow.parentRunId', None))
            info['user_id'].append(run.info.user_id)

            # Update params, metrics, and tags with appropriate value or None / np.nan
            # Check for additional params, metrics, tags that need to be added to the dataset.
            # Add appropriate null values for preceeding runs

            # Params
            for key in param_keys:
                if key in run.data.params:
                    params[key].append(run.data.params[key])
                else:
                    params[key].append(PARAM_NULL)
            new_params = run.data.params.keys() - param_keys
            for p in new_params:
                params[p] = [PARAM_NULL]*i  # Fill in null values for all previous runs
                params[p].append(run.data.params[p])

            # Metrics
            for key in metric_keys:
                if key in run.data.metrics:
                    metrics[key].append(run.data.metrics[key])
                else:
                    metrics[key].append(METRIC_NULL)
            new_metrics = run.data.metrics.keys() - metric_keys
            for m in new_metrics:
                metrics[m] = [METRIC_NULL]*i
                metrics[m].append(run.data.metrics[m])

            # Tags
            for key in tag_keys:
                if key in run.data.tags:
                    tags[key].append(run.data.tags[key])
                else:
                    tags[key].append(TAG_NULL)
            new_tags = run.data.tags.keys() - tag_keys
            for t in new_tags:
                if not t.startswith("mlflow."):
                    tags[t] = [TAG_NULL]*i
                    tags[t].append(run.data.tags[t])

        # Create the DataFrame object from all the dictionaries:
        # Rename columns of metrics, params, and tags to
        # metrics.<metric key>, params.<param key>, tags.<tag key>
        data = {}
        data.update(info)
        for key in metric_keys:
            data['metrics.' + key] = metrics[key]
        for key in param_keys:
            data['params.' + key] = params[key]
        for key in tag_keys:
            data['tags.' + key] = tags[key]
        return pd.DataFrame(data)
