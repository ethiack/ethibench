"""Dataset and target management."""

from pathlib import Path

import pydantic
import yaml
from loguru import logger


class Target(pydantic.BaseModel):
    """A test target identified by its target_id (directory name)."""

    target_id: str
    url: str = ""  # Optional reference, not used for matching.


class Dataset(pydantic.BaseModel):
    """A subset of targets sharing a common ground truth file."""

    subset: str
    targets: list[Target]
    weight: float = 1.0
    gt_file: str | None = None


class DatasetCollection:
    """Registry of all targets and subsets, loaded from a YAML file."""

    def __init__(self, datasets: list[Dataset] | None = None):
        self.datasets: list[Dataset] = datasets or []
        self._target_to_subset: dict[str, str] = {}

    def init_from_yaml(self, yaml_file: str | Path) -> None:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)
        self.datasets = [Dataset(**item) for item in data]
        self._build_index()

    def _build_index(self) -> None:
        """Build target_id → subset_name lookup."""
        self._target_to_subset = {}
        for dataset in self.datasets:
            for target in dataset.targets:
                self._target_to_subset[target.target_id] = dataset.subset

    def get_subset_for_target(self, target_id: str) -> str | None:
        """Return the subset name that owns *target_id*, or ``None``."""
        return self._target_to_subset.get(target_id)

    def get_all_target_ids(self) -> set[str]:
        """Return every registered target_id."""
        return set(self._target_to_subset.keys())

    def get_target_ids_for_subset(self, subset_name: str) -> set[str]:
        """Return target_ids registered for a given subset."""
        for dataset in self.datasets:
            if dataset.subset == subset_name:
                return {t.target_id for t in dataset.targets}
        return set()

    def extract_weights_dict(self) -> dict[str, float]:
        return {d.subset: d.weight for d in self.datasets}

    def get_gt_file_for_subset(self, subset_name: str) -> str | None:
        """Return the gt_file path for a subset, if configured."""
        for dataset in self.datasets:
            if dataset.subset == subset_name:
                return dataset.gt_file
        return None
