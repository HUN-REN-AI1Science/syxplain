"""
Visualization generators.

Implements the Strategy pattern for different types of plots.
Each generator is responsible for a specific visualization type.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Protocol
import base64
import io

from slurm_worker.logging_config import get_logger

logger = get_logger("visualization")


class DataFrame(Protocol):
    """Protocol for DataFrame-like objects (duck typing)."""
    def __getitem__(self, key: str) -> Any: ...


class VisualizationGenerator(ABC):
    """
    Abstract base class for visualization generators.

    Implements the Template Method pattern - subclasses override
    the _create_figure method while the generate method handles
    common serialization logic.
    """

    def __init__(self, dpi: int = 100, figsize: tuple = (5, 4)):
        """
        Initialize generator.

        Args:
            dpi: Figure DPI
            figsize: Figure size (width, height)
        """
        self.dpi = dpi
        self.figsize = figsize

    @abstractmethod
    def _create_figure(self, data: Dict[str, Any]) -> Any:
        """
        Create matplotlib figure.

        Args:
            data: Data for the visualization

        Returns:
            Matplotlib figure
        """
        pass

    @abstractmethod
    def get_filename(self, data: Dict[str, Any]) -> str:
        """
        Get filename for the visualization.

        Args:
            data: Data for the visualization

        Returns:
            Filename string
        """
        pass

    @abstractmethod
    def get_type(self) -> str:
        """Get visualization type identifier."""
        pass

    def generate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate visualization and encode as base64.

        Args:
            data: Data for the visualization

        Returns:
            Dict with filename, content_b64, and type
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        try:
            fig = self._create_figure(data)

            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=self.dpi)
            buf.seek(0)

            result = {
                "filename": self.get_filename(data),
                "content_b64": base64.b64encode(buf.getvalue()).decode(),
                "type": self.get_type(),
            }

            plt.close(fig)
            return result

        except Exception as e:
            logger.warning(f"Failed to generate {self.get_type()}: {e}")
            raise


class FeaturePlotGenerator(VisualizationGenerator):
    """Generates feature vs target scatter plots."""

    def get_type(self) -> str:
        return "feature_plot"

    def get_filename(self, data: Dict[str, Any]) -> str:
        feature = data["feature"]
        target = data["target"]
        return f"{feature}_vs_{target}.png"

    def _create_figure(self, data: Dict[str, Any]) -> Any:
        import matplotlib.pyplot as plt

        df = data["df"]
        feature = data["feature"]
        target = data["target"]

        fig, ax = plt.subplots(figsize=self.figsize)
        ax.scatter(df[feature], df[target], alpha=0.1)
        ax.set_xlabel(feature)
        ax.set_ylabel(target)
        ax.set_title(f"{feature} vs {target}")
        plt.tight_layout()

        return fig


class InteractionPlotGenerator(VisualizationGenerator):
    """Generates feature interaction scatter plots."""

    def get_type(self) -> str:
        return "interaction_plot"

    def get_filename(self, data: Dict[str, Any]) -> str:
        f1 = data["feature1"]
        f2 = data["feature2"]
        return f"{f1}_vs_{f2}_interaction.png"

    def _create_figure(self, data: Dict[str, Any]) -> Any:
        import matplotlib.pyplot as plt

        df = data["df"]
        f1 = data["feature1"]
        f2 = data["feature2"]

        fig, ax = plt.subplots(figsize=self.figsize)
        ax.scatter(df[f1], df[f2], alpha=0.1)
        ax.set_xlabel(f1)
        ax.set_ylabel(f2)
        ax.set_title(f"{f1} vs {f2}")
        plt.tight_layout()

        return fig


class VisualizationService:
    """
    Service for generating multiple visualizations.

    Coordinates visualization generation using the appropriate generators.
    """

    def __init__(self):
        """Initialize with default generators."""
        self._feature_gen = FeaturePlotGenerator()
        self._interaction_gen = InteractionPlotGenerator()

    def generate_feature_plots(
        self,
        df: DataFrame,
        target_column: str,
        predictor_columns: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Generate feature vs target plots.

        Args:
            df: Input DataFrame
            target_column: Target column name
            predictor_columns: List of predictor columns

        Returns:
            List of visualization dictionaries
        """
        logger.info(f"Generating {len(predictor_columns)} feature vs target plots")
        visualizations = []

        for col in predictor_columns:
            try:
                viz = self._feature_gen.generate({
                    "df": df,
                    "feature": col,
                    "target": target_column,
                })
                visualizations.append(viz)
            except Exception as e:
                logger.warning(f"Skipping plot for {col}: {e}")

        return visualizations

    def generate_interaction_plots(
        self,
        df: DataFrame,
        interactions: List[Dict[str, Any]],
        max_plots: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Generate interaction plots.

        Args:
            df: Input DataFrame
            interactions: List of interaction pairs
            max_plots: Maximum number of plots

        Returns:
            List of visualization dictionaries
        """
        interactions_to_plot = interactions[:max_plots]
        logger.info(f"Generating {len(interactions_to_plot)} interaction plots")
        visualizations = []

        for interaction in interactions_to_plot:
            try:
                viz = self._interaction_gen.generate({
                    "df": df,
                    "feature1": interaction["feature1"],
                    "feature2": interaction["feature2"],
                })
                visualizations.append(viz)
            except Exception as e:
                f1, f2 = interaction["feature1"], interaction["feature2"]
                logger.warning(f"Skipping interaction plot for {f1} vs {f2}: {e}")

        return visualizations

    def generate_all(
        self,
        df: DataFrame,
        target_column: str,
        predictor_columns: List[str],
        interactions: List[Dict[str, Any]],
        max_interaction_plots: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Generate all visualizations.

        Args:
            df: Input DataFrame
            target_column: Target column name
            predictor_columns: List of predictor columns
            interactions: List of interaction pairs
            max_interaction_plots: Maximum interaction plots

        Returns:
            List of all visualization dictionaries
        """
        visualizations = []

        visualizations.extend(
            self.generate_feature_plots(df, target_column, predictor_columns)
        )
        visualizations.extend(
            self.generate_interaction_plots(df, interactions, max_interaction_plots)
        )

        logger.info(f"Generated {len(visualizations)} total visualizations")
        return visualizations
